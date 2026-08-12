#!/usr/bin/env python3
"""
SchoolOS News — збирач новин (етап 1, без AI).

Джерела описані в sources.json; кожен парсер призначається полем "parser".
Етапи: завантаження -> нормалізація -> шкільний фільтр -> дедуплікація ->
importance_score -> feed.json (останні ~150) + meta.json (статистика).

Стійкість: кожне джерело ізольоване (try/except); недоступне джерело
друкує [WARN] у stderr і пропускається. Скрипт завжди завершується
з формуванням feed.json, навіть якщо працює лише одне джерело.
"""
import html as html_mod
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
NEWS_DIR = os.path.normpath(os.path.join(SCRIPTS_DIR, ".."))
DATA_DIR = os.path.join(NEWS_DIR, "data")
SOURCES_PATH = os.path.join(SCRIPTS_DIR, "sources.json")
FEED_PATH = os.path.join(DATA_DIR, "feed.json")
META_PATH = os.path.join(DATA_DIR, "meta.json")
OWN_PATH = os.path.join(DATA_DIR, "own.json")

UA = "SchoolOS-NewsBot/1.0 (schoolosua.github.io)"
TIMEOUT = 30
MAX_FEED_ITEMS = 150
DESC_LIMIT = 220
DEDUP_TITLE_SIMILARITY = 0.5
DEDUP_MAX_HOURS = 72

STRONG_SCHOOL = [
    r"школ", r"учень", r"учн[іи]в", r"учня", r"школяр", r"першокласн",
    r"вчител", r"учител", r"педагог", r"освітян",
    r"НУШ|нов[оі]й? українськ",
    r"НМТ", r"ЗНО", r"ДПА", r"мультипредметн",
    r"ліцей", r"гімназі", r"канікул", r"підручник", r"інклюзі",
    r"ООП\b", r"особлив[иою]ми? освітніми потребами",
    r"дошкільн", r"омбудсмен",
    r"середньої освіти", r"батьк",
]

# Ядро шкільної тематики: якщо в тексті є заперечний термін (вища освіта тощо),
# новина проходить лише при збігу хоча б одного з цих термінів.
SCHOOL_CORE = [
    r"школ", r"учень", r"учн[іи]в", r"учня", r"школяр", r"першокласн",
    r"вчител", r"учител",
    r"НУШ|нов[оі]й? українськ", r"НМТ", r"ЗНО", r"ДПА",
    r"ліцей", r"гімназі", r"канікул", r"підручник", r"дошкільн",
]

WEAK_SCHOOL = [
    r"освіт", r"навчанн", r"МОН\b|міністерство освіти", r"реформ",
    r"закон", r"безпек", r"урок", r"класн", r"директор", r"навчальн",
]

NEGATIVE_TERMS = [
    r"магістратур", r"аспірантур", r"ЄВІ", r"ЄФВВ", r"студент",
    r"університет", r"вищої освіти", r"ЗВО", r"докторант", r"професійн",
]

CATEGORY_RULES = [
    ("НМТ", r"НМТ|ЗНО|ДПА|мультипредметн"),
    ("НУШ", r"НУШ|нов[оі]й? українськ"),
    ("ШІ", r"штучн|ШІ|AI"),
    ("Інклюзія", r"інклюзі|ООП|особлив[иою]ми? освітніми потребами|ресурсн[ио]й? центр"),
    ("Безпека", r"безпек|безпечн|булінг|укритт"),
    ("Реформи", r"реформ|законопроєкт|наказ|постанов|затвердж|зміни в|зміни до"),
    ("Вчителі", r"вчител|учител|педагог|кваліфікац|сертифікац|зарплат|навантаженн|педпрац"),
    ("Учні", r"учн|школяр|першокласник|випускник|старшокласник"),
]

IMPORTANT_TERMS = [
    r"змін", r"нові правила", r"наказ", r"затвердж", r"важлив", r"конкурс",
    r"реформ", r"безпек", r"обов'язк", r"старт", r"результат",
]


def warn(msg):
    print(f"[WARN] {msg}", file=sys.stderr)


def log(msg):
    print(msg)


