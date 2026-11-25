import pytest

from bike_safety_ca.hospital import epicenter


def _files():
    return [
        f"{outcome}_{name}.csv"
        for outcome in epicenter.OUTCOMES
        for _county, _years, queries in epicenter.scopes("Alder")
        for name, _ages, _groups, outcomes in queries
        if outcome in (outcomes or ("ed", "hosp"))
    ]


def test_query_output_files_are_unique():
    files = _files()
    assert len(files) == len(set(files))


def test_every_hospitalization_outcome_pins_a_case_definition():
    for ids in epicenter.OUTCOMES.values():
        if ids["tab"] == "Hospitalizations":
            assert ids["case_definition"] in epicenter.CASE_DEFINITION_TEXT


def test_surveillance_queries_have_comprehensive_counterparts():
    files = set(_files())
    for f in files:
        if f.startswith("hosp_surveillance_"):
            assert f.replace("hosp_surveillance_", "hosp_") in files


def test_csv_drops_select_column_and_blanks_suppressed_counts():
    result = {"columns": ["Select", "Year", "Count"], "rows": [["", 2016, 12], ["", 2017, None]]}
    assert epicenter._csv(result) == "Year,Count\n2016,12\n2017,\n"


def test_statewide_queries_are_named_apart_from_county_ones():
    assert all(name.startswith("state_") for name, *_ in epicenter.STATEWIDE_QUERIES)
    assert not any(name.startswith("state_") for name, *_ in epicenter.QUERIES)


SUMMARY = (
    "Currently displaying 4,321 non-fatal injury ED visits from 2016 to 2024 among "
    "Californians aged 0 to 17 years, filtered by:\n"
)
BIKE_FILTERS = "Injury Intent: Unintentional\nInjury Mechanism: " + ", ".join(epicenter.BIKE)


def _read(filter_text, groups=("Year",), busy=False):
    return {"busy": busy, "columns": ["Select", *groups, "Count"], "filter": filter_text}


def _accepts(result, county="Alder"):
    return epicenter.accepts(result, ["Year"], (0, 17), (2016, 2024), county)


def test_a_table_with_exactly_the_requested_filters_is_accepted():
    assert _accepts(_read(SUMMARY + "County of Residence: Alder\n" + BIKE_FILTERS))
    assert _accepts(_read(SUMMARY + BIKE_FILTERS), county=None)


def test_an_extra_county_or_any_extra_filter_is_refused():
    assert not _accepts(_read(SUMMARY + "County of Residence: Alder, Birch\n" + BIKE_FILTERS))
    assert not _accepts(_read(SUMMARY + "County of Residence: Alder\nSex: Male\n" + BIKE_FILTERS))
    extra = BIKE_FILTERS + ", Fall"
    assert not _accepts(_read(SUMMARY + "County of Residence: Alder\n" + extra))


def test_a_county_table_is_refused_for_a_statewide_query_and_the_reverse():
    county = _read(SUMMARY + "County of Residence: Alder\n" + BIKE_FILTERS)
    assert not _accepts(county, county=None)
    assert not _accepts(_read(SUMMARY + BIKE_FILTERS))


def test_wrong_ages_years_grouping_or_a_busy_page_are_refused():
    good = SUMMARY + "County of Residence: Alder\n" + BIKE_FILTERS
    assert not _accepts(_read(good.replace("aged 0 to 17 ", "aged 0 to 170 ")))
    assert not _accepts(_read(good.replace("2016 to 2024", "2016 to 2023")))
    assert not _accepts(_read(good, groups=("Sex",)))
    assert not _accepts(_read(good, busy=True))


def test_the_case_definition_must_be_the_one_asked_for():
    text = SUMMARY.replace("4,321", "115 surveillance case definition")
    text += "County of Residence: Alder\n" + BIKE_FILTERS
    args = (["Year"], (0, 17), (2016, 2024), "Alder")
    assert epicenter.accepts(_read(text), *args, "surveillance case definition")
    assert not epicenter.accepts(_read(text), *args, "comprehensive case definition")


def test_a_filter_named_twice_or_an_unreadable_line_is_refused():
    twice = "County of Residence: Birch\nCounty of Residence: Alder\n" + BIKE_FILTERS
    assert not _accepts(_read(SUMMARY + twice))
    assert not _accepts(_read(SUMMARY + "County of Residence: Alder\nand others\n" + BIKE_FILTERS))


def test_reading_filters_refuses_text_it_cannot_read_cleanly():
    assert (
        epicenter.filters(SUMMARY + "County of Residence: Alder\n" + BIKE_FILTERS)[
            "County of Residence"
        ]
        == "Alder"
    )
    with pytest.raises(ValueError):
        epicenter.filters(SUMMARY + "County of Residence: A\nCounty of Residence: B")


class Stop(Exception):
    """Ends a fake run at the first step after the agreement."""


