"""Conservative local table row line segmentation (v2.0).

Uses only geometry; it does NOT claim to recognize handwriting, assign values,
approve CMT results, or connect to ElmTree. It supports synthetic, authorized
images only. Each result requires independent inspection of original pixels.
"""
from __future__ import annotations
from dataclasses import dataclass
from forms.local_ocr_v19 import open_image

MAX_ROWS=100

@dataclass(frozen=True)
class Line:
    y:int
    width:int


def detect_table_grid(data:bytes, *, min_width_ratio:float=.55)->dict:
    if not .3<=min_width_ratio<=.95:raise ValueError('invalid width ratio')
    im=open_image(data)
    try:import cv2,numpy as np
    except ImportError as exc:raise RuntimeError('Optional local OpenCV required; install requirements-table.txt') from exc
    arr=np.asarray(im.convert('L'))
    _,bw=cv2.threshold(arr,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
    # Morphological opening of long horizontal rules, robust to printed text.
    width=im.width
    kernel=cv2.getStructuringElement(cv2.MORPH_RECT,(max(50,width//8),1))
    long=cv2.morphologyEx(bw,cv2.MORPH_OPEN,kernel)
    counts=np.sum(long>0,axis=1)
    rows=np.where(counts >= int(width*min_width_ratio))[0].tolist()
    bands=[]
    for y in rows:
        if bands and y<=bands[-1][-1]+1:bands[-1].append(y)
        else:bands.append([y])
    marks=[Line(int(round(sum(b)/len(b))),int(counts[b[len(b)//2]])) for b in bands]
    segments=[]
    for a,b in zip(marks,marks[1:]):
        gap=b.y-a.y
        if gap<18:continue  # Not a real form row
        if len(segments)>=MAX_ROWS:break
        segments.append({'row_index':len(segments)+1,'top_px':a.y+1,'bottom_px':b.y-1,
                         'height_px':gap-2,'needs_human_review':True})
    return {'schema':'cmt-grid-proposals-v2.0','image_size':[im.width,im.height],
            'horizontal_guides_px':[x.y for x in marks[:MAX_ROWS+1]],
            'row_boxes':segments,'autofill_allowed':False,
            'warning':'Geometric candidates only; excludes handwriting recognition, engineering acceptance and ElmTree import.'}