def load_sources():
    with open(SOURCES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return [s for s in data["sources"] if s.get("enabled", False)]


def fetch(url, delay):
    time.sleep(delay)
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "uk-UA,uk;q=0.9,ru;q=0.5,en;q=0.3",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
            charset = resp.headers.get_content_charset() or ""
    except Exception as exc:  # noqa: BLE001
        warn(f"не вдалося отримати {url}: {exc}")
        return ""
    for enc in (charset, "utf-8", "cp1251"):
        if not enc:
            continue
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def clean_html(text):
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_mod.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def strip_and_truncate(text, limit=DESC_LIMIT):
    text = clean_html(text)
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def parse_dd_mm_yyyy(text):
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if not m:
        return None
    try:
        return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), tzinfo=timezone.utc)
    except ValueError:
        return None


def iso(dt):
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_rss(raw, src):
    """Стандартний RSS 2.0 (Освіта.ua, НУШ)."""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        warn(f"{src['id']}: не вдалося розпарсити RSS: {exc}")
        return []
    items = []
    now = datetime.now(timezone.utc)
    for item in root.iter("item"):
        def field(name):
            el = item.find(name)
            return el.text.strip() if el is not None and el.text else ""
        title = field("title")
        link = field("link")
        if not title or not link:
            continue
        pub = field("pubDate")
        published = now
        if pub:
            try:
                published = parsedate_to_datetime(pub)
            except (ValueError, TypeError):
                published = now
        desc = strip_and_truncate(field("description"))
        if "The post" in desc:
            desc = desc.split(" The post")[0].strip()
        items.append({
            "title": title,
            "url": link,
            "published_at": iso(published),
            "description": desc,
        })
    return items


def parse_testportal(raw, src):
    """УЦОЯО: https://testportal.gov.ua/news/ — блоки div.catalog-item."""
    items = []
    for block in re.findall(r'<div class="catalog-item[^>]*>(.*?)</div>', raw, re.S):
        m = re.search(r'<a href="(https://testportal\.gov\.ua/[^"]+)"[^>]*rel="bookmark"[^>]*>(.*?)</a>', block, re.S)
        if not m:
            continue
        title = clean_html(m.group(2))
        url = m.group(1)
        if not title or not url:
            continue
        desc = ""
        dp = re.search(r"<p>(.*?)</p>", block, re.S)
        if dp:
            desc = strip_and_truncate(dp.group(1))
        published = None
        tm = re.search(r"<time>(.*?)</time>", block)
        if tm:
            published = parse_dd_mm_yyyy(tm.group(1))
        items.append({
            "title": title,
            "url": url,
            "published_at": iso(published),
            "description": desc,
        })
    return items


def parse_ombudsman(raw, src):
    """Освітній омбудсмен: https://eo.gov.ua/novini — блоки .pld-post-list-inr."""
    items = []
    chunks = re.split(r'<div class="pld-post-list-inr">', raw)
    for chunk in chunks[1:]:
        m = re.search(r'<h2 class="pld-post-title">\s*<a href="([^"]+)">(.*?)</a>', chunk, re.S)
        if not m:
            continue
        title = clean_html(m.group(2))
        url = m.group(1)
        if not title or not url:
            continue
        published = None
        pm = re.search(r'pld-post-meta">(.*?)</div>', chunk, re.S)
        if pm:
            published = parse_dd_mm_yyyy(pm.group(1))
        desc = ""
        pi = re.search(r'pld-post-content-inner">(.*?)</div>', chunk, re.S)
        if pi:
            desc = strip_and_truncate(pi.group(1))
        items.append({
            "title": title,
            "url": url,
            "published_at": iso(published),
            "description": desc,
        })
    return items


EMOJI_RE = re.compile(
    r"[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D\u25A0-\u25FF\u2300-\u23FF]+"
)


def first_meaningful_line(text):
    """Перший змістовний рядок (з літерами/цифрами) — заголовок для Telegram-постів."""
    line = ""
    for ln in text.split("\n"):
        cand = EMOJI_RE.sub(" ", ln).strip(" \t•·–—-|")
        cand = re.sub(r"\s+", " ", cand)
        if len(re.findall(r"[a-zA-Zа-яіїєґ0-9]", cand)) >= 3:
            line = cand
            break
    if not line:
        line = EMOJI_RE.sub(" ", text).strip(" \t•·–—-|")[:80]
    if len(line) > 150:
        cut = re.search(r"[.:;]\s", line[60:])
        if cut:
            line = line[:60 + cut.start() + 1]
    return line.strip()


