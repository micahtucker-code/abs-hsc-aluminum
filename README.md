# abs_hsc_al - aluminum scantling checker (ABS HSC Rules, July 2022)

Checks aluminum high-speed-craft scantlings against ABS Rules for Building and Classing
High Speed Craft (July 2022), Part 3, Chapter 2. Pure Python 3, no dependencies.

    python -m abs_hsc_al inputs/example_vessel.json --md report.md --json report.json
    python -m unittest discover -s tests -t .

**GUI:** `python -m abs_hsc_al.gui` opens a form in your browser (local only, nothing leaves your machine). Enter vessel, alloy, plates, stiffeners and midship section properties, press *Run checks*, and download the report. *Save JSON* / *Open JSON* exchange files with the command line tool.

**Printed report:** after *Run checks*, press *Create printable report* (web or local GUI), then *Print / Save as PDF* (or *Download HTML*). The report follows the layout of a submitted calculation set: title-block cover with official/drawing/revision numbers, running page header, summary sheets, calculation sheets showing each equation with the numbers substituted, PASS/FAIL with margin, speed-vs-wave-height table, sign-off and the input data. Fill in the *Project information* section first; logos and a cover image can be attached there.

**Stations:** the *Stations* section (or `"stations"` in the JSON) takes x/L, deadrise, Kv and Fv for each station from AP to FP. The report then includes a station-by-station table of bottom slamming, side slamming and fore-end pressure, and any plate or stiffener can be tied to a station by name (`"station": "MID"` in its pressure). Kv and Fv come from the Rule figures and are never assumed.

Exit code is 0 when every check passes, 1 otherwise.

## What it checks
| Area | Rule | Notes |
|---|---|---|
| Design pressures | 3-2-2 | bottom/side slamming, hydrostatic, fore end, decks, superstructure, tanks, watertight, wet deck, ncg |
| Plating | 3-2-3/1.3, 1.5 | lateral thickness, 0.012 s, minimum thickness, uniaxial buckling |
| Stiffeners / girders | 3-2-4/1.3, 1.5.1, 1.5.6, 1.9 | SM, I, web thickness, web/flange proportions, column buckling |
| Hull girder | 3-2-1 | SM and I (all craft); wave/still-water/slam moments for L >= 61 m; catamaran loads |

## Inputs you must supply (not guessed)
1. **Aluminum properties** (`material`): use the built-in library, e.g.
   `"material": {"alloy": "5083-H116", "product": "plate", "thickness_mm": 8}`, or type your own four values.
   The library (`alloys.py`) holds unwelded minimums from ABS Part 2 2-5-5 (Tables 1B, 2, 3, 4) and as-welded
   minimums from 2-4-5/17 Table 2, by thickness band. Combinations without a published as-welded value
   (5059, 5083-H128, 6082, ...) are not included; enter those by hand. The GUI has a *Fill from ABS tables* button.
   One material applies to the whole run: use the lowest-strength band you have in the structure, or run twice.
2. **Graph-based factors**: FD, Kv, Fv, wet-deck F1, hull-girder M, shear F1/F2. Give a direct value
   (e.g. `"FD": 0.62`) or a digitised curve under `curves` (see `figures.py`). A missing factor stops
   with an error naming the figure.
3. Section properties of the hull girder: either build the midship section in the program (see below) or type `SM_deck_cm3`, `SM_bottom_cm3`, `I_cm4` from your own calculation.

## Input format
See `inputs/example_vessel.json`. Units: m, mm, tonnes, knots, kN/m2, N/mm2. Pressures can be given as a
number or as `{"calc": "bottom_slam_cg", "FD": 0.75}` etc. (see `report.resolve_pressure`).

See `RULE_REFERENCE.md` for clause mapping, interpretation choices and what is not implemented.
This tool supports a designer's check; it is not an ABS approval.


## Midship section calculator (v0.5)

The *Midship section properties* block computes area, neutral axis, I and the deck and bottom section moduli and feeds them to the hull girder check (leave the three manual hull girder fields blank).

- **Members:** plate lines (y from the centreline, z up from the baseline, mm) with an optional regular set of flat-bar, tee or angle stiffeners, an effectiveness factor (0 to 1), and free-standing `lump` areas in the JSON file (catalogue extrusions, bulbs, negative lumps for openings).
- **Half sections:** tick *enter one side only* to mirror about the centreline; members lying on the centreline are counted once.
- **DXF import:** export the section as an ASCII DXF (LINE, LWPOLYLINE with arcs, POLYLINE, ARC and CIRCLE are read; SPLINE, ELLIPSE and INSERT blocks are reported and skipped, so explode blocks first). Pick the drawing plane and units, then give each layer a thickness (layer names such as `T8` or `PL_10` are suggested automatically). Layers without a thickness are listed in a warning and left out. A sample is in `inputs/example_section.dxf`.
- **PDF drawings** are not read directly; convert to DXF in your CAD package.
- The report adds section 11.1 with the properties table, a drawing of the idealised section and a per-group contribution table. Limits: no plate-buckling effective-width reduction, no shear lag, a single alloy.
