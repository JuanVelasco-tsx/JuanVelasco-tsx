#!/usr/bin/env python3
"""Genera assets/banner/{dark,light}.svg y banner-mobile-{dark,light}.svg: banner "terminal neofetch" animado con SMIL.

Todos los datos, rutas, colores y tiempos salen de banner.config.json.
Uso:  python scripts/banner/generate_banner.py
"""
import json
import math
import random
import re
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
from PIL import Image, ImageOps
from scipy.optimize import linear_sum_assignment
from scipy.spatial.distance import cdist

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CFG = json.loads((HERE / 'banner.config.json').read_text(encoding='utf-8'))
# paleta y fuente compartidas con las tarjetas de proyectos y los encabezados
CFG.update(json.loads((HERE.parent / 'shared' / 'theme.json').read_text(encoding='utf-8')))

DUR = float(CFG['loop_seconds'])
TL = CFG['timeline']

# --- layout (px absolutos del viewBox)
BOX = (30, 84, 420, 472)            # panel VISUAL.MAP de escritorio: x, y, w, h
GCOLS, GROWS = CFG['portrait']['grid']
PX = min((BOX[2] - 12) / GCOLS, (BOX[3] - 12) / GROWS)
OX = BOX[0] + (BOX[2] - GCOLS * PX) / 2
OY = BOX[1] + (BOX[3] - GROWS * PX) / 2
# el panel del retrato mide lo mismo en las dos versiones: retrato y partículas son idénticos, solo se desplazan.
# ix: x de SYSTEM.INFO; vcol: columna de los valores; wrap: máx. caracteres por valor (None = sin partir)
LAYOUTS = {
    'desktop': dict(W=1180, box=BOX, ix=486, bar=46, title=12, label=10, status=12, name=22, rule=16,
                    fs=16, step=26, vcol=CFG['terminal']['value_column'], wrap=None),
    'mobile': dict(W=600, box=((600 - BOX[2]) // 2, 116) + BOX[2:], ix=24, bar=56, title=18, label=18, status=18,
                   name=26, rule=20, fs=18, step=30, vcol=13, wrap=37),
}


def f(v, n=2):
    """Número compacto para el SVG."""
    s = f'{v:.{n}f}'.rstrip('0').rstrip('.')
    return s if s not in ('-0', '') else '0'


# ---------------------------------------------------------------- imágenes
def load_layers():
    p = CFG['portrait']
    v1 = Image.open(ROOT / p['v1']).convert('RGBA')
    v3 = Image.open(ROOT / p['v3']).convert('RGBA')
    al = p['v3_align']
    size = int(v3.width * al['scale'])
    s = v3.resize((size, size), Image.LANCZOS)
    v3a = Image.new('RGBA', v1.size, (0, 0, 0, 0))
    v3a.paste(s, (al['dx'], al['dy']), s)
    box = tuple(p['crop'])
    return v1.crop(box), v3a.crop(box)


def dither(im, gamma):
    """Floyd–Steinberg a 3 tonos (+ transparente) sobre la rejilla GCOLSxGROWS; alfa como máscara."""
    lo, hi = CFG['portrait']['levels']
    im = im.resize((GCOLS, GROWS), Image.LANCZOS)
    a = np.array(im)[..., 3] / 255.
    g = np.array(ImageOps.grayscale(im.convert('RGB')), float) / 255.
    g = np.clip((g - lo) / (hi - lo), 0, 1) ** gamma
    v = g * a
    lv = np.array([0, .33, .66, 1.])
    e = v.tolist()
    q = np.zeros((GROWS, GCOLS), int)
    for y in range(GROWS):
        row, nxt = e[y], e[y + 1] if y + 1 < GROWS else None
        for x in range(GCOLS):
            o = row[x]
            i = int(np.abs(lv - o).argmin())
            q[y, x] = i
            err = o - lv[i]
            if x + 1 < GCOLS:
                row[x + 1] += err * 7 / 16
            if nxt is not None:
                if x > 0:
                    nxt[x - 1] += err * 3 / 16
                nxt[x] += err * 5 / 16
                if x + 1 < GCOLS:
                    nxt[x + 1] += err / 16
    q[a < 0.5] = 0
    return q


def runs(q, rows=None, cap=None):
    """Fusiona celdas contiguas del mismo tono de cada fila en rectángulos (y, x, largo, tono)."""
    out = []
    for y in (range(GROWS) if rows is None else rows):
        x = 0
        while x < GCOLS:
            t = q[y, x]
            if t == 0:
                x += 1
                continue
            x0 = x
            while x < GCOLS and q[y, x] == t and (cap is None or x - x0 < cap):
                x += 1
            out.append((y, x0, x - x0, t))
    return out


def pathd(rs):
    return ''.join(f'M{x} {y}h{n}v1h-{n}z' for y, x, n, _ in rs)


# ---------------------------------------------------------------- logos
def rasterize(svg_path, size):
    """Alfa (size x size) del SVG. cairosvg; si falta libcairo (p. ej. Windows) usa Chromium vía Playwright."""
    data = Path(svg_path).read_bytes()
    try:
        import cairosvg
        png = cairosvg.svg2png(bytestring=data, output_width=size, output_height=size)
    except (ImportError, OSError):
        png = _rasterize_playwright(data.decode('utf-8'), size)
    from io import BytesIO
    return np.array(Image.open(BytesIO(png)).convert('RGBA'))[..., 3]


def _rasterize_playwright(svg, size):
    from playwright.sync_api import sync_playwright
    svg = svg.replace('<svg ', f'<svg width="{size}" height="{size}" ', 1)
    html = f'<html><body style="margin:0;background:transparent">{svg}</body></html>'
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={'width': size, 'height': size})
        pg.set_content(html)
        png = pg.screenshot(omit_background=True, clip={'x': 0, 'y': 0, 'width': size, 'height': size})
        b.close()
    return png


