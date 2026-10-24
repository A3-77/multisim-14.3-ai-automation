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
import json
import os
import sys
import uuid
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel

BLANK = os.path.join(ROOT, "out", "ref", "blank_circuit.xml")
INDEX_PATH = os.path.join(ROOT, "corpus", "samples_index.json")


# ---------------------------------------------------------------- 样例库索引
_INDEX = {}
_CIRCUITS = {}


def part_index():
    """{(family, part): [(样例 cache 路径, 位号), ...]}，按样例出现顺序去重。

    数据源 corpus/samples_index.json（108 个官方样例的元件清单），
    cache 是解压后的明文 XML，可直接喂 msmodel。
    """
    if "idx" in _INDEX:
        return _INDEX["idx"]
    idx = {}
    try:
        data = json.load(open(INDEX_PATH, encoding="utf-8"))
    except Exception:
        data = []
    for entry in data:
        cache = entry.get("cache")
        if not cache or not os.path.exists(cache):
            continue
        for comp in entry.get("components") or []:
            key = ((comp.get("family") or ""), (comp.get("part") or ""))
            ref = (comp.get("name") or "").replace("&ASC", "")
            if not ref:
                continue
            lst = idx.setdefault(key, [])
            if (cache, ref) not in lst:
                lst.append((cache, ref))
    _INDEX["idx"] = idx
    return idx


def find_part(family, part=None):
    """按 (family, part) 找第一个可用样例元件，返回 (cache 路径, 位号)。

    part 传 None 表示"这个家族里随便哪个"。找不到返回 None。
    """
    idx = part_index()
    if part is None:
        for (f, _p), lst in sorted(idx.items()):
            if f.upper() == (family or "").upper() and lst:
                return lst[0]
        return None
    if (family, part) in idx:
        return idx[(family, part)][0]
    fl, pl = (family or "").lower(), (part or "").lower()
    for (f, p), lst in idx.items():
        if (f or "").lower() == fl and (p or "").lower() == pl:
            return lst[0]
    return None


def load_donor(path):
    """加载并缓存 donor 电路（.ms14 压缩包或明文 XML 都行，也可直接传 Circuit）。"""
    if isinstance(path, msmodel.Circuit):
        return path
    key = os.path.abspath(path)
    if key not in _CIRCUITS:
        try:
            _CIRCUITS[key] = msmodel.Circuit.load(key)
        except Exception:
            _CIRCUITS[key] = msmodel.Circuit.from_xml_file(key)
    return _CIRCUITS[key]



def _fresh_guid():
    return "{%s}" % str(uuid.uuid4()).upper()


