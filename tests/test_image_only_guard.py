import subprocess
import sys
from pathlib import Path


def test_guard_allows_image_and_own_output_but_denies_gt(tmp_path):
    image = tmp_path / '000.png'
    image.write_bytes(b'image')
    gt = tmp_path / 'answer.disguised'
    gt.write_bytes(b'ground truth')
    out = tmp_path / 'output'
    out.mkdir()
    code_dir = Path(__file__).resolve().parents[1] / 'src'
    script = f'''
from pathlib import Path
from image_to_editable_ppt.research.image_only_guard import install_guard
reads, denied = install_guard({str(image)!r}, {str(out)!r}, {str(code_dir)!r})
assert Path({str(image)!r}).read_bytes() == b'image'
Path({str(out / 'own.pptx')!r}).write_bytes(b'own')
assert Path({str(out / 'own.pptx')!r}).read_bytes() == b'own'
try:
    Path({str(gt)!r}).read_bytes()
except PermissionError:
    pass
else:
    raise AssertionError('GT was readable')
assert len(denied) == 1
'''
    subprocess.run([sys.executable, '-B', '-c', script], check=True)
