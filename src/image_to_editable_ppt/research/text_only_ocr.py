"""Small text-only crops, one frozen transform, no lexical or semantic repair."""
from dataclasses import replace
import math

import cv2
import numpy as np

from image_to_editable_ppt.region.text import recognize_consistent
from image_to_editable_ppt.v3.core.enums import NodeKind


def recover_text_only(scene, rgb, engine):
    h, w = rgb.shape[:2]
    shapes, audit = [], {}
    for shape in scene.shapes:
        if shape.shape_kind is not NodeKind.LABEL_ANCHOR:
            shapes.append(shape)
            continue
        b = shape.bbox
        x0, y0 = max(0, math.floor(b.x0)-2), max(0, math.floor(b.y0)-2)
        x1, y1 = min(w, math.ceil(b.x1)+2), min(h, math.ceil(b.y1)+2)
        record = dict(reason='crop_size_unsupported')
        label = None
        if min(x1-x0, y1-y0) >= 2 and (x1-x0)*(y1-y0) <= 40_000:
            crop = rgb[y0:y1, x0:x1]
            color = np.median(crop.reshape(-1, 3), axis=0).tolist()
            padded = cv2.copyMakeBorder(crop, 16, 16, 16, 16, cv2.BORDER_CONSTANT, value=color)
            enlarged = cv2.resize(padded, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            label, record = recognize_consistent(engine, enlarged)
        audit[shape.id] = dict(record, crop_xyxy=[x0, y0, x1, y1],
                              transform='bbox_expand2_median_border16_bicubic3', previous_label=shape.label)
        shapes.append(replace(shape, label=label))
    return replace(scene, shapes=tuple(shapes)), audit
