#!/usr/bin/env python3
"""
fetch_ivy.py — Build the IVY_LEAGUE JS object for all non-Harvard Ivy schools.

Pulls season stats only (no game logs, no prior-year data) — just enough for
Season Snapshot and Roster Comparison overlays in the analytics tool.

Sources:
  - ESPN public API  : roster metadata (name, number, pos, class, height)
  - Sports-Reference : per-game + advanced season stats

Usage:
    python fetch_ivy.py --year 2026 --gender mens
    python fetch_ivy.py --year 2026 --gender womens

Output:
    ivy_league_<gender>_<year>.js  — const IVY_LEAGUE = { yale: [...], ... };
"""

import argparse
import json
import re
import time
from difflib import SequenceMatcher

import requests
from bs4 import BeautifulSoup, Comment

# ── constants ──────────────────────────────────────────────────────────────────

IVY_SCHOOLS = ['yale', 'princeton', 'pennsylvania', 'columbia', 'brown', 'dartmouth', 'cornell']

ESPN_SLUG_OVERRIDE = {
    'pennsylvania': 'penn',
}

IVY_DISPLAY = {
    'yale':         'Yale',
    'princeton':    'Princeton',
    'pennsylvania': 'Penn',
    'columbia':     'Columbia',
    'brown':        'Brown',
    'dartmouth':    'Dartmouth',
    'cornell':      'Cornell',
}

ESPN_GENDER = {
    'mens':   'mens-college-basketball',
    'womens': 'womens-college-basketball',
}

SR_GENDER_PATH = {
    'mens':   '',
    'womens': '/women',
}

SR_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.sports-reference.com/',
}

# ── helpers ────────────────────────────────────────────────────────────────────

def _sr_get(url, delay=3.0):
    time.sleep(delay)
    r = requests.get(url, headers=SR_HEADERS, timeout=20)
    if r.status_code == 429:
        print('    Rate-limited — waiting 30s...')
        time.sleep(30)
        r = requests.get(url, headers=SR_HEADERS, timeout=20)
    r.raise_for_status()
    return BeautifulSoup(r.text, 'html.parser')

def _cell(row, stat):
    td = row.find('td', {'data-stat': stat})
    return td.text.strip() if td else ''

def _float(val, default=0.0):
    try:
        return float(val) if val and val not in ('', '-') else default
    except (ValueError, TypeError):
        return default

def _int(val, default=0):
    try:
        return int(val) if val and val not in ('', '-') else default
    except (ValueError, TypeError):
        return default

def _parse_height(h):
    if h is None:
        return ''
    if isinstance(h, (int, float)):
        feet, inches = divmod(int(h), 12)
        return f'{feet}-{inches}'
    m = re.match(r"(\d+)'?\s*(\d+)", str(h))
    return f"{m.group(1)}-{m.group(2)}" if m else str(h)

def _sim(a, b):
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()

# ── ESPN roster ────────────────────────────────────────────────────────────────

def get_espn_roster(school, gender):
    sport = ESPN_GENDER[gender]
    espn_slug = ESPN_SLUG_OVERRIDE.get(school, school)
    url = f'https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/teams/{espn_slug}/roster'
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f'    ESPN ERROR: {e}')
        return []

    athletes = data.get('players', data.get('athletes', []))
    roster = []
    for p in athletes:
        exp = p.get('experience', {})
        bp  = p.get('birthPlace', {})
        roster.append({
            'name':   p['displayName'],
            'number': p.get('jersey', ''),
            'pos':    p.get('position', {}).get('abbreviation', ''),
            'class':  exp.get('abbreviation', ''),
            'height': _parse_height(p.get('displayHeight') or p.get('height')),
        })
    return roster

# ── Sports-Reference season stats ─────────────────────────────────────────────

def _extract_player_rows(table):
    for row in table.find_all('tr'):
        if any(c in row.get('class', []) for c in ('thead', 'over_header')):
            continue
        nd = row.find('td', {'data-stat': 'name_display'})
        if not nd:
            continue
        a = nd.find('a')
        if not a:
            continue
        name = a.text.strip()
        yield name, row

def _parse_pg_row(row):
    ast = _float(_cell(row, 'ast_per_g'))
    tov = _float(_cell(row, 'tov_per_g'))
    return {
        'G':       _int(_cell(row, 'games')),
        'MP':      _float(_cell(row, 'mp_per_g')),
        'PTS':     _float(_cell(row, 'pts_per_g')),
        'TS':      0.0,
        'USG':     0.0,
        'AST':     ast,
        'TOV':     tov,
        'AST_TOV': round(ast / tov, 2) if tov > 0 else 0.0,
        'TRB':     _float(_cell(row, 'trb_per_g')),
        'ORB':     _float(_cell(row, 'orb_per_g')),
        'DRB':     _float(_cell(row, 'drb_per_g')),
        'STL':     _float(_cell(row, 'stl_per_g')),
        'BLK':     _float(_cell(row, 'blk_per_g')),
        'PF':      _float(_cell(row, 'pf_per_g')),
        'BPM':     0.0,
        'OBPM':    0.0,
        'DBPM':    0.0,
    }

