"""R7 development-only oracle boundary. Never imported by the production CLI."""
from dataclasses import dataclass, replace
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

from image_to_editable_ppt.region.geometry import detect_scene, intersection, area
from image_to_editable_ppt.region._selection_local import select_local
from image_to_editable_ppt.region.tracing import trace_scene
from image_to_editable_ppt.region.text import recover_labels
from image_to_editable_ppt.v3.core.enums import NodeKind, ContainerKind, PortOwnerKind
from image_to_editable_ppt.v3.core.types import BBox, ImageSize
from image_to_editable_ppt.v3.emit.models import EmitScene, EmitShapePrimitive

ROLES = {'node', 'container', 'connector', 'port', 'nonstructural', 'unknown'}
SUPPORTED = {'box', 'rounded_box', 'ellipse'}


def box_tuple(shape):
    b = shape.bbox
    return b.x0, b.y0, b.x1, b.y1


def iou(a, b):
    overlap = intersection(a, b)
    return overlap / max(1, area(a) + area(b) - overlap)


def contained(inner, outer):
    return all((inner[0] >= outer[0], inner[1] >= outer[1],
                inner[2] <= outer[2], inner[3] <= outer[3]))


def checked_box(value, size):
    if (len(value) != 4 or any(isinstance(v, bool) or not isinstance(v, (int, float))
                             or not math.isfinite(v) for v in value)
            or not 0 <= value[0] < value[2] <= size[0]
            or not 0 <= value[1] < value[3] <= size[1]):
        raise ValueError('invalid source-pixel box')
    return tuple(value)


def validate_annotation(data, rgb, source_bytes):
    """Validate provenance, coordinate frame, identity and ownership before use."""
    if data['schema'] != 'r7_source_roles_v1' or data['population'] != 'consumed_development':
        raise ValueError('research population/schema required')
    size = (rgb.shape[1], rgb.shape[0])
    if list(size) != data['source_size'] or hashlib.sha256(source_bytes).hexdigest() != data['source_sha256']:
        raise ValueError('source binding mismatch')
    if data['coordinate_space'] != 'original_pixels':
        raise ValueError('original pixels required')
    # This first cohort is deliberately identity-view only. Reject ambiguous
    # display scaling rather than silently converting annotation coordinates.
    if data['view_to_source'] != {'scale': [1, 1], 'offset': [0, 0], 'view_size': list(size)}:
        raise ValueError('unsupported or inconsistent view transform')
    scope = checked_box(data['scope'], size)
    objects = data['objects']
    by_id = {o['id']: o for o in objects}
    if len(by_id) != len(objects) or any(not isinstance(k, str) or not k for k in by_id):
        raise ValueError('duplicate/invalid object IDs')
    for o in objects:
        b = checked_box(o['bbox'], size)
        if not contained(b, scope) or o['role'] not in ROLES:
            raise ValueError('object outside scope or invalid role')
        if o['role'] in {'node', 'container'}:
            if o.get('geometry') not in SUPPORTED | {'cylinder'} or o.get('closed') is not True:
                raise ValueError('explicit closed geometry required')
        p = o.get('parent')
        visited = {o['id']}
        while p is not None:
            if p not in by_id or p in visited:
                raise ValueError('unknown/cyclic parent')
            parent = by_id[p]
            if parent['role'] not in {'node', 'container'} or not contained(b, parent['bbox']):
                raise ValueError('invalid parent ownership')
            visited.add(p)
            p = parent.get('parent')
    relations = data['relations']
    if len({r['id'] for r in relations}) != len(relations):
        raise ValueError('duplicate relation IDs')
    for r in relations:
        if r['source'] == r['target'] or r.get('directed') is not True or r.get('style') not in {'solid', 'dashed'}:
            raise ValueError('invalid observed relation')
        for end in ('source', 'target'):
            if r[end] not in by_id or by_id[r[end]]['role'] != 'node':
                raise ValueError('relation requires known node owners')
    return data


