"""One-off: convert the first Changing Sky night (2026-07-14, per-category files in data/<cat>.json) to the tiled layout.

Old row: [id, sid, ra, dec, cat, name, band, mag, snr, rel, mjd, note, sources, satellite note, (sso extra)]
New row: [id, sid, ra, dec, cat, name, band, mag, snr, rel, mjd, note, age_days, tags, sso extra]
The satellite note is appended to the catalogue note; 'sources' becomes the tags field.
Usage: python pipeline/convert_legacy.py --site <site folder>
"""
import argparse, glob, json, os, shutil, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_night as bn

NIGHT = '20260714'
FINK = {'fink_objects': 403821, 'fink_alerts': 473344, 'fink_sso': 32641, 'fink_visits': 129}

def convert(site, log=print):
    rows = []
    for f in sorted(glob.glob(os.path.join(site, 'data', '*.json'))):
        if os.path.basename(f) == 'nights.json': continue
        for r in json.load(open(f)):
            r = list(r) + [None] * (15 - len(r))
            note = r[11]
            if r[13]: note = (note + ' · ' if note else '') + '🛰 ' + r[13]
            rows.append(bn.trim([r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], note, None, r[12], r[14]]))
    log('legacy rows', len(rows))
    out = os.path.join(site, 'data', 'n', NIGHT)
    if os.path.exists(out): shutil.rmtree(out)
    os.makedirs(os.path.join(out, 't'))
    ra = np.array([r[2] for r in rows]); de = np.array([r[3] for r in rows]); tj, ti = bn.tiles_of(ra, de)
    snr = np.array([r[8] if len(r) > 8 and r[8] is not None else 0 for r in rows], float)
    bytile, bycat = {}, {}
    for k in np.argsort(-snr):
        bytile.setdefault((int(tj[k]), int(ti[k])), []).append(rows[k]); bycat.setdefault(rows[k][4], []).append(rows[k])
    dens = {}; nbytes = 0
    for (j, i), lst in bytile.items():
        p = os.path.join(out, 't', f'{j}_{i}.json'); bn.jdump(lst, p); nbytes += os.path.getsize(p)
        cnt = {}
        for r in lst: cnt[r[4]] = cnt.get(r[4], 0) + 1
        c = bn.tile_centre(j, i); dens[f'{j}_{i}'] = [round(c[0], 3), round(c[1], 3), cnt]
    bn.jdump(dens, os.path.join(out, 'dens.json'))
    top = [r for c, lst in bycat.items() if c != 'star' for r in lst[:bn.TOPK]] + bycat.get('star', [])[:bn.TOPK]
    bn.jdump(top, os.path.join(out, 'top.json')); nbytes += os.path.getsize(os.path.join(out, 'top.json'))
    mj = [r[10] for r in rows if len(r) > 10 and r[10] is not None]
    entry = {'night': NIGHT, 'n': len(rows), 'counts': {c: len(v) for c, v in bycat.items()}, 'tiles': len(bytile),
             'mjd': [min(mj), max(mj)], 'visits': bn.visit_times(mj), 'bytes': nbytes, 'top': len(top), 'fink': FINK, 'coverage': round(379171 / 403821, 4),
             'xm': {'gaia': True, 'simbad': True, 'milliquas': True}, 'legacy': True,
             'note': 'First Changing Sky night, built before the nightly pipeline; includes predicted satellite tracks and asteroids.'}
    bn.update_index(site, entry, log=log)
    return entry

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--site', required=True); a = ap.parse_args()
    print(json.dumps(convert(a.site)))
