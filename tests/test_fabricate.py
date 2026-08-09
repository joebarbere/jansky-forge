"""Tests for M2 fabrication.

These matter more than most: their output becomes cut metal, and a wrong number here is not
a wrong plot, it is a wasted sheet of aluminium. So the checks are dimensional and
independent — a development is verified against the horn geometry it came from, not against
itself.
"""

from __future__ import annotations

import json
import math
import re

import pytest

from jansky_forge.fabricate import (
    TYPICAL_KERF_MM,
    Panel,
    build_cutlist,
    conical_development,
    development_dxf,
    plan_tiling,
    pyramidal_development,
    render_pages,
    thickness_note,
    write_packet,
)
from jansky_forge.horns import design_conical_horn, design_pyramidal_horn

HI_HZ = 1_420_405_751.768
WR650_A, WR650_B = 0.1651, 0.08255


# --------------------------------------------------------------------------------------
# Pyramidal development
# --------------------------------------------------------------------------------------


def test_panels_have_the_frustum_slant_heights():
    """Panel heights are the frustum slant in each flare plane, computed by hand here."""
    dev = pyramidal_development(
        waveguide_a_m=0.100,
        waveguide_b_m=0.050,
        aperture_a1_m=0.300,
        aperture_b1_m=0.200,
        axial_length_m=0.400,
    )
    # E-flare panel (top/bottom): parallel sides a and a1, height sqrt(L^2+((b1-b)/2)^2)
    #   = sqrt(400^2 + 75^2) = 406.97 mm
    e_panel = dev.panels[0]
    assert e_panel.size_mm[1] == pytest.approx(math.hypot(400.0, 75.0), abs=1e-6)
    assert e_panel.size_mm[0] == pytest.approx(300.0)  # widest edge is the aperture
    # H-flare panel: parallel sides b and b1, height sqrt(400^2 + 100^2) = 412.31 mm
    h_panel = dev.panels[1]
    assert h_panel.size_mm[1] == pytest.approx(math.hypot(400.0, 100.0), abs=1e-6)
    assert h_panel.size_mm[0] == pytest.approx(200.0)
    assert e_panel.quantity == 2 and h_panel.quantity == 2


def test_the_corner_edge_agrees_measured_on_either_panel():
    """The constraint that decides whether four shapes assemble into a horn.

    Adjacent panels share a corner edge. Measured across the E panel it is
    hypot(height_E, (a1-a)/2); across the H panel, hypot(height_H, (b1-b)/2). If those
    disagree the parts cannot meet, and no amount of careful cutting will save them.
    """
    a, b, a1, b1, length = 100.0, 50.0, 300.0, 200.0, 400.0
    dev = pyramidal_development(
        waveguide_a_m=a / 1000,
        waveguide_b_m=b / 1000,
        aperture_a1_m=a1 / 1000,
        aperture_b1_m=b1 / 1000,
        axial_length_m=length / 1000,
    )
    height_e, height_h = dev.panels[0].size_mm[1], dev.panels[1].size_mm[1]
    from_e = math.hypot(height_e, (a1 - a) / 2)
    from_h = math.hypot(height_h, (b1 - b) / 2)
    assert from_e == pytest.approx(from_h, rel=1e-12)
    assert dev.key_dimensions["corner_edge_mm"] == pytest.approx(from_e)
    # And it equals the direct 3-D diagonal.
    assert from_e == pytest.approx(math.sqrt(length**2 + ((a1 - a) / 2) ** 2 + ((b1 - b) / 2) ** 2))


def test_development_matches_the_design_it_came_from():
    """End to end: synthesize a horn, unroll it, and check against the design's own numbers."""
    design = design_pyramidal_horn(
        gain_dbi=18.0, freq_hz=HI_HZ, waveguide_a_m=WR650_A, waveguide_b_m=WR650_B
    )
    dev = pyramidal_development(
        waveguide_a_m=design.waveguide_a_m,
        waveguide_b_m=design.waveguide_b_m,
        aperture_a1_m=design.aperture_a1_m,
        aperture_b1_m=design.aperture_b1_m,
        axial_length_m=design.axial_length_m,
    )
    assert dev.key_dimensions["aperture_a1_mm"] == pytest.approx(design.aperture_a1_m * 1000)
    assert dev.key_dimensions["axial_length_mm"] == pytest.approx(design.axial_length_m * 1000)
    # Independent route to the panel height: Balanis' slant scaled by L/rho1.
    expected_e = design.slant_e_m * design.axial_length_m / design.rho1_m * 1000
    assert dev.key_dimensions["panel_height_e_mm"] == pytest.approx(expected_e, rel=1e-9)


