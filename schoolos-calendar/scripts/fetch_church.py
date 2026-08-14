"""
Скрипт збирає церковні свята ПЦУ та УГКЦ на <рік> у файли
data/pcu-<рік>.json та data/ugcc-<рік>.json (тип "релігійне").

ДЖЕРЕЛА (офіційні, новоюліанський календар):
  - ПЦУ:  «Календар і богослужбові вказівки» — pomisna.info/uk/tserkva/kalendar
          (з PDF беруться Пасха, перехідні дванадесяті й дні поминання;
           неперехідні дванадесяті та пости — стабільні новоюліанські дати);
  - УГКЦ: «Церковний календар УГКЦ на <рік> рік», укладений Патріаршою
          літургійною комісією (ugcc.ua) — парситься повна календарна
          сітка, лишаємо тільки великі свята, пости та дні поминання.

Один запис не видаляється на користь іншого джерела: якщо те саме свято
є і в календарі УГКЦ/ПЦУ, і в офіційному/державному — воно зберігається
в обох файлах. Фронтенд (index.html) на етапі злиття зводить такі
дублікати в одну картку та показує кілька пігулок-джерел (УГКЦ, ПЦУ,
офіційне, державне…). Запуск: python scripts/fetch_church.py
"""

import json
import os
import re
import urllib.parse
import urllib.request
from datetime import date, timedelta

import pypdf

import dedup

DATA_DIR = dedup.DATA_DIR
PCU_PAGE = "https://www.pomisna.info/uk/tserkva/kalendar/"
TARGET_YEARS = [2026, 2027]

HEADERS = {"User-Agent": "SchoolOS-Calendar-Bot (church-calendar-import)"}

MONTHS_EN = {"січня": 1, "лютого": 2, "березня": 3, "квітня": 4, "травня": 5,
             "червня": 6, "липня": 7, "серпня": 8, "вересня": 9, "жовтня": 10,
             "листопада": 11, "грудня": 12}
MONTH_UK = {1: "січня", 2: "лютого", 3: "березня", 4: "квітня", 5: "травня",
            6: "червня", 7: "липня", 8: "серпня", 9: "вересня", 10: "жовтня",
            11: "листопада", 12: "грудня"}

# Великі свята УГКЦ/ПЦУ (новоюліанський календар): фрагменти назв, які
# вирізняють мажорні події з повної сітки святих.
MAJOR_KEYWORDS = (
    "обрізання", "навечір", "богоявленн", "водохрещ", "стрітенн",
    "благовіщенн", "вхід господній", "вербна", "квітна", "великодн",
    "паска", "пасха", "воскресіння", "вознесінн", "п'ятдесятниц",
    "трійц", "преображенн", "успінн", "різдво", "воздвиженн", "введенн",
    "покров", "микол", "андрі", "володимир", "петра і павла", "хрестител",
    "усікновенн", "святвечір", "великий піст", "чистий понеділок",
    "петрів піст", "успенський піст", "пилипів", "різдвяний піст",
    "м'ясопусн", "сиропусн", "поминальн", "поминанн", "проводи",
    "радониця",
)

# Неперехідні великі свята (новий стиль): дати стабільні щороку.
PCU_FIXED = [
    (1, 1, "Обрізання Господнє. Свт. Василія Великого"),
    (1, 6, "Богоявлення Господнє (Хрещення Господнє)"),
    (2, 2, "Стрітення Господнє"),
    (3, 25, "Благовіщення Пресвятої Богородиці"),
    (6, 24, "Різдво св. Івана Хрестителя"),
    (6, 29, "Свв. апп. Петра і Павла"),
    (8, 6, "Преображення Господнє"),
    (8, 15, "Успіння Пресвятої Богородиці"),
    (8, 29, "Усікновення глави св. Івана Хрестителя"),
    (9, 8, "Різдво Пресвятої Богородиці"),
    (9, 14, "Воздвиження Чесного Хреста"),
    (10, 1, "Покров Пресвятої Богородиці"),
    (11, 21, "Введення в храм Пресвятої Богородиці"),
    (11, 30, "Св. ап. Андрія Первозванного"),
    (12, 6, "Св. Миколая Чудотворця"),
    (12, 24, "Навечір'я Різдва Христового (Святвечір)"),
    (12, 25, "Різдво Христове"),
]

