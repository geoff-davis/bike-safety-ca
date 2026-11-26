"""A report as a finished PDF (``--pdf`` on the report commands).

Each report's text comes from its own module as Markdown.  Here it is laid out
as a page, the charts are put in where the text marks them, and Chrome prints
it.  Needs Google Chrome or Chromium installed.

Every page carries the credit the EpiCenter agreement asks for.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import markdown as md

CREDIT = "Source: California Department of Public Health, EpiCenter – California Injury Data Online"
BROWSERS = ("google-chrome", "chromium", "chromium-browser")

STYLE = (
    """
@page {
  size: Letter; margin: 15mm 19mm 16mm;
  @bottom-left { content: "%s"; font: 7.5pt "Helvetica Neue", Arial, sans-serif; color: #566772; }
  @bottom-right { content: "Page " counter(page) " of " counter(pages);
                  font: 7.5pt "Helvetica Neue", Arial, sans-serif; color: #566772; }
}
body { font: 10pt/1.4 "Helvetica Neue", Arial, sans-serif; color: #16222a; margin: 0; }
h1 { font-size: 20pt; line-height: 1.2; margin: 0 0 8pt; padding-top: 8pt;
     border-top: 3pt solid #0a6657; }
h2 { font-size: 13pt; margin: 14pt 0 4pt; break-after: avoid; }
h3 { font-size: 10.5pt; margin: 8pt 0 3pt; break-after: avoid; }
p, ul, ol { margin: 0 0 6pt; }
ul, ol { padding-left: 16pt; break-inside: avoid; } li { margin-bottom: 3pt; break-inside: avoid; }
p { orphans: 3; widows: 3; }
.box { background: #eef4f2; border-left: 3pt solid #0a6657; border-radius: 3pt;
       padding: 9pt 14pt 3pt; margin: 10pt 0 10pt; break-inside: avoid; }
.box h2 { margin-top: 0; font-size: 11.5pt; }
table { border-collapse: collapse; width: 100%%; font-size: 9pt; margin: 4pt 0 10pt;
        font-variant-numeric: tabular-nums; break-inside: avoid; }
th, td { border-bottom: 0.5pt solid #c3ced4; padding: 2pt 6pt; text-align: right; }
th { font-size: 8pt; text-transform: uppercase; letter-spacing: 0.04em; color: #566772;
     border-bottom: 1pt solid #16222a; vertical-align: bottom; }
th:first-child, td:first-child { text-align: left; padding-left: 0; font-weight: 600;
                                 white-space: nowrap; }
figure { margin: 4pt 0 6pt; break-inside: avoid; }
.keep { break-inside: avoid; }
table + p { break-before: avoid; }
figure svg { display: block; width: 74%%; height: auto; }
figcaption { margin-top: 4pt; }
blockquote { margin: 6pt 0 10pt; padding: 7pt 12pt; background: #f3f5f6;
             border-left: 3pt solid #c3ced4; break-inside: avoid; }
blockquote p { margin: 0 0 3pt; }
em { color: #566772; font-style: normal; font-size: 9pt; }
.appendix { border-top: 1pt solid #16222a; margin-top: 26pt; }
.appendix + h2 { margin-top: 12pt; }
code { font-size: 9pt; }
"""  # noqa: UP031 - the CSS is full of braces, which str.format would need doubled
    % CREDIT
)

# What stays on one page where it fits: a chart or table with the headings over it, a chart
# with the headings and the one paragraph or list between them, a table with its chart above
# and its note below, and any heading with the paragraph or list under it.  So a table is not
# carried over leaving its chart behind, and no heading ends a page.


def _block(tag: str) -> str:
    """One element, never running on past its own closing tag to a later one."""
    return rf"<{tag}>(?:(?!</{tag}>).)*</{tag}>"


_HEADS = rf"(?:{_block('h2')}\s*|{_block('h3')}\s*)"
_TABLE = rf"{_block('table')}(?:\s*{_block('p')})?"
_LIST = rf"(?:{_block('ul')}|{_block('blockquote')})"
_FIGURE = rf"{_block('figure')}(?:\s*{_TABLE})?"
KEPT = re.compile(
    rf"{_HEADS}+(?:{_block('p')}|{_block('ul')})\s*{_FIGURE}"
    rf"|{_HEADS}*(?:{_block('figure')}(?:\s*{_TABLE})?|{_TABLE}|{_block('p')}\s*{_LIST})"
    rf"|{_HEADS}+(?:{_block('p')}|{_block('ul')})",
    re.S,
)


def page(text: str, charts: dict[str, str]) -> str:
    """A report's Markdown as one HTML page, with its charts in place."""
    body = md.markdown(text, extensions=["tables", "sane_lists"])
    for name, svg in charts.items():
        marker = f"<!-- chart: {name} -->"
        if marker not in body:
            raise ValueError(f"the text has no place for the {name} chart")
        body = body.replace(marker, f"<figure>{svg}</figure>")
    # The note under a chart belongs to it, so the two stay on one page.
    body = re.sub(
        r"</figure>\s*<p>(.*?)</p>", r"<figcaption>\1</figcaption></figure>", body, flags=re.S
    )
    body = KEPT.sub(r'<div class="keep">\g<0></div>', body)
    if "<!-- chart:" in body:
        raise ValueError("the text asks for a chart that was not supplied")
    for marker, tag in (
        ("<!-- box -->", '<div class="box">'),
        ("<!-- /box -->", "</div>"),
        ("<!-- appendix -->", '<div class="appendix"></div>'),
    ):
        body = body.replace(marker, tag)
    return (
        f'<!doctype html><html lang="en"><meta charset="utf-8"><style>{STYLE}</style>{body}</html>'
    )


def write(name: str, text: str, charts: dict[str, str], out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{name}.pdf"
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / f"{name}.html"
        source.write_text(page(text, charts))
        print_url(source.as_uri(), target)
    return target


def print_url(url: str, target: Path, wait_ms: int = 0) -> Path:
    """Print a page to ``target`` with headless Chrome.

    ``wait_ms`` gives a page that draws itself with scripts, such as the crash map, time to
    finish first.  Each print gets a fresh browser profile: one Chrome locks a profile, so a
    shared one fails when another Chrome is running.
    """
    browser = next((found for b in BROWSERS if (found := shutil.which(b))), None)
    if browser is None:
        raise RuntimeError("printing a PDF needs Google Chrome or Chromium")
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run(
            [
                browser,
                "--headless=new",
                "--disable-gpu",
                "--no-first-run",
                f"--user-data-dir={profile}",
                "--no-pdf-header-footer",
                *([f"--virtual-time-budget={wait_ms}"] if wait_ms else []),
                f"--print-to-pdf={target}",
                url,
            ],
            check=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=300,
        )
    return target
