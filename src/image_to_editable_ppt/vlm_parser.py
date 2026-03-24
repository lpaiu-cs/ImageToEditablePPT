from __future__ import annotations

from dataclasses import dataclass
import base64
import io
import json
import mimetypes
import os
from pathlib import Path
from typing import Literal, Protocol
from urllib import error, request

from PIL import Image

from .ir import BBox

NodeType = Literal["box", "cylinder", "document", "text_only"]
EdgeType = Literal["solid_arrow", "dashed_arrow", "line"]
CoordinateSpace = Literal["pixel", "normalized_1000"]

DEFAULT_VLM_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_VLM_MODEL = "gpt-4o"
NORMALIZED_COORDINATE_MAX = 1000.0

SYSTEM_PROMPT = """
You extract only structural diagram information from a paper figure.
Return JSON only.

Rules:
- Prefer omission over guessing.
- Keep only structural nodes, text labels, and logical edges.
- Ignore icons, logos, photos, textures, gradients, glow, shadows, and decorative graphics.
- Boxes may be partially occluded by text or icons; still output a coarse bounding box when geometry is clear.
- Do not invent hidden nodes or connections without strong visual evidence.
- Bounding boxes must be normalized between 0 and 1000 relative to the full image:
  x uses image width, y uses image height.
- Return bounding boxes as [x_min, y_min, x_max, y_max] using that 0..1000 coordinate space only.
- Edge labels are optional and should be omitted when uncertain.
""".strip()

USER_PROMPT = """
Analyze this diagram and return a JSON object with this exact schema:
{
  "nodes": [
    {"id": "n1", "type": "box|cylinder|document|text_only", "text": "label", "approx_bbox": [x_min, y_min, x_max, y_max]}
  ],
  "edges": [
    {"source": "n1", "target": "n2", "type": "solid_arrow|dashed_arrow|line", "label": "optional"}
  ]
}

Important:
- Bounding box coordinates are not pixels.
- Every bbox coordinate must be normalized to the 0..1000 range for the full image.
""".strip()


class VLMError(RuntimeError):
    """Raised when the semantic parser cannot return a usable structure."""


@dataclass(slots=True, frozen=True)
class VLMNode:
    id: str
    type: NodeType
    text: str
    approx_bbox: BBox


@dataclass(slots=True, frozen=True)
class VLMEdge:
    source: str
    target: str
    type: EdgeType
    label: str = ""


@dataclass(slots=True, frozen=True)
class DiagramStructure:
    nodes: list[VLMNode]
    edges: list[VLMEdge]
    coordinate_space: CoordinateSpace = "pixel"


class StructureParser(Protocol):
    def extract_structure(
        self,
        image: Image.Image,
        *,
        image_path: str | Path | None = None,
    ) -> DiagramStructure: ...


def load_env_file(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


class OpenAICompatibleVLMParser:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_VLM_URL,
        model: str = DEFAULT_VLM_MODEL,
        timeout_seconds: float = 90.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.timeout_seconds = timeout_seconds

    def extract_structure(
        self,
        image: Image.Image,
        *,
        image_path: str | Path | None = None,
    ) -> DiagramStructure:
        encoded, mime_type = encode_image(image, image_path=image_path)
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": USER_PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}},
                    ],
                },
            ],
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = request.urlopen(
                request.Request(self.base_url, data=body, headers=headers, method="POST"),
                timeout=self.timeout_seconds,
            )
        except error.HTTPError as exc:  # pragma: no cover - network/runtime dependent
            message = exc.read().decode("utf-8", errors="replace")
            raise VLMError(f"VLM request failed with HTTP {exc.code}: {message}") from exc
        except OSError as exc:  # pragma: no cover - network/runtime dependent
            raise VLMError(f"VLM request failed: {exc}") from exc
        raw_payload = response.read().decode("utf-8")
        return parse_chat_completion_payload(raw_payload)


def get_default_structure_parser() -> StructureParser:
    load_env_file()
    api_key = os.environ.get("VLM_API_KEY", "").strip()
    if not api_key:
        raise VLMError("VLM_API_KEY is not set")
    base_url = os.environ.get("VLM_BASE_URL", DEFAULT_VLM_URL).strip() or DEFAULT_VLM_URL
    model = os.environ.get("VLM_MODEL", DEFAULT_VLM_MODEL).strip() or DEFAULT_VLM_MODEL
    timeout_seconds = safe_float(os.environ.get("VLM_TIMEOUT_SECONDS"), default=90.0)
    return OpenAICompatibleVLMParser(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout_seconds=timeout_seconds,
    )


def extract_structure(
    image: Image.Image,
    *,
    image_path: str | Path | None = None,
    parser: StructureParser | None = None,
) -> DiagramStructure:
    active_parser = parser or get_default_structure_parser()
    return active_parser.extract_structure(image, image_path=image_path)


