from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

from .ir import BoxGeometry, Element, Point, PolylineGeometry

SVG_NS = "http://www.w3.org/2000/svg"


def export_to_svg(
    elements: list[Element],
    image_size: tuple[int, int],
    output_path: str | Path,
) -> None:
    width, height = image_size
    ET.register_namespace("", SVG_NS)
    svg = ET.Element(
        f"{{{SVG_NS}}}svg",
        attrib={
            "width": str(width),
            "height": str(height),
            "viewBox": f"0 0 {width} {height}",
            "version": "1.1",
        },
    )
    defs = ET.SubElement(svg, f"{{{SVG_NS}}}defs")
    marker = ET.SubElement(
        defs,
        f"{{{SVG_NS}}}marker",
        attrib={
            "id": "arrow-tip",
            "markerWidth": "10",
            "markerHeight": "7",
            "refX": "9",
            "refY": "3.5",
            "orient": "auto",
            "markerUnits": "strokeWidth",
        },
    )
    ET.SubElement(
        marker,
        f"{{{SVG_NS}}}polygon",
        attrib={"points": "0 0, 10 3.5, 0 7", "fill": "#000000"},
    )
    ET.SubElement(
        svg,
        f"{{{SVG_NS}}}rect",
        attrib={
            "x": "0",
            "y": "0",
            "width": str(width),
            "height": str(height),
            "fill": "#ffffff",
        },
    )
    for element in elements:
        append_svg_element(svg, element)
    tree = ET.ElementTree(svg)
    tree.write(Path(output_path), encoding="utf-8", xml_declaration=True)


def append_svg_element(parent: ET.Element, element: Element) -> None:
    if isinstance(element.geometry, BoxGeometry):
        bbox = element.geometry.bbox
        attrib = {
            "x": format_number(bbox.x0),
            "y": format_number(bbox.y0),
            "width": format_number(bbox.width),
            "height": format_number(bbox.height),
            "fill": to_svg_color(element.fill.color) if element.fill.enabled and element.fill.color is not None else "none",
            "stroke": to_svg_color(element.stroke.color),
            "stroke-width": format_number(max(1.0, element.stroke.width)),
        }
        if element.kind == "rounded_rect" and element.geometry.corner_radius > 0:
            attrib["rx"] = format_number(element.geometry.corner_radius)
            attrib["ry"] = format_number(element.geometry.corner_radius)
        ET.SubElement(parent, f"{{{SVG_NS}}}rect", attrib=attrib)
        return
    if not isinstance(element.geometry, PolylineGeometry):
        return
    points = " ".join(f"{format_number(point.x)},{format_number(point.y)}" for point in element.geometry.points)
    tag = "polyline" if len(element.geometry.points) > 2 else "line"
    if tag == "line":
        start, end = element.geometry.points
        attrib = {
            "x1": format_number(start.x),
            "y1": format_number(start.y),
            "x2": format_number(end.x),
            "y2": format_number(end.y),
            "fill": "none",
            "stroke": to_svg_color(element.stroke.color),
            "stroke-width": format_number(max(1.0, element.stroke.width)),
            "stroke-linecap": "round",
        }
        if element.kind == "arrow":
            attrib["marker-end"] = "url(#arrow-tip)"
        ET.SubElement(parent, f"{{{SVG_NS}}}line", attrib=attrib)
        return
    attrib = {
        "points": points,
        "fill": "none",
        "stroke": to_svg_color(element.stroke.color),
        "stroke-width": format_number(max(1.0, element.stroke.width)),
        "stroke-linecap": "round",
        "stroke-linejoin": "round",
    }
    if element.kind == "arrow":
        attrib["marker-end"] = "url(#arrow-tip)"
    ET.SubElement(parent, f"{{{SVG_NS}}}polyline", attrib=attrib)


def to_svg_color(color: tuple[int, int, int] | None) -> str:
    if color is None:
        return "none"
    return "#{:02x}{:02x}{:02x}".format(*color)


def format_number(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")
