#!/usr/bin/env python3
"""JRG's House of IPs safety checker. Standard library only, no secrets.
quick mode (every run): pages 200 on apex + www, maintenance banner, content guard, SSL validity/expiry,
  security headers, HTTP->HTTPS redirect, Google Safe Browsing (keyless transparency-report lookup).
full mode (once a day): quick + every outbound link, Spotify embed and external image (broken / hijacked / parked).
Exit code 1 on any failure; writes a Markdown summary to $GITHUB_STEP_SUMMARY."""
import os, re, ssl, sys, json, socket, time, datetime, urllib.request, urllib.parse, urllib.error, html
from concurrent.futures import ThreadPoolExecutor

HOSTS = ["jrghouseofip.com", "www.jrghouseofip.com"]
BASE = "https://jrghouseofip.com"
REQUIRED = ["/", "/music/", "/publishing/", "/audiobooks/", "/music/neon-hallows/violence/"]
BANNED = ["Summeer Fox", "James R. Gibson", "houseofips.com", "jrg@houseofips.com"]
BANNER = "This site is under maintenance while we continue finishing it."
# Language rollout (Oct 18, 2026): /es/ /fr/ ... pages carry the translated banner (same strings as the site build).
BANNERS = [BANNER] + ['Este sitio está en mantenimiento mientras terminamos de completarlo. Gracias por tu paciencia.', 'Ce site est en maintenance pendant que nous finissons de le compléter. Merci de votre patience.', 'Este site está em manutenção enquanto terminamos de finalizá-lo. Obrigado pela paciência.', 'Diese Website wird gewartet, während wir sie fertigstellen. Danke für Ihre Geduld.', '本网站正在维护中，我们仍在继续完善。感谢您的耐心等待。', '現在、サイトの完成に向けてメンテナンス中です。今しばらくお待ちください。', '사이트를 마무리하는 동안 유지보수 중입니다. 양해해 주셔서 감사합니다.', 'Trang web đang được bảo trì trong khi chúng tôi tiếp tục hoàn thiện. Cảm ơn bạn đã kiên nhẫn.', 'हम इस साइट को पूरा करने पर काम कर रहे हैं, इसलिए यह अभी रखरखाव में है। आपके धैर्य के लिए धन्यवाद।']
def has_banner(body):
    import html as _h
    t = _h.unescape(body)
    return any(b in t for b in BANNERS)
SEC_HEADERS = ["content-security-policy", "strict-transport-security", "x-content-type-options",
               "x-frame-options", "referrer-policy"]
SSL_MIN_DAYS = 14
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36 JRG-safety-check"
SKIP_LINK = re.compile(r"^https://(www\.facebook\.com/sharer|x\.com/intent|fonts\.googleapis\.com|fonts\.gstatic\.com)|^https?://(www\.)?jrghouseofip\.com")
PARKED = re.compile(r"domain (is|may be) for sale|buy this domain|this domain is parked|parked free|domain parking|hugedomains|sedo\.com/search", re.I)
MODE = (sys.argv[1] if len(sys.argv) > 1 else "quick").lower()

fails, warns, oks = [], [], []
def fail(m): fails.append(m)
def warn(m): warns.append(m)
def ok(m): oks.append(m)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None

def fetch(url, method="GET", follow=True, timeout=15, maxbytes=3_000_000, tries=2):
    """-> (status, final_url, headers(dict lower), body str, error)"""
    last = None
    for i in range(tries):
        try:
            op = urllib.request.build_opener() if follow else urllib.request.build_opener(NoRedirect)
            req = urllib.request.Request(url, method=method, headers={"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.8"})
            with op.open(req, timeout=timeout) as r:
                body = r.read(maxbytes).decode("utf-8", "replace") if method == "GET" else ""
                return r.status, r.geturl(), {k.lower(): v for k, v in r.headers.items()}, body, None
        except urllib.error.HTTPError as e:
            try: body = e.read(200_000).decode("utf-8", "replace")
            except Exception: body = ""
            res = (e.code, e.geturl() or url, {k.lower(): v for k, v in (e.headers or {}).items()}, body, None)
            if e.code < 500 and e.code != 429: return res
            last = res
        except Exception as e:
            last = (0, url, {}, "", f"{type(e).__name__}: {e}")
        time.sleep(1.5)
    return last

# ---------- pages ----------
def sitemap_paths():
    s, _, _, body, err = fetch(BASE + "/sitemap.xml")
    if s != 200:
        fail(f"sitemap.xml returned {s or err}"); return []
    paths = [urllib.parse.urlparse(u).path or "/" for u in re.findall(r"<loc>([^<]+)</loc>", body)]
    ok(f"sitemap.xml lists {len(paths)} pages")
    return paths

PAGES = {}
def check_page(host, path):
    url = f"https://{host}{path}"
    s, final, h, body, err = fetch(url)
    return host, path, url, s, final, h, body, err

