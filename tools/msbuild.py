# -*- coding: utf-8 -*-
"""从样例电路里"克隆元件"到空白电路，组装新电路。

核心思路：不手写符号几何，而是从真实电路里复制元件的完整对象子树
（电气对象 CiComponent + 引脚 CiPort + 模型 CiModel + 绘图对象 CIITSymbolComp），
换一套新 ID、平移坐标、改位号和参数，再插进目标电路，最后补上导线。

关键结构（已验证）：
    元件位置        = 绘图子对象上的 Transformer-M20/M21
    引脚绝对坐标    = 引脚符号变换矩阵 × 局部连接点 (ptCenterX, ptCenterY)
    引脚引用        = CIITPinSymbolComp/ConnectList/Item@ID -> ReferencedComponents/CODPinComp
    导线            = Objects/Item[CIITLinkComp]，Points 相对 Transformer，Node 指向 CiNode
"""
import copy
import os
import sys
import uuid
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

BLANK = os.path.join(ROOT, "out", "ref", "blank_circuit.xml")


def _fresh_guid():
    return "{%s}" % str(uuid.uuid4()).upper()


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


class Donor:
    """一个元件模板（来自真实电路）。"""

    def __init__(self, circuit, refdes):
        self.circuit = circuit
        c = circuit.find(refdes)
        self.ciid = c["ciid"]
        self.refdes = refdes
        self.family = c["family"]
        self.part = c["part"]
        self.comp_item = circuit._item_of(self.ciid)
        self.port_items = [p["node"] for p in circuit.ports() if p["component"] == self.ciid]
        self.sym_item = circuit.symbol_of(self.ciid)
        self.model_ciid = self.comp_item.find("CiComponent").get("Model")
        self.model_item = None
        if self.model_ciid:
            for e in circuit.elements:
                if e.get("CiID") == self.model_ciid:
                    self.model_item = e
                    break
        self.pos = circuit.position(self.ciid)
        self.params = circuit.params(self.comp_item.find("CiComponent"))

        # 引脚定义原件（CODPinComp），供克隆时平移复制
        self.pin_def_items = {}
        rc = circuit.diagram.find("Components/CODComposite/ReferencedComponents")
        if rc is not None:
            for it in rc:
                if it.get("ID"):
                    self.pin_def_items[it.get("ID")] = it

    def describe(self):
        return {"refdes": self.refdes, "family": self.family, "part": self.part,
                "ports": len(self.port_items), "symbol": self.sym_item is not None,
                "model": self.model_item is not None, "pos": self.pos,
                "params": self.params[:4]}


