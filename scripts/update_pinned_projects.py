"""Refresh the public pinned-project catalog, ranked by GitHub stars."""

from __future__ import annotations

import json
import os
import re
from html import escape, unescape
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
        name nameWithOwner description url isPrivate stargazerCount
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
        "WhatsNow",
        "Keep multiple WhatsApp accounts in one focused desktop workspace.",
        "Named accounts, Focus sessions, themes, and App Lock.",
    ),
    "benedictusrey/TubeNow": (
        "TubeNow",
        "Watch YouTube in a dedicated desktop app.",
        "Local ad and tracker filtering, fullscreen controls, and background playback.",
    ),
    "benedictusrey/TikTok-Now": (
        "TikTok Now",
        "Browse TikTok with desktop playback controls.",
        "Pause on minimize, photo carousels, and a system tray menu.",
    ),
    "benedictusrey/IG-Now": (
        "IG Now",
        "Keep Instagram messages and media in their own desktop window.",
        "Message notifications, video seeking, and volume controls.",
    ),
    "benedictusrey/X-Now": (
        "X Now",
        "Use X in a dedicated desktop window.",
        "Tray controls, media saving, and themes that follow your system.",
    ),
    "benedictusrey/Tweak4Windows": (
        "Tweak4Windows",
        "Review and adjust Windows from one portable toolkit.",
        "Reversible settings, hardware information, and maintenance previews.",
    ),
}
ARTWORK = {
    "benedictusrey/WhatsNow-for-WhatsApp": "whatsnow",
    "benedictusrey/TubeNow": "tubenow",
    "benedictusrey/TikTok-Now": "tiktok-now",
    "benedictusrey/IG-Now": "ig-now",
    "benedictusrey/X-Now": "x-now",
    "benedictusrey/Tweak4Windows": "tweak4windows",
}
RESERVED_FRAGMENTS = frozenset(
    {
        "benedictus-rh",
        "benedictusrey",
        "pinned-apps",
        "pinned-projects",
        "featured-projects",
        "more-pinned-projects",
        "activity-and-updates",
        "github-progress",
        "a-year-of-contributions-in-3d",
        "tools--automatic-updates",
    }
)


def available_platforms(release: dict[str, Any]) -> str:
    """Label only platforms with recognizable packages in the published release."""
    names = [
        asset["name"].lower()
        for asset in release.get("releaseAssets", {}).get("nodes", [])
    ]
    names = [
        name
        for name in names
        if name.endswith(
            (
                ".exe",
                ".msi",
                ".zip",
                ".dmg",
                ".app.tar.gz",
                ".appimage",
                ".deb",
                ".rpm",
                ".tar.gz",
                ".tgz",
                "-x86_64",
                "-aarch64",
                "-universal",
            )
        )
    ]
    platforms = []
    if any(
        name.endswith((".exe", ".msi")) or ("windows" in name and name.endswith(".zip"))
        for name in names
    ):
        platforms.append("Windows")
    if any(name.endswith((".dmg", ".app.tar.gz")) or "macos" in name for name in names):
        platforms.append("macOS")
    if any(
        name.endswith((".appimage", ".deb", ".rpm")) or "linux" in name
        for name in names
    ):
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
    nodes = payload["data"]["user"]["pinnedItems"]["nodes"]
    if not isinstance(nodes, list) or any(not isinstance(node, dict) for node in nodes):
        raise RuntimeError("GitHub returned an invalid pinned-repository list")
    return nodes


def heading_fragment(title: str) -> str:
    """Return GitHub's fragment for ordinary ASCII heading text."""
    return re.sub(r"[^\w -]", "", title.lower()).replace(" ", "-")


def surrounding_fragments(text: str) -> set[str]:
    """Reserve headings and explicit anchors outside the owned README block."""
    titles = re.findall(r"^ {0,3}#{1,6}\s+(.+?)(?:\s+#+)?\s*$", text, re.M)
    titles.extend(re.findall(r"<h[1-6]\b[^>]*>(.*?)</h[1-6]>", text, re.I))
    fragments = set(RESERVED_FRAGMENTS)
    for title in titles:
        plain = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", title)
        plain = unescape(re.sub(r"<[^>]+>", "", plain))
        base = heading_fragment(plain)
        fragment = base
        suffix = 0
        while fragment in fragments:
            suffix += 1
            fragment = f"{base}-{suffix}"
        fragments.update((base, fragment))
    fragments.update(re.findall(r"(?:id|name)=[\'\"]([^\'\"]+)[\'\"]", text))
    return fragments


def navigation_targets(
    public: list[dict[str, Any]],
    reserved_fragments: set[str],
) -> list[tuple[str, str, str]]:
    """Use native headings where unambiguous, retaining legacy named anchors."""
    legacy_anchors = []
    occupied = set(reserved_fragments) | set(RESERVED_FRAGMENTS)
    for repo in public:
        base = "app-" + re.sub(r"[^a-z0-9_-]", "-", repo["nameWithOwner"].lower())
        anchor = base
        suffix = 1
        while anchor in legacy_anchors:
            suffix += 1
            anchor = f"{base}-{suffix}"
        legacy_anchors.append(anchor)
    occupied.update(legacy_anchors)
    # Reserve duplicate-heading suffixes before allocating any custom anchor.
    names = [COPY.get(repo["nameWithOwner"], (repo["name"],))[0] for repo in public]
    occupied.update(heading_fragment(name) for name in names)
    headings = set(reserved_fragments) | set(RESERVED_FRAGMENTS)
    actual_fragments = []
    for name in names:
        base = heading_fragment(name)
        actual = base
        suffix = 0
        while actual in headings:
            suffix += 1
            actual = f"{base}-{suffix}"
        headings.add(actual)
        actual_fragments.append(actual)
    occupied.update(actual_fragments)
    targets = []
    for name, legacy, actual in zip(names, legacy_anchors, actual_fragments):
        base = heading_fragment(name)
        native = (
            bool(base)
            and name.isascii()
            and actual == base
            and base not in legacy_anchors
            and not base.startswith("user-content-")
        )
        custom = ""
        destination = f"user-content-{base}"
        if not native:
            custom = f"catalog-{legacy}"
            suffix = 1
            while custom in occupied or f"user-content-{custom}" in occupied:
                suffix += 1
                custom = f"catalog-{legacy}-{suffix}"
            occupied.add(custom)
            destination = f"user-content-{custom}"
        targets.append((legacy, custom, destination))
    return targets


