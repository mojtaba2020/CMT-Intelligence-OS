"""Generate a neutral printed test card for offline OCR validation. No employer records."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BASE=Path(__file__).resolve().parent

def generate(out:Path):
    im=Image.new('RGB',(1200,1360),'white');d=ImageDraw.Draw(im)
    font_path='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    font=ImageFont.truetype(font_path,34)
    title=ImageFont.truetype(font_path,42)
    lines=['Project: SYNTHETIC-001','Date: 2026-10-26','Slump: 4.5','Air Content: 5.2',
           'Concrete Temp: 76','Field Technician: DEMO ONLY','Laboratory data pending independent review']
    d.text((75,70),'CMT NEUTRAL SAMPLE - SYNTHETIC',font=title,fill='black')
    for i,line in enumerate(lines):d.text((95,190+125*i),line,font=font,fill='black')
    d.text((95,1180),'NOT AN OFFICIAL ENGINEERING RECORD',font=font,fill='black')
    out.parent.mkdir(parents=True,exist_ok=True);im.save(out)
    return out

if __name__=='__main__':
    path=generate(BASE/'examples'/'SYNTHETIC_PRINTED_CONCRETE_V19.png')
    print(path)
