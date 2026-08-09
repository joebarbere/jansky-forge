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


def test_output_uses_the_scientific_characters_it_means(capsys):
    """The output genuinely contains λ, ° and ² — spelling them out would be the wrong fix.

    Windows consoles default to cp1252 and cannot encode these, which crashed the CLI until
    `_ensure_utf8_stdout` reconfigured the stream. This asserts the characters are still
    there, so nobody "fixes" a future encoding report by degrading the output instead.
    """
    assert cli.main(["show", "discovery-dish"]) == 0
    out = capsys.readouterr().out
    assert "°" in out  # beamwidths
    assert "²" in out  # effective area, m²
    assert "λ" in out  # the model's electrically-small note


def test_utf8_reconfiguration_tolerates_a_stream_that_cannot_do_it(monkeypatch):
    """A captured or replaced stdout need not support reconfigure; that must not crash."""

    class PlainStream:
        def write(self, _s: str) -> int:
            return 0

    monkeypatch.setattr("sys.stdout", PlainStream())
    cli._ensure_utf8_stdout()  # no reconfigure attribute — returns quietly

    class FussyStream(PlainStream):
        def reconfigure(self, **_kwargs: object) -> None:
            raise ValueError("this stream refuses")

    monkeypatch.setattr("sys.stdout", FussyStream())
    cli._ensure_utf8_stdout()  # raises internally, swallowed


# --------------------------------------------------------------------------------------
# M1: the design subcommand
# --------------------------------------------------------------------------------------


def test_design_prints_buildable_pyramidal_dimensions(capsys):
    assert cli.main(["design", "--gain-dbi", "18"]) == 0
    out = capsys.readouterr().out
    assert "Optimum pyramidal horn" in out
    assert "18.00 dBi" in out
    # The numbers a builder needs, and the realizability reassurance.
    assert "aperture a1 (H-plane, wide)" in out
    assert "axial length (p_e = p_h)" in out
    assert "phase deviation s / t" in out
    assert "0.2500 / 0.3750" in out  # landed exactly on the optimum flare
    assert "buildable as a single horn" in out


def test_design_conical_and_band_selection(capsys):
    assert cli.main(["design", "--gain-dbi", "20", "--shape", "conical", "--band", "oh1667"]) == 0
    out = capsys.readouterr().out
    assert "Optimum conical horn" in out
    assert "1667.359 MHz" in out
    assert "slant (apex to rim)" in out
    # Honest about the model behind it.
    assert "empirical loss figure" in out


def test_design_accepts_an_explicit_frequency_and_custom_waveguide(capsys):
    assert (
        cli.main(["design", "--gain-dbi", "22.6", "--freq-mhz", "11000", "--waveguide", "wr90"])
        == 0
    )
    out = capsys.readouterr().out
    assert "11000.000 MHz" in out
    assert "22.9 x 10.2 mm" in out  # WR-90 internal dimensions, printed to 0.1 mm

    # And free-form 'AxB' in millimetres.
    assert cli.main(["design", "--gain-dbi", "15", "--waveguide", "165.1x82.55"]) == 0
    assert "165.1 x 82.5 mm" in capsys.readouterr().out


def test_design_rejects_an_unknown_waveguide():
    with pytest.raises(SystemExit, match="unrecognized waveguide"):
        cli.main(["design", "--gain-dbi", "18", "--waveguide", "banana"])


def test_design_refuses_a_gain_no_horn_can_deliver():
    with pytest.raises(ValueError, match="reflector"):
        cli.main(["design", "--gain-dbi", "55"])


def test_show_reports_the_non_buildable_catalog_entry(capsys):
    """The CLI must surface a realizability failure, not bury it."""
    assert cli.main(["show", "horn-18dbi-worked"]) == 0
    out = capsys.readouterr().out
    assert "NOT a single buildable pyramidal horn" in out
    assert "phase_deviation_e" in out
