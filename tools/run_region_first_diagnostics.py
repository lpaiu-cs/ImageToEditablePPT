"""Run the preregistered, development-only R0 intervention matrix."""
from __future__ import annotations
import argparse
from dataclasses import replace
import importlib.metadata
import json
from pathlib import Path
import subprocess

import numpy as np

from image_to_editable_ppt.research.region_first import (
    digest,draw_overlay,evaluate,inspect_pptx,manual_box_inputs,recover_scene,
    scene_for_pptx,serialize_scene,validate_sample,
)
from image_to_editable_ppt.v3.emit import sample_shape_styles,write_pptx


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",default="benchmarks/region_first_r0_v1.json")
    parser.add_argument("--output-dir",required=True)
    parser.add_argument("--overlays-only",action="store_true")
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    manifest=root/args.manifest
    data=json.loads(manifest.read_text(encoding="utf-8"))
    if data["schema_version"]!="region_first_r0_v1" or "diagnostics_not_acceptance" not in data["purpose"]:
        raise ValueError("not the R0 diagnostic contract")
    # Preflight all samples before creating anything. Fail closed on missing/drifted sources.
    inputs=[(s,validate_sample(s,root)) for s in data["samples"]]
    output=root/args.output_dir
    output.mkdir(parents=True,exist_ok=False)
    code_paths=["src/image_to_editable_ppt/research/region_first.py","tools/run_region_first_diagnostics.py",
        "src/image_to_editable_ppt/ml/visual_geometry.py","src/image_to_editable_ppt/ml/visual_connectors.py",
        "src/image_to_editable_ppt/v3/text/ocr.py","src/image_to_editable_ppt/v3/emit/pptx_writer.py",
        "src/image_to_editable_ppt/v3/emit/style.py"]
    summary=dict(schema_version="region_first_r0_results_v1",status="diagnostic_not_acceptance",
        git_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip(),
        git_status=subprocess.check_output(["git","status","--porcelain"],cwd=root,text=True).strip(),
        manifest_sha256=digest(manifest),code_sha256={p:digest(root/p) for p in code_paths},
        versions={p:importlib.metadata.version(p) for p in ("numpy","Pillow","python-pptx","opencv-python-headless","rapidocr-onnxruntime")},
        records=[])
    for sample,image in inputs:
        draw_overlay(image,sample,output/f"{sample['id']}-targets.png")
        if args.overlays_only:
            continue
        for arm in ("full_cv","roi_cv","oracle_boxes"):
            kwargs={} if arm=="full_cv" else dict(roi=sample["roi"])
            if arm=="oracle_boxes":
                kwargs["manual_boxes"]=manual_box_inputs(sample)
            scene=recover_scene(image,**kwargs)
            name=f"{sample['id']}--{arm}"
            scene_path=output/f"{name}.json"
            scene_path.write_text(json.dumps(serialize_scene(scene),indent=2,ensure_ascii=False),encoding="utf-8")
            pptx_path=output/f"{name}.pptx"
            styles=sample_shape_styles(np.asarray(image),scene)
            write_pptx(scene_for_pptx(scene),pptx_path,styles=styles)
            draw_overlay(image,sample,output/f"{name}-overlay.png",scene)
            record=dict(sample=sample["id"],arm=arm,manual_information=arm!="full_cv",source_sha256=sample["sha256"],
                scene_path=str(scene_path.relative_to(root)),scene_sha256=digest(scene_path),
                pptx_path=str(pptx_path.relative_to(root)),pptx_sha256=digest(pptx_path),
                metrics=evaluate(scene,sample),native=inspect_pptx(pptx_path))
            summary["records"].append(record)
            (output/"results.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf-8")
            m=record["metrics"]
            print(f"{name}: objects {m['matched_objects']}/{m['target_objects']}; edges {m['matched_directed_edges']}/{m['target_edges']}; local-extra {len(m['unmatched_local_objects'])}; excluded {len(m['excluded_region_hits'])}",flush=True)
    (output/"results.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf-8")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
