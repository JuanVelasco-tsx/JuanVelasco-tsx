#!/usr/bin/env python3
"""Genera las tarjetas de proyecto y los encabezados de sección (claro y oscuro) con la paleta del banner.

Uso:  python scripts/projects/generate_projects.py [carpeta_salida]   (por defecto: dist/)
Datos: scripts/projects/projects.json + API de GitHub (fetch_data.py); paleta: scripts/shared/theme.json.
"""
import json
import math
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from fetch_data import enrich

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CFG = json.loads((HERE / 'projects.json').read_text(encoding='utf-8'))
THEME = json.loads((HERE.parent / 'shared' / 'theme.json').read_text(encoding='utf-8'))
FONT = escape(THEME['font_family'], {'"': '&quot;'})


def f(v, n=1):
    s = f'{v:.{n}f}'.rstrip('0').rstrip('.')
    return s if s not in ('-0', '') else '0'


def wrap(text, width):
    """Parte el texto en líneas de ≤ width caracteres; un '·' se queda al final de la línea, nunca al inicio."""
    lines, cur = [], ''
    for w in re.split(r' (?!·)', text):
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f'{cur} {w}' if cur else w
    return lines + [cur]


def lang_split(langs, top=3):
    """[(nombre, fracción)], máximo `top` lenguajes + 'Otros' (si suma ≥ 1 %)."""
    total = sum(langs.values()) or 1
    items = sorted(langs.items(), key=lambda kv: -kv[1])
    out = [(k, v / total) for k, v in items[:top] if v / total >= 0.01]
    rest = 1 - sum(v for _, v in out)
    if rest >= 0.01:
        out.append(('Otros', rest))
    return out


def svg_open(w, h, label, extra=''):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'font-family="{FONT}" role="img" aria-label="{escape(label)}"{extra}>')


def border_defs(th):
    b = th['border']
    stops = ''.join(f'<stop offset="{f(i / (len(b) - 1), 3)}" stop-color="{c}"/>' for i, c in enumerate(b))
    return (f'<linearGradient id="bd" x1="0" y1="0" x2="1" y2="1">{stops}'
            f'<animateTransform attributeName="gradientTransform" type="rotate" values="0 .5 .5;360 .5 .5" '
            f'dur="8s" repeatCount="indefinite"/></linearGradient>'
            '<filter id="gl" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="6"/></filter>')


def shine_defs(x, w, th):
    """Brillo que cruza un texto (x, ancho w) cada 6 s; en t=0 está fuera del texto, así que no tapa nada."""
    band, c = 90, th['flash']
    return (f'<linearGradient id="sh" gradientUnits="userSpaceOnUse" x1="{f(x - band)}" y1="0" x2="{f(x)}" y2="0">'
            f'<stop offset="0" stop-color="{c}" stop-opacity="0"/><stop offset=".5" stop-color="{c}" stop-opacity=".85"/>'
            f'<stop offset="1" stop-color="{c}" stop-opacity="0"/><animateTransform attributeName="gradientTransform" '
            f'type="translate" values="0 0;0 0;{f(w + band)} 0" keyTimes="0;.75;1" dur="6s" repeatCount="indefinite"/>'
            '</linearGradient>')


def cursor(x, y, size, th):
    return (f'<text x="{f(x)}" y="{f(y)}" font-size="{size}" fill="{th["accent"]}">█<animate attributeName="fill-opacity" '
            f'values="1;1;0;0" keyTimes="0;.5;.5;1" dur="1s" repeatCount="indefinite"/></text>')


def frame(W, H, p, th, title_h, title_fs, body, defs=''):
    """Ventana: fondo, barra de título, contenido y borde animado."""
    o = [svg_open(W, H, f'{p["name"]} — {p["subtitle"]}'), f'<title>{escape(p["name"])}</title>',
         f'<defs>{border_defs(th)}{defs}<clipPath id="c"><rect x="2" y="2" width="{W - 4}" height="{H - 4}" rx="14"/></clipPath></defs>',
         f'<g clip-path="url(#c)"><rect width="{W}" height="{H}" fill="{th["bg"]}"/>'
         f'<rect width="{W}" height="{title_h}" fill="{th["titlebar"]}"/>'
         f'<line x1="0" y1="{title_h + .5}" x2="{W}" y2="{title_h + .5}" stroke="{th["divider"]}"/></g>']
    k = title_h / 38                # escala de la barra respecto a la de escritorio
    for i, c in enumerate(th['window_dots']):
        o.append(f'<circle cx="{f((26 + 20 * i) * k)}" cy="{f(title_h / 2)}" r="{f(5.5 * k)}" fill="{c}"/>')
    title = f'{p["path"]} — git log --oneline'
    dots_end = 71.5 * k + 14
    # centrado si cabe sin pisar los puntos; si no (móvil), justo después de ellos
    x, anchor = (W / 2, 'middle') if len(title) * title_fs * .61 / 2 < W / 2 - dots_end else (dots_end, 'start')
    o.append(f'<text x="{f(x)}" y="{f(title_h / 2 + title_fs * .42, 0)}" text-anchor="{anchor}" font-size="{title_fs}" '
             f'fill="{th["title_text"]}">{escape(title)}</text>')
    o += body
    o.append(f'<rect x="2.5" y="2.5" width="{W - 5}" height="{H - 5}" rx="14" fill="none" stroke="url(#bd)" stroke-width="3" '
             f'opacity=".45" filter="url(#gl)"/>')
    o.append(f'<rect x="2.5" y="2.5" width="{W - 5}" height="{H - 5}" rx="14" fill="none" stroke="url(#bd)" stroke-width="1.6"/>')
    o.append('</svg>')
    return '\n'.join(o)


