"""Offline same-ID controlled-revision deltas, never a production quality gate."""
import math


GROUPS = {
    'shapes': {'label', 'shape_kind', 'owner_kind'},
    'connectors': {'kind', 'source_owner_id', 'target_owner_id', 'source_owner_kind',
                   'target_owner_kind', 'arrowhead_start', 'arrowhead_end',
                   'source_port_id', 'target_port_id', 'source_instance_id', 'target_instance_id'},
    'texts': {'text', 'role', 'owner_ids'},
    'residuals': {'kind', 'reason'},
}


def _finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError('nonfinite scene value')
    if isinstance(value, dict):
        for v in value.values():
            _finite(v)
    elif isinstance(value, (tuple, list)):
        for v in value:
            _finite(v)


def _validate(scene):
    _finite(scene)
    size = scene['image_size']
    if any(not isinstance(size[k], (int, float)) or size[k] <= 0 for k in ('width', 'height')):
        raise ValueError('invalid image size')
    seen = set()
    for group in GROUPS:
        for obj in scene[group]:
            key = obj['id']
            if not isinstance(key, str) or not key or key in seen:
                raise ValueError('invalid or duplicate object ID')
            seen.add(key)
            if 'bbox' in obj:
                b = obj['bbox']
                if not all(isinstance(b[k], (int, float)) for k in ('x0','y0','x1','y1')):
                    raise ValueError('nonnumeric bbox')
                if b['x0'] >= b['x1'] or b['y0'] >= b['y1']:
                    raise ValueError('degenerate bbox')
            for p in obj.get('path_points', []):
                if not all(isinstance(p[k], (int, float)) for k in ('x','y')):
                    raise ValueError('nonnumeric path')


def assess_revision(before, after):
    """Compare controlled scenes in a shared coordinate system and ID namespace.

    Structural changes can be improvements, not necessarily errors. Endpoint
    displacement is not a whole-path distance. No scalar acceptance threshold.
    """
    _validate(before)
    _validate(after)
    if (before['image_size'] != after['image_size']
            or before.get('coordinate_space') != after.get('coordinate_space')):
        raise ValueError('different image coordinate systems')
    structural, geometry, metadata = [], [], []
    diagonal = math.hypot(before['image_size']['width'], before['image_size']['height'])
    for group, semantic in GROUPS.items():
        left = {o['id']: o for o in before[group]}
        right = {o['id']: o for o in after[group]}
        for key in sorted(left.keys() - right.keys()):
            structural.append(dict(group=group, id=key, change='removed'))
        for key in sorted(right.keys() - left.keys()):
            structural.append(dict(group=group, id=key, change='added'))
        for key in sorted(left.keys() & right.keys()):
            a, b = left[key], right[key]
            changed = {k for k in a.keys() | b.keys() if a.get(k) != b.get(k)}
            fields = sorted(changed & semantic)
            if fields:
                structural.append(dict(group=group, id=key, change='fields', fields=fields))
            if 'bbox' in changed:
                x, y = a['bbox'], b['bbox']
                distance = max(math.hypot(x[f'x{i}']-y[f'x{i}'], x[f'y{i}']-y[f'y{i}']) for i in (0,1))
                geometry.append(dict(group=group,id=key,change='bbox',max_corner_displacement_px=distance,
                                     fraction_image_diagonal=distance/diagonal))
            if 'path_points' in changed:
                x, y = a.get('path_points', []), b.get('path_points', [])
                distance = None
                if x and y:
                    distance = max(math.hypot(x[i]['x']-y[i]['x'], x[i]['y']-y[i]['y']) for i in (0,-1))
                geometry.append(dict(group=group,id=key,change='path',
                    before_point_count=len(x),after_point_count=len(y),
                    max_endpoint_displacement_px=distance,
                    fraction_image_diagonal=distance/diagonal if distance is not None else None))
            other = sorted(changed - semantic - {'bbox','path_points'})
            if other:
                metadata.append(dict(group=group,id=key,fields=other))
    top = sorted(k for k in before.keys() | after.keys()
                 if k not in GROUPS and before.get(k) != after.get(k))
    if top:
        metadata.append(dict(group='scene',fields=top))
    return dict(schema='controlled_revision_delta_v1',
        scope='offline same-ID controlled comparison; not object matching or product acceptance',
        geometry_unit='input scene pixels',image_diagonal_px=diagonal,
        structural_changes=structural,geometry_changes=geometry,metadata_changes=metadata)
