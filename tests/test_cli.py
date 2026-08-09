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
    # "yagi" used to match nothing; M5 added two, so this now needs a genuinely absent
    # family. Helical, log-periodic and Moxon antennas remain unmodelled.
    assert cli.main(["list", "--kind", "helical"]) == 0
    assert "No templates match" in capsys.readouterr().out


def test_list_finds_the_wire_antennas_m5_unlocked(capsys):
    """These waited from M0 to M5 for a model that could evaluate them."""
    assert cli.main(["list", "--kind", "yagi"]) == 0
    out = capsys.readouterr().out
    assert "graves-yagi-7el" in out and "graves-yagi-3el" in out

    assert cli.main(["list", "--band", "jove"]) == 0
    assert "radio-jove" in capsys.readouterr().out


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


# --------------------------------------------------------------------------------------
# M2: the fabricate subcommand
# --------------------------------------------------------------------------------------


def test_fabricate_writes_a_packet_and_reports_what_to_print(capsys, tmp_path):
    out = tmp_path / "horn15"
    assert cli.main(["fabricate", "--gain-dbi", "15", "--out", str(out), "--tool", "jigsaw"]) == 0
    text = capsys.readouterr().out
    assert "templates:" in text
    assert "E-flare panel" in text and "H-flare panel" in text
    assert "sheet(s)" in text
    assert "material:" in text
    # The scale warning is the whole point of a printed template.
    assert "Actual size" in text and "100 mm ruler" in text
    for name in ("cutlist.md", "assembly.md", "template.dxf", "design.json"):
        assert (out / name).exists()
    assert list(out.glob("*.svg"))


def test_fabricate_warns_when_the_template_needs_a_lot_of_taping(capsys, tmp_path):
    """A 22 dBi horn on A4 runs to dozens of sheets; say so rather than let it print."""
    assert cli.main(["fabricate", "--gain-dbi", "22", "--out", str(tmp_path / "big")]) == 0
    text = capsys.readouterr().out
    assert "sheets is a lot of taping" in text
    assert "--page a3" in text


def test_fabricate_conical_and_seam_allowance(capsys, tmp_path):
    out = tmp_path / "cone"
    assert (
        cli.main(
            [
                "fabricate",
                "--gain-dbi",
                "16",
                "--shape",
                "conical",
                "--out",
                str(out),
                "--seam-mm",
                "8",
                "--page",
                "a3",
            ]
        )
        == 0
    )
    assert "Cone wall" in capsys.readouterr().out
    assert "Roll the sector" in (out / "assembly.md").read_text()


def test_fabricate_respects_an_explicit_frequency(tmp_path):
    out = tmp_path / "oh"
    assert cli.main(["fabricate", "--gain-dbi", "14", "--freq-mhz", "1612", "--out", str(out)]) == 0
    payload = json.loads((out / "design.json").read_text())
    assert payload["freq_hz"] == pytest.approx(1.612e9)


# --------------------------------------------------------------------------------------
# M3: feed and probe subcommands
# --------------------------------------------------------------------------------------


def test_feed_says_what_feed_a_dish_wants(capsys):
    assert cli.main(["feed", "--f-over-d", "0.35"]) == 0
    out = capsys.readouterr().out
    assert "rim sits" in out
    assert "half-power beamwidth near" in out
    assert "eta_ap" in out


def test_feed_evaluates_a_named_beamwidth(capsys):
    assert cli.main(["feed", "--f-over-d", "0.4", "--feed-hpbw", "80"]) == 0
    out = capsys.readouterr().out
    assert "cos^2q model" in out
    assert "edge taper" in out and "optimum -10.9" in out
    assert "illumination efficiency" in out and "spillover efficiency" in out
    assert "best dish would be f/D" in out


def test_feed_evaluates_a_real_synthesized_horn(capsys):
    """The M1-to-M3 join, reachable from the command line."""
    assert cli.main(["feed", "--f-over-d", "0.35", "--horn-gain-dbi", "12"]) == 0
    out = capsys.readouterr().out
    assert "synthesized 12 dBi pyramidal horn" in out
    assert "not rotationally symmetric" in out  # the approximation is surfaced
    # A 12 dBi horn is too directive for an f/D 0.35 dish; the tool should say so.
    assert "outer dish is barely lit" in out