def pages_check():
    paths = sitemap_paths()
    targets = [(HOSTS[0], p) for p in dict.fromkeys(REQUIRED + paths)] + [(HOSTS[1], p) for p in REQUIRED]
    with ThreadPoolExecutor(12) as ex:
        results = list(ex.map(lambda t: check_page(*t), targets))
    bad = 0
    for host, path, url, s, final, h, body, err in results:
        if s != 200:
            fail(f"{url} returned {s or err}"); bad += 1; continue
        if urllib.parse.urlparse(final).hostname not in HOSTS:
            fail(f"{url} redirected off-site to {final}"); bad += 1; continue
        if not has_banner(body):
            fail(f"Maintenance banner missing on {url}"); bad += 1
        low = body.lower()
        hits = [b for b in BANNED if b.lower() in low]
        if hits:
            fail(f"Content guard: {url} contains {', '.join(repr(x) for x in hits)}"); bad += 1
        if host == HOSTS[0]: PAGES[path] = body
    req_ok = all(any(r[0] == hst and r[1] == p and r[3] == 200 for r in results) for hst in HOSTS for p in REQUIRED)
    if req_ok: ok("Home, /music/, /publishing/, /audiobooks/ and release page return 200 on apex and www")
    if not bad: ok(f"All {len(results)} page checks passed (200, banner present, content guard clean)")
    # 404 page: real 404 status + banner
    s, _, _, body, err = fetch(BASE + "/safety-check-does-not-exist/", tries=1)
    if s != 404: fail(f"Missing page returned {s or err}, expected 404")
    elif not has_banner(body): fail("Maintenance banner missing on 404 page")
    else: ok("404 page returns 404 with banner")

# ---------- SSL ----------
def ssl_check(host):
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ss:
                cert = ss.getpeercert()
        exp = datetime.datetime.fromtimestamp(ssl.cert_time_to_seconds(cert["notAfter"]), datetime.timezone.utc)
        days = (exp - datetime.datetime.now(datetime.timezone.utc)).days
        if days < SSL_MIN_DAYS: fail(f"SSL certificate for {host} expires in {days} days ({exp:%Y-%m-%d})")
        else: ok(f"SSL valid for {host}, {days} days left (expires {exp:%Y-%m-%d})")
    except Exception as e:
        fail(f"SSL check failed for {host}: {type(e).__name__}: {e}")

# ---------- headers / redirect ----------
def headers_check(host):
    s, _, h, _, err = fetch(f"https://{host}/", method="GET")
    if s != 200: return  # reported by pages check
    missing = [x for x in SEC_HEADERS if x not in h]
    if missing: fail(f"{host} missing security headers: {', '.join(missing)}")
    else: ok(f"{host} sends CSP, HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy")
    csp = h.get("content-security-policy", "")
    if csp and "open.spotify.com" not in csp: fail(f"{host} CSP no longer allows Spotify embeds")
    s, final, h2, _, err = fetch(f"http://{host}/", follow=False, tries=1)
    loc = h2.get("location", "")
    if s in (301, 302, 307, 308) and loc.startswith("https://"): ok(f"http://{host} redirects to HTTPS")
    else: fail(f"http://{host} does not redirect to HTTPS (status {s or err}, location {loc!r})")

# ---------- Safe Browsing (keyless transparency report) ----------
SB_TEXT = {1: "no unsafe content found", 2: "UNSAFE", 3: "SOME PAGES UNSAFE", 4: "no site-level verdict (check specific URLs)",
           5: "hosts uncommon downloads", 6: "no data yet (normal for a new site)"}
def safebrowsing(host):
    url = "https://transparencyreport.google.com/transparencyreport/api/v3/safebrowsing/status?site=" + urllib.parse.quote(host)
    s, _, _, body, err = fetch(url)
    try:
        data = json.loads(body.split("\n", 1)[1].strip()) if body.startswith(")]}'") else json.loads(body)
        row = data[0]; code = row[1]; flags = row[2:7]
    except Exception:
        warn(f"Safe Browsing lookup for {host} unavailable (status {s or err}); skipped this run"); return
    if code in (2, 3, 5) or any(f is True for f in flags):
        fail(f"Google Safe Browsing flags {host}: {SB_TEXT.get(code, code)} (flags {flags})")
    else: ok(f"Google Safe Browsing for {host}: {SB_TEXT.get(code, code)}")

# ---------- outbound links (daily) ----------
def regdom(host):
    parts = (host or "").lower().split(".")
    if len(parts) >= 3 and parts[-2] in ("com", "co", "org", "net") and len(parts[-1]) == 2: return ".".join(parts[-3:])
    return ".".join(parts[-2:])