def test_seam_allowance_widens_only_the_sloped_edges():
    """Throat and aperture edges keep their electrical length; the slopes gain a flange."""
    plain = pyramidal_development(
        waveguide_a_m=0.1,
        waveguide_b_m=0.05,
        aperture_a1_m=0.3,
        aperture_b1_m=0.2,
        axial_length_m=0.4,
    )
    seamed = pyramidal_development(
        waveguide_a_m=0.1,
        waveguide_b_m=0.05,
        aperture_a1_m=0.3,
        aperture_b1_m=0.2,
        axial_length_m=0.4,
        seam_allowance_mm=10.0,
    )
    # Height (throat-to-aperture) is unchanged: the allowance is not on those edges.
    assert seamed.panels[0].size_mm[1] == pytest.approx(plain.panels[0].size_mm[1])
    assert seamed.panels[0].size_mm[0] > plain.panels[0].size_mm[0]
    # The fold polygon still carries the electrical outline.
    assert seamed.panels[0].fold_polygon == plain.panels[0].polygon
    # The flange is a true perpendicular 10 mm, not 10 mm of horizontal shift: for this
    # panel the sloped edge tilts by atan(100/406.97), so the horizontal offset is larger.
    grew = (seamed.panels[0].size_mm[0] - plain.panels[0].size_mm[0]) / 2
    assert grew > 10.0
    assert grew == pytest.approx(10.0 * math.hypot(406.9705, 100.0) / 406.9705, rel=1e-6)


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(waveguide_a_m=0.3, aperture_a1_m=0.2),  # aperture must exceed waveguide
        dict(waveguide_b_m=0.3, aperture_b1_m=0.2),
        dict(axial_length_m=0.0),
    ],
)
def test_pyramidal_development_rejects_impossible_geometry(kwargs):
    base = dict(
        waveguide_a_m=0.1,
        waveguide_b_m=0.05,
        aperture_a1_m=0.3,
        aperture_b1_m=0.2,
        axial_length_m=0.4,
    )
    with pytest.raises(ValueError):
        pyramidal_development(**(base | kwargs))


# --------------------------------------------------------------------------------------
# Conical development
# --------------------------------------------------------------------------------------


def test_cone_sector_arcs_equal_the_real_circumferences():
    """The check that proves the unrolling: both arcs must match the circles they become.

    The sector angle is chosen so the OUTER arc equals the aperture circumference. The
    inner arc then matching the throat circumference is not something we imposed — it
    follows from similar triangles, so it is a genuine test of the development.
    """
    dev = conical_development(aperture_diameter_m=0.4, slant_m=0.6, throat_diameter_m=0.1)
    sector = dev.sectors[0]
    angle = math.radians(sector.angle_deg)
    assert angle * sector.outer_radius_mm == pytest.approx(math.pi * 400.0)
    assert angle * sector.inner_radius_mm == pytest.approx(math.pi * 100.0)
    assert sector.angle_deg == pytest.approx(120.0)  # 2*pi*200/600 rad = 120 deg


def test_cone_with_no_throat_develops_to_a_point_and_says_so():
    dev = conical_development(aperture_diameter_m=0.4, slant_m=0.6)
    assert dev.sectors[0].inner_radius_mm == 0.0
    assert any("full cone to a point" in n for n in dev.notes)


def test_cone_sector_area_is_exact_not_polygonal():
    """Area comes from the annulus formula, so it does not drift with the polygon count."""
    sector = conical_development(
        aperture_diameter_m=0.4, slant_m=0.6, throat_diameter_m=0.1
    ).sectors[0]
    expected = (120.0 / 360.0) * math.pi * (600.0**2 - 150.0**2)
    assert sector.area_mm2 == pytest.approx(expected)


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(aperture_diameter_m=0.0),
        dict(slant_m=0.1),  # slant below the aperture radius is geometrically impossible
    ],
)
def test_conical_development_rejects_impossible_geometry(kwargs):
    with pytest.raises(ValueError):
        conical_development(**(dict(aperture_diameter_m=0.4, slant_m=0.6) | kwargs))


