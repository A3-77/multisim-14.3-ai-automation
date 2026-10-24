# -*- coding: utf-8 -*-
"""Multisim 电路 XML 的对象模型层。

结构速查（以 CIITDiagram 为根）：
    Elements/Item[Class=CiComponent]   元件（电气）
        CiComponent@LocalName          位号，如 &ASCR1
        CiComponent@SymCompID          指向绘图对象（可能悬空，不可靠）
        CiComponent/Attributes/Item[i] 属性槽，i 的含义见下
            [2] CiaParamList/doubles   参数值（#1 是主参数）
            [4] CiaCollString          家族/型号：RESISTOR, RESISTOR_VIRTUAL, ...
    Elements/Item[Class=CiPort]        引脚
        CiPort@Component               属于哪个元件（CiComponent 的 CiID）
    Elements/Item[Class=CiNode]        网络
        CiNode/Ports/Item@CiID         连了哪些引脚
    Elements/Item[Class=CiCircuit]     电路根，用 CiID 索引 Models/Nodes/Probes/Components
    Components/CODComposite/Objects    绘图对象
        Item/CIITSymbolComp@CiComponent 属于哪个元件
            子对象上的 Transformer-M20/M21 = 元件绝对位置
            Transformer-M00/M01/M10/M11  = 旋转/镜像

坐标单位：与符号局部坐标一致（元件宽约 27 单位），栅格通常 9。
"""
import copy
import os
import re
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dcl

P = "{http://none}"  # 占位，本文件 XML 无命名空间

ATTR_PARAMS = 2
ATTR_IDENT = 4


def _txt(v, default=""):
    """属性值归一化：去掉空值。"""
    return v if v else default


def _flt(s, default=0.0):
    """宽容的浮点解析。

    官方样例里坐标写法不统一：既有 "455." 也有 "455.369."（双尾点，来自高精度存盘），
    直接 float() 会抛 ValueError。这里先原样试，再剥掉尾部多余的点。
    """
    if s is None:
        return default
    try:
        return float(s)
    except (TypeError, ValueError):
        try:
            return float(str(s).strip().rstrip("."))
        except (TypeError, ValueError):
            return default


# 工程记数法前缀（10^3 一档），与 Multisim 的显示规则一致
_PREFIX = [
    (-12, "p"), (-9, "n"), (-6, "u"), (-3, "m"), (0, ""),
    (3, "k"), (6, "M"), (9, "G"), (12, "T"),
]


def eng(value, digits=4):
    """把数值格式化成 Multisim 的人类可读形式：1000 -> "1k"，0.0005 -> "500u"。

    规则来自 108 个官方样例的实测统计（76 组数值/显示配对）：
    尾数落在 [1,1000)，最多 4 位有效数字，去掉多余的 0。
    """
    v = float(value)
    if v == 0:
        return "0"
    neg = v < 0
    v = abs(v)
    exp = 0
    for e, _ in _PREFIX:
        if v >= 10.0 ** e:
            exp = e
    mant = v / (10.0 ** exp)
    # 修正边界：999.96 会四舍五入成 1000，应进位到下一档
    if round(mant, digits - 1) >= 1000.0:
        exp += 3
        mant = v / (10.0 ** exp)
    s = "%.*g" % (digits, mant)
    if "e" in s or "E" in s:
        s = ("%.*f" % (digits, mant)).rstrip("0").rstrip(".")
    suf = ""
    for e, p in _PREFIX:
        if e == exp:
            suf = p
            break
    return ("-" if neg else "") + s + suf


def _num_str(value):
    """数值槽的写法：Multisim 用 "1000." 这种带尾点的十进制。"""
    v = float(value)
    s = "%.10g" % v
    if "e" not in s and "E" not in s and "." not in s:
        s += "."
    return s


