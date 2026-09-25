#!/usr/bin/env python3
"""Completa projects.json con datos en vivo de la API de GitHub (lenguajes y pushed_at).

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
    """Añade p['languages'] (bytes por lenguaje, sumando todos los repos) y p['pushed_at'] (el más reciente)."""
    for p in projects:
        try:
            langs, pushed = {}, []
            for repo in p['repos']:
                pushed.append(gh(f'https://api.github.com/repos/{repo}')['pushed_at'])
                for k, v in gh(f'https://api.github.com/repos/{repo}/languages').items():
                    langs[k] = langs.get(k, 0) + v
            p['languages'], p['pushed_at'], p['source'] = langs, max(pushed), 'api'
        except Exception as e:  # noqa: BLE001 — cualquier fallo de red o de API cae al config
            print(f'warn: {p["slug"]}: {e} — uso fallback del config', file=sys.stderr)
            p['languages'], p['pushed_at'], p['source'] = p['fallback']['languages'], p['fallback']['pushed_at'], 'fallback'
    return projects


if __name__ == '__main__':
    from pathlib import Path
    cfg = json.loads((Path(__file__).parent / 'projects.json').read_text(encoding='utf-8'))
    for p in enrich(cfg['projects']):
        print(p['slug'], p['source'], p['pushed_at'], p['languages'])
