"""R1: export fixed R0 scenes without running detection or OCR."""
import argparse
import json
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image

from image_to_editable_ppt.research.native_emit import load_scene,normalize_scene,write_native_sites,endpoint_audit
from image_to_editable_ppt.research.region_first import digest,inspect_pptx
from image_to_editable_ppt.v3.emit import sample_shape_styles,write_pptx


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    manifest=root/"benchmarks/region_first_r1_inputs_v1.json"
    inputs=json.loads(manifest.read_text(encoding="utf-8"))["inputs"]
    samples={s["id"]:s for s in json.loads((root/"benchmarks/region_first_r0_v1.json").read_text(encoding="utf-8"))["samples"]}
    for item in inputs:
        for key in ("scene","baseline_pptx"):
            if digest(root/item[key+"_path"])!=item[key+"_sha256"]:
                raise ValueError(f"R0 artifact drift: {item['sample']} {key}")
        s=samples[item["sample"]]
        if digest(root/s["path"])!=s["sha256"]:
            raise ValueError("source drift")
    output=root/args.output_dir
    output.mkdir(parents=True,exist_ok=False)
    result=dict(status="r1_emitter_diagnostic_not_reconstruction_acceptance",manifest_sha256=digest(manifest),
        git_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip(),
        git_status=subprocess.check_output(["git","status","--porcelain"],cwd=root,text=True).strip(),
        code_sha256={p:digest(root/p) for p in ("src/image_to_editable_ppt/research/native_emit.py","tools/run_native_emit_experiment.py","src/image_to_editable_ppt/v3/emit/pptx_writer.py")},records=[])
    for item in inputs:
        scene=load_scene(root/item["scene_path"])
        with Image.open(root/samples[item["sample"]]["path"]) as img:
            styles=sample_shape_styles(np.asarray(img.convert("RGB")),scene)
        normalized=normalize_scene(scene)
        for arm in ("normalize_only","normalized_sites"):
            path=output/f"{item['sample']}--{arm}.pptx"
            sites=None
            if arm=="normalize_only":
                write_pptx(normalized,path,styles=styles)
            else:
                sites=write_native_sites(normalized,path,styles=styles)
            audit=endpoint_audit(path,normalized)
            record=dict(sample=item["sample"],arm=arm,input_scene_sha256=item["scene_sha256"],
                path=str(path.relative_to(root)),sha256=digest(path),native=inspect_pptx(path),
                endpoint_audit=audit,sites=sites)
            result["records"].append(record)
            (output/"results.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
            print(f"{path.name}: endpoints {sum(r['bound_endpoints'] for r in audit)}, max error {max((r['max_coordinate_error_px'] for r in audit),default=0):.3f}px",flush=True)


if __name__=="__main__":
    main()