def parse_telegram(raw, src):
    """МОН: https://t.me/s/MON_Ukraine — прев'ю-сторінка каналу."""
    items = []
    for block in re.split(r'<div class="tgme_widget_message_wrap js-widget_message_wrap">', raw)[1:]:
        tm = re.search(r'data-post="([^"]+)"', block)
        if not tm:
            continue
        post_id = tm.group(1).rstrip("/")
        post_url = f"https://t.me/{post_id}"
        tx = re.search(r'tgme_widget_message_text js-message_text"[^>]*>(.*?)</div>', block, re.S)
        if not tx:
            continue
        text = re.sub(r"<[^>]+>", "\n", tx.group(1))
        text = html_mod.unescape(text)
        text = re.sub(r"[ \t]+", " ", text).strip()
        if not text:
            continue
        title = first_meaningful_line(text)
        mon_url = ""
        mu = re.search(r'https://mon\.gov\.ua/[^"<\s]+', text)
        if mu:
            mon_url = mu.group(0)
        published = None
        tm = re.search(r'<time datetime="([^"]+)"', block)
        if tm:
            try:
                published = datetime.fromisoformat(tm.group(1).replace("Z", "+00:00"))
            except ValueError:
                published = None
        if published is None:
            tv = re.search(r'"t":(\d{10})', block)
            if tv:
                try:
                    published = datetime.fromtimestamp(int(tv.group(1)), tz=timezone.utc)
                except (ValueError, OSError):
                    published = None
        items.append({
            "title": title,
            "url": mon_url or post_url,
            "telegram_url": post_url,
            "published_at": iso(published),
            "description": strip_and_truncate(text),
        })
    return items


PARSERS = {
    "rss": parse_rss,
    "testportal": parse_testportal,
    "ombudsman": parse_ombudsman,
    "telegram": parse_telegram,
}


def find_category(item):
    text = f"{item['title']} {item.get('description', '')}"
    for name, pattern in CATEGORY_RULES:
        if re.search(pattern, text, re.IGNORECASE):
            return name
    return "Школа"


def school_relevant(item):
    text = f"{item['title']} {item.get('description', '')}"
    negative = any(re.search(p, text, re.IGNORECASE) for p in NEGATIVE_TERMS)
    if negative:
        core = any(re.search(p, text, re.IGNORECASE) for p in SCHOOL_CORE)
        return core
    strong = any(re.search(p, text, re.IGNORECASE) for p in STRONG_SCHOOL)
    if strong:
        return True
    weak = sum(1 for p in WEAK_SCHOOL if re.search(p, text, re.IGNORECASE))
    return weak >= 2


def importance_score(item, priority, published):
    score = priority // 2
    if published:
        hours = max(0.0, (datetime.now(timezone.utc) - published).total_seconds() / 3600)
        if hours <= 24:
            score += 25
        elif hours <= 48:
            score += 18
        elif hours <= 72:
            score += 10
        elif hours <= 120:
            score += 4
    text = f"{item['title']} {item.get('description', '')}"
    keyword_hits = sum(1 for p in STRONG_SCHOOL if re.search(p, text, re.IGNORECASE))
    score += min(15, keyword_hits * 5)
    if any(re.search(p, text, re.IGNORECASE) for p in IMPORTANT_TERMS):
        score += 10
    return max(0, min(100, score))


def norm_title_key(title):
    return re.sub(r"[^a-zа-яіїєґ0-9]+", " ", title.lower()).strip()


def title_similar(a, b):
    ta = {t for t in re.findall(r"[a-zа-яіїєґ0-9]+", norm_title_key(a)) if len(t) >= 3}
    tb = {t for t in re.findall(r"[a-zа-яіїєґ0-9]+", norm_title_key(b)) if len(t) >= 3}
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= DEDUP_TITLE_SIMILARITY


