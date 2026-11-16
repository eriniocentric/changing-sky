"""Collect every (non-Solar-System) alerted object of one Rubin night from the Fink LSST REST API.

Method: Fink has no "all alerts of a night" route, and cone searches wider than about 2 deg time out.
So the sky is cut into ~1.4-deg cells; each cell is fetched with a 1.05-deg cone restricted to the night
(kind=across). The night's footprint is not known in advance, so the search starts from seed cells
(positions of tagged alerts, plus optional extra seeds) and flood-fills: every cell that returns alerts
has its 8 neighbours queued. Coverage is then checked against Fink's own nightly object count.

Usage: python fink_night.py 20261115 [outdir]
"""
import sys, io, json, math, time, datetime as dt, collections, concurrent.futures as cf
import requests, numpy as np, pandas as pd

B = 'https://api.lsst.fink-portal.org/api/v1'
CELL = 1.4            # deg
RADIUS = 3780         # arcsec = 1.05 deg, covers a cell's half-diagonal (0.99 deg) with margin
SEED_TAGS = ['most_likely_sn', 'in_tns', 'extragalactic_new_candidate', 'extragalactic_lt20mag_candidate',
             'sn_near_galaxy_candidate', 'hostless_candidate', 'faint_trails']
COLS = ("r:diaObjectId,r:diaSourceId,r:midpointMjdTai,r:ra,r:dec,r:band,r:psfFlux,r:psfFluxErr,r:snr,r:reliability,"
        "r:isDipole,r:glint_trail,r:pixelFlags_saturatedCenter,r:trailLength,r:ssObjectId,f:xm_simbad_otype,f:xm_vsx_Type,"
        "f:xm_gaiadr3_VarFlag,f:xm_tns_fullname,f:xm_tns_type,f:xm_x4lac_type,f:xm_x3hsp_type,f:clf_cats_class,"
        "f:clf_cats_score,f:xm_legacydr8_pstar,f:xm_mangrove_HyperLEDA_name,f:firstDiaSourceMjdTaiFink")
# f:firstDiaSourceMjdTaiFink must be among the columns or the date filter is silently ignored.

def night_window(night):
    """Fink night YYYYMMDD = UTC date of the morning. Window 18:00 UTC the day before to 14:00 UTC."""
    d = dt.datetime.strptime(str(night), '%Y%m%d')
    s, e = d - dt.timedelta(hours=6), d + dt.timedelta(hours=14)
    mjd = lambda x: (x - dt.datetime(1858, 11, 17)).total_seconds() / 86400
    return s.strftime('%Y-%m-%d %H:%M:%S'), e.strftime('%Y-%m-%d %H:%M:%S'), mjd(s), mjd(e)

def _post(ep, payload, timeout=300, tries=4):
    err = None
    for k in range(tries):
        try:
            r = requests.post(f'{B}/{ep}', json=payload, timeout=timeout)
            if r.status_code == 200:
                return r
            err = f'{r.status_code} {r.text[:120]}'
        except Exception as ex:
            err = repr(ex)[:120]
        time.sleep(4 * (k + 1))
    raise RuntimeError(err)

# ---- sky grid -------------------------------------------------------------
NBAND = int(round(180 / CELL))
def band_n(j):
    dec = -90 + (j + 0.5) * 180 / NBAND
    return max(1, int(math.ceil(360 * math.cos(math.radians(dec)) / CELL)))
def cell_of(ra, dec):
    j = min(NBAND - 1, max(0, int((dec + 90) / (180 / NBAND))))
    n = band_n(j)
    return j, int((ra % 360) / (360 / n)) % n
def cell_centre(c):
    j, i = c; n = band_n(j)
    return (i + 0.5) * 360 / n, -90 + (j + 0.5) * 180 / NBAND
def neighbours(c):
    j, i = c; n = band_n(j); ra, _ = cell_centre(c); out = {(j, (i - 1) % n), (j, (i + 1) % n)}
    for jj in (j - 1, j + 1):
        if 0 <= jj < NBAND:
            nn = band_n(jj); k = int((ra % 360) / (360 / nn))
            out |= {(jj, (k + d) % nn) for d in (-1, 0, 1)}
    out.discard(c)
    return out

