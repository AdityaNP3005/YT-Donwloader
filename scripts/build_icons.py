"""Rebuild code-drawn UI assets; Pillow is a development-only dependency."""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'assets'
BLUE = '#1672df'


def logo(size):
    scale = 4
    image = Image.new('RGBA', (size * scale, size * scale))
    draw = ImageDraw.Draw(image)
    k = size * scale / 256
    def box(coords, **kw):
        draw.rounded_rectangle(tuple(round(v * k) for v in coords), **kw)
    def line(coords, fill, width):
        points = [(round(x * k), round(y * k)) for x, y in coords]
        draw.line(points, fill=fill, width=max(1, round(width * k)), joint='curve')
        r = width * k / 2
        for x, y in (points[0], points[-1]):
            draw.ellipse((x-r, y-r, x+r, y+r), fill=fill)
    box((8, 8, 248, 248), radius=round(58*k), fill=BLUE)
    box((37, 57, 219, 188), radius=round(23*k), fill='#ffffff')
    draw.polygon([(round(x*k), round(y*k)) for x,y in [(68,86),(68,155),(120,121)]], fill=BLUE)
    line([(165,89),(165,147)], BLUE, 13)
    line([(145,130),(165,150),(185,130)], BLUE, 13)
    line([(143,168),(188,168)], BLUE, 9)
    box((90, 207, 166, 216), radius=round(4*k), fill='#abd2ff')
    return image.resize((size,size), Image.Resampling.LANCZOS)


PATHS = {
    'link': [('line', [(8,12),(12,8)]), ('arc',(3,8,11,16),45,225), ('arc',(9,2,17,10),225,405)],
    'plus': [('line',[(10,4),(10,16)]),('line',[(4,10),(16,10)])],
    'paste': [('rect',(5,5,16,17)),('rect',(7,2,13,6))],
    'search': [('ellipse',(3,3,13,13)),('line',[(12,12),(17,17)])],
    'stop': [('rect',(5,5,15,15))],
    'download': [('line',[(10,3),(10,12)]),('line',[(6,8),(10,12),(14,8)]),('line',[(3,13),(3,17),(17,17),(17,13)])],
    'pause': [('line',[(7,4),(7,16)]),('line',[(13,4),(13,16)])],
    'cancel': [('ellipse',(3,3,17,17)),('line',[(7,7),(13,13)]),('line',[(13,7),(7,13)])],
    'retry': [('arc',(3,3,17,17),40,320),('line',[(13,2),(17,4),(16,8)])],
    'trash': [('line',[(4,6),(16,6)]),('line',[(6,6),(7,17),(13,17),(14,6)]),('line',[(8,3),(12,3)]),('line',[(9,9),(9,14)]),('line',[(11,9),(11,14)])],
    'folder': [('line',[(2,6),(2,16),(17,16),(18,7),(9,7),(7,4),(2,4),(2,6)])],
    'check': [('rect',(3,3,17,17)),('line',[(6,10),(9,13),(14,7)])],
    'clear': [('rect',(3,3,17,17)),('line',[(7,10),(13,10)])],
    'checkbox-off': [('rect',(3,3,17,17))],
    'checkbox-on': [('rect',(3,3,17,17)),('line',[(6,10),(9,13),(14,7)])],
    'list': [('line',[(7,5),(17,5)]),('line',[(7,10),(17,10)]),('line',[(7,15),(17,15)]),('line',[(3,5),(4,5)]),('line',[(3,10),(4,10)]),('line',[(3,15),(4,15)])],
    'chevron-left': [('line',[(12,5),(7,10),(12,15)])],
    'chevron-right': [('line',[(8,5),(13,10),(8,15)])],
}


def action(name, color, size=18):
    k = 4
    image = Image.new('RGBA',(size*k,size*k))
    d=ImageDraw.Draw(image)
    factor=size*k/20
    width=round(1.65*factor)
    for kind,coords,*angles in PATHS[name]:
        if kind=='line':
            points=[(round(x*factor),round(y*factor)) for x,y in coords]
            d.line(points,fill=color,width=width,joint='curve')
            r=width/2
            for x,y in (points[0],points[-1]):
                d.ellipse((x-r,y-r,x+r,y+r),fill=color)
        else:
            box=tuple(round(v*factor) for v in coords)
            if kind=='ellipse':d.ellipse(box,outline=color,width=width)
            elif kind=='arc':d.arc(box,*angles,fill=color,width=width)
            else:d.rounded_rectangle(box,radius=round(1.5*factor),outline=color,width=width)
    return image.resize((size,size),Image.Resampling.LANCZOS)


def main():
    ASSETS.mkdir(exist_ok=True)
    icons=ASSETS/'icons';icons.mkdir(exist_ok=True)
    for size in (16,24,32,48,64,96,128,144,192,256,512):
        logo(size).save(ASSETS/f'youtube-downloader-{size}.png')
    logo(256).save(ASSETS/'youtube-downloader.ico',sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
    for name in PATHS:
        action(name,'#59728f').save(icons/f'{name}.png')
        action(name,'#ffffff').save(icons/f'{name}-white.png')
        for factor in (2,3):
            action(name,'#59728f',18*factor).save(icons/f'{name}@{factor}x.png')
            action(name,'#ffffff',18*factor).save(icons/f'{name}-white@{factor}x.png')


if __name__=='__main__':
    main()
