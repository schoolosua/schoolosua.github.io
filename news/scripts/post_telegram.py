#!/usr/bin/env python3
"""
SchoolOS News — постинг у Telegram (етап 4).

Ланцюг: feed.json -> нові новини (не в telegram_sent.json) ->
importance_score >= MIN_SCORE -> максимум MAX_POSTS -> Telegram Bot API ->
запис відправлених URL у telegram_sent.json (щоб не дублювати).

Стан: news/data/telegram_sent.json — список {"url", "sent_at"}; історія
обрізається до MAX_HISTORY записів. URL — ключ дедуплікації: якщо новини
вже немає у feed.json, її не надсилають ще раз.

Вимоги до середовища (секрети GitHub Actions):
  TELEGRAM_BOT_TOKEN і TELEGRAM_CHAT_ID.
Додатково: --dry-run друкує повідомлення без відправки й без запису стану.

Стійкість: помилка API не зупиняє скрипт — невідправлений URL не
записується у стан і буде повторений наступним запуском.
"""
import html as html_mod
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001 — на Linux/CI це не потрібно
    pass

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
NEWS_DIR = os.path.normpath(os.path.join(SCRIPTS_DIR, ".."))
DATA_DIR = os.path.join(NEWS_DIR, "data")
FEED_PATH = os.path.join(DATA_DIR, "feed.json")
SENT_PATH = os.path.join(DATA_DIR, "telegram_sent.json")

API_URL = "https://api.telegram.org/bot{token}/sendMessage"
TIMEOUT = 30
MIN_SCORE = 60
MAX_POSTS = 4
MAX_HISTORY = 1000
HEADER = "📰 Головне в освіті"


def warn(msg):
    print(f"[WARN] {msg}", file=sys.stderr)


def log(msg):
    print(msg)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_feed():
    with open(FEED_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


def load_sent():
    if not os.path.exists(SENT_PATH):
        return {}
    with open(SENT_PATH, encoding="utf-8-sig") as f:
        data = json.load(f)
    if isinstance(data, list):
        return {rec["url"]: rec["sent_at"] for rec in data if rec.get("url")}
    return {}


def fmt_sent(sent_map):
    return [{"url": url, "sent_at": at} for url, at in sent_map.items()]


def escape_html(text):
    return html_mod.escape(text, quote=False)


def format_post(item):
    title = item["title"]
    url = item.get("telegram_url") or item["url"]
    desc = (item.get("description") or "").strip()
    source = item.get("source", "")

    parts = [HEADER, ""]
    parts.append(f"<b>{escape_html(title)}</b>")
    if desc:
        parts.append(f"Коротко: {escape_html(desc)}")
        parts.append("")
    else:
        parts.append("")
    parts.append(f"🔗 <a href=\"{url}\">Читати →</a>")
    if source:
        parts.append(f"Джерело: {escape_html(source)}")
    return "\n".join(parts).rstrip()


def send_message(token, chat_id, text):
    body = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        API_URL.format(token=token),
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API: {data}")
    return data


def main():
    dry_run = "--dry-run" in sys.argv
    if not dry_run:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        if not token or not chat_id:
            warn("TELEGRAM_BOT_TOKEN і TELEGRAM_CHAT_ID мають бути задані в середовищі")
            sys.exit(1)

    feed = load_feed()
    if not feed:
        warn("feed.json порожній — нічого надсилати")
        return

    sent_map = load_sent()
    candidates = [
        it for it in feed
        if (it.get("importance_score") or 0) >= MIN_SCORE
        and (it.get("telegram_url") or it["url"]) not in sent_map
    ]
    candidates.sort(key=lambda it: (it.get("importance_score") or 0, it.get("published_at") or ""), reverse=True)
    picks = candidates[:MAX_POSTS]

    log(f"feed={len(feed)} поріг={MIN_SCORE} кандидатів={len(candidates)} до посту={len(picks)}")

    for it in picks:
        url = it.get("telegram_url") or it["url"]
        text = format_post(it)
        if dry_run:
            log("[dry-run] ----")
            log(text)
            log("[dry-run] ----")
            continue
        try:
            send_message(token, chat_id, text)
            sent_map[url] = iso(datetime.now(timezone.utc))
            log(f"[OK] відправлено: {it['source']} / {it['title'][:60]}")
        except Exception as exc:  # noqa: BLE001
            warn(f"[FAIL] {it['title'][:60]}: {exc}")

    if dry_run:
        log(f"[dry-run] надіслано б було {len(picks)} новин; стан не змінено")
        return

    if sent_map:
        trimmed = dict(list(sent_map.items())[-MAX_HISTORY:])
        with open(SENT_PATH, "w", encoding="utf-8") as f:
            json.dump(fmt_sent(trimmed), f, ensure_ascii=False, indent=2)
        log(f"стан збережено: {len(trimmed)} URL в історії")


if __name__ == "__main__":
    main()