def node_attributes():
    """新建 CiNode 的 Attributes 模板（36 槽，实测自 samples/7812.ms12 的真实 CiNode）。

    **关键**：只写空 <Attributes /> 会导致 Multisim 不认这个网络，
    探针无法注册成 COM output（EnumOutputs 返回空）。
    槽位含义（实测）：
        [2]  CiaParamList  6 个 doubles: 0,0,0,0,-1,1
        [9]  CiaDisplay
        [14] CiaDOUBLE 1.
        [19] CiaCString ""
        [22..35] CiaDOUBLE -1.
    """
    at = ET.Element("Attributes")
    for _ in range(2):
        ET.SubElement(at, "Item")
    pl = ET.SubElement(at, "Item")
    CiaParamList = ET.SubElement(pl, "CiaParamList")
    CiaParamList.set("Class", "CiaParamList")
    doubles = ET.SubElement(CiaParamList, "doubles")
    for v in ("0.", "0.", "0.", "0.", "-1.", "1."):
        i = ET.SubElement(doubles, "Item")
        i.set("Value", v)
    ET.SubElement(CiaParamList, "strings")
    for _ in range(6):
        ET.SubElement(at, "Item")
    d = ET.SubElement(at, "Item")
    CiaDisplay = ET.SubElement(d, "CiaDisplay")
    for k, v in (("Class", "CiaDisplay"), ("ShowLabels", "1"), ("ShowValues", "1"),
                 ("ShowReferenceID", "0"), ("ShowCompIC", "1"), ("ShowCompTol", "1")):
        CiaDisplay.set(k, v)
    for _ in range(4):
        ET.SubElement(at, "Item")
    d = ET.SubElement(at, "Item")
    CiaDOUBLE = ET.SubElement(d, "CiaDOUBLE")
    CiaDOUBLE.set("Class", "CiaDOUBLE")
    CiaDOUBLE.set("Double", "1.")
    for _ in range(4):
        ET.SubElement(at, "Item")
    s = ET.SubElement(at, "Item")
    CiaCString = ET.SubElement(s, "CiaCString")
    CiaCString.set("Class", "CiaCString")
    CiaCString.set("String", "")
    for _ in range(2):
        ET.SubElement(at, "Item")
    for _ in range(14):
        d = ET.SubElement(at, "Item")
        CiaDOUBLE = ET.SubElement(d, "CiaDOUBLE")
        CiaDOUBLE.set("Class", "CiaDOUBLE")
        CiaDOUBLE.set("Double", "-1.")
    return at


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
        # **关键**：CiComponent/Ports 列表里存的是引脚 CiID，深拷贝后仍是 donor
        # 的旧 ID。必须清空并改写成新克隆端口的 CiID，否则 Multisim 加载后
        # 元件引脚全部悬空——网络表建不起来，仿真无输出，探针也不注册。
        ports_el = inner.find("Ports")
        if ports_el is None:
            ports_el = ET.SubElement(inner, "Ports")
        else:
            for ch in list(ports_el):
                ports_el.remove(ch)
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
            it = ET.SubElement(ports_el, "Item")
            it.set("CiID", new_pid)
            port_ids.append((new_pid, (pin.get("LocalName") or "").replace("&ASC", "")))

        # 绘图 + 引脚定义
        if donor.sym_item is not None:
            sym = copy.deepcopy(donor.sym_item)
            sym.set("ID", self.new_id())
            for el in sym.iter():
                if el.get("CiComponent") == old_ciid:
                    el.set("CiComponent", new_ciid)
            # **关键（P11 修复）**：CIITPinSymbolComp@PortID 指向 CiPort 的 CiID。
            # 深拷贝后它仍是 donor 的旧端口 ID，目标电路里不存在这个对象，
            # 引脚符号与电气端口就脱钩了 —— 元件看着在、属性全对，
            # 但 Multisim 建不出网表，仿真报「输出未找到」、RLCValue 报未指定错误。
            port_name_to_id = {name: pid for pid, name in port_ids}
            for el in sym.iter("CIITPinSymbolComp"):
                pname = (el.get("PinName") or "").replace("&ASC", "")
                if pname in port_name_to_id:
                    el.set("PortID", port_name_to_id[pname])
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

    def add_part(self, family, part, refdes, value=None, x=None, y=None,
                 donor_path=None, donor_refdes=None):
        """统一元件入口：按 (family, part) 从样例库找模板，克隆进当前电路。

        与 add() 的区别只在"找模板"这一步：add() 要求调用方自己给 Donor，
        这里给家族/型号字符串就行（如 add_part("RESISTOR","RESISTOR_VIRTUAL","R1",1000)）。

        参数：
            family, part  样例索引里的家族/型号；part=None 表示该家族任意型号
            refdes        新位号（如 "R1"）
            value         元件主参数，走 set_value_by_refdes 写（None 表示沿用模板值）
            x, y          放置位置（元件原点）；None 表示沿用模板坐标
            donor_path    指定 donor（路径或 Circuit）；给了就忽略索引
            donor_refdes  指定 donor 里的位号（配合 donor_path）

        返回 (新 CiID, [(引脚CiID, 引脚名), ...])，与 add() 一致。
        克隆沿用 add() 里已修好的 PortID / ConnectList / Circuit / Model 重映射。
        """
        if donor_path is None:
            hit = find_part(family, part)
            if hit is None:
                raise KeyError("样例库里没有 (%r, %r)" % (family, part))
            donor_path, donor_refdes = hit[0], hit[1]
        elif donor_refdes is None:
            raise ValueError("给了 donor_path 就必须同时给 donor_refdes")

        donor_circuit = load_donor(donor_path)
        d = Donor(donor_circuit, donor_refdes)
        ciid, ports = self.add(d, x=x, y=y, refdes=refdes)
        if value is not None:
            self.c.set_value_by_refdes(refdes, value)

        # 记一笔来源，方便调用方写报告
        self.last_part = {"family": family, "part": part, "refdes": refdes,
                          "donor": str(donor_path), "donor_refdes": donor_refdes,
                          "donor_family": d.family, "donor_part": d.part,
                          "value": value, "ciid": ciid}
        return ciid, ports

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
        node.append(node_attributes())      # ← 完整属性，不能是空的
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

    # ---------- 老式电压/电流探针 ----------
    def add_probe(self, net_name, x, y, kind="V", name=None, donor_path=None,
                  donor_index=0):
        """克隆一个老式探针（CIITProbeComponent + CiProbeComp），绑到指定网络。

        老式探针靠**显式 NetName** 绑网络，但 COM 的 EnumOutputs 还要求
        探针的 Transformer-M20/M21 **精确落在那条网络的导线顶点（或引脚）上**，
        落在线段中间不会注册成 output。

        参数：
            net_name   网络名（CiNode 的 LocalName，不带 &ASC 前缀），如 "1"
            x, y       探针位置，必须是该网络导线的一个顶点
            kind       "V" 或 "I"（目前都克隆同一个对象，靠 Multisim 自己区分）
            name       探针名，默认 Probe1/Probe2... 自动编号
            donor_path 探针模板来源，默认 samples/7812.ms12
        返回 (新电气 CiID, 新绘图 ID)
        """
        donor_path = donor_path or os.path.join(ROOT, "samples", "7812.ms12")
        donor = msmodel.Circuit.load(donor_path)

        # 找第 donor_index 个老式探针
        draws = []
        for e in donor.objects:
            inner = list(e)
            if inner and inner[0].get("Class") == "CIITProbeComponent":
                draws.append(e)
        elecs = [e for e in donor.elements if e.get("Class") == "CiProbeComp"]
        if not draws or not elecs:
            raise RuntimeError("donor %s 里没有老式探针" % donor_path)
        draw, elec = draws[donor_index], elecs[donor_index]
        di = draw.find("CIITProbeComponent")
        ei = elec.find("CiProbeComp")

        # donor 的引脚定义
        donor_defs = {}
        rc = donor.diagram.find("Components/CODComposite/ReferencedComponents")
        if rc is not None:
            for it in rc:
                if it.get("ID"):
                    donor_defs[it.get("ID")] = it

        old_pos = (float(di.get("Transformer-M20")), float(di.get("Transformer-M21")))
        dx, dy = x - old_pos[0], y - old_pos[1]

        # 目标容器
        tgt_rc = self.c.diagram.find("Components/CODComposite/ReferencedComponents")
        if tgt_rc is None:
            tgt_rc = ET.SubElement(self.c.diagram.find("Components/CODComposite"),
                                   "ReferencedComponents")
        circuit_inner = None
        circuit_ciid = None
        for e in self.c.elements:
            if e.get("Class") == "CiCircuit":
                circuit_inner = e.find("CiCircuit")
                circuit_ciid = e.get("CiID")     # CiID 在外层 Item 上
                break
        if circuit_inner is None:
            raise RuntimeError("目标电路没有 CiCircuit")
        probes_node = circuit_inner.find("Probes")
        if probes_node is None:
            probes_node = ET.SubElement(circuit_inner, "Probes")

        # 1) 引脚定义（复制 + 平移）
        # 新绘图对象 ID 先分配：引脚定义内部的 ConnectList 指向探针绘图对象，
        # 深拷贝后仍是 donor 旧 ID，必须改写成新的，否则 Multisim 丢弃整个探针。
        new_draw_id = self.new_id()
        new_def_map = {}
        conn = di.find(".//ConnectList")
        def_ids = [i.get("ID") for i in conn.findall("Item")] if conn is not None else []
        for old_id in def_ids:
            src = donor_defs.get(old_id)
            if src is None:
                continue
            nd = copy.deepcopy(src)
            nid = self.new_id()
            nd.set("ID", nid)
            inner = list(nd)[0]
            inner.set("CenterX", "%g" % (_f(inner.get("CenterX")) + dx))
            inner.set("CenterY", "%g" % (_f(inner.get("CenterY")) + dy))
            for cl in nd.iter("ConnectList"):
                for it2 in cl.findall("Item"):
                    if it2.get("Class") == "CIITProbeComponent":
                        it2.set("ID", new_draw_id)
            tgt_rc.append(nd)
            new_def_map[old_id] = nid

        # 2) 绘图对象
        new_draw = copy.deepcopy(draw)
        new_draw.set("ID", new_draw_id)
        ndi = new_draw.find("CIITProbeComponent")
        ndi.set("Transformer-M20", "%g." % x)
        ndi.set("Transformer-M21", "%g." % y)
        ndi.set("NetName", "&ASC" + net_name)
        for it in ndi.findall(".//ConnectList/Item"):
            if it.get("ID") in new_def_map:
                it.set("ID", new_def_map[it.get("ID")])
        self.objs.append(new_draw)

        # 3) 电气对象
        new_elec = copy.deepcopy(elec)
        new_ciid = self.new_id()
        new_elec.set("CiID", new_ciid)
        nei = new_elec.find("CiProbeComp")
        nei.set("SymCompID", new_draw_id)
        ndi.set("CiProbeComp", new_ciid)
        nei.set("Circuit", circuit_ciid)
        nei.set("InstanceID", "&ASC" + _fresh_guid())
        if name is None:
            name = "Probe%d" % (len(probes_node) + 1)
        nei.set("LocalName", "&ASC" + name)
        at = nei.find("Attributes")
        if at is not None and len(list(at)) > 5:
            for cs in at[5].iter("CiaCollString"):
                items = cs.find("strings")
                if items is not None and len(list(items)) > 4:
                    list(items)[4].set("Value", "&ASC" + name + "%d")
        self.els.append(new_elec)

        # 4) 注册
        it = ET.SubElement(probes_node, "Item")
        it.set("CiID", new_ciid)

        # 5) triggers（donor 有就抄，NextProbeID 顺延）
        src_tpt = None
        for e in donor.tree.iter():
            if (e.get("Class") or "").endswith("CTotalProbeTriggers"):
                src_tpt = e
                break
        if src_tpt is not None:
            tpt = copy.deepcopy(src_tpt)
            try:
                nxt = int(tpt.get("NextProbeID") or "1") + 1
            except ValueError:
                nxt = 2
            tpt.set("NextProbeID", str(nxt))
            for e in tpt.iter():
                if e.tag == "InstProbeTriggers":
                    e.set("ProbeID", str(len(probes_node)))
            self.c.diagram.append(tpt)

        return new_ciid, new_draw_id