FEAST_NAMES = {
    "ПАСХА": "Великдень (Пасха Христова)",
}


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


# Прямі URL календарів (виявлені з минулих публікацій);
# у нових роках слід доповнювати.
KNOWN_UGCC_POSTS = {
    2026: "https://ugcc.ua/data/tserkovnyy-kalendar-ugkts-na-2026-rik-8059/",
}


def find_ugcc_post(year: int) -> str:
    """Шукає на ugcc.ua пост «Церковний календар УГКЦ на <рік> рік»."""
    if year in KNOWN_UGCC_POSTS:
        return KNOWN_UGCC_POSTS[year]
    query = urllib.parse.quote(f"церковний календар угкц на {year} рік")
    html = fetch(f"https://ugcc.ua/?s={query}").decode("utf-8", errors="replace")
    for url in re.findall(r'href="(https://ugcc\.ua/[^"]+)"', html):
        if f"tserkovnyy-kalendar-ugkts-na-{year}-" in url:
            return url
    return ""


def clean_name(name: str) -> str:
    """Нормалізує назву празника з календаря УГКЦ."""
    name = re.sub(r"\s+", " ", name).strip()
    low = name.lower()
    low = re.sub(r"гніх", "Господнє", low)
    low = re.sub(
        r"пресвятої владичиці нашої богородиці і приснодіви марії",
        "Пресвятої Богородиці", low)
    low = re.sub(r"господа бога і спаса нашого ісуса христа", "Господнє", low)
    low = re.sub(r"чесного і животворного хреста", "Чесного Хреста", low)
    return low[:1].upper() + low[1:]


# Великі святі, які в УГКЦ не є червоними днями, але важливі для школи.
UGCC_EXTRA = [
    (6, 24, "Різдво св. Івана Хрестителя"),
    (6, 29, "Свв. апп. Петра і Павла"),
    (7, 15, "Св. рівноапостольного князя Володимира"),
    (11, 30, "Св. ап. Андрія Первозванного"),
    (12, 6, "Св. Миколая Чудотворця"),
]


# Маркери малих днів, які не є великими святами.
DENY_TOKENS = (
    "передсвятт", "відданн", "післясвятт", "спомин", "знайденн", "перенесенн",
    "зачаття", "блаженн", "свщмч", "прпмч", "мч.", "прп.", "ап.", "єп.",
    "архиєп", "патр.", "св.", "час", "::: ", "вак", "перед", "за ",
    "вселенськ", "субота", "тиждень", "неділя", "глас", " св.",
)
# Стебла великих неперехідних/перехідних свят (новий стиль).
FEAST_STEMS = (
    "введення", "воздвиженн", "богоявленн", "стрітенн", "благовіщ",
    "преображенн", "успінн", "різдво", "вознесінн", "п'ятдесятниц",
    "трійц", "покров", "обрізанн", "усікновенн", "вербн", "вхід господній",
    "зіслання святого духа", "навечір",
)


def major_segment(seg: str):
    """Повертає назву, якщо сегмент – велике свято (інакше None)."""
    low = seg.lower().strip()
    # Великдень: «НЕДІЛЯ ПАСХИ», «ВОСКРЕСІННЯ ГОСПОДА…», «ПАСХА ХРИСТОВА»
    if re.match(r"^(неділя\s+)?пасхи\b|^(світле\s+)?(христове\s+)?воскресінн|"
                r"^пасха\s+христова", low):
        return "Великдень (Пасха Христова)"
    if any(t in low for t in DENY_TOKENS):
        return None
    if any(t in low for t in FEAST_STEMS):
        return clean_name(seg)
    return None


def segmentise(part: str) -> list:
    return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()
            for s in re.split(r"<br\s*/?>", part) if s.strip()]