class Circuit:
    def __init__(self, xml_bytes):
        self.raw = xml_bytes
        self.tree = ET.fromstring(xml_bytes)
        self.diagram = self.tree.find(".//CIITDiagram")
        if self.diagram is None:
            raise ValueError("找不到 CIITDiagram")
        self.elements = self.diagram.find("Elements")
        self.objects = self.diagram.find("Components/CODComposite/Objects")
        self.circuit_item = self._one("CiCircuit")
        self._reseed()

    # ---------- 基础 ----------
    @staticmethod
    def load(path):
        xml, info = dcl.read_ms14(path)
        c = Circuit(xml)
        c.source = path
        c.info = info
        return c

    @staticmethod
    def from_xml_file(path):
        """从解压后的明文 XML 读（样例缓存就是这种）。"""
        c = Circuit(open(path, "rb").read())
        c.source = path
        return c

    def save(self, path, matches=True):
        xml = ET.tostring(self.tree, encoding="ascii", xml_declaration=True)
        return dcl.write_ms14(path, xml, matches=matches)

    def _reseed(self):
        """收集已用 ID，后续分配新 ID 时避开。"""
        self.used = set()
        for el in self.tree.iter():
            for a in ("CiID", "ID"):
                v = el.get(a)
                if v and v.isdigit():
                    self.used.add(int(v))
        self._next = max(self.used) + 8 if self.used else 1000

    def new_id(self):
        self._next += 8
        while self._next in self.used:
            self._next += 8
        self.used.add(self._next)
        return str(self._next)

    # ---------- 查询 ----------
    def _one(self, cls):
        for e in self.elements:
            if e.get("Class") == cls:
                return e
        return None

    def all_items(self, cls):
        return [e for e in self.elements if e.get("Class") == cls]

    def _item_of(self, ciid):
        """按 CiID 取 Elements 下的 Item。"""
        for e in self.elements:
            if e.get("CiID") == ciid:
                return e
        raise KeyError("没有 CiID=%r 的元素" % ciid)

    def components(self):
        out = []
        for e in self.elements:
            if e.get("Class") != "CiComponent":
                continue
            c = e.find("CiComponent")
            out.append({
                "ciid": e.get("CiID"),
                "refdes": _txt(c.get("LocalName")).replace("&ASC", ""),
                "family": self.ident(c)[0],
                "part": self.ident(c)[1],
                "node": e, "comp": c,
            })
        return out

    def find(self, refdes):
        for c in self.components():
            if c["refdes"] == refdes:
                return c
        raise KeyError("没有位号 %r" % refdes)

    @staticmethod
    def ident(comp):
        """(家族, 型号)，取自 Attributes[4] 的 CiaCollString。"""
        attrs = comp.find("Attributes")
        if attrs is None or len(attrs) <= ATTR_IDENT:
            return "", ""
        for cs in attrs[ATTR_IDENT].iter("CiaCollString"):
            vals = [(i.get("Value") or "").replace("&ASC", "") for i in cs.iter("Item")]
            vals = [v for v in vals if v.strip()]
            if vals:
                return vals[0], (vals[1] if len(vals) > 1 else "")
        return "", ""

    def params(self, comp):
        """返回 CiaParamList 的 doubles 列表（字符串）。"""
        attrs = comp.find("Attributes")
        if attrs is None or len(attrs) <= ATTR_PARAMS:
            return []
        out = []
        for d in attrs[ATTR_PARAMS].iter("Item"):
            v = d.get("Value")
            if v is not None:
                out.append(v)
        return out

    def set_param(self, comp, idx, value):
        attrs = comp.find("Attributes")
        items = [d for d in attrs[ATTR_PARAMS].iter("Item") if d.get("Value") is not None]
        items[idx].set("Value", value)

    # ---------- 元件值（四处同步） ----------
    def set_value(self, comp, value, human=None, idx=1):
        """把元件主参数改成 value，并同步所有副本。

        Multisim 把同一个值存了四份，只改一份不会生效：
            [2]/CiaParamList/doubles[idx]      数值        "1000."
            [2]/CiaParamList/parameters[idx]   人类可读    "&ASC1k"
            [41]/CiaCString@String             权威副本    "&ASC1k"
            [42]/CiaCString@String             显示缓存    "&UNI1k_uc103a9"
        外加绘图对象 CIITSymTextCompValue@Output = [42]。
        """
        attrs = comp.find("Attributes")
        items = list(attrs)
        pl = items[ATTR_PARAMS].find("CiaParamList")

        # 1) 数值
        doubles = pl.find("doubles")
        nums = doubles.findall("Item")
        if idx >= len(nums):
            raise IndexError("参数索引 %d 越界（只有 %d 个）" % (idx, len(nums)))
        nums[idx].set("Value", _num_str(value))

        # 2) 人类可读
        human = human or eng(value)
        params = pl.find("parameters")
        if params is not None:
            ps = params.findall("Item")
            if idx < len(ps):
                ps[idx].set("Value", "&ASC" + human)

        # 3/4) 属性槽 41 / 42（只对主参数）
        if idx == 1 and len(items) > 42:
            c41 = items[41].find("CiaCString")
            if c41 is not None:
                c41.set("String", "&ASC" + human)
            c42 = items[42].find("CiaCString")
            if c42 is not None:
                old = c42.get("String") or ""
                suffix = old.split("_uc", 1)[1] if "_uc" in old else ""
                disp = "&UNI" + human + ("_uc" + suffix if suffix else "")
                c42.set("String", disp)
                # 5) 图上文字（CiID 在父 Item 上，CiComponent 自身没有）
                for e in self.elements:
                    if e.find("CiComponent") is comp:
                        self.set_value_text(e.get("CiID"), disp)
                        break
        return human

    def set_value_by_refdes(self, refdes, value, human=None):
        c = self.find(refdes)
        return self.set_value(c["comp"], value, human)

    # ---------- 绘图对象 ----------
    def symbol_of(self, ciid):
        for item in self.objects:
            inner = list(item)
            if not inner:
                continue
            if inner[0].get("CiComponent") == ciid:
                return item
        return None

    def translate(self, ciid, dx, dy):
        """平移元件的所有绘图子对象。"""
        item = self.symbol_of(ciid)
        if item is None:
            return False
        for el in item.iter():
            x, y = el.get("Transformer-M20"), el.get("Transformer-M21")
            if x is not None and y is not None:
                el.set("Transformer-M20", "%g." % (_flt(x) + dx))
                el.set("Transformer-M21", "%g." % (_flt(y) + dy))
        return True

    def position(self, ciid):
        item = self.symbol_of(ciid)
        if item is None:
            return None
        for el in item.iter():
            x, y = el.get("Transformer-M20"), el.get("Transformer-M21")
            if x is not None and y is not None:
                return _flt(x), _flt(y)
        return None

    def set_refdes(self, ciid, refdes):
        c = self._comp_by_ciid(ciid)
        c.set("LocalName", "&ASC" + refdes)
        item = self.symbol_of(ciid)
        if item is not None:
            for el in item.iter():
                if el.tag == "CIITSymbolComp":
                    el.set("InstanceRefDes", "&ASC" + refdes)
                elif el.tag == "CIITSymTextCompName":
                    el.set("Output", "&ASC" + refdes)

    def set_value_text(self, ciid, text):
        """改元件显示的值文字。

        Multisim 用 &UNI<人类可读值>_uc<单位哈希> 这种形式，
        例如 1kΩ -> &UNI1k_uc103a9。传 "" 表示清空。
        """
        item = self.symbol_of(ciid)
        if item is None:
            return False
        for el in item.iter():
            if el.tag == "CIITSymTextCompValue":
                el.set("Output", text)
                return True
        return False

    def _comp_by_ciid(self, ciid):
        for e in self.elements:
            if e.get("CiID") == ciid:
                return e.find("CiComponent")
        raise KeyError(ciid)

    # ---------- 网络 ----------
    def ports(self):
        out = []
        for e in self.elements:
            if e.get("Class") != "CiPort":
                continue
            p = e.find("CiPort")
            out.append({"ciid": e.get("CiID"), "component": p.get("Component"),
                        "name": _txt(p.get("LocalName")).replace("&ASC", ""),
                        "node": e, "port": p})
        return out

    def nodes(self):
        out = []
        for e in self.elements:
            if e.get("Class") != "CiNode":
                continue
            n = e.find("CiNode")
            refs = [i.get("CiID") for i in n.find("Ports")]
            out.append({"ciid": e.get("CiID"),
                        "name": _txt(n.get("LocalName")).replace("&ASC", ""),
                        "ports": refs, "node": e, "inner": n})
        return out

    # ---------- 引脚几何 ----------
    def pin_defs(self):
        """ReferencedComponents 里的 CODPinComp 定义：ID -> (x, y) 绝对坐标。"""
        rc = self.diagram.find("Components/CODComposite/ReferencedComponents")
        out = {}
        if rc is None:
            return out
        for it in rc:
            inner = list(it)
            if inner and inner[0].get("Class") == "CODPinComp":
                out[it.get("ID")] = (_flt(inner[0].get("CenterX")),
                                     _flt(inner[0].get("CenterY")))
        return out

    def pin_info(self, ciid):
        """元件的引脚信息。

        链路：CIITPinSymbolComp@PortID -> CiPort
              CIITPinSymbolComp/CIITPinConnectorComp  (局部点 ptCenterX/Y + 变换矩阵)
              .../ConnectList/Item@ID -> ReferencedComponents 里的 CODPinComp 定义

        返回 {引脚名: {"xy": (x, y), "def_ids": [ID...], "conn": <ConnectorComp>}}
        """
        item = self.symbol_of(ciid)
        out = {}
        if item is None:
            return out
        for pin in item.iter("CIITPinSymbolComp"):
            conn = pin.find(".//CIITPinConnectorComp")
            if conn is None:
                continue
            lx, ly = float(conn.get("ptCenterX")), float(conn.get("ptCenterY"))
            m00 = float(pin.get("Transformer-M00"))
            m01 = float(pin.get("Transformer-M01"))
            m10 = float(pin.get("Transformer-M10"))
            m11 = float(pin.get("Transformer-M11"))
            tx = float(pin.get("Transformer-M20"))
            ty = float(pin.get("Transformer-M21"))
            x = m00 * lx + m10 * ly + tx
            y = m01 * lx + m11 * ly + ty
            name = _txt(pin.get("PinName")).replace("&ASC", "")
            refs = [i.get("ID") for i in conn.findall(".//ConnectList/Item")]
            out[name] = {"xy": (x, y), "def_ids": refs, "conn": conn,
                         "port": _txt(pin.get("PortID"))}
        return out

    def summary(self):
        cs = self.components()
        return {"components": [(c["refdes"], c["family"], c["part"]) for c in cs],
                "ports": len(self.ports()),
                "nodes": [(n["name"], len(n["ports"])) for n in self.nodes()]}


if __name__ == "__main__":
    import gzip
    import json

    _src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        ROOT, "corpus", "samples", "Analyses__Monte Carlo - RLC Circuit.xml.gz")
    if _src.endswith(".gz"):
        c = Circuit(gzip.open(_src, "rb").read())
    else:
        c = Circuit(open(_src, "rb").read())
    print(json.dumps(c.summary(), ensure_ascii=False, indent=1))
    for comp in c.components():
        print(comp["refdes"], comp["family"], comp["part"],
              "位置=", c.position(comp["ciid"]),
              "参数=", c.params(comp["comp"])[:6])
