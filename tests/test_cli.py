"""Tests for the CLI — including the rule that a model's caveats are never suppressed."""

from __future__ import annotations

import json

import pytest

from jansky_forge import cli


def test_bands_lists_the_hydrogen_line_with_its_reason(capsys):
    assert cli.main(["bands"]) == 0
    out = capsys.readouterr().out
    assert "1420.4058 MHz" in out
    assert "Neutral hydrogen" in out
    assert "rotation curves" in out  # the 'why', not just the number
    assert "jove" in out and "graves" in out


def test_list_shows_the_catalog_and_filters(capsys):
    assert cli.main(["list"]) == 0
    assert "discovery-dish" in capsys.readouterr().out

    assert cli.main(["list", "--kind", "horn"]) == 0
    out = capsys.readouterr().out
    assert "bharat-horn" in out
    assert "discovery-dish" not in out

    assert cli.main(["list", "--band", "ku"]) == 0
    assert "itty-bitty" in capsys.readouterr().out


def test_list_says_so_when_nothing_matches(capsys):
    assert cli.main(["list", "--kind", "yagi"]) == 0  # wire antennas arrive at M5
    assert "No templates match" in capsys.readouterr().out


def test_show_prints_geometry_provenance_and_the_model_notes(capsys):
    assert cli.main(["show", "discovery-dish"]) == 0
    out = capsys.readouterr().out
    assert "diameter_m" in out
    assert "provenance" in out and "krakenrf" in out
    assert "caveats" in out
    # The honesty rule: a model's own warnings reach the user, always.
    assert "model notes" in out
    assert "aperture theory degrades" in out


def test_show_labels_published_figures_as_not_ours(capsys):
    """A source's numbers must never be presented as this tool's output."""
    assert cli.main(["show", "bharat-horn"]) == 0
    out = capsys.readouterr().out
    assert "published figures (cross-checks, not our output)" in out
    assert "gain_dbi" in out
    # And our own prediction is printed separately, under its own heading.
    assert "predicted performance" in out


def test_show_at_a_different_frequency(capsys):
    assert cli.main(["show", "discovery-dish", "--freq-mhz", "1667.359"]) == 0
    out = capsys.readouterr().out
    assert "1667.359 MHz" in out


def test_show_json_is_machine_readable_and_carries_the_caveats(capsys):
    assert cli.main(["show", "pictor", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["slug"] == "pictor"
    assert payload["parameters"]["diameter_m"] == 1.5
    assert payload["published"]["hpbw_deg"] == 8.95
    assert payload["characterization"]["hpbw_e_deg"] == pytest.approx(9.85, abs=0.05)
    # Caveats and model notes survive serialization — a JSON consumer sees the same honesty
    # a human reader does.
    assert any("63.6" in c for c in payload["caveats"])
    assert payload["characterization"]["notes"]


def test_characterize_across_several_frequencies(capsys):
    assert cli.main(["characterize", "salsa", "--band", "hi", "--freq-mhz", "1612"]) == 0
    out = capsys.readouterr().out
    assert "@ hi" in out
    assert "@ 1612 MHz" in out
    assert out.count("predicted performance") == 2


def test_characterize_defaults_to_the_design_band(capsys):
    assert cli.main(["characterize", "bharat-horn"]) == 0
    out = capsys.readouterr().out
    assert "@ hi" in out
    assert "1420.406 MHz" in out


def test_unknown_template_raises_with_alternatives():
    with pytest.raises(KeyError, match="known templates"):
        cli.main(["show", "not-a-real-antenna"])


def test_no_subcommand_is_an_error():
    with pytest.raises(SystemExit):
        cli.main([])