def parse_ugcc(html: str, year: int, post_url: str) -> list:
    """Парсить календар УГКЦ: червоні дні (великі празники).

    Повертає [(date, name)].
    """
    month_names = {
        "січень": 1, "лютий": 2, "березень": 3, "квітень": 4, "травень": 5,
        "червень": 6, "липень": 7, "серпень": 8, "вересень": 9, "жовтень": 10,
        "листопад": 11, "грудень": 12,
    }
    parts = re.split(r"<h[1-6][^>]*>\s*(Січень|Лютий|Березень|Квітень|Травень|"
                     r"Червень|Липень|Серпень|Вересень|Жовтень|Листопад|"
                     r"Грудень)\s*</h[1-6]>", html, flags=re.IGNORECASE)
    entries = []
    for i in range(1, len(parts), 2):
        month = month_names[parts[i].lower()]
        content = parts[i + 1]
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", content, re.DOTALL | re.IGNORECASE):
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
            if len(cells) < 3:
                continue
            day_text = re.sub(r"<[^>]+>", " ", cells[0])
            day_match = re.search(r"\b(\d{1,2})\b", day_text)
            if not day_match:
                continue
            red = re.search(r'<p class="e-red">(.*?)</p>', cells[2], re.DOTALL)
            if not red:
                continue
            bold_parts = re.findall(r"<b[^>]*>(.*?)</b>", red.group(1), re.DOTALL)
            candidates = []
            for part in bold_parts:
                for seg in segmentise(part):
                    name = major_segment(seg)
                    if name:
                        candidates.append(name)
            if not candidates:
                for seg in segmentise(red.group(1)):
                    name = major_segment(seg)
                    if name:
                        candidates.append(name)
            if not candidates:
                continue
            day = int(day_match.group(1))
            try:
                date_str = date(year, month, day).isoformat()
            except ValueError:
                continue
            entries.append((date_str, candidates[0]))

    # Додаткові святі (не червоні дні) + канонічні назви для своїх дат
    by_date = {d: n for d, n in entries}
    for month, day, name in UGCC_EXTRA:
        date_str = date(year, month, day).isoformat()
        by_date[date_str] = name
    return sorted(by_date.items())


def pcu_pdf_url(year: int) -> str:
    html = fetch(PCU_PAGE).decode("utf-8", errors="replace")
    for url in re.findall(r'https?://[^\s"\'<>]+\.pdf', html):
        if f"kalendar_{year}" in url:
            return url
    return ""


def parse_pcu_pdf(pdf_url: str, year: int) -> list:
    """Резюме-сторінки PDF ПЦУ: Пасха, перехідні свята, дні поминання."""
    data = fetch(pdf_url)
    import tempfile
    path = os.path.join(tempfile.gettempdir(), "pcu_kalendar.pdf")
    with open(path, "wb") as f:
        f.write(data)
    reader = pypdf.PdfReader(path)

    text = " ".join((p.extract_text() or "")
                    for p in reader.pages[:4]).replace("\u00a0", " ")
    text = re.sub(r"[–—]", "–", text)
    text = re.sub(r"\s+", " ", text)

    events = []
    seen = set()

    def add(day, month, name):
        try:
            date_str = date(year, month, day).isoformat()
        except ValueError:
            return
        key = (date_str, name)
        if key not in seen:
            seen.add(key)
            events.append((date_str, name))

    # 1. «ПАСХА ХРИСТОВА – 12 квітня»
    for m in re.finditer(r"ПАСХА[^–]{0,20}?[–]\s*(\d{1,2})\s+(\w+)", text):
        month = MONTHS_EN.get(m.group(2))
        if month:
            add(int(m.group(1)), month, FEAST_NAMES["ПАСХА"])

    # 2. «5 квітня, неділя – Вхід Господній у Єрусалим» (дата спочатку)
    for m in re.finditer(
            r"(\d{1,2})\s+(\w+)\s*(?:,\s*\w+)?\s*[–]\s*(.{4,70}?)\s*(?=[.;]|$)",
            text):
        month = MONTHS_EN.get(m.group(2))
        if not month:
            continue
        name = re.sub(r"\s+", " ", m.group(3)).strip(".")
        if any(k in name.lower() for k in MAJOR_KEYWORDS):
            add(int(m.group(1)), month, name)

    # 3. «Субота м'ясопусна – 14 лютого» (дата в кінці)
    for m in re.finditer(
            r"([А-ЯІЇЄҐ][^–]{4,60}?)\s*[–]\s*(\d{1,2})\s+(\w+)",
            text):
        month = MONTHS_EN.get(m.group(3))
        if not month:
            continue
        name = re.sub(r"\s+", " ", m.group(1)).strip()
        # відрізаємо заголовок секції («РІК 33 ДНІ ОСОБЛИВОГО...»)
        if ":" in name:
            name = name.split(":")[-1].strip()
        if not name or not any(k in name.lower() for k in MAJOR_KEYWORDS):
            continue
        if name[0].isupper() and name.lower().startswith(("рік", "дні")):
            continue
        add(int(m.group(2)), month, name)

    # 4. Неперехідні великі свята (стабільні дати новоюліанського календаря)
    for month, day, name in PCU_FIXED:
        add(day, month, name)
    return events