def load_annotation(path, root):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    source = (Path(root) / data['source_path']).resolve()
    source.relative_to(Path(root).resolve())
    payload = source.read_bytes()
    import io
    with Image.open(io.BytesIO(payload)) as im:
        rgb = np.asarray(im.convert('RGB'))
    return validate_annotation(data, rgb, payload), rgb


@dataclass(frozen=True)
class CandidateScene:
    scene: EmitScene
    windows: tuple[tuple[int, int, int, int], ...]

    def __post_init__(self):
        if self.scene.connectors or self.scene.texts or any(s.label for s in self.scene.shapes):
            raise ValueError('candidates cannot carry labels or relations')


@dataclass(frozen=True)
class AcceptedScene:
    scene: EmitScene
    parents: tuple[tuple[str, str | None], ...]
    exclusions: tuple[tuple[float, float, float, float], ...]
    authority: str

    def __post_init__(self):
        ids = {s.id for s in self.scene.shapes}
        mapping = dict(self.parents)
        if (self.authority not in {'oracle_roles', 'oracle_geometry'}
                or len(ids) != len(self.scene.shapes) or len(mapping) != len(self.parents)
                or set(mapping) != ids):
            raise ValueError('accepted identity/authority contract')
        for key in ids:
            visited = {key}
            p = mapping[key]
            while p is not None:
                if p not in ids or p in visited:
                    raise ValueError('invalid accepted parent graph')
                visited.add(p)
                p = mapping[p]
        if self.scene.connectors or self.scene.texts or any(s.label for s in self.scene.shapes):
            raise ValueError('approval must precede OCR/tracing')
        for box in self.exclusions:
            checked_box(box, (self.scene.image_size.width, self.scene.image_size.height))


def proposals(rgb, scope, *, local=False):
    h, w = rgb.shape[:2]
    roi = tuple(v / (w, h)[i % 2] for i, v in enumerate(scope))
    full, _ = select_local(detect_scene(rgb, roi), rgb, roi, 'combined')
    shapes = list(full.shapes)
    windows = [tuple(scope)]
    if local:
        def starts(lo, hi):
            last = max(lo, hi - 512)
            return sorted(set([*range(lo, last + 1, 384), last]))
        x0, y0, x1, y1 = map(int, scope)
        for y in starts(y0, y1):
            for x in starts(x0, x1):
                window = (x, y, min(x1, x + 512), min(y1, y + 512))
                if window == tuple(scope):
                    continue
                windows.append(window)
                tile = detect_scene(rgb, tuple(v / (w, h)[i % 2] for i, v in enumerate(window)))
                for s in tile.shapes:
                    b = box_tuple(s)
                    if min(b[0]-window[0], b[1]-window[1], window[2]-b[2], window[3]-b[3]) <= 2:
                        continue
                    if any(iou(b, box_tuple(t)) >= .90 for t in shapes):
                        continue
                    shapes.append(replace(s, id=f'local:{len(shapes)}', provenance=s.provenance+('r7:fixed_tile',)))
    return CandidateScene(replace(full, shapes=tuple(shapes)), tuple(windows))


def targets(annotation):
    return [o for o in annotation['objects'] if o['role'] in {'node', 'container'}]


def match(candidates, annotation):
    if not isinstance(candidates, CandidateScene):
        raise TypeError('CandidateScene required')
    objects = targets(annotation)
    pairs = []
    for s in candidates.scene.shapes:
        b = box_tuple(s)
        for o in objects:
            score = iou(b, o['bbox'])
            if score >= .70 and max(abs(a-c) for a, c in zip(b, o['bbox'])) <= 8:
                pairs.append((-score, s.id, o['id']))
    used = set()
    matched = {}
    for _, sid, oid in sorted(pairs):
        if sid not in matched and oid not in used:
            matched[sid] = oid
            used.add(oid)
    return matched


