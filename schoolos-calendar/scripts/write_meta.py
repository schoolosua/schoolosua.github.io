"""
Скрипт записує data/updated.json з датою останнього оновлення бази подій.

Сторінка календаря показує цю дату в блоці «Останнє оновлення».

Запускається автоматично через GitHub Actions
(див. .github/workflows/update-events.yml),
але можна запустити і вручну: python scripts/write_meta.py
"""

import json
import os
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def main():
    meta = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    output_path = os.path.join(DATA_DIR, "updated.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"Збережено: {output_path} ({meta['updated']})")


if __name__ == "__main__":
    main()
