"""
Скрипт збирає офіційні свята України з Верховної Ради:
  - https://zakon.rada.gov.ua/laws/main/days<рік>/name
    («Календар офіційних свят в Україні» — список за місяцями)

Кожен запис: дата (день, місяць, рік), назва свята, посилання на сторінку
дня (https://zakon.rada.gov.ua/laws/main/day<N>) і категорія за кольором
легенди: державне (#f33), свято в Україні (без маркера), професійне (#5cb85c),
релігійне (#f0ad4e), міжнародне (#55b0ed), пам'ятна дата (#111).

Сайт захищений від DDoS — без браузерного User-Agent повертає 403.

Результати: data/rada-<рік>.json (тип "офіційне", поле category, url-першоджерело)
"""
import json
import os
import re
import sys
import urllib.request

DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data"))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TARGET_YEARS = [2026, 2027]

MONTHS_UK = {"Січень": 1, "Лютий": 2, "Березень": 3, "Квітень": 4, "Травень": 5,
             "Червень": 6, "Липень": 7, "Серпень": 8, "Вересень": 9, "Жовтень": 10,
             "Листопад": 11, "Грудень": 12}

# Колір маркера (iday) -> категорія
COLOR_CATEGORY = {
    "#f33": "державне",
    "#5cb85c": "професійне",
    "#f0ad4e": "релігійне",
    "#55b0ed": "міжнародне",
    "#111": "памятна",
}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "uk-UA,uk;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def parse_year(html: str) -> list:
    """-> [(year, month, day, name, url, category)]"""
    seg = re.search(r"<main(.*?)</main>", html, re.S)
    seg = seg.group(1) if seg else html
    rows = []
    cur_month = 0
    for mh in re.finditer(
        r'<h3[^>]*><span>([А-Яа-яіїєґ]+), <small>(20\d\d)</small></span>', seg
    ):
        cur_month = MONTHS_UK.get(mh.group(1), cur_month)
        year = int(mh.group(2))
        chunk_end = seg.find('<div class="card doc">', mh.end())
        if chunk_end < 0:
            chunk_end = seg.find('</section>', mh.end())
        chunk = seg[mh.end():chunk_end]
        for it in re.finditer(
            r'<li><span class="dat\d">(\d+), ([А-Яа-яіїєґ]+)</span> '
            r'&mdash; <a href="([^"]+)">(.*?)</a>(.*?)</li>', chunk, re.S
        ):
            name = re.sub(r"<[^>]+>", "", it.group(4))
            name = re.sub(r"\s+", " ", name).strip()
            if not name:
                continue
            tail = it.group(5)
            category = "свято"
            for color, cat in COLOR_CATEGORY.items():
                if color in tail:
                    category = cat
                    break
            rows.append((year, cur_month, int(it.group(1)), name,
                         it.group(3), category))
    return rows


def main():
    items = []
    for year in TARGET_YEARS:
        url = f"https://zakon.rada.gov.ua/laws/main/days{year}/name"
        print(f"Fetch {url}")
        html = fetch(url)
        rows = parse_year(html)
        print(f"  {year}: {len(rows)} подій")
        for yr, month, day, name, href, category in rows:
            items.append({
                "type": "офіційне",
                "date": f"{yr:04d}-{month:02d}-{day:02d}",
                "name": name,
                "url": href,
                "category": category,
            })

    items.sort(key=lambda x: (x["date"], x["name"]))
    print(f"всього: {len(items)}")

    os.makedirs(DATA_DIR, exist_ok=True)
    for year in TARGET_YEARS:
        sub = [x for x in items if x["date"].startswith(str(year))]
        path = os.path.join(DATA_DIR, f"rada-{year}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sub, f, ensure_ascii=False, indent=2)
        print(f"wrote {path} ({len(sub)} items)")


if __name__ == "__main__":
    main()
