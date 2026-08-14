"""
Скрипт збирає «Календар знаменних і пам'ятних дат» Харківської академії
неперервної освіти (edu-post-diploma.kharkov.ua) і зберігає події у файли
data/khano-<рік>.json у форматі, який розуміє модуль "Календар".

Академія публікує щомісячний календар (PDF) в інформаційну підтримку
педагогів: міжнародні події, визначні дати, історичні й літературні
постаті з короткими анотаціями.

ЯК ЦЕ ПРАЦЮЄ:
  1. Пошуком на сайті (/?s=календар+знаменних) знаходимо всі пости
     зі слагом календар-знаменних-і-пам'ятних-дат (пост на місяць).
  2. У кожному пості беремо посилання на PDF та качаємо його.
  3. З PDF визначаємо місяць і рік, а рядки «N <місяць> – Назва»
     перетворюємо на події.
  4. Дедуплікація проти інших джерел (див. scripts/dedup.py).

УВАГА: сайт ХАНО працює лише по HTTP (на 443 порті TLS зламано),
тому скрипт ходить на http:// ... Запуск: python scripts/fetch_khano.py
"""

import json
import os
import re
import urllib.parse
import urllib.request

import pypdf

import dedup

DATA_DIR = dedup.DATA_DIR
BASE_URL = "http://edu-post-diploma.kharkov.ua"
SEARCH_QUERY = "календар знаменних"
TARGET_YEARS = [2026, 2027]

HEADERS = {"User-Agent": "SchoolOS-Calendar-Bot (khano-calendar-import)"}

MONTHS_UK = {
    "січня": 1, "лютого": 2, "березня": 3, "квітня": 4, "травня": 5,
    "червня": 6, "липня": 7, "серпня": 8, "вересня": 9, "жовтня": 10,
    "листопада": 11, "грудня": 12,
}
MONTH_NAMES = {
    "січень": 1, "лютий": 2, "березень": 3, "квітень": 4, "травень": 5,
    "червень": 6, "липень": 7, "серпень": 8, "вересень": 9, "жовтень": 10,
    "листопад": 11, "грудень": 12,
}


def fetch(url: str, timeout: int = 30) -> bytes:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def find_posts() -> list:
    """URL всіх постів-календарів (переглядаємо сторінки пошуку)."""
    urls = []
    seen = set()
    for page in range(1, 11):
        url = (f"{BASE_URL}/?s={urllib.parse.quote(SEARCH_QUERY)}"
               + (f"&paged={page}" if page > 1 else ""))
        html = fetch(url).decode("utf-8", errors="replace")
        found = re.findall(r'href="(http[^"]*?news=[^"]+)"', html)
        new = []
        for u in found:
            if urllib.parse.unquote(u).find("календар-знаменних") != -1 and u not in seen:
                new.append(u)
                seen.add(u)
        if not new:
            break
        urls.extend(new)
    return urls


def download_pdf(pdf_url: str) -> str:
    """Качає PDF і повертає шлях до тимчасового файлу."""
    import tempfile
    data = fetch(pdf_url)
    path = os.path.join(tempfile.gettempdir(), "khano_cal.pdf")
    with open(path, "wb") as f:
        f.write(data)
    if not data.startswith(b"%PDF"):
        raise ValueError("відповідь не схожа на PDF")
    return path


def pdf_info(pdf_path: str) -> tuple:
    """-> (month_number, year) з першої сторінки PDF."""
    reader = pypdf.PdfReader(pdf_path)
    text = (reader.pages[0].extract_text() or "").lower()
    month = None
    for name, num in MONTH_NAMES.items():
        if name in text:
            month = num
            break
    year_match = re.search(r"20\d\d", text)
    year = int(year_match.group(0)) if year_match else None
    return month, year


def parse_pdf(pdf_path: str, month: int, year: int) -> list:
    """-> [(date, name)] з усіх сторінок PDF."""
    reader = pypdf.PdfReader(pdf_path)

    month_gen = next(k for k, v in MONTHS_UK.items() if v == month)
    events = []
    for page in reader.pages:
        text = (page.extract_text() or "").replace("\u00a0", " ")
        for m in re.finditer(
                r"(?m)^(\d{1,2})\s+([а-яіїєґ']+)\s*[–—-]\s*(.+?)\s*$", text):
            day = int(m.group(1))
            if m.group(2) != month_gen:
                continue
            name = re.sub(r"\s+", " ", m.group(3)).strip(" \u201c\u201d«»")
            if not name:
                continue
            events.append((f"{year:04d}-{month:02d}-{day:02d}", name))
    return events


def main():
    posts = find_posts()
    print(f"Знайдено постів-календарів: {len(posts)}")
    by_year = {y: [] for y in TARGET_YEARS}

    for post_url in posts:
        try:
            html = fetch(post_url).decode("utf-8", errors="replace")
        except Exception as error:
            print(f"[WARN] {post_url}: {error}")
            continue
        pdf_url = next(iter(re.findall(
            r'https?://[^\s"\'<>]+?/wp-content/uploads/[^\s"\'<>]+?\.pdf',
            html)), None)
        if not pdf_url:
            print(f"[WARN] Нема PDF у пості: {post_url}")
            continue
        try:
            pdf_path = download_pdf(pdf_url)
            month, year = pdf_info(pdf_path)
        except Exception as error:
            print(f"[WARN] PDF {pdf_url}: {error}")
            continue
        if not month or year not in TARGET_YEARS:
            print(f"[WARN] {pdf_url}: місяць={month}, рік={year} — пропуск")
            continue
        try:
            events = parse_pdf(pdf_path, month, year)
        except Exception as error:
            print(f"[WARN] parse {pdf_url}: {error}")
            continue
        print(f"{year}-{month:02d}: {len(events)} подій")
        by_year[year].extend((date, name, pdf_url) for date, name in events)

    for year in TARGET_YEARS:
        entries = by_year[year]
        existing = dedup.load_existing(year, exclude_prefixes=("khano-",))
        kept, dropped = dedup.dedup_exact(
            entries, existing, key_of=lambda e: (e[0], e[1]))
        kept, dropped_anniv = dedup.dedup_anniversary(
            kept, existing, key_of=lambda e: (e[0], e[1]))
        print(f"{year}: зібрано {len(entries)}, дублікатів (точних) = {dropped}, "
              f"(ювілеї) = {dropped_anniv}, збережено {len(kept)}")
        items = [{
            "date": date, "name": name, "type": "памятна", "subtype": "подія",
            "source": "ХАНО — Календар знаменних і пам'ятних дат",
            "url": url,
        } for date, name, url in kept]
        items.sort(key=lambda x: x["date"])
        if not items:
            print(f"[WARN] {year}: немає даних — файл не створюю")
            continue
        path = os.path.join(DATA_DIR, f"khano-{year}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        print(f"Збережено: {path} ({len(items)} записів)")


if __name__ == "__main__":
    main()