class FakePage:
    """Stands in for a Playwright page showing the agreement; records what is asked of it."""

    def __init__(self, agreed, closes=True):
        self.agreed = agreed
        self.closes = closes
        self.calls = []

    def add_init_script(self, script):
        self.calls.append(("init", script))

    def goto(self, url, **kwargs):
        self.calls.append(("goto", url))

    def wait_for_function(self, script, timeout=0):
        self.calls.append(("function", script))

    def wait_for_selector(self, selector, state="visible", timeout=0):
        self.calls.append(("wait", selector, state))
        if state == "hidden" and not self.closes:
            raise TimeoutError("agreement still open")

    def wait_for_timeout(self, ms):
        pass

    def evaluate(self, script, *args):
        self.calls.append(("evaluate", script))
        return self.agreed if script == epicenter._AGREED else None

    def click(self, selector, **kwargs):
        # The agreement is never clicked; the first tab click ends the fake run.
        assert "shiny-modal" not in selector and "Agree" not in selector
        self.calls.append(("click", selector))
        raise Stop


def test_an_agreement_closed_without_i_agree_stops_the_pull():
    with pytest.raises(RuntimeError, match="without"):
        epicenter.await_agreement(FakePage(agreed=None), timeout_ms=1)


def test_the_pull_waits_for_the_agreement_to_show_before_waiting_for_it_to_close():
    # It fades in: waiting for "hidden" before it is visible would end at once.
    page = FakePage(agreed=None)
    with pytest.raises(RuntimeError):
        epicenter.await_agreement(page, timeout_ms=1)
    waits = [c for c in page.calls if c[0] in ("wait", "function")]
    assert waits == [
        ("function", epicenter._SHOWN_OR_AGREED),
        ("function", epicenter._VISIBLE_OR_AGREED),  # visible or already agreed, in one wait
        ("wait", "#shiny-modal", "hidden"),
    ]
    assert "__bscAgreed === true" in epicenter._VISIBLE_OR_AGREED


def test_an_agreement_left_open_stops_the_pull():
    with pytest.raises(TimeoutError):
        epicenter.await_agreement(FakePage(agreed=True, closes=False), timeout_ms=1)


def test_the_agreement_watch_counts_only_a_persons_click_on_i_agree():
    script = epicenter._WATCH_AGREEMENT
    assert "e.isTrusted" in script  # a script's .click() is not trusted
    assert "=== 'I Agree'" in script and "includes(" not in script
    assert "#shiny-modal button" in script
    assert ".click(" not in script


def _fake_playwright(monkeypatch, page, launched):
    import sys
    import types

    class Browser:
        def new_page(self, **kwargs):
            return page

        def close(self):
            pass

    class Chromium:
        def launch(self, **kwargs):
            launched.update(kwargs)
            return Browser()

    class Playwright:
        chromium = Chromium()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    fake = types.ModuleType("playwright.sync_api")
    fake.sync_playwright = Playwright  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake)


def test_the_pull_waits_for_the_persons_agreement_in_a_visible_browser(tmp_path, monkeypatch):
    launched: dict = {}
    page = FakePage(agreed=True)
    _fake_playwright(monkeypatch, page, launched)
    with pytest.raises(Stop):
        epicenter.download("Alder", tmp_path)
    assert launched["headless"] is False
    steps = [c[0] for c in page.calls]
    # Watching before the site loads, the agreement checked before the first tab is touched.
    assert page.calls[0] == ("init", epicenter._WATCH_AGREEMENT)
    assert steps.index("init") < steps.index("goto")
    assert page.calls.index(("evaluate", epicenter._AGREED)) < steps.index("click")


def test_the_pull_stops_before_any_table_without_the_persons_agreement(tmp_path, monkeypatch):
    page = FakePage(agreed=False)
    _fake_playwright(monkeypatch, page, {})
    with pytest.raises(RuntimeError, match="without"):
        epicenter.download("Alder", tmp_path)
    assert not [c for c in page.calls if c[0] == "click"]
    assert not list(tmp_path.iterdir())


def test_the_default_plan_pulls_six_tables_and_skips_the_surveillance_tab():
    pulled = [
        f"{outcome}_{q[0]}"
        for outcome, scoped in epicenter.plan("Alder", names=epicenter.REPORT_TABLES)
        for _where, _span, queries in scoped
        for q in queries
    ]
    assert sorted(pulled) == sorted(epicenter.REPORT_TABLES)
    tabs = [outcome for outcome, _ in epicenter.plan("Alder", names=epicenter.REPORT_TABLES)]
    assert tabs == ["ed", "hosp"]


def test_the_full_plan_is_every_table_once():
    names = epicenter.table_names()
    assert len(names) == len(set(names)) == len(_files())
    assert {f"{n}.csv" for n in names} == set(_files())


def test_statewide_tables_are_pulled_statewide_and_county_ones_for_the_county():
    for _outcome, scoped in epicenter.plan("Alder", names=epicenter.REPORT_TABLES):
        for where, span, queries in scoped:
            for q in queries:
                state = q[0].startswith("state_")
                assert (where is None) == state
                # Trends span the county years; the rest of the statewide tables, 2023-2024.
                trend = q[0].startswith("state_trend_")
                assert span == (
                    epicenter.STATEWIDE_YEARS if state and not trend else epicenter.YEARS
                )
