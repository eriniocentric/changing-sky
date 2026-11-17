"""Build the published data for one night from its raw table (one row per object).

Output, under <site>/data/n/<night>/ :
  top.json        the strongest TOPK objects of every type, for the zoomed-out view
  t/<j>_<i>.json  every object in one sky tile (2.8 deg), strongest first, loaded when the view zooms in
  dens.json       per-tile counts by type, for the density layer and to know which tiles exist
and <site>/data/nights.json, the index of nights (rolling window of WINDOW nights).

Row layout: [id, sourceId, ra, dec, type, name, band, mag, snr, reliability, mjd, catalogue note, age_days, tags, sso]
(trailing empty fields are dropped; ids are strings because they exceed JavaScript's integer range).

Usage: python pipeline/build_night.py 20261115 --raw <raw folder> --site <site folder>
"""
import argparse, datetime as dt, io, json, math, os, re, shutil, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fink_night as fn, xmatch

WINDOW = 1       # nights kept on the site (only the latest; older nights load from Fink on demand)
TOPK = 200       # objects per type in top.json
TB = 64          # tile bands: 180/64 = 2.8125 deg

# ---------------- tiles ----------------
_TN = np.array([max(1, int(math.ceil(360 * math.cos(math.radians(-90 + (j + 0.5) * 180 / TB)) / (180 / TB)))) for j in range(TB)])
def tiles_of(ra, dec):
    j = np.clip(np.floor((np.asarray(dec, float) + 90) / (180 / TB)).astype(int), 0, TB - 1)
    n = _TN[j]
    i = np.floor((np.asarray(ra, float) % 360) / (360 / n)).astype(int) % n
    return j, i
def tile_centre(j, i):
    return (i + 0.5) * 360 / _TN[j], -90 + (j + 0.5) * 180 / TB

# ---------------- classification ----------------
S_AGN = {'AGN', 'AG?', 'QSO', 'Q?', 'Sy1', 'Sy2', 'SyG', 'BLL', 'BL?', 'Bla', 'Bz?', 'LIN', 'rG'}
S_GAL = {'G', 'GiC', 'GiG', 'GrG', 'EmG', 'LSB', 'bCG', 'SBG', 'H2G', 'LeG', 'BiC', 'ClG', 'PaG', 'IG', 'GiP', 'SCG', 'CGG', 'HzG', 'GWE', 'BCG', 'G?'}
S_VAR = {'V*', 'EB*', 'RR*', 'CV*', 'Pu*', 'Mi*', 'dS*', 'LP*', 'Ce*', 'cC*', 'RS*', 'BY*', 'Er*', 'TT*', 'Y*O', 'Fl*', 'Ro*', 'No*', 'gD*', 'SX*',
         'RC*', 'sr*', 'Or*', 'El*', 'Ir*', 'WV*', 'bC*', 'RV*', 'Sy*', 'XB*', 'LXB', 'HXB', 'Ae*', 'a2*', 'Psr'}
S_NOTSTAR = {'Cl*', 'As*', 'St*', 'GlC', 'OpC', 'MGr', 'SN*'}
NICE = {'QSO': 'quasar', 'AGN': 'active galaxy', 'Sy1': 'Seyfert 1 galaxy', 'Sy2': 'Seyfert 2 galaxy', 'SyG': 'Seyfert galaxy', 'BLL': 'BL Lac object',
        'Bla': 'blazar', 'LIN': 'LINER galaxy', 'rG': 'radio galaxy', 'RR*': 'RR Lyrae star', 'EB*': 'eclipsing binary', '*': 'star', 'G': 'galaxy',
        'WD*': 'white dwarf', 'CV*': 'cataclysmic variable', 'LP*': 'long-period variable', 'Mi*': 'Mira variable', 'dS*': 'delta Scuti star',
        'Ce*': 'Cepheid', 'cC*': 'classical Cepheid', 'PM*': 'high proper-motion star', 'V*': 'variable star', 'Y*O': 'young stellar object',
        'TT*': 'T Tauri star', 'RS*': 'RS CVn variable', 'BY*': 'BY Dra variable', 'Er*': 'eruptive variable', 'Pu*': 'pulsating variable',
        'El*': 'ellipsoidal variable', 'Ro*': 'rotational variable', 'X': 'X-ray source', 'Rad': 'radio source', 'IR': 'infrared source',
        'UV': 'ultraviolet source', 'blu': 'blue object', 'GiC': 'galaxy in a cluster', 'GiG': 'galaxy in a group', 'EmG': 'emission-line galaxy',
        'LSB': 'low surface brightness galaxy', 'SN*': 'supernova', 'HB*': 'horizontal-branch star', 'RG*': 'red giant', 'BS*': 'blue straggler',
        'LM*': 'low-mass star', '**': 'double star', 'SB*': 'spectroscopic binary', 'HS*': 'hot subdwarf', 'C*': 'carbon star', 'AB*': 'AGB star',
        'No*': 'nova', 'gD*': 'gamma Doradus star', 'SX*': 'SX Phe star', 'Psr': 'pulsar', 'GlC': 'globular cluster', 'Em*': 'emission-line star'}

