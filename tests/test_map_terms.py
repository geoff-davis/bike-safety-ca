"""Every term the movement map marks has a definition to show."""

import re
from importlib import resources


def _template() -> str:
    return resources.files("bike_safety_ca.report").joinpath("movement_map.html").read_text()


def test_each_marked_term_has_a_definition() -> None:
    page = _template()
    glossary = re.search(r"const TIPS=\{(.*?)\n\};", page, re.S)
    assert glossary is not None
    defined = set(re.findall(r"^ (\w+):\"", glossary.group(1), re.M))
    used = set(re.findall(r"TIPS\.(\w+)", page)) | set(re.findall(r'data-term="(\w+)"', page))
    assert used, "the map marks no terms"
    assert used <= defined, f"no definition for {sorted(used - defined)}"
    assert defined <= used, f"defined but never shown: {sorted(defined - used)}"


def test_the_tooltip_box_and_its_script_are_on_the_page() -> None:
    page = _template()
    assert '<div id="tip" role="tooltip" hidden></div>' in page
    assert 'closest("[data-tip]")' in page
    # Printed views leave the box and the dotted underlines out.
    assert re.search(
        r"@media print\{\s*#tip\{display:none!important\}\[data-tip\]\{border:0\}", page
    )
