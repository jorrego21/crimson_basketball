# Harvard Crimson Basketball Analytics Tool

## Purpose
A single-page web app built to impress Harvard Men's Basketball Assistant Coach Mike and re-open a conversation about a volunteer analytics role. The tool profiles every player on the 2025–26 roster with stats, roster comparisons, season arcs, and year-over-year growth. The target audience is **coaching staff — not stats people**. Everything must be self-explanatory, warm, and polished.

## File structure
```
/HMB
├── index.html              ← men's tool (single file, no build step)
├── index_womens.html       ← women's tool (same structure, gender-adapted)
├── Pictures_improved/      ← men's player photos (webp)
├── Pictures_womens/        ← women's player photos (webp)
├── fetch_players.py        ← pipeline: ESPN + SR → PLAYERS JS array
├── fetch_photos.py         ← pipeline: ESPN CDN → webp photo folder
├── requirements.txt        ← pip dependencies (requests, beautifulsoup4, Pillow)
└── CLAUDE.md
```

## Tech stack
- Vanilla HTML/CSS/JS — no framework, no build step
- Chart.js 4.4.0 (CDN)
- All player data embedded in `PLAYERS` array in the script

## Color system
```
--cr:    #A41034   Harvard Crimson (primary accent)
--crL:   rgba(164,16,52,0.08)
--dark:  #1A1A1A   (header background)
--bg:    #F2EFEC   (warm off-white page background)
--white: #fff
--gL:    #E8E2DC   (light gray border)
--gM:    #9B9490   (medium gray)
--text:  #1A1A1A
--soft:  #5A5550   (secondary text)
```

## App structure (two pages, single HTML)

### Page 1 — Roster (`#pg1`)
- Header with site title
- Welcome intro (2 sentences + Sports Reference attribution)
- 6-column player card grid — photo (2:3 aspect ratio, `object-position: top center`), name, pos/class/size, G/MPG/PPG
- Bench players (`s26.MP < 15`) get `.pcard.bench` class (opacity 0.72, muted colors)
- Bench explanation text visible on the page so coaches understand the differentiation
- **Team summary strip** (`#team-summary`) — "Season at a glance" headline + 6 chips: Overall W-L, Ivy W-L, Leading Scorer (PPG), Leading Assists (APG), Leading Rebounder (RPG), Leading Steals (SPG)
- Footer: "Built by Juan Carlos Orrego · Harvard Kennedy School · Stats: Sports Reference CBB"

