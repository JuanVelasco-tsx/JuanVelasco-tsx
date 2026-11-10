#!/usr/bin/env python3
"""Completa projects.json con los lenguajes en vivo de la API de GitHub.

Usa GITHUB_TOKEN si existe. Si la API falla para un proyecto, se usan los valores de "fallback" del config.
"""
import json
import os
import sys
import urllib.request

TOKEN = os.environ.get('GITHUB_TOKEN', '')


def gh(url):
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'projects-cards'}
    if TOKEN:
        headers['Authorization'] = f'Bearer {TOKEN}'
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=15) as r:
        return json.load(r)


def enrich(projects):
    """Añade p['languages'] (bytes por lenguaje, sumando todos los repos)."""
    for p in projects:
        if not p.get('show_languages', True):  # tarjeta sin gráfico de lenguajes: no se consulta nada
            continue
        if p.get('private'):  # repo privado: sin API, solo los lenguajes del config
            p['languages'], p['source'] = p['fallback']['languages'], 'private'
            continue
        try:
            langs = {}
            for repo in p['repos']:
                for k, v in gh(f'https://api.github.com/repos/{repo}/languages').items():
                    langs[k] = langs.get(k, 0) + v
            p['languages'], p['source'] = langs, 'api'
        except Exception as e:  # noqa: BLE001 — cualquier fallo de red o de API cae al config
            print(f'warn: {p["slug"]}: {e} — uso fallback del config', file=sys.stderr)
            p['languages'], p['source'] = p['fallback']['languages'], 'fallback'
    return projects


if __name__ == '__main__':
    from pathlib import Path
    cfg = json.loads((Path(__file__).parent / 'projects.json').read_text(encoding='utf-8'))
    for p in enrich(cfg['projects']):
        print(p['slug'], p.get('source', '-'), p.get('languages', {}))
