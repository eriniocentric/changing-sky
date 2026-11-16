"""Cross-matches that do not depend on CDS Strasbourg.

Gaia DR3  : ESA Gaia archive TAP (table upload). The join must list gaia_source first and test the uploaded
            point against a circle centred on the Gaia source; the other way round does not use the index and
            times out. Chunks are kept spatially compact and small because anonymous jobs are aborted after ~2 min.
SIMBAD    : Harvard mirror TAP (table upload), which answers 10,000 rows in a few seconds.
Both return the nearest match within RADIUS arcsec per object, and a flag saying whether every chunk succeeded.
"""
import io, time, concurrent.futures as cf
import requests, numpy as np, pandas as pd

RADIUS = 1.5  # arcsec
GAIA = 'https://gea.esac.esa.int/tap-server/tap'
SIMBAD = 'https://simbad.harvard.edu/simbad/sim-tap/sync'

def votable(df):
    rows = ''.join(f'<TR><TD>{o}</TD><TD>{a:.7f}</TD><TD>{b:.7f}</TD></TR>' for o, a, b in zip(df.oid, df.ra, df.dec))
    return ('<?xml version="1.0"?><VOTABLE version="1.3" xmlns="http://www.ivoa.net/xml/VOTable/v1.3"><RESOURCE><TABLE>'
            '<FIELD name="oid" datatype="long"/><FIELD name="ra" datatype="double" unit="deg"/><FIELD name="dec" datatype="double" unit="deg"/>'
            '<DATA><TABLEDATA>' + rows + '</TABLEDATA></DATA></TABLE></RESOURCE></VOTABLE>').encode()

QG = ("SELECT u.oid, g.parallax_over_error AS rplx, g.phot_g_mean_mag AS gmag, g.classprob_dsc_combmod_quasar AS pqso, "
      "g.classprob_dsc_combmod_galaxy AS pgal, g.classprob_dsc_combmod_star AS pstar, g.phot_variable_flag AS varflag, "
      "DISTANCE(POINT('ICRS',u.ra,u.dec),POINT('ICRS',g.ra,g.dec))*3600 AS gsep "
      "FROM gaiadr3.gaia_source AS g JOIN tap_upload.t AS u ON 1=CONTAINS(POINT('ICRS',u.ra,u.dec),CIRCLE('ICRS',g.ra,g.dec,%.7f))" % (RADIUS / 3600))
QS = ("SELECT u.oid, b.main_id AS sim_id, b.otype AS sim_type, DISTANCE(POINT('ICRS',u.ra,u.dec),POINT('ICRS',b.ra,b.dec))*3600 AS ssep "
      "FROM TAP_UPLOAD.t AS u JOIN basic AS b ON 1=CONTAINS(POINT('ICRS',b.ra,b.dec),CIRCLE('ICRS',u.ra,u.dec,%.7f))" % (RADIUS / 3600))

def _gaia_job(df, max_wait=240):
    r = requests.post(GAIA + '/async', data={'REQUEST': 'doQuery', 'LANG': 'ADQL', 'FORMAT': 'csv', 'PHASE': 'RUN', 'QUERY': QG, 'UPLOAD': 't,param:t'},
                      files={'t': ('t.xml', votable(df))}, timeout=300, allow_redirects=False)
    job = r.headers.get('Location')
    if not job: raise RuntimeError(f'submit {r.status_code}')
    job = job.replace('http://', 'https://'); t0 = time.time()
    while True:
        ph = requests.get(job + '/phase', timeout=60).text.strip()
        if ph in ('COMPLETED', 'ERROR', 'ABORTED'): break
        if time.time() - t0 > max_wait: raise RuntimeError('timeout waiting for Gaia job')
        time.sleep(3)
    if ph != 'COMPLETED': raise RuntimeError(ph)
    return pd.read_csv(io.StringIO(requests.get(job + '/results/result', timeout=300).text))

def _gaia_chunk(df, depth=0):
    """Run one chunk; on failure split it in two (down to 500 rows) before giving up."""
    try:
        return _gaia_job(df), True
    except Exception as ex:
        if len(df) <= 500 or depth >= 3:
            return pd.DataFrame(), False
        h = len(df) // 2
        a, oka = _gaia_chunk(df.iloc[:h], depth + 1); b, okb = _gaia_chunk(df.iloc[h:], depth + 1)
        return pd.concat([a, b], ignore_index=True), oka and okb

def _nearest(x, sepcol):
    return x.sort_values(sepcol).drop_duplicates('oid') if len(x) else x

def spatial_sort(pos, step=2.0):
    k = (np.floor((pos['dec'].values + 90) / step) * 1000 + np.floor(pos['ra'].values * np.cos(np.radians(pos['dec'].values)) / step)).astype(int)
    return pos.assign(_k=k).sort_values(['_k', 'ra']).drop(columns='_k').reset_index(drop=True)

def gaia(pos, chunk=5000, workers=2, log=print):
    """pos: DataFrame with oid (int), ra, dec. Returns (matches, complete)."""
    ps = spatial_sort(pos); parts = [ps.iloc[i:i + chunk] for i in range(0, len(ps), chunk)]
    out = []; ok = True; t0 = time.time()
    with cf.ThreadPoolExecutor(workers) as ex:
        for k, (x, good) in enumerate(ex.map(_gaia_chunk, parts)):
            out.append(x); ok = ok and good
            if (k + 1) % 5 == 0: log(f'  Gaia chunk {k+1}/{len(parts)}, {time.time()-t0:.0f}s')
    x = pd.concat(out, ignore_index=True) if out else pd.DataFrame()
    return _nearest(x, 'gsep'), ok

def simbad(pos, chunk=10000, log=print):
    out = []; ok = True
    for i in range(0, len(pos), chunk):
        part = pos.iloc[i:i + chunk]; got = None
        for attempt in range(3):
            try:
                r = requests.post(SIMBAD, data={'request': 'doQuery', 'lang': 'adql', 'format': 'csv', 'query': QS, 'upload': 't,param:t'},
                                  files={'t': ('t.xml', votable(part))}, timeout=600)
                if r.status_code == 200 and r.text.startswith('oid'):
                    got = pd.read_csv(io.StringIO(r.text)); break
            except Exception:
                pass
            time.sleep(5 * (attempt + 1))
        if got is None: ok = False
        else: out.append(got)
    x = pd.concat(out, ignore_index=True) if out else pd.DataFrame()
    return _nearest(x, 'ssep'), ok
