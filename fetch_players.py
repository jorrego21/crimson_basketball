#!/usr/bin/env python3
"""
fetch_players.py — Build the PLAYERS JS array for any college basketball team.

Sources:
  - ESPN public API  : roster info (name, number, pos, class, height, hometown)
  - Sports-Reference : season stats + previous-year stats + game logs

Usage:
    python fetch_players.py --school harvard --year 2026 --gender womens
    python fetch_players.py --school yale    --year 2026 --gender mens

Output:
    players_<school>_<gender>_<year>.js  — paste PLAYERS = [...] into index.html

Requirements:
    pip install requests beautifulsoup4
"""

import argparse
import json
import re
import sys
import time
from difflib import SequenceMatcher

import requests
from bs4 import BeautifulSoup, Comment

# ── constants ─────────────────────────────────────────────────────────────────

IVY_SR_SLUGS = {
    'harvard', 'yale', 'princeton', 'pennsylvania',
    'columbia', 'brown', 'dartmouth', 'cornell',
}

ESPN_GENDER = {
    'mens':   'mens-college-basketball',
    'womens': 'womens-college-basketball',
}

SR_GENDER_PATH = {
    'mens':   '',        # /cbb/schools/harvard/2026.html
    'womens': '/women',  # /cbb/schools/harvard/women/2026.html
}

