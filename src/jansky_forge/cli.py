"""``jansky-forge`` — the command line over the catalog and the analytic models.

Four verbs at M0: ``bands``, ``list``, ``show``, ``characterize``. The CLI is a thin
presenter over the library; every number it prints comes from a model's
:meth:`characterize`, and every caveat a model attaches is printed too. Suppressing a
model's own warnings to make output tidy is not a trade this project makes.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from jansky_forge import catalog, fabricate, horns
from jansky_forge.bands import BANDS, get_band


def _ensure_utf8_stdout() -> None:
    """Make stdout carry λ, °, and ² on every platform.

    Windows consoles still default to cp1252, which cannot encode the characters this
    output is genuinely made of — wavelengths, degrees, square metres. The alternative
    would be to spell them out for everyone, degrading the output on the two platforms
    that were never broken, so instead the stream is reconfigured here.

    Guarded because a captured or replaced stdout (pytest, a redirect wrapper) need not
    be a ``TextIOWrapper``, and because reconfiguration can fail on an exotic stream —
    neither is worth crashing over.
    """
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(encoding="utf-8")
    except (ValueError, OSError):  # pragma: no cover - platform-specific stream oddities
        pass


def _print_bands() -> None:
    print(f"{'SLUG':<12} {'FREQUENCY':>16}  NAME")
    for slug in sorted(BANDS, key=lambda s: BANDS[s].freq_hz):
        band = BANDS[slug]
        print(f"{slug:<12} {band.freq_mhz:>13.4f} MHz  {band.name}")
        print(f"{'':<12} {'':>16}  {band.why}")


def _print_list(band: str | None, kind: str | None) -> None:
    templates = catalog.find(band=band, kind=kind)
    if not templates:
        print("No templates match that filter.")
        return
    print(f"{'SLUG':<20} {'KIND':<20} {'BAND':<10} NAME")
    for t in templates:
        print(f"{t.slug:<20} {t.kind:<20} {t.design_band.slug:<10} {t.name}")


def _print_template(template: catalog.Template, freq_hz: float | None) -> None:
    print(f"{template.name}  [{template.slug}]")
    print(f"  kind        : {template.kind}")
    print(f"  design band : {template.design_band.name} ({template.design_band.freq_mhz:.4f} MHz)")
    print(f"  provenance  : {template.provenance}  <{template.source_url}>")
    print(f"  summary     : {template.summary}")
    print("  geometry:")
    for key, value in template.model.parameters().items():
        print(f"    {key:<28} {value:g}")
    if template.published:
        print("  published figures (cross-checks, not our output):")
        for key, value in template.published.items():
            print(f"    {key:<28} {value:g}")
    if template.caveats:
        print("  caveats:")
        for caveat in template.caveats:
            print(f"    - {caveat}")
    print()
    _print_characterization(template.characterize(freq_hz))


def _print_characterization(char) -> None:  # noqa: ANN001 - Characterization, kept loose for reuse
    print("  predicted performance:")
    print(f"    {char.summary()}")
    print(f"    beam solid angle             {char.beam_solid_angle_sr:.5f} sr")
    for key, value in char.detail.items():
        print(f"    {key:<28} {value:g}")
    if char.notes:
        print("  model notes:")
        for note in char.notes:
            print(f"    - {note}")


def _as_json(template: catalog.Template, freq_hz: float | None) -> str:
    char = template.characterize(freq_hz)
    return json.dumps(
        {
            "slug": template.slug,
            "name": template.name,
            "kind": template.kind,
            "provenance": str(template.provenance),
            "source_url": template.source_url,
            "design_band": template.design_band.slug,
            "parameters": template.model.parameters(),
            "published": template.published,
            "caveats": list(template.caveats),
            "characterization": {
                "freq_hz": char.freq_hz,
                "gain_dbi": char.gain_dbi,
                "hpbw_e_deg": char.hpbw_e_deg,
                "hpbw_h_deg": char.hpbw_h_deg,
                "aperture_efficiency": char.aperture_efficiency,
                "effective_area_m2": char.effective_area_m2,
                "beam_solid_angle_sr": char.beam_solid_angle_sr,
                "detail": char.detail,
                "notes": list(char.notes),
            },
        },
        indent=2,
    )


#: Standard rectangular waveguides, internal dimensions in metres (a = broad wall).
#: WR-650 is the L-band part an amateur 21 cm horn is normally fed with.
WAVEGUIDES: dict[str, tuple[float, float]] = {
    "wr650": (0.16510, 0.08255),
    "wr430": (0.10922, 0.05461),
    "wr340": (0.08636, 0.04318),
    "wr284": (0.07214, 0.03404),
    "wr90": (0.02286, 0.01016),
}


def _parse_waveguide(spec: str) -> tuple[float, float]:
    """A named standard, or 'AxB' in millimetres."""
    key = spec.lower().replace("-", "")
    if key in WAVEGUIDES:
        return WAVEGUIDES[key]
    if "x" in key:
        a_mm, _, b_mm = key.partition("x")
        try:
            return float(a_mm) / 1000.0, float(b_mm) / 1000.0
        except ValueError:
            pass
    raise SystemExit(
        f"unrecognized waveguide {spec!r}; use one of {', '.join(sorted(WAVEGUIDES))} "
        "or give 'AxB' in mm (e.g. 165.1x82.55)"
    )


def _print_design(args) -> None:  # noqa: ANN001 - argparse namespace
    freq_hz = args.freq_mhz * 1e6 if args.freq_mhz else get_band(args.band).freq_hz

    if args.shape == "conical":
        cone = horns.design_conical_horn(gain_dbi=args.gain_dbi, freq_hz=freq_hz)
        print(f"Optimum conical horn — {cone.summary()}")
        print("\n  cut to:")
        print(f"    aperture diameter            {cone.aperture_diameter_m * 1000:9.1f} mm")
        print(f"    axial length                 {cone.axial_length_m * 1000:9.1f} mm")
        print(f"    slant (apex to rim)          {cone.slant_m * 1000:9.1f} mm")
        print("\n  Gain uses Balanis' empirical loss figure; see 'show' notes for its limits.")
        return

    wg_a, wg_b = _parse_waveguide(args.waveguide)
    design = horns.design_pyramidal_horn(
        gain_dbi=args.gain_dbi, freq_hz=freq_hz, waveguide_a_m=wg_a, waveguide_b_m=wg_b
    )
    print(f"Optimum pyramidal horn — {design.summary()}")
    print("\n  cut to:")
    print(f"    aperture a1 (H-plane, wide)  {design.aperture_a1_m * 1000:9.1f} mm")
    print(f"    aperture b1 (E-plane, tall)  {design.aperture_b1_m * 1000:9.1f} mm")
    print(f"    axial length (p_e = p_h)     {design.axial_length_m * 1000:9.1f} mm")
    print(f"    waveguide a x b              {wg_a * 1000:9.1f} x {wg_b * 1000:.1f} mm")
    print("\n  geometry:")
    print(
        f"    rho1 / rho2 (axial to apex)  {design.rho1_m * 1000:9.1f} / {design.rho2_m * 1000:.1f} mm"
    )
    print(
        f"    rho_e / rho_h (slant to rim) {design.slant_e_m * 1000:9.1f} / {design.slant_h_m * 1000:.1f} mm"
    )
    print(
        f"    phase deviation s / t        {design.phase_deviation_e:9.4f} / "
        f"{design.phase_deviation_h:.4f}  (optima 0.25 / 0.375)"
    )
    print(
        "\n  Both flares share one axial length, so this is buildable as a single horn — "
        "\n  which is not true of every published design; see 'show horn-18dbi-worked'."
    )


def _print_fabricate(args) -> None:  # noqa: ANN001 - argparse namespace
    freq_hz = args.freq_mhz * 1e6 if args.freq_mhz else get_band(args.band).freq_hz
    design: horns.ConicalDesign | horns.PyramidalDesign
    if args.shape == "conical":
        design = horns.design_conical_horn(gain_dbi=args.gain_dbi, freq_hz=freq_hz)
    else:
        wg_a, wg_b = _parse_waveguide(args.waveguide)
        design = horns.design_pyramidal_horn(
            gain_dbi=args.gain_dbi, freq_hz=freq_hz, waveguide_a_m=wg_a, waveguide_b_m=wg_b
        )

    packet = fabricate.write_packet(
        design,
        args.out,
        seam_allowance_mm=args.seam_mm,
        kerf_mm=args.kerf_mm,
        tool=args.tool,
        material_thickness_mm=args.thickness_mm,
        page=args.page,
        landscape=args.landscape,
    )

    print(design.summary())
    print(f"\n{packet.summary()}\n")
    print("  templates:")
    for label, sheets, width, height in packet.templates:
        print(f"    {label:<32} {width:7.0f} x {height:<7.0f} mm   {sheets:3d} sheet(s)")
    print(
        f"\n  material: {packet.cutlist.total_area_m2:.4f} m² of parts, "
        f"{packet.cutlist.total_cut_length_mm / 1000:.2f} m of cutting"
    )
    print("\n  read cutlist.md first, then assembly.md.")
    if packet.sheets > 20:
        print(
            f"\n  NOTE: {packet.sheets} sheets is a lot of taping. A larger paper size "
            "(--page a3) or a print shop\n  will be quicker and more accurate — every taped "
            "joint is a chance to introduce error."
        )
    print(
        "\n  Print at 100% / 'Actual size' and measure the 100 mm ruler on each sheet\n"
        "  BEFORE cutting. A 'fit to page' print looks perfect and is a few percent small."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jansky-forge",
        description="Design, build, and characterize radio-astronomy antennas.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("bands", help="List the radio-astronomy bands this tool knows")

    p_list = sub.add_parser("list", help="List catalog templates")
    p_list.add_argument("--band", help="Filter by band slug (see 'bands')")
    p_list.add_argument("--kind", help="Filter by antenna kind substring, e.g. dish, horn")

    p_show = sub.add_parser("show", help="Show one template's geometry and predicted performance")
    p_show.add_argument("slug", help="Template slug (see 'list')")
    p_show.add_argument("--freq-mhz", type=float, help="Characterize at this frequency instead")
    p_show.add_argument("--json", action="store_true", help="Machine-readable output")

    p_design = sub.add_parser(
        "design", help="Synthesize a horn for a target gain (M1): gain in, dimensions out"
    )
    p_design.add_argument("--gain-dbi", type=float, required=True, help="Target gain in dBi")
    p_design.add_argument(
        "--band", default="hi", help="Design band slug (default: hi, the hydrogen line)"
    )
    p_design.add_argument("--freq-mhz", type=float, help="Design frequency, overrides --band")
    p_design.add_argument(
        "--shape", choices=["pyramidal", "conical"], default="pyramidal", help="Horn type"
    )
    p_design.add_argument(
        "--waveguide",
        default="wr650",
        help="Feeding waveguide for a pyramidal horn: a named standard (wr650, wr430, wr340, "
        "wr284, wr90) or 'AxB' in mm, e.g. '165.1x82.55'",
    )

    p_fab = sub.add_parser(
        "fabricate",
        help="Write a full fabrication packet (M2): 1:1 templates, DXF, cut list, assembly",
    )
    p_fab.add_argument("--gain-dbi", type=float, required=True, help="Target gain in dBi")
    p_fab.add_argument("--out", required=True, help="Directory to write the packet into")
    p_fab.add_argument("--band", default="hi", help="Design band slug (default: hi)")
    p_fab.add_argument("--freq-mhz", type=float, help="Design frequency, overrides --band")
    p_fab.add_argument("--shape", choices=["pyramidal", "conical"], default="pyramidal")
    p_fab.add_argument("--waveguide", default="wr650", help="Waveguide for a pyramidal horn")
    p_fab.add_argument(
        "--page", default="a4", help=f"Paper size: {', '.join(sorted(fabricate.PAGE_SIZES))}"
    )
    p_fab.add_argument("--landscape", action="store_true", help="Rotate the paper")
    p_fab.add_argument(
        "--seam-mm", type=float, default=0.0, help="Seam allowance on sloped edges (mm)"
    )
    p_fab.add_argument(
        "--tool",
        help=f"Cutting tool, sets kerf: {', '.join(sorted(fabricate.TYPICAL_KERF_MM))}",
    )
    p_fab.add_argument("--kerf-mm", type=float, default=0.0, help="Kerf width if not using --tool")
    p_fab.add_argument(
        "--thickness-mm", type=float, default=1.0, help="Sheet thickness (default 1.0)"
    )

    p_char = sub.add_parser(
        "characterize", help="Characterize a template across one or more frequencies"
    )
    p_char.add_argument("slug", help="Template slug (see 'list')")
    p_char.add_argument(
        "--band", action="append", default=[], help="Band slug; repeatable (see 'bands')"
    )
    p_char.add_argument(
        "--freq-mhz", action="append", type=float, default=[], help="Frequency in MHz; repeatable"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    _ensure_utf8_stdout()
    args = build_parser().parse_args(argv)

    if args.command == "bands":
        _print_bands()
        return 0

    if args.command == "list":
        _print_list(args.band, args.kind)
        return 0

    if args.command == "design":
        _print_design(args)
        return 0

    if args.command == "fabricate":
        _print_fabricate(args)
        return 0

    template = catalog.get(args.slug)

    if args.command == "show":
        freq = args.freq_mhz * 1e6 if args.freq_mhz else None
        print(_as_json(template, freq) if args.json else "", end="")
        if not args.json:
            _print_template(template, freq)
        return 0

    # characterize
    frequencies: list[tuple[str, float]] = [(b, get_band(b).freq_hz) for b in args.band]
    frequencies += [(f"{mhz:g} MHz", mhz * 1e6) for mhz in args.freq_mhz]
    if not frequencies:
        frequencies = [(template.design_band.slug, template.design_band.freq_hz)]

    print(f"{template.name}  [{template.slug}]")
    for label, freq_hz in frequencies:
        print(f"\n  @ {label}")
        _print_characterization(template.characterize(freq_hz))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
