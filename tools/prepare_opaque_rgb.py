"""Lossless removal of a verified all-255 alpha channel for research input."""
import argparse
from pathlib import Path
import numpy as np
from PIL import Image
from run_region_rgb_baseline import digest,save


def prepare(source,output):
    if output.exists():raise FileExistsError(output)
    with Image.open(source) as im:
        if im.mode!='RGBA' or im.getextrema()[3]!=(255,255):
            raise ValueError('Only RGBA with alpha identically 255 can be stripped losslessly')
        original=np.asarray(im).copy()
        rgb=im.convert('RGB')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as stream:rgb.save(stream,format='PNG')
    with Image.open(output) as im:assert np.array_equal(np.asarray(im),original[:,:,:3])
    save(output.with_suffix('.provenance.json'),dict(source=str(source.resolve()),source_sha256=digest(source),
        rgb_sha256=digest(output),operation='drop only alpha channel after verifying every alpha=255; RGB pixels identical',
        source_size=[original.shape[1],original.shape[0]]))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();prepare(a.source,a.output)
