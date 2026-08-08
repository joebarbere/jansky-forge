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

from jansky_forge import catalog
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
