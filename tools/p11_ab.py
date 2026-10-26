# -*- coding: utf-8 -*-
"""P11 A/B 构建：单变量互换电压源。

A: out/_p10.xml（能跑）里把 V2 换成 Assembler 克隆源，其余不动 -> out/p11_a.ms14
B: out/_accept.xml（不跑）里把 V1 换成 donor_spice 的原 V2 对象，其余不动 -> out/p11_b.ms14

用法：runtime\\py32\\python.exe tools\\p11_ab.py a|b
"""
import copy
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import msmodel
import msbuild

DONOR = os.path.join(ROOT, "out", "_donor_spice.xml")
BASE_A = os.path.join(ROOT, "out", "_p10.xml")
BASE_B = os.path.join(ROOT, "out", "_accept.xml")
OUT_A = "p11_a.ms14"


def parents(tree):
    p = {}
    for par in tree.iter():
        for ch in par:
            p[ch] = par
    return p


def kill(e, pmap):
    par = pmap.get(e)
    if par is not None:
        par.remove(e)


def port_nodes(c):
    """{端口 CiID: [(CiNode Item, Ports 里的引用 Item), ...]}"""
    out = {}
    for e in c.elements:
        if e.get("Class") != "CiNode":
            continue
        inner = e.find("CiNode")
        pe = inner.find("Ports")
        if pe is None:
            continue
        for it in pe:
            out.setdefault(it.get("CiID"), []).append((e, it))
    return out


def strip_component(c, ciid, pmap):
    """删掉一个元件的全部对象：CiComponent / CiModel / CiPort / 绘图对象 / 引脚定义。"""
    comp_item = c._item_of(ciid)
    inner = comp_item.find("CiComponent")
    model_id = inner.get("Model")
    ports = [e for e in c.elements
             if e.get("Class") == "CiPort" and e.find("CiPort").get("Component") == ciid]
    sym = c.symbol_of(ciid)
    def_ids = set()
    if sym is not None:
        for cl in sym.iter("ConnectList"):
            for it in cl.findall("Item"):
                if it.get("ID"):
                    def_ids.add(it.get("ID"))

    for e in c.elements:
        if e.get("Class") != "CiCircuit":
            continue
        ci = e.find("CiCircuit")
        for tag in ("Components", "Models"):
            nd = ci.find(tag)
            if nd is None:
                continue
            for i in list(nd):
                if i.get("CiID") in (ciid, model_id):
                    nd.remove(i)
    rc = c.diagram.find("Components/CODComposite/ReferencedComponents")
    if rc is not None:
        for i in list(rc):
            if i.get("ID") in def_ids:
                rc.remove(i)
    if model_id:
        for e in list(c.elements):
            if e.get("CiID") == model_id:
                kill(e, pmap)
    for e in ports:
        kill(e, pmap)
    kill(comp_item, pmap)
    if sym is not None:
        kill(sym, pmap)
    return {"model": model_id, "def_ids": def_ids,
            "ports": {p.find("CiPort").get("LocalName", "").replace("&ASC", ""): p.get("CiID")
                      for p in ports}}


def attach(c, new_ports, old_ports, pn_map):
    """把克隆端口挂到原端口所在的节点上（节点引用 + 端口反向 Nodes）。"""
    for name, new_pid in new_ports.items():
        old_pid = old_ports.get(name)
        if old_pid is None:
            print("  !! 旧端口没有 %s" % name)
            continue
        for node_item, ref_item in pn_map.get(old_pid, []):
            ref_item.set("CiID", new_pid)
            port = c._item_of(new_pid).find("CiPort")
            nd = port.find("Nodes")
            if nd is None:
                nd = ET.SubElement(port, "Nodes")
            it = ET.SubElement(nd, "Item")
            it.set("CiID", node_item.get("CiID"))


def remap_wires(c, def_map):
    """导线端点的 Connect1/Connect2 从旧引脚定义改到新引脚定义。"""
    n = 0
    for e in c.objects:
        inner = list(e)
        if not inner or inner[0].get("Class") != "CIITLinkComp":
            continue
        lnk = inner[0]
        for k in ("Connect1", "Connect2"):
            v = lnk.get(k)
            if v in def_map:
                lnk.set(k, def_map[v])
                n += 1
    return n


