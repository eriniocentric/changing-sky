"""Daily job for Changing Sky. Version 1: capture the newest Rubin night from Fink as a raw table.

Why it must run every day: Fink's cone search returns each object's LATEST alert. For the newest night
that is the night's own alert, so one sweep captures the night exactly. Once a later night has been
ingested, objects seen again show the later alert instead, and the night can only be rebuilt with a much
slower light-curve pass. Nights that were missed are therefore listed in missing.json, not fetched here.

Usage: python pipeline/daily.py --raw <folder for raw tables> [--night YYYYMMDD]
"""
import argparse, datetime as dt, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fink_night as fn

FIRST_NIGHT = '20261115'      # first night captured by this pipeline

def utcnow():
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

def fink_nights():
    out = {}
    for month in sorted({utcnow().strftime('%Y%m'), (utcnow() - dt.timedelta(days=20)).strftime('%Y%m')}):
        try:
            for r in fn._post('statistics', {'date': month, 'output-format': 'json'}, tries=2).json():
                out[str(r['f:night'])] = r
        except Exception as ex:
            print('statistics failed for', month, ex, flush=True)
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--raw', required=True); ap.add_argument('--night')
    a = ap.parse_args(); os.makedirs(a.raw, exist_ok=True)
    have = {f[4:12] for f in os.listdir(a.raw) if f.startswith('raw_') and f.endswith('.parquet')}
    stats = fink_nights()
    today = utcnow().strftime('%Y%m%d')
    night = a.night or today
    log = lambda *x: print(*x, flush=True)
    log('Fink nights known:', len(stats), '| newest in statistics:', max(stats) if stats else None, '| already captured:', sorted(have)[-3:])
    if night in have:
        log(night, 'already captured; nothing to do')
    else:
        newer = [n for n in stats if n > night]
        if newer:
            log(night, 'is no longer the newest night (newer:', newer, '), so the fast capture would be wrong; listing it as missing')
        else:
            df, st = fn.collect_night(night, log=log)
            fs = stats.get(night) or fn.fink_night_stats(night) or {}
            st['fink_objects'] = int(fs.get('f:objects', 0) or 0); st['fink_alerts'] = int(fs.get('f:alerts', 0) or 0)
            st['fink_sso'] = int(fs.get('f:is_sso', 0) or 0); st['fink_visits'] = int(fs.get('f:visits', 0) or 0)
            st['coverage_vs_fink_objects'] = round(st['objects'] / st['fink_objects'], 4) if st['fink_objects'] else None
            st['captured_utc'] = utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
            log(json.dumps(st))
            if st['objects'] == 0:
                log(night, ': no alerts found (no observing, or data not in Fink yet); nothing saved')
            elif st['objects_with_later_alert'] > 0.02 * st['objects']:
                log(night, ': a later night is already mixed in; not saved as a clean night')
            else:
                df[df['in_night']].drop(columns=['in_night']).to_parquet(os.path.join(a.raw, f'raw_{night}.parquet'))
                json.dump(st, open(os.path.join(a.raw, f'raw_{night}.stats.json'), 'w'))
                have.add(night); log('saved', night, st['objects'], 'objects')
    missing = sorted(n for n in stats if n >= FIRST_NIGHT and n not in have and n != today)
    json.dump({'missing_nights': missing, 'checked_utc': utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}, open(os.path.join(a.raw, 'missing.json'), 'w'))
    log('nights in Fink since', FIRST_NIGHT, 'not captured:', missing)

if __name__ == '__main__':
    main()
