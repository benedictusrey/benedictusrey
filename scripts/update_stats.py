"""Render a dependency-free profile dashboard from paginated public GitHub data."""

from __future__ import annotations

import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree

USERNAME = "benedictusrey"
ROOT = Path(__file__).resolve().parents[1]
PALETTE = ("#5eead4", "#7dd3fc", "#c4b5fd", "#fbbf24", "#fda4af", "#94a3b8")


def fetch_json(endpoint: str) -> Any:
    """Read GitHub JSON; retry transient failures without publishing partial data."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "benedictusrey-profile-stats",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"https://api.github.com/{endpoint}", headers=headers)
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504} or attempt == 2:
                raise
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(2 ** attempt)
    raise RuntimeError("GitHub request exhausted retries")


def fetch_pages(endpoint: str) -> list[dict[str, Any]]:
    """Collect every page of a GitHub list endpoint."""
    items: list[dict[str, Any]] = []
    separator = "&" if "?" in endpoint else "?"
    page = 1
    while True:
        batch = fetch_json(f"{endpoint}{separator}per_page=100&page={page}")
        if not isinstance(batch, list):
            raise ValueError("Expected a GitHub list response")
        items.extend(batch)
        if len(batch) < 100:
            return items
        page += 1


def svg_text(x: float, y: float, value: str, size: int = 14,
             color: str = "#b8c7d8", weight: int = 400) -> str:
    """Escape API strings before embedding them as SVG text."""
    return (f'<text x="{x}" y="{y}" font-size="{size}" '
            f'fill="{color}" font-weight="{weight}">{escape(value)}</text>')


def render_dashboard(repositories: list[dict[str, Any]],
                     languages: Counter[str], releases: int) -> str:
    """Render totals and byte-weighted language shares for original public projects."""
    date = datetime.now(timezone.utc).strftime("%d %b %Y")
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="550" '
        'viewBox="0 0 1000 550" role="img" aria-labelledby="title desc">',
        '<title id="title">Benedictus RH public GitHub dashboard</title>',
        '<desc id="desc">Public original projects, stars, forks, published releases, '
        'source language shares, and most-starred projects. Forks and the profile '
        'repository are excluded.</desc>',
        '<rect x=".5" y=".5" width="999" height="549" rx="18" '
        'fill="#0b1220" stroke="#26394a"/>',
        '<g font-family="Segoe UI, Arial, sans-serif">',
        svg_text(32, 43, "PUBLIC WORK / AT A GLANCE", 13, "#5eead4", 600),
        svg_text(770, 43, f"Updated {date} UTC", 12, "#93a8bc"),
    ]
    metrics = (
        ("Original projects", len(repositories)),
        ("Stars earned", sum(repo["stargazers_count"] for repo in repositories)),
        ("Project forks", sum(repo["forks_count"] for repo in repositories)),
        ("Published releases", releases),
    )
    for index, (label, value) in enumerate(metrics):
        x = 32 + index * 238
        parts.extend([
            f'<rect x="{x}" y="66" width="222" height="106" rx="10" '
            'fill="#111e2d" stroke="#26394a"/>',
            svg_text(x + 18, 113, f"{value:,}", 34, "#f1f5f9", 700),
            svg_text(x + 18, 146, label, 14),
        ])
    parts.extend([
        svg_text(32, 212, "Languages in public code", 19, "#f1f5f9", 600),
        svg_text(32, 236, "Share of source bytes · original projects", 12, "#93a8bc"),
        svg_text(532, 212, "Most-starred projects", 19, "#f1f5f9", 600),
        svg_text(532, 236, "Public repository stars", 12, "#93a8bc"),
    ])
    total_bytes = sum(languages.values())
    leading = languages.most_common(5)
    if len(languages) > 5:
        leading.append(("Other", total_bytes - sum(value for _, value in leading)))
    if not total_bytes:
        parts.append(svg_text(32, 285, "No language data available"))
    offset = 32.0
    for index, (language, source_bytes) in enumerate(leading):
        fraction = source_bytes / total_bytes
        width = 436 * fraction
        color = PALETTE[index]
        parts.append(f'<rect x="{offset:.3f}" y="257" width="{width:.3f}" '
                     f'height="12" fill="{color}"/>')
        offset += width
        y = 305 + index * 29
        parts.extend([
            f'<circle cx="38" cy="{y - 5}" r="4" fill="{color}"/>',
            svg_text(52, y, language, 14, "#e2e8f0"),
            svg_text(396, y, f"{fraction:.1%}", 14, "#e2e8f0"),
        ])
    ranked = sorted(repositories, key=lambda repo: (-repo["stargazers_count"], repo["name"].lower()))[:5]
    for index, repo in enumerate(ranked):
        y = 285 + index * 39
        parts.extend([
            svg_text(532, y, repo["name"], 14, "#e2e8f0", 500),
            svg_text(916, y, f'{repo["stargazers_count"]} ★', 14, "#5eead4", 600),
            f'<path d="M532 {y + 13}h436" stroke="#1d3040"/>',
        ])
    parts.extend([
        '<path d="M32 493h936" stroke="#26394a"/>',
        svg_text(32, 523, "GitHub API · public non-fork projects · profile repository excluded", 12, "#93a8bc"),
        '</g></svg>\n',
    ])
    return "\n".join(parts)


def main() -> None:
    """Fetch complete public data, validate SVG, and replace the dashboard atomically."""
    repositories = [
        repo for repo in fetch_pages(f"users/{USERNAME}/repos?type=owner")
        if not repo["fork"] and not repo.get("private", False)
        and repo["name"].lower() != USERNAME.lower()
    ]
    languages: Counter[str] = Counter()
    release_count = 0
    for repository in repositories:
        endpoint = f'repos/{USERNAME}/{repository["name"]}'
        languages.update(fetch_json(f"{endpoint}/languages"))
        release_count += sum(
            not release.get("draft", False)
            for release in fetch_pages(f"{endpoint}/releases")
        )
    dashboard = render_dashboard(repositories, languages, release_count)
    ElementTree.fromstring(dashboard)
    destination = ROOT / "assets" / "stats.svg"
    temporary = destination.with_suffix(".svg.tmp")
    temporary.write_text(dashboard, encoding="utf-8")
    temporary.replace(destination)
    print(f"Dashboard refreshed: {len(repositories)} projects, {release_count} releases")


if __name__ == "__main__":
    main()