CLASS_MAP = {
    'freshman':  'FR',
    'sophomore': 'SO',
    'junior':    'JR',
    'senior':    'SR',
    'graduate':  'GR',
    '5th year':  'GR',
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

# ── helpers ───────────────────────────────────────────────────────────────────

def _sr_get(url, delay=3.0):
    """Fetch a Sports-Reference page with polite rate limiting."""
    time.sleep(delay)
    r = requests.get(url, headers=SR_HEADERS, timeout=20)
    if r.status_code == 429:
        print('    Rate-limited — waiting 30s...')
        time.sleep(30)
        r = requests.get(url, headers=SR_HEADERS, timeout=20)
    r.raise_for_status()
    return BeautifulSoup(r.text, 'html.parser')

def _find_table(soup, id_pattern):
    """Find a table by id pattern, unwrapping SR's HTML-comment-wrapped tables."""
    table = soup.find('table', id=re.compile(id_pattern, re.I))
    if table:
        return table
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        inner = BeautifulSoup(str(comment), 'html.parser')
        table = inner.find('table', id=re.compile(id_pattern, re.I))
        if table:
            return table
    return None

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
    """'5\' 11"'  →  '5-11'  (handles string, float inches, or None)"""
    if h is None:
        return ''
    if isinstance(h, (int, float)):
        feet, inches = divmod(int(h), 12)
        return f'{feet}-{inches}'
    m = re.match(r"(\d+)'?\s*(\d+)", str(h))
    return f"{m.group(1)}-{m.group(2)}" if m else str(h)

def _name_sim(a, b):
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()

# ── ESPN roster ───────────────────────────────────────────────────────────────

def get_espn_roster(school, gender):
    sport = ESPN_GENDER[gender]
    url = f'https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/teams/{school}/roster'
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    data = r.json()

    athletes = data.get('players', data.get('athletes', []))
    roster = []
    for p in athletes:
        exp = p.get('experience', {})
        bp  = p.get('birthPlace', {})
        roster.append({
            'name':      p['displayName'],
            'number':    p.get('jersey', ''),
            'pos':       p.get('position', {}).get('abbreviation', ''),
            'class':     exp.get('abbreviation', ''),
            'height':    _parse_height(p.get('displayHeight') or p.get('height')),
            'weight':    '',
            'hometown':  bp.get('displayText', ''),
            'hs':        '',
            'espn_id':   p['id'],
            'photo_url': p.get('headshot', {}).get('href', ''),
        })
    return roster

# ── Sports-Reference season stats ─────────────────────────────────────────────
# SR uses two separate tables on the school page:
#   players_per_game   — counting stats (direct HTML)
#   players_advanced   — TS%, USG%, BPM/OBPM/DBPM (wrapped in HTML comment)

def _parse_pg_row(row):
    """Parse a players_per_game row (counting stats only)."""
    ast = _float(_cell(row, 'ast_per_g'))
    tov = _float(_cell(row, 'tov_per_g'))
    return {
        'G':       _int(_cell(row, 'games')),
        'MP':      _float(_cell(row, 'mp_per_g')),
        'PTS':     _float(_cell(row, 'pts_per_g')),
        'TS':      0.0,   # filled from advanced table below
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
    """Parse a players_advanced row (TS%, USG%, BPM)."""
    return {
        'TS':   round(_float(_cell(row, 'ts_pct')), 3),
        'USG':  round(_float(_cell(row, 'usg_pct')), 1),
        'BPM':  _float(_cell(row, 'bpm')),
        'OBPM': _float(_cell(row, 'obpm')),
        'DBPM': _float(_cell(row, 'dbpm')),
    }

def _extract_player_rows(table):
    """Yield (name, sr_slug, row) for every player row in a stats table."""
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
        slug_m = re.search(r'/players/([^/]+)\.html', a['href'])
        sr_slug = slug_m.group(1) if slug_m else None
        yield name, sr_slug, row

def get_sr_season(school, gender, year):
    """Returns {player_name: {'sr_slug': str, 'season': dict}} for all players."""
    gpath = SR_GENDER_PATH[gender]
    url   = (
        f'https://www.sports-reference.com/cbb/schools/{school}{gpath}/{year}.html'
        if gpath else
        f'https://www.sports-reference.com/cbb/schools/{school}/{year}.html'
    )
    print(f'    SR: {url}')
    try:
        soup = _sr_get(url)
    except requests.HTTPError as e:
        print(f'    ERROR: {e}')
        return {}

    # Per-game table — direct in HTML
    pg_table = soup.find('table', id='players_per_game')
    if not pg_table:
        print('    WARNING: players_per_game not found')
        return {}

    result = {}
    for name, sr_slug, row in _extract_player_rows(pg_table):
        result[name] = {'sr_slug': sr_slug, 'season': _parse_pg_row(row)}

    # Advanced table — wrapped in HTML comment
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        inner = BeautifulSoup(str(comment), 'html.parser')
        adv_table = inner.find('table', id='players_advanced')
        if adv_table:
            for name, _, row in _extract_player_rows(adv_table):
                if name in result:
                    result[name]['season'].update(_parse_adv_row(row))
            break

    return result

# ── Sports-Reference game log ─────────────────────────────────────────────────

_SKIP_REASONS = {'did not play', 'inactive', 'did not dress', 'not with team', 'suspended'}

def get_sr_gamelog(sr_slug, year):
    url = f'https://www.sports-reference.com/cbb/players/{sr_slug}/gamelog/{year}/'
    print(f'      game log: {sr_slug}')
    try:
        soup = _sr_get(url)
    except requests.HTTPError as e:
        print(f'      ERROR: {e}')
        return []

    # Table id is 'player_game_log', found directly (not in comments)
    table = soup.find('table', id='player_game_log')
    if not table:
        table = _find_table(soup, r'player_game_log')
    if not table:
        print('      WARNING: game log table not found')
        return []

    games = []
    for row in table.find_all('tr'):
        if any(c in row.get('class', []) for c in ('thead', 'over_header')):
            continue

        g_td = row.find('td', {'data-stat': 'team_game_num_season'})
        if not g_td or not g_td.text.strip().isdigit():
            continue

        mp_val = _cell(row, 'mp').lower()
        if not mp_val or any(s in mp_val for s in _SKIP_REASONS):
            continue

        opp_td   = row.find('td', {'data-stat': 'opp_name_abbr'})
        opp_name = opp_td.text.strip() if opp_td else ''

        loc_raw    = _cell(row, 'game_location')
        result_raw = _cell(row, 'game_result')
        game_type  = _cell(row, 'game_type')

        games.append({
            'g':    _int(g_td.text.strip()),
            'opp':  opp_name,
            'date': _cell(row, 'date'),
            'conf': game_type == 'REG (Conf)',
            'loc':  'A' if loc_raw == '@' else ('N' if loc_raw == 'N' else 'H'),
            'win':  result_raw.startswith('W') if result_raw else False,
            'pts':  _int(_cell(row, 'pts')),
            'ast':  _float(_cell(row, 'ast')),
            'trb':  _float(_cell(row, 'trb')),
            'stl':  _float(_cell(row, 'stl')),
            'blk':  _float(_cell(row, 'blk')),
            'tov':  _float(_cell(row, 'tov')),
            'sc':   _float(_cell(row, 'game_score')),
        })
    return games

# ── name matching ─────────────────────────────────────────────────────────────

def match_rosters(espn_players, sr_stats):
    """Return {espn_name: sr_name} for best matches (similarity > 0.6)."""
    sr_names = list(sr_stats.keys())
    result = {}
    for ep in espn_players:
        if not sr_names:
            break
        best = max(sr_names, key=lambda n: _name_sim(ep['name'], n))
        sim  = _name_sim(ep['name'], best)
        if sim > 0.6:
            result[ep['name']] = best
        else:
            print(f'    UNMATCHED: "{ep["name"]}" (best SR match: "{best}", sim={sim:.2f})')
    return result

# ── photo path helper ─────────────────────────────────────────────────────────

def _photo_path(name, folder):
    last = name.split()[-1]
    return f'{folder}/{last}.webp'

# ── main pipeline ─────────────────────────────────────────────────────────────

def build_players(school, year, gender, photo_folder):
    print(f'\n{"="*60}')
    print(f'  {school.upper()} | {gender} | {year}')
    print(f'{"="*60}')

    print('\n[1/4] ESPN roster...')
    espn = get_espn_roster(school, gender)
    print(f'  {len(espn)} players found')

    print('\n[2/4] Sports-Reference season stats...')
    sr_cur  = get_sr_season(school, gender, year)
    sr_prev = get_sr_season(school, gender, year - 1)
    print(f'  Current ({year}): {len(sr_cur)} | Previous ({year-1}): {len(sr_prev)}')

    print('\n[3/4] Matching names...')
    match_cur  = match_rosters(espn, sr_cur)
    match_prev = match_rosters(espn, sr_prev) if sr_prev else {}

    print('\n[4/4] Game logs...')
    players = []
    for ep in espn:
        name         = ep['name']
        sr_name_cur  = match_cur.get(name)
        sr_name_prev = match_prev.get(name)
        entry_cur    = sr_cur.get(sr_name_cur)  if sr_name_cur  else None
        entry_prev   = sr_prev.get(sr_name_prev) if sr_name_prev else None

        if not entry_cur:
            print(f'  SKIP {name} — no current-year SR stats')
            continue

        sr_slug  = entry_cur['sr_slug']
        gamelog  = get_sr_gamelog(sr_slug, year) if sr_slug else []

        players.append({
            'info': {
                'name':     name,
                'number':   ep['number'],
                'class':    ep['class'],
                'pos':      ep['pos'],
                'height':   ep['height'],
                'weight':   ep['weight'],
                'hometown': ep['hometown'],
                'hs':       ep['hs'],
                'photo':    _photo_path(name, photo_folder),
            },
            's26':  entry_cur['season'],
            's25':  entry_prev['season'] if entry_prev else None,
            'games': gamelog,
        })
        print(f'  ✓ {name} — {len(gamelog)} games')

    return players


def main():
    p = argparse.ArgumentParser(description='Build PLAYERS array for a CBB team.')
    p.add_argument('--school',  required=True,
                   help='Sports-Reference school slug (e.g. harvard, yale)')
    p.add_argument('--year',    type=int, required=True,
                   help='Season end year (e.g. 2026)')
    p.add_argument('--gender',  choices=['mens', 'womens'], default='mens')
    p.add_argument('--photos',  default=None,
                   help='Photo folder path in output JS (default: Pictures_<gender>)')
    args = p.parse_args()

    photo_folder = args.photos or f'Pictures_{args.gender}'
    players      = build_players(args.school, args.year, args.gender, photo_folder)

    players.sort(key=lambda p: p['s26']['MP'], reverse=True)

    out = f'players_{args.school}_{args.gender}_{args.year}.js'
    with open(out, 'w') as f:
        f.write('const PLAYERS = ' + json.dumps(players, indent=2) + ';\n')

    print(f'\n{"="*60}')
    print(f'  Done — {len(players)} players → {out}')
    print(f'  Next: run fetch_photos.py, then paste PLAYERS into index.html')
    print(f'{"="*60}\n')


if __name__ == '__main__':
    main()
