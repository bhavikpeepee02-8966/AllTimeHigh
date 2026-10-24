import json, os, sys, time, urllib.request, urllib.parse

IDX = {
    'n5': ['^CRSLDX', 'NIFTY500.NS'],
    'md': ['NIFTYMIDCAP150.NS', '^NIFTYMIDCAP150', 'NIFTYMID150.NS'],
    'sm': ['NIFTYSMLCAP250.NS', '^NIFTYSMLCAP250', 'NIFTYSML250.NS'],
}
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36'}


def is_daily(j):
    try:
        ts = j['chart']['result'][0].get('timestamp') or []
        return len(ts) > 50 and (ts[-1] - ts[0]) / (len(ts) - 1) < 5 * 86400
    except Exception:
        return False


def get(sym):
    p2 = int(time.time()) + 86400
    q = urllib.parse.quote(sym)
    paths = ['%s?period1=946684800&period2=%d&interval=1d' % (q, p2),
             '%s?range=max&interval=1d' % q]
    fallback = None
    for path in paths:
        for host in ('query1', 'query2'):
            url = 'https://%s.finance.yahoo.com/v8/finance/chart/%s' % (host, path)
            for _ in range(3):
                try:
                    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                        j = json.load(r)
                    if j.get('chart', {}).get('result'):
                        if is_daily(j):
                            return j
                        print('  not daily data', sym, host)
                        fallback = fallback or j
                        break
                except Exception as e:
                    print('  retry', sym, host, e)
                    time.sleep(3)
    return fallback


def proc(j):
    r = j['chart']['result'][0]
    ts = r.get('timestamp') or []
    q = r['indicators']['quote'][0]
    rows = []  # [day, close, high, ts] - એક દિવસની એક જ લીટી
    for i, t in enumerate(ts):
        c = q['close'][i]
        h = q['high'][i]
        if c is None:
            continue
        day = (t + 19800) // 86400
        if rows and rows[-1][0] == day:
            rows[-1][1] = c
            rows[-1][2] = max(rows[-1][2] or 0, h or 0)
        else:
            rows.append([day, c, h, t])
    hc = hh = 0
    hcd = hhd = None
    for day, c, h, t in rows:
        if c > hc:
            hc, hcd = c, t
        if h is not None and h > hh:
            hh, hhd = h, t
    last = rows[-1][1] if rows else None
    prev = rows[-2][1] if len(rows) > 1 else None
    cur = (r.get('meta') or {}).get('regularMarketPrice') or last
    if cur > hh:
        hh = cur
    if cur > hc:
        hc = cur
    return {'cur': cur, 'prev': prev, 'hh': hh, 'hc': hc, 'hhd': hhd, 'hcd': hcd}


def main():
    old = {}
    if os.path.exists('data.json'):
        try:
            old = json.load(open('data.json')).get('d', {})
        except Exception:
            pass
    d = dict(old)
    ok = 0
    for k, syms in IDX.items():
        best = None
        for s in syms:
            j = get(s)
            if not j:
                continue
            try:
                v = proc(j)
                if not (v['cur'] and v['hh']):
                    continue
                v['daily'] = is_daily(j)
                v['sym'] = s
                print('OK', k, s, v['cur'], 'daily' if v['daily'] else 'NOT-DAILY')
                if v['daily']:
                    best = v
                    break
                best = best or v
            except Exception as e:
                print('  parse fail', s, e)
        if best:
            d[k] = best
            ok += 1
        else:
            print('FAIL', k)
    if ok == 0:
        sys.exit(1)
    json.dump({'t': int(time.time() * 1000), 'd': d}, open('data.json', 'w'))


main()