def norm_otype(c):
    """SIMBAD candidate codes end in '?': map them to the confirmed code and remember they are candidates."""
    if c is None: return None, False
    if c in S_AGN or c in S_GAL or not c.endswith('?') or c == '?': return c, False
    base = {'Y*?': 'Y*O', 'LX?': 'LXB', 'HX?': 'HXB', 'SN?': 'SN*'}.get(c) or (c[:-1] + '*')
    return base, True

def clean(v):
    s = str(v)
    return None if s in ('nan', 'None', 'Fail', '', 'Unknown', '<NA>', 'NaN') else s

def fnum(v, default=0.0):
    try:
        f = float(v)
        return f if f == f else default
    except Exception:
        return default

def classify(r):
    """Returns (type, name, catalogue note). Same precedence as the first Changing Sky build:
    TNS class > explicit AGN > explicit variable star > Gaia quasar candidate > TNS unclassified > star > hostless > galaxy > Fink stream > other > unidentified."""
    vsx = clean(r.get('f:xm_vsx_Type')); tns = clean(r.get('f:xm_tns_fullname')); tt = clean(r.get('f:xm_tns_type'))
    bl = clean(r.get('f:xm_x4lac_type')) or clean(r.get('f:xm_x3hsp_type')); led = clean(r.get('f:xm_mangrove_HyperLEDA_name'))
    raw_sim = clean(r.get('sim_type')); sim, cand = norm_otype(raw_sim); simid = clean(r.get('sim_id')); tags = r.get('tags') if isinstance(r.get('tags'), str) else ''
    pq, ps, pg, rplx = fnum(r.get('pqso')), fnum(r.get('pstar')), fnum(r.get('pgal')), fnum(r.get('rplx'))
    gmag = fnum(r.get('gmag'), None); gvar = r.get('varflag') == 'VARIABLE'
    simlab = None
    if sim:
        simlab = 'SIMBAD ' + NICE.get(sim, sim) + (' candidate' if cand else '') + (f' ({simid})' if simid else '')
    if tt and tt not in ('AGN', 'Varstar', 'CV'):
        return 'sn', tns, tt
    sim_var = sim in S_VAR
    sim_star = bool(sim) and ('*' in sim or sim == 'Psr') and sim not in S_NOTSTAR
    if (sim in S_AGN) or (vsx in ('AGN', 'BLLAC', 'CV|QSO')) or bl or tt == 'AGN':
        return 'agn', tns, (simlab if sim in S_AGN else None) or (f'VSX {vsx}' if vsx else None) or bl or 'AGN'
    if (vsx and vsx not in ('SN Ia', 'SN Ia-pec')) or tt in ('Varstar', 'CV') or sim_var or (gvar and (pq <= 0.5 or rplx >= 5 or sim_star)):
        return 'var', tns, (f'VSX {vsx}' if vsx else None) or simlab or ('Gaia DR3 variable' if gvar else tt)
    if pq > 0.5 and rplx < 5 and not sim_star:
        return 'agn', tns, f'Gaia DR3 quasar candidate (prob {pq:.2f}' + (', variable)' if gvar else ')')
    if tns:
        return 'at', tns, 'TNS transient'
    if sim_star or ps > 0.5 or rplx > 5:
        return 'star', None, simlab or (f'Gaia star (G={gmag:.1f})' if gmag is not None else 'Gaia star')
    if 'hostless' in tags:
        return 'host', None, 'hostless (ELEPHANT)'
    if (sim in S_GAL) or led or pg > 0.5:
        return 'gal', None, simlab or (f'HyperLEDA {led}' if led else f'Gaia galaxy prob {pg:.2f}')
    if 'extragalactic' in tags or 'most_likely_sn' in tags or 'sn_near_galaxy' in tags:
        return 'xgal', None, 'Fink extragalactic/SN stream'
    if sim:
        return 'other', None, simlab
    return 'unk', None, None

# ---------------- Fink stream membership for the night ----------------
TAGS = {'hostless_candidate': 'hostless', 'extragalactic_new_candidate': 'extragalactic', 'extragalactic_lt20mag_candidate': 'extragalactic',
        'most_likely_sn': 'most_likely_sn', 'sn_near_galaxy_candidate': 'sn_near_galaxy'}
