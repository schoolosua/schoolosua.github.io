"""
Скрипт збирає свята та події з daytoday.ua (WordPress + Content Views).

Джерела:
  - 12 сторінок місяців: https://daytoday.ua/<місяць>-svyata-ta-podii/
    (список розбито на декілька частин через ?_page=N; ~100 карток на сторінку)
  - 12 сторінок «Церковний календар»: https://daytoday.ua/tserkovnyy-kalendar-na-<місяць>/
    (авторитетний перелік релігійних свят на кожен день)

Логіка:
  - кожна картка місячної сторінки дає назву, URL (першоджерело) та тег-дату
    (<день>-<місяць>; для плаваючих дат день уже розв'язаний на рік сторінки);
  - рік визначається з H1 сторінки (напр. «Свята та події у січні 2026»);
  - релігійні свята відсікаються через зіставлення назви картки з переліком
    церковного календаря того самого дня (співпадіння хоча б одного 4-літерного
    слово-стовбура).

Результат: data/daytoday-<рік>.json (тип "день"; кожна подія має url-першоджерело)
"""
import json
import os
import re
import sys
import urllib.request

DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data"))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

MONTHS = {
    1: ("sichen", "sichen"), 2: ("lutyi", "liutyy"), 3: ("berezen", "berezen"),
    4: ("kviten", "kviten"), 5: ("traven", "traven"), 6: ("cherven", "cherven"),
    7: ("lypen", "lypen"), 8: ("serpen", "serpen"), 9: ("veresn", "veresen"),
    10: ("zhovten", "zhovten"), 11: ("lystopad", "lystopad"), 12: ("gruden", "hruden"),
}

# Родовий відмінок місяця у тезі-дати картки (1-sichnia, 14-liutoho, ...)
MONTH_GENITIVE = {
    "sichnia": 1, "liutoho": 2, "bereznia": 3, "kvitnia": 4, "travnia": 5,
    "chervnia": 6, "lypnia": 7, "serpnia": 8, "veresnia": 9, "zhovtnia": 10,
    "lystopada": 11, "hrudnia": 12,
}

# Службові слова (цілими), які не свідчать про схожість назв подій
RAW_STOPWORDS = """
день дні дня рік роки років року році свято свят святого святий святого свято
святкува відзнач память памяті пам'ять пам'яті місяць місяця місяці місяців
міжнародний міжнародна міжнародні міжнародне всесвітній всесвітня всесвітні
національний національна національні український українська українські назва
подія події подій провод проводиться кожного присвячується та й і в на але що
як у за по про яка який які це для з від до не
"""


def norm_token(word: str) -> str:
    w = re.sub(r"['’ʼ`]", "", word.lower().strip())
    w = re.sub(r"[^а-яіїєґa-z0-9]", "", w)
    return w[:4] if len(w) > 4 else w


# стеб-версія стоп-слів (усі зрівнюються у 4-буквеному стебі)
STOP_STEMS = {norm_token(w) for w in re.findall(r"[\w']+", RAW_STOPWORDS) if len(w) >= 4}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
        return raw.decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] не вдалося отримати {url}: {exc}", file=sys.stderr)
        return ""


def norm_token(word: str) -> str:
    w = re.sub(r"['’ʼ`]", "", word.lower().strip())
    w = re.sub(r"[^а-яіїєґa-z0-9]", "", w)
    return w[:4] if len(w) > 4 else w


def content_tokens(text: str) -> set:
    out = set()
    for w in re.findall(r"[\w'’ʼ'-]+", text.lower(), re.UNICODE):
        if len(w) < 4 or w.isdigit():
            continue
        t = norm_token(w)
        if t in STOP_STEMS:
            continue
        out.add(t)
    return out


def parse_month_cards(html: str) -> list:
    cards = []
    for m in re.finditer(
        r'<div class="col-md-12 col-sm-12 col-xs-12 pt-cv-content-item[^"]*" '
        r'data-pid="(\d+)">(.*?)<div class="pt-cv-social', html, re.S
    ):
        body = m.group(2)
        tm = re.search(r'<h3 class="pt-cv-title"><a href="([^"]+)"[^>]*>([^<]+)</a>', body)
        if not tm:
            continue
        mday = re.search(r'pt-cv-tax-(\d+)-([a-z]+)"', body)
        if not mday:
            continue
        flags = set(re.findall(r'pt-cv-tax-(holovni-podii|plavaiucha-data|ne-propustit)"', body))
        cards.append({
            "name": re.sub(r"\s+", " ", tm.group(2)).strip(),
            "url": tm.group(1),
            "day": int(mday.group(1)),
            "mth": mday.group(2),
            "flags": sorted(flags),
        })
    return cards


