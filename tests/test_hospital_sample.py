"""The made-up county report shown in the README."""

from __future__ import annotations

import pytest

from bike_safety_ca.hospital import pdf, population, report, sample


def test_the_sample_report_says_it_is_made_up_and_credits_no_one(tmp_path):
    before = (population.COUNTIES, population.NAMES, pdf.STYLE)
    text, charts = sample.markdown(tmp_path)
    assert text.startswith("# Bicycle injuries treated in hospital: Sample County")
    assert text.count(sample.NOTICE) == 2  # under the title, and as the source
    assert "California Department of Public Health" not in text
    assert "as published by EpiCenter" not in text
    assert "Residents are the Census Bureau's" not in text
    assert report.SHARING not in text
    # The real report code holds back a group beside the hidden under-one cell.
    assert "| 5–9 | not shown | not shown | not shown | not shown |" in text
    assert set(charts) == {"yearly"}
    assert (population.COUNTIES, population.NAMES, pdf.STYLE) == before


def test_the_made_up_state_keeps_the_credit_off_the_pdf():
    with sample.made_up_state():
        assert pdf.CREDIT not in pdf.STYLE
        assert population.NAMES == tuple(sample.RESIDENTS)
    assert pdf.CREDIT in pdf.STYLE


def test_the_made_up_visits_by_year_add_up_to_the_age_table():
    hidden = 5  # the made-up value of the one hidden visits cell
    yearly = sum(c or 0 for c in sample.UNDER_18 + sample.ADULT)
    assert yearly == sum(c or 0 for c in sample.VISITS) + hidden


def test_the_sample_command_writes_the_report(tmp_path):
    sample.main(["--out", str(tmp_path)])
    text = (tmp_path / "hospital_sample.md").read_text()
    assert sample.NOTICE in text and report.CREDIT not in text


@pytest.mark.parametrize(
    "name, changed, message",
    [
        ("SHARING", "A sharing note the report no longer prints.", "credit or sharing"),
        ("CREDIT", "*A credit the report no longer prints.*", "credit or sharing"),
    ],
)
def test_the_sample_refuses_a_report_whose_wording_has_moved(
    tmp_path, monkeypatch, name, changed, message
):
    real = getattr(report, name)
    monkeypatch.setattr(report, "markdown", _without(report.markdown, real))
    with pytest.raises(ValueError, match=message):
        sample.markdown(tmp_path)


def test_the_sample_refuses_a_report_without_its_source_paragraph(tmp_path, monkeypatch):
    monkeypatch.setattr(report, "markdown", _without(report.markdown, "**Source.**"))
    with pytest.raises(ValueError, match="source paragraph"):
        sample.markdown(tmp_path)


def test_the_sample_refuses_a_report_whose_appendix_has_moved(tmp_path, monkeypatch):
    monkeypatch.setattr(report, "markdown", _without(report.markdown, "as published by EpiCenter."))
    with pytest.raises(ValueError, match="appendix"):
        sample.markdown(tmp_path)


def _without(make, real):
    def changed(*args, **kwargs):
        text, charts = make(*args, **kwargs)
        return text.replace(real, "(reworded)"), charts

    return changed