def mjd2iso(m):
    return (dt.datetime(1858, 11, 17) + dt.timedelta(days=float(m))).strftime('%Y-%m-%d %H:%M:%S')
def tag_members(night, log=print):
    S, E, m0, m1 = fn.night_window(night); out = {}
    for tag, lab in TAGS.items():
        stop = E; ids = set()
        for page in range(12):
            try:
                r = fn._post('tags', {'tag': tag, 'n': 5000, 'startdate': S, 'stopdate': stop, 'columns': 'r:diaObjectId,r:midpointMjdTai', 'output-format': 'json'}, tries=2)
                js = json.loads(re.sub(r'(:\s*)(-?\d{16,})(\s*[,}])', r'\1"\2"\3', r.text))
            except Exception as ex:
                log('  tag', tag, 'failed:', ex); break
            if not isinstance(js, list) or not js: break
            ids |= {str(x['r:diaObjectId']) for x in js if 'r:diaObjectId' in x}
            if len(js) < 5000: break
            stop = mjd2iso(min(x['r:midpointMjdTai'] for x in js) - 38 / 86400)   # TAI -> UTC, step back 1 s
        for i in ids: out.setdefault(i, set()).add(lab)
        log(f'  stream {tag}: {len(ids)} objects')
    return {i: ' '.join(sorted(v)) for i, v in out.items()}

def visit_times(mjds, gap=0.0002):
    """Distinct exposure times of a night (alerts from one exposure share its midpoint time)."""
    out = []
    for m in sorted(round(float(x), 4) for x in mjds if x is not None):
        if not out or m - out[-1] > gap: out.append(m)
    return out

# ---------------- build ----------------
def jdump(obj, path):
    with open(path, 'w') as fh: json.dump(obj, fh, separators=(',', ':'), allow_nan=False)

def rnd(v, k):
    try:
        f = float(v)
        return round(f, k) if f == f else None
    except Exception:
        return None

def trim(row):
    while row and row[-1] is None: row.pop()
    return row

