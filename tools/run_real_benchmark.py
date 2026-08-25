"""Run the fixed real-figure benchmark and bind inputs, models, and PPTX outputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from image_to_editable_ppt.ml.model_bundle import load_model_bundle, sha256_file
from tools.evaluate_pptx_editability import evaluate


def _sample_acceptance(sample: dict[str, object], summary: dict[str, object], thresholds: dict[str, float]) -> dict[str, object]:
    nodes = int(summary["nodes"])
    containers = int(summary["containers"])
    primitives = nodes + containers
    connectors = int(summary["connectors"])
    if sample["kind"] == "non_diagram":
        empty = nodes == 0 and containers == 0 and connectors == 0
        return {"passed": empty, "expected": "empty", "observed_empty": empty}
    ground_truth = sample["ground_truth"]
    minimum_primitives = int(ground_truth["verified_min_primitives"])
    maximum_primitives = int(ground_truth["verified_max_primitives"])
    minimum_connectors = int(ground_truth["verified_min_connectors"])
    maximum_connectors = int(ground_truth["verified_max_connectors"])
    primitive_fraction = min(1.0, primitives / max(1, minimum_primitives))
    connector_fraction = min(1.0, connectors / max(1, minimum_connectors))
    within_upper_bounds = primitives <= maximum_primitives and connectors <= maximum_connectors
    passed = (
        primitive_fraction >= thresholds["diagram_min_primitive_fraction"]
        and connector_fraction >= thresholds["diagram_min_connector_fraction"]
        and within_upper_bounds
    )
    return {
        "passed": passed,
        "expected": "diagram",
        "verified_min_primitives": minimum_primitives,
        "verified_max_primitives": maximum_primitives,
        "verified_min_connectors": minimum_connectors,
        "verified_max_connectors": maximum_connectors,
        "observed_primitives": primitives,
        "primitive_fraction": primitive_fraction,
        "connector_fraction": connector_fraction,
        "within_upper_bounds": within_upper_bounds,
    }


def _conversion_args(args: argparse.Namespace, first_input: Path) -> argparse.Namespace:
    from image_to_editable_ppt.ml.convert_to_pptx import build_parser

    argv = [str(first_input), "--width", str(args.width), "--models-dir", str(args.models_dir)]
    if args.bundle:
        argv.extend(["--bundle", str(args.bundle)])
    if args.allow_candidate_bundle:
        argv.append("--allow-candidate-bundle")
    for enabled, flag in (
        (args.no_ml, "--no-ml"),
        (args.no_gate, "--no-gate"),
        (args.no_ocr, "--no-ocr"),
        (args.no_style, "--no-style"),
    ):
        if enabled:
            argv.append(flag)
    return build_parser().parse_args(argv)


def _model_binding(args: argparse.Namespace) -> dict[str, object]:
    if args.no_ml:
        return {"mode": "heuristic"}
    bundle_path = Path(args.bundle) if args.bundle else Path(args.models_dir) / "model_bundle.json"
    bundle = load_model_bundle(bundle_path)
    return {
        "mode": "ml_bundle",
        "bundle": str(bundle.path),
        "bundle_sha256": bundle.sha256,
        "status": bundle.status,
        "checkpoints": {
            role: str(path) if path is not None else None for role, path in bundle.checkpoints.items()
        },
    }


def run_benchmark(args: argparse.Namespace) -> dict[str, object]:
    from image_to_editable_ppt.ml.convert_to_pptx import _build_provider, convert_one

    manifest_path = Path(args.manifest).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = Path(args.root).resolve()
    samples = manifest["samples"]
    if not samples:
        raise ValueError("benchmark manifest has no samples")
    conversion_args = _conversion_args(args, root / samples[0]["path"])
    provider = None if args.no_ml else _build_provider(conversion_args)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, object]] = []
    failures = 0
    for sample in samples:
        input_path = root / sample["path"]
        actual_input_sha = sha256_file(input_path)
        if actual_input_sha != sample["sha256"]:
            raise ValueError(f"input hash mismatch for {sample['id']}: {actual_input_sha}")
        output_path = output_dir / f"{sample['id']}.pptx"
        try:
            summary = convert_one(input_path, output_path, args=conversion_args, provider=provider)
            native_report = evaluate(output_path, None)
            native_objects = native_report["native_objects"]
            editable_counts = {
                "nodes": native_objects["nodes"],
                "containers": native_objects["containers"],
                "connectors": native_objects["semantic_connectors"],
            }
            acceptance = _sample_acceptance(sample, editable_counts, manifest["acceptance"])
            record = {
                "id": sample["id"],
                "kind": sample["kind"],
                "input": str(input_path),
                "input_sha256": actual_input_sha,
                "output": str(output_path),
                "output_sha256": sha256_file(output_path),
                "summary": summary,
                "native_objects": native_objects,
                "endpoint_bindings": native_report["endpoint_bindings"],
                "acceptance": acceptance,
            }
        except Exception as error:
            failures += 1
            record = {
                "id": sample["id"],
                "kind": sample["kind"],
                "input": str(input_path),
                "input_sha256": actual_input_sha,
                "error": f"{type(error).__name__}: {error}",
                "acceptance": {"passed": False},
            }
        records.append(record)

    diagram_records = [record for record in records if record["kind"] == "diagram"]
    non_diagram_records = [record for record in records if record["kind"] == "non_diagram"]
    diagram_pass_rate = sum(bool(record["acceptance"]["passed"]) for record in diagram_records) / len(diagram_records)
    non_diagram_reject_rate = sum(bool(record["acceptance"]["passed"]) for record in non_diagram_records) / len(non_diagram_records)
    thresholds = manifest["acceptance"]
    passed = (
        failures == 0
        and diagram_pass_rate >= thresholds["required_diagram_pass_rate"]
        and non_diagram_reject_rate >= thresholds["required_non_diagram_reject_rate"]
    )
    result = {
        "schema_version": "real_figure_benchmark_run_v1",
        "benchmark_manifest": str(manifest_path),
        "benchmark_manifest_sha256": sha256_file(manifest_path),
        "model": _model_binding(args),
        "settings": {
            "width": args.width,
            "ocr": not args.no_ocr,
            "style": not args.no_style,
            "gate": not args.no_gate and not args.no_ml,
        },
        "summary": {
            "passed": passed,
            "failures": failures,
            "diagram_pass_rate": diagram_pass_rate,
            "non_diagram_reject_rate": non_diagram_reject_rate,
        },
        "samples": records,
    }
    output_manifest = output_dir / "run_manifest.json"
    output_manifest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("benchmarks/real_v1/manifest.json"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--models-dir", type=Path, default=Path("workbench-ml"))
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--allow-candidate-bundle", action="store_true")
    parser.add_argument("--width", type=int, default=768)
    parser.add_argument("--no-ml", action="store_true")
    parser.add_argument("--no-gate", action="store_true")
    parser.add_argument("--no-ocr", action="store_true")
    parser.add_argument("--no-style", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_benchmark(args)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(json.dumps(result["summary"], indent=2))
    return 0 if result["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