def test_sector_rejects_a_full_turn():
    with pytest.raises(ValueError, match="in .0, 360."):
        from jansky_forge.fabricate import AnnularSector

        AnnularSector(label="x", inner_radius_mm=0, outer_radius_mm=10, angle_deg=360.0)


# --------------------------------------------------------------------------------------
# Panel primitives
# --------------------------------------------------------------------------------------


def test_panel_area_and_perimeter_of_a_known_trapezoid():
    # Trapezoid with parallel sides 100 and 200, height 50: area = (100+200)/2*50 = 7500
    panel = Panel(label="t", polygon=((-50, 0), (50, 0), (100, 50), (-100, 50)), quantity=1)
    assert panel.area_mm2 == pytest.approx(7500.0)
    slope = math.hypot(50.0, 50.0)
    assert panel.perimeter_mm == pytest.approx(100.0 + 200.0 + 2 * slope)
    assert panel.size_mm == pytest.approx((200.0, 50.0))


def test_panel_rejects_degenerate_definitions():
    with pytest.raises(ValueError, match="at least 3 points"):
        Panel(label="t", polygon=((0, 0), (1, 1)), quantity=1)
    with pytest.raises(ValueError, match="quantity"):
        Panel(label="t", polygon=((0, 0), (1, 0), (1, 1)), quantity=0)


# --------------------------------------------------------------------------------------
# SVG: the scale promise
# --------------------------------------------------------------------------------------


def _one_page(dev):
    return render_pages(dev)[0].files[0][1]


SMALL = dict(
    waveguide_a_m=0.05,
    waveguide_b_m=0.025,
    aperture_a1_m=0.12,
    aperture_b1_m=0.09,
    axial_length_m=0.10,
)


