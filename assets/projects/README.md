# Project cover system

The shared `cover.html` source uses the “name as a monument” direction (seed
1132334059): large project names, the original app marks, and solid navy/cyan fields.
Every exported cover is 1800 × 900 pixels. The profile displays the leading two
public pins by stars; all six covers are prepared so daily changes need no export.

Export locally from the repository root with Chrome or Chromium and FFmpeg:

```powershell
python scripts/export_project_covers.py --browser "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

The script uses only Python's standard library. Neither the template nor the export
script runs in GitHub Actions. Each output is limited to 300 KB. Original app marks
remain in `assets/apps`; no logos are repainted. These are graphic covers, not app
screenshots. Capabilities, release versions, star badges, and links remain native
README content.

Manrope by The Manrope Project Authors is distributed under the SIL Open Font
License 1.1, included in `fonts/OFL.txt`. The variable font was obtained from
[Google Fonts](https://github.com/google/fonts/tree/main/ofl/manrope).

The frontend-design and design-taste-frontend direction is adapted to GitHub's
sanitized Markdown: native headings, links, images, and disclosures replace custom
CSS, animation, and scroll scenes. The supplied research banner is unchanged.
