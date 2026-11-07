"""AIRAC / FAA NASR 28-day cycle dates."""
import datetime as dt

REF = dt.date(2020, 1, 2)          # AIRAC 2001 effective date
STEP = dt.timedelta(days=28)

def cycle_start(day):
    """Effective date of the cycle in force on `day`."""
    k = (day - REF).days // 28
    return REF + k * STEP

def cycle_id(eff):
    """'2611' style identifier for the cycle effective on `eff`."""
    k = (eff - REF).days // 28
    first = k
    while (REF + (first - 1) * STEP).year == eff.year:
        first -= 1
    return '%02d%02d' % (eff.year % 100, k - first + 1)

def nasr_csv_url(eff, group='APT'):
    return 'https://nfdc.faa.gov/webContent/28DaySub/extra/%s_%s_CSV.zip' % (eff.strftime('%d_%b_%Y'), group)

if __name__ == '__main__':
    import sys
    d = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else dt.date.today()
    e = cycle_start(d)
    print(cycle_id(e), e, e + STEP, nasr_csv_url(e))
