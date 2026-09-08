import importlib.util
import json
from pathlib import Path
import sys
import numpy as np
from PIL import Image
import pytest


@pytest.fixture
def cli(monkeypatch):
    tools=Path(__file__).resolve().parents[1]/'tools'
    monkeypatch.syspath_prepend(str(tools))
    spec=importlib.util.spec_from_file_location('closed_cli_under_test',tools/'convert_closed_native.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    def fake_run(source,output,**kwargs):
        assert kwargs==dict(trace=True,boundary_union=True,owned_text=True,portrait_boxes=True,texture_guard=True,
            nested_owners=True,pixel_agreement=True,portrait_text=True,spatial_texture=True)
        assert Image.open(source).mode=='RGB'
        output.mkdir()
        pptx=output/'result.pptx';pptx.write_bytes(b'unit-test-boundary-only-not-real-ppt')
        (output/'lock.json').write_text('{}')
        (output/'result.json').write_text(json.dumps(dict(pptx_sha256=module.digest(pptx),
            nodes=1,labels=1,emitted_scene=dict(connectors=[]))))
    monkeypatch.setattr(module,'run',fake_run)
    return module


def test_opaque_alpha_conversion_preserves_original_and_pixel_values(cli,tmp_path):
    source=tmp_path/'source.png';rgb=np.full((32,32,4),255,np.uint8);rgb[:,:,:3]=(50,100,150)
    Image.fromarray(rgb).save(source);before=source.read_bytes()
    out=tmp_path/'out';result=cli.convert(source,out)
    assert source.read_bytes()==before
    assert np.array_equal(np.array(Image.open(out/'input-rgb.png')),rgb[:,:,:3])
    assert not result['production_approved']
    assert result['configuration']=='closed-native-v3'
    assert result['input_mode']=='RGBA'
    assert result['input_sha256']==cli.digest(source)


def test_transparent_input_fails_before_output_creation(cli,tmp_path):
    source=tmp_path/'transparent.png';Image.new('RGBA',(32,32),(0,0,0,0)).save(source)
    out=tmp_path/'out'
    with pytest.raises(ValueError):cli.convert(source,out)
    assert not out.exists()


def test_existing_output_is_not_overwritten(cli,tmp_path):
    source=tmp_path/'source.png';Image.new('RGB',(32,32),'white').save(source)
    out=tmp_path/'out';out.mkdir();marker=out/'keep.txt';marker.write_text('keep')
    with pytest.raises(FileExistsError):cli.convert(source,out)
    assert marker.read_text()=='keep'