def label(x, y, text, size, th):
    return f'<text x="{x}" y="{y}" font-size="{size}" letter-spacing="3" fill="{th["muted"]}">{text}</text>'


def name_text(x, y, size, p, th):
    """Nombre del proyecto + una copia encima que lleva el brillo (url(#sh))."""
    t = f'x="{x}" y="{y}" font-size="{size}" font-weight="700"'
    return f'<text {t} fill="{th["values"]}">{escape(p["name"])}</text><text {t} fill="url(#sh)">{escape(p["name"])}</text>'


def chips(a, chip_list, x0, y, size, h, x_max, th):
    """Chips en filas que no pasan de x_max; devuelve (x, y) tras el último, para el cursor."""
    x = x0
    for t in chip_list:
        w = len(t) * size * .6 + 24
        if x + w > x_max and x > x0:
            x, y = x0, y + h + 10
        a(f'<rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="{h}" rx="6" fill="{th["chip_bg"]}" stroke="{th["chip_stroke"]}" '
          f'stroke-opacity=".7"/><text x="{f(x + w / 2)}" y="{f(y + h / 2 + size * .36)}" text-anchor="middle" '
          f'font-size="{size}" fill="{th["labels"]}">{escape(t)}</text>')
        x += w + 10
    return x, y


def donut(a, split, cx, cy, r, sw, lx, ly, step, size, th):
    """Anillo de lenguajes (estático, visible desde t=0) + leyenda desde (lx, ly)."""
    C = 2 * math.pi * r
    a(f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{r}" fill="none" stroke="{th["chip_bg"]}" stroke-width="{sw}"/>')
    off = 0
    for i, (n, fr) in enumerate(split):
        c = th['series'][-1] if n == 'Otros' else th['series'][i]
        seg = C * fr
        gap = 2 if len(split) > 1 else 0
        a(f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{r}" fill="none" stroke="{c}" stroke-width="{sw}" '
          f'stroke-dasharray="{f(max(seg - gap, .5))} {f(C - seg + gap)}" stroke-dashoffset="{f(-off)}" '
          f'transform="rotate(-90 {f(cx)} {f(cy)})"/>')
        off += seg
        y = ly + i * step
        a(f'<rect x="{f(lx)}" y="{f(y - size * .78)}" width="{f(size * .78)}" height="{f(size * .78)}" rx="2" fill="{c}"/>'
          f'<text x="{f(lx + size * 1.35)}" y="{f(y)}" font-size="{size}" fill="{th["values"]}">{escape(n)} '
          f'<tspan fill="{th["muted"]}">{fr * 100:.0f}%</tspan></text>')


def kv_rows(a, rows, x, y, step, size, th):
    for i, (k, v) in enumerate(rows):
        dots = '.' * max(1, 12 - len(k))
        vc = th['accent'] if k == 'estado' else th['values']
        a(f'<text x="{x}" y="{y + i * step}" font-size="{size}" xml:space="preserve"><tspan fill="{th["labels"]}">{escape(k)}</tspan>'
          f'<tspan fill="{th["guide_dots"]}"> {dots} </tspan><tspan fill="{vc}">{escape(v)}</tspan></text>')


# ---------------------------------------------------------------- tarjeta de proyecto
def card(p, th):
    W, H = 1180, 330
    o = []
    a = o.append

    # PROJECT.INFO
    a(label(36, 76, 'PROJECT.INFO', 10, th))
    a(name_text(36, 112, 26, p, th))
    a(f'<text x="36" y="138" font-size="13" fill="{th["labels"]}">{escape(p["subtitle"])}</text>')
    for i, b in enumerate(p['bullets']):
        a(f'<text x="36" y="{180 + i * 28}" font-size="15" fill="{th["values"]}">'
          f'<tspan fill="{th["accent"]}">▸ </tspan>{escape(b)}</text>')
    x, _ = chips(a, p['chips'], 36, 268, 13, 26, W, th)
    a(cursor(x + 4, 287, 16, th))

    # LANG.MAP (o solo las filas, centradas bajo la etiqueta, si el proyecto no muestra lenguajes)
    X0 = 868
    a(f'<line x1="{X0 - 34}" y1="62" x2="{X0 - 34}" y2="{H - 28}" stroke="{th["divider"]}"/>')
    if p.get('show_languages', True):
        a(label(X0, 76, 'LANG.MAP', 10, th))
        donut(a, lang_split(p['languages']), X0 + 46, 148, 38, 14, X0 + 104, 124, 22, 13, th)
        kv_rows(a, p['rows'], X0, 238, 24, 13, th)
    else:
        a(label(X0, 76, 'PROJECT.META', 10, th))
        mid = (76 + H - 28) / 2
        kv_rows(a, p['rows'], X0, round(mid - (len(p['rows']) - 1) * 24 / 2 + 13 * .36), 24, 13, th)
    return frame(W, H, p, th, 38, 12, o, shine_defs(36, len(p['name']) * 26 * .6, th))


def card_mobile(p, th):
    """Versión para celular (600 de ancho): PROJECT.INFO arriba, LANG.MAP abajo, texto ≥ 18 px."""
    W, PAD, FS, LH = 600, 24, 18, 28
    maxc = int((W - 2 * PAD) / (FS * .61))      # .61 em por carácter: margen para las monoespaciadas más anchas
    o = []
    a = o.append

    y = 96
    a(label(PAD, y, 'PROJECT.INFO', FS, th))
    y += 46
    a(name_text(PAD, y, 30, p, th))
    for ln in wrap(p['subtitle'], maxc):
        y += LH + 4
        a(f'<text x="{PAD}" y="{y}" font-size="{FS}" fill="{th["labels"]}">{escape(ln)}</text>')
    y += 14
    for b in p['bullets']:
        for j, ln in enumerate(wrap(b, maxc - 2)):
            y += LH + 2
            pre = f'<tspan fill="{th["accent"]}">▸ </tspan>' if j == 0 else '  '
            a(f'<text x="{PAD}" y="{y}" font-size="{FS}" fill="{th["values"]}" xml:space="preserve">{pre}{escape(ln)}</text>')
    x, cy = chips(a, p['chips'], PAD, y + 26, FS, 34, W - PAD, th)
    a(cursor(x + 4, cy + 25, 20, th))

    y = cy + 34 + 30
    a(f'<line x1="{PAD}" y1="{y}" x2="{W - PAD}" y2="{y}" stroke="{th["divider"]}"/>')
    y += 44
    if p.get('show_languages', True):
        a(label(PAD, y, 'LANG.MAP', FS, th))
        split = lang_split(p['languages'])
        r, sw, step = 52, 18, 32
        cx, dcy = PAD + r + sw / 2, y + 30 + r + sw / 2
        donut(a, split, cx, dcy, r, sw, cx + r + sw / 2 + 30, dcy - (len(split) - 1) * step / 2 + FS * .36, step, FS, th)
        y = dcy + r + sw / 2 + 50
    else:
        a(label(PAD, y, 'PROJECT.META', FS, th))
        y += 44
    kv_rows(a, p['rows'], PAD, y, 32, FS, th)
    H = int(y + (len(p['rows']) - 1) * 32 + 34)
    return frame(W, H, p, th, 52, FS, o, shine_defs(PAD, len(p['name']) * 30 * .6, th))


# ---------------------------------------------------------------- encabezado de sección
def header(h, th):
    W, H = 1180, 58
    return '\n'.join([
        # alto fijo en el README + "slice": en pantallas estrechas se recorta la derecha y el texto no encoge
        svg_open(W, H, f'{h["path"]} $ {h["command"]}', ' preserveAspectRatio="xMinYMid slice"'),
        f'<text x="4" y="36" font-size="22" xml:space="preserve"><tspan fill="{th["labels"]}" font-weight="700">'
        f'{escape(h["path"])}</tspan><tspan fill="{th["muted"]}"> $ </tspan><tspan fill="{th["values"]}">'
        f'{escape(h["command"])} </tspan><tspan fill="{th["accent"]}">█<animate attributeName="fill-opacity" '
        f'values="1;1;0;0" keyTimes="0;.5;.5;1" dur="1s" repeatCount="indefinite"/></tspan></text>',
        f'<line x1="0" y1="{H - .5}" x2="{W}" y2="{H - .5}" stroke="{th["rule"]}"/>',
        '</svg>'])


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'dist'
    out.mkdir(parents=True, exist_ok=True)
    projects = enrich(CFG['projects'])
    for name, th in THEME['themes'].items():
        for p in projects:
            (out / f'card-{p["slug"]}-{name}.svg').write_text(card(p, th), encoding='utf-8', newline='\n')
            (out / f'card-{p["slug"]}-mobile-{name}.svg').write_text(card_mobile(p, th), encoding='utf-8', newline='\n')
        for h in CFG['headers']:
            (out / f'header-{h["slug"]}-{name}.svg').write_text(header(h, th), encoding='utf-8', newline='\n')
    for fp in sorted(out.glob('*.svg')):
        print(f'{fp.name}: {fp.stat().st_size / 1024:.1f} KB')


if __name__ == '__main__':
    main()