def accept_oracle(candidates, annotation, *, exact_geometry=False):
    """Truth is an experimental intervention, never an automatic classifier."""
    if not isinstance(candidates, CandidateScene):
        raise TypeError('CandidateScene required')
    objects = targets(annotation)
    by_id = {o['id']: o for o in objects}
    matched = match(candidates, annotation)
    if exact_geometry:
        rows = [(None, o) for o in objects]
    else:
        rows = [(s, by_id[matched[s.id]]) for s in candidates.scene.shapes if s.id in matched]
    exclusions = tuple(tuple(o['bbox']) for o in annotation['objects'] if o['role'] in {'nonstructural', 'unknown'})
    shapes = []
    rejected = []
    for candidate, o in rows:
        if o['geometry'] not in SUPPORTED:
            rejected.append(dict(id=o['id'], reason='unsupported_owner_geometry'))
            continue
        box = tuple(o['bbox']) if candidate is None else box_tuple(candidate)
        # Excluded content INSIDE a valid node is masked, not a reason to discard
        # its enclosing structural outline. A candidate inside excluded content is rejected.
        if any(intersection(box, e) / max(1, area(box)) >= .50 for e in exclusions):
            rejected.append(dict(id=o['id'], reason='excluded_region'))
            continue
        role = PortOwnerKind(o['role'])
        kind = ContainerKind.PANEL if role is PortOwnerKind.CONTAINER else NodeKind(o['geometry'])
        shapes.append(EmitShapePrimitive(o['id'], role, kind, BBox(*box), 1.,
                                        source='r7:oracle_geometry' if exact_geometry else candidate.source,
                                        provenance=('r7:oracle_not_automatic',)))
    accepted_ids = {s.id for s in shapes}
    parents = tuple((s.id, by_id[s.id].get('parent') if by_id[s.id].get('parent') in accepted_ids else None) for s in shapes)
    missing_parents = [s.id for s in shapes if by_id[s.id].get('parent') and by_id[s.id]['parent'] not in accepted_ids]
    scene = replace(candidates.scene, shapes=tuple(shapes), source='r7:research_only')
    return AcceptedScene(scene, parents, exclusions, 'oracle_geometry' if exact_geometry else 'oracle_roles'), dict(
        matches=matched, rejected=rejected, missing_parents=missing_parents,
        unsupported=[o['id'] for o in objects if o['geometry'] not in SUPPORTED])


def observe_accepted(accepted, rgb, scope, *, ocr=True):
    """Only accepted owners reach masking/OCR. Truth labels/edges are not inputs."""
    if not isinstance(accepted, AcceptedScene):
        raise TypeError('OCR and owner masking require AcceptedScene')
    if (rgb.shape[1], rgb.shape[0]) != (accepted.scene.image_size.width, accepted.scene.image_size.height):
        raise ValueError('source size mismatch')
    clean = rgb.copy()
    for box in accepted.exclusions:
        a, b, c, d = map(round, box)
        # Constant local neutralization avoids passing icon pixels to OCR or
        # tracing. It does not synthesize an outline or a connection.
        left, top = max(0, a-3), max(0, b-3)
        right, bottom = min(rgb.shape[1], c+3), min(len(rgb), d+3)
        patch = rgb[top:bottom, left:right]
        ring = np.ones(patch.shape[:2], dtype=bool)
        ring[b-top:d-top, a-left:c-left] = False
        color = np.median(patch[ring], axis=0) if ring.any() else np.array([255, 255, 255])
        clean[b:d, a:c] = color
    h, w = rgb.shape[:2]
    roi = tuple(v / (w, h)[i % 2] for i, v in enumerate(scope))
    traced, audit, _ = trace_scene(accepted.scene, clean, roi)
    labeled, text = recover_labels(traced, clean, enabled=ocr)
    return labeled, dict(tracing=audit, text=text)
