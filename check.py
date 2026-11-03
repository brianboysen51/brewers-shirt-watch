"""Restock watcher for Brewers merch. Currently: the Gold/Navy (yellow crown) New Era
2026 World Series Side Patch 9TWENTY adjustable hat. (Previously the women's cream
Parade tee in S/M, bought 2026-11-03.)

Fetches each seller page, reads per-size stock from the page's embedded JSON
(schema.org offers, window.__STATE__ blobs, Fanatics' inline size records), and pushes
an urgent ntfy alert when a watched size flips to in stock. State lives in state.json
so each restock alerts once.

MLB Shop sits behind Akamai, which 403s plain HTTP clients, so it is loaded in real
headed Google Chrome (Patchright, run under xvfb-run) with a persistent profile, the
same way delta-watch drives delta.com. Bundled Chromium gets denied far more often than
Chrome. Chrome is the .deb unpacked (no sudo) under ~/.local/opt/chrome-deb. A profile
Akamai has flagged stays denied, so a denied run wipes the profile and retries cold
(homepage first, which sets fresh cookies, then the product page).

  python3 check.py            # normal run
  python3 check.py --test     # send a test push and exit
  python3 check.py --debug    # also save fetched pages to debug/
"""
import json, os, re, shutil, sys, time, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).parent
STATE = ROOT / "state.json"
BLIND_AFTER = 6  # consecutive failed checks before a "watcher is blind" notice

PROFILE = ROOT / "profile"
CHROME = Path.home() / ".local/opt/chrome-deb/root/opt/google/chrome/chrome"
ITEM = "Brewers Gold/Navy World Series Side Patch 9TWENTY hat"
# site -> (url, how to fetch, sizes to watch). On Fanatics pages, watch {itemId: label}
# instead of bare sizes: a product page also embeds its other colors' size records (the
# Gold/Navy page carries the in-stock Navy OSFM, item 214313435), so matching on size
# alone gave a false alert on 2026-11-03. MLB Shop, Fanatics.com and Lids share one
# Fanatics stock pool, so watching MLB Shop covers all three. The yellow hat is its own
# listing (the navy page hides out-of-stock color swatches). New Era and Rally House
# don't sell a gold 9TWENTY of this hat (checked 2026-11-03).
SITES = {
    "MLB Shop": ("https://www.mlbshop.com/milwaukee-brewers/mens-milwaukee-brewers-new-era-gold/navy-2026-world-series-side-patch-9twenty-adjustable-hat/t-36994327+p-247750670383987+z-9-95215330", "browser", {"214313434": "OSFM"}),
}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
SIZE_WORDS = {"S": "S", "SM": "S", "SMALL": "S", "M": "M", "MD": "M", "MED": "M", "MEDIUM": "M",
              "XS": "XS", "L": "L", "LG": "L", "LARGE": "L", "XL": "XL", "2XL": "2XL", "XXL": "2XL", "3XL": "3XL",
              "OSFM": "OSFM", "OSFA": "OSFM", "ONE SIZE": "OSFM"}
SIZE_KEYS = ("size", "sizeName", "sizeLabel", "displaySize", "label", "displayValue", "value", "name", "sku")
STOCK_TRUE = ("available", "isAvailable", "inStock", "isInStock", "purchasable", "isPurchasable")
STOCK_FALSE = ("soldOut", "isSoldOut", "outOfStock", "isOutOfStock")
STOCK_TEXT = ("availability", "inventoryStatus", "stockStatus", "status")


def _env(key):
    env = ROOT / ".env"
    for line in env.read_text().splitlines() if env.exists() else []:
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"')
    return os.environ.get(key)


def ntfy(title, body, priority="default", tags="", click=None):
    topic = _env("NTFY_TOPIC")
    if not topic:
        print("ntfy: no NTFY_TOPIC set;", title, "|", body)
        return
    headers = {"Title": title.encode("ascii", "ignore").decode(), "Priority": priority, "Tags": tags}
    if click:
        headers["Click"] = click
        headers["Actions"] = f"view, Open store, {click}, clear=true"
    req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=body.encode(), method="POST", headers=headers)
    urllib.request.urlopen(req, timeout=15).read()


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


class Denied(RuntimeError):
    pass


