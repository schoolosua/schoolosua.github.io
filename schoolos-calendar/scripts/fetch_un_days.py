"""
Скрипт збирає міжнародні й всесвітні дні, проголошені ООН.
  - дати: https://www.un.org/en/observances/list-days-weeks (офіційний перелік, 241 рядок)
  - українські назви: uk.wikipedia.org, стаття «Міжнародні дні ООН» (сирий wikitext через action=raw)
Зшивка за датою (місяць+день) у порядку появи; при різниці кількості —
суміжні рядки розпарсовуються і звітуються у stderr.
Результати: data/un-days-2026.json, data/un-days-2027.json
"""
import html as html_mod
import json
import os
import re
import sys
import urllib.request

DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data"))
EN_URL = "https://www.un.org/en/observances/list-days-weeks"
WIKI_URL = "https://uk.wikipedia.org/w/index.php?title=%D0%9C%D1%96%D0%B6%D0%BD%D0%B0%D1%80%D0%BE%D0%B4%D0%BD%D1%96_%D0%B4%D0%BD%D1%96_%D0%9E%D0%9E%D0%9D&action=raw"
TARGET_YEARS = [2026, 2027]
HEADERS = {"User-Agent": "SchoolOS-Calendar-Bot (un-days-import)"}

# Події, які ніколи не мають потрапляти в календар (повні рядки або підрядки).
# Ключі збігаються з англійською назвою un.org та українською назвою з Вікіпедії.
BLOCKED_EN = ("Russian Language Day",)
BLOCKED_SUBSTRINGS_UK = ("російської мови",)

MONTHS_EN = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
             "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}
MONTHS_UK = {"січня": 1, "лютого": 2, "березня": 3, "квітня": 4, "травня": 5,
             "червня": 6, "липня": 7, "серпня": 8, "вересня": 9, "жовтня": 10,
             "листопада": 11, "грудня": 12}

