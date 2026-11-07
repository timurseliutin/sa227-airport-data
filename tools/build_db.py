"""Build the SA227 Performance airport database for one AIRAC cycle.

United States (incl. territories): FAA NASR 28-day subscription, APT CSV group
  (APT_BASE, APT_RWY, APT_RWY_END) - official, public domain.
Canada and Mexico: OurAirports (airports.csv, runways.csv) - community data,
  Unlicense; marked as not official in the app.
Magnetic variation: World Magnetic Model 2025 (pygeomag) at the cycle date.

Output format (v2), compact JSON:
  {v, meta, a: {CODE: airport}, alias: {OTHER: CODE}}
  airport = [name, city, region, elev_ft, var_deg(+E), runways, src('N'|'O')]
  runway  = [length_ft, width_ft, surface, ends]
  end     = [ident, mag_hdg|null, displaced_thr_ft, end_elev_ft|null, hdg_src,
             tora|null, toda|null, asda|null, lda|null]
  hdg_src: T = published true alignment, C = from end coordinates, N = from runway number.
"""
import argparse, csv, datetime as dt, json, math, os, sys
from pygeomag import GeoMag
import airac

MIN_LEN = 2000

def f(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None

def bearing(la1, lo1, la2, lo2):
    p1, p2 = math.radians(la1), math.radians(la2); dl = math.radians(lo2 - lo1)
    y = math.sin(dl) * math.cos(p2); x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360

def num_hdg(ident):
    n = ''.join(ch for ch in ident if ch.isdigit())
    return int(n) * 10 if n and 1 <= int(n) <= 36 else None

def mag(true_deg, var):
    return round((true_deg - var) % 360) or 360

def title(s):
    small = {'INTL': 'International', 'MUNI': 'Municipal', 'RGNL': 'Regional', 'CO': 'County', 'MEML': 'Memorial', 'ARPT': 'Airport', 'FLD': 'Field'}
    out = []
    for w in (s or '').split():
        out.append(small.get(w, w.capitalize() if len(w) > 1 else w))
    return ' '.join(out)

def rows(path):
    with open(path, encoding='utf-8-sig', errors='replace', newline='') as fh:
        yield from csv.DictReader(fh)

def end_hdg(true_al, coords, ident, var):
    t = f(true_al)
    if t is not None:
        return mag(t, var), 'T'
    if coords and None not in coords and (coords[0] != coords[2] or coords[1] != coords[3]):
        return mag(bearing(*coords), var), 'C'
    n = num_hdg(ident)
    return (n, 'N') if n else (None, '-')

def i_or_none(x):
    v = f(x)
    return None if v is None else int(round(v))

def e1(x):
    v = f(x)
    return None if v is None else round(v, 1)

def build(nasr_dir, oa_dir, eff, oa_date):
    geo = GeoMag(coefficients_file='wmm/WMM_2025.COF')
    year = eff.year + (eff.timetuple().tm_yday - 1) / 365.25
    out, alias = {}, {}

    # ---------- OurAirports (names/IATA for the US, full data for CA and MX) ----------
    oa_ap = {}
    for r in rows(os.path.join(oa_dir, 'airports.csv')):
        if r['iso_country'] in ('US', 'CA', 'MX', 'PR', 'GU', 'VI', 'AS', 'MP') and r['type'] in ('small_airport', 'medium_airport', 'large_airport'):
            oa_ap[r['id']] = r
    oa_by_code = {}
    for r in oa_ap.values():
        for k in (r['gps_code'], r['icao_code'], r['local_code'], r['ident']):
            k = (k or '').upper().strip()
            if k: oa_by_code.setdefault(k, r)

    # ---------- NASR (United States) ----------
    base = {}
    for r in rows(os.path.join(nasr_dir, 'APT_BASE.csv')):
        if r['SITE_TYPE_CODE'] != 'A' or r['ARPT_STATUS'] != 'O':
            continue
        base[r['SITE_NO']] = r
    rwy = {}
    for r in rows(os.path.join(nasr_dir, 'APT_RWY.csv')):
        if r['SITE_NO'] not in base: continue
        L = f(r['RWY_LEN'])
        s = (r['SURFACE_TYPE_CODE'] or '').upper()
        if not L or L < MIN_LEN or 'WATER' in s: continue
        if r['RWY_ID'].upper().startswith('H'): continue
        rwy[(r['SITE_NO'], r['RWY_ID'])] = {'r': r, 'ends': []}
    for r in rows(os.path.join(nasr_dir, 'APT_RWY_END.csv')):
        k = (r['SITE_NO'], r['RWY_ID'])
        if k in rwy: rwy[k]['ends'].append(r)

    by_site = {}
    for (site, _), v in rwy.items():
        by_site.setdefault(site, []).append(v)
    nasr_n = 0
    for site, rws in by_site.items():
        a = base[site]
        la, lo = f(a['LAT_DECIMAL']), f(a['LONG_DECIMAL'])
        if la is None or lo is None: continue
        var = geo.calculate(glat=la, glon=lo, alt=0, time=year).d
        runways = []
        for v in rws:
            r = v['r']; L = int(round(f(r['RWY_LEN'])))
            ends_raw = sorted(v['ends'], key=lambda e: r['RWY_ID'].split('/').index(e['RWY_END_ID']) if e['RWY_END_ID'] in r['RWY_ID'].split('/') else 9)
            ends = []
            for e in ends_raw:
                ident = (e['RWY_END_ID'] or '').strip().upper()
                if not ident: continue
                other = [o for o in ends_raw if o is not e]
                coords = None
                if other:
                    coords = [f(e['LAT_DECIMAL']), f(e['LONG_DECIMAL']), f(other[0]['LAT_DECIMAL']), f(other[0]['LONG_DECIMAL'])]
                h, src = end_hdg(e['TRUE_ALIGNMENT'], coords, ident, var)
                ends.append([ident, h, i_or_none(e['DISPLACED_THR_LEN']) or 0, e1(e['RWY_END_ELEV']), src,
                             i_or_none(e['TKOF_RUN_AVBL']), i_or_none(e['TKOF_DIST_AVBL']), i_or_none(e['ACLT_STOP_DIST_AVBL']), i_or_none(e['LNDG_DIST_AVBL'])])
            if ends:
                runways.append([L, i_or_none(r['RWY_WIDTH']) or 0, (r['SURFACE_TYPE_CODE'] or '').upper()[:10], ends])
        if not runways: continue
        runways.sort(key=lambda x: -x[0])
        lid = a['ARPT_ID'].upper().strip(); icao = (a['ICAO_ID'] or '').upper().strip()
        code = icao or lid
        oa = oa_by_code.get(code) or oa_by_code.get(lid)
        name = (oa['name'] if oa else title(a['ARPT_NAME']))[:48]
        elev = f(a['ELEV'])
        out[code] = [name, title(a['CITY'])[:32], 'US-' + a['STATE_CODE'] if a['STATE_CODE'] else a['COUNTRY_CODE'],
                     None if elev is None else int(round(elev)), round(var, 1), runways, 'N']
        for k in (lid, icao, oa and oa['iata_code'], oa and oa['local_code'], oa and oa['ident']):
            k = (k or '').upper().strip()
            if k and k != code: alias.setdefault(k, code)
        nasr_n += 1

    # ---------- OurAirports (Canada, Mexico) ----------
    oa_rw = {}
    for r in rows(os.path.join(oa_dir, 'runways.csv')):
        a = oa_ap.get(r['airport_ref'])
        if not a or a['iso_country'] not in ('CA', 'MX') or r['closed'] == '1': continue
        L = f(r['length_ft'])
        if not L or L < MIN_LEN: continue
        s = (r['surface'] or '').upper()
        if 'WATER' in s or s in ('WAT', 'W'): continue
        le = r['le_ident'].strip()
        if not le or le.upper().startswith('H'): continue
        oa_rw.setdefault(r['airport_ref'], []).append(r)
    oa_n = 0
    for aid, rws in oa_rw.items():
        a = oa_ap[aid]
        la, lo = f(a['latitude_deg']), f(a['longitude_deg'])
        if la is None or lo is None: continue
        var = geo.calculate(glat=la, glon=lo, alt=0, time=year).d
        runways = []
        for r in rws:
            ends = []
            for p, q in (('le', 'he'), ('he', 'le')):
                ident = r[p + '_ident'].strip().upper()
                if not ident: continue
                t = f(r[p + '_heading_degT'])
                coords = [f(r[p + '_latitude_deg']), f(r[p + '_longitude_deg']), f(r[q + '_latitude_deg']), f(r[q + '_longitude_deg'])]
                h, src = end_hdg(t, coords, ident, var)
                ends.append([ident, h, int(f(r[p + '_displaced_threshold_ft']) or 0), e1(r[p + '_elevation_ft']), src, None, None, None, None])
            if ends:
                runways.append([int(f(r['length_ft'])), int(f(r['width_ft']) or 0), (r['surface'] or '').upper()[:10], ends])
        runways.sort(key=lambda x: -x[0])
        code = (a['icao_code'] or a['gps_code'] or a['ident']).upper()
        if code in out: code = a['ident'].upper()
        if code in out: continue
        elev = f(a['elevation_ft'])
        out[code] = [a['name'][:48], (a['municipality'] or '')[:32], a['iso_region'], None if elev is None else int(round(elev)), round(var, 1), runways, 'O']
        for k in (a['ident'], a['gps_code'], a['icao_code'], a['iata_code'], a['local_code']):
            k = (k or '').upper().strip()
            if k and k != code: alias.setdefault(k, code)
        oa_n += 1

    for k in list(alias):
        if k in out: del alias[k]
    exp = eff + airac.STEP
    meta = {'cycle': airac.cycle_id(eff), 'eff': eff.isoformat(), 'exp': exp.isoformat(),
            'us': 'FAA NASR 28-day subscription, effective ' + eff.isoformat(),
            'ca_mx': 'OurAirports ' + oa_date + ' (not an official source)',
            'var': 'WMM2025 at %.2f' % year, 'counts': {'us': nasr_n, 'ca_mx': oa_n, 'alias': len(alias)}}
    return {'v': 2, 'meta': meta, 'a': out, 'alias': alias}

# ---------- checks: the build fails rather than publish a bad database ----------
CONTROL = {  # code: (runway end ident, minimum TORA ft) - long-established runways
    'KLRD': ('18R', 8000), 'KYIP': ('23', 7000), 'KJFK': ('31L', 10000), 'KDEN': ('16R', 15000),
    'PANC': ('7R', 10000), 'KSLC': ('34R', 11000), 'KPVU': ('13', 8000), 'PHNL': ('8R', 11000),
    'CYVR': ('08R', 9000), 'CYYZ': ('05', 10000), 'MMMX': ('05L', 12000), 'MMUN': ('12R', 10000),
}

def check(db):
    errs = []
    a = db['a']; c = db['meta']['counts']
    if c['us'] < 4000: errs.append('only %d US airports' % c['us'])
    if c['ca_mx'] < 400: errs.append('only %d CA/MX airports' % c['ca_mx'])
    for code, (end, mn) in CONTROL.items():
        ap = a.get(code)
        if not ap: errs.append('control airport %s missing' % code); continue
        found = [(rw, e) for rw in ap[5] for e in rw[3] if e[0].lstrip('0') == end.lstrip('0')]
        if not found: errs.append('%s runway %s missing' % (code, end)); continue
        rw, e = found[0]
        tora = e[5] or rw[0]
        if tora < mn: errs.append('%s %s TORA %d < %d' % (code, end, tora, mn))
    for code, ap in a.items():
        if not ap[5]: errs.append(code + ' has no runways')
        if not (-1500 < (ap[3] or 0) < 15000): errs.append('%s elevation %s' % (code, ap[3]))
        for rw in ap[5]:
            if rw[0] < MIN_LEN or rw[0] > 20000: errs.append('%s runway length %s' % (code, rw[0]))
            for e in rw[3]:
                if e[1] is not None and not (1 <= e[1] <= 360): errs.append('%s %s heading %s' % (code, e[0], e[1]))
                for v in e[5:9]:
                    if v is not None and not (500 <= v <= 20000): errs.append('%s %s declared distance %s' % (code, e[0], v))
        if len(errs) > 40: break
    return errs

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--nasr', required=True); ap.add_argument('--oa', required=True)
    ap.add_argument('--eff', required=True); ap.add_argument('--oa-date', required=True)
    ap.add_argument('--out', required=True); ap.add_argument('--no-check', action='store_true')
    o = ap.parse_args()
    eff = dt.date.fromisoformat(o.eff)
    if airac.cycle_start(eff) != eff: sys.exit('not an AIRAC effective date: %s' % eff)
    db = build(o.nasr, o.oa, eff, o.oa_date)
    errs = [] if o.no_check else check(db)
    if errs:
        print('CHECK FAILED:\n  ' + '\n  '.join(errs)); sys.exit(1)
    s = json.dumps(db, separators=(',', ':'), ensure_ascii=False)
    with open(o.out, 'w', encoding='utf-8') as fh: fh.write(s)
    print(db['meta']['cycle'], db['meta']['counts'], '%d KB' % (len(s) // 1024))
