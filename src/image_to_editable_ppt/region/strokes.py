"""Local stroke evidence independent of a particular hue or page polarity."""
import cv2
import numpy as np


def stroke_mask(rgb):
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    k=max(15,min(61,round(min(gray.shape)*.035)))
    if k%2==0: k+=1
    kernel=np.ones((k,k),np.uint8)
    closed=cv2.morphologyEx(gray,cv2.MORPH_CLOSE,kernel)
    opened=cv2.morphologyEx(gray,cv2.MORPH_OPEN,kernel)
    # A dark page is not one enormous stroke. Retain dark ink only when an
    # observed local background differs, without selecting a particular color.
    dark=(gray<110)&(closed.astype(np.int16)-gray>=24)
    chromatic=((rgb.max(axis=2).astype(np.int16)-rgb.min(axis=2)>=60)
        &(rgb.max(axis=2)>=160)&(rgb.min(axis=2)<=160)).astype(np.uint8)
    chromatic=chromatic>cv2.morphologyEx(chromatic,cv2.MORPH_OPEN,kernel)
    # The median guard prevents thin white gaps on a light page from becoming
    # bright strokes merely because two nearby black lines surround them.
    bright=(gray>145)&(cv2.medianBlur(gray,k)<110)&(gray.astype(np.int16)-opened>=24)
    return (dark|chromatic|bright).astype(np.uint8)
