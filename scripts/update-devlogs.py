"""
Update the "Latest Devlogs" section of README.md with the most recent
Steam news/announcements for the configured games.

Runs in CI via .github/workflows/update-devlogs.yml.
"""

import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GAMES = [
    {"name": "Mars Clicker",             "appid": 3272970, "emoji": "🪐"},
    {"name": "Space Battle",             "appid": 1309140, "emoji": "🚀"},
    {"name": "Space Battle: Mayhem DLC", "appid": 2808620, "emoji": "💥"},
]

MAX_PER_GAME = 3       # how many news items to pull per game before merging
TOTAL_LIMIT  = 6       # max items rendered in the README
SUMMARY_LEN  = 160     # max characters in the summary preview
TIMEOUT      = 20      # seconds per HTTP request

README_PATH  = Path("README.md")
START_MARKER = "<!-- DEVLOGS:START -->"
END_MARKER   = "<!-- DEVLOGS:END -->"

STEAM_NEWS_URL = (
    "https://api.steampowered.com/ISteamNews/GetNewsForApp/v0002/"
    "?appid={appid}&count={count}&maxlength=600&format=json"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fetch_news(appid: int, count: int) -> list[dict]:
    url = STEAM_NEWS_URL.format(appid=appid, count=count)
    req = urllib.request.Request(url, headers={"User-Agent": "devlog-sync/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("appnews", {}).get("newsitems", []) or []
    except Exception as exc:                                          # noqa: BLE001
        print(f"  ! Failed to fetch appid={appid}: {exc}", file=sys.stderr)
        return []

def strip_markup(text: str) -> str:
    """Remove BBCode tags, HTML tags and collapse whitespace."""
    text = re.sub(r"\[/?[^\]]+\]", " ", text)           # [b]...[/b], [url=...] etc.
    text = re.sub(r"<[^>]+>", " ", text)                # <p>, <br>, ...
    text = re.sub(r"&[a-zA-Z#0-9]+;", " ", text)        # &nbsp; &amp; ...
    text = re.sub(r"\s+", " ", text).strip()
    return text

def truncate(text: str, length: int) -> str:
    if len(text) <= length:
        return text
    cut = text[:length].rsplit(" ", 1)[0]
    return cut.rstrip(",.;:- ") + "…"

def collect_devlogs() -> list[dict]:
    items: list[dict] = []
    for game in GAMES:
        print(f"→ Fetching {game['name']} ({game['appid']})")
        for raw in fetch_news(game["appid"], MAX_PER_GAME):
            items.append({
                "game":    game["name"],
                "emoji":   game["emoji"],
                "title":   raw.get("title", "Untitled"),
                "url":     raw.get("url", ""),
                "date":    int(raw.get("date", 0)),
                "summary": truncate(strip_markup(raw.get("contents", "")), SUMMARY_LEN),
            })
    items.sort(key=lambda x: x["date"], reverse=True)
    return items[:TOTAL_LIMIT]

def render_markdown(items: list[dict]) -> str:
    if not items:
        return "_No devlogs published yet — stay tuned!_"

    lines: list[str] = []
    for it in items:
        date_str = datetime.fromtimestamp(it["date"], tz=timezone.utc).strftime("%b %d, %Y")
        lines.append(f"#### {it['emoji']} [{it['title']}]({it['url']})")
        lines.append(f"<sub>**{it['game']}** · {date_str}</sub>")
        if it["summary"]:
            lines.append("")
            lines.append(f"> {it['summary']}")
        lines.append("")
    lines.append(f"<sub>_Last sync: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_</sub>")
    return "\n".join(lines).strip()

def update_readme(block: str) -> bool:
    if not README_PATH.exists():
        print(f"! {README_PATH} not found", file=sys.stderr)
        sys.exit(1)

    original = README_PATH.read_text(encoding="utf-8")
    pattern  = re.compile(
        re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER),
        re.DOTALL,
    )
    if not pattern.search(original):
        print(f"! Markers {START_MARKER} / {END_MARKER} not found in README", file=sys.stderr)
        sys.exit(1)

    new_block = f"{START_MARKER}\n{block}\n{END_MARKER}"
    updated   = pattern.sub(new_block, original)

    if updated == original:
        print("• README already up to date.")
        return False

    README_PATH.write_text(updated, encoding="utf-8")
    print("✓ README updated.")
    return True

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    devlogs = collect_devlogs()
    print(f"• Collected {len(devlogs)} devlog(s).")
    markdown = render_markdown(devlogs)
    changed  = update_readme(markdown)
    # Exit 0 in both cases — the workflow handles "no changes" gracefully.
    sys.exit(0 if changed or not devlogs else 0)
