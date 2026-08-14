"""
Скрипт збирає «Пам'ятні літературні дати» з сайту Національної бібліотеки
України для дітей (chl.kiev.ua) і зберігає їх у файли
data/chl-<рік>.json у форматі, який розуміє наш модуль "Календар".

ЯК ЦЕ ПРАЦЮЄ:
  1. З розділу «Пам'ятні літературні дати» (id=5289) знаходимо сторінки
     видань за роки: «Пам'ятні літературні дати <рік> року».
  2. На сторінці видання знаходимо 12 посилань на місяці (СІЧЕНЬ..ГРУДЕНЬ).
  3. Для кожного місяця парсимо HTML-таблицю: <td> з числом дня і <td>
     з текстом «N років від дня народження <особа> (роки життя), ...».
  4. Дедуплікація проти решти джерел (див. scripts/dedup.py): точний збіг
     (дата+назва) і збіг ювілею про ту саму особу на ту саму дату.

Запускається автоматично через GitHub Actions (update-events.yml),
але можна запустити і вручну: python scripts/fetch_chl.py
"""

from html import unescape
import json
import os
import re
import urllib.request

import dedup

DATA_DIR = dedup.DATA_DIR
SECTION_ID = 5289          # розділ «Пам'ятні літературні дати»
KNOWN_2026_ID = 11663      # відоме видання 2026 (запасний шлях пошуку)
BASE_URL = "https://chl.kiev.ua/default.aspx"
TARGET_YEARS = [2026, 2027]

HEADERS = {"User-Agent": "SchoolOS-Calendar-Bot (chl-literary-dates-import)"}

MONTHS = {
    "СІЧЕНЬ": 1, "ЛЮТИЙ": 2, "БЕРЕЗЕНЬ": 3, "КВІТЕНЬ": 4,
    "ТРАВЕНЬ": 5, "ЧЕРВЕНЬ": 6, "ЛИПЕНЬ": 7, "СЕРПЕНЬ": 8,
    "ВЕРЕСЕНЬ": 9, "ЖОВТЕНЬ": 10, "ЛИСТОПАД": 11, "ГРУДЕНЬ": 12,
}


def fetch_html(url: str) -> str:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
    return raw.decode("utf-8", errors="replace")


def find_edition_pages() -> dict:
    """year -> page_id видання «Пам'ятні літературні дати <рік> року»."""
    html = fetch_html(f"{BASE_URL}?id={SECTION_ID}")
    found = {}
    for m in re.finditer(
        r'href="[^"]*[?&]id=(\d+)"[^>]*>\s*ПАМ[\'’]?ЯТНІ[^<]{0,80}ЛІТЕРАТУРНІ ДАТИ\s+(\d{4})\s+РОКУ',
        html, re.IGNORECASE | re.DOTALL,
    ):
        found[int(m.group(2))] = m.group(1)
    if 2026 not in found and KNOWN_2026_ID:
        found[2026] = str(KNOWN_2026_ID)
    return found


def find_month_pages(edition_id: str) -> dict:
    """month_number -> url сторінки місяця."""
    html = fetch_html(f"{BASE_URL}?id={edition_id}")
    pages = {}
    for m in re.finditer(
        r'href="([^"]*[?&]id=\d+)"[^>]*>\s*([А-ЯІЇЄҐ]{4,12})\s*<',
        html, re.IGNORECASE,
    ):
        month_name = m.group(2).upper()
        if month_name in MONTHS and m.group(2).isupper():
            url = m.group(1)
            pages[MONTHS[month_name]] = url if url.startswith("http") else BASE_URL + "?id=" + url.split("id=")[-1]
    return pages


def parse_month(month_url: str) -> list:
    """-> [(day, text)] для одного місяця."""
    html = fetch_html(month_url)
    rows = []
    for block in re.split(r"<tr[^>]*>", html, flags=re.IGNORECASE)[1:]:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", block, re.DOTALL | re.IGNORECASE)
        if len(cells) < 2:
            continue
        day_text = re.sub(r"<[^>]+>", " ", cells[0])
        day_text = unescape(day_text)
        day_match = re.search(r"\b(\d{1,2})\b", day_text)
        if not day_match:
            continue
        text = clean_text(cells[1])
        if text:
            rows.append((int(day_match.group(1)), text))
    return rows


def clean_text(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def main():
    editions = find_edition_pages()
    print(f"Знайдено видань за роками: {sorted(editions.items())}")
    os.makedirs(DATA_DIR, exist_ok=True)

    for year in TARGET_YEARS:
        edition_id = editions.get(year)
        if not edition_id:
            print(f"[WARN] Видання за {year} рік не знайдено — пропускаю")
            continue
        month_pages = find_month_pages(edition_id)
        print(f"{year}: місячних сторінок = {len(month_pages)}")
        if len(month_pages) != 12:
            print(f"[WARN] {year}: очікувалось 12 місяців, знайдено {len(month_pages)}")

        entries = []
        for month_number in range(1, 13):
            url = month_pages.get(month_number)
            if not url:
                print(f"[WARN] {year}: нема сторінки місяця {month_number}")
                continue
            try:
                rows = parse_month(url)
            except Exception as error:
                print(f"[WARN] {year}-{month_number:02d}: {error}")
                continue
            for day, text in rows:
                entries.append((f"{year}-{month_number:02d}-{day:02d}", text, url))

        existing = dedup.load_existing(year, exclude_prefixes=("chl-",))
        kept, exact = dedup.dedup_exact(
            [(date, text) for date, text, _ in entries],
            existing, key_of=lambda e: e,
        )
        kept, fuzzy = dedup.dedup_anniversary(
            kept, existing, key_of=lambda e: e,
        )
        print(f"{year}: зібрано {len(entries)}, дублікатів (точних) = {exact}, "
              f"дублікатів (ювілеї) = {fuzzy}, збережено {len(kept)}")

        url_by_date_text = {(d, t): u for d, t, u in entries}
        items = [{
            "date": date,
            "name": text,
            "type": "памятна",
            "subtype": "ювілей",
            "source": "НБУ для дітей — Пам'ятні літературні дати",
            "url": url_by_date_text[(date, text)],
        } for date, text in kept]
        items.sort(key=lambda x: x["date"])

        path = os.path.join(DATA_DIR, f"chl-{year}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        print(f"Збережено: {path} ({len(items)} записів)")


if __name__ == "__main__":
    main()