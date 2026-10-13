/* Printable calculation report in the style of a submitted calculation set (title block, running header,
   summary sheets, calculation sheets with PASS / margin).  buildReport(result, assets) -> full HTML string. */
const REPORT_CSS=`
@page{size:Letter;margin:20mm 13mm 17mm 13mm;
 @top-left{content:var(--hl);font:7.5pt Arial,sans-serif;color:#222}
 @top-right{content:var(--hr);font:7.5pt Arial,sans-serif;color:#222;text-align:right}
 @bottom-left{content:var(--fl);font:7pt Arial,sans-serif;color:#444}
 @bottom-right{content:"Page " counter(page) " of " counter(pages);font:7.5pt Arial,sans-serif;color:#444}}
@page :first{margin:10mm;@top-left{content:none}@top-right{content:none}@bottom-left{content:none}@bottom-right{content:none}}
*{box-sizing:border-box}body{font:9.5pt/1.38 Calibri,"Segoe UI",Arial,sans-serif;color:#111;margin:0 auto;max-width:195mm;padding:6mm}
.sheet{page-break-before:always}.flow{margin-top:8mm}.cover{page-break-before:avoid;height:256mm;overflow:hidden;border:1.5px solid #000;display:flex;flex-direction:column;padding:0}
.cover .img{flex:1;display:flex;align-items:center;justify-content:center;padding:6mm;min-height:0}.cover .img img{max-width:100%;max-height:115mm}
.note{border:1px solid #000;margin:0 22mm 6mm;padding:3mm;text-align:center;font-size:9pt}
.tb{display:grid;grid-template-columns:34% 36% 30%;border-top:1.5px solid #000;font-size:9pt}.tb>div{border-right:1px solid #000;border-bottom:1px solid #000;padding:1.5mm 2.5mm;min-height:11mm}
.tb>div:nth-child(3n){border-right:0}.tb b{font-size:8.5pt}.tb .big{font-size:13pt;text-align:center;padding-top:3mm}.logo{max-height:16mm;max-width:100%}
h2{font-size:13pt;margin:0 0 3mm;padding:1.5mm 0;border-bottom:2px solid #123;color:#123;page-break-after:avoid}h3{font-size:10.5pt;margin:4mm 0 1.5mm;page-break-after:avoid}
table{border-collapse:collapse;width:100%;margin:1.5mm 0 3mm;font-size:8.4pt}th,td{border:1px solid #889;padding:1mm 1.6mm;text-align:left;vertical-align:top}
th{background:#e3eaf1;font-weight:600}td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
tr{page-break-inside:avoid}.kv td:first-child{width:40%;background:#f3f6f9;font-weight:600}
td.ok,.ok{background:#d9f2e0;color:#0a5b32;font-weight:700;text-align:center}td.bad,.bad{background:#fbd9dc;color:#a0001c;font-weight:700;text-align:center}
.eq{font-family:Consolas,monospace;font-size:7.8pt}.wk{font-size:7.8pt;color:#333}.small{font-size:8pt;color:#333}
.box{border:1px solid #123;padding:2.5mm 3mm;margin:3mm 0;background:#f7f9fb}.warn{border-color:#a0001c;background:#fdf0f0}
.sig td{height:13mm}pre{font-size:7pt;white-space:pre-wrap;word-break:break-word;border:1px solid #ccd;padding:2mm;background:#fafbfc}
ul,ol{margin:1mm 0 2mm 5mm;padding:0}li{margin:.6mm 0}.toc td{border:0;border-bottom:1px dotted #999;padding:1mm}
@media print{body{padding:0}}
`;
function _e(s){return String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
function _n(x,d){if(x===undefined||x===null||x===""||isNaN(x))return"";const a=Math.abs(x);return (+x).toFixed(d??(a>=1000?0:a>=100?1:a>=10?2:3))}
function _kv(rows){return `<table class="kv">`+rows.filter(r=>r[1]!==undefined&&r[1]!==""&&r[1]!==null).map(r=>`<tr><td>${_e(r[0])}</td><td>${_e(r[1])}</td></tr>`).join("")+`</table>`}
function _margin(x){return x.unit==="-"||x.limit?(x.provided/x.required):(x.provided/x.required)}
function _mg(x){const m=x.required>0?x.provided/x.required*100:Infinity;return isFinite(m)?m.toFixed(0)+"%":"-"}
function _chk(x){return `<td class="${x.passed?"ok":"bad"}">${x.passed?"PASS":"FAIL"}</td>`}
function _resRows(list){return list.map(x=>`<tr><td>${_e(x.kind)}<div class="small">${_e(x.clause)}</div></td><td><div class="eq">${_e(x.formula)}</div><div class="wk">${_e(x.working)}</div></td><td class="n">${_n(x.required)} ${_e(x.unit)}</td><td class="n">${_n(x.provided)}</td>${_chk(x)}<td class="n">${_mg(x)}</td></tr>`).join("")}
function _resTable(list){return `<table><tr><th style="width:16%">Check / Rule clause</th><th>Equation and working</th><th>Required</th><th>Provided</th><th>Check</th><th>Margin</th></tr>${_resRows(list)}</table>`}
const _MM_IN=1/25.4,_KPA_PSI=0.145038,_M_FT=3.28084;
const _LIMITS=[
 "Longitudinal hull girder: section modulus and inertia are checked against 3-2-1/1.1.1, 1.1.2 (craft of 61 m and over) and 1.5, using section properties calculated by the designer. Hull girder shear (1.9) and catamaran cross-structure stress analysis (3-2-1/3.5) are not evaluated.",
 "Stiffener torsional/flexural buckling (3-2-4/1.5.2), plate shear buckling stress (3-2-3/1.5.2), corrugated panels (3-2-4/1.7), extruded planking and sandwich panels (3-2-3/3), wheel-load decks (3-2-3/1.9), water jet and thruster tunnels (3-2-3/1.7), welded connections and end attachments (3-2-4/1.11), tripping brackets, rudders, hatches, appendages and machinery foundations are outside the scope of the calculation program.",
 "Direct analysis (3-1-3, 3-1-4) is not performed. Where the Rules require direct analysis of primary structure it is submitted separately.",
 "Graph-based Rule factors (FD, Kv, Fv, wet-deck F1, hull girder distribution factors) were supplied by the designer as direct values or digitised curves, are listed in the pressure sheets, and should be verified against the Rule figures.",
 "Net scantlings are assumed; any corrosion or wear allowance must be applied by the designer to the thicknesses entered.",
 "Material properties are minimum values from the ABS Rules for Materials and Welding (Part 2); mill certificates and approved welding procedures must support them."];
const _INTERP=[
 "3-2-3/1.3.3 minimum thickness is evaluated as a x sqrt(L x qa) + b (square-root sign not reproduced in the source text).",
 "3-2-4/1.9.1 web proportion thickness uses the unwelded yield strength (the more conservative reading).",
 "3-2-3 TABLE 3 transverse buckling coefficient m1 = C2 [1 + (s/l)^2]^2 is evaluated as a product.",
 "3-2-2/1.3.3 fore-end pressure: the symbol printed as 'Cp' is taken as CF.",
 "3-2-2/3.5 wet-deck V1 uses the square root of L (consistent with the US-unit coefficients).",
 "3-2-2/1.3.2 Hs at exactly L = 30 m is not specified; the 'over 30 m' expression is used.",
 "3-2-1/1.1.2(c) still-water hogging moment is evaluated exactly as printed.",
 "3-2-4 TABLE 1 for aluminum: sigma_y is the welded yield strength, not exceeding 0.7 of the welded ultimate."];
const _METHOD=["Vessel particulars, operating condition and material properties are entered (Sections 6 and 7).","Vertical acceleration ncg at the LCG is calculated from 3-2-2/1.1.3, limited by the Rule maximum; slamming, hydrostatic, side, deck, tank and bulkhead design pressures are evaluated for each member (Section 8).","Plating thickness is checked for each load case against 3-2-3/1.3 (lateral pressure with design stress from Table 2, secondary stiffening, minimum thickness) and, where applicable, buckling 3-2-3/1.5.","Each stiffener or girder is combined with its effective plating width; section modulus, moment of inertia, web thickness and web/flange proportions are checked against 3-2-4 (Section 10).","Hull girder section modulus and inertia are checked against 3-2-1 (Section 11).","Each check reports Required, Provided, PASS/FAIL and Margin = Provided / Required."];
function buildReport(j,assets){
 assets=assets||{};
 const P=j.project||{},V=j.inputs.vessel,M=j.material,D=j.derived,R=j.results,OL=j.operating_limits||[];
 const fails=R.filter(x=>!x.passed),today=new Date().toISOString().slice(0,10);
 const dwg=P.document_no||"",rev=P.revision||"-",off=P.official_no||"",dt=P.date||today;
 const plateIds=[...new Set((j.inputs.plates||[]).map(p=>p.id))],stiffIds=[...new Set((j.inputs.stiffeners||[]).map(p=>p.id))];
 const grp=id=>R.filter(x=>x.id===id),q=s=>String(s).replace(/["\\]/g,"'");
 let h=`<!doctype html><html><head><meta charset="utf-8"><title>${_e(P.project||"Structural calculation report")}</title><style>${REPORT_CSS}:root{--hl:"${q(P.company||"")}  |  ${q(P.vessel_name||"")}";--hr:"OFFICIAL NO.: ${q(off)}   DWG NO.: ${q(dwg)}   REV: ${q(rev)}";--fl:"${q(dwg)} - Structural calculations (ABS HSC Aluminum Checker v${j.version})   Date: ${q(dt)}"}</style></head><body>`;
 // ---- cover
 h+=`<div class="cover"><div class="img">${assets.vessel?`<img src="${assets.vessel}">`:`<div style="color:#999">${_e(P.vessel_type||"")}</div>`}</div>
 <div class="note"><b>PLEASE NOTE:</b><br>THIS CALCULATION SET WAS PERFORMED USING THE ABS RULES FOR BUILDING AND CLASSING HIGH SPEED CRAFT (JULY 2022), ALUMINUM CONSTRUCTION.${P.notation?`<br>${_e(P.notation)}`:""}</div>
 <div class="tb">
 <div><b>DATE:</b><br>${_e(dt)}</div><div><b>DEPARTMENT NAME</b><br>${_e(P.department||"")}</div><div><b>VESSEL TYPE</b><br>${_e(P.vessel_type||"")}</div>
 <div style="grid-row:span 2;text-align:center">${assets.client?`<img class="logo" src="${assets.client}">`:""}</div><div><b>OFFICIAL NO.</b><br>${_e(off)}</div><div><b>VESSEL NAME</b><br>${_e(P.vessel_name||"")}</div>
 <div><b>APPROVED:</b> ${_e(P.approved_by||"")}<br><b>CHECKED:</b> ${_e(P.checked_by||"")}</div><div style="grid-row:span 2"><b>NAME OF DRAWING</b><div class="big">${_e(P.project||"Vessel Structural Calculations and Report")}</div></div>
 <div>${assets.logo?`<img class="logo" src="${assets.logo}"><br>`:""}<b>DRAWN:</b> ${_e(P.prepared_by||"")}<br>${_e(P.company||"")}<br>${_e(P.address||"")}</div><div><b>SUBMITTED TO</b><br>${_e(P.submitted_to||"")}</div>
 <div></div><div></div><div style="display:flex;gap:6mm"><div><b>DRAWING NO.</b><br>${_e(dwg)}</div><div><b>REV NO</b><br>${_e(rev)}</div></div></div></div>`;
 // ---- contents
 const TOC=["Revision history, general notes and references","Vessel route designation","Summary of results (plating, stiffeners, pressures)","Operating speed versus significant wave height","Calculation methodology","Aluminum strength characteristics","Design factors (vessel particulars)","Design pressures","Plate thickness calculations","Stiffener and frame calculations","Longitudinal hull girder","Basis, interpretations and limitations","Sign-off","Appendix A - Input data"];
 h+=`<div class="sheet"><h2>CONTENTS</h2><table class="toc">${TOC.map((t,i)=>`<tr><td style="width:12mm">${i<13?i+1:"A"}</td><td>${t}</td></tr>`).join("")}</table></div>`;
 // ---- 1 revision, notes, references
 h+=`<div class="sheet"><h2>1. Revision history, general notes and references</h2><h3>Revision history</h3><table><tr><th>Date</th><th>Rev</th><th>Description</th><th>Drawn</th><th>Checked</th><th>Approved</th></tr><tr><td>${_e(dt)}</td><td>${_e(rev)}</td><td>${_e(P.rev_description||"Issued for approval")}</td><td>${_e(P.prepared_by||"")}</td><td>${_e(P.checked_by||"")}</td><td>${_e(P.approved_by||"")}</td></tr></table>
 <h3>General notes</h3><table><tr><th style="width:8mm">No.</th><th>Description</th></tr>
 <tr><td>1</td><td><b>Regulatory standard.</b> The design and construction of the hull structure is evaluated against the ABS Rules for Building and Classing High Speed Craft (July 2022)${P.submitted_to?` to the satisfaction of ${_e(P.submitted_to)}`:""}.</td></tr>
 <tr><td>2</td><td><b>Design scope.</b> ${_e(P.scope||"")}</td></tr>
 <tr><td>3</td><td><b>Construction.</b> These calculations are valid only for the hull structure described by the scantlings entered in this report${P.drawing_ref?` and shown in ${_e(P.drawing_ref)}`:""}.</td></tr>
 <tr><td>4</td><td><b>Operation.</b> The vessel speed shall be controlled to limit wave slamming pressures in accordance with the table in Section 4. Operation outside those limits produces hull loads not covered by these calculations.</td></tr>
 ${P.notes?`<tr><td>5</td><td>${_e(P.notes)}</td></tr>`:""}</table>
 <h3>References</h3><ol>${(P.references||"").split(/\n|;/).filter(x=>x.trim()).map(x=>`<li>${_e(x.trim())}</li>`).join("")||"<li>ABS Rules for Building and Classing High Speed Craft, July 2022 (Parts 2, 3)</li><li>ABS Rules for Materials and Welding, July 2022 (Part 2, Chapters 4 and 5)</li>"}</ol></div>`;
 // ---- 2 route
 h+=`<div class="flow"><h2>2. Vessel route designation</h2><p><b>Proposed route:</b> ${_e(P.route||"-")}</p><p><b>Route designation / service:</b> ${_e(P.route_designation||"-")}</p><p>Design service for the pressure calculations: <b>${_e(V.service||"high-speed")}</b>, design significant wave height h<sub>1/3</sub> = <b>${D.h13} m</b> (3-2-2/1.1.3 Table 1${V.service==="crewboat"?"; 5-2-3/5 crewboat":""}).</p></div>`;
 // ---- 3 summaries
 h+=`<div class="sheet"><h2>3. Summary of results</h2><div class="box ${fails.length?"warn":""}"><b>${R.length-fails.length} of ${R.length} checks pass${fails.length?`; <span style="color:#a0001c">${fails.length} FAIL</span>`:""}.</b>${fails.length?`<ul>${fails.map(x=>`<li>${_e(x.id)} - ${_e(x.kind)} (${_e(x.clause)}): required ${_n(x.required)} ${_e(x.unit)}, provided ${_n(x.provided)}</li>`).join("")}</ul>`:""}<div class="small">The summary covers only the checks performed (see Section 12). It is not a statement of compliance with the Rules as a whole and is not an approval.</div></div>`;
 if(plateIds.length){h+=`<h3>3.1 Plate thickness summary</h3><table><tr><th>Plate / location</th><th>Spacing (mm)</th><th>Governing check</th><th>Required (mm)</th><th>Required (in)</th><th>Actual (mm)</th><th>Actual (in)</th><th>Check</th><th>Margin</th></tr>`+
  plateIds.map(id=>{const rs=grp(id);const g=rs.reduce((a,b)=>b.required>a.required?b:a);const pl=j.inputs.plates.find(p=>p.id===id);const ok=rs.every(x=>x.passed&&true);return `<tr><td>${_e(id)}</td><td class="n">${pl.s_mm}</td><td>${_e(g.kind)}</td><td class="n">${_n(g.required)}</td><td class="n">${_n(g.required*_MM_IN,3)}</td><td class="n">${_n(pl.t_mm)}</td><td class="n">${_n(pl.t_mm*_MM_IN,3)}</td><td class="${ok?"ok":"bad"}">${ok?"PASS":"FAIL"}</td><td class="n">${_mg({required:g.required,provided:pl.t_mm})}</td></tr>`}).join("")+`</table>`}
 if(stiffIds.length){h+=`<h3>3.2 Stiffener and frame summary</h3><table><tr><th>Member</th><th>SM req. (cm3)</th><th>SM prov. (cm3)</th><th>I req. (cm4)</th><th>I prov. (cm4)</th><th>Web t req. (mm)</th><th>Web t prov. (mm)</th><th>Check</th><th>Min. margin</th></tr>`+
  stiffIds.map(id=>{const rs=grp(id),f=k=>rs.find(x=>x.kind===k)||{};const sm=f("section modulus"),mi=f("moment of inertia"),wt=f("web thickness");const ok=rs.every(x=>x.passed);const mg=Math.min(...rs.filter(x=>x.required>0).map(x=>x.provided/x.required*100));return `<tr><td>${_e(id)}</td><td class="n">${_n(sm.required)}</td><td class="n">${_n(sm.provided)}</td><td class="n">${_n(mi.required)}</td><td class="n">${_n(mi.provided)}</td><td class="n">${_n(wt.required)}</td><td class="n">${_n(wt.provided)}</td><td class="${ok?"ok":"bad"}">${ok?"PASS":"FAIL"}</td><td class="n">${mg.toFixed(0)}%</td></tr>`}).join("")+`</table>`}
 h+=`<h3>3.3 Design pressures summary</h3><table><tr><th>Member</th><th>Load case</th><th>Clause</th><th>p (kN/m2)</th><th>p (psi)</th></tr>${(j.pressure_log||[]).map(x=>`<tr><td>${_e(x.item)}</td><td>${_e(x.case)}</td><td>${_e(x.clause)}</td><td class="n">${_n(x.p,2)}</td><td class="n">${_n(x.p*_KPA_PSI,2)}</td></tr>`).join("")}</table>`;
 const hgr=grp("hull girder");if(hgr.length)h+=`<h3>3.4 Longitudinal hull girder summary</h3><table><tr><th>Check</th><th>Required</th><th>Provided</th><th>Check</th><th>Margin</th></tr>${hgr.map(x=>`<tr><td>${_e(x.kind)} (${_e(x.clause)})</td><td class="n">${_n(x.required)} ${_e(x.unit)}</td><td class="n">${_n(x.provided)}</td>${_chk(x)}<td class="n">${_mg(x)}</td></tr>`).join("")}</table>`;
 h+=`</div>`;
 // ---- 4 operating limits
 h+=`<div class="sheet"><h2>4. Operating speed versus significant wave height</h2>`;
 if(OL.length){h+=`<p>The design vertical acceleration (3-2-2/1.1.3) is held at its design value of n<sub>cg</sub> = ${_n(D.ncg_used,2)} g, reached at V = ${V.V} kn and h<sub>1/3</sub> = ${D.h13} m. For higher significant wave heights the speed is reduced to keep the acceleration, and therefore the slamming pressure, constant (cf. 5-2-3/5). Speeds are limited to the design speed.</p><table><tr><th>Significant wave height h1/3 (m)</th><th>(ft)</th><th>Maximum speed (kn)</th><th>Speed-length ratio V/sqrt(L)</th></tr>${OL.map(o=>`<tr><td class="n">${_n(o.h13,2)}</td><td class="n">${_n(o.h13*_M_FT,1)}</td><td class="n">${_n(o.V,1)}</td><td class="n">${_n(o.V/Math.sqrt(V.L),2)}</td></tr>`).join("")}</table><p class="small">The table is derived from the acceleration equation only. Limits imposed by comfort, stability or the Administration are not included.</p>`}
 else h+=`<p>Not calculated: the vertical acceleration was supplied directly by the designer (model test or direct analysis), so a speed/wave-height relationship must be taken from that source.</p>`;
 h+=`</div>`;
 // ---- 5 methodology
 h+=`<div class="flow"><h2>5. Calculation methodology</h2><ol>${_METHOD.map(x=>`<li>${_e(x)}</li>`).join("")}</ol><p class="small">Aluminum design strengths follow the Rules: sigma_y is the welded yield strength capped at 0.7 of the welded ultimate; Q, qa and tau_yw are as defined in 3-2-1/1.1.1 and 3-2-3.</p></div>`;
 // ---- 6 material
 h+=`<div class="sheet"><h2>6. Aluminum strength characteristics</h2><p class="small">Minimum values from ABS Rules for Materials and Welding (July 2022): unwelded 2-5-5, as-welded (butt weld) 2-4-5/17 Table 2.</p>`+_kv([["Alloy / temper / form",M.name],["Source",M.source],["Yield strength, unwelded (N/mm2)",M.sigma_y_unwelded],["Ultimate strength, unwelded (N/mm2)",M.sigma_u_unwelded],["Yield strength, as welded (N/mm2)",M.sigma_y_welded],["Ultimate strength, as welded (N/mm2)",M.sigma_u_welded],["Design yield sigma_y = min(welded yield, 0.7 welded ultimate) (N/mm2)",_n(M.sigma_y_design,1)],["sigma_ya = min(unwelded yield, 0.7 welded ultimate) (N/mm2)",_n(M.sigma_ya,1)],["qa = 115 / sigma_ya",_n(M.q_a,3)],["Q = max(0.9 + 115/sigma_ya, 635/(sigma_ya + sigma_uw))",_n(M.Q,3)],["Shear yield tau_yw = welded yield / sqrt(3) (N/mm2)",_n(M.tau_yw,1)],["Modulus of elasticity E (N/mm2)","69,000"]])+`</div>`;
 // ---- 7 design factors
 const ft=x=>x===undefined?"":` / ${_n(x*_M_FT,2)} ft`;
 h+=`<div class="sheet"><h2>7. Design factors (vessel particulars)</h2><table><tr><th>Definition</th><th>Symbol</th><th>Value</th><th>Notes</th></tr>
 ${[["Scantling length","L",V.L+" m"+ft(V.L),"3-1-1/3"],["Waterline length","Lw",V.Lw+" m"+ft(V.Lw),""],["Breadth, molded","B",V.B+" m"+ft(V.B),""],["Waterline beam, one hull","Bw",V.Bw+" m"+ft(V.Bw),""],["Number of hulls","n",V.n_hulls||1,"1 = monohull, 2 = catamaran"],["Depth","D",V.D+" m"+ft(V.D),""],["Draft","d",V.d+" m"+ft(V.d),""],["Displacement","Delta",V.delta_t+" t / "+_n(V.delta_t*0.98421,2)+" LT",""],["Block coefficient (from particulars)","Cb",_n(D.Cb_calc,3),"3-1-1/17"],["Design speed","V",V.V+" kn",""],["Running trim","tau",(V.tau??4)+" deg",""],["Deadrise at LCG","beta_cg",(V.beta_cg??15)+" deg",""],["Design significant wave height","h1/3",D.h13+" m",V.service||"high-speed"],["Wave parameter","H",_n(D.H,3)+" m","0.0172 L + 3.653"],["Acceleration at LCG, 3-2-2/1.1.3 equation","ncg",_n(D.ncg_formula,3)+" g","limited by Rule maximum"],["Acceleration used","ncg",_n(D.ncg_used,3)+" g",D.ncg_override!=null?"designer-supplied (model test / direct analysis)":"from equation"],["Rule constants","N1, N2, N3, kn","0.1, 0.0078, 9.8, 0.256","3-2-2/1.1.1"]].map(r=>`<tr><td>${_e(r[0])}</td><td>${_e(r[1])}</td><td>${_e(r[2])}</td><td>${_e(r[3])}</td></tr>`).join("")}</table></div>`;
 // ---- 8 pressures
 h+=`<div class="sheet"><h2>8. Design pressures</h2><table><tr><th>Member</th><th>Load case</th><th>Clause</th><th>Equation</th><th>Rule factors used</th><th>p (kN/m2)</th></tr>${(j.pressure_log||[]).map(x=>`<tr><td>${_e(x.item)}</td><td>${_e(x.case)}</td><td>${_e(x.clause)}</td><td class="eq">${_e(x.equation)}</td><td>${Object.entries(x.factors||{}).map(([k,v])=>`${_e(k)} = ${_n(v,3)}`).join("<br>")||"-"}</td><td class="n">${_n(x.p,2)}</td></tr>`).join("")}</table>${j.inputs.curves?`<p class="small">Digitised curves supplied for: ${Object.keys(j.inputs.curves).map(_e).join(", ")} (points in Appendix A).</p>`:""}</div>`;
 // ---- 9 plates
 h+=`<div class="sheet"><h2>9. Plate thickness calculations</h2>${(j.inputs.plates||[]).map(p=>`<h3>${_e(p.id)}</h3><p class="small">Location: ${_e(p.location)}. Stiffener spacing s = ${p.s_mm} mm; panel length l = ${p.l_mm} mm; thickness provided t = ${p.t_mm} mm (${_n(p.t_mm*_MM_IN,3)} in).</p>`+_resTable(grp(p.id))).join("")||"<p>No plating entered.</p>"}</div>`;
 // ---- 10 stiffeners
 h+=`<div class="sheet"><h2>10. Stiffener and frame calculations</h2>${(j.inputs.stiffeners||[]).map(s=>`<h3>${_e(s.id)}</h3><p class="small">${_e(s.profile)}; web ${s.hw_mm} x ${s.tw_mm} mm${s.bf_mm?`; flange ${s.bf_mm} x ${s.tf_mm} mm`:""}; attached plate ${s.t_plate_mm} mm; spacing ${s.spacing_mm} mm; span ${s.l_m} m; design-stress case ${_e(s.member_case)}.</p>`+_resTable(grp(s.id))).join("")||"<p>No stiffeners entered.</p>"}</div>`;
 // ---- 11 hull girder
 h+=`<div class="sheet"><h2>11. Longitudinal hull girder</h2>`+(hgr.length?(()=>{const g=j.inputs.hull_girder||{};return `<p>Section properties provided by the designer: section modulus at deck ${g.SM_deck_cm3} cm3, at bottom ${g.SM_bottom_cm3} cm3, moment of inertia ${g.I_cm4} cm4; the smaller modulus governs.</p>`+_resTable(hgr)})():"<p>Hull girder strength was not evaluated in this run.</p>")+`</div>`;
 // ---- 12 basis
 h+=`<div class="sheet"><h2>12. Basis, interpretations and limitations</h2><h3>12.1 Not evaluated in this report</h3><ul>${_LIMITS.map(x=>`<li>${_e(x)}</li>`).join("")}</ul><h3>12.2 Interpretation of Rule text</h3><ul>${_INTERP.map(x=>`<li>${_e(x)}</li>`).join("")}</ul><div class="box small">The calculation program is a design aid and has not been certified or approved by ABS or any other authority. The results are submitted for review by the reviewing body, who remain the judge of compliance. The designer is responsible for the input data and for items outside the scope listed above.</div></div>`;
 h+=`<div class="flow"><h2>13. Sign-off</h2><table class="sig"><tr><th></th><th>Name</th><th>Signature</th><th>Date</th></tr><tr><td>Drawn / prepared by</td><td>${_e(P.prepared_by)}</td><td></td><td></td></tr><tr><td>Checked by</td><td>${_e(P.checked_by)}</td><td></td><td></td></tr><tr><td>Approved by</td><td>${_e(P.approved_by||"")}</td><td></td><td></td></tr></table></div>`;
 h+=`<div class="sheet"><h2>Appendix A - Input data</h2><p class="small">Complete input file used for this run (reload with <i>Open JSON</i>).</p><pre>${_e(JSON.stringify(j.inputs,null,1))}</pre></div></body></html>`;
 return h}
