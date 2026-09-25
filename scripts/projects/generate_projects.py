#!/usr/bin/env python3
"""Genera las tarjetas de proyecto y los encabezados de sección (claro y oscuro) con la paleta del banner.

Uso:  python scripts/projects/generate_projects.py [carpeta_salida]   (por defecto: dist/)
Datos: scripts/projects/projects.json + API de GitHub (fetch_data.py); paleta: scripts/shared/theme.json.
"""
import json
import math
import sys
from datetime import datetime, timezone
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


def relative(iso, now):
    """'hace 3 días', 'hace 2 semanas'…"""
    d = (now - datetime.fromisoformat(iso.replace('Z', '+00:00'))).days
    if d <= 0:
        return 'hoy'
    if d == 1:
        return 'ayer'
    for size, one, many in ((365, 'año', 'años'), (30, 'mes', 'meses'), (7, 'semana', 'semanas')):
        if d >= size:
            n = d // size
            return f'hace {n} {one if n == 1 else many}'
    return f'hace {d} días'


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


# ---------------------------------------------------------------- tarjeta de proyecto
def card(p, th, now):
    W, H = 1180, 330
    o = [svg_open(W, H, f'{p["name"]} — {p["subtitle"]}'), f'<title>{escape(p["name"])}</title>']
    a = o.append
    a(f'<defs>{border_defs(th)}<clipPath id="c"><rect x="2" y="2" width="{W - 4}" height="{H - 4}" rx="14"/></clipPath></defs>')
    a(f'<g clip-path="url(#c)"><rect width="{W}" height="{H}" fill="{th["bg"]}"/>'
      f'<rect width="{W}" height="38" fill="{th["titlebar"]}"/>'
      f'<line x1="0" y1="38.5" x2="{W}" y2="38.5" stroke="{th["divider"]}"/></g>')
    for i, c in enumerate(th['window_dots']):
        a(f'<circle cx="{26 + i * 20}" cy="19" r="5.5" fill="{c}"/>')
    a(f'<text x="{W / 2}" y="24" text-anchor="middle" font-size="12" fill="{th["title_text"]}">'
      f'{escape(p["path"])} — git log --oneline</text>')

    # PROJECT.INFO
    a(f'<text x="36" y="76" font-size="10" letter-spacing="3" fill="{th["muted"]}">PROJECT.INFO</text>')
    a(f'<text x="36" y="112" font-size="26" font-weight="700" fill="{th["values"]}">{escape(p["name"])}</text>')
    a(f'<text x="36" y="138" font-size="13" fill="{th["labels"]}">{escape(p["subtitle"])}</text>')
    for i, b in enumerate(p['bullets']):
        a(f'<g opacity="0"><animate attributeName="opacity" from="0" to="1" dur=".4s" begin="{f(.3 + i * .25, 2)}s" '
          f'fill="freeze"/><text x="36" y="{180 + i * 28}" font-size="15" fill="{th["values"]}">'
          f'<tspan fill="{th["accent"]}">▸ </tspan>{escape(b)}</text></g>')
    x = 36
    for t in p['chips']:
        w = len(t) * 7.8 + 24
        a(f'<rect x="{f(x)}" y="268" width="{f(w)}" height="26" rx="6" fill="{th["chip_bg"]}" stroke="{th["chip_stroke"]}" '
          f'stroke-opacity=".7"/><text x="{f(x + w / 2)}" y="285.5" text-anchor="middle" font-size="13" '
          f'fill="{th["labels"]}">{escape(t)}</text>')
        x += w + 10
    a(f'<text x="{f(x + 4)}" y="287" font-size="16" fill="{th["accent"]}">█<animate attributeName="fill-opacity" '
      f'values="1;1;0;0" keyTimes="0;.5;.5;1" dur="1s" repeatCount="indefinite"/></text>')

    # LANG.MAP
    X0 = 868
    a(f'<line x1="{X0 - 34}" y1="62" x2="{X0 - 34}" y2="{H - 28}" stroke="{th["divider"]}"/>')
    a(f'<text x="{X0}" y="76" font-size="10" letter-spacing="3" fill="{th["muted"]}">LANG.MAP</text>')
    cx, cy, r = X0 + 46, 148, 38
    C = 2 * math.pi * r
    a(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{th["chip_bg"]}" stroke-width="14"/>')
    split = lang_split(p['languages'])
    off = 0
    for i, (n, fr) in enumerate(split):
        c = th['series'][-1] if n == 'Otros' else th['series'][i]
        seg = C * fr
        gap = 2 if len(split) > 1 else 0
        a(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{c}" stroke-width="14" stroke-dasharray="0 {f(C)}" '
          f'stroke-dashoffset="{f(-off)}" transform="rotate(-90 {cx} {cy})"><animate attributeName="stroke-dasharray" '
          f'to="{f(max(seg - gap, .5))} {f(C - seg + gap)}" dur=".6s" begin="{f(.3 + i * .25, 2)}s" fill="freeze"/></circle>')
        off += seg
        ly = 124 + i * 22
        a(f'<rect x="{X0 + 104}" y="{ly - 10}" width="10" height="10" rx="2" fill="{c}"/>'
          f'<text x="{X0 + 122}" y="{ly}" font-size="13" fill="{th["values"]}">{escape(n)} '
          f'<tspan fill="{th["muted"]}">{fr * 100:.0f}%</tspan></text>')
    rows = p['rows'] + [['último push', relative(p['pushed_at'], now)]]
    for i, (k, v) in enumerate(rows):
        dots = '.' * max(1, 12 - len(k))
        vc = th['accent'] if k == 'estado' else th['values']
        a(f'<text x="{X0}" y="{238 + i * 24}" font-size="13" xml:space="preserve"><tspan fill="{th["labels"]}">{escape(k)}</tspan>'
          f'<tspan fill="{th["guide_dots"]}"> {dots} </tspan><tspan fill="{vc}">{escape(v)}</tspan></text>')

    a(f'<rect x="2.5" y="2.5" width="{W - 5}" height="{H - 5}" rx="14" fill="none" stroke="url(#bd)" stroke-width="3" '
      f'opacity=".45" filter="url(#gl)"/>')
    a(f'<rect x="2.5" y="2.5" width="{W - 5}" height="{H - 5}" rx="14" fill="none" stroke="url(#bd)" stroke-width="1.6"/>')
    a('</svg>')
    return '\n'.join(o)


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
    now = datetime.now(timezone.utc)
    projects = enrich(CFG['projects'])
    for name, th in THEME['themes'].items():
        for p in projects:
            (out / f'card-{p["slug"]}-{name}.svg').write_text(card(p, th, now), encoding='utf-8', newline='\n')
        for h in CFG['headers']:
            (out / f'header-{h["slug"]}-{name}.svg').write_text(header(h, th), encoding='utf-8', newline='\n')
    for fp in sorted(out.glob('*.svg')):
        print(f'{fp.name}: {fp.stat().st_size / 1024:.1f} KB')


if __name__ == '__main__':
    main()
