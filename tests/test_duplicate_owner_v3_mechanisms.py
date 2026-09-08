"""Locked mechanism controls; expectations do not use observer outputs."""
from fractions import Fraction
import numpy as np
import pytest

from image_to_editable_ppt.research.duplicate_owner_v3 import (
    CONTRAST_SCALE,integer_contrast,luminance_numerator,shaft_glyph_contact_guard,
    candidate_support_check,background_speck_mask,
)


@pytest.mark.parametrize('delta',[11,12,13,79,80,81])
@pytest.mark.parametrize('layout',['scalar','crop','fortran','stride'])
def test_integer_cutoff(delta,layout):
    shape=(3,) if layout=='scalar' else (161,187,3)
    rgb=np.full(shape,255-delta,np.uint8)
    if layout=='fortran':rgb=np.asfortranarray(rgb)
    if layout=='stride':rgb=rgb[:,::-1,:]
    out=integer_contrast(rgb,background_luminance2=5100000)
    assert np.all(out['contrast2']==delta*20000)
    assert np.all(out['weak']==(delta>=12)) and np.all(out['core']==(delta>=80))


def test_color_extremes_against_rational_reference():
    rgb=np.array([[255,255,255],[255,0,0],[0,255,0],[0,0,255],[1,254,127]],np.uint8)
    expected=[int(sum(Fraction(int(v))*w for v,w in zip(pixel,[2126,7152,722]))) for pixel in rgb]
    assert luminance_numerator(rgb).tolist()==expected


def test_even_ring_median_exact_half_unit():
    rgb=np.array([[[255,255,255],[254,254,254],[243,243,243]]],np.uint8)
    out=integer_contrast(rgb,np.array([[True,True,False]]))
    assert out['background_luminance2']==5090000
    assert out['contrast2'][0,2]==230000 and not out['weak'][0,2]


@pytest.mark.parametrize('offset,safe',[((0,1),False),((1,1),False),((0,2),True),((0,0),False)])
def test_explicit_contact(offset,safe):
    shaft=np.zeros((20,20),bool);glyph=shaft.copy();shaft[8,8]=True;glyph[8+offset[0],8+offset[1]]=True
    a=shaft.copy();b=glyph.copy()
    assert shaft_glyph_contact_guard(shaft,glyph)['safe'] is safe
    assert np.array_equal(shaft,a) and np.array_equal(glyph,b)


def test_same_component_owner_boundary_is_uncertain():
    shaft=np.zeros((24,24),bool);shaft[2:22,10]=True;glyph=np.zeros_like(shaft);glyph[5:8,10:13]=True
    own=np.zeros_like(shaft);own[3:10,7:15]=True
    out=shaft_glyph_contact_guard(shaft,glyph,original_ink=shaft|glyph,owner_mask=own)
    assert not out['safe'] and out['mixed_components']


def test_separated_shaft_does_not_force_contact():
    shaft=np.zeros((24,24),bool);shaft[2:22,20]=True;glyph=np.zeros_like(shaft);glyph[5:8,8:11]=True
    own=np.zeros_like(shaft);own[3:10,7:15]=True
    assert shaft_glyph_contact_guard(shaft,glyph,original_ink=shaft|glyph,owner_mask=own)['safe']


def test_negative_cell_padding_without_pixel_loss_is_allowed():
    core=np.zeros((20,20),bool);core[4:8,4:8]=True
    result=candidate_support_check(core,core,np.zeros_like(core),[4.25,4.25,7.75,7.75])
    assert result['negative_padding'] and result['eligible'] and not result['veto_components']


def test_same_component_fringe_inside_one_pixel_band():
    core=np.zeros((20,20),bool);core[5:10,5:10]=True;residual=np.zeros_like(core);residual[6,10]=True
    result=candidate_support_check(core,core,residual,[5,5,10,10])
    assert result['eligible'] and result['boundary_components']


def test_fringe_outside_band_is_not_silently_allowed():
    core=np.zeros((20,20),bool);core[5:10,5:10]=True;residual=np.zeros_like(core);residual[6,10:13]=True
    result=candidate_support_check(core,core,residual,[5,5,10,10])
    assert not result['eligible'] and result['veto_components']


@pytest.mark.parametrize('contrast',[8,12,255])
def test_whole_tiny_component_loss_is_vetoed(contrast):
    rgb=np.full((30,30,3),255,np.uint8);rgb[10:16,10:16]=0;rgb[13,19]=255-contrast
    channels=integer_contrast(rgb,background_luminance2=5100000)
    out=candidate_support_check(channels['core'],channels['weak'],channels['residual'],[9,9,17,17])
    assert not out['eligible']


def test_large_core_cut_is_vetoed():
    core=np.zeros((20,20),bool);core[4:14,4:14]=True
    assert not candidate_support_check(core,core,np.zeros_like(core),[4,4,12,14])['eligible']


def test_far_speck_exception_and_near_ambiguity():
    rgb=np.full((100,100,3),255,np.uint8);rgb[40:50,40:50]=0;rgb[80,80]=235;rgb[45,55]=235
    ch=integer_contrast(rgb,background_luminance2=5100000)
    ignored,_=background_speck_mask(ch['core'],ch['weak']|ch['residual'],ch['contrast2'],[40,40,50,50],10)
    assert ignored[80,80] and not ignored[45,55]
    rgb[45,55]=255;ch=integer_contrast(rgb,background_luminance2=5100000)
    ignored,_=background_speck_mask(ch['core'],ch['weak']|ch['residual'],ch['contrast2'],[40,40,50,50],10)
    assert candidate_support_check(ch['core'],ch['weak'],ch['residual'],[39,39,51,51],ignored=ignored)['eligible']


def test_masks_must_be_source_consistent():
    core=np.ones((3,3),bool);empty=np.zeros_like(core)
    with pytest.raises(ValueError):candidate_support_check(core,empty,empty,[0,0,3,3])
