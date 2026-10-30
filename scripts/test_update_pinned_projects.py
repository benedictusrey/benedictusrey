"""Verify catalog output and refresh safety without modifying the real README."""

from __future__ import annotations

import json
import unittest
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from scripts import update_pinned_projects as catalog


def repository(
    full_name: str = "owner/app",
    stars: int = 0,
    *,
    name: str | None = None,
    private: bool = False,
    release: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Supply API-shaped pins with explicit, including zero, star counts."""
    return {
        "name": name if name is not None else full_name.split("/")[-1],
        "nameWithOwner": full_name,
        "url": f"https://github.com/{full_name}",
        "description": "Purpose from the public repository.",
        "isPrivate": private,
        "stargazerCount": stars,
        "latestRelease": release,
    }


def stable_release(
    assets: tuple[str, ...] = ("App-setup.exe",),
    *,
    prerelease: bool = False,
    draft: bool = False,
) -> dict[str, Any]:
    return {
        "tagName": "v1.2.3",
        "url": "https://github.com/owner/app/releases/tag/v1.2.3",
        "isDraft": draft,
        "isPrerelease": prerelease,
        "releaseAssets": {
            "totalCount": len(assets),
            "nodes": [{"name": name} for name in assets],
        },
    }


class CatalogHTML(HTMLParser):
    """Inspect link and image semantics without snapshotting whitespace."""

    def __init__(self, markup: str) -> None:
        super().__init__(convert_charrefs=True)
        self.headings: list[str] = []
        self.images: list[dict[str, str | None]] = []
        self.anchors: list[str] = []
        self.ids: list[str] = []
        self.links: list[tuple[str, str, bool]] = []
        self._heading: list[str] | None = None
        self._link: dict[str, Any] | None = None
        self.feed(markup)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.append(str(attributes["id"]))
        if tag == "h3":
            self._heading = []
        if tag == "img":
            self.images.append(attributes)
        if tag == "a":
            if attributes.get("name"):
                self.anchors.append(str(attributes["name"]))
            if attributes.get("href"):
                self._link = {"href": attributes["href"], "text": [], "bold": False}
        if tag == "strong" and self._link is not None:
            self._link["bold"] = True

    def handle_data(self, data: str) -> None:
        if self._heading is not None:
            self._heading.append(data)
        if self._link is not None:
            self._link["text"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h3" and self._heading is not None:
            self.headings.append("".join(self._heading))
            self._heading = None
        if tag == "a" and self._link is not None:
            self.links.append(
                (
                    self._link["href"],
                    "".join(self._link["text"]),
                    self._link["bold"],
                )
            )
            self._link = None

    @property
    def covers(self) -> list[dict[str, str | None]]:
        return [
            image
            for image in self.images
            if str(image.get("src")).startswith("assets/")
        ]

    @property
    def jumps(self) -> list[str]:
        return [href for href, _, _ in self.links if href.startswith("#")]


class CatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / "README.md"

    def render(self, pins: list[dict[str, Any]]) -> str:
        return catalog.render_catalog(pins, root=self.root)

    def add_artwork(self) -> None:
        directory = self.root / "assets" / "projects"
        directory.mkdir(parents=True)
        for slug in catalog.ARTWORK.values():
            (directory / f"{slug}.webp").touch()

    def write_readme(self, newline: str = "\n") -> bytes:
        original = newline.join(
            [
                "# Benedictus RH",
                "Banner stays exactly as supplied.",
                catalog.START,
                "old catalog",
                catalog.END,
                "## Activity and updates",
                "Statistics stay.",
                "",
            ]
        ).encode("utf-8")
        self.path.write_bytes(original)
        return original

    def test_query_requests_stars_and_native_release_fields(self) -> None:
        for field in (
            "stargazerCount",
            "isPrivate",
            "tagName",
            "isDraft",
            "isPrerelease",
            "releaseAssets(first: 100)",
            "totalCount",
            "nodes { name }",
        ):
            self.assertIn(field, catalog.QUERY)

    def test_descending_stars_and_stable_ties_without_mutating_input(self) -> None:
        pins = [
            repository("owner/first-tie", 4),
            repository("owner/zero", 0),
            repository("owner/leader", 10),
            repository("owner/second-tie", 4),
            repository("owner/middle", 5),
        ]
        original_order = [pin["name"] for pin in pins]
        self.assertEqual(
            CatalogHTML(self.render(pins)).headings,
            [
                "leader",
                "middle",
                "first-tie",
                "second-tie",
                "zero",
            ],
        )
        self.assertEqual([pin["name"] for pin in pins], original_order)

    def test_live_count_fixture_preserves_last_tie(self) -> None:
        pins = [
            repository(full_name, stars)
            for full_name, stars in zip(
                catalog.COPY,
                (10, 5, 4, 2, 1, 1),
            )
        ]
        self.assertEqual(
            CatalogHTML(self.render(pins)).headings,
            [
                "WhatsNow",
                "TubeNow",
                "TikTok Now",
                "IG Now",
                "X Now",
                "Tweak4Windows",
            ],
        )

    def test_zero_stars_are_valid_and_remain_visible(self) -> None:
        parsed = CatalogHTML(
            self.render(
                [
                    repository("owner/first", 0),
                    repository("owner/second", 0),
                ]
            )
        )
        self.assertEqual(parsed.headings, ["first", "second"])
        self.assertEqual(
            [image["alt"] for image in parsed.images],
            [
                "first: 0 GitHub stars",
                "second: 0 GitHub stars",
            ],
        )

    def test_missing_or_invalid_counts_fail_instead_of_inventing_rank(self) -> None:
        for stars in (None, -1, "10", True):
            with self.subTest(stars=stars), self.assertRaises(ValueError):
                self.render([{**repository(), "stargazerCount": stars}])
        pin = repository()
        del pin["stargazerCount"]
        with self.assertRaises(KeyError):
            self.render([pin])

    def test_zero_one_two_and_six_public_pins(self) -> None:
        self.add_artwork()
        pins = [repository(name, 6 - index) for index, name in enumerate(catalog.COPY)]
        for count in (0, 1, 2, 6):
            with self.subTest(count=count):
                markup = self.render(pins[:count])
                parsed = CatalogHTML(markup)
                self.assertEqual(len(parsed.headings), count)
                self.assertEqual(len(parsed.covers), min(count, 2))
                self.assertEqual(len(parsed.jumps), count)
                self.assertEqual(
                    markup.count("## More pinned projects"), int(count > 2)
                )
                if count == 0:
                    self.assertIn("No public projects are pinned", markup)
                    self.assertIn(
                        "https://github.com/benedictusrey?tab=repositories", markup
                    )
                if count > 2:
                    self.assertLess(
                        markup.index("TubeNow</a></h3>"), markup.index("## More")
                    )
                    self.assertLess(
                        markup.index("## More"), markup.index("TikTok Now</a></h3>")
                    )

    def test_private_pins_are_filtered_before_ranking_or_rendering(self) -> None:
        self.add_artwork()
        known = list(catalog.COPY)
        pins = [
            {"isPrivate": True, "name": "secret", "stargazerCount": 1000},
            repository(known[0], 0),
            repository(known[1], 2),
        ]
        markup = self.render(pins)
        self.assertNotIn("secret", markup)
        self.assertEqual(CatalogHTML(markup).headings, ["TubeNow", "WhatsNow"])
        self.assertEqual(len(CatalogHTML(markup).covers), 2)
        self.assertIn("No public projects", self.render([pins[0]]))

    def test_featured_covers_change_when_star_leaders_change(self) -> None:
        self.add_artwork()
        pins = [
            repository(name, stars)
            for name, stars in zip(catalog.COPY, (10, 5, 4, 2, 1, 1))
        ]
        self.assertEqual(
            [image["src"] for image in CatalogHTML(self.render(pins)).covers],
            [
                "assets/projects/whatsnow.webp",
                "assets/projects/tubenow.webp",
            ],
        )
        pins[-1]["stargazerCount"] = 20
        parsed = CatalogHTML(self.render(pins))
        self.assertEqual(parsed.headings[:2], ["Tweak4Windows", "WhatsNow"])
        self.assertEqual(
            [image["src"] for image in parsed.covers],
            [
                "assets/projects/tweak4windows.webp",
                "assets/projects/whatsnow.webp",
            ],
        )

    def test_all_artwork_mappings_dimensions_and_heading_before_cover(self) -> None:
        self.add_artwork()
        self.assertEqual(
            list(catalog.ARTWORK.values()),
            [
                "whatsnow",
                "tubenow",
                "tiktok-now",
                "ig-now",
                "x-now",
                "tweak4windows",
            ],
        )
        for full_name, slug in catalog.ARTWORK.items():
            with self.subTest(project=full_name):
                markup = self.render([repository(full_name, 1)])
                cover = CatalogHTML(markup).covers[0]
                self.assertEqual(cover["src"], f"assets/projects/{slug}.webp")
                self.assertEqual((cover["width"], cover["height"]), ("1800", "900"))
                self.assertLess(
                    markup.index("<h3><a href="), markup.index('<img src="assets/')
                )
                self.assertIn(f'<h3><a href="https://github.com/{full_name}">', markup)
                self.assertNotIn("raw.githubusercontent.com", markup)

    def test_missing_known_artwork_keeps_facts_and_actions_without_placeholder(
        self,
    ) -> None:
        markup = self.render([repository(next(iter(catalog.COPY)), 10)])
        self.assertEqual(CatalogHTML(markup).covers, [])
        self.assertNotIn("artwork", markup)
        self.assertNotIn("placeholder", markup)
        self.assertIn("Keep multiple WhatsApp accounts", markup)
        self.assertIn("Named accounts, Focus sessions", markup)
        self.assertIn("Explore project", markup)

    def test_missing_top_cover_does_not_promote_third_place_art(self) -> None:
        self.add_artwork()
        (self.root / "assets/projects/whatsnow.webp").unlink()
        pins = [repository(name, 6 - index) for index, name in enumerate(catalog.COPY)]
        markup = self.render(pins)
        self.assertEqual(
            [image["src"] for image in CatalogHTML(markup).covers],
            [
                "assets/projects/tubenow.webp",
            ],
        )
        self.assertNotIn("not available", markup)

    def test_directory_is_not_treated_as_artwork(self) -> None:
        (self.root / "assets/projects/whatsnow.webp").mkdir(parents=True)
        self.assertEqual(
            CatalogHTML(
                self.render(
                    [
                        repository(next(iter(catalog.COPY)), 1),
                    ]
                )
            ).covers,
            [],
        )

    def test_unknown_pin_escapes_name_description_url_and_has_no_placeholder(
        self,
    ) -> None:
        pin = repository("owner/new-project", 7, name='<script> " & new')
        pin["description"] = "Read <local> & public data"
        pin["url"] += '?a="quoted"&b=2'
        markup = self.render([pin])
        self.assertIn("&lt;script&gt; &quot; &amp; new", markup)
        self.assertIn("Read &lt;local&gt; &amp; public data", markup)
        self.assertIn("?a=&quot;quoted&quot;&amp;b=2", markup)
        self.assertNotIn("<script>", markup)
        self.assertIn("See the repository for features and usage.", markup)
        self.assertNotIn("artwork", markup)
        self.assertNotIn("Download latest", markup)

    def test_missing_description_does_not_invent_features(self) -> None:
        pin = repository()
        pin["description"] = None
        markup = self.render([pin])
        self.assertIn("View this project on GitHub.", markup)
        self.assertIn("See the repository for features and usage.", markup)

    def test_explore_is_bold_primary_and_download_is_secondary(self) -> None:
        markup = self.render([repository(release=stable_release())])
        parsed = CatalogHTML(markup)
        self.assertIn(
            ("https://github.com/owner/app", "Explore project", True), parsed.links
        )
        self.assertIn(
            (
                "https://github.com/owner/app/releases/latest",
                "Download latest",
                False,
            ),
            parsed.links,
        )
        explore = next(
            i for i, link in enumerate(parsed.links) if link[1] == "Explore project"
        )
        download = next(
            i for i, link in enumerate(parsed.links) if link[1] == "Download latest"
        )
        self.assertLess(explore, download)
        self.assertNotIn("assets/download.png", markup)

    def test_native_stable_release_tag_links_to_specific_release(self) -> None:
        release = stable_release()
        release["tagName"] = "v1.2.3 & stable"
        markup = self.render([repository(release=release)])
        self.assertIn("Release <strong>v1.2.3 &amp; stable</strong>", markup)
        self.assertIn(
            (release["url"], "Release v1.2.3 & stable", True), CatalogHTML(markup).links
        )
        self.assertIn("Available for Windows.", markup)
        self.assertNotIn("img.shields.io/github/v/release", markup)

    def test_release_tag_url_fallback_is_encoded(self) -> None:
        release = stable_release()
        release.pop("url")
        release["tagName"] = "release/1 & 2"
        self.assertIn(
            'href="https://github.com/owner/app/releases/tag/release%2F1%20%26%202"',
            self.render([repository(release=release)]),
        )

    def test_absent_draft_and_prerelease_have_no_stable_metadata_or_download(
        self,
    ) -> None:
        for release in (
            None,
            stable_release(draft=True),
            stable_release(prerelease=True),
        ):
            with self.subTest(release=release):
                markup = self.render([repository(release=release)])
                self.assertNotIn("Download latest", markup)
                self.assertNotIn("v1.2.3", markup)
                self.assertNotIn("Available for", markup)
                self.assertIn("No stable release is available.", markup)
                self.assertIn("Explore project", markup)

    def test_stable_assetless_release_keeps_tag_but_has_no_download(self) -> None:
        markup = self.render([repository(release=stable_release(()))])
        self.assertIn("v1.2.3", markup)
        self.assertNotIn("Download latest", markup)
        self.assertNotIn("Available for", markup)

    def test_assetful_release_without_package_does_not_guess_platform(self) -> None:
        markup = self.render(
            [repository(release=stable_release(("checksums.sha256",)))]
        )
        self.assertNotIn("Download latest", markup)
        self.assertNotIn("Available for", markup)

    def test_platforms_come_from_packages_not_documentation(self) -> None:
        release = stable_release(
            (
                "windows-installation.md",
                "macos-notes.pdf",
                "linux-guide.md",
                "source.zip",
            )
        )
        self.assertEqual(catalog.available_platforms(release), "")
        release = stable_release(
            (
                "App_windows_x64-setup.exe",
                "App_v2_macos-universal",
                "App_amd64.AppImage",
                "App.MSI",
                "App.DMG",
                "App.deb",
                "App.rpm",
                "App.app.tar.gz",
            )
        )
        self.assertEqual(catalog.available_platforms(release), "Windows, macOS, Linux")
        for asset, expected in (
            ("App_windows.zip", "Windows"),
            ("App_linux.tar.gz", "Linux"),
            ("App_macos.zip", "macOS"),
        ):
            with self.subTest(asset=asset):
                self.assertEqual(
                    catalog.available_platforms(stable_release((asset,))), expected
                )

    def test_stars_badge_is_metadata_separate_from_actions(self) -> None:
        markup = self.render([repository(stars=0, release=stable_release())])
        parsed = CatalogHTML(markup)
        self.assertEqual(len(parsed.images), 1)
        self.assertIn(
            "img.shields.io/github/stars/owner/app", str(parsed.images[0]["src"])
        )
        self.assertIn("style=flat-square", str(parsed.images[0]["src"]))
        self.assertIn(
            ("https://github.com/owner/app/stargazers", "", False), parsed.links
        )
        paragraph = next(
            part for part in markup.split("\n\n") if "Explore project" in part
        )
        self.assertNotIn("<img", paragraph)

    def test_friendly_native_fragments_and_preserved_legacy_anchors(self) -> None:
        parsed = CatalogHTML(
            self.render([repository(name, 0) for name in catalog.COPY])
        )
        self.assertEqual(parsed.ids, parsed.anchors)
        self.assertEqual(
            parsed.jumps,
            [
                "#user-content-whatsnow",
                "#user-content-tubenow",
                "#user-content-tiktok-now",
                "#user-content-ig-now",
                "#user-content-x-now",
                "#user-content-tweak4windows",
            ],
        )
        self.assertEqual(
            parsed.anchors,
            [
                "app-benedictusrey-whatsnow-for-whatsapp",
                "app-benedictusrey-tubenow",
                "app-benedictusrey-tiktok-now",
                "app-benedictusrey-ig-now",
                "app-benedictusrey-x-now",
                "app-benedictusrey-tweak4windows",
            ],
        )

    def test_unknown_ordinary_name_uses_github_punctuation_rules(self) -> None:
        parsed = CatalogHTML(self.render([repository(name="A.B_C - Tool!", stars=0)]))
        self.assertEqual(parsed.jumps, ["#user-content-ab_c---tool"])

    def test_ambiguous_reserved_and_unicode_names_get_unique_custom_jumps(self) -> None:
        names = [
            "Pinned apps",
            "More pinned projects",
            "Benedictus RH",
            "benedictusrey",
            "Same!",
            "Same?",
            "Same-1",
            "!!!",
            "日本語",
        ]
        pins = [
            repository(f"owner/repo-{i}", 0, name=name) for i, name in enumerate(names)
        ]
        parsed = CatalogHTML(self.render(pins))
        self.assertEqual(len(set(parsed.jumps)), len(names))
        for index in (0, 1, 2, 3, 5, 6, 7, 8):
            jump = parsed.jumps[index]
            self.assertTrue(jump.startswith("#user-content-catalog-"), jump)
            self.assertIn(jump.removeprefix("#user-content-"), parsed.anchors)
        self.assertEqual(parsed.jumps[4], "#user-content-same")
        self.assertEqual(len(set(parsed.anchors)), len(parsed.anchors))
        self.assertTrue(set(parsed.anchors).issubset(parsed.ids))

    def test_new_external_heading_collision_uses_fallback_on_update(self) -> None:
        self.path.write_text(
            f"# My project\n{catalog.START}\nold\n{catalog.END}\n## Other\n",
            encoding="utf-8",
        )
        catalog.update_readme([repository(name="My project")], self.path)
        parsed = CatalogHTML(self.path.read_text(encoding="utf-8"))
        self.assertEqual(parsed.jumps, ["#user-content-catalog-app-owner-app"])
        self.assertIn("catalog-app-owner-app", parsed.anchors)

    def test_fallback_does_not_collide_with_external_custom_anchor(self) -> None:
        self.path.write_text(
            '<a name="catalog-app-owner-app"></a>\n'
            f"{catalog.START}\nold\n{catalog.END}",
            encoding="utf-8",
        )
        catalog.update_readme([repository(name="Pinned apps")], self.path)
        parsed = CatalogHTML(self.path.read_text(encoding="utf-8"))
        self.assertEqual(parsed.jumps, ["#user-content-catalog-app-owner-app-2"])

    def test_fallback_reserves_future_duplicate_heading_suffixes(self) -> None:
        pins = [repository(name="Pinned apps")]
        pins.extend(
            repository(
                f"owner/repo-{index}",
                name="catalog-app-owner-app",
            )
            for index in range(3)
        )
        parsed = CatalogHTML(self.render(pins))
        self.assertEqual(parsed.jumps[0], "#user-content-catalog-app-owner-app-3")
        self.assertEqual(len(set(parsed.jumps)), 4)
        self.assertIn("catalog-app-owner-app-3", parsed.anchors)

    def test_legacy_and_github_namespace_collisions_use_custom_navigation(self) -> None:
        for name in ("app-owner-app", "user-content-pinned-apps"):
            with self.subTest(name=name):
                parsed = CatalogHTML(self.render([repository(name=name)]))
                self.assertEqual(parsed.jumps, ["#user-content-catalog-app-owner-app"])
                self.assertIn("app-owner-app", parsed.anchors)

    def test_no_spacer_breaks_or_empty_paragraphs(self) -> None:
        markup = self.render([repository(name, 1) for name in catalog.COPY])
        self.assertNotIn("<br", markup)
        self.assertNotRegex(markup, r"<p>\s*</p>")

    def test_only_managed_block_changes_with_byte_exact_lf_and_crlf_boundaries(
        self,
    ) -> None:
        for newline in ("\n", "\r\n"):
            with self.subTest(newline=repr(newline)):
                original = self.write_readme(newline)
                catalog.update_readme([repository()], self.path)
                updated = self.path.read_bytes()
                start, end = catalog.START.encode(), catalog.END.encode()
                self.assertEqual(original.split(start)[0], updated.split(start)[0])
                self.assertEqual(original.split(end)[1], updated.split(end)[1])
                self.assertEqual(updated.count(start), 1)
                self.assertEqual(updated.count(end), 1)
                if newline == "\r\n":
                    self.assertNotIn(b"\n", updated.replace(b"\r\n", b""))
                catalog.update_readme([repository()], self.path)
                self.assertEqual(self.path.read_bytes(), updated)

    def test_invalid_marker_boundaries_preserve_readme(self) -> None:
        for text in (
            "no markers",
            catalog.START,
            catalog.END,
            f"{catalog.END}\n{catalog.START}",
            f"{catalog.START}\n{catalog.START}\n{catalog.END}",
            f"{catalog.START}\n{catalog.END}\n{catalog.END}",
            f"{catalog.START}\n{catalog.END}\n{catalog.START}\n{catalog.END}",
        ):
            with self.subTest(text=text):
                original = text.encode()
                self.path.write_bytes(original)
                with self.assertRaises(ValueError):
                    catalog.update_readme([], self.path)
                self.assertEqual(self.path.read_bytes(), original)

    def test_render_failure_preserves_previous_readme(self) -> None:
        original = self.write_readme()
        with patch.object(
            catalog, "render_catalog", side_effect=RuntimeError("render failed")
        ):
            with self.assertRaises(RuntimeError):
                catalog.update_readme([repository()], self.path)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(self.path.with_suffix(".md.tmp").exists())

    def test_atomic_replace_failure_preserves_readme_and_cleans_temp(self) -> None:
        original = self.write_readme()
        with patch.object(Path, "replace", side_effect=OSError("replace failed")):
            with self.assertRaises(OSError):
                catalog.update_readme([repository()], self.path)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(self.path.with_suffix(".md.tmp").exists())

    def test_main_fetches_then_updates_specified_readme(self) -> None:
        self.write_readme()
        with patch.object(
            catalog, "fetch_pins", return_value=[repository(stars=7)]
        ) as fetch:
            catalog.main(self.path)
        fetch.assert_called_once_with()
        self.assertIn("7 GitHub stars", self.path.read_text(encoding="utf-8"))

    def test_main_default_path_can_be_isolated(self) -> None:
        self.write_readme()
        with (
            patch.object(catalog, "ROOT", self.root),
            patch.object(catalog, "fetch_pins", return_value=[]),
        ):
            catalog.main()
        self.assertIn("No public projects", self.path.read_text(encoding="utf-8"))

    def test_api_failures_preserve_previous_readme_byte_for_byte(self) -> None:
        failures = (
            URLError("offline"),
            TimeoutError("timed out"),
            HTTPError("https://api.github.com/graphql", 403, "rate limited", {}, None),
        )
        for error in failures:
            with self.subTest(error=error):
                original = self.write_readme("\r\n")
                with (
                    patch.dict("os.environ", {"GH_TOKEN": "test-token"}),
                    patch.object(
                        catalog,
                        "urlopen",
                        side_effect=error,
                    ),
                ):
                    with self.assertRaises(type(error)):
                        catalog.main(self.path)
                self.assertEqual(self.path.read_bytes(), original)

    def test_graphql_release_errors_and_malformed_payloads_preserve_readme(
        self,
    ) -> None:
        valid_data = {"user": {"pinnedItems": {"nodes": [repository()]}}}
        payloads = (
            {"data": valid_data, "errors": [{"message": "latestRelease failed"}]},
            {"data": {"user": None}},
            {"data": {"user": {"pinnedItems": {"nodes": None}}}},
            {"data": {"user": {"pinnedItems": {"nodes": [None]}}}},
            {},
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                original = self.write_readme()
                response = BytesIO(json.dumps(payload).encode())
                with (
                    patch.dict("os.environ", {"GH_TOKEN": "test-token"}),
                    patch.object(
                        catalog,
                        "urlopen",
                        return_value=response,
                    ),
                ):
                    with self.assertRaises((RuntimeError, KeyError, TypeError)):
                        catalog.main(self.path)
                self.assertEqual(self.path.read_bytes(), original)

    def test_invalid_json_and_missing_token_preserve_readme(self) -> None:
        original = self.write_readme()
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(KeyError):
                catalog.main(self.path)
        with (
            patch.dict("os.environ", {"GH_TOKEN": "test-token"}),
            patch.object(
                catalog,
                "urlopen",
                return_value=BytesIO(b"not json"),
            ),
        ):
            with self.assertRaises(json.JSONDecodeError):
                catalog.main(self.path)
        self.assertEqual(self.path.read_bytes(), original)

    def test_successful_api_response_uses_graphql_and_timeout(self) -> None:
        pins = [repository(stars=0)]
        response = BytesIO(
            json.dumps(
                {
                    "data": {"user": {"pinnedItems": {"nodes": pins}}},
                }
            ).encode()
        )
        with (
            patch.dict("os.environ", {"GH_TOKEN": "test-token"}),
            patch.object(
                catalog,
                "urlopen",
                return_value=response,
            ) as fetch,
        ):
            self.assertEqual(catalog.fetch_pins(), pins)
        request = fetch.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.github.com/graphql")
        self.assertEqual(json.loads(request.data)["query"], catalog.QUERY)
        self.assertEqual(fetch.call_args.kwargs["timeout"], 30)


if __name__ == "__main__":
    unittest.main()
