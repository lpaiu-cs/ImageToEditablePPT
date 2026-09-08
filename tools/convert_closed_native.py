"""One image -> editable partial native PPT, with a fixed research configuration."""
import argparse
import json
from pathlib import Path
from PIL import Image
from prepare_opaque_rgb import prepare
from run_closed_rect_proposal_probe import run
from run_region_rgb_baseline import digest,save


def convert(image,output):
    image=Path(image).resolve();output=Path(output).resolve()
    original_sha=digest(image);cli_sha=digest(Path(__file__))
    with Image.open(image) as im:
        mode=im.mode
        if mode not in ('RGB','RGBA') or (mode=='RGBA' and im.getextrema()[3]!=(255,255)):
            raise ValueError('RGB or fully opaque RGBA required; transparent pixels are not silently composited')
    output.mkdir(parents=True,exist_ok=False)
    source=image
    if mode=='RGBA':
        source=output/'input-rgb.png';prepare(image,source)
    run(source,output/'native',trace=True,boundary_union=True,owned_text=True,
        portrait_boxes=True,texture_guard=True,nested_owners=True,pixel_agreement=True,portrait_text=True)
    assert digest(image)==original_sha and digest(Path(__file__))==cli_sha
    result=json.loads((output/'native/result.json').read_text(encoding='utf-8'))
    handoff=dict(status='partial_research_draft_requires_review' if result['nodes'] else 'no_confident_structure',
        production_approved=False,configuration='closed-native-v2',input_path=str(image),input_sha256=original_sha,input_mode=mode,
        rgb_sha256=digest(source),cli_sha256=cli_sha,
        pptx=str(output/'native/result.pptx'),pptx_sha256=result['pptx_sha256'],
        nodes=result['nodes'],labels=result['labels'],native_edges=len(result['emitted_scene']['connectors']),
        native_lock_sha256=digest(output/'native/lock.json'),
        limitations=['Missing structures and labels are intentional when uncertain.',
            'Texture veto is not a general diagram-versus-photo classifier.',
            'Inspect the actual PowerPoint render before using the draft.'])
    save(output/'handoff.json',handoff)
    print(json.dumps(handoff,ensure_ascii=False,indent=2))
    return handoff


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True,help='New directory; existing output is never overwritten')
    args=parser.parse_args();convert(args.image,args.output)
