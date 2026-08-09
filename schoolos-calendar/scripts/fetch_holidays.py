"""
Скрипт автоматично завантажує державні свята України
з безкоштовного публічного API Nager.Date і зберігає
їх у файли data/holidays-<рік>.json

Запускається автоматично через GitHub Actions
(див. .github/workflows/update-events.yml),
але можна запустити і вручну: python scripts/fetch_holidays.py
"""

import json
import os
import urllib.request
from datetime import date

# Папка, куди зберігаємо готові файли з датами
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# Код країни для API (UA = Україна)
COUNTRY_CODE = "UA"


def fetch_holidays_for_year(year: int) -> list:
    """Завантажує список державних свят на вказаний рік."""
    url = f"https://date.nager.at/api/v3/publicholidays/{year}/{COUNTRY_CODE}"
    print(f"Завантажую свята за {year} рік з {url}")

    request = urllib.request.Request(url, headers={"User-Agent": "SchoolOS-Calendar-Bot"})

    with urllib.request.urlopen(request, timeout=30) as response:
        raw_data = response.read()

    holidays = json.loads(raw_data)
    print(f"Отримано {len(holidays)} свят за {year} рік")
    return holidays


def convert_to_schoolos_format(nager_holidays: list) -> list:
    """
    Перетворює формат Nager.Date у формат, зручний для наших модулів.
    Кожна подія матиме: date, name, name_en, type, source
    """
    result = []
    for item in nager_holidays:
        result.append({
            "date": item.get("date"),
            "name": item.get("localName") or item.get("name"),
            "name_en": item.get("name"),
            "type": "державне",
            "source": "Nager.Date API",
        })
    return result


def save_json(data: list, filepath: str) -> None:
    """Зберігає список подій у JSON-файл з красивим форматуванням."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Збережено: {filepath}")


def main():
    current_year = date.today().year
    years_to_fetch = [current_year, current_year + 1]

    for year in years_to_fetch:
        try:
            raw_holidays = fetch_holidays_for_year(year)
            formatted = convert_to_schoolos_format(raw_holidays)

            output_path = os.path.join(DATA_DIR, f"holidays-{year}.json")
            save_json(formatted, output_path)

        except Exception as error:
            print(f"ПОМИЛКА при завантаженні свят за {year} рік: {error}")
            # Не зупиняємо весь скрипт через один рік з помилкою
            continue

    print("Готово! Всі доступні дані завантажено.")


if __name__ == "__main__":
    main()