# ---------------------------------------------------------------- A
def build_a():
    a = msbuild.Assembler(base_path=BASE_A)
    c = a.c
    pmap = parents(c.tree)
    vc = c.find("V2")
    old = vc["ciid"]
    pos = c.position(old)
    old_pin = c.pin_info(old)
    old_ports = {p["name"]: p["ciid"] for p in c.ports() if p["component"] == old}
    pn_map = port_nodes(c)
    print("A: p10 原 V2 CiID=%s pos=%s pins=%s" % (old, pos, {k: v["xy"] for k, v in old_pin.items()}))

    stripped = strip_component(c, old, pmap)
    donor = msmodel.Circuit.from_xml_file(DONOR)
    new_ciid, port_ids = a.add(msbuild.Donor(donor, "V2"), x=pos[0], y=pos[1], refdes="V2")
    a.c.set_value_by_refdes("V2", 5.0)
    print("A: 克隆 V2 CiID=%s ports=%s" % (new_ciid, port_ids))

    attach(c, {name: pid for pid, name in port_ids}, old_ports, pn_map)

    new_pin = c.pin_info(new_ciid)
    def_map = {}
    for name, info in old_pin.items():
        nd = new_pin.get(name, {}).get("def_ids") or []
        od = info.get("def_ids") or []
        if nd and od:
            def_map[od[0]] = nd[0]
    print("A: 引脚定义重映射 %s" % def_map)
    print("A: 导线端点改写 %d 处" % remap_wires(c, def_map))

    out = os.path.join(ROOT, "out", OUT_A)
    n, _ = a.save(out)
    print("A: 写出 %s (%d 字节)" % (out, n))
    back = msmodel.Circuit.load(out)
    print("A: 回读", back.summary())
    print("A: V2 pin_info", {k: v["xy"] for k, v in back.pin_info(back.find("V2")["ciid"]).items()})
    return out


