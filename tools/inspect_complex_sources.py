"""Source-only selection contact sheets, never consult candidate outputs."""
import json
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageOps

root=Path(__file__).resolve().parents[1]
out=root/'artifacts/region-complex-v1/selection'; out.mkdir(parents=True,exist_ok=False)
data=json.loads((root/'benchmarks/phase16_dev_v1/manifest.json').read_text())
items=[(s['id'],root/s['path']) for s in data['samples'] if s['kind']=='diagram']
items.append(('original-input',root/'input.png'))
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',18)
for offset in range(0,len(items),9):
    page=Image.new('RGB',(1350,990),'#e8edf2'); draw=ImageDraw.Draw(page)
    for index,(name,path) in enumerate(items[offset:offset+9]):
        with Image.open(path) as im:
            rgb=im.convert('RGB'); thumb=ImageOps.contain(rgb,(430,290))
            x,y=(index%3)*450,(index//3)*330
            draw.text((x+10,y+5),f'{name} {im.width}x{im.height}',font=font,fill='black')
            page.paste(thumb,(x+10+(430-thumb.width)//2,y+35+(290-thumb.height)//2))
    path=out/f'sources-{offset//9}.png'; page.save(path); print(path)