def add_fasts(events, year):
    """Пости й суто-постові дати (Пасха вже має бути в events)."""
    pascha = None
    for date_str, name in events:
        if name.startswith("Великдень") or "Пасха" in name:
            pascha = date.fromisoformat(date_str)
            break
    if not pascha:
        return events
    have = {d for d, _ in events}
    out = [e for e in events
           if not e[1].lower().startswith(
               ("великий піст", "петрів піст", "успенський піст",
                "різдвяний піст", "пилипів"))]

    def add(d, name):
        if d.isoformat() not in have and name not in {n for _, n in out}:
            out.append((d.isoformat(), name))

    add(pascha - timedelta(days=48), "Початок Великого посту (Чистий понеділок)")
    trinity = pascha + timedelta(days=49)
    add(trinity, "Свята Трійця. П'ятдесятниця")
    add(trinity + timedelta(days=8), "Початок Петрового посту")
    add(date(year, 6, 28), "Завершення Петрового посту")
    add(date(year, 8, 1), "Початок Успенського посту")
    add(date(year, 8, 14), "Завершення Успенського посту")
    add(date(year, 11, 15), "Початок Різдвяного посту (Пилипівка)")
    add(date(year, 12, 24), "Завершення Різдвяного посту (Навечір'я Різдва)")
    return out


def save(source_name, url, entries, year, prefix):
    """Записує всі події без вирізання дублікатів з іншими джерелами:
    перекриття (УГКЦ/ПЦУ + офіційне) розв’язує фронтенд пігулками."""
    items = [{
        "date": date_str, "name": name, "type": "релігійне",
        "source": source_name, "url": url,
    } for date_str, name in entries]
    items.sort(key=lambda x: x["date"])
    path = os.path.join(DATA_DIR, f"{prefix}-{year}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"Збережено: {path} ({len(items)} записів)")


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    for year in TARGET_YEARS:
        # --- УГКЦ ---
        post_url = find_ugcc_post(year)
        if post_url:
            html = fetch(post_url).decode("utf-8", errors="replace")
            entries = parse_ugcc(html, year, post_url)
            entries = add_fasts(entries, year)
            save("УГКЦ — Церковний календар (Патріарша літургійна комісія)",
                 post_url, entries, year, "ugcc")
        else:
            print(f"[WARN] УГКЦ: календар за {year} рік не знайдено — пропускаю")

        # --- ПЦУ ---
        pdf_url = pcu_pdf_url(year)
        if pdf_url:
            entries = parse_pcu_pdf(pdf_url, year)
            entries = add_fasts(entries, year)
            save("ПЦУ — Православний церковний календар (pomisna.info)",
                 pdf_url, entries, year, "pcu")
        else:
            print(f"[WARN] ПЦУ: календар за {year} рік не знайдено — пропускаю")


if __name__ == "__main__":
    main()