class Assembler:
    def __init__(self, base_path=BLANK):
        self.c = msmodel.Circuit.from_xml_file(base_path)
        self.els = self.c.elements
        self.objs = self.c.objects
        self.refcomp = self.c.diagram.find("Components/CODComposite/ReferencedComponents")
        self.circuit_item = self.c.circuit_item
        self.circuit_inner = self.circuit_item.find("CiCircuit")
        self.circuit_ciid = self.circuit_item.get("CiID")

    # ---------- 克隆元件 ----------
    def add(self, donor, x=None, y=None, refdes=None, params=None):
        """把 donor 元件放到 (x, y)，返回 (新 CiID, [(引脚CiID, 引脚名)...])。"""
        comp = copy.deepcopy(donor.comp_item)
        old_ciid = donor.ciid
        new_ciid = self.new_id()
        comp.set("CiID", new_ciid)
        inner = comp.find("CiComponent")
        inner.set("Circuit", self.circuit_ciid)
        inner.set("InstanceID", _fresh_guid())

        dx = dy = 0.0
        if x is not None and y is not None and donor.pos is not None:
            dx, dy = x - donor.pos[0], y - donor.pos[1]

        # 模型
        if donor.model_item is not None:
            m = copy.deepcopy(donor.model_item)
            new_model = self.new_id()
            m.set("CiID", new_model)
            mi = m.find("CiModel")
            if mi is not None:
                mi.set("Scope", self.circuit_ciid)
            self.els.append(m)
            self._append_ref(self.circuit_inner, "Models", new_model)
            inner.set("Model", new_model)

        # 引脚（电气）
        port_ids = []
        for pi in donor.port_items:
            p = copy.deepcopy(pi)
            new_pid = self.new_id()
            p.set("CiID", new_pid)
            pin = p.find("CiPort")
            pin.set("Component", new_ciid)
            nd = pin.find("Nodes")
            if nd is not None:
                for ch in list(nd):
                    nd.remove(ch)
            self.els.append(p)
            port_ids.append((new_pid, (pin.get("LocalName") or "").replace("&ASC", "")))

        # 绘图 + 引脚定义
        if donor.sym_item is not None:
            sym = copy.deepcopy(donor.sym_item)
            sym.set("ID", self.new_id())
            for el in sym.iter():
                if el.get("CiComponent") == old_ciid:
                    el.set("CiComponent", new_ciid)
            for el in sym.iter():
                px, py = el.get("Transformer-M20"), el.get("Transformer-M21")
                if px is not None and py is not None:
                    el.set("Transformer-M20", "%g." % (_f(px) + dx))
                    el.set("Transformer-M21", "%g." % (_f(py) + dy))

            # 把引脚引用的 CODPinComp 定义也复制一份并平移
            refs = []
            for el in sym.iter():
                if el.tag == "ConnectList":
                    for it in el.findall("Item"):
                        if it.get("ID"):
                            refs.append(it)
            pin_map = {}
            for it in refs:
                old = it.get("ID")
                if old not in pin_map:
                    src = donor.pin_def_items.get(old)
                    if src is None:
                        continue
                    new_def = copy.deepcopy(src)
                    nid = self.new_id()
                    new_def.set("ID", nid)
                    di = list(new_def)[0]
                    di.set("CenterX", "%g" % (_f(di.get("CenterX")) + dx))
                    di.set("CenterY", "%g" % (_f(di.get("CenterY")) + dy))
                    self.refcomp.append(new_def)
                    pin_map[old] = nid
                it.set("ID", pin_map[old])

            self.objs.append(sym)
            inner.set("SymCompID", sym.get("ID"))

        self.els.append(comp)
        self._append_ref(self.circuit_inner, "Components", new_ciid)

        if refdes:
            self.c.set_refdes(new_ciid, refdes)
        if params:
            for idx, val in params.items():
                self.c.set_param(inner, idx, val)
        return new_ciid, port_ids

    def new_id(self):
        return self.c.new_id()

    @staticmethod
    def _append_ref(parent, tag, ciid):
        node = parent.find(tag)
        if node is None:
            node = ET.SubElement(parent, tag)
        it = ET.SubElement(node, "Item")
        it.set("CiID", ciid)
        return it

    # ---------- 连线 ----------
    def connect(self, ports, name=""):
        """ports: [(元件CiID, 引脚名), ...]，建一个节点并把相邻引脚用导线串起来。"""
        node_id = self.new_id()
        item = ET.SubElement(self.els, "Item")
        item.set("CiID", node_id)
        item.set("Class", "CiNode")
        node = ET.SubElement(item, "CiNode")
        node.set("Class", "CiNode")
        node.set("LocalName", "&ASC" + name)
        node.set("Circuit", self.circuit_ciid)
        ET.SubElement(node, "Attributes")
        ports_el = ET.SubElement(node, "Ports")

        index = {(p["component"], p["name"]): p for p in self.c.ports()}
        resolved = []
        for comp_ciid, pin in ports:
            p = index.get((comp_ciid, pin))
            if p is None:
                raise KeyError("找不到引脚 %s.%s" % (comp_ciid, pin))
            r = ET.SubElement(ports_el, "Item")
            r.set("CiID", p["ciid"])
            nd = p["port"].find("Nodes")
            if nd is None:
                nd = ET.SubElement(p["port"], "Nodes")
            n = ET.SubElement(nd, "Item")
            n.set("CiID", node_id)
            resolved.append((comp_ciid, pin))

        self._append_ref(self.circuit_inner, "Nodes", node_id)

        # 相邻引脚之间画导线
        for i in range(len(resolved) - 1):
            self.wire(node_id, resolved[i], resolved[i + 1])
        return node_id

    def wire(self, node_id, a, b, color="0"):
        """在两个引脚之间画一条正交导线。"""
        pa = self.c.pin_info(a[0]).get(a[1])
        pb = self.c.pin_info(b[0]).get(b[1])
        if not pa or not pb:
            return None
        (x1, y1), (x2, y2) = pa["xy"], pb["xy"]
        if abs(x1 - x2) < 0.5 or abs(y1 - y2) < 0.5:
            pts = [(x1, y1), (x2, y2)]
        else:
            pts = [(x1, y1), (x2, y1), (x2, y2)]

        item = ET.SubElement(self.objs, "Item")
        item.set("ID", self.new_id())
        item.set("Class", "CIITLinkComp")
        lnk = ET.SubElement(item, "CIITLinkComp")
        for k, v in (("Class", "CIITLinkComp"), ("instID", "0"),
                     ("Stretchable", "1"), ("Moveable", "1"),
                     ("LabelSelectable", "1"), ("Selectable", "1"),
                     ("LockedPenColor", "0"), ("LockedBrushColor", "0"),
                     ("Layer", "511"), ("ArrowAtSource", "0"), ("ArrowAtTarget", "0"),
                     ("LineHidden", "0"), ("PenColor", color), ("FgColor", "0"),
                     ("BgColor", "16777215"), ("Pen-Style", "0"), ("Pen-Width", "1"),
                     ("Pen-Color", color),
                     ("Transformer-M00", "1."), ("Transformer-M01", "0."),
                     ("Transformer-M10", "0."), ("Transformer-M11", "1."),
                     ("Transformer-M20", "0."), ("Transformer-M21", "0."),
                     ("Hidden", "0"), ("ShowWhenNetSet", "0")):
            lnk.set(k, v)
        lnk.set("Connect1", pa["def_ids"][0] if pa["def_ids"] else "")
        lnk.set("Connect2", pb["def_ids"][0] if pb["def_ids"] else "")
        lnk.set("IsElvisHiddenWireFlags", "0")
        lnk.set("Node", node_id)
        pts_el = ET.SubElement(lnk, "Points")
        for x, y in pts:
            p = ET.SubElement(pts_el, "Item")
            p.set("X", "%g" % x)
            p.set("Y", "%g" % y)
        eo = ET.SubElement(lnk, "ElectricalObject")
        eo.set("HiddenName", "0")
        mi = ET.SubElement(eo, "ModifierInfo")
        el = ET.SubElement(mi, "Element")
        el.set("NetModifier", "&ASCNI_EWB_NET_AUTONAMED")
        it = ET.SubElement(el, "Item")
        it.set("Value", "")
        it.set("Guid", _fresh_guid())
        return item

    def save(self, path):
        return self.c.save(path)