def test_probe_reproduces_the_published_build_from_the_command_line(capsys):
    assert cli.main(["probe", "--waveguide", "146x117"]) == 0
    out = capsys.readouterr().out
    assert "52.8 mm" in out  # probe length, free-space quarter wave
    assert "76.4 mm" in out  # backshort, quarter GUIDE wavelength
    assert "cutoff frequency" in out
    assert "common error" in out


def test_probe_refuses_a_waveguide_below_cutoff():
    with pytest.raises(ValueError, match="below this waveguide"):
        cli.main(["probe", "--waveguide", "50x25"])


# --------------------------------------------------------------------------------------
# M4: the sensitivity subcommand
# --------------------------------------------------------------------------------------


def test_sensitivity_from_a_catalog_template(capsys):
    assert cli.main(["sensitivity", "--template", "discovery-dish"]) == 0
    out = capsys.readouterr().out
    assert "Discovery Dish" in out
    assert "Tsys" in out and "dominated by" in out
    assert "SEFD" in out and "G/T" in out and "K/Jy" in out
    assert "ideal" in out and "feed (M3)" in out  # it fed the dish sensibly by default
    assert "not a measurement" in out


def test_sensitivity_from_an_arbitrary_dish_with_a_point_source(capsys):
    assert (
        cli.main(
            [
                "sensitivity",
                "--diameter-m",
                "3.0",
                "--f-over-d",
                "0.4",
                "--flux-jy",
                "1900",
                "--integration-s",
                "600",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "1900 Jy point source" in out
    assert "time to SNR 5" in out


def test_sensitivity_routes_extended_sources_correctly(capsys):
    """The CLI must not let the point-source formula flatter an HI estimate."""
    assert cli.main(["sensitivity", "--template", "discovery-dish", "--brightness-k", "100"]) == 0
    out = capsys.readouterr().out
    assert "100 K extended emission" in out
    assert "does NOT improve with a bigger aperture" in out
    assert "baseline stability" in out
    # A vast thermal SNR is reported as "not your limitation", not as a promise.
    assert "thermal noise is not your limitation" in out


def test_sensitivity_needs_an_antenna():
    with pytest.raises(SystemExit, match="either --template or --diameter-m"):
        cli.main(["sensitivity"])


def test_sensitivity_refuses_a_horn_template():
    with pytest.raises(SystemExit, match="needs a dish"):
        cli.main(["sensitivity", "--template", "bharat-horn"])


def test_a_worse_lna_raises_tsys(capsys):
    assert cli.main(["sensitivity", "--diameter-m", "1.0", "--lna-nf-db", "0.3"]) == 0
    good = capsys.readouterr().out
    assert cli.main(["sensitivity", "--diameter-m", "1.0", "--lna-nf-db", "3.0"]) == 0
    bad = capsys.readouterr().out

    def tsys_of(text):
        return float(text.split("Tsys ")[1].split(" K")[0])

    assert tsys_of(bad) > tsys_of(good) + 100


def test_sources_lists_the_catalogue_with_provenance(capsys):
    assert cli.main(["sources"]) == 0
    out = capsys.readouterr().out
    assert "cas-a" in out and "Cassiopeia A" in out
    assert "Perley & Butler 2017" in out  # every entry states where it came from
    assert "EPOCH-DEPENDENT" in out
    assert "epoch 2016" in out


def test_sensitivity_against_a_catalogued_source_at_an_epoch(capsys):
    assert (
        cli.main(
            [
                "sensitivity",
                "--template",
                "discovery-dish",
                "--source",
                "cas-a",
                "--epoch-year",
                "2026.6",
                "--integration-s",
                "600",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "Cassiopeia A" in out
    assert "Extrapolated" in out and "NOT constant" in out
    assert "arXiv:1609.05940" in out


def test_sensitivity_against_a_catalogued_extended_source(capsys):
    assert (
        cli.main(["sensitivity", "--template", "discovery-dish", "--source", "hi-inner-plane"]) == 0
    )
    out = capsys.readouterr().out
    assert "Galactic HI" in out
    assert "reads the AVERAGE" in out  # the beam-averaging correction reaches the user


# ---------------------------------------------------------------------------------------
# N0 -- reading a two-port
# ---------------------------------------------------------------------------------------

DEMO_S2P = """! demo amplifier, invented numbers
# HZ S RI R 50
1.3e9 -0.20 0.10   9.00 1.00   0.010 0.002  -0.30 0.05
1.4e9 -0.18 0.08  10.00 0.50   0.012 0.001  -0.28 0.04
1.5e9 -0.16 0.06   9.50 0.20   0.014 0.000  -0.26 0.03
1.3e9 0.30 0.45  40.0 0.20
1.4e9 0.32 0.44  45.0 0.21
1.5e9 0.35 0.43  50.0 0.22
"""


def test_network_reads_an_s2p_and_names_all_three_gains(tmp_path, capsys):
    path = tmp_path / "amp.s2p"
    path.write_text(DEMO_S2P)
    assert cli.main(["network", str(path)]) == 0
    out = capsys.readouterr().out
    assert "non-reciprocal (active)" in out
    # S21 must be reported as the gain and S12 as the isolation -- the ordering trap.
    assert "+20.01 dB" in out
    assert "transducer" in out and "available" in out and "operating" in out
    # And it must not claim they are equal when the device is mismatched.
    assert "S11 = S22 = 0" in out
    assert "Fmin" in out and "Gamma_opt" in out
    assert "NOT the best noise match" in out


def test_network_reports_a_chosen_frequency(tmp_path, capsys):
    path = tmp_path / "amp.s2p"
    path.write_text(DEMO_S2P)
    assert cli.main(["network", str(path), "--freq-mhz", "1300"]) == 0
    assert "at 1300.000 MHz" in capsys.readouterr().out


def test_network_says_so_when_a_file_carries_no_noise_data(tmp_path, capsys):
    path = tmp_path / "pad.s2p"
    path.write_text(
        "# HZ S RI R 50\n1.4e9 0 0 0.708 0 0.708 0 0 0\n1.5e9 0 0 0.708 0 0.708 0 0 0\n"
    )
    assert cli.main(["network", str(path)]) == 0
    out = capsys.readouterr().out
    assert "no noise block" in out
    assert "reciprocal (passive)" in out


def test_network_diagnoses_an_unstable_device_instead_of_crashing(tmp_path, capsys):
    """A potentially unstable part drives |Γin|, |Γout| past 1, where a gain is not a gain.

    The gain functions raise there rather than returning a negative power ratio, so the CLI
    has to catch it. Before the fix this was `ValueError: math domain error` from log10.
    """
    path = tmp_path / "unstable.s2p"
    path.write_text(
        "# HZ S MA R 50\n"
        "1.3e9 1.20 -60  3.0 120  0.15 70  1.10 -30\n"
        "1.4e9 1.20 -60  3.0 120  0.15 70  1.10 -30\n"
    )
    assert cli.main(["network", str(path)]) == 0
    out = capsys.readouterr().out
    assert "transducer" in out and "+9.5" in out  # this one is still defined
    assert out.count("undefined") == 2  # available and operating are not
    assert "returns more power than it receives" in out
    assert "N1's stability circles" in out


def test_network_reports_stability_for_an_amplifier(tmp_path, capsys):
    """N1's requirement: the check runs on any amplifier the tool touches, unasked."""
    path = tmp_path / "hfet.s2p"
    path.write_text(
        "! HP HFET-102, Pozar Example 12.1\n"
        "# HZ S MA R 50\n"
        "1.9e9 0.894 -60.6  3.122 123.6  0.020 62.4  0.781 -27.6\n"
        "2.0e9 0.894 -60.6  3.122 123.6  0.020 62.4  0.781 -27.6\n"
    )
    assert cli.main(["network", str(path), "--freq-mhz", "2000"]) == 0
    out = capsys.readouterr().out
    assert "stability (N1)" in out
    assert "POTENTIALLY UNSTABLE" in out
    assert "K = 0.607" in out and "0.696" in out  # the textbook numbers
    assert "source stability circle" in out and "load stability circle" in out
    assert "max stable gain (MSG)" in out and "21.93" in out
    assert "does not exist for a K < 1 device" in out  # MAG must not be substituted
    assert "does not mean the part is faulty" in out


def test_network_is_quiet_about_stability_for_a_passive_part(tmp_path, capsys):
    """A pad cannot oscillate, and telling someone so would be noise."""
    path = tmp_path / "pad.s2p"
    path.write_text(
        "# HZ S RI R 50\n1.4e9 0 0 0.708 0 0.708 0 0 0\n1.5e9 0 0 0.708 0 0.708 0 0 0\n"
    )
    assert cli.main(["network", str(path)]) == 0
    assert "stability (N1)" not in capsys.readouterr().out