def test_svg_is_exactly_one_to_one_in_millimetres():
    """One user unit must be one millimetre, or every printed template is wrong."""
    svg = _one_page(pyramidal_development(**SMALL))
    m = re.search(r'width="([\d.]+)mm" height="([\d.]+)mm" viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    assert m, "SVG must declare physical mm size and a matching viewBox"
    width_mm, height_mm, view_w, view_h = map(float, m.groups())
    assert width_mm / view_w == pytest.approx(1.0)
    assert height_mm / view_h == pytest.approx(1.0)


def test_drawn_panel_measures_its_real_dimensions():
    svg = _one_page(pyramidal_development(**SMALL))
    coords = re.search(r'class="cut" d="M ([^"]+)"', svg).group(1)
    points = [
        tuple(map(float, token.replace("M", "").split()))
        for token in coords.replace("Z", "").split("L")
    ]
    # Path coordinates are written to 3 decimals — a micron, far below any cutting
    # tolerance — so compare at that precision rather than to floating-point exactness.
    assert abs(points[1][0] - points[0][0]) == pytest.approx(50.0, abs=1e-3)  # throat edge
    assert abs(points[2][0] - points[3][0]) == pytest.approx(120.0, abs=1e-3)  # aperture
    assert abs(points[2][1] - points[1][1]) == pytest.approx(math.hypot(100.0, 32.5), abs=1e-3)


def test_every_page_carries_a_ruler_that_is_actually_100mm():
    """The guard against a 'fit to page' print. It has to be right or it is worse than none."""
    for _, svg in render_pages(pyramidal_development(**SMALL))[0].files:
        ruler = re.search(r'class="ruler" d="M ([\d.]+) ([\d.]+) L ([\d.]+) ([\d.]+)"', svg)
        assert ruler, "every sheet must carry the scale check"
        x0, y0, x1, y1 = map(float, ruler.groups())
        assert x1 - x0 == pytest.approx(100.0)
        assert y0 == y1
        assert "MEASURE THIS LINE" in svg
        assert "Actual size" in svg


def test_multi_sheet_templates_get_registration_and_overlap_guides():
    big = pyramidal_development(
        waveguide_a_m=0.1,
        waveguide_b_m=0.05,
        aperture_a1_m=0.8,
        aperture_b1_m=0.6,
        axial_length_m=0.7,
    )
    rendered = render_pages(big)[0]
    assert rendered.tiling.pages > 1
    first = rendered.files[0][1]
    assert 'class="reg"' in first  # corner crop marks
    assert 'class="overlap"' in first  # where the next sheet lands
    assert "sheet 1 of" in first
    # Sheet names are ordered so taping them together is unambiguous.
    assert [n for n, _ in rendered.files][:2] == [
        f"{rendered.slug}-sheet-01.svg",
        f"{rendered.slug}-sheet-02.svg",
    ]


def test_each_shape_gets_its_own_template_set():
    """Not one giant composite: a builder prints the panel they are about to cut."""
    rendered = render_pages(pyramidal_development(**SMALL))
    assert len(rendered) == 2
    assert {r.label for r in rendered} == {
        "E-flare panel (top / bottom)",
        "H-flare panel (left / right)",
    }
    assert all(r.quantity == 2 for r in rendered)


def test_tiling_arithmetic_accounts_for_overlap():
    # 400 mm wide on A4 (190 mm usable, 15 mm overlap -> 175 mm of new area per sheet):
    # ceil((400-15)/175) = 3 columns.
    tiling = plan_tiling(400.0, 100.0, page="a4")
    assert (tiling.columns, tiling.rows) == (3, 1)
    assert plan_tiling(100.0, 100.0, page="a4").pages == 1
    # Landscape swaps the page, changing the split.
    assert plan_tiling(400.0, 100.0, page="a4", landscape=True).columns == 2


def test_tiling_rejects_nonsense():
    with pytest.raises(KeyError, match="known"):
        plan_tiling(100, 100, page="a0")
    with pytest.raises(ValueError, match="no usable area"):
        plan_tiling(100, 100, page="a4", margin_mm=100.0)


# --------------------------------------------------------------------------------------
# DXF
# --------------------------------------------------------------------------------------


def test_dxf_declares_millimetres_and_separates_cut_from_fold():
    dev = pyramidal_development(**SMALL, seam_allowance_mm=8.0)
    text = development_dxf(dev)
    assert "$INSUNITS" in text and "\n4\n" in text  # 4 = millimetres
    assert "CUT" in text and "FOLD" in text
    assert text.rstrip().endswith("EOF")


def test_dxf_emits_true_arcs_for_a_cone():
    text = development_dxf(
        conical_development(aperture_diameter_m=0.4, slant_m=0.6, throat_diameter_m=0.1)
    )
    assert text.count("\nARC\n") == 2  # outer and inner
    assert text.count("\nLINE\n") == 2  # the two radial edges
    radii = [float(v) for v in re.findall(r"\n40\n([\d.]+)\n", text)]
    assert sorted(radii) == pytest.approx([150.0, 600.0])


def test_dxf_cone_without_a_throat_closes_on_the_apex():
    text = development_dxf(conical_development(aperture_diameter_m=0.4, slant_m=0.6))
    assert text.count("\nARC\n") == 1
    assert text.count("\nLINE\n") == 2


# --------------------------------------------------------------------------------------
# Cut list, kerf, BOM
# --------------------------------------------------------------------------------------


def test_cutlist_totals_and_kerf_budget():
    dev = pyramidal_development(**SMALL)
    cut = build_cutlist(dev, tool="jigsaw")
    assert cut.kerf_mm == TYPICAL_KERF_MM["jigsaw"]
    assert cut.kerf_area_mm2 == pytest.approx(dev.total_cut_length_mm * 1.5)
    # Quantities are carried through: two of each panel.
    assert sum(i.quantity for i in cut.items) == 4
    assert cut.total_area_mm2 == pytest.approx(sum(p.area_mm2 * p.quantity for p in dev.panels))


def test_shears_are_zero_kerf_and_the_note_says_what_that_means():
    cut = build_cutlist(pyramidal_development(**SMALL), tool="shears")
    assert cut.kerf_mm == 0.0
    assert any("displace rather than remove" in n for n in cut.notes)


def test_nonzero_kerf_warns_about_double_compensation():
    cut = build_cutlist(pyramidal_development(**SMALL), tool="laser")
    assert any("apply it twice" in n for n in cut.notes)


def test_cutlist_rejects_a_bad_tool_or_negative_kerf():
    dev = pyramidal_development(**SMALL)
    with pytest.raises(KeyError, match="known"):
        build_cutlist(dev, tool="lightsaber")
    with pytest.raises(ValueError, match="negative"):
        build_cutlist(dev, kerf_mm=-1.0)


def test_cutlist_markdown_is_a_checklist_with_reasons():
    md = build_cutlist(pyramidal_development(**SMALL), tool="jigsaw").to_markdown()
    assert md.count("- [ ]") >= 5  # every cut and every pre-flight step is tickable
    assert "| Item | Quantity | Why |" in md  # the BOM justifies each line
    assert "Actual size" in md
    assert "slots radiate" in md  # the electrical reason the seam matters


def test_thickness_note_scales_its_verdict_with_wavelength():
    negligible = thickness_note(1.0, 211.06)  # 1 mm at 21 cm
    assert "negligible" in negligible
    significant = thickness_note(1.0, 30.0)  # same sheet at 10 GHz
    assert "worth compensating" in significant


# --------------------------------------------------------------------------------------
# The packet
# --------------------------------------------------------------------------------------


def test_packet_writes_a_complete_buildable_folder(tmp_path):
    design = design_pyramidal_horn(
        gain_dbi=15.0, freq_hz=HI_HZ, waveguide_a_m=WR650_A, waveguide_b_m=WR650_B
    )
    packet = write_packet(design, tmp_path / "horn", tool="jigsaw", seam_allowance_mm=8.0)
    written = set(packet.files)
    assert {"cutlist.md", "assembly.md", "template.dxf", "design.json"} <= written
    assert packet.sheets == sum(t[1] for t in packet.templates)
    for name in written:
        assert (packet.directory / name).stat().st_size > 0


def test_packet_design_json_carries_the_prediction_and_its_caveat(tmp_path):
    design = design_pyramidal_horn(
        gain_dbi=18.0, freq_hz=HI_HZ, waveguide_a_m=WR650_A, waveguide_b_m=WR650_B
    )
    packet = write_packet(design, tmp_path / "h")
    payload = json.loads((packet.directory / "design.json").read_text())
    assert payload["schema"] == "jansky-forge.fabrication-packet/1"
    assert payload["shape"] == "pyramidal"
    assert payload["predicted_gain_dbi"] == pytest.approx(18.0)
    assert payload["aperture_a1_m"] == pytest.approx(design.aperture_a1_m)
    # A packet must never let a prediction be mistaken for a measurement.
    assert "not measurements" in payload["caution"]


def test_packet_for_a_conical_horn(tmp_path):
    design = design_conical_horn(gain_dbi=16.0, freq_hz=HI_HZ)
    packet = write_packet(design, tmp_path / "cone")
    payload = json.loads((packet.directory / "design.json").read_text())
    assert payload["shape"] == "conical"
    assert packet.development.sectors and not packet.development.panels
    assert "Roll the sector" in (packet.directory / "assembly.md").read_text()


def test_assembly_notes_refuse_to_overstate_the_prediction(tmp_path):
    design = design_pyramidal_horn(
        gain_dbi=18.0, freq_hz=HI_HZ, waveguide_a_m=WR650_A, waveguide_b_m=WR650_B
    )
    packet = write_packet(design, tmp_path / "h")
    text = (packet.directory / "assembly.md").read_text()
    assert "prediction from geometry, not a measurement" in text
    assert "Measure return loss" in text
    assert text.count("- [ ]") >= 10


def test_larger_paper_needs_fewer_sheets(tmp_path):
    design = design_pyramidal_horn(
        gain_dbi=18.0, freq_hz=HI_HZ, waveguide_a_m=WR650_A, waveguide_b_m=WR650_B
    )
    a4 = write_packet(design, tmp_path / "a4", page="a4")
    a3 = write_packet(design, tmp_path / "a3", page="a3")
    assert a3.sheets < a4.sheets


def test_version_is_importable_without_importing_the_package():
    """`_version` exists to break an import cycle; a regression would be a hard crash.

    `fabricate.packet` stamps the version into every design.json, and the top-level package
    re-exports it. If either route went through `jansky_forge/__init__` the two would form a
    cycle — which they briefly did, so this pins the fix.
    """
    from jansky_forge import __version__ as package_version
    from jansky_forge._version import __version__ as module_version

    assert package_version == module_version
    assert module_version.count(".") == 2
