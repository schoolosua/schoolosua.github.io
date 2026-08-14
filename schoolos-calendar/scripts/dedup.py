"""
Спільні утиліти дедуплікації для скриптів-парсерів календаря.

Щоб на одну дату не було двох записів про одну подію (користувач бачить
«дублювання»), кожен парсер перед збереженням звіряється з рештою файлів
data/*-<рік>.json:

  - dedup_exact: точний збіг (дата + нормалізована назва) — завжди дублікат;
  - dedup_anniversary: ювілей («N років від дня народження <особа>»), якщо на
    ту саму дату вже є ювілей про ту саму особу (збіг основ прізвища,
    узгоджений за відмінками);
  - dedup_church: церковна подія, якщо на ту саму дату вже є подія зі
    спільними словами в назві (напр. «Обрізання Господнє» уже в календарі ВРУ).
"""

import json
import os
import re

DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data"))

STOPWORDS = {
    "років", "роки", "року", "році", "від", "дня", "народження",
    "із", "народився", "народилась", "народилася", "український",
    "українського", "українська", "української", "українця", "українці",
    "поета", "поетки", "письменника", "письменниці", "прозаїка",
    "драматурга", "перекладача", "перекладачки", "художника",
    "художниці", "письменник", "поет", "поетеса", "прозаїк", "драматург",
    "перекладач", "перекладачка", "художник", "художниця", "педагога",
    "педагог", "педагогиня", "науковця", "науковець", "журналіста",
    "журналіст", "громадського", "діяча", "діячки", "діяч", "діячка",
    "композитора", "композитор", "композиторка", "актора", "акторки",
    "режисера", "режисер", "митця", "мисткині", "митець", "мисткиня",
    "одночасно", "день", "свято", "святий", "святого", "свята", "святі",
    "вірних", "православних", "греко", "католицької", "церкви", "церква",
}


def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[’'`‘“”\"«»]", "", text)
    text = re.sub(r"[^а-яіїєґa-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def word_bases(text: str) -> set:
    """Основи слів (закінчення відкидається) — для зіставлення відмінків."""
    result = set()
    for token in re.findall(r"[а-яіїєґ]{4,}", text.lower()):
        if token in STOPWORDS:
            continue
        base = re.sub(r"[аяуіиоє]$", "", token)
        if len(base) >= 5:
            result.add(base)
    return result


def is_anniversary(text: str) -> bool:
    low = text.lower()
    if "народив" in low or "народил" in low:
        return True
    return "років" in low and "народженн" in low


def person_name(text: str) -> str:
    m = re.match(
        r".*?років (?:від|із|з) дня (?:народження|заснування)[^А-ЯA-Z]*?\s+"
        r"([А-ЯІЇЄҐ][^(),]*?)\s*\(\d{4}", text)
    if m:
        return " ".join(m.group(1).split())
    m = re.match(
        r"^\d{3,4}\s*[–—\-]\s*(?:народився|народилась|народилася)\s+"
        r"([А-ЯІЇЄҐ][^,]+)", text)
    if m:
        return " ".join(m.group(1).split())
    return ""


def load_existing(year: int, exclude_prefixes=("chl-",)) -> list:
    """Усі події інших джерел за рік: [(date, name, type), ...]."""
    existing = []
    for filename in os.listdir(DATA_DIR):
        if not filename.endswith(f"-{year}.json"):
            continue
        if any(filename.startswith(p) for p in exclude_prefixes):
            continue
        path = os.path.join(DATA_DIR, filename)
        try:
            with open(path, encoding="utf-8") as f:
                existing.extend(
                    (item["date"], item["name"], item.get("type", ""))
                    for item in json.load(f)
                )
        except (OSError, ValueError):
            continue
    return existing


def dedup_exact(entries, existing, key_of):
    """-> (kept, dropped). entries: list; key_of(entry) -> (date, name)."""
    existing_norm = {(date, normalize(name)) for date, name, _ in existing}
    kept, dropped = [], 0
    for entry in entries:
        date, name = key_of(entry)
        if (date, normalize(name)) in existing_norm:
            dropped += 1
            continue
        kept.append(entry)
    return kept, dropped


def dedup_anniversary(entries, existing, key_of):
    """Прибирає ювілеї, якщо на ту саму дату вже є ювілей про ту саму особу."""
    anniv_by_date = {}
    for date, name, event_type in existing:
        if event_type in ("офіційне", "державне", "день", "оон"):
            continue
        if not is_anniversary(name):
            continue
        anniv_by_date.setdefault(date, []).append(name)

    kept, dropped = [], 0
    for entry in entries:
        date, name = key_of(entry)
        if not is_anniversary(name):
            kept.append(entry)
            continue
        person = person_name(name)
        if not person:
            kept.append(entry)
            continue
        bases = word_bases(person)
        if not bases:
            kept.append(entry)
            continue
        duplicated = False
        for other in anniv_by_date.get(date, []):
            if word_bases(other) & bases:
                duplicated = True
                break
        if duplicated:
            dropped += 1
            continue
        kept.append(entry)
    return kept, dropped


def dedup_church(entries, existing, key_of):
    """Церковна подія — дублікат, якщо на дату вже є запис зі спільними словами."""
    by_date = {}
    for date, name, event_type in existing:
        if event_type == "день":
            continue
        by_date.setdefault(date, []).append(name)

    kept, dropped = [], 0
    for entry in entries:
        date, name = key_of(entry)
        bases = word_bases(name)
        duplicated = False
        for other in by_date.get(date, []):
            if (word_bases(other) & bases) or normalize(other) == normalize(name):
                duplicated = True
                break
        if duplicated:
            dropped += 1
            continue
        kept.append(entry)
    return kept, dropped