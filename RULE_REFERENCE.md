# Rule reference and interpretation notes

## Clause map
- pressures.py: 3-2-2/1.1 (ncg, pbcg, pbxx, pd), 1.3 (side), 3.5 (wet deck), 5 Table 3, 7 Table 4, 9.
- plating.py: 3-2-3/1.3.1 Tables 1-2 (k, sigma_a), 1.3.2, 1.3.3, 1.5.1, 1.5.2 Table 3.
- stiffeners.py: 3-2-4/1.3.1 Table 1, 1.3.2, 1.5.1, 1.5.3, 1.5.5, 1.5.6, 1.9.1.
- hullgirder.py: 3-2-1/1.1.1, 1.1.2(b)-(e), 1.5 Table 2, 1.9, 3.3, 3.5.3.

## Interpretation choices (text extraction lost some typography; please confirm against the printed Rules)
1. Minimum thickness 3-2-3/1.3.3: read as `a*sqrt(L*qa) + b`.
2. Web thickness 3-2-4/1.9.1: `dw/50*sqrt(sigma_y/127.6)`, using the UNWELDED yield (the more conservative reading).
3. Transverse buckling coefficient m1 = C2[1+(s/l)^2]^2, read as a product. The 1.45 factor at sigma'=sigma/3 is interpolated linearly.
4. Fore-end pressure 3-2-2/1.3.3: the printed "Cp" is read as CF.
5. Wet-deck V1 uses sqrt(L) (checked against the US-unit coefficients).
6. Hs at exactly 30 m is not specified; treated as the >30 m formula.
7. 3-2-1/1.1.2(c) still-water hogging moment is coded as printed: 0.375 fp C1 C2 L^2 B (Cb+0.7), fp = 17.5, C2 = 0.01.
8. Hull-girder SM printed in cm2-m: inputs in cm3 are divided by 100; I in cm4 divided by 1e4.
9. Table 1 of 3-2-4: for aluminum sigma_y is the welded yield (capped at 0.7 sigma_uw).

## Not implemented (check by other means)
Torsional/flexural buckling of stiffeners (3-2-4/1.5.2), plate shear buckling stress (working shear
stress is by "acceptable method"), local shear stress calc 1.9.4, corrugated panels, extruded planking,
sandwich/FRP, wheel loads 3-2-3/1.9, water jet and thruster tunnels, direct analysis (3-1-3/3-1-4),
catamaran cross-structure stress analysis (only loads and allowables), hydrofoil craft, welding/connections.

## Part 5 (Specialized Craft, Jan 2022)
- Ch.2 Sec.3 (5-2-3/5), Crewboat: design pressures use h1/3 = 3.35 m minimum and V = the maximum design speed at that wave height (reduce V at higher h1/3 to hold nxx constant). Implemented as `service: "crewboat"`; the speed V you enter must be that speed.
- Ch.1 Sec.3 (5-1-3/1), Passenger craft: scantlings follow Part 3 unchanged.
- Part 5 contains no aluminum strength table; the alloy values (Part 2, Ch.5, Sec.5) are still needed.

## Aluminum property library (Part 2, July 2022)
- Unwelded: 2-5-5 TABLE 1B (marine plate 5059/5083/5086/5383/5456 H116/H321), TABLE 2 (6061-T6 plate, long-transverse), TABLES 3-4 (extrusions).
- As-welded: 2-4-5/17 TABLE 2 (plate up to 38 mm, filler per 2-4-5 TABLE 4); ABS notes the as-welded yield is not required for procedure qualification, but these are the values the Part 3 formulas call for.
- 6061-T6 welded values change at 9.5 mm (yield 138 below, 103 above).
- 5086-H116 plate band 3-6.3 mm and 6.3-50 mm have identical values; merged.
- Not in the library: 5059 (no welded row), 5083-H128, 5086-H321, 6082, 6005A, 6063, and non-marine 5083-H111/H112 plate (published welded yield exceeds the unwelded minimum).


## Midship section calculator (not a Rule item)

3-2-1 gives SM and I requirements; how the provided values are calculated is left to the designer. The calculator idealises the section as thin straight members (A = l t; own inertia t l^3 sin^2(a)/12 + l t^3 cos^2(a)/12 about the horizontal centroidal axis) and uses the parallel-axis theorem about the neutral axis. SM deck = I/(z deck - z NA), SM bottom = I/(z NA - z base); the deck and baseline default to the highest and lowest points of the drawn members unless given. Stiffener webs start at the plate surface and flanges are centred (tee) or one-sided (angle) at the web tip. Plating is not reduced for buckling or shear lag; the designer should confirm that this is acceptable to the reviewing body, or reduce the effectiveness of compressed panels.


## Shear and cross-structure interpretations (v0.6)

1. 1.9.1 asks for the maximum algebraic sum of Fsw, Fw and Fsl, while 1.9.4 gives two separate equations (Fsw+Fw and Fsl alone, "the greater of"). Both are evaluated and the 1.9.1 sum is added as a third row (switch off with `combined_sum: false`).
2. Fsl uses (ncg + 1) exactly as printed in 1.9.3, without the Table 1 minimum that 1.1.2(d) applies to the slamming moment.
3. fs = F m / (2 ts I) is generalised to F m / (sum of shear-web thicknesses x I), so two equal side shells reproduce the printed form and a catamaran with four webs is handled. All plate members crossing the neutral axis count as shear webs; stiffener webs do not.
4. For the cross structure, A2/5.5 and A2/5.7 stresses are compared with sigma_ab = 0.75 sigma_y and tau_a = 0.38 sigma_y; the Rule does not combine them with the transverse bending stress of A2/1 and this program does not either.
5. Torsion elements are treated as fixed-guided beams (BM = P L / 2) as printed in A2/5.3, and all of Mtt is taken by the listed elements.