def fetch_cell(c, S, E):
    ra, dec = cell_centre(c)
    r = _post('conesearch', {'ra': ra, 'dec': dec, 'radius': RADIUS, 'startdate': S, 'stopdate': E, 'kind': 'across',
                             'n': 100, 'columns': COLS, 'output-format': 'parquet'})
    d = pd.read_parquet(io.BytesIO(r.content))
    return d

def seed_positions(S, E):
    pos = []
    for tag in SEED_TAGS:
        try:
            r = _post('tags', {'tag': tag, 'n': 5000, 'startdate': S, 'stopdate': E, 'columns': 'r:ra,r:dec', 'output-format': 'json'}, tries=2)
            js = r.json()
            if isinstance(js, list):
                pos += [(x['r:ra'], x['r:dec']) for x in js if 'r:ra' in x]
        except Exception as ex:
            print('seed tag', tag, 'failed:', ex, flush=True)
    return pos

def collect_night(night, extra_seeds=(), workers=2, log=print, max_cells=6000, expand_any=False):
    S, E, m0, m1 = night_window(night)
    seeds = seed_positions(S, E) + list(extra_seeds)
    queue = collections.deque(sorted({cell_of(a, b) for a, b in seeds}))
    seen = set(queue); frames = []; failed = []; nhit = nq = 0; t0 = time.time()
    log(f'{night}: window {S} to {E} UTC, {len(seeds)} seed positions in {len(queue)} cells')
    with cf.ThreadPoolExecutor(workers) as ex:
        pending = {}
        while queue or pending:
            while queue and len(pending) < workers and nq < max_cells:
                c = queue.popleft(); pending[ex.submit(fetch_cell, c, S, E)] = c; nq += 1
            if not pending: break
            done, _ = cf.wait(pending, return_when=cf.FIRST_COMPLETED)
            for f in done:
                c = pending.pop(f)
                try: d = f.result()
                except Exception as e2:
                    failed.append(c); log(f'  cell {c} failed: {e2}'); continue
                if len(d):
                    d = d.assign(in_night=(d['r:midpointMjdTai'] >= m0) & (d['r:midpointMjdTai'] <= m1))
                    frames.append(d)
                    if d['in_night'].any() or expand_any:
                        nhit += 1
                        for nb in neighbours(c):
                            if nb not in seen: seen.add(nb); queue.append(nb)
            if nq % 25 == 0:
                log(f'  {nq} cells queried, {nhit} with alerts, {sum(map(len, frames))} rows, {time.time()-t0:.0f}s')
    # one retry pass, sequential, for failed cells (their neighbours are not expanded)
    still = []
    for c in failed:
        try:
            d = fetch_cell(c, S, E)
            if len(d): frames.append(d.assign(in_night=(d['r:midpointMjdTai'] >= m0) & (d['r:midpointMjdTai'] <= m1)))
        except Exception: still.append(c)
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if len(df):
        df = df.sort_values('r:midpointMjdTai').drop_duplicates('r:diaObjectId', keep='last').reset_index(drop=True)
    stats = dict(night=str(night), cells_queried=nq, cells_with_alerts=nhit, cells_failed=len(still), objects=int(df['in_night'].sum()) if len(df) else 0,
                 objects_with_later_alert=int((~df['in_night']).sum()) if len(df) else 0,
                 seconds=round(time.time() - t0), truncated=bool(queue))
    return df, stats

def fink_night_stats(night):
    r = _post('statistics', {'date': str(night), 'output-format': 'json'}, tries=2).json()
    return r[0] if r else {}

if __name__ == '__main__':
    night = sys.argv[1]; out = sys.argv[2] if len(sys.argv) > 2 else '.'
    df, st = collect_night(night)
    fs = fink_night_stats(night)
    st['fink_objects'] = int(fs.get('f:objects', 0)); st['fink_alerts'] = int(fs.get('f:alerts', 0)); st['fink_sso'] = int(fs.get('f:is_sso', 0))
    st['coverage_vs_fink_objects'] = round(st['objects'] / st['fink_objects'], 4) if st['fink_objects'] else None
    if len(df): df.to_parquet(f'{out}/raw_{night}.parquet')
    json.dump(st, open(f'{out}/raw_{night}.stats.json', 'w'))
    print(json.dumps(st), flush=True)
