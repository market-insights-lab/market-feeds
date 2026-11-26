"""Daily harvester: piezo-relevant EU tenders (TED API) and patents (Patentscope RSS).
Keeps everything ever found in data/*.json and rewrites feeds/*.xml (RSS 2.0) for a research tool.
Standard library only."""
import json, os, re, html, time, urllib.request, datetime as dt
from pathlib import Path
from email.utils import format_datetime, parsedate_to_datetime
from xml.sax.saxutils import escape as e

ROOT = Path(__file__).parent
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
UA = {"User-Agent": "Mozilla/5.0 (feed harvester)", "Content-Type": "application/json"}
TODAY = dt.date.today()
# Applicant names are kept out of the public repo: set them as the WATCHLIST and COMPETITORS secrets (comma-separated).
env_list = lambda k: [x.strip().upper() for x in os.environ.get(k, "").split(",") if x.strip()]
OWN = env_list("WATCHLIST")
COMPETITORS = env_list("COMPETITORS") + [c.upper() for c in CFG["patents"].get("competitors", [])]

def load(name):
    p = ROOT / "data" / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

def save(name, obj):
    (ROOT / "data" / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")

def first(v):
    if isinstance(v, dict): return first(v.get("eng") or next(iter(v.values()), ""))
    if isinstance(v, list): return first(v[0]) if v else ""
    return "" if v is None else str(v)

# ---------------- Tenders (EU TED) ----------------
COMP = r"piezo|hydrophon|hydrofon|transduc|transducteur|wandler|przetwornik|traductor|trasduttor|sonda ultra|ultrasound probe|ultraschallsonde|głowic|sonar dom|sonardom|phased array|defektoskop|ultradźwiękow|ultrasonic test|zerstörungsfrei|nanopositi|hexapod|piezoaktor|actuator"
SYS = r"sonar|multibeam|fächerecholot|echolot|ecosonda|subacv|unterwasser|underwater|podwodn|povandenin|ROV\b|AUV|hidrograf|hydrograph|litotri|lithotri|HIFU|focaliz|focused ultrasound|histotrip|shock ?wave|stoßwelle|cohlear|coclear|cochle|implant(e|ul)? auditiv|bone conduction|conducción ósea|ultrahang|ultrazvuk|ultrasonograf|ecógraf|ecograf|ultraschallger|ultrason|ultrasound"
EXCL = r"consumable|fungible|consumibil|kit |service|serwis|mantenimiento|maintenance|wartung|construction|budow|reparaci|repair|insurance|termowizyj|natiivikuva|röntgen|x-ray"

def ted_search(query, page):
    body = json.dumps({"query": query, "limit": 250, "page": page,
        "fields": ["publication-number", "notice-title", "buyer-name", "publication-date", "deadline-receipt-tender-date-lot"]}).encode()
    req = urllib.request.Request("https://api.ted.europa.eu/v3/notices/search", data=body, headers=UA)
    return json.load(urllib.request.urlopen(req, timeout=60))

def segment(text):
    if re.search(r"sonar|hydro|underwater|unterwasser|subacv|podwodn|ROV|AUV|multibeam|echolot|naval|marine", text, re.I): return "Aerospace & Defense"
    if re.search(r"litotri|lithotri|HIFU|focaliz|focused|histotri|shock|cohlear|coclear|cochle|auditiv|ultrahang|ultrazvuk|ecógraf|ecograf|ultrasonograf|ultraschallger|medical|hospital|ultrasound", text, re.I): return "Medical Technology"
    if re.search(r"laborator|research|nanopositi|hexapod|thin film", text, re.I): return "Life Sciences Technology"
    return "Industrial Manufacturing & Measurement"

def harvest_tenders():
    store = load("tenders.json")
    days = CFG["tenders"]["lookback_days_daily"] if store else CFG["tenders"]["lookback_days_first_run"]
    since = (TODAY - dt.timedelta(days=days)).strftime("%Y%m%d")
    new = 0
    for term in CFG["tenders"]["search_terms"]:
        for page in range(1, 6):
            try: d = ted_search(f"FT~({term}) AND publication-date>={since}", page)
            except Exception as ex: print("TED skip", term, ex); break
            for n in d.get("notices", []):
                title = first(n.get("notice-title"))
                m = re.match(r"^(.+?)\s+–\s+(.+?)\s+–\s+(.*)$", title)
                country, cat, name = m.groups() if m else ("", "", title)
                text = name + " " + cat
                if re.search(EXCL, text, re.I) and not re.search(COMP, text, re.I): continue
                if re.search(COMP, text, re.I): rel, why = "High", "Component level: buyer needs piezo transducers, probes or actuators – possible direct or partner bid"
                elif re.search(SYS, text, re.I): rel, why = "Medium", "System level: equipment built around piezo transducers – demand signal for OEM customers"
                else: continue
                key = (name.lower()[:70] + "|" + first(n.get("buyer-name")).lower()[:40])
                if any(v.get("dedupe") == key for v in store.values()) and n["publication-number"] not in store: continue
                pn = n["publication-number"]
                if pn not in store: new += 1
                store[pn] = dict(id=pn, date=n["publication-date"][:10], country=country, category=cat, title=name.strip(),
                    buyer=first(n.get("buyer-name")), deadline=first(n.get("deadline-receipt-tender-date-lot"))[:10],
                    relevance=rel, why=why, segment=segment(text), dedupe=key, link=f"https://ted.europa.eu/en/notice/-/detail/{pn}")
            if len(d.get("notices", [])) < 250: break
            time.sleep(0.5)
    save("tenders.json", store)
    print(f"Tenders: {new} new, {len(store)} total")
    return store

# ---------------- Patents (Patentscope RSS) ----------------
def score_patent(p):
    apps = p["applicant"].upper(); t = (p["title"] + " " + p["abstract"]).lower(); s = 0; why = []
    if any(c and c in apps for c in COMPETITORS): s += 3; why.append("filed by a competitor")
    if any(c and c in apps for c in OWN): s += 3; why.append("watch-list applicant")
    if re.search(r"piezo(electric)?[ -]?(ceramic|stack|bender|bimorph|element|disc|disk|plate|multilayer|actuator|crystal|transducer|film)|lead-free|knn|pmn-pt|single crystal", t): s += 2; why.append("about the piezo element/material itself")
    if re.search(r"medical|implant|catheter|ultrasound|histotripsy|focused|semiconductor|wafer|lithograph|mass flow|dispens|microfluid|sonar|hydrophone", t): s += 1; why.append("target market")
    y = int(p["date"][:4]); s += 2 if y >= TODAY.year - 2 else 1 if y >= TODAY.year - 5 else -1 if y < TODAY.year - 11 else 0
    if re.search(r"fuel|injector|engine|guitar|musical", t): s -= 2
    rel = "High" if s >= 5 else "Medium" if s >= 3 else "Low"
    return rel, ("; ".join(why) or "general piezo prior art").capitalize()

def harvest_patents():
    store = load("patents.json"); new = 0
    for f in CFG["patents"]["rss_feeds"]:
        try:
            xml = urllib.request.urlopen(urllib.request.Request(f["url"], headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read().decode("utf-8", "replace")
        except Exception as ex: print("Patent feed skip", f["name"], ex); continue
        for it in re.findall(r"<item>(.*?)</item>", xml, re.S):
            g = lambda tag: [html.unescape(re.sub(r"<[^>]+>", " ", x)).strip() for x in re.findall(rf"<{tag}>(.*?)</{tag}>", it, re.S)]
            link = (g("link") or [""])[0]; pid = (g("guid") or [link.split("docId=")[-1]])[0]
            if not pid or pid in store: continue
            p = dict(id=pid, title=(g("title") or ["(no title)"])[0], link=link,
                     abstract=re.sub(r"\s+", " ", (g("description") or [""])[0]),
                     date=parsedate_to_datetime(g("pubDate")[0]).date().isoformat() if g("pubDate") else TODAY.isoformat(),
                     applicant="; ".join(dict.fromkeys(c for c in g("dc:creator") if re.search(r"[A-Za-z]", c))), feed=f["name"])
            p["relevance"], p["why"] = score_patent(p)
            store[pid] = p; new += 1
    save("patents.json", store)
    print(f"Patents: {new} new, {len(store)} total")
    return store

# ---------------- RSS output ----------------
def write_rss(fn, title, desc, items):
    out = []
    for it in sorted(items, key=lambda x: x["date"], reverse=True)[:1000]:
        d = format_datetime(dt.datetime.fromisoformat(it["date"]).replace(hour=8, tzinfo=dt.timezone.utc), usegmt=True)
        out.append(f'<item><title>{e(it["t"])}</title><link>{e(it["link"])}</link><description>{e(it["d"])}</description>'
                   f'<pubDate>{d}</pubDate><guid isPermaLink="false">{e(it["id"])}</guid>'
                   + "".join(f"<category>{e(c)}</category>" for c in it["cats"]) + "</item>")
    now = format_datetime(dt.datetime.now(dt.timezone.utc), usegmt=True)
    (ROOT / "feeds" / fn).write_text('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
        f"<title>{e(title)}</title><link>https://github.com/</link><description>{e(desc)}</description><language>en</language><lastBuildDate>{now}</lastBuildDate>\n"
        + "\n".join(out) + "\n</channel></rss>\n", encoding="utf-8")

def main():
    T = harvest_tenders(); P = harvest_patents()
    write_rss("tenders.xml", "Piezo and ultrasound – public tenders (EU TED)",
        "EU tenders naming piezo-based products. High = component level, Medium = system level. Updated daily.",
        [dict(id="TED-" + t["id"], date=t["date"], link=t["link"],
              t=f'Tender – {t["country"]}, {t["category"]}: {t["title"][:200]}',
              d=f'{t["country"]} – {t["category"]}. Buyer: {t["buyer"]}. ' + (f'Deadline: {t["deadline"]}. ' if t["deadline"] else "") + f'Segment: {t["segment"]}. Relevance: {t["relevance"]} – {t["why"]}.',
              cats=["Tenders", t["segment"], "Relevance: " + t["relevance"]]) for t in T.values()])
    write_rss("patents.xml", "Piezo technology – patents (WIPO Patentscope)",
        "Patents rated High or Medium relevance. Updated daily.",
        [dict(id=p["id"], date=p["date"], link=p["link"],
              t=f'{p["title"].capitalize() if p["title"].isupper() else p["title"]} ({p["id"]})',
              d=f'{p["abstract"]}\n\nApplicant: {p["applicant"] or "n/a"} · Publication: {p["id"]} · Relevance: {p["relevance"]} – {p["why"]}',
              cats=["Patents", "Relevance: " + p["relevance"]]) for p in P.values() if p["relevance"] != "Low"])

if __name__ == "__main__":
    main()
