"""Guard catalog boundaries and release availability without network calls."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import re

from scripts.update_pinned_projects import ARTWORK, END, START, available_platforms, render_catalog, update_readme


class CatalogTests(unittest.TestCase):
    def test_release_version_is_escaped_text_without_external_release_lookup(self) -> None:
        result = render_catalog([{
            "name": "App", "nameWithOwner": "owner/app",
            "url": "https://github.com/owner/app", "isPrivate": False,
            "latestRelease": {"tagName": "v1.2.3 & stable", "isDraft": False,
                              "isPrerelease": False, "releaseAssets": {"totalCount": 1}},
        }])
        self.assertIn('Release&nbsp;<strong>v1.2.3 &amp; stable</strong>', result)
        self.assertNotIn('img.shields.io/github/v/release', result)
        self.assertIn('img.shields.io/github/stars/owner/app', result)

    def test_covers_follow_public_pins_and_unknown_pins_keep_text_fallback(self) -> None:
        known = next(iter(ARTWORK))
        result = render_catalog([
            {"name": known.split("/")[1], "nameWithOwner": known,
             "url": f"https://github.com/{known}", "isPrivate": False},
            {"name": "new-app", "nameWithOwner": "owner/new-app",
             "url": "https://github.com/owner/new-app", "isPrivate": False},
            {"name": "private-app", "nameWithOwner": "owner/private-app", "isPrivate": True},
        ])
        self.assertEqual(result.count('project artwork"'), 1)
        self.assertIn(ARTWORK[known][0], result)
        self.assertIn('WhatsNow%20hero.png', result)
        self.assertIn('width="1944" height="809"', result)
        self.assertIn('new-app</a></h3>', result)
        self.assertNotIn("private-app", result)
        self.assertNotIn("<table", result)

    def test_jump_index_targets_every_public_pin_in_order(self) -> None:
        pins = [
            {"name": "app-one", "nameWithOwner": "owner/app-one", "url": "https://github.com/owner/app-one", "isPrivate": False},
            {"name": "app-two", "nameWithOwner": "owner/app-two", "url": "https://github.com/owner/app-two", "isPrivate": False},
        ]
        result = render_catalog(pins)
        targets = re.findall(r'href="#([^"]+)"', result)
        anchors = re.findall(r'<a name="([^"]+)"', result)
        self.assertEqual(anchors, ["app-owner-app-one", "app-owner-app-two"])
        self.assertEqual(targets, [f"user-content-{anchor}" for anchor in anchors])

    def test_platform_labels_come_from_packages_not_document_names(self) -> None:
        release = {"releaseAssets": {"nodes": [
            {"name": "windows-installation.md"}, {"name": "macos-notes.pdf"},
            {"name": "linux-guide.md"},
        ]}}
        self.assertEqual(available_platforms(release), "")
        release["releaseAssets"]["nodes"] = [
            {"name": "App_2.1.0_windows_x64-setup.exe"},
            {"name": "App_v2.1.0_macos-universal"},
            {"name": "App_2.1.0_amd64.AppImage"},
        ]
        self.assertEqual(available_platforms(release), "Windows, macOS, Linux")

    def test_empty_pins_have_a_real_destination(self) -> None:
        self.assertIn("No public projects", render_catalog([]))
        self.assertIn("?tab=repositories", render_catalog([]))

    def test_private_pins_do_not_leak(self) -> None:
        result = render_catalog([{"isPrivate": True, "name": "secret-project"}])
        self.assertNotIn("secret-project", result)

    def test_unknown_project_copy_is_escaped_and_has_no_fake_download(self) -> None:
        result = render_catalog([{
            "name": "<script>", "nameWithOwner": "owner/new-project",
            "url": "https://github.com/owner/new-project", "isPrivate": False,
            "description": "Read <local> & public data", "latestRelease": None,
        }])
        self.assertIn("&lt;script&gt;", result)
        self.assertIn("&lt;local&gt; &amp; public", result)
        self.assertNotIn("<script>", result)
        self.assertNotIn("Download", result)
        self.assertIn("View project", result)
        self.assertNotIn('/stargazers"', result)

    def test_prereleases_and_releases_without_assets_are_not_downloads(self) -> None:
        for prerelease, assets in [(True, 2), (False, 0)]:
            result = render_catalog([{
                "name": "App", "nameWithOwner": "owner/app",
                "url": "https://github.com/owner/app", "isPrivate": False,
                "latestRelease": {"isDraft": False, "isPrerelease": prerelease,
                                  "releaseAssets": {"totalCount": assets}},
            }])
            self.assertNotIn("Download", result)

    def test_only_managed_block_changes_and_missing_markers_preserve_file(self) -> None:
        with TemporaryDirectory() as folder:
            path = Path(folder) / "README.md"
            path.write_text(f"banner\n{START}\nold\n{END}\nstats", encoding="utf-8")
            update_readme([], path)
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.startswith(f"banner\n{START}"))
            self.assertTrue(text.endswith(f"{END}\nstats"))
            path.write_text("missing markers", encoding="utf-8")
            with self.assertRaises(ValueError):
                update_readme([], path)
            self.assertEqual(path.read_text(), "missing markers")


if __name__ == "__main__":
    unittest.main()
