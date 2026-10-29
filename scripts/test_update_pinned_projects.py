"""Guard catalog boundaries and release availability without network calls."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.update_pinned_projects import END, START, available_platforms, render_catalog, update_readme


class CatalogTests(unittest.TestCase):
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
