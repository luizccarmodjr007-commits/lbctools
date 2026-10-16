#!/usr/bin/env python3
"""s10tool.py - analisa / exporta / reimporta / reconstrói o arquivo "s10" (mesmo contêiner do s05/s08; também serve p/ eles)
(Little Big City 1, Gameloft J2ME, pacote 800x480).

Formato CONFIRMADO nos 11 blocos do s10 fornecido (ver RELATORIO_s10.md):
  arquivo : u16 N | u32 1 | u32 offsets[N+1]      (offsets[0]==6+4*(N+1); offsets[N]==tamanho)
  bloco   : PRE (bytes opacos: assinatura 02 DF 05 B1 85 45 + tabelas de módulos/pontos/frames)
            MARCADOR 44 44 02 56 01 01      (aparece 1x por bloco)
            u8 npal | u16 pal[npal] (ARGB4444 little-endian; pal[0]=0x0F0F = transparente)
            u16 W | u16 H | u32 W*H | W*H bytes de índice (8 bpp, linha a linha)
            (nenhum byte depois dos pixels nos 11 blocos; se houver, é preservado em TAIL)
O que NÃO foi decodificado (PRE) é preservado byte a byte e nunca é alterado.

Comandos:
  info    S10                              resumo da estrutura
  verify  S10                              parse -> serialização == original?  + checagens
  export  S10 PASTA                        bNN.png (RGBA), bNN_indexed.png (índices exatos), manifest.json
  import  S10 BLOCO PNG SAIDA [--rect X Y W H] [--extend-palette] [--force]
  build   S10 PASTA SAIDA [--extend-palette] [--force]   aplica todos os bNN*.png da pasta
  roundtrip S10 PASTA_TRABALHO             export -> build -> compara byte a byte
  diff    A B                              mostra onde dois arquivos diferem (por região)
O arquivo de entrada NUNCA é modificado; a saída é sempre um arquivo novo.
"""
import argparse, hashlib, json, os, struct, sys
from PIL import Image

MARKER = bytes.fromhex('444402560101')
SIG = bytes.fromhex('02df05b18545')   # 6 primeiros bytes de todo bloco (s10, s06, s10); bytes 6..10 variam (ex.: s10 bloco 21 tem byte 7 = 0x10)


# ----------------------------------------------------------------- modelo
class Block:
    def __init__(self, pre, npal, pal, w, h, pix, tail=b''):
        self.pre, self.pal, self.w, self.h, self.pix, self.tail = pre, list(pal), w, h, bytearray(pix), tail

    def serialize(self):
        n = len(self.pal)
        assert 1 <= n <= 255 and len(self.pix) == self.w * self.h
        assert all(p < n for p in self.pix), "índice de pixel >= tamanho da paleta"
        return (self.pre + MARKER + bytes([n]) + struct.pack('<%dH' % n, *self.pal) +
                struct.pack('<HHI', self.w, self.h, self.w * self.h) + bytes(self.pix) + self.tail)


def parse_block(blk):
    pos = [i for i in range(len(blk)) if blk.startswith(MARKER, i)]
    if len(pos) != 1:
        raise ValueError("marcador 44 44 02 56 01 01 encontrado %d vezes (esperado 1)" % len(pos))
    m = pos[0]
    npal = blk[m + 6]
    p = m + 7 + 2 * npal
    pal = struct.unpack_from('<%dH' % npal, blk, m + 7)
    w, h, sz = struct.unpack_from('<HHI', blk, p)
    if sz != w * h or p + 8 + sz > len(blk):
        raise ValueError("campos W/H/size inconsistentes")
    return Block(blk[:m], npal, pal, w, h, blk[p + 8:p + 8 + sz], blk[p + 8 + sz:])


class Cont:
    def __init__(self, data):
        self.n, self.flag = struct.unpack_from('<HI', data, 0)
        offs = struct.unpack_from('<%dI' % (self.n + 1), data, 6)
        if offs[0] != 6 + 4 * (self.n + 1) or offs[-1] != len(data) or list(offs) != sorted(offs):
            raise ValueError("tabela de offsets inconsistente")
        self.offs = offs
        self.blocks = [parse_block(data[offs[k]:offs[k + 1]]) for k in range(self.n)]

    def serialize(self):
        bl = [b.serialize() for b in self.blocks]
        offs, o = [], 6 + 4 * (self.n + 1)
        for b in bl:
            offs.append(o); o += len(b)
        offs.append(o)
        return struct.pack('<HI', self.n, self.flag) + struct.pack('<%dI' % (self.n + 1), *offs) + b''.join(bl)


