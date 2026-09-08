"""R9-D v1 preregistered observations. Pure array input; no OCR, model or file IO."""
from copy import deepcopy
import hashlib
import itertools
import json
import math

import cv2
import numpy as np

PARAMETERS = dict(thresholds=[110, 140, 170], scale_height=360,
    max_cluster=4, crop_padding_heights=3, max_crop=256, ring=2,
    background_median=225, background_range=30, tiny_area=2,
    shaft_span_heights=3, external_span_heights=1, shaft_p95=1.5,
    shaft_max=3, shaft_width=6, coverage_owned=.95, coverage_partial_min=.05,
    group_vertical_overlap=.5, group_gap=.35, atom_height_min=3, atom_height_max=24,
    winner_coverage=.98, no_worse=[.01, .05, .05], better=[.05, .25, .25])
FIELDS = {'id', 'semantic_kind', 'bbox_xyxy', 'confidence'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def mask_digest(mask):
    return hashlib.sha256(str(mask.shape).encode()+mask.astype('uint8').tobytes()).hexdigest()


def overlap(a, b):
    intersection = max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))
    aa, bb = (a[2]-a[0])*(a[3]-a[1]), (b[2]-b[0])*(b[3]-b[1])
    return intersection, intersection/(aa+bb-intersection), intersection/min(aa, bb)


def components(adjacency):
    remaining = set(range(len(adjacency)))
    groups = []
    while remaining:
        todo, group = [min(remaining)], []
        while todo:
            i = todo.pop()
            if i not in remaining:
                continue
            remaining.remove(i)
            group.append(i)
            todo.extend(sorted(adjacency[i] & remaining, reverse=True))
        groups.append(sorted(group))
    return groups


def inside(xx, yy, box):
    return (xx >= box[0]) & (xx < box[2]) & (yy >= box[1]) & (yy < box[3])


def atoms(mask, origin):
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype('uint8'), connectivity=8)
    result = []
    for i in range(1, count):
        ys, xs = np.where(labels == i)
        x, y, w, h, area = map(int, stats[i])
        local = labels[y:y+h, x:x+w] == i
        result.append(dict(box=[x+origin[0], y+origin[1], x+w+origin[0], y+h+origin[1]],
            area=area, sha256=mask_digest(local), ys=ys, xs=xs,
            touches_crop=bool(x == 0 or y == 0 or x+w == mask.shape[1] or y+h == mask.shape[0])))
    result.sort(key=lambda a: (a['box'][1], a['box'][0], a['box'][3], a['box'][2], a['area'], a['sha256']))
    return result


