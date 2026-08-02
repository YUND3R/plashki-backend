"""CLI: переписать сохранённые URL файлов на текущий PUBLIC_BASE_URL."""

from __future__ import annotations

import sys

from app.db.rewrite_media_urls import rewrite_stored_media_urls


def main() -> None:
    try:
        counts = rewrite_stored_media_urls(required=True)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

    total = sum(counts.values())
    for label, count in counts.items():
        print(f"{label}: {count}")
    print(f"total rows updated: {total}")


if __name__ == "__main__":
    main()
