"""Export the shared cover template locally; this is never run by Actions."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ("ig-now", "whatsnow", "tubenow", "tiktok-now", "x-now", "tweak4windows")


def export_covers(browser: Path) -> None:
    """Rasterize exact original app marks and licensed type at 1800 by 900."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg with libwebp is required for local exports")
    template = ROOT / "assets/projects/cover.html"
    with tempfile.TemporaryDirectory(prefix="profile-covers-") as folder:
        temporary = Path(folder)
        for slug in PROJECTS:
            screenshot = temporary / f"{slug}.png"
            subprocess.run(
                [
                    str(browser),
                    "--headless=new",
                    "--disable-gpu",
                    "--hide-scrollbars",
                    "--no-first-run",
                    f"--user-data-dir={temporary / 'browser'}",
                    "--window-size=1800,900",
                    "--force-device-scale-factor=1",
                    "--virtual-time-budget=2500",
                    f"--screenshot={screenshot}",
                    f"{template.as_uri()}?project={slug}",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=45,
            )
            destination = template.parent / f"{slug}.webp"
            subprocess.run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(screenshot),
                    "-c:v",
                    "libwebp",
                    "-quality",
                    "90",
                    "-compression_level",
                    "6",
                    str(destination),
                ],
                check=True,
                timeout=30,
            )
            if destination.stat().st_size > 300_000:
                raise RuntimeError(f"Artwork exceeds 300 KB: {destination.name}")
            print(f"{destination.name}: {destination.stat().st_size:,} bytes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", type=Path, required=True)
    export_covers(parser.parse_args().browser)