def sample_logo(alpha, n):
    """n puntos en rejilla hexagonal sobre la zona rellena; devuelve (puntos centrados en 0, separación)."""
    mask = alpha > 127
    S = alpha.shape[0]

    def grid(s):
        pts = []
        dy = s * math.sqrt(3) / 2
        j = 0
        y = dy / 2
        while y < S:
            x = s / 2 + (s / 2 if j % 2 else 0)
            while x < S:
                if mask[int(y), int(x)]:
                    pts.append((x, y))
                x += s
            y += dy
            j += 1
        return pts

    lo, hi = 1.0, 40.0
    for _ in range(40):             # mayor separación con al menos n puntos
        mid = (lo + hi) / 2
        if len(grid(mid)) >= n:
            lo = mid
        else:
            hi = mid
    pts = np.array(grid(lo), float)
    pts = pts[np.linspace(0, len(pts) - 1, n).round().astype(int)]
    return pts - S / 2, lo


def assign(src, dst):
    """Reordena dst para que dst[i] sea el destino de la partícula i, minimizando la distancia total."""
    r, c = linear_sum_assignment(cdist(src, dst))
    out = np.empty_like(dst)
    out[r] = dst[c]
    return out


# ---------------------------------------------------------------- SMIL
def anim(attr, pairs, extra='', ease=False):
    """<animate> en bucle; pairs = [(segundo, valor), ...] con 0 y DUR incluidos."""
    kt = ';'.join(f(t / DUR, 4) for t, _ in pairs)
    vs = ';'.join(str(v) for _, v in pairs)
    if ease:
        ks = ';'.join('.45 0 .25 1' if pairs[i][1] != pairs[i + 1][1] else '0 0 1 1'
                      for i in range(len(pairs) - 1))
        extra += f' calcMode="spline" keySplines="{ks}"'
    return (f'<animate attributeName="{attr}" values="{vs}" keyTimes="{kt}" dur="{f(DUR)}s" '
            f'repeatCount="indefinite"{extra}/>')


def anim_tr(pairs, ease=True):
    kt = ';'.join(f(t / DUR, 4) for t, _ in pairs)
    vs = ';'.join(v for _, v in pairs)
    extra = ''
    if ease:
        ks = ';'.join('.45 0 .25 1' if pairs[i][1] != pairs[i + 1][1] else '0 0 1 1'
                      for i in range(len(pairs) - 1))
        extra = f' calcMode="spline" keySplines="{ks}"'
    return (f'<animateTransform attributeName="transform" type="translate" values="{vs}" keyTimes="{kt}" '
            f'dur="{f(DUR)}s" repeatCount="indefinite"{extra}/>')