def parse_chat_completion_payload(payload: str) -> DiagramStructure:
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise VLMError("VLM response is not valid JSON") from exc
    if "choices" not in parsed:
        return parse_structure_object(parsed, coordinate_space="normalized_1000")
    choices = parsed.get("choices") or []
    if not choices:
        raise VLMError("VLM response does not contain choices")
    message = choices[0].get("message", {})
    content = message.get("content", "")
    content_text = flatten_message_content(content)
    return parse_structure_object(json.loads(content_text), coordinate_space="normalized_1000")


def flatten_message_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                chunks.append(str(item.get("text", "")))
        combined = "\n".join(chunk for chunk in chunks if chunk.strip())
        if combined:
            return combined
    raise VLMError("VLM response content is not a JSON string")


def parse_structure_object(
    payload: dict[str, object],
    *,
    coordinate_space: CoordinateSpace = "pixel",
) -> DiagramStructure:
    nodes_payload = payload.get("nodes")
    edges_payload = payload.get("edges")
    if not isinstance(nodes_payload, list) or not isinstance(edges_payload, list):
        raise VLMError("VLM response must include 'nodes' and 'edges' lists")
    nodes: list[VLMNode] = []
    node_ids: set[str] = set()
    for raw_node in nodes_payload:
        if not isinstance(raw_node, dict):
            raise VLMError("Each node must be an object")
        node = parse_node(raw_node)
        if node.id in node_ids:
            raise VLMError(f"Duplicate node id: {node.id}")
        node_ids.add(node.id)
        nodes.append(node)
    edges: list[VLMEdge] = []
    for raw_edge in edges_payload:
        if not isinstance(raw_edge, dict):
            raise VLMError("Each edge must be an object")
        edge = parse_edge(raw_edge)
        if edge.source not in node_ids or edge.target not in node_ids:
            continue
        edges.append(edge)
    return DiagramStructure(nodes=nodes, edges=edges, coordinate_space=coordinate_space)


def parse_node(payload: dict[str, object]) -> VLMNode:
    node_id = str(payload.get("id", "")).strip()
    node_type = str(payload.get("type", "")).strip()
    if node_type not in {"box", "cylinder", "document", "text_only"}:
        raise VLMError(f"Unsupported node type: {node_type or '<empty>'}")
    bbox = parse_bbox(payload.get("approx_bbox"))
    return VLMNode(
        id=node_id or "node",
        type=node_type,
        text=str(payload.get("text", "")).strip(),
        approx_bbox=bbox,
    )


def parse_edge(payload: dict[str, object]) -> VLMEdge:
    edge_type = str(payload.get("type", "")).strip()
    if edge_type not in {"solid_arrow", "dashed_arrow", "line"}:
        raise VLMError(f"Unsupported edge type: {edge_type or '<empty>'}")
    return VLMEdge(
        source=str(payload.get("source", "")).strip(),
        target=str(payload.get("target", "")).strip(),
        type=edge_type,
        label=str(payload.get("label", "")).strip(),
    )


def parse_bbox(value: object) -> BBox:
    if not isinstance(value, list) or len(value) != 4:
        raise VLMError("Bounding boxes must be a 4-item list")
    try:
        x0, y0, x1, y1 = (float(part) for part in value)
    except (TypeError, ValueError) as exc:
        raise VLMError("Bounding boxes must contain numeric coordinates") from exc
    if x1 <= x0 or y1 <= y0:
        raise VLMError("Bounding boxes must have positive width and height")
    return BBox(x0, y0, x1, y1)


def encode_image(image: Image.Image, *, image_path: str | Path | None = None) -> tuple[str, str]:
    if image_path is not None:
        path = Path(image_path)
        mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
        data = path.read_bytes()
        return base64.b64encode(data).decode("ascii"), mime_type
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii"), "image/png"


def safe_float(raw: str | None, *, default: float) -> float:
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def denormalize_structure(
    structure: DiagramStructure,
    *,
    image_size: tuple[int, int],
) -> DiagramStructure:
    if structure.coordinate_space == "pixel":
        return structure
    width, height = image_size
    if width <= 0 or height <= 0:
        raise VLMError("Image size must be positive to denormalize coordinates")
    nodes = [
        VLMNode(
            id=node.id,
            type=node.type,
            text=node.text,
            approx_bbox=denormalize_bbox(node.approx_bbox, width=width, height=height),
        )
        for node in structure.nodes
    ]
    return DiagramStructure(nodes=nodes, edges=structure.edges, coordinate_space="pixel")


def denormalize_bbox(bbox: BBox, *, width: int, height: int) -> BBox:
    scale_x = width / NORMALIZED_COORDINATE_MAX
    scale_y = height / NORMALIZED_COORDINATE_MAX
    return BBox(
        bbox.x0 * scale_x,
        bbox.y0 * scale_y,
        bbox.x1 * scale_x,
        bbox.y1 * scale_y,
    )
