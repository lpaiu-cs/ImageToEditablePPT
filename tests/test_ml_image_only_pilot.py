import importlib.util
from pathlib import Path

import pytest
import torch

spec = importlib.util.spec_from_file_location('ml_pilot', Path(__file__).parents[1] / 'tools/ml_image_only_pilot.py')
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def test_legacy_section_anchor_and_container_semantics_survive_enum_insertion():
    from image_to_editable_ppt.ml.dataset import label_to_kind
    mapped = pilot.map_legacy_labels(torch.tensor([1,2,3,4,5,6]))
    assert [label_to_kind(int(i)).value for i in mapped] == ['box','rounded_box','section','label_anchor','flow_cluster','panel']
    assert pilot.map_current_targets(mapped).tolist() == [1,2,3,4,5,6]


def test_legacy_training_rejects_new_ellipse_instead_of_relabelling():
    with pytest.raises(ValueError, match='ellipse'):
        pilot.map_current_targets(torch.tensor([3]))


def test_gt_guard_blocks_source_annotation_in_separate_process():
    import subprocess
    import sys
    command = "import sys; sys.path.insert(0, 'tools'); from ml_image_only_pilot import install_gt_guard; install_gt_guard(); open('C:/vs/ImageToEditablePPT/workbench-ml/ds-v13-soffice/dataset_manifest.json')"
    result = subprocess.run([sys.executable, '-c', command], capture_output=True, text=True, cwd=Path(__file__).parents[1])
    assert result.returncode != 0
    assert 'GT access forbidden' in result.stderr
