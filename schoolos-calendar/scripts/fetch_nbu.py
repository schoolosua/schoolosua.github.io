"""
Скрипт збирає «Календар знаменних і пам'ятних дат» Національної бібліотеки
України імені Ярослава Мудрого (nlu.org.ua) і зберігає у файли
data/nbu-<рік>.json у форматі, який розуміє модуль "Календар".

Джерело — багате: ювілеї письменників, науковців, діячів культури й
мистецтва, історичні події тощо (12 сторінок місяців на рік).

Сторінка місяця: день = <p style="text-align:center"><strong>N</strong></p>,
далі параграфи подій (курсивом або «N років від дня народження …»);
пояснювальні абзаци («Заснований Папою…») відсікаються.

Дедуплікація проти інших джерел: точний збіг (дата+назва) і збіг ювілею
про ту саму особу (див. scripts/dedup.py).

Запускається автоматично через GitHub Actions (update-events.yml):
python scripts/fetch_nbu.py
"""

from html import unescape
import json
import os
import re
import urllib.request

import dedup

DATA_DIR = dedup.DATA_DIR
BASE_URL = "https://nlu.org.ua/calendar_dat.php"
TARGET_YEARS = [2026, 2027]

HEADERS = {"User-Agent": "SchoolOS-Calendar-Bot (nbu-calendar-import)"}

MONTHS = {
    "січня": 1, "лютого": 2, "березня": 3, "квітня": 4, "травня": 5,
    "червня": 6, "липня": 7, "серпня": 8, "вересня": 9, "жовтня": 10,
    "листопада": 11, "грудня": 12,
}

ANNIVERSARY_RE = re.compile(
    r"років (?:від|із|з) дня (?:народження|заснування)|років від часу видання"
)


def fetch_html(url: str) -> str:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" \u2013–-—")


def parse_month(html: str, year: int, month: int) -> list:
    """-> [(date, name), ...] для однієї сторінки місяця."""
    parts = re.split(
        r'<p style="text-align: ?center;"><strong>\s*(\d{1,2})\s*</strong></p>',
        html, flags=re.IGNORECASE,
    )
    # parts[0] — хвостик до першого дня, далі пари (день, контент)
    entries = []
    for i in range(1, len(parts), 2):
        day = int(parts[i])
        content = parts[i + 1]
        for block in re.findall(r"<p[^>]*>(.*?)</p>", content, re.DOTALL | re.IGNORECASE):
            name = clean(block)
            if not name or not is_event(block):
                continue
            try:
                from datetime import date
                date_str = date(year, month, day).isoformat()
            except ValueError:
                continue
            entries.append((date_str, name))
    return entries


def is_event(block: str) -> bool:
    """Подія — це параграф курсивом (свято/день) або ювілей; пояснення — ні."""
    if "<em>" in block or "<i>" in block:
        return True
    text = clean(block)
    return bool(ANNIVERSARY_RE.search(text))


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    for year in TARGET_YEARS:
        entries = []
        for month in range(1, 13):
            url = f"{BASE_URL}?year={year}&month={month}"
            try:
                html = fetch_html(url)
            except Exception as error:
                print(f"[WARN] {year}-{month:02d}: {error}")
                continue
            entries.extend(
                (date_str, name, url)
                for date_str, name in parse_month(html, year, month)
            )
        print(f"{year}: зібрано {len(entries)}")

        existing = dedup.load_existing(year, exclude_prefixes=("nbu-",))
        kept, dropped_exact = dedup.dedup_exact(
            entries, existing, key_of=lambda e: (e[0], e[1]))
        kept, dropped_anniv = dedup.dedup_anniversary(
            kept, existing, key_of=lambda e: (e[0], e[1]))
        print(f"{year}: дублікатів (точних) = {dropped_exact}, "
              f"(ювілеї) = {dropped_anniv}, збережено {len(kept)}")

        items = [{
            "date": date_str,
            "name": name,
            "type": "памятна",
            "subtype": "ювілей" if ANNIVERSARY_RE.search(name) else "подія",
            "source": "НБУ ім. Ярослава Мудрого — Календар знаменних і пам'ятних дат",
            "url": url,
        } for date_str, name, url in kept]
        items.sort(key=lambda x: x["date"])

        path = os.path.join(DATA_DIR, f"nbu-{year}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        print(f"Збережено: {path} ({len(items)} записів)")


if __name__ == "__main__":
    main()