def _parse_adv_row(row):
    return {
        'TS':   round(_float(_cell(row, 'ts_pct')), 3),
        'USG':  round(_float(_cell(row, 'usg_pct')), 1),
        'BPM':  _float(_cell(row, 'bpm')),
        'OBPM': _float(_cell(row, 'obpm')),
        'DBPM': _float(_cell(row, 'dbpm')),
    }

def get_sr_season(school, gender, year):
    gpath = SR_GENDER_PATH[gender]
    url = (
        f'https://www.sports-reference.com/cbb/schools/{school}{gpath}/{year}.html'
        if gpath else
        f'https://www.sports-reference.com/cbb/schools/{school}/{year}.html'
    )
    print(f'    SR: {url}')
    try:
        soup = _sr_get(url)
    except Exception as e:
        print(f'    ERROR: {e}')
        return {}

    pg_table = soup.find('table', id='players_per_game')
    if not pg_table:
        print('    WARNING: players_per_game not found')
        return {}

    result = {}
    for name, row in _extract_player_rows(pg_table):
        result[name] = _parse_pg_row(row)

    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        inner = BeautifulSoup(str(comment), 'html.parser')
        adv_table = inner.find('table', id='players_advanced')
        if adv_table:
            for name, row in _extract_player_rows(adv_table):
                if name in result:
                    result[name].update(_parse_adv_row(row))
            break

    return result

# ── name matching ──────────────────────────────────────────────────────────────

def match_rosters(espn_players, sr_stats):
    sr_names = list(sr_stats.keys())
    result = {}
    for ep in espn_players:
        if not sr_names:
            break
        best = max(sr_names, key=lambda n: _sim(ep['name'], n))
        if _sim(ep['name'], best) > 0.6:
            result[ep['name']] = best
        else:
            print(f'    UNMATCHED: "{ep["name"]}" (best: "{best}")')
    return result

# ── per-school builder ─────────────────────────────────────────────────────────

def build_school(school, year, gender):
    print(f'\n{"="*60}')
    print(f'  {IVY_DISPLAY[school].upper()} | {gender} | {year}')
    print(f'{"="*60}')

    print('  [1/2] ESPN roster...')
    espn = get_espn_roster(school, gender)
    print(f'    {len(espn)} players')

    print('  [2/2] SR season stats...')
    sr = get_sr_season(school, gender, year)
    print(f'    {len(sr)} players')

    matches = match_rosters(espn, sr)

    players = []
    for ep in espn:
        sr_name = matches.get(ep['name'])
        if not sr_name:
            continue
        stats = sr[sr_name]
        if stats['G'] < 8 or stats['MP'] < 8.0:
            continue
        players.append({
            'info': {
                'name':   ep['name'],
                'number': ep['number'],
                'pos':    ep['pos'],
                'class':  ep['class'],
                'height': ep['height'],
                'school': IVY_DISPLAY[school],
            },
            's26': stats,
        })

    players.sort(key=lambda p: p['s26']['MP'], reverse=True)
    print(f'    → {len(players)} players ready')
    return players

# ── main ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description='Fetch Ivy League season stats for comparison overlay.')
    ap.add_argument('--year',   type=int, required=True, help='Season end year (e.g. 2026)')
    ap.add_argument('--gender', choices=['mens', 'womens'], default='mens')
    ap.add_argument('--schools', nargs='+', default=IVY_SCHOOLS,
                    help='Subset of schools to run (default: all 7 non-Harvard)')
    args = ap.parse_args()

    out = f'ivy_league_{args.gender}_{args.year}.js'

    # Load existing data so partial runs merge rather than overwrite
    existing = {}
    try:
        with open(out) as f:
            content = f.read().replace('const IVY_LEAGUE = ', '').rstrip(';\n')
        existing = json.loads(content)
        print(f'\nMerging into existing {out} ({list(existing.keys())})')
    except FileNotFoundError:
        pass

    for school in args.schools:
        existing[school] = build_school(school, args.year, args.gender)

    with open(out, 'w') as f:
        f.write('const IVY_LEAGUE = ' + json.dumps(existing, indent=2) + ';\n')

    total = sum(len(v) for v in existing.values())
    print(f'\n{"="*60}')
    print(f'  Done — {total} players across {len(existing)} schools → {out}')
    print(f'{"="*60}\n')


if __name__ == '__main__':
    main()