def render_catalog(
    repositories: list[dict[str, Any]],
    *,
    root: Path | None = None,
    reserved_fragments: set[str] | None = None,
) -> str:
    """Rank public pins stably; feature at most two locally available covers."""
    root = ROOT if root is None else root
    public = [repo for repo in repositories if not repo["isPrivate"]]
    for repo in public:
        stars = repo["stargazerCount"]
        if type(stars) is not int or stars < 0:
            raise ValueError("Public repositories require a nonnegative stargazerCount")
    public.sort(key=lambda repo: -repo["stargazerCount"])
    if not public:
        return (
            "No public projects are pinned yet. "
            "[Browse repositories](https://github.com/benedictusrey?tab=repositories)."
        )
    navigation = navigation_targets(public, reserved_fragments or set())
    index = []
    for repo, (_, _, destination) in zip(public, navigation):
        name = COPY.get(repo["nameWithOwner"], (repo["name"],))[0]
        label = escape(name).replace(" ", "&nbsp;")
        index.append(f'<a href="#{escape(destination)}">{label}</a>')
    rows = ["<p>" + " &nbsp; ".join(index) + "</p>"]
    for position, (repo, (legacy, custom, _)) in enumerate(zip(public, navigation)):
        if position == 2:
            rows.append("## More pinned projects")
        full_name = repo["nameWithOwner"]
        name, purpose, features = COPY.get(
            full_name,
            (
                repo["name"],
                repo.get("description") or "View this project on GitHub.",
                "See the repository for features and usage.",
            ),
        )
        title = escape(name)
        url = escape(repo["url"], quote=True)
        badge_repo = quote(full_name, safe="/")
        release = repo.get("latestRelease")
        stable = release and not release["isDraft"] and not release["isPrerelease"]
        platforms = available_platforms(release) if stable else ""
        metadata = "No stable release is available."
        if stable:
            tag = release["tagName"]
            release_url = escape(
                release.get("url")
                or f"{repo['url']}/releases/tag/{quote(tag, safe='')}",
                quote=True,
            )
            metadata = (
                f'<a href="{release_url}">Release <strong>{escape(tag)}</strong></a>'
            )
            if platforms:
                metadata += f" · Available for {platforms}."
        actions = f'<a href="{url}"><strong>Explore project</strong></a>'
        if stable and platforms and release["releaseAssets"]["totalCount"] > 0:
            actions += f' &nbsp; <a href="{url}/releases/latest">Download latest</a>'
        anchors = f'<a name="{escape(legacy)}"></a>'
        if custom:
            anchors += f'<a name="{escape(custom)}"></a>'
        rows.extend(
            [
                anchors,
                f'<h3><a href="{url}">{title}</a></h3>',
            ]
        )
        if position < 2:
            slug = ARTWORK.get(full_name)
            path = f"assets/projects/{slug}.webp" if slug else None
            if path and (root / path).is_file():
                rows.append(
                    f'<p><a href="{url}"><img src="{path}" width="1800" '
                    f'height="900" alt="{title} project artwork"></a></p>'
                )
        badge = (
            f'<a href="{url}/stargazers"><img '
            f'src="https://img.shields.io/github/stars/{badge_repo}'
            '?style=flat-square&amp;label=stars&amp;color=6e7681&amp;labelColor=30363d" '
            f'alt="{title}: {repo["stargazerCount"]} GitHub stars"></a>'
        )
        rows.extend(
            [
                f"<p><strong>{escape(purpose)}</strong> {escape(features)}</p>",
                f"<p>{metadata} &nbsp; {badge}</p>",
                f"<p>{actions}</p>",
            ]
        )
    return "\n\n".join(rows)


def update_readme(repositories: list[dict[str, Any]], path: Path) -> None:
    """Replace one managed block only after the complete catalog is rendered."""
    text = path.read_bytes().decode("utf-8")
    if (
        text.count(START) != 1
        or text.count(END) != 1
        or text.index(START) >= text.index(END)
    ):
        raise ValueError("README must contain exactly one pinned-projects block")
    before, rest = text.split(START)
    _, after = rest.split(END)
    catalog = render_catalog(
        repositories,
        root=path.parent,
        reserved_fragments=surrounding_fragments(before + "\n" + after),
    )
    newline = "\r\n" if "\r\n" in text else "\n"
    catalog = catalog.replace("\n", newline)
    updated = f"{before}{START}{newline}{catalog}{newline}{END}{after}"
    temporary = path.with_suffix(".md.tmp")
    try:
        temporary.write_bytes(updated.encode("utf-8"))
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main(path: Path | None = None) -> None:
    """Fetch completely before updating; propagate failures to the daily workflow."""
    repositories = fetch_pins()
    update_readme(repositories, ROOT / "README.md" if path is None else path)


if __name__ == "__main__":
    main()
