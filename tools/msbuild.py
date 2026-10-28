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
import re
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
# 元件模板（donor）来源 = 真实的 .ms14 文件。
#
# ★ 2026-10-26 修正：旧实现读 corpus/samples_index.json 里的 "cache" 路径，
#   但那些 out/samples/*.ms14 其实是**残缺片段**（从某个属性中间开始，
#   连 XML 头都没有），根本打不开 —— add_part() 一调就 ParseError。
#   现在改成直接扫真实 .ms14，索引在内存里缓存。
#
# 扫描顺序：先 corpus/samples14（随仓库提交，10 个文件，覆盖 R/C/L/GND/
# 电源/555/运放/buck），找不到再懒加载扫本机 Multisim 安装目录的 108 个
# 官方样例（不随仓库走，换机器可能没有）。
DONOR_DIRS = [os.path.join(ROOT, "corpus", "samples14")]
INSTALL_SAMPLES = os.path.join(
    os.environ.get("PUBLIC", r"C:\Users\Public"),
    "Documents", "National Instruments", "Circuit Design Suite 14.3", "samples")

_INDEX = {}
_CIRCUITS = {}


def _iter_ms14(d):
    if not os.path.isdir(d):
        return
    for root, _dirs, files in os.walk(d):
        for f in sorted(files):
            if f.lower().endswith(".ms14"):
                yield os.path.join(root, f)


def _scan_dirs(dirs):
    """扫若干目录下的 .ms14，返回 {(family, part): [(路径, 位号), ...]}。"""
    idx = {}
    for d in dirs:
        for p in _iter_ms14(d):
            try:
                c = load_donor(p)
            except Exception:
                continue
            for comp in c.components():
                ref = comp.get("refdes") or ""
                if not ref:
                    continue
                key = ((comp.get("family") or ""), (comp.get("part") or ""))
                lst = idx.setdefault(key, [])
                if (p, ref) not in lst:
                    lst.append((p, ref))
    return idx


def part_index():
    """{(family, part): [(ms14 路径, 位号), ...]}。

    数据源是真实的 .ms14（默认 corpus/samples14）。返回的路径可以直接
    喂给 msmodel.Circuit.load，也可以当 add_part(donor_path=...) 的参数。
    """
    if "idx" in _INDEX:
        return _INDEX["idx"]
    idx = _scan_dirs(DONOR_DIRS)
    _INDEX["idx"] = idx
    _INDEX["extended"] = False
    return idx


def find_part(family, part=None):
    """按 (family, part) 找第一个可用模板，返回 (ms14 路径, 位号)。

    part 传 None 表示"这个家族里随便哪个"。找不到返回 None。
    corpus/samples14 里没有时，会自动再扫一遍 Multisim 安装目录的官方样例
    （只扫一次，结果并入索引）。
    """
    idx = part_index()

    def lookup():
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

    hit = lookup()
    if hit is not None:
        return hit
    if not _INDEX.get("extended") and os.path.isdir(INSTALL_SAMPLES):
        _INDEX["extended"] = True
        idx.update({k: v for k, v in _scan_dirs([INSTALL_SAMPLES]).items()
                    if k not in idx})
        return lookup()
    return None


def suggest_part(family, part=None, n=5):
    """找不到时给候选：先列同 family 的所有 part，再给名字最像的几个。"""
    import difflib
    idx = part_index()
    keys = ["%s/%s" % k for k in idx]
    want = "%s/%s" % (family or "", part or "")
    same = [k for k in keys if k.split("/")[0].upper() == (family or "").upper()]
    close = difflib.get_close_matches(want, keys, n=n, cutoff=0.5)
    out = []
    for k in (close + same[:n]):
        if k not in out:
            out.append(k)
    return out[:n]


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


def _probe_local_name(base, index):
    """把探针的 LocalName 换成指定序号。

    donor 里探针的 LocalName 形如 ``&UNI_uc263a294881``，
    其 RefDes 管理器条目是 ``IRPrefix="&UNI_uc263a29488" IRNumber="1"``，
    即 **LocalName = 前缀 + 序号**。所以换序号只需替换最后一位数字。

    这个值直接决定 COM ``EnumOutputs`` 里的名字：序号重复 → 名字重复 →
    两个探针分不开（见 Assembler.add_probe_ext 的说明）。
    """
    s = base or ""
    stem = s[:-1] if s and s[-1].isdigit() else s
    return "%s%d" % (stem, index)


