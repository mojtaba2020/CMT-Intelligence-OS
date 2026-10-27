"""Generated printed grid segmentation benchmark; NOT real handwriting accuracy."""
from __future__ import annotations
from io import BytesIO
from PIL import Image,ImageDraw,ImageFont
from forms.table_rows_v20 import detect_table_grid


def fixture(n=8,width=1000):
    im=Image.new('RGB',(width,160+n*60),'white');d=ImageDraw.Draw(im)
    left,right=40,width-40;top=100;step=60
    # Horizontal rule length close to full image width: easy synthetic grid.
    for j in range(n+1):
        y=top+j*step;d.line((left,y,right,y),fill='black',width=3)
    for x in [left,350,550,720,right]:d.line((x,top,x,top+n*step),fill='black',width=2)
    for j in range(n):d.text((65,top+j*step+18),f'T-{j+1:02}   {118.0+j*.4:.1f}   {12.0+j*.1:.1f}',fill='black')
    b=BytesIO();im.save(b,format='PNG');return b.getvalue(),[top+j*step for j in range(n+1)]


def benchmark():
    result=[]
    for n in (2,4,8,12,20):
        data,expected=fixture(n)
        got=detect_table_grid(data,min_width_ratio=.65)
        actual=got['horizontal_guides_px']
        matched=sum(1 for y in expected if any(abs(y-z)<=3 for z in actual))
        result.append({'synthetic_rows':n,'true_lines':len(expected),'detected_lines':len(actual),
                       'matched_lines':matched,'detected_row_regions':len(got['row_boxes'])})
    return result
if __name__=='__main__':
    import json
    print(json.dumps({'scope':'synthetic printed lines only; NOT handwritten OCR benchmark','runs':benchmark()},indent=2))