def threshold_observation(mask, owners, union, origin, s, h):
    minimum = max(1, math.ceil(2*s*s))
    shaft, unresolved = np.zeros_like(mask), np.zeros_like(mask)
    component_records = []
    reasons = set()
    for atom in atoms(mask, origin):
        ys, xs = atom['ys'], atom['xs']
        xy = np.column_stack((xs+origin[0]+.5, ys+origin[1]+.5))
        occupied = inside(xy[:, 0], xy[:, 1], union)
        row = {k: v for k, v in atom.items() if k not in ('ys', 'xs')}
        row.update(inside=int(occupied.sum()), outside=int((~occupied).sum()), category='ink')
        if len(xy) < minimum or len(xy) < 2:
            row['category'] = 'tiny'
        else:
            centered = xy-xy.mean(axis=0)
            values, vectors = np.linalg.eigh(centered.T @ centered / len(xy))
            if np.isclose(values[0], values[1], rtol=1e-12, atol=1e-12):
                row['axis_uncertain'] = True
                if occupied.any():
                    reasons.add('axis_uncertain')
            else:
                axis = vectors[:, 1]
                if axis[0] < 0 or (axis[0] == 0 and axis[1] < 0):
                    axis = -axis
                along = centered @ axis
                perpendicular = centered @ np.array([-axis[1], axis[0]])
                span = float(np.ptp(along))
                outside_span = float(np.ptp(along[~occupied])) if (~occupied).sum() > 1 else 0.
                p95, maximum = float(np.percentile(abs(perpendicular), 95)), float(abs(perpendicular).max())
                width = float(np.ptp(perpendicular))
                row.update(axis=axis.tolist(), center=xy.mean(axis=0).tolist(), span=span,
                    outside_span=outside_span, perpendicular_p95=p95, perpendicular_max=maximum, width=width)
                if span >= 3*h and outside_span >= h and p95 <= 1.5*s and maximum <= 3*s and width <= 6*s:
                    shaft[ys, xs] = True
                    row['category'] = 'shaft_like'
                elif span >= 3*h and occupied.any() and (~occupied).any():
                    unresolved[ys, xs] = True
                    row['category'] = 'unresolved'
        component_records.append(row)
    yy, xx = np.indices(mask.shape)
    xx, yy = xx+origin[0]+.5, yy+origin[1]+.5
    owner_masks = [inside(xx, yy, o['bbox_xyxy']) for o in owners]
    if any((unresolved & own).sum() >= minimum for own in owner_masks):
        reasons.add('shaft_touch_uncertain')
    glyph = mask & ~shaft & ~unresolved
    # Neighbourhood query only; it does not modify the observation masks.
    if np.any(cv2.dilate(shaft.astype('uint8'), np.ones((3, 3), 'uint8')).astype(bool) & glyph):
        reasons.add('shaft_glyph_contact')
    atom_records, signatures, tiny_counts = [], [set() for _ in owners], [0 for _ in owners]
    all_atoms = atoms(glyph, origin)
    for k, atom in enumerate(all_atoms):
        coverage = [float(own[atom['ys'], atom['xs']].sum()/atom['area']) for own in owner_masks]
        row = {name: value for name, value in atom.items() if name not in ('ys', 'xs')}
        row.update(id=k, coverage=coverage)
        atom_records.append(row)
        for i, fraction in enumerate(coverage):
            if .05 < fraction < .95:
                reasons.add('partial_glyph')
            if atom['area'] < minimum:
                tiny_counts[i] += int(owner_masks[i][atom['ys'], atom['xs']].sum())
            elif fraction >= .95:
                signatures[i].add(k)
    if any(n > 2*s*s for n in tiny_counts):
        reasons.add('small_ink_uncertain')
    shared = signatures[0] if signatures else set()
    same = bool(shared) and all(sig == shared for sig in signatures)
    if not same:
        reasons.add('different_ink_ownership')
    losses, winner, group_count, bg = [], None, None, None
    dominance = []
    if same:
        chosen = [all_atoms[k] for k in sorted(shared)]
        heights = [a['box'][3]-a['box'][1] for a in chosen]
        median = float(np.median(heights))
        if not 3*s <= median <= 24*s:
            reasons.add('atom_height_unsupported')
        adj = [set() for _ in chosen]
        for i, j in itertools.combinations(range(len(chosen)), 2):
            a, b = chosen[i]['box'], chosen[j]['box']
            vertical = max(0, min(a[3], b[3])-max(a[1], b[1]))/min(a[3]-a[1], b[3]-b[1])
            gap = max(0, max(a[0], b[0])-min(a[2], b[2]))
            if vertical >= .5 and gap <= .35*median:
                adj[i].add(j); adj[j].add(i)
        group_count = len(components(adj))
        if group_count != 1:
            reasons.add('multiple_ink_groups')
        bg = [min(a['box'][0] for a in chosen), min(a['box'][1] for a in chosen),
              max(a['box'][2] for a in chosen), max(a['box'][3] for a in chosen)]
        shared_mask = np.zeros_like(mask)
        for a in chosen:
            shared_mask[a['ys'], a['xs']] = True
        for o, own in zip(owners, owner_masks):
            b = o['bbox_xyxy']
            padding = [bg[0]-b[0], bg[1]-b[1], b[2]-bg[2], b[3]-bg[3]]
            coverage = float((shared_mask & own).sum()/shared_mask.sum())
            vector = [float((shaft & own).sum()/max(1, (mask & own).sum())),
                max(0., ((b[2]-b[0])*(b[3]-b[1])-(bg[2]-bg[0])*(bg[3]-bg[1]))/((bg[2]-bg[0])*(bg[3]-bg[1]))),
                (abs(padding[0]-padding[2])+abs(padding[1]-padding[3]))/(bg[3]-bg[1])]
            losses.append(dict(id=o['id'], glyph_coverage=coverage, padding=padding, losses=vector,
                               eligible=bool(coverage >= .98 and min(padding) >= 0)))
        for i, a in enumerate(losses):
            row = []
            for j, b in enumerate(losses):
                delta = np.array(a['losses'])-np.array(b['losses'])
                row.append(bool(i != j and a['eligible'] and np.all(delta <= [.01,.05,.05]) and np.any(delta <= -np.array([.05,.25,.25]))))
            dominance.append(row)
        winners = [i for i in range(len(owners)) if all(dominance[i][j] for j in range(len(owners)) if j != i)]
        if len(winners) != 1:
            reasons.add('representative_ambiguous')
        elif not reasons:
            winner = owners[winners[0]]['id']
    masks = dict(M=mask, S=shaft, U=unresolved, G=glyph)
    audit = dict(reasons=sorted(reasons), proposed_winner=winner, shared_ink_supported=same,
        representative_supported=winner is not None, components=component_records, atoms=atom_records,
        signatures=[sorted(sig) for sig in signatures], tiny_inside=tiny_counts,
        independent_group_count=group_count, glyph_bbox=bg, candidate_losses=losses,
        dominance=dominance, masks={name:dict(sha256=mask_digest(m), count=int(m.sum())) for name,m in masks.items()})
    return audit, masks


