"""External-flow-supported empty frames, not semantic approval of their content."""
import math
from image_to_editable_ppt.region.emitter import supported_scene
from image_to_editable_ppt.region.geometry import normalize_scene
from image_to_editable_ppt.research.source_centerline_v2 import segment_hits_box
from image_to_editable_ppt.v3.core.enums import NodeKind,PortOwnerKind


def frame_witnesses(scene,content,nontext=None):
    owners={s.id:s for s in scene.shapes}
    seeds={s.id for s in scene.shapes if content[s.id]['eligible'] and s.label}
    native,_,_=supported_scene(normalize_scene(scene)[0])
    valid={e.id for e in native.connectors};witnesses={}
    linked={v for e in native.connectors for v in (e.source_owner_id,e.target_owner_id)}
    def box(s):return (s.bbox.x0,s.bbox.y0,s.bbox.x1,s.bbox.y1)
    def children(s):
        p=s.bbox
        return {v.id for v in scene.shapes if v.id!=s.id and p.x0<=v.bbox.x0 and p.y0<=v.bbox.y0 and v.bbox.x1<=p.x1 and v.bbox.y1<=p.y1}
    for edge in scene.connectors:
        if (edge.id not in valid or edge.source!='r3_stroke_trace' or len(edge.path_points)!=2
                or edge.arrowhead_start or not edge.arrowhead_end):continue
        a,b=edge.path_points
        if min(abs(a.x-b.x),abs(a.y-b.y))>1:continue
        pair={edge.source_owner_id,edge.target_owner_id}
        if any(segment_hits_box((a.x,a.y),(b.x,b.y),box(s)) for s in scene.shapes if s.id not in pair):continue
        for identity,other,point,direction in ((edge.source_owner_id,edge.target_owner_id,a,'out'),
                (edge.target_owner_id,edge.source_owner_id,b,'in')):
            s=owners[identity];o=owners[other];p=s.bbox;q=o.bbox
            target=not content[identity]['eligible'] or (nontext is not None and
                nontext[identity]['reason']=='unexplained_interior_content')
            if not target or other not in seeds:continue
            if s.source!='raw_closed_rectangle_proposal':continue
            if any(v.owner_kind is not PortOwnerKind.NODE or v.shape_kind not in (NodeKind.BOX,NodeKind.ROUNDED_BOX) for v in (s,o)):continue
            if max(p.x0,q.x0)<=min(p.x1,q.x1) and max(p.y0,q.y0)<=min(p.y1,q.y1):continue
            inside=children(s)
            if inside & (seeds|linked) or len(inside)>1:continue
            witnesses.setdefault(identity,[]).append(dict(edge=edge.id,seed=other,direction=direction,port=[point.x,point.y]))
    accepted={identity:rows for identity,rows in witnesses.items() if any(
        a['direction']!=b['direction'] and math.dist(a['port'],b['port'])>=8*scene.image_size.height/360
        for i,a in enumerate(rows) for b in rows[i+1:])}
    blocked={identity for identity,rows in accepted.items() if any(r['seed'] in accepted for r in rows)}
    frames={identity:rows for identity,rows in accepted.items() if identity not in blocked}
    omitted=blocked|{child for identity in accepted for child in children(owners[identity])}
    return frames,omitted


def surviving_frames(witnesses,emitted):
    """Use frozen source witnesses; emitted blank frames never become new seeds."""
    edges={e.id:e for e in emitted.connectors};owners={s.id for s in emitted.shapes}
    return {identity for identity,rows in witnesses.items() if identity in owners and all(
        r['edge'] in edges and edges[r['edge']].arrowhead_end and not edges[r['edge']].arrowhead_start
        and (edges[r['edge']].source_owner_id,edges[r['edge']].target_owner_id)==(
            (identity,r['seed']) if r['direction']=='out' else (r['seed'],identity))
        for r in rows)}