# ---------------------------------------------------------------- RefDes 注册
# Multisim 除了把位号存在 CiComponent@LocalName，还在工程扩展里维护一份
# 「层级位号管理器」（Project/Extensions/.../CMultisimExtension/RefDesMgrs）：
#
#   RefDesMgr/RefDesInfoContainers/RefDesInfoContainer/CIRToInfoMap
#       CIRToInfoMapItem CIRKey="&ASCR1"
#           RefDesInfo IRPrefix="&ASCR" IRNumber="1"
#               RefDesInfoData RefDes="&ASC!0!0!0R1!0<文件全路径>!01!0<图纸名>!0"
#   RefDesMgr/RefDesPrefixUsageMap
#       RefDesPrefixUsage RefDes="&ASCR" Prefix="&ASCR" NextNumber="1"
#
# 生成网表时 %p（位号）就是从这里解析的。克隆出来的元件如果没有登记，
# 连通性（CiNode/CiPort）看着完全正确、ReportNetlist 也对，但 SPICE 侧
# 解析不出位号，元素被整条丢弃 —— 表现为「电阻开路、电流为零」。

_PREFIX_RE = re.compile(r"^([A-Za-z_]+)(\d+)$")

# 总开关：置 False 可复现「不登记 RefDes」的旧行为（用于 A/B 对照）
REGISTER_REFDES = True


def refdes_extension(circuit):
    """取 CMultisimExtension 节点（RefDes 管理器的挂载点）。"""
    for e in circuit.tree.iter("Extension"):
        if e.get("Class") == "CMultisimExtension":
            return e
    return None


def _refdes_container(circuit, create=False):
    ext = refdes_extension(circuit)
    if ext is None:
        return None
    mgrs = ext.find("RefDesMgrs")
    if mgrs is None:
        if not create:
            return None
        mgrs = ET.SubElement(ext, "RefDesMgrs")
    mgr = mgrs.find("RefDesMgr")
    if mgr is None:
        if not create:
            return None
        mgr = ET.SubElement(mgrs, "RefDesMgr")
        mgr.set("Class", "CIITHierRefDesManager")
    conts = mgr.find("RefDesInfoContainers")
    if conts is None:
        if not create:
            return None
        conts = ET.SubElement(mgr, "RefDesInfoContainers")
    cont = conts.find("RefDesInfoContainer")
    if cont is None:
        if not create:
            return None
        cont = ET.SubElement(conts, "RefDesInfoContainer")
        cont.set("Class", "CIITHierRefDesInfoContainer")
        cont.set("CIR", "&ASC#1/:")
        for k, v in (("UsePreOffset", "0"), ("Prefix", ""), ("Offset", "0"),
                     ("UsePreOffsetParent", "0"), ("PrefixParent", ""),
                     ("OffsetParent", "0")):
            cont.set(k, v)
    return cont


def donor_refdes_info(donor_circuit, refdes):
    """从 donor 里取同位号的 RefDesInfo 作为模板（没有就返回 None）。"""
    cont = _refdes_container(donor_circuit)
    if cont is None:
        return None
    m = cont.find("CIRToInfoMap")
    if m is None:
        return None
    for it in m.findall("CIRToInfoMapItem"):
        if (it.get("CIRKey") or "").replace("&ASC", "") == refdes:
            return it.find("RefDesInfo")
    return None


def _sheet_name(container):
    """从 CIR="&ASC#1/blank:" 里抠出图纸名。"""
    cir = container.get("CIR") or ""
    if "/" in cir:
        tail = cir.split("/", 1)[1]
        return tail.rstrip(":")
    return ""


