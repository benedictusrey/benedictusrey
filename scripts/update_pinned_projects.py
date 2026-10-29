"""Keep the profile's app catalog in the same order as public GitHub pins."""

from __future__ import annotations

import json
import os
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
START = "<!-- pinned-projects:start -->"
END = "<!-- pinned-projects:end -->"
QUERY = """query {
  user(login: "benedictusrey") {
    pinnedItems(first: 6, types: REPOSITORY) {
      nodes { ... on Repository {
        name nameWithOwner description url isPrivate
        latestRelease {
          tagName url isPrerelease isDraft
          releaseAssets(first: 100) { totalCount nodes { name } }
        }
      } }
    }
  }
}"""
COPY = {
    "benedictusrey/WhatsNow-for-WhatsApp": (
        "WhatsNow", "Keep multiple WhatsApp accounts in one focused desktop workspace.",
        "Named accounts, Focus sessions, themes, and App Lock.",
    ),
    "benedictusrey/TubeNow": (
        "TubeNow", "Watch YouTube in a dedicated desktop app.",
        "Local ad and tracker filtering, fullscreen controls, and background playback.",
    ),
    "benedictusrey/TikTok-Now": (
        "TikTok Now", "Browse TikTok with desktop playback controls.",
        "Pause on minimize, photo carousels, and a system tray menu.",
    ),
    "benedictusrey/IG-Now": (
        "IG Now", "Keep Instagram messages and media in their own desktop window.",
        "Message notifications, video seeking, and volume controls.",
    ),
    "benedictusrey/X-Now": (
        "X Now", "Use X in a dedicated desktop window.",
        "Tray controls, media saving, and themes that follow your system.",
    ),
    "benedictusrey/Tweak4Windows": (
        "Tweak4Windows", "Review and adjust Windows from one portable toolkit.",
        "Reversible settings, hardware information, and maintenance previews.",
    ),
}
ICONS = {
    "WhatsNow-for-WhatsApp": "whatsnow.png",
    "TubeNow": "tubenow.png",
    "TikTok-Now": "tiktok-now.png",
    "IG-Now": "ig-now.png",
    "X-Now": "x-now.png",
    "Tweak4Windows": "tweak4windows.png",
}


def available_platforms(release: dict[str, Any]) -> str:
    """Label only platforms with recognizable packages in the published release."""
    names = [asset["name"].lower() for asset in release["releaseAssets"].get("nodes", [])]
    names = [name for name in names if name.endswith((
        ".exe", ".msi", ".zip", ".dmg", ".app.tar.gz", ".appimage", ".deb", ".rpm",
        ".tar.gz", ".tgz", "-x86_64", "-aarch64", "-universal",
    ))]
    platforms = []
    if any(name.endswith((".exe", ".msi")) or ("windows" in name and name.endswith(".zip")) for name in names):
        platforms.append("Windows")
    if any(name.endswith((".dmg", ".app.tar.gz")) or "macos" in name for name in names):
        platforms.append("macOS")
    if any(name.endswith((".appimage", ".deb", ".rpm")) or "linux" in name for name in names):
        platforms.append("Linux")
    return ", ".join(platforms)


def fetch_pins() -> list[dict[str, Any]]:
    """Fail on API errors so a failed refresh cannot erase the last good catalog."""
    request = Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY}).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
            "Content-Type": "application/json",
            "User-Agent": "benedictusrey-profile",
        },
    )
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("errors"):
        raise RuntimeError("GitHub could not read pinned repositories")
    return payload["data"]["user"]["pinnedItems"]["nodes"]


def render_catalog(repositories: list[dict[str, Any]]) -> str:
    """Render public pins only; never invent release availability or star counts."""
    public = [repo for repo in repositories if not repo["isPrivate"]]
    if not public:
        return "No public projects are pinned yet. [Browse repositories](https://github.com/benedictusrey?tab=repositories)."
    rows = [
        '<table width="100%">',
        '<tbody>',
    ]
    for repo in public:
        full_name = repo["nameWithOwner"]
        name, purpose, features = COPY.get(
            full_name, (repo["name"], repo.get("description") or "View this project on GitHub.", "")
        )
        title = escape(name)
        url = escape(repo["url"], quote=True)
        badge_repo = quote(full_name, safe="/")
        release = repo.get("latestRelease")
        downloadable = (
            release and not release["isDraft"] and not release["isPrerelease"]
            and release["releaseAssets"]["totalCount"] > 0
        )
        action = "Download" if downloadable else "View project"
        target = f"{url}/releases/latest" if downloadable else url
        release_badge = (
            f'<a href="{target}"><img src="https://img.shields.io/github/v/release/{badge_repo}'
            f'?style=flat-square&amp;label=release&amp;color=176b91&amp;labelColor=30363d" '
            f'width="100" alt="{escape(name)} latest release"></a>'
            if downloadable else ""
        )
        icon = ICONS.get(repo["name"])
        brand = f'<img src="assets/apps/{icon}" width="36" height="36" alt="">&nbsp; ' if icon else ""
        platforms = available_platforms(release) if downloadable else ""
        platform_line = f'<p><strong>{platforms}</strong></p>' if platforms else ""
        action_link = (
            f'<a href="{target}"><img src="assets/download.png" width="136" height="44" '
            f'alt="Download {escape(name)}: choose an installer on the latest release page"></a>'
            if downloadable else f'<a href="{target}"><strong>{action}</strong></a>'
        )
        rows.extend([
            '<tr>',
            f'<td width="1000"><h3><a href="{url}">{brand}{title}</a></h3>',
            f'{platform_line}<p>{escape(purpose)}<br>{escape(features)}</p>',
            f'<p>{action_link}</p>',
            f'<p>{release_badge} &nbsp; <a href="{url}"><img src="https://img.shields.io/github/stars/{badge_repo}'
            f'?style=flat-square&amp;label=stars&amp;color=93621b&amp;labelColor=30363d" '
            f'width="80" alt="{escape(name)} GitHub stars"></a></p></td>',
            '</tr>',
        ])
    return "\n".join([*rows, '</tbody></table>'])


def update_readme(repositories: list[dict[str, Any]], path: Path) -> None:
    """Replace one managed block only after the complete catalog is rendered."""
    text = path.read_text(encoding="utf-8")
    if text.count(START) != 1 or text.count(END) != 1:
        raise ValueError("README must contain exactly one pinned-projects block")
    before, rest = text.split(START)
    _, after = rest.split(END)
    updated = f"{before}{START}\n{render_catalog(repositories)}\n{END}{after}"
    temporary = path.with_suffix(".md.tmp")
    temporary.write_text(updated, encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    update_readme(fetch_pins(), ROOT / "README.md")
