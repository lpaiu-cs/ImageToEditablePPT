"""Tamper checks for the artifact-to-native boundary, using no real GT/model."""
from copy import deepcopy
import json
from pathlib import Path
import sys

from PIL import Image
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from run_source_evidence_pipeline import verified_inputs
from run_region_rgb_baseline import digest
from image_to_editable_ppt.research.prediction_handoff import LEGACY_ADAPTER,digest as canonical_digest


def fixture(tmp_path,change=None):
    image=tmp_path/'input.png';Image.new('RGB',(100,100),'white').save(image)
    weight=tmp_path/'opaque.ckpt';weight.write_bytes(b'not loaded by boundary validator')
    code=tmp_path/'inference.py';code.write_text('# fixture')
    row=dict(id='fixture',image=str(image),image_sha256=digest(image))
    lock=dict(git_commit='fixture-sha',class_map=deepcopy(LEGACY_ADAPTER),code_sha256={str(code):digest(code)},
        checkpoint=dict(path=str(weight),sha256=digest(weight)),inputs_sha256='manifest-sha',inputs=[row])
    pred=dict(schema='fresh_rgb_detector_predictions_v1',execution_attested=True,label_adapter=deepcopy(LEGACY_ADAPTER),
        run_git_commit='fixture-sha',inference_code=lock['code_sha256'],checkpoint_sha256=digest(weight),inputs_sha256='manifest-sha',
        predictions=[dict(id='fixture',source_sha256=digest(image),image_size=[100,100],coordinate_system='original_image_pixels',
            source_labels=[1],prediction=dict(boxes=[[10,10,30,30]],scores=[.9],labels=[1]))])
    execution=dict(status='complete',denied_reads=0,samples=1,raw_objects=1)
    reads=dict(events=[dict(allowed=True)])
    data={'predictions.json':pred,'execution-lock.json':lock,'execution.json':execution,'reads.json':reads}
    payload=dict(schema='fresh_rgb_detector_handoff_v1',execution_attested=True,research_only=True,run_git_commit='fixture-sha',
        class_map=deepcopy(LEGACY_ADAPTER),checkpoint_sha256=digest(weight),sample_count=1,raw_object_count=1)
    if change:change(payload,data)
    payload['artifacts']={}
    for name,value in data.items():
        path=tmp_path/name;path.write_text(json.dumps(value),encoding='utf-8')
        payload['artifacts'][name]=dict(path=str(path),sha256=digest(path))
    path=tmp_path/'handoff.json';path.write_text(json.dumps(dict(payload=payload,payload_sha256=canonical_digest(payload))),encoding='utf-8')
    return path


def test_verified_rgb_detector_contract(tmp_path):
    samples,_=verified_inputs(fixture(tmp_path))
    assert len(samples)==1 and len(samples[0]['objects'])==1
    assert set(samples[0]['objects'][0])=={'id','role','semantic_kind','bbox_xyxy','confidence'}


@pytest.mark.parametrize('mode',['artifact','sha','manifest','map','weight','count','samples','denied','failed','gt','geometry','adapter','code','duplicate'])
def test_inconsistent_fresh_attestations_rejected(tmp_path,mode):
    def change(p,d):
        pred=d['predictions.json'];lock=d['execution-lock.json'];ex=d['execution.json']
        if mode=='artifact':d['extra.json']={}
        if mode=='manifest':pred['inputs_sha256']='other'
        if mode=='map':p['class_map']['1']=2
        if mode=='weight':p['checkpoint_sha256']='other'
        if mode=='count':p['raw_object_count']=2
        if mode=='samples':ex['samples']=2
        if mode=='denied':d['reads.json']['events'][0]['allowed']=False
        if mode=='failed':ex['status']='failed'
        if mode=='gt':lock['inputs'][0]['annotation']='forbidden'
        if mode=='geometry':pred['predictions'][0]['prediction']['boxes'][0][2]=101
        if mode=='adapter':pred['predictions'][0]['prediction']['labels'][0]=2
        if mode=='code':lock['code_sha256'][next(iter(lock['code_sha256']))]='other'
        if mode=='duplicate':pred['predictions'].append(deepcopy(pred['predictions'][0]))
    path=fixture(tmp_path,change)
    if mode=='sha':
        value=json.loads(path.read_text());value['payload']['research_only']=False;path.write_text(json.dumps(value))
    with pytest.raises(ValueError):verified_inputs(path)