# ---------------------------------------------------------------- B
def build_b():
    c = msmodel.Circuit.from_xml_file(BASE_B)
    pmap = parents(c.tree)
    circuit_ciid = c.circuit_item.get("CiID")
    old = c.find("V1")["ciid"]
    pos = c.position(old)
    old_pin = c.pin_info(old)
    old_ports = {p["name"]: p["ciid"] for p in c.ports() if p["component"] == old}
    pn_map = port_nodes(c)
    print("B: acceptance 克隆 V1 CiID=%s pos=%s pins=%s"
          % (old, pos, {k: v["xy"] for k, v in old_pin.items()}))

    stripped = strip_component(c, old, pmap)

    donor = msmodel.Circuit.from_xml_file(DONOR)
    dv = donor.find("V2")
    dciid = dv["ciid"]
    d_pos = donor.position(dciid)
    dx, dy = pos[0] - d_pos[0], pos[1] - d_pos[1]
    print("B: donor V2 CiID=%s pos=%s 平移=(%g,%g)" % (dciid, d_pos, dx, dy))

    dcomp_item = donor._item_of(dciid)
    dcomp = dcomp_item.find("CiComponent")
    dmodel_id = dcomp.get("Model")
    dmodel = next(e for e in donor.elements if e.get("CiID") == dmodel_id)
    dsym = donor.symbol_of(dciid)
    dports = [p for p in donor.ports() if p["component"] == dciid]

    # 引脚定义（donor ReferencedComponents）
    d_rc = donor.diagram.find("Components/CODComposite/ReferencedComponents")
    d_defs = {i.get("ID"): i for i in d_rc} if d_rc is not None else {}

    # 1) 模型：逐字保留，只换 CiID / Scope
    m = copy.deepcopy(dmodel)
    new_model = c.new_id()
    m.set("CiID", new_model)
    m.find("CiModel").set("Scope", circuit_ciid)
    c.elements.append(m)

    # 2) 元件：逐字保留，只换 CiID / Circuit / InstanceID / LocalName / Model
    comp_item = copy.deepcopy(dcomp_item)
    new_ciid = c.new_id()
    comp_item.set("CiID", new_ciid)
    inner = comp_item.find("CiComponent")
    inner.set("Circuit", circuit_ciid)
    inner.set("InstanceID", msbuild._fresh_guid())
    inner.set("LocalName", "&ASCV1")
    inner.set("Model", new_model)

    # 3) 端口
    ports_el = inner.find("Ports")
    for ch in list(ports_el):
        ports_el.remove(ch)
    new_ports = {}
    for p in dports:
        pid = c.new_id()
        pi = copy.deepcopy(p["node"])
        pi.set("CiID", pid)
        pin = pi.find("CiPort")
        pin.set("Component", new_ciid)
        pin.set("Circuit", circuit_ciid)
        nd = pin.find("Nodes")
        if nd is not None:
            for ch in list(nd):
                nd.remove(ch)
        c.elements.append(pi)
        it = ET.SubElement(ports_el, "Item")
        it.set("CiID", pid)
        new_ports[p["name"]] = pid

    # 4) 绘图对象 + 引脚定义（平移 + 换 ID）
    sym = copy.deepcopy(dsym)
    new_sym = c.new_id()
    sym.set("ID", new_sym)
    for el in sym.iter():
        if el.get("CiComponent") == dciid:
            el.set("CiComponent", new_ciid)
        px, py = el.get("Transformer-M20"), el.get("Transformer-M21")
        if px is not None and py is not None:
            el.set("Transformer-M20", "%g." % (float(px) + dx))
            el.set("Transformer-M21", "%g." % (float(py) + dy))
    # PortID 必须改指新端口（否则引脚符号与电气端口脱钩）
    for el in sym.iter("CIITPinSymbolComp"):
        pname = (el.get("PinName") or "").replace("&ASC", "")
        if pname in new_ports:
            el.set("PortID", new_ports[pname])
    rc = c.diagram.find("Components/CODComposite/ReferencedComponents")
    def_map = {}
    for cl in sym.iter("ConnectList"):
        for it in cl.findall("Item"):
            oid = it.get("ID")
            if not oid or oid not in d_defs:
                continue
            if oid not in def_map:
                nd = copy.deepcopy(d_defs[oid])
                nid = c.new_id()
                nd.set("ID", nid)
                di = list(nd)[0]
                di.set("CenterX", "%g" % (float(di.get("CenterX")) + dx))
                di.set("CenterY", "%g" % (float(di.get("CenterY")) + dy))
                rc.append(nd)
                def_map[oid] = nid
            it.set("ID", def_map[oid])
    c.objects.append(sym)
    inner.set("SymCompID", new_sym)
    c.elements.append(comp_item)

    # 5) 注册进 CiCircuit
    ci = c.circuit_item.find("CiCircuit")
    for tag, cid in (("Components", new_ciid), ("Models", new_model)):
        nd = ci.find(tag)
        if nd is None:
            nd = ET.SubElement(ci, tag)
        it = ET.SubElement(nd, "Item")
        it.set("CiID", cid)

    attach(c, new_ports, old_ports, pn_map)

    new_pin = c.pin_info(new_ciid)
    dm = {}
    for name, info in old_pin.items():
        nd2 = new_pin.get(name, {}).get("def_ids") or []
        od = info.get("def_ids") or []
        if nd2 and od:
            dm[od[0]] = nd2[0]
    print("B: 引脚定义重映射 %s" % dm)
    print("B: 导线端点改写 %d 处" % remap_wires(c, dm))

    c.set_value_by_refdes("V1", 5.0)
    out = os.path.join(ROOT, "out", "p11_b.ms14")
    xml = ET.tostring(c.tree, encoding="ascii", xml_declaration=True)
    import dcl
    dcl.write_ms14(out, xml)
    print("B: 写出 %s" % out)
    back = msmodel.Circuit.load(out)
    print("B: 回读", back.summary())
    print("B: V1 pin_info", {k: v["xy"] for k, v in back.pin_info(back.find("V1")["ciid"]).items()})
    return out


if __name__ == "__main__":
    which = (sys.argv[1] if len(sys.argv) > 1 else "a").lower()
    if len(sys.argv) > 2:
        OUT_A = sys.argv[2]
    (build_a if which == "a" else build_b)()