# Ручні підстановки: ключ — нормалізована англійська назва з un.org,
# якої немає в українській Вікіпедії або яку вікі дає у невідповідному порядку.
OVERRIDES = {
    "International Day of Clean Energy": "Міжнародний день чистої енергії",
    "International Day of Peaceful Coexistence": "Міжнародний день мирного співіснування",
    "World Interfaith Harmony Week": "Всесвітній тиждень міжрелігійної гармонії",
    "International Day of Human Fraternity": "Міжнародний день людського братства",
    "International Day for the Prevention of Violent Extremism as and when Conducive to Terrorism": "Міжнародний день запобігання насильницькому екстремізму, що веде до тероризму",
    "Global Tourism Resilience Day": "Всесвітній день стійкості туризму",
    "World Day for Glaciers": "Всесвітній день льодовиків",
    "International Day of Forests": "Міжнародний день лісів",
    "International Day for the Elimination of Racial Discrimination": "Міжнародний день ліквідації расової дискримінації",
    "World Poetry Day": "Всесвітній день поезії",
    "International Day of Nowruz": "Міжнародний день Навруз",
    "World Down Syndrome Day": "Всесвітній день людей із синдромом Дауна",
    "International Day of Zero Waste": "Міжнародний день нульових відходів",
    "International Day of Conscience": "Міжнародний день совісті",
    "International Wellness Day": "Міжнародний день добробуту",
    "International Girls in ICT Day": "Міжнародний день дівчат в ІКТ",
    "World Book and Copyright Day": "Всесвітній день книги та авторського права",
    "English Language Day": "День англійської мови",
    "Spanish Language Day": "День іспанської мови",
    "World Day for Safety and Health at Work": "Всесвітній день охорони праці",
    "International Day in Memory of the Victims of Earthquakes": "Міжнародний день пам'яті жертв землетрусів",
    "Vesak, the Day of the Full Moon": "Весак — день повного місяця",
    "World Migratory Bird Day": "Всесвітній день мігруючих птахів",
    "World Fair Play Day": "Всесвітній день чесної гри",
    "International Day of the Markhor": "Міжнародний день мархора",
    "World Football Day": "Всесвітній день футболу",
    "Week of Solidarity with the Peoples of Non-Self-Governing Territories": "Тиждень солідарності з народами, які не мають самоврядування",
    "International Day of Potato": "Міжнародний день картоплі",
    "International Day for Dialogue among Civilizations": "Міжнародний день діалогу між цивілізаціями",
    "International Day of Play": "Міжнародний день гри",
    "International Day of Cooperatives": "Міжнародний день кооперативів",
    "World Rural Development Day": "Всесвітній день розвитку сільських територій",
    "International Day of Combating Sand and Dust Storms": "Міжнародний день боротьби з піщаними та пиловими бурями",
    "International Day of Hope": "Міжнародний день надії",
    "World Breastfeeding Week": "Всесвітній тиждень грудного вигодовування",
    "International Day of Awareness of the Special Development Needs and Challenges of Landlocked Developing Countries": "Міжнародний день поширення інформації про особливі потреби розвитку країн, що не мають виходу до моря",
    "World Steelpan Day": "Всесвітній день стальпана",
    "World Lake Day": "Всесвітній день озер",
    "International Day for People of African Descent": "Міжнародний день людей африканського походження",
    "International Day of Clean Air for Blue Skies": "Міжнародний день чистого повітря для блакитного неба",
    "International Day of Police Cooperation": "Міжнародний день поліцейської співпраці",
    "World Duchenne Awareness Day": "Всесвітній день поширення інформації про м'язову дистрофію Дюшенна",
    "International Literacy Day": "Міжнародний день грамотності",
    "International Day to Protect Education from Attack": "Міжнародний день захисту освіти від нападів",
    "World Cleanup Day": "Всесвітній день прибирання",
    "World Maritime Day": "Всесвітній день моря",
    "International Day for Universal Access to Information": "Міжнародний день загального доступу до інформації",
    "International Day of Non-Violence": "Міжнародний день ненасильства",
    "World Space Week": "Всесвітній тиждень космосу",
    "World Habitat Day": "Всесвітній день середовища проживання",
    "International Day of the Snow Leopard": "Міжнародний день снігового барса",
    "Disarmament Week": "Тиждень роззброєння",
    "United Nations Day": "День Організації Об'єднаних Націй",
    "World Development Information Day": "Всесвітній день інформації про розвиток",
    "Global Media and Information Literacy Week": "Глобальний тиждень медійної та інформаційної грамотності",
    "International Day of Care and Support": "Міжнародний день догляду та підтримки",
    "International Week of Science and Peace": "Міжнародний тиждень науки і миру",
    "International Day for the Prevention of and Fight against All Forms of Transnational Organized Crime": "Міжнародний день попередження та боротьби з усіма формами транснаціональної організованої злочинності",
    "World Day of Remembrance for Road Traffic Victims": "Всесвітній день пам'яті жертв дорожньо-транспортних пригод",
    "World Conjoined Twins Day": "Всесвітній день сіамських близнюків",
    "World Sustainable Transport Day": "Всесвітній день сталого транспорту",
    "International Day against Colonialism in All its Forms and Manifestations": "Міжнародний день боротьби проти колоніалізму в усіх його формах і проявах",
    "World Meditation Day": "Всесвітній день медитації",
    "World Basketball Day": "Всесвітній день баскетболу",
    "International Anti-Cybercrime Day": "Міжнародний день боротьби з кіберзлочинністю",
}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def is_blocked(en_name: str, uk_name: str) -> bool:
    if en_name in BLOCKED_EN:
        return True
    low = uk_name.lower()
    return any(sub in low for sub in BLOCKED_SUBSTRINGS_UK)


def clean_en_name(name: str) -> str:
    name = html_mod.unescape(name)
    name = name.replace("\u2019", "'")
    name = re.sub(r"\s*\[[^\]]+\]", "", name)
    name = re.sub(r",\s*\d{1,2}\s*[-–]\s*\d{1,2}\s*[A-Za-z]+\s*$", "", name)
    return re.sub(r"\s+", " ", name).strip()


