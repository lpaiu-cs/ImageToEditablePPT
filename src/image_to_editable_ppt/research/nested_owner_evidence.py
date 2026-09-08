"""Share verified closed children and avoid erasing observed panel interiors."""
from dataclasses import replace
from image_to_editable_ppt.v3.core.enums import PortOwnerKind,ContainerKind


def exclusion_regions(raw_regions,verified_candidates):
    """Only add actually observed contours, never an invented bounding rectangle."""
    result=[];seen=set()
    for region in [*raw_regions,*verified_candidates]:
        key=tuple(region['bbox'])
        if key not in seen:
            seen.add(key);result.append(region)
    return result


def panel_children(scene):
    result={}
    for parent in scene.shapes:
        p=parent.bbox;children=[]
        for child in scene.shapes:
            c=child.bbox
            if (p.x0<c.x0<c.x1<p.x1 and p.y0<c.y0<c.y1<p.y1
                    and c.width*c.height<.8*p.width*p.height):children.append(child)
        # One badge or a near-duplicate inner face is not panel evidence.
        separate=any(a.bbox.x1<b.bbox.x0 or b.bbox.x1<a.bbox.x0 or
            a.bbox.y1<b.bbox.y0 or b.bbox.y1<a.bbox.y0
            for i,a in enumerate(children) for b in children[i+1:])
        if separate:result[parent.id]=[c.id for c in children]
    return result


def trace_nested(scene,rgb,*,raw_branches=False):
    from image_to_editable_ppt.research.source_centerline_v2 import trace_with_centerlines
    from image_to_editable_ppt.research.box_centerline_b_v1 import refine_box_centerlines
    from image_to_editable_ppt.research.box_terminals import recover_box_terminals
    parents=panel_children(scene)
    # This is a temporary mask role, not a new semantic classification or shape.
    mask_scene=replace(scene,shapes=tuple(replace(s,owner_kind=PortOwnerKind.CONTAINER,
        shape_kind=ContainerKind.PANEL) if s.id in parents else s for s in scene.shapes))
    traced,_,trace=trace_with_centerlines(mask_scene,rgb)
    traced,box=refine_box_centerlines(traced,rgb)
    traced,terminals=recover_box_terminals(traced,rgb,box)
    if raw_branches:
        from image_to_editable_ppt.research.raw_branch_completion import add_raw_branches
        traced,trace['raw_branches']=add_raw_branches(traced,rgb)
    assert all(e.source_owner_id not in parents and e.target_owner_id not in parents for e in traced.connectors)
    return replace(traced,shapes=scene.shapes),trace,box,terminals,dict(border_only_parents=parents,
        policy='strict enclosure of two spatially separate closed owners; temporary tracing role only; parent endpoint links abstain')
