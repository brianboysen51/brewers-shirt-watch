"""Restock watcher: Women's Brewers cream 2026 World Series Champions Parade tee, sizes S/M.

Fetches each seller page, reads per-size stock from the page's embedded JSON
(schema.org offers + any window.__STATE__ blobs), and pushes an urgent ntfy alert
when a watched size flips to in stock. State lives in state.json so each restock
alerts once. Stdlib only so it runs on a bare GitHub Actions runner.

  python3 check.py            # normal run
  python3 check.py --test     # send a test push and exit
  python3 check.py --debug    # also save fetched pages to debug/
"""
import json, os, re, sys, time, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).parent
STATE = ROOT / "state.json"
WANT = ("S", "M")
BLIND_AFTER = 6  # consecutive failed checks before a "watcher is blind" notice

# MLB Shop / Fanatics / Lids (one shared Fanatics stock pool) return Akamai 403 to any
# scripted request, from a UK home IP and from GitHub's US runners alike, so they are
# not watched here.
SITES = {
    "Rally House":"https://www.rallyhouse.com/Brewers-Womens-Cream-2026-World-Series-Champions-Parade-Locker-Room-Short-Sleeve-T-Shirt-9589313",
}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
SIZE_WORDS = {"S": "S", "SM": "S", "SMALL": "S", "M": "M", "MD": "M", "MED": "M", "MEDIUM": "M",
              "XS": "XS", "L": "L", "LG": "L", "LARGE": "L", "XL": "XL", "2XL": "2XL", "XXL": "2XL", "3XL": "3XL"}
SIZE_KEYS = ("size", "sizeName", "sizeLabel", "displaySize", "label", "displayValue", "value", "name", "sku")
STOCK_TRUE = ("available", "isAvailable", "inStock", "isInStock", "purchasable", "isPurchasable")
STOCK_FALSE = ("soldOut", "isSoldOut", "outOfStock", "isOutOfStock")
STOCK_TEXT = ("availability", "inventoryStatus", "stockStatus", "status")


def ntfy(title, body, priority="default", tags="", click=None):
    topic = os.environ.get("NTFY_TOPIC")
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
    return found


def main():
    if "--test" in sys.argv:
        ntfy("TEST: Brewers parade tee watcher", "Test push. A real alert means S or M is in stock: buy immediately.",
             priority="urgent", tags="rotating_light,shirt", click=SITES["Rally House"])
        return
    debug = "--debug" in sys.argv
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    for site, url in SITES.items():
        st = state.setdefault(site, {"fails": 0})
        try:
            html = fetch(url)
            if debug:
                (ROOT / "debug").mkdir(exist_ok=True)
                (ROOT / "debug" / f"{site.replace(' ', '_')}.html").write_text(html)
            sizes = sizes_in(html)
            if not any(s in sizes for s in WANT):
                raise ValueError(f"no S/M stock data found in page (sizes seen: {sizes or 'none'})")
        except Exception as e:
            err = f"{type(e).__name__}: {e}"[:200]
            st["fails"] += 1
            st["error"] = err
            print(f"{site}: FAILED ({st['fails']}x) {err}")
            if st["fails"] == BLIND_AFTER:
                ntfy(f"Shirt watcher blind on {site}", f"{BLIND_AFTER} checks in a row failed: {err}",
                     tags="warning", click=url)
            continue
        if st["fails"] >= BLIND_AFTER:
            ntfy(f"Shirt watcher recovered on {site}", "Checks are working again.", priority="low", tags="white_check_mark")
        st["fails"], st["error"] = 0, None
        print(f"{site}: " + ", ".join(f"{s}={'IN' if v else 'out'}" for s, v in sorted(sizes.items())))
        newly = [s for s in WANT if sizes.get(s) and not st.get(s)]
        for s in WANT:
            if s in sizes:
                st[s] = sizes[s]
        if newly:
            which = " and ".join(newly)
            ntfy(f"BUY NOW: Brewers parade tee size {which} back at {site}",
                 f"Women's cream 2026 WS Champions Parade tee, size {which} is IN STOCK at {site}. "
                 "It may sell out within minutes. Tap to open and check out now.",
                 priority="urgent", tags="rotating_light,shirt", click=url)
    state["last_run_day"] = time.strftime("%Y-%m-%d")  # one commit a day keeps the scheduled workflow alive
    STATE.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
