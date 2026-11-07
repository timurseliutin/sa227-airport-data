"""Build the current and the next AIRAC cycle if missing, then write dist/manifest.json.

FAA posts NASR subscriber files 28 days before their effective date, so the
next cycle is normally available for the whole current cycle. The app downloads
both and switches to the next one on its effective date, even offline.
"""
import datetime as dt, hashlib, io, json, os, subprocess, sys, urllib.request, zipfile
import airac

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, 'dist')
WORK = os.path.join(ROOT, '.work')
UA = {'User-Agent': 'sa227-airport-data-build (github.com/timurseliutin/sa227-airport-data)'}
OA = 'https://davidmegginson.github.io/ourairports-data/'
KEEP = 4  # cycle files kept in dist/

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()

def oa_files():
    d = os.path.join(WORK, 'oa')
    if not os.path.exists(os.path.join(d, 'runways.csv')):
        os.makedirs(d, exist_ok=True)
        for n in ('airports.csv', 'runways.csv'):
            open(os.path.join(d, n), 'wb').write(get(OA + n))
    return d

def nasr_files(eff):
    d = os.path.join(WORK, 'nasr-' + eff.isoformat())
    if not os.path.exists(os.path.join(d, 'APT_RWY_END.csv')):
        try:
            data = get(airac.nasr_csv_url(eff))
        except Exception as e:
            print('NASR %s not available: %s' % (eff, e)); return None
        os.makedirs(d, exist_ok=True)
        zipfile.ZipFile(io.BytesIO(data)).extractall(d)
    return d

def entry(cyc):
    p = os.path.join(DIST, 'airports-%s.json' % cyc)
    if not os.path.exists(p): return None
    b = open(p, 'rb').read(); m = json.loads(b)['meta']
    return {'cycle': cyc, 'eff': m['eff'], 'exp': m['exp'], 'file': os.path.basename(p),
            'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest(), 'counts': m['counts']}

def ensure(eff, today):
    cyc = airac.cycle_id(eff)
    if entry(cyc): return True
    nd = nasr_files(eff)
    if not nd: return False
    out = os.path.join(DIST, 'airports-%s.json' % cyc)
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'build_db.py'), '--nasr', nd, '--oa', oa_files(),
                        '--eff', eff.isoformat(), '--oa-date', today.isoformat(), '--out', out], cwd=os.path.join(ROOT, 'tools'))
    if r.returncode: raise SystemExit('build failed for cycle ' + cyc)
    return True

def main():
    today = dt.datetime.now(dt.timezone.utc).date()
    os.makedirs(DIST, exist_ok=True)
    cur = airac.cycle_start(today); nxt = cur + airac.STEP
    if not ensure(cur, today): raise SystemExit('current cycle %s not available from FAA' % airac.cycle_id(cur))
    ensure(nxt, today)  # optional: posted 28 days ahead
    man = {'v': 2, 'current': entry(airac.cycle_id(cur)), 'next': entry(airac.cycle_id(nxt)),
           'base': 'https://raw.githubusercontent.com/timurseliutin/sa227-airport-data/main/dist/'}
    old_p = os.path.join(DIST, 'manifest.json')
    old = json.load(open(old_p)) if os.path.exists(old_p) else {}
    if {k: old.get(k) for k in ('current', 'next')} != {k: man[k] for k in ('current', 'next')}:
        man['updated'] = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%MZ')
        json.dump(man, open(old_p, 'w'), indent=1)
        print('manifest updated:', man['current']['cycle'], man['next'] and man['next']['cycle'])
    else:
        print('manifest unchanged')
    files = sorted(f for f in os.listdir(DIST) if f.startswith('airports-'))
    keep = {man['current']['file']} | ({man['next']['file']} if man['next'] else set())
    for f in files[:-KEEP]:
        if f not in keep: os.remove(os.path.join(DIST, f))

if __name__ == '__main__':
    main()