def parse_en(html_text: str) -> list:
    """-> [(normalized_en_name, month, day, url)]"""
    rows = []
    for block in re.split(r'<div class="views-row', html_text)[1:]:
        a = re.search(r'class="field-content"><a href="([^"]+)">([^<]+)</a>', block)
        d = re.search(r'date-display-single">([^<]+)</span>', block)
        if not a or not d:
            continue
        m = re.match(r"^(\d{1,2})\s+([A-Za-z]{3})", d.group(1).strip())
        if not m:
            continue
        url = a.group(1)
        if url.startswith("/"):
            url = "https://www.un.org" + url
        rows.append((clean_en_name(a.group(2)), MONTHS_EN[m.group(2)],
                     int(m.group(1)), url))
    return rows


def parse_wiki(wikitext: str) -> list:
    """-> [(uk_name, month, day)]"""
    rows = []
    wk = html_mod.unescape(wikitext)
    wk = wk.replace("&nbsp;", " ")
    for line in wk.splitlines():
        line = line.strip()
        if not line.startswith("*"):
            continue
        mdate = re.match(r"\*\s*\[\[(\d{1,2})\s+([а-яіїєґ']+)\s*\]\]\s*[—–-]\s*(.*)$", line)
        if not mdate:
            continue
        month = MONTHS_UK.get(mdate.group(2))
        if not month:
            continue
        name = mdate.group(3)
        name = re.split(r"<ref", name)[0]
        name = re.sub(r"\s*\([^()]*\)\s*$", "", name)
        name = re.sub(r"\[\[([^|\]]*\|)?([^\]]+)\]\]", r"\2", name)
        name = name.strip()
        if not name:
            continue
        rows.append((name, month, int(mdate.group(1))))
    return rows


def merge(en_rows, wiki_rows) -> tuple:
    """Повертає (final_rows, unmatched)"""
    wiki_by_date = {}
    for name, month, day in wiki_rows:
        wiki_by_date.setdefault((month, day), []).append(name)

    en_counts = {}
    for name, month, day, url in en_rows:
        en_counts[(month, day)] = en_counts.get((month, day), 0) + 1
    seen = {}

    final = []
    err = []
    for en_name, month, day, url in en_rows:
        uk_list = wiki_by_date.get((month, day))
        if not uk_list:
            err.append(f"NO UK for [{month}-{day}] {en_name}")
            final.append(OVERRIDES.get(en_name, en_name))
            continue
        if len(uk_list) == 1:
            final.append(uk_list[0])
            continue
        idx = seen.get((month, day), 0)
        seen[(month, day)] = idx + 1
        if idx < len(uk_list) and en_counts.get((month, day)) == len(uk_list):
            final.append(uk_list[idx])
        else:
            err.append(f"COUNT mismatch [{month}-{day}] {en_name}: en={en_counts.get((month, day))} uk={len(uk_list)}")
            final.append(OVERRIDES.get(en_name, en_name))
    return final, err


def main():
    print(f"Fetch {EN_URL}")
    en_html = fetch(EN_URL)
    print(f"Fetch {WIKI_URL}")
    wiki_text = fetch(WIKI_URL)

    en_rows = parse_en(en_html)
    wiki_rows = parse_wiki(wiki_text)
    print(f"en rows={len(en_rows)} wiki rows={len(wiki_rows)}")

    final, err = merge(en_rows, wiki_rows)
    for e in err:
        print(f"[WARN] {e}", file=sys.stderr)

    os.makedirs(DATA_DIR, exist_ok=True)
    filtered = 0
    for year in TARGET_YEARS:
        items = []
        for uk_name, (en_name, month, day, url) in zip(final, en_rows):
            if is_blocked(en_name, uk_name):
                filtered += 1
                continue
            items.append({"type": "оон", "date": f"{year:04d}-{month:02d}-{day:02d}",
                          "name": uk_name, "url": url})
        items.sort(key=lambda x: x["date"])
        path = os.path.join(DATA_DIR, f"un-days-{year}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        print(f"wrote {path} ({len(items)} items)")
    if filtered:
        print(f"відфільтровано заблокованих подій: {filtered}")


if __name__ == "__main__":
    main()