def build(night, rawdir, sitedir, log=print, extra_rows=None, extra_stats=None):
    raw = pd.read_parquet(os.path.join(rawdir, f'raw_{night}.parquet'))
    st = json.load(open(os.path.join(rawdir, f'raw_{night}.stats.json'))) if os.path.exists(os.path.join(rawdir, f'raw_{night}.stats.json')) else {}
    raw['oid'] = raw['r:diaObjectId'].astype('int64')
    # cross-matches, cached next to the raw table
    xp = os.path.join(rawdir, f'xm_{night}.parquet'); xs = os.path.join(rawdir, f'xm_{night}.stats.json')
    if os.path.exists(xp) and os.path.exists(xs):
        xm = pd.read_parquet(xp); xst = json.load(open(xs))
    else:
        pos = raw[['oid', 'r:ra', 'r:dec']].rename(columns={'r:ra': 'ra', 'r:dec': 'dec'})
        s, oks = xmatch.simbad(pos, log=log); g, okg = xmatch.gaia(pos, log=log)
        xm = pos[['oid']].merge(g, on='oid', how='left').merge(s, on='oid', how='left'); xm.to_parquet(xp)
        xst = {'gaia_complete': bool(okg), 'simbad_complete': bool(oks), 'gaia_matches': int(len(g)), 'simbad_matches': int(len(s))}
        json.dump(xst, open(xs, 'w'))
    for c in ['rplx', 'gmag', 'pqso', 'pgal', 'pstar', 'varflag', 'sim_id', 'sim_type']:
        if c not in xm: xm[c] = None
    d = raw.merge(xm[['oid', 'rplx', 'gmag', 'pqso', 'pgal', 'pstar', 'varflag', 'sim_id', 'sim_type']], on='oid', how='left')
    tags = tag_members(night, log=log)
    d['id'] = d['oid'].astype(str); d['tags'] = d['id'].map(tags)
    n_objects = len(d)
    b = lambda c: d[c].fillna(False).astype(bool)
    glint = d[b('r:glint_trail')].copy()
    ok = (~b('r:isDipole')) & (~b('r:glint_trail')) & (~b('r:pixelFlags_saturatedCenter')) & (d['r:snr'] >= 5)
    d = d[ok].copy(); n_cut1 = len(d)
    res = [classify(r) for r in d.to_dict('records')]
    d['cat'] = [x[0] for x in res]; d['name'] = [x[1] for x in res]; d['xm'] = [x[2] for x in res]
    d = d[~((d['cat'] == 'unk') & (d['r:reliability'] < 0.8))]; n_cut2 = len(d)
    if len(glint):
        tl = glint['r:trailLength']
        glint['cat'] = 'glint'; glint['name'] = None
        glint['xm'] = ['Rubin glint-trail flag' + (f' · trail length {v:.1f}″' if v == v and v is not None else '') for v in tl]
        d = pd.concat([d, glint], ignore_index=True)
    d['mag'] = (31.4 - 2.5 * np.log10(d['r:psfFlux'].abs().clip(lower=1))).round(2)
    age = np.floor(d['r:midpointMjdTai'] - d['f:firstDiaSourceMjdTaiFink'])
    d['age'] = [None if v != v else int(max(0, v)) for v in age]
    rows = [trim([r['id'], str(int(r['r:diaSourceId'])), rnd(r['r:ra'], 5), rnd(r['r:dec'], 5), r['cat'], r['name'], r['r:band'], rnd(r['mag'], 2),
                  rnd(r['r:snr'], 1), rnd(r['r:reliability'], 2), rnd(r['r:midpointMjdTai'], 4), r['xm'], r['age'], r['tags'] if isinstance(r['tags'], str) else None])
            for r in d.to_dict('records')]
    if extra_rows: rows += extra_rows
    # ---- write ----
    out = os.path.join(sitedir, 'data', 'n', str(night))
    if os.path.exists(out): shutil.rmtree(out)
    os.makedirs(os.path.join(out, 't'))
    ra = np.array([r[2] for r in rows]); de = np.array([r[3] for r in rows]); tj, ti = tiles_of(ra, de)
    snr = np.array([r[8] if len(r) > 8 and r[8] is not None else 0 for r in rows], float)
    order = np.argsort(-snr); bytile = {}; bycat = {}
    for k in order:
        bytile.setdefault((int(tj[k]), int(ti[k])), []).append(rows[k]); bycat.setdefault(rows[k][4], []).append(rows[k])
    dens = {}; nbytes = 0
    for (j, i), lst in bytile.items():
        p = os.path.join(out, 't', f'{j}_{i}.json'); jdump(lst, p); nbytes += os.path.getsize(p)
        cnt = {}
        for r in lst: cnt[r[4]] = cnt.get(r[4], 0) + 1
        c = tile_centre(j, i); dens[f'{j}_{i}'] = [round(c[0], 3), round(c[1], 3), cnt]
    jdump(dens, os.path.join(out, 'dens.json'))
    top = [r for c, lst in bycat.items() for r in lst[:TOPK]]
    jdump(top, os.path.join(out, 'top.json')); nbytes += os.path.getsize(os.path.join(out, 'top.json'))
    counts = {c: len(lst) for c, lst in bycat.items()}
    mj = [r[10] for r in rows if len(r) > 10 and r[10] is not None]
    entry = {'night': str(night), 'n': len(rows), 'counts': counts, 'tiles': len(bytile), 'mjd': [min(mj), max(mj)] if mj else None,
             'bytes': nbytes, 'top': len(top), 'visits': visit_times(mj),
             'fink': {k: st.get(k) for k in ('fink_objects', 'fink_alerts', 'fink_sso', 'fink_visits') if st.get(k) is not None},
             'coverage': st.get('coverage_vs_fink_objects'),
             'cuts': {'objects': n_objects, 'after_artefact_cuts': n_cut1, 'after_reliability_cut': n_cut2},
             'xm': {'gaia': bool(xst.get('gaia_complete')), 'simbad': bool(xst.get('simbad_complete')), 'milliquas': False},
             'built_utc': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
    if extra_stats: entry.update(extra_stats)
    update_index(sitedir, entry, log=log)
    return entry

def update_index(sitedir, entry, log=print):
    p = os.path.join(sitedir, 'data', 'nights.json')
    idx = json.load(open(p)) if os.path.exists(p) else {'tile_bands': TB, 'nights': []}
    nights = [n for n in idx['nights'] if n['night'] != entry['night']] + [entry]
    nights.sort(key=lambda n: n['night'])
    for old in nights[:-WINDOW]:
        q = os.path.join(sitedir, 'data', 'n', old['night'])
        if os.path.exists(q): shutil.rmtree(q)
        log('dropped night outside the rolling window:', old['night'])
    idx['nights'] = nights[-WINDOW:]; idx['tile_bands'] = TB; idx['window'] = WINDOW
    idx['updated_utc'] = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    jdump(idx, p)

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('night'); ap.add_argument('--raw', required=True); ap.add_argument('--site', required=True)
    a = ap.parse_args()
    e = build(a.night, a.raw, a.site, log=lambda *x: print(*x, flush=True))
    print(json.dumps(e))
