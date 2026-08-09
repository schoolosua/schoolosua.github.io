"""
Скрипт автоматично збирає пам'ятні дати та історичні події
з Історичного календаря УІНП (uinp.gov.ua) і зберігає їх
у файли data/memorable-<рік>.json у форматі, який розуміє
наш модуль "Календар".

ЯК ЦЕ ПРАЦЮЄ (3 кроки):
  1. Заходимо на /istorychnyy-kalendar -> отримуємо 12 посилань на місяці
  2. Для кожного місяця заходимо на його сторінку -> збираємо реальні
     посилання на кожен день (важливо: беремо їх зі сторінки, а не
     вгадуємо за номером дня, бо на сайті трапляються "нестандартні" ID)
  3. Для кожного дня заходимо і забираємо список подій

Запускається автоматично через GitHub Actions двічі на рік,
але можна запустити і вручну: python scripts/fetch_memorable.py

УВАГА: цей скрипт робить ~380 запитів до uinp.gov.ua з паузою між
ними, тому виконання займає кілька хвилин — це нормально.
"""

import html
import json
import os
import re
import time
import urllib.request
from datetime import date

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
BASE_URL = "https://uinp.gov.ua/istorychnyy-kalendar"
REQUEST_DELAY_SECONDS = 0.3

# Українські назви місяців -> slug на сайті УІНП -> номер місяця
MONTHS = [
    ("Січень",   "sichen",   1),
    ("Лютий",    "lyutyy",   2),
    ("Березень", "berezen",  3),
    ("Квітень",  "kviten",   4),
    ("Травень",  "traven",   5),
    ("Червень",  "cherven",  6),
    ("Липень",   "lypen",    7),
    ("Серпень",  "serpen",   8),
    ("Вересень", "veresen",  9),
    ("Жовтень",  "zhovten",  10),
    ("Листопад", "lystopad", 11),
    ("Грудень",  "gruden",   12),
]

# Роки, на які генеруємо дати (повторювані щорічні події переносяться
# на обидва роки; 29 лютого автоматично пропускається для невисокосних)
TARGET_YEARS = [2026, 2027]

HEADERS = {"User-Agent": "SchoolOS-Calendar-Bot (memorial-calendar-import)"}


def fetch_html(url: str) -> str:
    """Завантажує сирий HTML сторінки (з 3 спробами на випадок мережевих збоїв)."""
    last_error = None
    for attempt in range(1, 4):
        try:
            request = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
            time.sleep(REQUEST_DELAY_SECONDS)
            return raw.decode("utf-8", errors="replace")
        except Exception as error:
            last_error = error
            print(f"  Спроба {attempt}/3 не вдалась ({error}) — повторюю...", flush=True)
            time.sleep(5)
    raise last_error


def get_day_links(month_slug: str) -> list:
    """
    Заходить на сторінку місяця і повертає список day_id, які
    реально є в посиланнях на сторінці (а не вгадані за номером).
    Приклад повернення: ['1', '2', '3', ..., '29']
    """
    url = f"{BASE_URL}/{month_slug}"
    html = fetch_html(url)

    pattern = re.compile(
        r'href="https://uinp\.gov\.ua/istorychnyy-kalendar/'
        + re.escape(month_slug)
        + r'/([A-Za-z0-9\-]+)"'
    )

    day_ids = []
    seen = set()
    for match in pattern.finditer(html):
        day_id = match.group(1)
        if day_id not in seen:
            seen.add(day_id)
            day_ids.append(day_id)

    return day_ids


def get_day_events(month_slug: str, day_id: str) -> list:
    """
    Заходить на сторінку конкретного дня і повертає список
    текстів подій (назви пам'ятних дат / історичних подій).
    """
    url = f"{BASE_URL}/{month_slug}/{day_id}"
    html = fetch_html(url)

    # Події - це посилання на рівень глибше за поточну сторінку дня,
    # напр.: /istorychnyy-kalendar/cherven/420/den-pamyati-ditey...
    pattern = re.compile(
        r'href="https://uinp\.gov\.ua/istorychnyy-kalendar/'
        + re.escape(month_slug) + r'/' + re.escape(day_id)
        + r'/[A-Za-z0-9\-]+"[^>]*>([^<]+)</a>'
    )

    events = []
    for match in pattern.finditer(html):
        text = html.unescape(match.group(1).strip())
        if text:
            events.append(text)

    return events


def classify_event(text: str) -> str:
    """
    Визначає підтип запису за текстом:
      'ювілей'      - починається з року, напр. "1863 – народився..."
      'полеглі'     - згадка про загиблого Героя війни
      'спостереження' - інше (напр. "День пам'яті...", "Міжнародний день...")
    """
    if re.match(r"^\d{3,4}\s*[–\-]\s*", text):
        if "загибл" in text.lower() or "Геро" in text:
            return "полеглі"
        return "ювілей"
    return "спостереження"


def extract_real_day_number(day_id: str, fallback_index: int) -> int:
    """
    Намагається дістати справжній номер дня з day_id (напр. '17' -> 17).
    Якщо day_id виглядає як внутрішній ID сайту (напр. '420' для
    4 червня), використовує порядковий номер у списку днів місяця
    як запасний варіант (fallback_index, рахуючи з 1).
    """
    if day_id.isdigit() and 1 <= int(day_id) <= 31:
        return int(day_id)
    return fallback_index


def build_memorable_calendar() -> list:
    """Проходить всі 12 місяців і збирає повний список подій."""
    all_events_by_month_day = []  # [(month_number, day_number, text), ...]

    for month_name, month_slug, month_number in MONTHS:
        print(f"Обробляю місяць: {month_name} ({month_slug})")
        day_ids = get_day_links(month_slug)
        print(f"  Знайдено днів на сторінці: {len(day_ids)}")

        for index, day_id in enumerate(day_ids, start=1):
            day_number = extract_real_day_number(day_id, index)
            try:
                events = get_day_events(month_slug, day_id)
            except Exception as error:
                print(f"  ПОМИЛКА на {month_name} / {day_id}: {error}")
                continue

            for event_text in events:
                all_events_by_month_day.append((month_number, day_number, event_text))

        print(f"  Зібрано подій за {month_name}: "
              f"{sum(1 for m, d, t in all_events_by_month_day if m == month_number)}")

    return all_events_by_month_day


def to_schoolos_format(raw_events: list, year: int) -> list:
    """
    Перетворює список (місяць, день, текст) на записи у форматі
    нашого модуля, для конкретного року. Дати, яких не існує в цьому
    році (29 лютого в невисокосний рік), пропускаються.
    """
    result = []
    for month_number, day_number, text in raw_events:
        try:
            event_date = date(year, month_number, day_number)
        except ValueError:
            continue  # напр. 29 лютого у невисокосному році

        result.append({
            "date": event_date.isoformat(),
            "name": text,
            "type": "памятна",
            "subtype": classify_event(text),
            "source": "УІНП — Історичний календар",
        })

    return result


def save_json(data: list, filepath: str) -> None:
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Збережено: {filepath} ({len(data)} записів)")


def main():
    print("Починаю збір Історичного календаря УІНП...")
    raw_events = build_memorable_calendar()
    print(f"\nВсього зібрано подій (з усіх місяців): {len(raw_events)}")

    for year in TARGET_YEARS:
        formatted = to_schoolos_format(raw_events, year)
        output_path = os.path.join(DATA_DIR, f"memorable-{year}.json")
        save_json(formatted, output_path)

    print("Готово!")


if __name__ == "__main__":
    main()