def load(fn):
    data = open(fn, 'rb').read()
    return data, Cont(data)


def sha(b): return hashlib.sha256(b).hexdigest()


# ----------------------------------------------------------------- cores
def to_rgba(v):                      # ARGB4444 -> RGBA8888 (expansão exata x*17, injetiva)
    return (((v >> 8) & 15) * 17, ((v >> 4) & 15) * 17, (v & 15) * 17, ((v >> 12) & 15) * 17)


def from_rgba(r, g, b, a):           # RGBA8888 -> ARGB4444 (arredonda p/ o nível de 4 bits mais próximo)
    q = lambda c: min(15, (c + 8) // 17)
    return (q(a) << 12) | (q(r) << 8) | (q(g) << 4) | q(b)


def block_rgba(b):
    P = [to_rgba(v) for v in b.pal]
    im = Image.new('RGBA', (b.w, b.h)); im.putdata([P[i] for i in b.pix]); return im


def block_indexed(b):
    im = Image.new('P', (b.w, b.h)); im.putdata(list(b.pix))
    flat = []
    for v in b.pal:
        r, g, bb, a = to_rgba(v); flat += [r, g, bb]
    im.putpalette(flat)
    im.info['transparency'] = bytes(to_rgba(v)[3] for v in b.pal)
    return im


# ----------------------------------------------------------------- comandos
def cmd_info(a):
    data, s = load(a.s10)
    print(f"{a.s10}: {len(data)} bytes, sha256 {sha(data)}")
    print(f"cabeçalho: N={s.n} blocos, u32 fixo={s.flag}, tabela de offsets 0x6..0x{6+4*(s.n+1)-1:X}")
    print(f"{'bl':>2} {'offset':>8} {'bytes':>6} {'PRE':>4} {'WxH':>8} {'npal':>4}  pixels@     pal@   nz-pix")
    for k, b in enumerate(s.blocks):
        a0 = s.offs[k]; pal_o = a0 + len(b.pre) + 7; pix_o = pal_o + 2 * len(b.pal) + 8
        print(f"{k:>2} 0x{a0:06X} {s.offs[k+1]-a0:>6} {len(b.pre):>4} {b.w:>4}x{b.h:<3} {len(b.pal):>4}  0x{pix_o:06X} 0x{pal_o:06X} {sum(1 for p in b.pix if p)}")


def checks(data, s):
    ok = True
    def rep(name, cond, extra=''):
        nonlocal ok; ok &= bool(cond); print(('  OK   ' if cond else '  FALHA'), name, extra)
    rep("serialização(parse(arquivo)) == arquivo", s.serialize() == data)
    rep("offsets[0]==6+4(N+1), crescentes, último==tamanho", True)   # Cont() já levanta erro se falhar
    rep("assinatura 02 DF 05 B1 85 45 em todos os blocos", all(b.pre[:6] == SIG for b in s.blocks))
    rep("marcador único por bloco / sem bytes após os pixels", all(not b.tail for b in s.blocks))
    rep("pal[0]==0x0F0F (transparente) em todos", all(b.pal[0] == 0x0F0F for b in s.blocks))
    rep("max(índice) < npal em todos", all(max(b.pix) < len(b.pal) for b in s.blocks))
    rep("alfa da paleta só 0 ou 15", all((v >> 12) in (0, 15) for b in s.blocks for v in b.pal))
    rep("sem cores duplicadas na paleta", all(len(set(b.pal)) == len(b.pal) for b in s.blocks))
    return ok


def cmd_verify(a):
    data, s = load(a.s10)
    print(f"sha256 {sha(data)}")
    sys.exit(0 if checks(data, s) else 1)


def cmd_export(a):
    data, s = load(a.s10); os.makedirs(a.dir, exist_ok=True)
    man = {'source_sha256': sha(data), 'blocks': []}
    for k, b in enumerate(s.blocks):
        block_rgba(b).save(f"{a.dir}/b{k:02d}.png")
        block_indexed(b).save(f"{a.dir}/b{k:02d}_indexed.png")
        man['blocks'].append({'block': k, 'w': b.w, 'h': b.h, 'npal': len(b.pal),
                              'pal_argb4444': [f"{v:04X}" for v in b.pal]})
        print(f"bloco {k}: {b.w}x{b.h} npal={len(b.pal)} -> b{k:02d}.png / b{k:02d}_indexed.png")
    json.dump(man, open(f"{a.dir}/manifest.json", 'w'), indent=1)


def image_to_indices(b, img, extend):
    """Converte uma imagem (PNG) em índices do bloco b. Devolve (índices, stats). Pode estender b.pal."""
    stats = dict(exact=0, nearest=0, new_colors=0, transparent=0, semi_alpha=0, max_err=0)
    # PNG indexado cuja paleta coincide com a do bloco -> índices usados diretamente
    if img.mode == 'P':
        pal = img.getpalette() or []
        trn = img.info.get('transparency')
        same = len(pal) >= 3 * len(b.pal) and all(
            pal[3*i:3*i+3] == list(to_rgba(v)[:3]) for i, v in enumerate(b.pal))
        raw = img.tobytes()
        if same and max(raw) < len(b.pal):
            stats['exact'] = img.width * img.height
            return list(raw), stats
    rgba = img.convert('RGBA')
    lut = {to_rgba(v): i for i, v in enumerate(b.pal)}
    opaque = [(i, to_rgba(v)) for i, v in enumerate(b.pal) if to_rgba(v)[3] >= 128]
    cache, out = {}, []
    rb = rgba.tobytes()
    for px in zip(rb[0::4], rb[1::4], rb[2::4], rb[3::4]):
        if px not in cache:
            r, g, bb, al = px
            if px in lut:
                cache[px] = (lut[px], 'exact')
            elif al < 128:
                cache[px] = (0, 'transparent')
            else:
                if 0 < al < 255: stats['semi_alpha'] += 1
                v = from_rgba(r, g, bb, 255)
                tgt = to_rgba(v)
                if tgt in lut:
                    cache[px] = (lut[tgt], 'exact')
                elif extend and len(b.pal) < 255:
                    b.pal.append(v); lut[tgt] = len(b.pal) - 1
                    opaque.append((len(b.pal) - 1, tgt)); cache[px] = (lut[tgt], 'new')
                else:
                    best = min(opaque, key=lambda t: sum((x - y) ** 2 for x, y in zip(t[1][:3], (r, g, bb))))
                    err = sum((x - y) ** 2 for x, y in zip(best[1][:3], (r, g, bb))) ** .5
                    stats['max_err'] = max(stats['max_err'], round(err, 1))
                    cache[px] = (best[0], 'nearest')
        i, kind = cache[px]
        out.append(i)
        key = {'exact': 'exact', 'nearest': 'nearest', 'transparent': 'transparent', 'new': 'exact'}[kind]
        stats[key] += 1
    stats['new_colors'] = sum(1 for v in cache.values() if v[1] == 'new')
    return out, stats


def apply_image(s, k, png, rect, extend):
    b = s.blocks[k]
    img = Image.open(png); img.load()
    if rect:
        x0, y0, w, h = rect
        assert img.size == (w, h), f"PNG é {img.size}, recorte pede {(w, h)}"
        assert 0 <= x0 and 0 <= y0 and x0 + w <= b.w and y0 + h <= b.h, "recorte fora do atlas"
    else:
        x0 = y0 = 0
        assert img.size == (b.w, b.h), f"PNG deve ser {b.w}x{b.h} (é {img.size[0]}x{img.size[1]})"
    npal0 = len(b.pal)
    idx, st = image_to_indices(b, img, extend)
    for yy in range(img.height):
        row = (y0 + yy) * b.w + x0
        b.pix[row:row + img.width] = bytes(idx[yy * img.width:(yy + 1) * img.width])
    return st, len(b.pal) - npal0


def write_out(s, outfn, src, force):
    if os.path.realpath(outfn) == os.path.realpath(src):
        sys.exit("ERRO: a saída não pode ser o arquivo original.")
    if os.path.exists(outfn) and not force:
        sys.exit(f"ERRO: {outfn} já existe (use --force).")
    out = s.serialize()
    Cont(out)                                  # re-parse: garante que o resultado é um s10 válido
    open(outfn, 'wb').write(out)
    return out


def cmd_import(a):
    data, s = load(a.s10)
    rect = tuple(a.rect) if a.rect else None
    st, added = apply_image(s, a.block, a.png, rect, a.extend_palette)
    print(f"bloco {a.block}: {st}")
    if added:
        print(f"AVISO: paleta ampliada em {added} cor(es) -> bloco {added*2} bytes maior; offsets dos blocos seguintes "
              f"foram recalculados. Índices existentes não mudam (outros sprites do atlas não são afetados). "
              f"Se algum outro arquivo/código do jogo guardar o tamanho/offset do s10 ou do bloco, precisa ser atualizado.")
    if st['nearest']:
        print(f"AVISO: {st['nearest']} pixel(s) usaram a cor mais próxima da paleta existente (erro RGB máx {st['max_err']}). " +
              ("Paleta cheia (limite 255 cores, u8): não dá para ampliar." if a.extend_palette else "Use --extend-palette para adicionar as cores novas."))
    out = write_out(s, a.out, a.s10, a.force)
    print(f"ok: {a.out} ({len(out)} bytes; original {len(data)}), sha256 {sha(out)}")


def cmd_build(a):
    data, s = load(a.s10)
    for k in range(s.n):
        f = f"{a.dir}/b{k:02d}.png"
        if not os.path.exists(f):
            continue
        st, added = apply_image(s, k, f, None, a.extend_palette)
        print(f"bloco {k}: {st} paleta+{added}")
    out = write_out(s, a.out, a.s10, a.force)
    print(f"ok: {a.out} ({len(out)} bytes), sha256 {sha(out)}")


def cmd_roundtrip(a):
    data, s = load(a.s10)
    class A: pass
    e = A(); e.s10, e.dir = a.s10, f"{a.dir}/png"; cmd_export(e)
    b = A(); b.s10, b.dir, b.out, b.force, b.extend_palette = a.s10, e.dir, f"{a.dir}/s10.rebuilt", True, False
    cmd_build(b)
    new = open(b.out, 'rb').read()
    print("\nIDÊNTICO byte a byte:", new == data, f"({len(data)} vs {len(new)} bytes)")
    print("sha256 original :", sha(data)); print("sha256 rebuilt  :", sha(new))
    sys.exit(0 if new == data else 1)


def region_of(s, pos):
    if pos < 6 + 4 * (s.n + 1): return 'tabela_offsets'
    for k, b in enumerate(s.blocks):
        a0, a1 = s.offs[k], s.offs[k + 1]
        if a0 <= pos < a1:
            m = a0 + len(b.pre); pix = m + 7 + 2 * len(b.pal) + 8
            return f"bloco{k}." + ('PRE' if pos < m else 'marcador/paleta/dims' if pos < pix else 'pixels')
    return '?'


def cmd_diff(a):
    A, B = open(a.a, 'rb').read(), open(a.b, 'rb').read()
    print(f"tamanhos: {len(A)} vs {len(B)}")
    if len(A) != len(B):
        print("tamanhos diferentes: comparação posicional não é significativa após o 1º bloco alterado.");
    sa = Cont(A); sb = Cont(B)
    for k in range(sa.n):
        x, y = sa.blocks[k], sb.blocks[k]
        diffs = [('PRE', x.pre != y.pre), ('paleta', x.pal != y.pal), ('WxH', (x.w, x.h) != (y.w, y.h)),
                 ('pixels', x.pix != y.pix)]
        ch = [n for n, d in diffs if d]
        npix = sum(1 for p, q in zip(x.pix, y.pix) if p != q) if len(x.pix) == len(y.pix) else None
        print(f"bloco {k}: " + (', '.join(ch) + (f" ({npix} pixels diferentes)" if 'pixels' in ch else '') if ch else 'idêntico'))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    p = sp.add_parser('info'); p.add_argument('s10'); p.set_defaults(f=cmd_info)
    p = sp.add_parser('verify'); p.add_argument('s10'); p.set_defaults(f=cmd_verify)
    p = sp.add_parser('export'); p.add_argument('s10'); p.add_argument('dir'); p.set_defaults(f=cmd_export)
    p = sp.add_parser('import'); p.add_argument('s10'); p.add_argument('block', type=int); p.add_argument('png')
    p.add_argument('out'); p.add_argument('--rect', type=int, nargs=4, metavar=('X', 'Y', 'W', 'H'))
    p.add_argument('--extend-palette', action='store_true'); p.add_argument('--force', action='store_true'); p.set_defaults(f=cmd_import)
    p = sp.add_parser('build'); p.add_argument('s10'); p.add_argument('dir'); p.add_argument('out')
    p.add_argument('--extend-palette', action='store_true'); p.add_argument('--force', action='store_true'); p.set_defaults(f=cmd_build)
    p = sp.add_parser('roundtrip'); p.add_argument('s10'); p.add_argument('dir'); p.set_defaults(f=cmd_roundtrip)
    p = sp.add_parser('diff'); p.add_argument('a'); p.add_argument('b'); p.set_defaults(f=cmd_diff)
    a = ap.parse_args(); a.f(a)