def _load(url):
    """One headed Chrome session. A cold profile visits the homepage first: Akamai answers
    it with a 403 whose script sets the cookies the product page then accepts."""
    from patchright.sync_api import sync_playwright
    cold = not PROFILE.exists()
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PROFILE), executable_path=str(CHROME),
                                                   headless=False, no_viewport=True)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            if cold:
                page.goto(re.match(r"https://[^/]+/", url).group(0), wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(7000)
            r = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            if not r or r.status != 200 or "Access Denied" in page.title():
                raise Denied(f"Akamai denied the page ({r.status if r else 'no response'}, {'cold' if cold else 'warm'} profile)")
            page.wait_for_timeout(3000)
            return page.content()
        finally:
            ctx.close()


def fetch_browser(url):
    try:
        return _load(url)
    except Denied:
        if not PROFILE.exists():
            raise
        shutil.rmtree(PROFILE)  # flagged profile; start over cold
        return _load(url)


def json_blobs(html):
    """Every JSON document embedded in the page: ld+json scripts and window.X = {...} assignments."""
    for m in re.finditer(r'<script[^>]*type="application/(?:ld\+)?json"[^>]*>(.*?)</script>', html, re.S):
        try:
            yield json.loads(m.group(1))
        except ValueError:
            pass
    dec = json.JSONDecoder()
    for m in re.finditer(r'window\.__?[A-Za-z_]+__?\s*=\s*', html):
        try:
            yield dec.raw_decode(html, m.end())[0]
        except ValueError:
            pass


def size_of(d):
    for k in SIZE_KEYS:
        v = d.get(k)
        if not isinstance(v, str):
            continue
        v = v.strip().upper()
        if v in SIZE_WORDS:
            return SIZE_WORDS[v]
        if k in ("sku", "name"):  # e.g. "9589313 : 9589313-S" or "Tee - M"
            tail = re.search(r"[-/ ]([0-9]?X*[SML]|XXL|SMALL|MEDIUM|LARGE)$", v)
            if tail and tail.group(1) in SIZE_WORDS:
                return SIZE_WORDS[tail.group(1)]
    return None


def stock_of(d):
    for k in STOCK_TRUE:
        if isinstance(d.get(k), bool):
            return d[k]
    for k in STOCK_FALSE:
        if isinstance(d.get(k), bool):
            return not d[k]
    for k in STOCK_TEXT:
        v = d.get(k)
        if isinstance(v, str):
            v = v.rsplit("/", 1)[-1].replace("_", "").replace(" ", "").lower()
            if v in ("instock", "available", "limitedavailability", "onlineonly", "lowstock"):
                return True
            if v in ("outofstock", "soldout", "unavailable", "discontinued", "notavailable"):
                return False
    return None


def sizes_in(html):
    """{size: in_stock} from any dict in the page that carries both a size and a stock flag."""
    found = {}

    def walk(o):
        if isinstance(o, dict):
            s, st = size_of(o), stock_of(o)
            if s and st is not None:
                found[s] = found.get(s, False) or st  # any in-stock record for a size wins
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for blob in json_blobs(html):
        walk(blob)
    # Fanatics inlines its size records in a script json_blobs can't isolate:
    # {"itemId":"214362650",...,"size":"S","available":false,...}
    for size, avail in re.findall(r'"size":"([0-9A-Z]{1,4})","available":(true|false)', html):
        if size in SIZE_WORDS:
            found[SIZE_WORDS[size]] = found.get(SIZE_WORDS[size], False) or avail == "true"
    return found


def items_in(html, ids):
    """{label: in_stock} for exact Fanatics item ids: {"itemId":"214313434",...,"available":false}"""
    found = {}
    for item, avail in re.findall(r'"itemId":"(\d+)"[^{}]{0,200}?"available":(true|false)', html):
        if item in ids:
            found[ids[item]] = found.get(ids[item], False) or avail == "true"
    return found


def main():
    if "--test" in sys.argv:
        ntfy(f"TEST: {ITEM} watcher", "Test push. A real alert means it is back in stock: buy immediately.",
             priority="urgent", tags="rotating_light,billed_cap", click=SITES["MLB Shop"][0])
        return
    debug = "--debug" in sys.argv
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    for site, (url, how, want) in SITES.items():
        st = state.setdefault(site, {"fails": 0})
        try:
            html = fetch_browser(url) if how == "browser" else fetch(url)
            if debug:
                (ROOT / "debug").mkdir(exist_ok=True)
                (ROOT / "debug" / f"{site.replace(' ', '_')}.html").write_text(html)
            sizes = items_in(html, want) if isinstance(want, dict) else sizes_in(html)
            want = list(want.values()) if isinstance(want, dict) else want
            if not any(s in sizes for s in want):
                raise ValueError(f"no {'/'.join(want)} stock data found in page (sizes seen: {sizes or 'none'})")
        except Exception as e:
            err = f"{type(e).__name__}: {e}"[:200]
            st["fails"] += 1
            st["error"] = err
            print(f"{site}: FAILED ({st['fails']}x) {err}")
            if st["fails"] == BLIND_AFTER:
                ntfy(f"{ITEM} watcher blind on {site}", f"{BLIND_AFTER} checks in a row failed: {err}",
                     tags="warning", click=url)
            continue
        if st["fails"] >= BLIND_AFTER:
            ntfy(f"{ITEM} watcher recovered on {site}", "Checks are working again.", priority="low", tags="white_check_mark")
        st["fails"], st["error"] = 0, None
        print(f"{site}: " + ", ".join(f"{s}={'IN' if v else 'out'}" for s, v in sorted(sizes.items())))
        newly = [s for s in want if sizes.get(s) and not st.get(s)]
        for s in want:
            if s in sizes:
                st[s] = sizes[s]
        if newly:
            which = "" if newly == ["OSFM"] else f" size {' and '.join(newly)}"
            ntfy(f"BUY NOW: yellow Brewers WS hat back at {site}",
                 f"{ITEM}{which} is IN STOCK at {site}. It may sell out within minutes. "
                 "Tap to open and check out now.",
                 priority="urgent", tags="rotating_light,billed_cap", click=url)
    STATE.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
