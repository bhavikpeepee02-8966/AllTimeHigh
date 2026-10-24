import json, os, re, sys, time, urllib.request, urllib.parse

IDX = {
    'n50': ['^NSEI', 'NIFTY50.NS'],
    'sx': ['^BSESN'],
    'vx': ['^INDIAVIX'],
    'gf': ['^NIFTYGIFT', 'GIFTNIFTY.NS', 'NIFTYGIFT.NS'],
    'sp5': ['^GSPC'],
    'nq': ['^IXIC'],
    'dj': ['^DJI'],
    # સોના-ચાંદીનો ATH: ભારતીય ભાવ સાથે ચાલતા ETF પરથી
    'gd': ['GOLDBEES.NS'],
    'sv': ['SILVERBEES.NS'],
    'br': ['BZ=F'],
    'fx': ['INR=X'],
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
    # છેલ્લા દૈનિક ક્લોઝ/ભાવને જ આજનો ભાવ ગણો (meta ભાવ ક્યારેક બીજા કોન્ટ્રાક્ટનો હોય છે)
    cur = last or (r.get('meta') or {}).get('regularMarketPrice')
    if cur > hh:
        hh = cur
    if cur > hc:
        hc = cur
    sp = [round(x[1], 2) for x in rows[-250:]]
    return {'cur': cur, 'prev': prev, 'hh': hh, 'hc': hc, 'hhd': hhd, 'hcd': hcd, 'sp': sp}


def page_text(url):
    req = urllib.request.Request(url, headers=dict(UA, **{'Accept-Language': 'en-IN,en;q=0.9'}))
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode('utf-8', 'ignore')
    html = re.sub(r'(?is)<(script|style).*?</\1>', ' ', html)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html))


def num(x):
    return int(x.replace(',', ''))


def first_ok(urls, pat):
    for u in urls:
        try:
            t = page_text(u)
            x = re.search(pat, t)
            if x:
                dt = re.search(r'Updated on\s*(\d{1,2} \w+,? \d{4})', t)
                return num(x.group(1)), (dt.group(1) if dt else ''), u
        except Exception as e:
            print('fail', u, e)
    return None


def fetch_metals():
    # ભુજનો ભાવ રાજકોટ મુજબ ચાલે છે, એટલે પહેલાં રાજકોટ, ન મળે તો ભુજ
    m = {}
    g = first_ok(['https://www.bankbazaar.com/gold-rate-rajkot.html',
                  'https://www.bankbazaar.com/gold-rate-bhuj.html'],
                 r'24 Carat Gold Rate in \w+.*?10 grams?\s*\u20b9\s*([\d,]+)')
    if g:
        m['gold'], m['gold_date'], m['gold_src'] = g
    sv = first_ok(['https://www.bankbazaar.com/silver-rate-rajkot.html',
                   'https://www.bankbazaar.com/silver-rate-bhuj.html'],
                  r'1 kg\s*\u20b9\s*([\d,]+)')
    if sv:
        m['silver'], m['silver_date'], m['silver_src'] = sv
    print('metals', m)
    return m


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
    oldm = {}
    if os.path.exists('data.json'):
        try:
            oldm = json.load(open('data.json')).get('m', {})
        except Exception:
            pass
    m = dict(oldm)
    m.update(fetch_metals())
    json.dump({'t': int(time.time() * 1000), 'd': d, 'm': m}, open('data.json', 'w'))


main()