def deduplicate(items):
    """1) унікальний URL; 2) схожі заголовки між джерелами -> одна подія."""
    by_url = {}
    merged = 0
    for item in items:
        by_url.setdefault(item["url"], item)
    items = sorted(by_url.values(), key=lambda it: it["_dt"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    keep = []
    for item in items:
        dup = None
        for k in keep:
            if abs((item["_dt"] or item["_now"]) - (k["_dt"] or k["_now"])).total_seconds() <= DEDUP_MAX_HOURS * 3600:
                if title_similar(item["title"], k["title"]):
                    dup = k
                    break
        if dup is None:
            keep.append(item)
        else:
            item.setdefault("sources", [item["source"]])
            dup.setdefault("sources", [dup["source"]])
            if item["priority"] > dup["priority"]:
                item["sources"] = [item["source"]] + dup["sources"]
                keep[keep.index(dup)] = item
            else:
                dup["sources"].append(item["source"])
            merged += 1
    return keep, merged


def main():
    sources = load_sources()
    if not sources:
        warn("sources.json: немає активних джерел")
        sys.exit(1)

    os.makedirs(DATA_DIR, exist_ok=True)
    raw_items = []
    meta_sources = {}
    warnings = []

    for src in sources:
        sid = src["id"]
        delay = src.get("crawl_delay", 2)
        parser_name = src.get("parser") or src["method"]
        parser = PARSERS.get(parser_name)
        if parser is None:
            warn(f"{sid}: невідомий parser '{parser_name}'")
            warnings.append(f"{sid}: parser '{parser_name}' невідомий")
            continue
        try:
            raw = fetch(src["fetch_url"], delay)
            if not raw:
                raise RuntimeError("порожня відповідь")
            parsed = parser(raw, src)
            for it in parsed:
                it["source"] = src["name"]
                it["priority"] = src["priority"]
            log(f"  {sid}: fetched={len(parsed)}")
            meta_sources[sid] = {"status": "ok", "fetched": len(parsed)}
        except Exception as exc:  # noqa: BLE001
            warn(f"{sid}: {exc}")
            meta_sources[sid] = {"status": "error", "error": str(exc)}
            warnings.append(f"{sid}: {exc}")
            continue
        raw_items.extend(parsed)

    now = datetime.now(timezone.utc)
    for it in raw_items:
        it["_dt"] = datetime.fromisoformat(it["published_at"].replace("Z", "+00:00")) if it["published_at"] else None
        it["_now"] = now
        it["category"] = find_category(it)
        it["school_relevant"] = school_relevant(it)

    for sid, meta in meta_sources.items():
        meta.setdefault("after_filter", 0)

    filtered = []
    for it in raw_items:
        src_id = next(s["id"] for s in sources if s["name"] == it["source"])
        if it["school_relevant"]:
            filtered.append(it)
            meta_sources[src_id]["after_filter"] += 1

    for it in filtered:
        it["importance_score"] = importance_score(it, it["priority"], it["_dt"])

    deduped, merged_count = deduplicate(filtered)

    for sid in meta_sources:
        meta_sources[sid]["after_dedup"] = 0
    for it in deduped:
        src_id = next(s["id"] for s in sources if s["name"] == it["source"])
        meta_sources[src_id]["after_dedup"] = meta_sources[src_id].get("after_dedup", 0) + 1

    deduped.sort(key=lambda it: (it["_dt"] or now, it["priority"]), reverse=True)
    feed = []
    for it in deduped[:MAX_FEED_ITEMS]:
        item = {
            "title": it["title"],
            "url": it["url"],
            "source": it["source"],
            "published_at": it["published_at"],
            "description": it["description"],
            "category": it["category"],
            "importance_score": it["importance_score"],
        }
        if it.get("telegram_url"):
            item["telegram_url"] = it["telegram_url"]
        if it.get("sources") and len(it["sources"]) > 1:
            item["sources"] = it["sources"]
        feed.append(item)

    if not feed and os.path.exists(FEED_PATH):
        with open(FEED_PATH, encoding="utf-8") as f:
            feed = json.load(f)
        log("  усі джерела недоступні — feed.json збережено з попереднім вмістом")

    with open(FEED_PATH, "w", encoding="utf-8") as f:
        json.dump(feed, f, ensure_ascii=False, indent=2)

    meta = {
        "updated_at": iso(now),
        "totals": {
            "fetched": len(raw_items),
            "after_filter": len(filtered),
            "after_dedup": len(deduped),
            "duplicates_merged": merged_count,
            "feed": len(feed),
        },
        "sources": meta_sources,
        "warnings": warnings,
    }
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    log("---")
    log(f"fetched={len(raw_items)} filter={len(filtered)} dedup={len(deduped)} merged={merged_count} feed={len(feed)}")
    for sid, m in meta_sources.items():
        log(f"  {sid}: {m.get('status', 'ok')} fetched={m.get('fetched', 0)} "
            f"filter={m.get('after_filter', 0)} dedup={m.get('after_dedup', 0)}")
    log(f"wrote {FEED_PATH}")


if __name__ == "__main__":
    main()
