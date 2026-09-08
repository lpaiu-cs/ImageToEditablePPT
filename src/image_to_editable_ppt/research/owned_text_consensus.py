"""Combine fixed image-only text observations without choosing against reference text."""
from image_to_editable_ppt.research.closed_rect_proposals import observe_text
from image_to_editable_ppt.research.source_text_rows import observe_rows


def balanced_prefix(lines):
    """Do not export an opening explanatory bracket whose later rows were omitted."""
    pairs={')':'(',']':'[','}':'{'};stack=[];last=0
    for index,line in enumerate(lines):
        invalid=False
        for char in line['text']:
            if char in '([{':stack.append(char)
            elif char in pairs:
                if not stack or stack.pop()!=pairs[char]:invalid=True;break
        if invalid:break
        if not stack:last=index+1
    return lines[:last]


def select_label(db_label,db_audit,row_label,row_audit):
    db_lines=db_audit['accepted'];row_lines=row_audit['accepted']
    chosen=[];reason='both_abstained';method=None
    if db_lines and row_lines:
        common=min(len(db_lines),len(row_lines))
        if all(a['text']==b['text'] for a,b in zip(db_lines[:common],row_lines[:common])):
            chosen,method=(row_lines,'source_rows') if len(row_lines)>len(db_lines) else (db_lines,'spatial_ocr')
            reason='shared_complete_prefix'
        else:reason='conflicting_source_observations'
    elif db_lines:
        # A one-character transcription can silently discard a hat/accent.
        if len((db_label or '').strip())==1:reason='single_glyph_requires_row_agreement'
        else:chosen=db_lines;method='spatial_ocr';reason='only_spatial_ocr_approved'
    elif row_lines:
        if len((row_label or '').strip())==1:reason='single_glyph_requires_spatial_agreement'
        else:chosen=row_lines;method='source_rows';reason='only_source_rows_approved'
    observed=chosen
    chosen=balanced_prefix(chosen)
    label='\n'.join(l['text'] for l in chosen) or None
    return label,dict(accepted=chosen,observed_accepted=observed,withheld_incomplete_lines=observed[len(chosen):],
        method=method,reason=reason,spatial_ocr=db_audit,source_rows=row_audit)


def observe_owned_label(rgb,candidate,owned,excluded,engine):
    db_label,db_audit=observe_text(rgb,candidate['bbox'],engine,excluded=excluded,whole_lines=True)
    row_label,row_audit=observe_rows(rgb,candidate,owned,engine)
    return select_label(db_label,db_audit,row_label,row_audit)