def link_check(item):
    kind, url, where = item
    host = urllib.parse.urlparse(url).hostname or ""
    if kind == "img":
        s, final, h, _, err = fetch(url, method="GET", maxbytes=2048)
        if s == 200 and h.get("content-type", "").startswith("image/"): return ("ok", kind, url, where, "")
        return ("fail", kind, url, where, f"image returned {s or err} {h.get('content-type','')}")
    if host == "open.spotify.com":
        target = url.replace("/embed/", "/")
        s, _, _, _, err = fetch("https://open.spotify.com/oembed?url=" + urllib.parse.quote(target, safe=""))
        if s == 200: return ("ok", kind, url, where, "")
        if s == 429 or s == 0: return ("warn", kind, url, where, f"Spotify unverifiable ({s or err})")
        return ("fail", kind, url, where, f"Spotify item not found (oEmbed {s})")
    if host.endswith("youtube.com") and "/watch" in url:
        s, _, _, _, err = fetch("https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(url, safe=""))
        if s == 200: return ("ok", kind, url, where, "")
        if s in (401, 403): return ("warn", kind, url, where, f"YouTube video exists but embedding/visibility restricted ({s})")
        if s == 429 or s == 0: return ("warn", kind, url, where, f"YouTube unverifiable ({s or err})")
        return ("fail", kind, url, where, f"YouTube video not found (oEmbed {s})")
    s, final, h, body, err = fetch(url)
    fhost = urllib.parse.urlparse(final).hostname or ""
    if s == 0: return ("fail", kind, url, where, f"unreachable: {err}")
    if h.get("cf-mitigated") == "challenge" or (s in (403, 429, 503) and ("Just a moment" in body or "captcha" in body.lower())) \
       or "google.com/sorry" in final or fhost == "consent.youtube.com" or s == 429:
        return ("warn", kind, url, where, f"bot protection, unverifiable from GitHub ({s})")
    if regdom(fhost) != regdom(host):
        return ("fail", kind, url, where, f"POSSIBLE HIJACK: redirects to another domain {final}")
    if s in (404, 410) or s >= 500 or s == 400:
        return ("fail", kind, url, where, f"broken link ({s})")
    if s != 200:
        return ("warn", kind, url, where, f"returned {s}")
    if PARKED.search(body[:200_000]):
        return ("fail", kind, url, where, "POSSIBLE HIJACK: page looks like a parked / for-sale domain")
    return ("ok", kind, url, where, "")

def outbound_check():
    items = {}
    for path, body in PAGES.items():
        for m in re.finditer(r'<a\b[^>]*href="(https?://[^"]+)"', body):
            u = html.unescape(m.group(1))
            if not SKIP_LINK.search(u): items.setdefault(("link", u), path)
        for m in re.finditer(r'<iframe\b[^>]*src="(https?://[^"]+)"', body):
            items.setdefault(("embed", html.unescape(m.group(1))), path)
        for m in re.finditer(r'<img\b[^>]*src="(https?://[^"]+)"', body):
            u = html.unescape(m.group(1))
            if not SKIP_LINK.search(u): items.setdefault(("img", u), path)
    work = [(k, u, p) for (k, u), p in items.items()]
    with ThreadPoolExecutor(16) as ex:
        res = list(ex.map(link_check, work))
    n = {"ok": 0, "warn": 0, "fail": 0}
    for st, kind, url, where, msg in res:
        n[st] += 1
        if st == "fail": fail(f"Outbound {kind} {url} (on {where}): {msg}")
    unver = [r for r in res if r[0] == "warn"]
    if unver:
        by = {}
        for _, _, url, _, msg in unver: by.setdefault(f"{urllib.parse.urlparse(url).hostname}: {msg}", []).append(url)
        for k, v in by.items(): warn(f"{len(v)} outbound link(s) skipped, {k}")
    ok(f"Outbound check: {len(res)} links/embeds/images, {n['ok']} OK, {n['warn']} unverifiable, {n['fail']} failed")

def main():
    t0 = time.time()
    pages_check()
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(ssl_check, HOSTS)); list(ex.map(headers_check, HOSTS)); list(ex.map(safebrowsing, HOSTS))
    if MODE == "full": outbound_check()
    dur = time.time() - t0
    status = "FAILED" if fails else "PASSED"
    lines = [f"## JRG's House of IPs safety check: {status}",
             f"Mode: **{MODE}** · {datetime.datetime.now(datetime.timezone.utc):%Y-%m-%d %H:%M UTC} · {dur:.1f}s", ""]
    if fails: lines += ["### ❌ Failures"] + [f"- {x}" for x in fails] + [""]
    if warns: lines += ["### ⚠️ Warnings (not failures)"] + [f"- {x}" for x in warns] + [""]
    lines += ["### ✅ Passed"] + [f"- {x}" for x in oks]
    out = "\n".join(lines)
    print(out)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f: f.write(out + "\n")
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