def once(begin, dur=0.4):
    """Aparición de una sola vez (no se repite en el bucle)."""
    return f'<animate attributeName="opacity" from="0" to="1" begin="{f(begin)}s" dur="{f(dur)}s" fill="freeze"/>'


def info_lines(rows, vcol, width):
    """[(clave, texto)] de SYSTEM.INFO; con width, los valores largos siguen en otra línea con clave ''."""
    out = []
    for k, v in rows:
        parts = [v]
        if width:
            parts, cur = [], ''
            for w in re.split(r' (?!·)', v):       # un '·' nunca empieza línea
                if cur and len(cur) + 1 + len(w) > width:
                    parts.append(cur)
                    cur = w
                else:
                    cur = f'{cur} {w}' if cur else w
            parts.append(cur)
        out.append((k, parts[0]))
        out += [('', x) for x in parts[1:]]
    return out


def shine_defs(x, w, th):
    """Brillo que cruza un texto (x, ancho w) cada 6 s; en t=0 está fuera del texto, así que no tapa nada."""
    band, c = 90, th['flash']
    return (f'<linearGradient id="sh" gradientUnits="userSpaceOnUse" x1="{f(x - band)}" y1="0" x2="{f(x)}" y2="0">'
            f'<stop offset="0" stop-color="{c}" stop-opacity="0"/><stop offset=".5" stop-color="{c}" stop-opacity=".85"/>'
            f'<stop offset="1" stop-color="{c}" stop-opacity="0"/><animateTransform attributeName="gradientTransform" '
            f'type="translate" values="0 0;0 0;{f(w + band)} 0" keyTimes="0;.75;1" dur="6s" repeatCount="indefinite"/>'
            '</linearGradient>')


