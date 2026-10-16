#!/usr/bin/env python3
"""s06tool.py - exporta/reimporta atlas do s06 (Little Big City 1, 800x480).
Layout confirmado por análise (ver relatório):
  arquivo : u16 N | u32 1 | u32 offsets[N+1]  (último offset == tamanho do arquivo)
  bloco   : [cabeçalho/tabelas] u8 npal | u16 pal[npal] (ARGB4444 LE) | u16 W | u16 H | u32 W*H | W*H bytes (índices 8bpp)
Uso:
  python s06tool.py export s06 saida/            -> saida/bNN.png (+ bNN_indexed.png)
  python s06tool.py import s06 BLOCO nova.png novo_s06 [x y w h]
     nova.png = imagem do atlas (mesmo W x H) ou recorte x,y,w,h colado no atlas.
     Só altera os bytes de índice (e nunca o tamanho do arquivo).
  python s06tool.py verify s06   -> confere reconstrução byte a byte
"""
import struct, sys, os
from PIL import Image

def load(fn):
    d = bytearray(open(fn,'rb').read())
    n, = struct.unpack_from('<H', d, 0)
    offs = struct.unpack_from('<%dI' % (n+1), d, 6)
    assert offs[-1] == len(d), "tabela de offsets não fecha com o tamanho"
    return d, n, offs

def parse_block(d, a, b):
    blk = d[a:b]
    for p in range(0x40, min(len(blk), 0x400)):
        w, h, sz = struct.unpack_from('<HHI', blk, p)
        if 8 <= w <= 1024 and 8 <= h <= 1024 and sz == w*h and p+8+sz == len(blk):
            for c in range(1, 256):
                if blk[p-2*c-1] == c:
                    pal = list(struct.unpack_from('<%dH' % c, blk, p-2*c))
                    return dict(p=p, w=w, h=h, npal=c, pal=pal, pal_off=a+p-2*c, pix_off=a+p+8)
    return None

def rgba(v):
    return (((v>>8)&15)*17, ((v>>4)&15)*17, (v&15)*17, ((v>>12)&15)*17)

def to4444(r, g, b, a):
    return ((a>>4)<<12) | ((r>>4)<<8) | ((g>>4)<<4) | (b>>4)

def export(fn, outdir):
    d, n, offs = load(fn); os.makedirs(outdir, exist_ok=True)
    for k in range(n):
        i = parse_block(d, offs[k], offs[k+1])
        if not i: print(f"bloco {k}: formato diferente (não decodificado)"); continue
        P = [rgba(v) for v in i['pal']] + [(0,0,0,0)]*(256-i['npal'])
        px = d[i['pix_off']:i['pix_off']+i['w']*i['h']]
        im = Image.new('RGBA', (i['w'], i['h'])); im.putdata([P[x] for x in px])
        im.save(f"{outdir}/b{k:02d}.png")
        print(f"bloco {k}: {i['w']}x{i['h']} pal={i['npal']} pixels@0x{i['pix_off']:X} pal@0x{i['pal_off']:X}")

def import_(fn, k, png, outfn, rect=None):
    d, n, offs = load(fn)
    i = parse_block(d, offs[k], offs[k+1]); assert i, "bloco não decodificável"
    W, H = i['w'], i['h']
    pal = [rgba(v) for v in i['pal']]
    src = Image.open(png).convert('RGBA')
    if rect:
        x0, y0, w, h = rect
        assert src.size == (w, h), "tamanho do PNG != recorte"
    else:
        x0, y0 = 0, 0; assert src.size == (W, H), f"PNG deve ser {W}x{H}"
    def nearest(px):
        r, g, b, a = px
        if a < 128: return 0                      # índice 0 = transparente (confirmar no bloco!)
        best, bi = 1e18, 1
        for j in range(1, len(pal)):
            pr, pg, pb, pa = pal[j]
            dd = (r-pr)**2 + (g-pg)**2 + (b-pb)**2 + (a-pa)**2
            if dd < best: best, bi = dd, j
        return bi
    cache = {}
    for yy in range(src.height):
        for xx in range(src.width):
            px = src.getpixel((xx, yy))
            if px not in cache: cache[px] = nearest(px)
            d[i['pix_off'] + (y0+yy)*W + (x0+xx)] = cache[px]
    open(outfn, 'wb').write(d)
    print("ok: tamanho preservado", len(d))

def verify(fn):
    d, n, offs = load(fn)
    for k in range(n):
        i = parse_block(d, offs[k], offs[k+1])
        print(k, 'ok' if i else 'não decodificado')

if __name__ == '__main__':
    c = sys.argv[1]
    if c == 'export': export(sys.argv[2], sys.argv[3])
    elif c == 'import':
        r = tuple(map(int, sys.argv[7:11])) if len(sys.argv) >= 11 else None
        import_(sys.argv[2], int(sys.argv[3]), sys.argv[4], sys.argv[5], r)
    elif c == 'verify': verify(sys.argv[2])