def total_pages(html: str) -> int:
    m = re.search(r'data-totalpages="(\d+)"', html)
    return int(m.group(1)) if m else 1


def parse_year(html: str) -> int:
    m = re.search(r"<h1[^>]*>([^<]*)</h1>", html)
    text = m.group(1) if m else ""
    if not text:
        m2 = re.search(r"<title>(.*?)</title>", html)
        text = m2.group(1) if m2 else ""
    y = re.search(r"(20\d{2})", text)
    return int(y.group(1)) if y else 0


def sample_year(urls: list) -> int:
    """Рік сторінки місяця за роками у заголовках кількох подій-карток.

    H1 сторінки місяця може відставати (наприклад, «у лютому 2025», коли
    контент уже за 2026 рік), тому рік береться з <title> самих подій:
    «Всесвітній день страуса (2026) - DAY TODAY».
    """
    for url in dict.fromkeys(urls):
        html = fetch(url)
        m = re.search(r"<title>([^<]*)</title>", html)
        if not m:
            continue
        y = re.search(r"\((20\d{2})\)", m.group(1))
        if y:
            return int(y.group(1))
    return 0


def parse_church(html: str) -> dict:
    days = {}
    cur = None
    k = html.find("Головні церковні свята")
    if k < 0:
        return days
    art = html[k:]
    f = art.find('id="footer"')
    if f > 0:
        art = art[:f]
    for m in re.finditer(
        r'<p[^>]*><strong>(\d+)\s+\S+</strong></p>|<li>(.*?)</li>', art, re.S
    ):
        if m.group(1):
            cur = int(m.group(1))
            days.setdefault(cur, [])
        elif m.group(2) and cur is not None:
            t = re.sub(r"<[^>]+>", "", m.group(2))
            t = re.sub(r"\s+", " ", t).strip(" .")
            if t:
                days[cur].append(t)
    return days


def is_religious(church, day: int, name: str) -> bool:
    nt = content_tokens(name)
    if not nt:
        return False
    for item in church.get(day, []):
        if nt & content_tokens(item):
            return True
    return False


def main():
    # зібрати всі картки місячних сторінок
    rows = []          # (year, month, day, name, url, flags)
    for month in range(1, 13):
        slug_page, _ = MONTHS[month]
        base = f"https://daytoday.ua/{slug_page}-svyata-ta-podii/"
        page, total = 1, 1
        first_html = ""
        cards = []
        while page <= total:
            url = base if page == 1 else f"{base}?_page={page}"
            html = fetch(url)
            if not html:
                break
            if page == 1:
                first_html = html
                total = total_pages(html)
            cards.extend(parse_month_cards(html))
            page += 1
        year = sample_year([c["url"] for c in cards])
        for c in cards:
            if MONTH_GENITIVE.get(c["mth"]) != month:
                continue
            rows.append((year, month, c["day"], c["name"], c["url"], c["flags"]))
        print(f"  {slug_page}: рік={year}, сторінок={total}, карток={len(cards)}")

    years = {r[0] for r in rows}
    if not years:
        print("Помилка: не знайдено рік", file=sys.stderr)
        sys.exit(1)
    year = min(years)

    # зібрати церковний календар (фільтр релігійних)
    churches = {}
    for month in range(1, 13):
        _, slug_church = MONTHS[month]
        html = fetch(f"https://daytoday.ua/tserkovnyy-kalendar-na-{slug_church}/")
        churches[month] = parse_church(html)

    items = []
    excluded = 0
    for yr, month, day, name, url, flags in rows:
        if is_religious(churches[month], day, name):
            excluded += 1
            continue
        items.append({
            "type": "день",
            "date": f"{yr:04d}-{month:02d}-{day:02d}",
            "name": name,
            "url": url,
            "flags": flags,
        })
    items.sort(key=lambda x: x["date"])
    print(f"всього: {len(items)}, виключено релігійних: {excluded}")

    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, f"daytoday-{year}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()