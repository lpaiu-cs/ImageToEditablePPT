"""Create source/PowerPoint comparison sheets, retaining full-render links and hashes."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from PIL import Image,ImageDraw,ImageFont,ImageOps

from image_to_editable_ppt.research.region_first import digest,pixel_box


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",default="benchmarks/region_first_r0_v1.json")
    parser.add_argument("--run-dir",default="artifacts/region-first-r0/run1")
    parser.add_argument("--render-dir",default="artifacts/region-first-r0/run1-renders")
    parser.add_argument("--output-dir",default="artifacts/region-first-r0/review-v1")
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    samples=json.loads((root/args.manifest).read_text(encoding="utf-8"))["samples"]
    run=root/args.run_dir
    renders=root/args.render_dir
    output=root/args.output_dir
    output.mkdir(parents=True,exist_ok=False)
    results=json.loads((run/"results.json").read_text(encoding="utf-8"))
    render_manifest=json.loads((renders/"powerpoint_render_manifest.json").read_text(encoding="utf-8-sig"))
    render_records={r["id"]:r for r in render_manifest["records"]}
    font=ImageFont.truetype("C:/Windows/Fonts/arial.ttf",18)
    review=[]
    for sample in samples:
        columns=[]
        arms=("source","full_cv","roi_cv","oracle_boxes")
        for arm in arms:
            if arm=="source":
                path=root/sample["path"]
            else:
                name=f"{sample['id']}--{arm}"
                path=renders/f"{name}.png"
                record=render_records[name]
                if digest(path)!=record["render_sha256"] or digest(run/f"{name}.pptx")!=record["pptx_sha256"]:
                    raise ValueError(f"render evidence drift: {name}")
            with Image.open(path) as opened:
                frame=opened.convert("RGB")
            scope=frame.crop(pixel_box(sample["roi"],frame.size))
            height=max(160,min(700,round(470*scope.height/scope.width)))
            panel=Image.new("RGB",(490,height+80),"#f1f5f9")
            thumb=ImageOps.contain(scope,(470,height))
            panel.paste(thumb,((490-thumb.width)//2,60+(height-thumb.height)//2))
            draw=ImageDraw.Draw(panel)
            title={"source":"SOURCE (target ROI)","full_cv":"A: full native CV", "roi_cv":"B: MANUAL ROI + CV", "oracle_boxes":"C: MANUAL boxes + roles"}[arm]
            draw.text((10,7),title,font=font,fill="black")
            if arm!="source":
                metrics=next(r["metrics"] for r in results["records"] if r["sample"]==sample["id"] and r["arm"]==arm)
                text=f"Objects {metrics['matched_objects']}/{metrics['target_objects']}, arrows {metrics['matched_directed_edges']}/{metrics['target_edges']}, extra {len(metrics['unmatched_local_objects'])}"
                draw.text((10,31),text,font=font,fill="#334155")
            columns.append(panel)
        sheet=Image.new("RGB",(1960,max(p.height for p in columns)),"white")
        for i,panel in enumerate(columns):
            sheet.paste(panel,(i*490,0))
        path=output/f"{sample['id']}-comparison.png"
        sheet.save(path)
        review.append(dict(sample=sample["id"],comparison_path=str(path.relative_to(root)),sha256=digest(path)))
    (output/"review_manifest.json").write_text(json.dumps(dict(status="awaiting_visual_review_not_acceptance",
        results_sha256=digest(run/"results.json"),render_manifest_sha256=digest(renders/"powerpoint_render_manifest.json"),
        records=review),indent=2),encoding="utf-8")
    print(f"Created {len(review)} source/native-PowerPoint comparison sheets at {output}")


if __name__=="__main__":
    main()