def observe_owners(rgb, owners, *, arm='D-O'):
    """Return unchanged/filtered deep-copied owners, audit, and diagnostic masks."""
    if arm not in ('D-O', 'D-S'):
        raise ValueError('unknown arm')
    if not isinstance(rgb, np.ndarray) or rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3 or min(rgb.shape[:2]) < 1:
        raise ValueError('RGB uint8 HxWx3 required')
    height, width = rgb.shape[:2]
    ids = set()
    for o in owners:
        if not isinstance(o, dict) or set(o) != FIELDS:
            raise ValueError('owner input fields must match whitelist')
        if not isinstance(o['id'], str) or not o['id'] or o['id'] in ids:
            raise ValueError('invalid or duplicate ID')
        ids.add(o['id'])
        b = o['bbox_xyxy']
        if len(b) != 4 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in b):
            raise ValueError('invalid bbox')
        if not 0 <= b[0] < b[2] <= width or not 0 <= b[1] < b[3] <= height:
            raise ValueError('bbox outside image or degenerate')
        if not isinstance(o['confidence'],(int,float)) or not math.isfinite(o['confidence']) or not 0 <= o['confidence'] <= 1:
            raise ValueError('invalid confidence')
        if not isinstance(o['semantic_kind'],str):
            raise ValueError('semantic kind must be string')
    selected = sorted((o for o in owners if o['semantic_kind']=='label_anchor'), key=lambda o:o['id'])
    adjacency = [set() for _ in selected]
    for i,j in itertools.combinations(range(len(selected)),2):
        if overlap(selected[i]['bbox_xyxy'],selected[j]['bbox_xyxy'])[0] > 0:
            adjacency[i].add(j); adjacency[j].add(i)
    records, masks, suppress = [], {}, set()
    s = height/360
    for indices in components(adjacency):
        if len(indices) < 2:
            continue
        group = [selected[i] for i in indices]
        row = dict(owners=deepcopy(group), reasons=[], proposed_winner=None, thresholds={})
        records.append(row)
        row['pairs'] = [dict(ids=[a['id'],b['id']], iou=overlap(a['bbox_xyxy'],b['bbox_xyxy'])[1],
            ios=overlap(a['bbox_xyxy'],b['bbox_xyxy'])[2]) for a,b in itertools.combinations(group,2)]
        if len(group)>4:
            row['reasons']=['cluster_too_large']; continue
        if any(j not in adjacency[i] for i,j in itertools.combinations(indices,2)):
            row['reasons']=['overlap_chain']; continue
        boxes = [o['bbox_xyxy'] for o in group]
        union = [min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]
        h = float(np.median([b[3]-b[1] for b in boxes])); pad = math.ceil(3*h)
        crop = [math.floor(union[0])-pad,math.floor(union[1])-pad,math.ceil(union[2])+pad,math.ceil(union[3])+pad]
        row['crop_xyxy']=crop
        if crop[0]<0 or crop[1]<0 or crop[2]>width or crop[3]>height:
            row['reasons']=['crop_clipped']; continue
        if max(crop[2]-crop[0],crop[3]-crop[1])>256*s:
            row['reasons']=['crop_too_large']; continue
        x,y,right,bottom = crop
        pixels = rgb[y:bottom,x:right].astype(float)
        lum = pixels @ np.array([.2126,.7152,.0722])
        ring = np.ones(lum.shape,dtype=bool); n=math.ceil(2*s)
        if min(ring.shape)>2*n: ring[n:-n,n:-n]=False
        p10,p90 = np.percentile(lum[ring],[10,90]); median=float(np.median(lum[ring]))
        row['background']=dict(channel_median=np.median(pixels[ring],axis=0).tolist(),median_y=median,p10=float(p10),p90=float(p90))
        if median<225 or p90-p10>30:
            row['reasons']=['background_unsupported']; continue
        for threshold in PARAMETERS['thresholds']:
            audit, group_masks=threshold_observation(lum<=threshold,group,union,(x,y),s,h)
            row['thresholds'][str(threshold)]=audit
            for name,mask in group_masks.items():
                key=audit['masks'][name]['sha256']; masks[key]=mask.copy()
        outcomes=[(a['proposed_winner'],a['reasons']) for a in row['thresholds'].values()]
        if any(value != outcomes[0] for value in outcomes[1:]):
            row['reasons']=['threshold_instability']
        else:
            row['proposed_winner'],row['reasons']=outcomes[0]
        if row['proposed_winner'] is not None:
            suppress.update(o['id'] for o in group if o['id']!=row['proposed_winner'])
    removed = suppress if arm=='D-S' else set()
    kept=deepcopy([o for o in owners if o['id'] not in removed])
    audit=dict(schema='r9_duplicate_owner_observations_v1',arm=arm,
        rgb_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(),rgb_shape=list(rgb.shape),owners_sha256=digest(owners),
        parameters=deepcopy(PARAMETERS),input_count=len(owners),kept_ids=[o['id'] for o in kept],
        suppressed_ids=sorted(removed),proposed_suppressed_ids=sorted(suppress),clusters=records,
        unchanged_nonanchors=[o['id'] for o in owners if o['semantic_kind']!='label_anchor'])
    return kept,audit,masks
