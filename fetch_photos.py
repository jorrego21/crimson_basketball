#!/usr/bin/env python3
"""
fetch_photos.py — Download player headshots from ESPN CDN and save as webp.

Usage:
    python fetch_photos.py --school harvard --gender womens
    python fetch_photos.py --school yale    --gender mens --output Pictures_yale/

Output:
    <output>/<LastName>.webp  for each player with a photo

Requirements:
    pip install requests pillow
"""

import argparse
import sys
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image

ESPN_GENDER = {
    'mens':   'mens-college-basketball',
    'womens': 'womens-college-basketball',
}

ESPN_SILHOUETTE_SIZE = (60, 60)   # ESPN placeholder is tiny — skip it


def get_espn_roster(school, gender):
    sport = ESPN_GENDER[gender]
    url   = f'https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/teams/{school}/roster'
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    data     = r.json()
    athletes = data.get('players', data.get('athletes', []))

    players = []
    for p in athletes:
        photo_url = p.get('headshot', {}).get('href', '')
        if photo_url:
            players.append({
                'name':      p['displayName'],
                'last_name': p['displayName'].split()[-1],
                'photo_url': photo_url,
            })
    return players


def download_photos(players, output_dir):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    ok, skipped, failed = 0, 0, 0

    for p in players:
        dest = out / f"{p['last_name']}.webp"
        print(f"  {p['name']:<28} → {dest.name}", end='  ')

        try:
            r = requests.get(p['photo_url'], timeout=15)
            r.raise_for_status()
            raw = Image.open(BytesIO(r.content))

            if raw.size <= ESPN_SILHOUETTE_SIZE:
                print('SKIP (placeholder silhouette)')
                skipped += 1
                continue

            # Composite RGBA over white so transparent areas don't go black
            if raw.mode == 'RGBA':
                bg = Image.new('RGB', raw.size, (255, 255, 255))
                bg.paste(raw, mask=raw.split()[3])
                img = bg
            else:
                img = raw.convert('RGB')

            img.save(dest, 'WEBP', quality=85)
            print(f'✓  {img.width}×{img.height}')
            ok += 1

        except Exception as e:
            print(f'FAILED — {e}')
            failed += 1

    print(f'\n  {ok} saved  |  {skipped} skipped (silhouette)  |  {failed} failed')
    print(f'  Folder: {out.resolve()}')


def main():
    p = argparse.ArgumentParser(description='Download ESPN headshots as webp.')
    p.add_argument('--school',  required=True,
                   help='ESPN school slug (e.g. harvard, yale, princeton)')
    p.add_argument('--gender',  choices=['mens', 'womens'], default='mens')
    p.add_argument('--output',  default=None,
                   help='Output folder (default: Pictures_<gender>)')
    args = p.parse_args()

    output = args.output or f'Pictures_{args.gender}'

    print(f'\nFetching {args.school} {args.gender} roster from ESPN...')
    try:
        players = get_espn_roster(args.school, args.gender)
    except requests.HTTPError as e:
        print(f'ERROR: Could not fetch ESPN roster — {e}')
        print('Check that --school matches ESPN\'s slug (e.g. "pennsylvania" not "penn")')
        sys.exit(1)

    print(f'Found {len(players)} players with headshot URLs\n')
    print(f'Downloading to {output}/...')
    download_photos(players, output)


if __name__ == '__main__':
    main()