def build_refdes_info(refdes, template=None, donor_refdes=None,
                      path="", sheet=""):
    """造一个 CIITHierRefDesInfo 节点（可直接插进 CIRToInfoMapItem）。"""
    m = _PREFIX_RE.match(refdes or "")
    if m is None:
        return None                      # 例如 GROUND 的位号 "0"，不登记
    prefix, number = m.group(1), m.group(2)

    if template is not None:
        ri = copy.deepcopy(template)
        old = (ri.get("IRPrefix") or "").replace("&ASC", "")
        if old and old != prefix:
            # 模板前缀不同（例如拿 R 的模板去登记 C），改掉
            pass
        ri.set("IRPrefix", "&ASC" + prefix)
        ri.set("IRNumber", number)
        ri.set("Locked", "0")
        if ri.get("IRSection") is None:
            ri.set("IRSection", "")
        if ri.get("IRSectionID") is None:
            ri.set("IRSectionID", "0")
        if ri.get("SpiceTemplate") is None:
            ri.set("SpiceTemplate", "")
        data = ri.find("RefDesInfoData")
        if data is not None:
            rd = data.get("RefDes") or ""
            tpl_ref = donor_refdes or ""
            if tpl_ref and tpl_ref != refdes:
                rd = rd.replace("!0!0!0%s!0" % tpl_ref, "!0!0!0%s!0" % refdes)
            elif not tpl_ref:
                rd = rd.replace("!0!0!0%s!0" % old, "!0!0!0%s!0" % refdes) \
                    if old else rd
            data.set("RefDes", rd)
            data.set("Prefix", "&ASC" + prefix)
            data.set("Number", number)
        return ri

    # 没有模板：按官方样例的写法从头造
    ri = ET.Element("RefDesInfo")
    ri.set("Class", "CIITHierRefDesInfo")
    ri.set("IRPrefix", "&ASC" + prefix)
    ri.set("IRNumber", number)
    for k, v in (("Locked", "0"), ("IRSection", ""), ("IRSectionID", "0"),
                 ("SpiceTemplate", "")):
        ri.set(k, v)
    data = ET.SubElement(ri, "RefDesInfoData")
    data.set("Class", "CIITHierRefDes")
    data.set("RefDesBufSize", "260")
    data.set("RefDesStrSize", "134")
    data.set("RefDesCount", "2")
    data.set("RefDes", "&ASC!0!0!0%s!0%s!01!0%s!0" % (refdes, path, sheet))
    data.set("SectionBufSize", "0")
    data.set("SectionStrSize", "0")
    data.set("Section", "&ASC(null)")
    data.set("Prefix", "&ASC" + prefix)
    data.set("Number", number)
    ET.SubElement(data, "RefDesData")
    for tag in ("PinOrderCIR", "PinOrderIR", "PinNumbersCIR", "PinNumbersIR",
                "SharedPins"):
        ET.SubElement(ri, tag)
    return ri


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
    """宽容浮点解析：官方样例里坐标有 "455." 也有 "455.369."（双尾点）。

    直接用 float() 会在双尾点上抛异常，被当成 default=0 —— 那会把元件坐标
    静默写成 0，比抛错更难查，所以这里必须兜住。
    """
    try:
        return float(v)
    except (TypeError, ValueError):
        try:
            return float(str(v).strip().rstrip("."))
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
        self.refdes_path = ""            # RefDes 串里记的文件全路径（save 时补全）
        self.refdes_registered = []
        self.node_texts = {}             # CiNode CiID -> CODNodeTextComp ID
        self.node_text_links = {}        # CiNode CiID -> <Links> 元素

    # ---------- 克隆元件 ----------
    def add(self, donor, x=None, y=None, refdes=None, params=None,
            anchor="origin"):
        """把 donor 元件放到 (x, y)，返回 (新 CiID, [(引脚CiID, 引脚名)...])。

        anchor 决定 (x, y) 的含义：
            "origin"  元件符号的 Transformer-M20/M21（旧行为，默认）
            "pin"     引脚坐标的质心。**新代码建议用这个** —— 因为
                      corpus/samples14 里有些元件的符号锚点根本不是它的
                      实际位置（例：某 RESISTOR_VIRTUAL 符号 M20/M21=(0,-18)，
                      引脚却在 (495,108)），按 origin 放会散到图纸角落。
                      按引脚质心放，元件的电气位置一定落在你指定的点上。
        """
        comp = copy.deepcopy(donor.comp_item)
        old_ciid = donor.ciid
        new_ciid = self.new_id()
        comp.set("CiID", new_ciid)
        inner = comp.find("CiComponent")
        inner.set("Circuit", self.circuit_ciid)
        inner.set("InstanceID", _fresh_guid())

        dx = dy = 0.0
        if x is not None and y is not None:
            if anchor == "pin":
                info = donor.circuit.pin_info(donor.ciid)
                pts = [v["xy"] for v in info.values() if v.get("xy")]
                if pts:
                    cx = sum(p[0] for p in pts) / len(pts)
                    cy = sum(p[1] for p in pts) / len(pts)
                    dx, dy = x - cx, y - cy
            elif donor.pos is not None:
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
            # **关键（v0.9.1 修复 · 符号不渲染）**
            # symbol 根节点（CIITSymbolComp 本身）的 Transformer 必须归零。
            #
            # Multisim 渲染时的最终位置 = 根变换 ∘ 子对象变换；而子对象
            # （CIITSymbolBorderRect / CIITPinSymbolComp / 文字）存的是**图纸绝对
            # 坐标**，不是相对根的偏移。所以根一旦带上平移，就等于把整个符号
            # 再叠加一次偏移 —— 符号被推到画布外，视觉上"符号丢失"，
            # 但 CiNode/CiPort 拓扑与 SPICE 网表完全正确（仿真照跑）。
            #
            # donor 原件里根平移通常很小（RESISTOR 是 (0,-18)）或干脆是
            # "绝对坐标的补偿量"，所以过去的做法（把根一起平移）看着没崩，
            # 实际已经在积累误差；GROUND 的根是 (270,450)，一叠加就飞出图纸。
            #
            # 实测：归零后 V1/R1/C1/GND 符号与导线全部正确对位
            # （out/fix_skel/rc_root0.png）。6 个 enabled 元件的根线性部分
            # 都是单位矩阵，归零不影响朝向/镜像。
            sym_root = list(sym)[0] if len(sym) else None
            for el in sym.iter():
                # CIITPinConnectorComp 的 Transformer 在官方样例里恒为 (0,0)；
                # 它代表电气连接点，跟着元件平移会让连接点偏离本体 200+ 单位，
                # 元件在 SPICE 里就悬空了（连通性表却仍然正确）。必须跳过。
                if el.tag == "CIITPinConnectorComp":
                    continue
                px, py = el.get("Transformer-M20"), el.get("Transformer-M21")
                if px is None or py is None:
                    continue
                if el is sym_root:
                    el.set("Transformer-M20", "0.")
                    el.set("Transformer-M21", "0.")
                    continue
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
            copied_defs = []
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
                    copied_defs.append(new_def)
                    pin_map[old] = nid
                it.set("ID", pin_map[old])

            # **关键（P17 修复）**：符号的子对象（本体图元、引脚符号、引脚连接点、
            # 名称/数值文字）深拷贝后仍然带着 donor 的旧 ID。从同一个 donor 克隆两次
            # （比如 R1、R2）时，两个元件会共用同一批子对象 ID；Multisim 的对象表按
            # ID 索引，后写覆盖先写 —— 第一个元件在画布上直接不显示，电气上也等于
            # 不存在。这正是「克隆电阻开路、连通性表却正确」的根因。
            # 注意：ConnectList 里的 Item 是引脚定义引用，已由上面的 pin_map 处理，
            # 不能再改，否则会和新建的 CODPinComp 定义脱钩。
            protected = set()
            for cl in sym.iter("ConnectList"):
                for it in cl.findall("Item"):
                    protected.add(it)
            id_map = {}
            for el in sym.iter("Item"):
                if el is sym or el in protected:
                    continue
                old = el.get("ID")
                if old and old not in id_map:
                    id_map[old] = self.new_id()
            for el in sym.iter("Item"):
                if el is sym or el in protected:
                    continue
                old = el.get("ID")
                if old in id_map:
                    el.set("ID", id_map[old])

            # **关键（P18 修复）**：引脚定义本体里的 ConnectList 指向「符号内部的
            # CIITPinConnectorComp」——那个对象刚刚被重新分配了 ID，引脚定义必须
            # 同步改写。否则引脚定义 → 连接器这条链断掉：
            #   连通性表（走 CiNode/Ports）仍然完全正确，
            #   但 SPICE 端子解析（走 引脚定义→连接器→导线）失败，
            #   元件在仿真里等效开路 —— 正是「电阻开路、网表却正确」的根因。
            conn_ids = []
            for new_def in copied_defs:
                for cl in new_def.iter("ConnectList"):
                    for it in cl.findall("Item"):
                        oid = it.get("ID")
                        if oid in id_map:
                            it.set("ID", id_map[oid])
            # 连接器登记进 ReferencedComponents（官方文件里每个连接器都有登记项）
            seen_conn = set()
            for el in sym.iter("Item"):
                if el.get("Class") != "CIITPinConnectorComp":
                    continue
                cid = el.get("ID")
                if cid and cid not in seen_conn:
                    seen_conn.add(cid)
                    conn_ids.append(cid)
                    ref = ET.SubElement(self.refcomp, "Item")
                    ref.set("ID", cid)
                    ref.set("Class", "CIITPinConnectorComp")

            self.objs.append(sym)
            inner.set("SymCompID", sym.get("ID"))

        self.els.append(comp)
        self._append_ref(self.circuit_inner, "Components", new_ciid)

        if refdes:
            self.c.set_refdes(new_ciid, refdes)
            self.register_refdes(refdes, donor=donor)
        if params:
            for idx, val in params.items():
                self.c.set_param(inner, idx, val)
        return new_ciid, port_ids

    def add_part(self, family, part, refdes, value=None, x=None, y=None,
                 donor_path=None, donor_refdes=None, params=None):
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
            params        额外参数 {参数序号: 数值}，写进 CiaParamList/doubles
                          并用 eng() 同步人类可读副本。用于 AC_VOLTAGE 这类
                          多参数元件（idx 1 = 幅值，idx 5 = 频率 Hz）。

        返回 (新 CiID, [(引脚CiID, 引脚名), ...])，与 add() 一致。
        克隆沿用 add() 里已修好的 PortID / ConnectList / Circuit / Model 重映射。
        """
        if donor_path is None:
            hit = find_part(family, part)
            if hit is None:
                raise KeyError(
                    "样例库里没有 (%r, %r)。最接近的候选：%s\n"
                    "（可用 msbuild.part_index() 查看全部 %d 个组合）"
                    % (family, part, suggest_part(family, part) or "无",
                       len(part_index())))
            donor_path, donor_refdes = hit[0], hit[1]
        elif donor_refdes is None:
            raise ValueError("给了 donor_path 就必须同时给 donor_refdes")

        donor_circuit = load_donor(donor_path)
        d = Donor(donor_circuit, donor_refdes)
        ciid, ports = self.add(d, x=x, y=y, refdes=refdes, anchor="pin")
        if value is not None:
            self.c.set_value_by_refdes(refdes, value)
        if params:
            self.set_params(refdes, params)

        # 记一笔来源，方便调用方写报告
        self.last_part = {"family": family, "part": part, "refdes": refdes,
                          "donor": str(donor_path), "donor_refdes": donor_refdes,
                          "donor_family": d.family, "donor_part": d.part,
                          "value": value, "ciid": ciid}
        return ciid, ports

    def new_id(self):
        return self.c.new_id()

    def set_params(self, refdes, params):
        """按参数序号写 CiaParamList/doubles，并同步 parameters 的人类可读副本。

        params = {序号: 数值}。序号就是 doubles 里的下标（0 起）。

        已知布局（实测）：
            AC_VOLTAGE（正弦源）：[1]=幅值 V，[5]=频率 Hz，[3]=相位，[7]=直流偏置
            RESISTOR_VIRTUAL / CAPACITOR_VIRTUAL（原生 14 文件）：doubles 为空，
                值只在 parameters 字符串里 —— 这种情况必须用 add_part(value=...)
                走 set_value，本方法对它们是空操作。
        """
        comp = self.c.find(refdes)["comp"]
        attrs = comp.find("Attributes")
        if attrs is None or len(attrs) <= msmodel.ATTR_PARAMS:
            return
        pl = attrs[msmodel.ATTR_PARAMS].find("CiaParamList")
        if pl is None:
            return
        doubles = pl.find("doubles")
        nums = doubles.findall("Item") if doubles is not None else []
        ps_el = pl.find("parameters")
        ps = ps_el.findall("Item") if ps_el is not None else []
        for idx, val in params.items():
            if idx < len(nums):
                nums[idx].set("Value", msmodel._num_str(val))
            if idx < len(ps):
                ps[idx].set("Value", "&ASC" + msmodel.eng(val))

    # ---------- RefDes 注册 ----------
    def register_refdes(self, refdes, donor=None, template=None):
        """把 refdes 登记进层级位号管理器（缺失会导致 SPICE 丢掉该元件）。

        donor  传 Donor 对象时，顺手拿它同位号的 RefDesInfo 当模板
               （这样 RefDes 里的文件路径/图纸名与官方文件同构）
        返回 True 表示新登记，False 表示已存在（幂等）。
        """
        m = _PREFIX_RE.match(refdes or "")
        if m is None:
            return False                  # 地（位号 "0"）本来就不登记
        if not REGISTER_REFDES:
            return False
        cont = _refdes_container(self.c, create=True)
        if cont is None:
            return False
        cir_map = cont.find("CIRToInfoMap")
        if cir_map is None:
            cir_map = ET.SubElement(cont, "CIRToInfoMap")
        key = "&ASC" + refdes
        for it in cir_map.findall("CIRToInfoMapItem"):
            if it.get("CIRKey") == key:
                return False              # 已有，别重复插

        tpl = template
        tpl_ref = None
        if tpl is None and donor is not None:
            tpl = donor_refdes_info(donor.circuit, donor.refdes)
            tpl_ref = donor.refdes
        ri = build_refdes_info(refdes, template=tpl, donor_refdes=tpl_ref,
                               path=self.refdes_path,
                               sheet=_sheet_name(cont))
        if ri is None:
            return False
        item = ET.SubElement(cir_map, "CIRToInfoMapItem")
        item.set("CIRKey", key)
        item.append(ri)

        # 前缀使用表：R / C / L / V ... 各自一条
        ext = refdes_extension(self.c)
        mgr = ext.find("RefDesMgrs/RefDesMgr") if ext is not None else None
        if mgr is not None:
            usage = mgr.find("RefDesPrefixUsageMap")
            if usage is None:
                usage = ET.SubElement(mgr, "RefDesPrefixUsageMap")
            prefix = m.group(1)
            have = {(u.get("Prefix") or "").replace("&ASC", "")
                    for u in usage.findall("RefDesPrefixUsage")}
            if prefix not in have:
                u = ET.SubElement(usage, "RefDesPrefixUsage")
                u.set("RefDes", "&ASC" + prefix)
                u.set("Class", "CIITRefDesPrefixUsage")
                u.set("Prefix", "&ASC" + prefix)
                u.set("NextNumber", "1")
        self.refdes_registered.append(refdes)
        return True

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

    def _node_text(self, node_id, x, y):
        """取（或新建）某个 CiNode 的网络文字标签对象 CODNodeTextComp。

        官方文件里每根导线都带 `NodeText` 属性指向一个 `CODNodeTextComp`，
        该对象的 `Links` 反向列出同一网络的所有导线。生成的电路照抄这个结构，
        目的是让文件和官方文件的形态一致（GUI 打开时行为更接近原生）。

        ⚠️ 2026-10-26 更正：这里原来写着「缺了它 SPICE 组不出网络、元件等效开路」，
        **那是错的**，属于当时对「电阻电流恒 0」的错误归因。真实根因是
        `CIITDiagram@SimState` 属性内的换行被 XML 解析器归一化，见
        tools/mssafe.py 文件头。NodeText 属于「照抄原生结构」的锦上添花，
        不是仿真成立的必要条件 —— 实测 3 引脚中点在没有额外结点对象的情况下
        也能读到正确的 2.5 V。
        """
        key = str(node_id)
        if key in self.node_texts:
            return self.node_texts[key]

        tid = self.new_id()
        item = ET.SubElement(self.objs, "Item")
        item.set("ID", tid)
        item.set("Class", "CODNodeTextComp")
        nt = ET.SubElement(item, "CODNodeTextComp")
        for k, v in (("Class", "CODNodeTextComp"), ("instID", "0"),
                     ("Stretchable", "0"), ("Moveable", "1"),
                     ("LabelSelectable", "1"), ("Selectable", "1"),
                     ("LockedPenColor", "0"), ("LockedBrushColor", "0"),
                     ("Layer", "511"), ("Output", ""), ("PenColor", "255"),
                     ("FgColor", "0"), ("BgColor", "16777215"),
                     ("Font-Height", "-13"), ("Font-Width", "0"),
                     ("Font-Escapement", "0"), ("Font-Orientation", "0"),
                     ("Font-Weight", "700"), ("Font-Italic", "0"),
                     ("Font-Underline", "0"), ("Font-StrikeOut", "0"),
                     ("Font-CharSet", "0"), ("Font-OutPrecision", "3"),
                     ("Font-ClipPrecision", "2"), ("Font-Quality", "1"),
                     ("Font-PitchAndFamily", "34"), ("Font-FaceName", "&ASCArial"),
                     ("Transformer-M00", "1."), ("Transformer-M01", "0."),
                     ("Transformer-M10", "0."), ("Transformer-M11", "1."),
                     ("Transformer-M20", "%g." % x), ("Transformer-M21", "%g." % y),
                     ("Hidden", "0"), ("HorizontalAlign", "0"),
                     ("VerticalAlign", "0"), ("KeepCurrentFont", "0")):
            nt.set(k, v)
        ET.SubElement(nt, "Links")
        self.node_texts[key] = tid
        self.node_text_links[key] = nt.find("Links")

        # 登记进 ReferencedComponents（官方文件里每个网络文字都有登记项）
        if self.refcomp is not None:
            ref = ET.SubElement(self.refcomp, "Item")
            ref.set("ID", tid)
            ref.set("Class", "CODNodeTextComp")
        return tid

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
        # 网络文字：把导线绑进 CiNode 对应的电气网络（见 _node_text 注释）
        mid_x = sum(p[0] for p in pts) / float(len(pts))
        mid_y = sum(p[1] for p in pts) / float(len(pts))
        tid = self._node_text(node_id, mid_x, mid_y)
        lnk.set("NodeText", tid)
        links = self.node_text_links.get(str(node_id))
        if links is not None:
            li = ET.SubElement(links, "Item")
            li.set("ID", item.get("ID"))
            li.set("Class", "CIITLinkComp")
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

        # 导线同样要登记进 ReferencedComponents（官方文件里每条导线都有登记项）
        ref = ET.SubElement(self.refcomp, "Item")
        ref.set("ID", item.get("ID"))
        ref.set("Class", "CIITLinkComp")
        return item

    def save(self, path):
        self._fix_refdes_path(path)
        return self.c.save(path)

    def _fix_refdes_path(self, path):
        """把已登记 RefDes 里的文件路径/图纸名改成真正要保存的文件。

        从 donor 复制来的 RefDesInfo 里写着 donor 的绝对路径，指向一个
        跟目标文件无关的 .ms14。留着它在层级解析里是脏数据，这里统一
        改成本次输出的文件路径与图纸名。
        """
        full = os.path.abspath(path)
        sheet = os.path.splitext(os.path.basename(path))[0]
        cont = _refdes_container(self.c)
        if cont is None:
            return
        cir = cont.get("CIR") or ""
        if "/" in cir:
            cont.set("CIR", cir.split("/", 1)[0] + "/" + sheet + ":")
        for data in cont.iter("RefDesInfoData"):
            rd = data.get("RefDes") or ""
            parts = rd.split("!0")
            # 结构: ['&ASC', '', '', '<refdes>', '<path>', '1', '<sheet>', '']
            if len(parts) >= 7:
                parts[4] = full
                parts[6] = sheet
                data.set("RefDes", "!0".join(parts))

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

    # ---------- 新式电压探针（ProbeExt）----------
    def add_probe_ext(self, x, y, index=None, donor_path=None):
        """克隆一个 14.3 新式电压探针（CIITProbeExtComponent + CiProbeExtComp）。

        与 add_probe()（老式 CiProbeComp，靠 NetName 显式绑网络）不同，新式探针
        **没有任何网络引用**，靠 Transformer-M20/M21 精确落在导线顶点上吸附网络。

        参数：
            x, y       落点，必须是目标网络导线的**一个顶点**（线段中间无效）
            index      探针序号，默认按已有探针数自动 +1
            donor_path 探针模板来源，默认 out/ref/with_probes.ms14
        返回 (新电气 CiID, 新绘图 ID)

        ★ 唯一命名（2026-10-26 实测定论，之前多探针重名的根因）：
            CiProbeExtComp@LocalName = <IRPrefix><IRNumber>，如 &UNI_uc263a294881。
            LocalName 就是 COM EnumOutputs 里的名字来源。克隆时如果照抄 donor 的
            LocalName，两个探针名字完全相同 → EnumOutputs 返回两条 V(探针2) →
            RequestOutput 无法区分，读回直接抛「未指定的错误」。
            把序号改成唯一值后实测得到 ['V(探针1)', 'V(探针2)']，两条读数各自正确。

        注意：序号只用 1 位（1..9）。超过 9 需要另找分隔方式，暂不支持。
        """
        donor_path = donor_path or os.path.join(ROOT, "out", "ref", "with_probes.ms14")
        donor = load_donor(donor_path)

        draw = None
        for e in donor.objects:
            inner = list(e)
            if inner and inner[0].get("Class") == "CIITProbeExtComponent":
                draw = e
                break
        elec = None
        for e in donor.elements:
            if e.get("Class") == "CiProbeExtComp":
                elec = e
                break
        if draw is None or elec is None:
            raise RuntimeError("donor %s 里没有新式 ProbeExt" % donor_path)

        old_draw_id = draw.get("ID")
        old_elec_id = elec.get("CiID")

        # 1) 绘图对象：新 ID + 落点
        new_draw = copy.deepcopy(draw)
        new_draw_id = self.new_id()
        new_draw.set("ID", new_draw_id)
        ndi = list(new_draw)[0]
        ndi.set("Transformer-M20", "%g" % x)
        ndi.set("Transformer-M21", "%g" % y)

        # 2) 电气对象：新 CiID + 回指 + 唯一 LocalName
        new_elec = copy.deepcopy(elec)
        new_elec_id = self.new_id()
        new_elec.set("CiID", new_elec_id)
        nei = list(new_elec)[0]
        nei.set("SymCompID", new_draw_id)
        nei.set("InstanceID", _fresh_guid())
        nei.set("Circuit", self.circuit_ciid)
        if index is None:
            index = self.probe_count() + 1
        nei.set("LocalName", _probe_local_name(nei.get("LocalName"), index))

        # 3) 双向引用 + 子树内所有旧 ID 重映射（COMPHANDLE_EXT 等）
        ndi.set("CiProbeExtComp", new_elec_id)
        for tree in (new_draw, new_elec):
            for el in tree.iter():
                for k, v in list(el.attrib.items()):
                    if v == old_draw_id:
                        el.set(k, new_draw_id)
                    elif v == old_elec_id:
                        el.set(k, new_elec_id)

        self.objs.append(new_draw)
        self.els.append(new_elec)

        # 4) 注册进 CiCircuit/ProbeExts（不注册 = 探针不存在）
        pe = self.circuit_inner.find("ProbeExts")
        if pe is None:
            pe = ET.SubElement(self.circuit_inner, "ProbeExts")
        it = ET.SubElement(pe, "Item")
        it.set("CiID", new_elec_id)

        self.last_probe = {"ciid": new_elec_id, "draw": new_draw_id,
                           "x": x, "y": y, "index": index,
                           "local_name": nei.get("LocalName")}
        return new_elec_id, new_draw_id

    def probe_count(self):
        """当前电路里已有的新式探针数。"""
        return sum(1 for e in self.els if e.get("Class") == "CiProbeExtComp")

    def net_vertices(self, node_ciid):
        """某条网络上所有导线的顶点坐标（探针只能落在这里）。

        返回 [(x, y), ...]，按导线顺序去重。
        """
        out = []
        for e in self.objs:
            inner = list(e)
            if not inner or inner[0].get("Class") != "CIITLinkComp":
                continue
            if inner[0].get("Node") != node_ciid:
                continue
            pts = inner[0].find("Points")
            if pts is None:
                continue
            for p in pts:
                xy = (_f(p.get("X")), _f(p.get("Y")))
                if xy not in out:
                    out.append(xy)
        return out
