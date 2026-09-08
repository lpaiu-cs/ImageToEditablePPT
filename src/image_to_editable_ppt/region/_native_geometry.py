"""Native owner sites derived from R1. Connector paths remain supported presets."""
from pptx.oxml.xmlchemy import OxmlElement
from image_to_editable_ppt.v3.core.enums import NodeKind, ContainerKind

def element(tag,**attrs):
    obj=OxmlElement("a:"+tag)
    for k,v in attrs.items():
        obj.set(k,str(v))
    return obj

def custom_geometry(primitive,sites):
    """One simple closed path plus normalized connection guides; no auxiliary shapes."""
    supported={NodeKind.BOX,NodeKind.ROUNDED_BOX,NodeKind.ELLIPSE,NodeKind.SECTION,ContainerKind.FLOW_CLUSTER,ContainerKind.PANEL}
    if primitive.shape_kind not in supported:
        raise ValueError("unsupported custom-geometry shape")
    geom=element("custGeom")
    geom.append(element("avLst"))
    guides=element("gdLst")
    geom.append(guides)
    geom.append(element("ahLst"))
    connections=element("cxnLst")
    geom.append(connections)
    for i,(u,v,angle) in enumerate(sites):
        guides.append(element("gd",name=f"r1x{i}",fmla=f"*/ w {round(u*1000000)} 1000000"))
        guides.append(element("gd",name=f"r1y{i}",fmla=f"*/ h {round(v*1000000)} 1000000"))
        site=element("cxn",ang=angle)
        site.append(element("pos",x=f"r1x{i}",y=f"r1y{i}"))
        connections.append(site)
    geom.append(element("rect",l="0",t="0",r="w",b="h"))
    paths=element("pathLst")
    path=element("path",w=100000,h=100000)
    paths.append(path)
    geom.append(paths)
    def command(name,*points):
        cmd=element(name)
        for x,y in points:
            cmd.append(element("pt",x=round(x),y=round(y)))
        path.append(cmd)
    if primitive.shape_kind is NodeKind.ELLIPSE:
        k=27614.2375
        command("moveTo",(50000,0))
        command("cubicBezTo",(50000+k,0),(100000,50000-k),(100000,50000))
        command("cubicBezTo",(100000,50000+k),(50000+k,100000),(50000,100000))
        command("cubicBezTo",(50000-k,100000),(0,50000+k),(0,50000))
        command("cubicBezTo",(0,50000-k),(50000-k,0),(50000,0))
    elif primitive.shape_kind is NodeKind.ROUNDED_BOX:
        radius=.12*min(primitive.bbox.width,primitive.bbox.height)
        rx=radius/primitive.bbox.width*100000
        ry=radius/primitive.bbox.height*100000
        k=.55228475
        command("moveTo",(rx,0))
        command("lnTo",(100000-rx,0))
        command("cubicBezTo",(100000-rx+k*rx,0),(100000,ry-k*ry),(100000,ry))
        command("lnTo",(100000,100000-ry))
        command("cubicBezTo",(100000,100000-ry+k*ry),(100000-rx+k*rx,100000),(100000-rx,100000))
        command("lnTo",(rx,100000))
        command("cubicBezTo",(rx-k*rx,100000),(0,100000-ry+k*ry),(0,100000-ry))
        command("lnTo",(0,ry))
        command("cubicBezTo",(0,ry-k*ry),(rx-k*rx,0),(rx,0))
    else:
        command("moveTo",(0,0))
        for p in ((100000,0),(100000,100000),(0,100000)):
            command("lnTo",p)
    command("close")
    return geom