### Page 2 — Player detail (`#pg2`)
- Dark header with ← Roster button, **player name dropdown** (jump between players), **Compare dropdown** (`#comp-select`) to select a second player for overlay, share button
- **Season Snapshot panel** — 5 metric buckets (Shooting, Playmaking, Rebounds, Defense, Impact), each with a primary metric and two secondary. Clicking any stat triggers the Roster Comparison panel. When a comparison player is selected, each metric cell also shows that player's value in blue below the primary value.
- **Roster Comparison panel** — placeholder until a stat is clicked. Bar charts for single-stat rankings (rank #X of 16). Scatter plots for bivariate comparisons with quadrant/diagonal reference lines.
- **Season Arc panel** — Game Score scatter + linear trend line + 4-chip meta (Season High, Season Low, Ivy League Avg, Non-Conf Avg). Critical zone shading: red band below 0, dashed green lines at 10 and 20. Ivy League start marked with crimson dashed vertical. Win = solid dot, Loss = hollow dot. Darker = Ivy League game. Tooltip: game #, H/A/N, conf/non-conf, opponent, date, W/L, pts/ast/reb. When a comparison player is selected, their arc overlays in blue. Collapsible **game log matrix** below the chart (stats as rows, games as columns — horizontally scrollable, stat labels sticky-left).
- **Year-over-Year panel** — 3-column grid (6 cards: USG, TS%, TRB, AST/TOV, OBPM, DBPM). Each card: metric name → question → big colored delta (▲/▼/→) → from/to values with season labels → **improvement rank** among returners with prior-year data.

## Data structure per player
```js
{
  info: { name, number, class, pos, height, weight, hometown, hs, photo },
  s26:  { G, MP, PTS, TS, USG, AST, TOV, AST_TOV, TRB, ORB, DRB, STL, BLK, PF, BPM, OBPM, DBPM },
  s25:  { same keys } | null,   // null for freshmen / no prior-year data
  games: [{ g, opp, date, conf, loc, win, pts, ast, trb, stl, blk, tov, sc }]
}
```
- `conf`: `true` when `game_type == 'REG (Conf)'` on Sports-Reference (exact match — excludes Non-Conf and tournament)
- `loc`: `'H'` | `'A'` | `'N'`
- `win`: boolean
- `sc`: Game Score (float)

## Key globals
```js
let CUR  = null;   // current player object
let COMP = null;   // comparison player object (null when no comparison active)
let compChart = null;
let arcChart  = null;
let activeChartKey = null;
const FIRST_IVY = Math.min(...);  // first Ivy League game number across all players
const WITH_PREV = PLAYERS.filter(p => p.s25);  // players with prior-year data
```

## TIPS object structure (plain/short/tech)
```js
TIPS[key] = {
  short: '2–4 word inline description shown below metric value',
  plain: 'Full plain-English interpretation (shown in the i tooltip — NO jargon)',
  tech:  'Formula / methodology (shown in the i tooltip)'
}
```
Keys: `TS`, `USG`, `AST_TOV`, `BPM`, `OBPM`, `DBPM`, `GS`

## Scripting approach for large edits
All major JS rewrites are done via **Python string-replacement scripts**, not the Edit tool — the PLAYERS JSON blob is too large for safe inline editing. Pattern:
```python
assert 'exact old string' in html   # fail fast before any write
html = html.replace(old, new, 1)
with open('index.html', 'w') as f: f.write(html)
```
Always `grep -n` for exact comment strings before using them as anchors — dash counts in section comments vary.

## Design principles (enforce strictly)
- **Coaching staff audience** — no unexplained jargon, ever. Labels and inline descs do the explaining, not hidden tooltips.
- **Warm tone** — language should feel like an invitation, not a dashboard.
- **Harvard Crimson palette** — use `--cr` sparingly as accent; don't over-crimson.
- **No comments in code** unless the WHY is non-obvious.
- **No new features beyond what's asked** — keep it focused.

---

## Scaling pipeline

The men's data was collected manually. Going forward, two scripts automate the full process for any team.

### Data sources
| Source | What it provides |
|--------|-----------------|
| **ESPN public API** | Roster info: name, number, position, class year, height, hometown, headshot URL |
| **Sports-Reference CBB** | Season stats (counting + advanced: TS%, USG%, BPM/OBPM/DBPM) and per-game game logs |

ESPN gives clean roster metadata; SR has the advanced stats. Neither alone is complete.

### Step 1 — Download photos
```bash
python3 fetch_photos.py --school harvard --gender womens --output Pictures_womens
# or
python3 fetch_photos.py --school yale --gender mens --output Pictures_yale
```
- Hits the ESPN roster API, downloads each headshot from ESPN's CDN as a `.png`
- Composites over white background (ESPN PNGs are RGBA — transparent areas go black without this step)
- Saves as `<LastName>.webp` in the output folder
- Takes ~10 seconds for a full roster

### Step 2 — Fetch player data
```bash
python3 fetch_players.py --school harvard --year 2026 --gender womens
# optional: --photos Pictures_womens  (sets the photo folder path in the output JS)
```
- Pulls roster from ESPN API (name, position, class, height, hometown)
- Scrapes `players_per_game` table (direct HTML) from SR for counting stats
- Scrapes `players_advanced` table (HTML comment-wrapped) from SR for TS%, USG%, BPM
- Fetches each player's `player_game_log` table from SR for the full game log
- Runs previous-year SR page to populate `s25` (freshmen get `null`)
- Uses 3-second delays between SR requests to stay polite
- Outputs `players_<school>_<gender>_<year>.js`

### Step 3 — Build the HTML
Use the Python string-replacement pattern to drop the PLAYERS array into a copy of the HTML:
```python
import json, re

with open('index.html') as f: html = f.read()
with open('players_yale_mens_2026.js') as f: players_js = f.read().strip()

m = re.search(r'const PLAYERS = \[.*?\];', html, re.DOTALL)
html = html.replace(m.group(), players_js, 1)

with open('index_yale.html', 'w') as f: f.write(html)
```
Then do text replacements for team name, school, gender pronouns, etc. as needed.

### Ivy League school slugs
All 8 schools use the same slug on both ESPN and Sports-Reference:

| School | Slug |
|--------|------|
| Harvard | `harvard` |
| Yale | `yale` |
| Princeton | `princeton` |
| Penn | `pennsylvania` |
| Columbia | `columbia` |
| Brown | `brown` |
| Dartmouth | `dartmouth` |
| Cornell | `cornell` |

### SR page structure (as of 2025–26)
- Season stats: `sports-reference.com/cbb/schools/<slug>/[women/]<year>.html`
  - `players_per_game` table (direct HTML) — counting stats, columns use `name_display`, `games`, `mp_per_g`, `pts_per_g`, etc.
  - `players_advanced` table (HTML comment-wrapped) — `ts_pct`, `usg_pct`, `obpm`, `dbpm`, `bpm`
- Game logs: `sports-reference.com/cbb/players/<player-slug>/gamelog/<year>/`
  - Table id: `player_game_log`
  - Key columns: `team_game_num_season`, `opp_name_abbr`, `game_type`, `game_location`, `game_result`, `game_score`
  - Conference detection: `game_type == 'REG (Conf)'`

### Known limitations
- `weight` and `hs` fields are empty — ESPN doesn't expose them; SR player bio pages would require one extra request per player
- SR occasionally returns 429 (rate limit); the script auto-waits 30s and retries once
- ESPN headshots sometimes show a silhouette placeholder for walk-ons or late additions; the script skips those (size check)

---

## Pending / known gaps
1. **Home/Away/Neutral on roster card** — user mentioned encoding H/A/N "perhaps only in the card" (Page 1 player cards). Not yet implemented. `loc` field already exists in game data.
2. **Mobile responsiveness** — not implemented. Desktop-only by design.

## Data source
[Sports Reference CBB](https://www.sports-reference.com/cbb/) — attributed in welcome panel and footer.

## Context
Juan Carlos Orrego is a research and teaching fellow at Harvard Kennedy School. He reached out to Harvard MBB Assistant Coach Mike volunteering his time, met with him in person, and built this tool as a follow-up to demonstrate his analytics capabilities and re-open the conversation about a volunteer role.
