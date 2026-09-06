"""Build a nominal design layout from R23 room bounds without changing the world."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape


LABELS = {
    "entry_hall": "玄關／走廊",
    "living_room": "客廳",
    "kitchen_dining": "廚房／餐區",
    "bedroom": "臥室",
    "office": "書房",
    "bathroom_laundry": "衛浴／洗衣",
}
COLORS = {
    "entry_hall": "#f3eadc",
    "living_room": "#eadfcf",
    "kitchen_dining": "#dbe3d5",
    "bedroom": "#eee5dc",
    "office": "#dfe5e6",
    "bathroom_laundry": "#dce8e6",
}
WINDOWS = {
    "entry_hall": None,
    "living_room": "west",
    "kitchen_dining": "east",
    "bedroom": "west",
    "office": "east",
    "bathroom_laundry": "north",
}
CAMERA_TARGETS = {
    "entry_hall": ["south_to_north", "north_to_south", "entry_oblique", "bench_material_detail"],
    "living_room": ["east_to_northwest", "southwest_to_east", "southwest_to_north", "sofa_material_detail"],
    "kitchen_dining": ["west_to_northeast", "southeast_to_northwest", "southwest_to_northeast", "sink_material_detail"],
    "bedroom": ["east_to_northwest", "northwest_to_southeast", "southwest_to_northeast", "bedside_material_detail"],
    "office": ["west_to_northeast", "southeast_to_northwest", "northwest_to_southeast", "chair_material_detail"],
    "bathroom_laundry": ["south_to_north", "northeast_to_southwest", "southeast_to_northwest", "faucet_material_detail"],
}


def build_contract(source: Path) -> dict:
    raw = source.read_bytes()
    house = json.loads(raw)
    if house["units"] != "meters":
        raise ValueError("This layout expects the pinned metre-based room source")
    rooms = []
    for room in house["rooms"]:
        if room["transform"]["rotation_deg"] != [0, 0, 0] or room["transform"]["scale"] != [1, 1, 1]:
            raise ValueError("Rotated/scaled room bounds require a separate projection")
        origin = room["transform"]["location_m"]
        low, high = room["bounds_m"]["min_m"], room["bounds_m"]["max_m"]
        rooms.append({
            "source_room_id": room["room_id"],
            "kind": room["kind"],
            "label_zh": LABELS[room["kind"]],
            "world_min_m": [a + b for a, b in zip(origin, low)],
            "world_max_m": [a + b for a, b in zip(origin, high)],
            "nominal_size_m": [round(b - a, 5) for a, b in zip(low, high)],
            "proposed_window_wall": WINDOWS[room["kind"]],
            "camera_intents": CAMERA_TARGETS[room["kind"]],
        })
    portals = [{
        "source_portal_id": p["portal_id"],
        "from_room_id": p["from_room_id"],
        "to_room_id": p["to_room_id"],
        "center_m": p["world_transform"]["location_m"],
        "nominal_width_m": p["clearance"]["width_m"],
        "nominal_height_m": p["clearance"]["height_m"],
    } for p in house["portals"]]
    return {
        "schema_version": "vista.photoreal-reference-design/v1",
        "status": "concept_reference_only",
        "source": {"repository_path": "world_packs/vista_playable_home_r1/house.json", "sha256": hashlib.sha256(raw).hexdigest(), "base_commit": "936d86d50aa1cc281fcbe4d91287db935fcc1f51"},
        "units": "meters",
        "coordinate_system": {"x": "east", "y": "north", "z": "up"},
        "dimension_authority": "Existing logical room bounds; not surveyed dimensions or a construction plan. New clear dimensions and wall assemblies need a Blender geometry decision.",
        "style": {"direction": "contemporary Taiwanese residence", "user_confirmation": "pending_optional_preference", "materials": ["natural oak", "warm offwhite plaster", "muted sage cabinetry", "low-gloss terrazzo", "satin stainless steel", "ivory glazed ceramic"], "realism": "ordinary lived-in home; credible construction details; restrained wear; natural exposure"},
        "design_assumptions": {"windows": "proposed original design; not extracted from source", "room_images": "appearance references only; panels may disagree geometrically", "render_comparison": "future single Blender scene with fixed cameras", "furniture_positions": "proposed in prompts; resolve to numeric transforms before production modeling"},
        "rooms": rooms,
        "portals": portals,
        "future_asset_namespace": "/Game/VISTA/PhotorealR1/",
        "runtime_migration": {"reuse": ["character controller", "typed action transactions", "EventSpec interfaces", "streaming interface"], "rebuild_and_verify": ["visual geometry", "collision matching visual geometry", "interaction anchors", "door pivots", "material response", "lighting", "camera clearance"], "first_slice": "kitchen_dining with pot, mug and articulated fridge"},
    }


def project(contract: dict):
    scale, left, top = 60, 145, 145
    xmin = min(r["world_min_m"][0] for r in contract["rooms"])
    ymax = max(r["world_max_m"][1] for r in contract["rooms"])
    def xy(x, y):
        return left + (x - xmin) * scale, top + (ymax - y) * scale
    return scale, xy


def write_drawio(contract: dict, target: Path) -> None:
    graph = ET.Element("mxGraphModel", {"dx": "1120", "dy": "1050", "grid": "1", "page": "1", "pageWidth": "1120", "pageHeight": "1050", "adaptiveColors": "auto"})
    root = ET.SubElement(graph, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})
    def vertex(key, value, x, y, w, h, style):
        node = ET.SubElement(root, "mxCell", {"id": key, "value": value, "style": style + ";html=1;whiteSpace=wrap;", "vertex": "1", "parent": "1"})
        ET.SubElement(node, "mxGeometry", {"x": str(x), "y": str(y), "width": str(w), "height": str(h), "as": "geometry"})
    vertex("title", "VISTA｜六房名義平面配置", 80, 35, 960, 40, "text;strokeColor=none;fillColor=none;fontSize=30;fontStyle=1")
    vertex("subtitle", "既有房間 bounds 與門口位置｜新版室內設計起點，非量測／施工圖", 80, 85, 960, 34, "text;strokeColor=none;fillColor=none;fontSize=16")
    scale, xy = project(contract)
    for room in contract["rooms"]:
        lo, hi = room["world_min_m"], room["world_max_m"]
        x, y = xy(lo[0], hi[1])
        w, h, z = room["nominal_size_m"]
        vertex(room["kind"], f"{room['label_zh']}<br>{w:g} × {h:g} m<br>名義高度 {z:g} m", x, y, w * scale, h * scale, f"rounded=0;fillColor={COLORS[room['kind']]};strokeColor=#384740;strokeWidth=2;fontSize=20")
    for i, p in enumerate(contract["portals"]):
        x, y = xy(*p["center_m"][:2])
        vertical = abs(p["center_m"][0]) == 1.5
        w, h = (10, scale * p["nominal_width_m"]) if vertical else (scale * p["nominal_width_m"], 10)
        vertex(f"portal-{i}", "", x - w / 2, y - h / 2, w, h, "rounded=0;fillColor=#ffffff;strokeColor=#4f7e66;strokeWidth=2")
    vertex("footer", "綠色門口標記：名義寬 1.0 m／高 2.1 m。圖中尚未指定牆厚、窗洞或家具。<br>北 ↑　比例：60 畫布單位／公尺。各圖尺寸以 design-contract.json 為準。", 80, 920, 960, 70, "text;strokeColor=none;fillColor=none;fontSize=16")
    ET.indent(graph)
    ET.ElementTree(graph).write(target, encoding="utf-8", xml_declaration=True)


def write_svg(contract: dict, target: Path) -> None:
    scale, xy = project(contract)
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="1050" viewBox="0 0 1120 1050">', '<rect width="1120" height="1050" fill="#fbfaf7"/>', '<g font-family="Noto Sans CJK TC, Noto Sans, sans-serif" fill="#293c32">', '<text x="80" y="68" font-size="30" font-weight="700">VISTA｜六房名義平面配置</text>', '<text x="80" y="105" font-size="16">既有房間 bounds 與門口位置｜新版室內設計起點，非量測／施工圖</text>']
    for room in contract["rooms"]:
        lo, hi = room["world_min_m"], room["world_max_m"]
        x, y = xy(lo[0], hi[1])
        w, h, z = room["nominal_size_m"]
        pw, ph = w * scale, h * scale
        parts.append(f'<rect x="{x}" y="{y}" width="{pw}" height="{ph}" fill="{COLORS[room["kind"]]}" stroke="#384740" stroke-width="2"/>')
        for text, offset, font in [(room["label_zh"], -18, 24), (f"{w:g} × {h:g} m", 18, 22), (f"名義高度 {z:g} m", 48, 15)]:
            parts.append(f'<text x="{x + pw/2}" y="{y + ph/2 + offset}" font-size="{font}" text-anchor="middle">{escape(text)}</text>')
    for p in contract["portals"]:
        x, y = xy(*p["center_m"][:2])
        vertical = abs(p["center_m"][0]) == 1.5
        w, h = (10, scale * p["nominal_width_m"]) if vertical else (scale * p["nominal_width_m"], 10)
        parts.append(f'<rect x="{x-w/2}" y="{y-h/2}" width="{w}" height="{h}" fill="white" stroke="#4f7e66" stroke-width="2"/>')
    parts += ['<path d="M 995 215 V 155 M 984 170 L 995 155 L 1006 170" fill="none" stroke="#384740" stroke-width="3"/>', '<text x="995" y="240" text-anchor="middle" font-size="20">北</text>', '<text x="80" y="941" font-size="16">綠色門口標記：名義寬 1.0 m／高 2.1 m。尚未指定牆厚、窗洞或家具。</text>', '<text x="80" y="973" font-size="16">尺寸以 design-contract.json 為準；此 SVG 與 draw.io 均由同一資料產生。</text>', '</g></svg>']
    target.write_text("\n".join(parts) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("world_packs/vista_playable_home_r1/house.json"))
    parser.add_argument("--output", type=Path, default=Path("docs/design/vista-photoreal-r1"))
    args = parser.parse_args()
    contract = build_contract(args.source)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "design-contract.json").write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n")
    write_drawio(contract, args.output / "floor-plan.drawio")
    write_svg(contract, args.output / "floor-plan.svg")
    print(json.dumps({"room_count": len(contract["rooms"]), "portal_count": len(contract["portals"]), "source_sha256": contract["source"]["sha256"], "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