def luminance(hexc):
    r, g, b = (int(hexc[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


# ---------------------------------------------------------------- escena
class Scene:
    """Cálculos independientes del tema que dependen de la semilla (partículas, grupos)."""

    def __init__(self):
        random.seed(CFG['seed'])
        self.rng = np.random.default_rng(CFG['seed'])
        self.v1, self.v3 = load_layers()
        pc = CFG['particles']
        n = pc['count']
        self.n = n
        cx, cy = BOX[0] + BOX[2] / 2 - OX, BOX[1] + BOX[3] / 2 - OY   # centro del panel en coords locales
        self.logos = []
        for lg in pc['logos']:
            pts, sp = sample_logo(rasterize(ROOT / lg['svg'], lg['size']), n)
            self.logos.append((pts + (cx, cy), sp))
            print(f'  logo {lg["name"]}: separación {sp:.2f}px')
        self.stagger = self.rng.uniform(0, TL['stagger'], n)
        self.groups_seed = CFG['seed']

    def particles(self, q1, q3):
        """Recorridos: píxeles de v1 -> logos -> silueta de v3 (cada tramo con asignación óptima)."""
        rng = np.random.default_rng(CFG['seed'] + 1)

        def cells(q):
            ys, xs = np.nonzero(q >= 2)
            idx = rng.choice(len(ys), self.n, replace=False)
            return np.stack([(xs[idx] + .5) * PX, (ys[idx] + .5) * PX], 1), q[ys[idx], xs[idx]]

        start, tones = cells(q1)
        end, _ = cells(q3)
        path = [start]
        for pts, _ in self.logos:
            path.append(assign(path[-1], pts))
        path.append(assign(path[-1], end))
        return path, tones


def build(theme_name, scene, layout):
    th = CFG['themes'][theme_name]
    tm = CFG['terminal']
    L = LAYOUTS[layout]
    W, box = L['W'], L['box']
    ox = box[0] + (box[2] - GCOLS * PX) / 2
    oy = box[1] + (box[3] - GROWS * PX) / 2
    lines = info_lines(tm['rows'], L['vcol'], L['wrap'])
    # SYSTEM.INFO: a la derecha del retrato en escritorio, debajo en móvil
    iy = box[1] - 12 if layout == 'desktop' else box[1] + box[3] + 18 + L['status'] + 54
    rows_y = iy + 88
    fy = box[1] + box[3] - 12 if layout == 'desktop' else rows_y + (len(lines) - 1) * L['step'] + 64
    H = 610 if layout == 'desktop' else fy + 40
    P = CFG['portrait']
    tones = th['tones']
    col = {1: tones[0], 2: tones[1], 3: tones[2]}
    bright = max((1, 2, 3), key=lambda k: luminance(col[k]))   # "tono claro" que pulsa

    q1 = dither(scene.v1, P['gamma_v1'])
    q3 = dither(scene.v3, P['gamma_v3'])
    path, ptones = scene.particles(q1, q3)

    s0, s1 = TL['scan']
    hit = TL['hit']
    c0, c1 = TL['crack']
    p0, p1 = TL['pulse']
    d0, d1 = TL['dissolve']
    mv = TL['moves']
    r0, r1 = TL['v3_return']
    o0, o1 = TL['particles_out']

    sx = GCOLS / (P['crop'][2] - P['crop'][0])
    CX = (P['crack_center'][0] - P['crop'][0]) * sx * PX
    CY = (P['crack_center'][1] - P['crop'][1]) * sx * PX
    RMAX = math.ceil(max(math.hypot(CX - x, CY - y) for x in (0, GCOLS * PX) for y in (0, GROWS * PX)))
    radius = [(0, 0), (c0, 0), (c1, RMAX), (r0 - .01, RMAX), (r0, 0), (DUR, 0)]
    rspl = 'calcMode="spline" keySplines="0 0 1 1;.2 .8 .3 1;0 0 1 1;0 0 1 1;0 0 1 1"'

    o = []
    a = o.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
      f'font-family="{escape(CFG["font_family"], {chr(34): "&quot;"})}" role="img" '
      f'aria-label="{escape(tm["header"])} — {escape(tm["title"])}">')
    a(f'<title>{escape(tm["header"])} · {escape(tm["rows"][1][1])}</title>')

    # ---------------- defs
    b = th['border']
    stops = ''.join(f'<stop offset="{f(i / (len(b) - 1))}" stop-color="{c}"/>' for i, c in enumerate(b))
    a('<defs>')
    a(f'<linearGradient id="bd" x1="0" y1="0" x2="1" y2="1">{stops}'
      f'<animateTransform attributeName="gradientTransform" type="rotate" values="0 .5 .5;360 .5 .5" '
      f'dur="8s" repeatCount="indefinite"/></linearGradient>')
    a(f'<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{th["bg"]}"/>'
      f'<stop offset="1" stop-color="{th["bg2"]}"/></linearGradient>')
    a(shine_defs(L['ix'], len(tm['header']) * L['name'] * .6, th))
    a('<filter id="gl" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="7"/></filter>')
    a('<filter id="g3" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="3"/></filter>')
    a(f'<clipPath id="win"><rect x="2" y="2" width="{W - 4}" height="{H - 4}" rx="18"/></clipPath>')
    a(f'<clipPath id="pc"><rect x="{box[0]}" y="{box[1]}" width="{box[2]}" height="{box[3]}" rx="10"/></clipPath>')
    m = f'maskUnits="userSpaceOnUse" x="-50" y="-50" width="{box[2] + 100}" height="{box[3] + 100}"'
    a(f'<mask id="m1" {m}><circle cx="{f(CX, 1)}" cy="{f(CY, 1)}" r="0" fill="#fff">{anim("r", radius, " " + rspl)}</circle></mask>')
    a(f'<mask id="m3" {m}><rect x="-50" y="-50" width="{box[2] + 100}" height="{box[3] + 100}" fill="#fff"/>'
      f'<circle cx="{f(CX, 1)}" cy="{f(CY, 1)}" r="0" fill="#000">{anim("r", radius, " " + rspl)}</circle></mask>')

    # partículas: un rect por tono; su tamaño y color se animan una sola vez para las 900 <use>
    def dot(sz):
        return f(sz, 2)
    sizes = [PX] + [min(sp * 0.8, 7.5) for _, sp in scene.logos] + [PX]
    size_pairs = [(0, dot(PX)), (mv[0][0], dot(PX))]
    for k, (t0, t1) in enumerate(mv):
        size_pairs.append((t1, dot(sizes[k + 1])))
        if k + 1 < len(mv):
            size_pairs.append((mv[k + 1][0], dot(sizes[k + 1])))
    size_pairs.append((DUR, dot(PX)))
    half = [(t, f(-float(v) / 2, 2)) for t, v in size_pairs]
    for k in (2, 3):
        cpairs = [(0, col[k]), (mv[0][0], col[k]), (mv[0][1], th['particle_logo']),
                  (mv[-1][0], th['particle_logo']), (mv[-1][1], col[k]), (DUR, col[k])]
        a(f'<rect id="p{k}" x="{half[0][1]}" y="{half[0][1]}" width="{dot(PX)}" height="{dot(PX)}" fill="{col[k]}">'
          f'{anim("width", size_pairs, ease=True)}{anim("height", size_pairs, ease=True)}'
          f'{anim("x", half, ease=True)}{anim("y", half, ease=True)}{anim("fill", cpairs)}</rect>')
    a('</defs>')

    # ---------------- ventana
    a(f'<rect x="2" y="2" width="{W - 4}" height="{H - 4}" rx="18" fill="{th["bg"]}"/>')
    a('<g clip-path="url(#win)">')
    a(f'<rect x="2" y="2" width="{W - 4}" height="{H - 4}" fill="url(#bg)"/>')
    bar = L['bar']
    a(f'<rect x="2" y="2" width="{W - 4}" height="{bar}" fill="{th["titlebar"]}"/>')
    a(f'<line x1="2" y1="{bar + 2}" x2="{W - 2}" y2="{bar + 2}" stroke="{th["divider"]}"/>')
    k = bar / 46                    # escala de la barra respecto a la de escritorio
    for i, c in enumerate(th['window_dots']):
        a(f'<circle cx="{f((30 + 20 * i) * k)}" cy="{f(bar / 2 + 2)}" r="{f(5.5 * k)}" fill="{c}"/>')
    a(f'<text x="{W / 2}" y="{f(bar / 2 + 2 + L["title"] * .33, 0)}" text-anchor="middle" font-size="{L["title"]}" '
      f'fill="{th["title_text"]}">{escape(tm["title"])}</text>')

    # ---------------- VISUAL.MAP
    a(f'<text x="{box[0] + 2}" y="{box[1] - 12}" font-size="{L["label"]}" letter-spacing="3" fill="{th["muted"]}">{escape(tm["portrait_label"])}</text>')
    a(f'<rect x="{box[0]}" y="{box[1]}" width="{box[2]}" height="{box[3]}" rx="10" fill="none" stroke="{th["accent"]}" '
      f'stroke-width="2" opacity=".35" filter="url(#g3)"/>')
    a(f'<rect x="{box[0]}" y="{box[1]}" width="{box[2]}" height="{box[3]}" rx="10" fill="{th["panel_bg"]}" stroke="{th["panel_stroke"]}"/>')

    a(f'<g clip-path="url(#pc)"><g transform="translate({f(ox)},{f(oy)})">')
    shake = [(0, '0 0'), (hit, '0 0'), (hit + .05, '-4 2'), (hit + .1, '4 -3'), (hit + .15, '-3 -1'),
             (hit + .2, '2 3'), (hit + .3, '0 0'), (DUR, '0 0')]
    a(f'<g>{anim_tr(shake, ease=False)}')

    # v3: escaneo inicial (una sola vez) + visibilidad en bucle
    v3vis = [(0, 1), (c1 + .1, 1), (c1 + .11, 0), (r0, 0), (r1, 1), (DUR, 1)]
    a(f'<g mask="url(#m3)"><g>{anim("opacity", v3vis)}<g transform="scale({f(PX, 4)})" shape-rendering="crispEdges">')
    B = P['scan_bands']
    bh = math.ceil(GROWS / B)
    for k in range(B):
        rs = runs(q3, range(k * bh, min((k + 1) * bh, GROWS)))
        if not rs:
            continue
        t = s0 + (s1 - s0) * k / B
        a(f'<g opacity="0">{once(t, .15)}')
        for tone in (1, 2, 3):
            d = pathd([r for r in rs if r[3] == tone])
            if d:
                a(f'<path fill="{col[tone]}" d="{d}"/>')
        a('</g>')
    a('</g></g></g>')

    # v1: revelado radial, pulso y disolución por grupos aleatorios
    rnd = random.Random(scene.groups_seed)
    G = P['dissolve_groups']
    groups = {g: [] for g in range(G)}
    for r in runs(q1, cap=6):
        groups[rnd.randrange(G)].append(r)
    pulse = [(0, 1), (p0, 1), (p0 + .6, .5), (p0 + 1.2, 1), (p0 + 1.8, .5), (p1, 1), (DUR, 1)]
    a(f'<g mask="url(#m1)"><g transform="scale({f(PX, 4)})" shape-rendering="crispEdges">')
    for g in range(G):
        t = d0 + (d1 - d0 - .35) * g / (G - 1)
        a(f'<g>{anim("opacity", [(0, 1), (t, 1), (t + .35, 0), (r1, 0), (r1 + .01, 1), (DUR, 1)])}')
        for tone in (1, 2, 3):
            d = pathd([r for r in groups[g] if r[3] == tone])
            if d:
                extra = anim('opacity', pulse) if tone == bright else ''
                a(f'<path fill="{col[tone]}" d="{d}">{extra}</path>')
        a('</g>')
    a('</g></g>')

    # frente de la grieta: anillo punteado + destello
    a(f'<circle cx="{f(CX, 1)}" cy="{f(CY, 1)}" r="0" fill="none" stroke="{th["flash"]}" stroke-width="3" '
      f'stroke-dasharray="2 5" opacity="0">{anim("r", radius, " " + rspl)}'
      f'{anim("opacity", [(0, 0), (hit, 0), (hit + .05, .9), (c1, 0), (DUR, 0)])}</circle>')
    a(f'<circle cx="{f(CX, 1)}" cy="{f(CY, 1)}" r="30" fill="{th["flash"]}" filter="url(#gl)" opacity="0">'
      f'{anim("opacity", [(0, 0), (hit, 0), (hit + .04, .6), (hit + .3, 0), (DUR, 0)])}</circle>')

    # partículas
    pvis = [(0, 0), (d0, 0), (d0 + .5, 1), (o0, 1), (o1, 0), (DUR, 0)]
    a(f'<g opacity="0">{anim("opacity", pvis)}')
    for i in range(scene.n):
        dl = scene.stagger[i]
        pts = [p[i] for p in path]
        fr = [(0, pts[0]), (mv[0][0] + dl, pts[0])]
        for k, (t0, t1) in enumerate(mv):
            fr.append((t1 + dl, pts[k + 1]))
            if k + 1 < len(mv):
                fr.append((mv[k + 1][0] + dl, pts[k + 1]))
        fr.append((DUR, pts[-1]))
        fr = [(t, f'{f(x, 1)} {f(y, 1)}') for t, (x, y) in fr]
        a(f'<use href="#p{ptones[i]}">{anim_tr(fr)}</use>')
    a('</g>')
    a('</g></g></g>')

    # línea de escaneo (solo en la intro)
    a(f'<rect x="{box[0]}" y="{box[1]}" width="{box[2]}" height="2" fill="{th["accent"]}" opacity="0" filter="url(#g3)">'
      f'<animate attributeName="y" from="{f(oy)}" to="{f(oy + GROWS * PX)}" begin="{s0}s" dur="{f(s1 - s0)}s" fill="freeze"/>'
      f'<set attributeName="opacity" to=".9" begin="{s0}s"/><set attributeName="opacity" to="0" begin="{s1 + .15}s"/></rect>')

    # esquinas de visor
    x0, y0, x1, y1, arm = box[0] - 5, box[1] - 5, box[0] + box[2] + 5, box[1] + box[3] + 5, 16
    for (x, y, sx_, sy_) in [(x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)]:
        a(f'<path d="M{x} {y + sy_ * arm}V{y}H{x + sx_ * arm}" fill="none" stroke="{th["accent"]}" stroke-width="2"/>')

    # status bajo el retrato
    sl = tm['status_labels']
    sy = box[1] + box[3] + 18 + L['status']
    st = [('stable', th['labels'], [(0, 1), (hit, 1), (hit + .01, 0), (r0, 0), (r0 + .01, 1), (DUR, 1)]),
          ('fractured', th['header'], [(0, 0), (hit, 0), (hit + .01, 1), (d0, 1), (d0 + .01, 0), (DUR, 0)]),
          ('particles', th['accent'], [(0, 0), (d0, 0), (d0 + .01, 1), (r0, 1), (r0 + .01, 0), (DUR, 0)])]
    for key, c, pr in st:
        a(f'<text x="{box[0] + 2}" y="{sy}" font-size="{L["status"]}" fill="{th["muted"]}" opacity="{pr[0][1]}">status: '
          f'<tspan fill="{c}">{escape(sl[key])}</tspan>{anim("opacity", pr)}</text>')

    # ---------------- SYSTEM.INFO (estático: se lee completo sin depender de la animación)
    ix, fs = L['ix'], L['fs']
    a(f'<text x="{ix}" y="{iy}" font-size="{L["label"]}" letter-spacing="3" fill="{th["muted"]}">{escape(tm["info_label"])}</text>')
    user, _, host = tm['header'].partition('@')
    t = f'x="{ix}" y="{iy + 38}" font-size="{L["name"]}" font-weight="700"'
    a(f'<text {t}><tspan fill="{th["labels"]}">{escape(user)}</tspan><tspan fill="{th["muted"]}">@</tspan>'
      f'<tspan fill="{th["header"]}">{escape(host)}</tspan></text><text {t} fill="url(#sh)">{escape(tm["header"])}</text>')
    a(f'<text x="{ix}" y="{iy + 56}" font-size="{L["rule"]}" fill="{th["guide_dots"]}">{"─" * len(tm["header"])}</text>')
    col_v = L['vcol']
    for i, (k, v) in enumerate(lines):
        y = rows_y + i * L['step']
        if k:
            dots = '.' * max(1, col_v - len(k) - 2)
            a(f'<text x="{ix}" y="{y}" font-size="{fs}" xml:space="preserve">'
              f'<tspan fill="{th["labels"]}">{escape(k)}</tspan><tspan fill="{th["guide_dots"]}"> {dots} </tspan>'
              f'<tspan fill="{th["values"]}">{escape(v)}</tspan></text>')
        else:
            a(f'<text x="{ix}" y="{y}" font-size="{fs}" xml:space="preserve" fill="{th["values"]}">{" " * col_v}{escape(v)}</text>')
    a(f'<line x1="{ix}" y1="{fy - 30}" x2="{W - 40 if layout == "desktop" else W - ix}" y2="{fy - 30}" stroke="{th["divider"]}"/>')
    a(f'<text x="{ix}" y="{fy}" font-size="{fs}" xml:space="preserve">'
      f'<tspan fill="{th["accent"]}">● {escape(tm["live_label"])}<animate attributeName="fill-opacity" '
      f'values="1;.25;1" dur="1.6s" repeatCount="indefinite"/></tspan>'
      f'<tspan fill="{th["values"]}">   {escape(tm["footer_text"])} </tspan>'
      f'<tspan fill="{th["labels"]}">█<animate attributeName="fill-opacity" values="1;1;0;0" keyTimes="0;.5;.5;1" '
      f'dur="1s" repeatCount="indefinite"/></tspan></text>')
    sw = [th['bg2']] + list(dict.fromkeys(tones + th['border']))
    right = W - 40 if layout == 'desktop' else W - ix
    for i, c in enumerate(sw[:7]):
        # el primero es del color del fondo: borde con más contraste para que se distinga
        stroke = f'stroke="{th["muted"]}" stroke-width="1.5"' if i == 0 else f'stroke="{th["panel_stroke"]}"'
        a(f'<rect x="{right - 22 * (7 - i)}" y="{fy - 14}" width="18" height="18" rx="3" fill="{c}" {stroke}/>')
    a('</g>')
    # borde con gradiente animado (rotación entre morados)
    a(f'<rect x="3" y="3" width="{W - 6}" height="{H - 6}" rx="17" fill="none" stroke="url(#bd)" stroke-width="3" '
      f'opacity=".5" filter="url(#gl)"/>')
    a(f'<rect x="3" y="3" width="{W - 6}" height="{H - 6}" rx="17" fill="none" stroke="url(#bd)" stroke-width="1.6"/>')
    a('</svg>')
    return '\n'.join(o)


def main():
    scene = Scene()
    for layout, outputs in (('desktop', CFG['output']), ('mobile', CFG['output_mobile'])):
        for name, rel in outputs.items():
            out = ROOT / rel
            out.write_text(build(name, scene, layout), encoding='utf-8', newline='\n')
            print(f'{rel}: {out.stat().st_size / 1024:.0f} KB')


if __name__ == '__main__':
    main()
