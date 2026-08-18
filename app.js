/* ==========================================================================
   CognitionBioChem — application logic

   Design rules, which exist because the previous version violated all three:
     1. No scientific value is rendered without a provenance record. renderValue()
        is the only path to the screen, and it emits a label rather than a number
        when the status is placeholder or not_computed.
     2. Nothing is synthesized. Every figure in the Structure tab is read from a
        file the user supplied. There is no fallback that invents data.
     3. Every renderer that allocates GPU or timer resources releases them.
   ========================================================================== */

'use strict';

const AA3 = {
  ALA:'A',ARG:'R',ASN:'N',ASP:'D',CYS:'C',GLN:'Q',GLU:'E',GLY:'G',HIS:'H',ILE:'I',
  LEU:'L',LYS:'K',MET:'M',PHE:'F',PRO:'P',SER:'S',THR:'T',TRP:'W',TYR:'Y',VAL:'V',MSE:'M'
};

/* AlphaFold's four published confidence bands. */
const PLDDT_BANDS = [
  { min: 90, max: 100, label: 'Very high (pLDDT > 90)', color: '#0053D6' },
  { min: 70, max: 90,  label: 'Confident (90 > pLDDT > 70)', color: '#65CBF3' },
  { min: 50, max: 70,  label: 'Low (70 > pLDDT > 50)', color: '#FFDB13' },
  { min: 0,  max: 50,  label: 'Very low (pLDDT < 50)', color: '#FF7D45' }
];

const state = {
  dataset: null,
  validation: null,
  prediction: null,
  regionFilter: 'all'
};

/* WebGL / chart lifecycle. The previous version created a renderer per modal open
   with no dispose, and its animation-loop guard tested a module-scope variable the
   next open had already reassigned, so loops accumulated. One viewer, explicitly
   torn down, removes the whole class of bug. */
let viewer3d = null;
let plddtChart = null;

/* --------------------------------------------------------------------------
   Provenance-aware rendering — the only way a value reaches the DOM
   -------------------------------------------------------------------------- */

function renderValue(v, opts = {}) {
  if (!v) return `<span class="val-missing">no record</span>`;
  const prov = v.provenance || {};
  const status = prov.status || 'unknown';

  if (status === 'not_computed') {
    return `<span class="val-missing" title="${esc(prov.note || '')}">not computed</span>`;
  }
  if (status === 'placeholder') {
    return `<span class="val-placeholder" title="${esc(prov.note || '')}">`
         + `illustrative only</span>`;
  }
  const num = typeof v.value === 'number'
    ? (Number.isInteger(v.value) ? v.value : v.value.toFixed(opts.dp ?? 2))
    : v.value;
  const units = v.units && v.units !== 'SMILES' ? ` <span class="units">${esc(v.units)}</span>` : '';
  const meta = [prov.method, prov.software, prov.source_id, prov.uncertainty]
    .filter(Boolean).join(' · ');
  return `<span class="val" title="${esc(meta)}">${esc(String(num))}${units}`
       + `<span class="badge ${status}">${esc(status.replace('_', ' '))}</span></span>`;
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

/* --------------------------------------------------------------------------
   Boot
   -------------------------------------------------------------------------- */

document.addEventListener('DOMContentLoaded', async () => {
  initTabs();
  initDropzone();
  await loadData();
});

async function loadData() {
  try {
    const [ds, vr] = await Promise.all([
      fetch('data/dataset.json').then(r => r.ok ? r.json() : null).catch(() => null),
      fetch('data/validation_gate.json').then(r => r.ok ? r.json() : null).catch(() => null)
    ]);
    state.dataset = ds;
    state.validation = vr;
  } catch (err) {
    console.error('data load failed', err);
  }

  if (!state.dataset) {
    document.querySelector('main').insertAdjacentHTML('afterbegin',
      `<div class="card error"><h2>Data layer not built</h2>
       <p>Run <code>./.venv/bin/python platform/build_dataset.py</code> to generate
       <code>data/dataset.json</code>, then reload. If you opened this file directly with
       <code>file://</code>, serve it instead —
       <code>python3 -m http.server</code> — because <code>fetch()</code> cannot read
       local files under the file scheme.</p></div>`);
    return;
  }

  renderDisclosure();
  renderOverview();
  renderValidation();
  renderCompounds();
  renderCandidates();
  renderRetracted();
}

function renderDisclosure() {
  const d = state.dataset.disclosure || {};
  setText('disclosure-headline', d.headline || '');
  setText('disclosure-detail', d.detail || '');
  setText('disclosure-sequences', d.sequences || '');
  setText('build-meta',
    `dataset ${state.dataset.schema_version} · built ${state.dataset.built} · `
    + `commit ${state.dataset.git_sha}`);
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

/* --------------------------------------------------------------------------
   Tabs
   -------------------------------------------------------------------------- */

function initTabs() {
  document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
      if (btn.dataset.tab === 'structure' && viewer3d) viewer3d.resize();
    });
  });
}

/* --------------------------------------------------------------------------
   Overview
   -------------------------------------------------------------------------- */

function renderOverview() {
  const ds = state.dataset;
  const valid = ds.candidates.filter(c => c.valid).length;
  const chem = ds.natural_products.filter(n => n.validation && n.validation.parses).length;
  const retracted = ds.candidates.filter(c => c.retracted_claims).length;
  const gate = state.validation;

  stats('overview-stats', [
    ['Candidate sequences', ds.candidates.length, `${valid} pass validation`],
    ['Natural products', ds.natural_products.length,
      `${chem} with a verified structure`],
    ['Retracted claims', retracted, 'preserved, not displayed as results'],
    ['Gate violations', gate ? gate.failures.length : '—',
      gate ? `${Object.keys(gate.counts).length} categories` : 'run the gate'],
    ['Predictions loaded', state.prediction ? 1 : 0,
      state.prediction ? state.prediction.source : 'none yet']
  ]);
}

function stats(containerId, rows) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = rows.map(([label, value, sub]) => `
    <div class="stat">
      <div class="stat-value">${esc(String(value))}</div>
      <div class="stat-label">${esc(label)}</div>
      ${sub ? `<div class="stat-sub">${esc(sub)}</div>` : ''}
    </div>`).join('');
}

/* --------------------------------------------------------------------------
   Validation report
   -------------------------------------------------------------------------- */

const CATEGORY_EXPLAIN = {
  thermodynamic_inconsistency:
    'ΔG and Kd cannot both be right. At 298.15 K they are locked together by '
    + 'ΔG = RT·ln(Kd), RT = 0.59248 kcal/mol.',
  sequence_invalid:
    'The sequence contains characters that are not standard amino acids, so it does not '
    + 'specify a synthesizable molecule and cannot be submitted to any predictor.',
  smiles_unparseable:
    'RDKit cannot parse the structure, so no chemical property can be computed.',
  smiles_wrong_molecule:
    'The stored structure is not the compound it is named after.',
  stereochemistry_undefined:
    'A flat structure with undefined stereocentres denotes 2^n distinct molecules. For a '
    + 'natural product with stereospecific activity, that makes the record ambiguous.',
  cysteine_parity:
    'An odd number of cysteines leaves at least one free thiol: expect disulfide '
    + 'scrambling and covalent dimerization.',
  disulfide_undeclared:
    'With four or more cysteines and no declared connectivity, the folded product is '
    + 'undefined.',
  duplicate_sequence:
    'Two supposedly distinct candidates share one sequence. Where their stated metrics '
    + 'differ, one molecule has been given several different binding free energies.',
  compartment_mismatch:
    'The stated target is cytoplasmic, but the molecule is an extracellular peptide with '
    + 'no cell-penetrating mechanism. It cannot reach its target.',
  affinity_implausible:
    'The stated affinity is tighter than biotin–streptavidin, among the strongest '
    + 'non-covalent interactions known.',
  prose_in_sequence_field:
    'The sequence field contains descriptive prose rather than a sequence.'
};

function renderValidation() {
  const gate = state.validation;
  const el = document.getElementById('validation-detail');
  if (!gate) {
    el.innerHTML = `<div class="card"><p>Run
      <code>./.venv/bin/python platform/validate.py --json &gt; data/validation_gate.json</code>
      to populate this tab.</p></div>`;
    return;
  }

  stats('validation-summary', [
    ['Result', gate.passed ? 'PASS' : 'FAIL', gate.passed ? '' : 'gate exits non-zero'],
    ['Violations', gate.failures.length, ''],
    ['Categories', Object.keys(gate.counts).length, '']
  ]);

  const byCat = {};
  gate.failures.forEach(f => (byCat[f.category] ||= []).push(f));
  el.innerHTML = Object.entries(byCat)
    .sort((a, b) => b[1].length - a[1].length)
    .map(([cat, items]) => `
      <div class="card">
        <h3>${esc(cat.replace(/_/g, ' '))}
          <span class="count-pill">${items.length}</span></h3>
        <p class="explain">${esc(CATEGORY_EXPLAIN[cat] || '')}</p>
        <ul class="violations">
          ${items.map(f => `<li><code>${esc(f.record)}</code><span>${esc(f.detail)}</span></li>`).join('')}
        </ul>
      </div>`).join('');
}

/* --------------------------------------------------------------------------
   Compounds
   -------------------------------------------------------------------------- */

function renderCompounds() {
  const el = document.getElementById('compound-list');
  el.innerHTML = state.dataset.natural_products.map(n => {
    const ok = n.validation && n.validation.parses;
    return `
    <div class="card compound ${ok ? '' : 'unverified'}">
      <div class="compound-head">
        <h3>${esc(n.name)}</h3>
        <span class="pill ${ok ? 'pill-ok' : 'pill-bad'}">
          ${ok ? 'structure verified' : 'structure unverified'}</span>
      </div>
      <p class="cls">${esc(n.class)}</p>
      ${ok ? `
        <div class="prop-grid">
          <div><span>Formula</span>${renderValue(n.formula)}</div>
          <div><span>Molecular weight</span>${renderValue(n.mol_weight)}</div>
          <div><span>cLogP</span>${renderValue(n.clogp)}</div>
          <div><span>TPSA</span>${renderValue(n.tpsa)}</div>
          <div><span>Defined stereocentres</span>${renderValue(n.stereocenters_defined)}</div>
          <div class="wide"><span>InChIKey</span>${renderValue(n.inchikey)}</div>
        </div>
        ${(n.cns_flags || []).length ? `<div class="flags"><strong>CNS exposure flags</strong>
          <ul>${n.cns_flags.map(f => `<li>${esc(f)}</li>`).join('')}</ul></div>` : ''}`
      : `<div class="notice">
           <p>${esc((n.smiles && n.smiles.provenance && n.smiles.provenance.note) || '')}</p>
           ${n.validation && n.validation.original_smiles_field
             ? `<p class="mono">stored value: <code>${esc(n.validation.original_smiles_field)}</code></p>` : ''}
           <p>No property is shown because none can be computed from an unparseable
              structure.</p>
         </div>`}
      <details>
        <summary>Reported binding residues</summary>
        <p class="warn-inline">${esc(n.binding_residues_text.provenance.note)}</p>
        <p class="mono">${esc(n.binding_residues_text.value)}</p>
      </details>
    </div>`;
  }).join('');
}

/* --------------------------------------------------------------------------
   Candidates
   -------------------------------------------------------------------------- */

function renderCandidates() {
  const regions = [...new Set(state.dataset.candidates.map(c => c.region).filter(Boolean))];
  const fr = document.getElementById('candidate-filters');
  fr.innerHTML = ['all', ...regions].map(r =>
    `<button class="chip ${state.regionFilter === r ? 'active' : ''}" data-region="${esc(r)}">
       ${esc(r)}</button>`).join('');
  fr.querySelectorAll('.chip').forEach(b => b.addEventListener('click', () => {
    state.regionFilter = b.dataset.region;
    renderCandidates();
  }));

  const list = state.dataset.candidates.filter(c =>
    state.regionFilter === 'all' || c.region === state.regionFilter);

  document.getElementById('candidate-list').innerHTML = list.map(c => `
    <div class="card candidate ${c.valid ? '' : 'invalid'}">
      <div class="compound-head">
        <h3>${esc(c.code)}</h3>
        <span class="pill ${c.valid ? 'pill-ok' : 'pill-bad'}">
          ${c.valid ? 'sequence valid' : 'sequence invalid'}</span>
      </div>
      ${c.name ? `<p class="cls">${esc(c.name)}</p>` : ''}
      ${c.valid ? `
        <div class="seq mono">${esc(c.sequence)}</div>
        <div class="prop-grid">
          <div><span>Length</span>${c.length} aa</div>
          <div><span>Molecular weight</span>${renderValue(c.mol_weight, { dp: 0 })}</div>
          <div><span>Net charge (pH 7.4)</span>${renderValue(c.net_charge, { dp: 1 })}</div>
          <div><span>Isoelectric point</span>${renderValue(c.isoelectric_point, { dp: 2 })}</div>
          <div><span>GRAVY</span>${renderValue(c.gravy, { dp: 2 })}</div>
          <div><span>Cysteines</span>${renderValue(c.cysteines)}</div>
          <div><span>Disulfides</span>${renderValue(c.disulfide_connectivity)}</div>
          <div><span>ΔG</span>${renderValue(c.binding_free_energy)}</div>
          <div><span>K<sub>d</sub></span>${renderValue(c.dissociation_constant)}</div>
          <div><span>pLDDT</span>${renderValue(c.plddt)}</div>
        </div>
        <button class="btn small copy-fasta" data-seq="${esc(c.sequence)}"
                data-code="${esc(c.code)}">Copy FASTA</button>`
      : `<div class="notice">
           <p><strong>Not submittable.</strong></p>
           <ul>${(c.errors || []).map(e => `<li>${esc(e)}</li>`).join('')}</ul>
         </div>`}
      ${(c.liabilities || []).length ? `
        <details class="liabilities">
          <summary>${c.liabilities.length} developability liabilit${c.liabilities.length === 1 ? 'y' : 'ies'}</summary>
          <ul>${c.liabilities.map(l => `<li>${esc(l)}</li>`).join('')}</ul>
        </details>` : ''}
      ${c.retracted_claims ? renderRetractedInline(c.retracted_claims) : ''}
    </div>`).join('');

  document.querySelectorAll('.copy-fasta').forEach(b =>
    b.addEventListener('click', () => {
      const fasta = `>${b.dataset.code}\n${b.dataset.seq}`;
      navigator.clipboard.writeText(fasta).then(() => {
        const old = b.textContent;
        b.textContent = 'Copied';
        setTimeout(() => { b.textContent = old; }, 1600);
      });
    }));
}

function renderRetractedInline(rc) {
  const a = rc.thermodynamic_audit;
  return `<details class="retracted">
    <summary>Retracted claims from the previous version</summary>
    <p class="explain">${esc(rc.reason)}</p>
    <ul>${Object.entries(rc.values).map(([k, v]) =>
      `<li><code>${esc(k)}</code>: <s>${esc(v)}</s></li>`).join('')}</ul>
    ${a ? `<p class="audit">Thermodynamic audit: the stated ΔG implies
      K<sub>d</sub> = ${esc(a.kd_implied_by_stated_dg.value)}, against the stated value —
      a gap of ${esc(a.discrepancy.value)} kcal/mol
      (${esc(a.discrepancy_orders.value)} orders of magnitude). ${esc(a.verdict)}.</p>` : ''}
  </details>`;
}

function renderRetracted() {
  const rows = state.dataset.candidates.filter(c => c.retracted_claims);
  document.getElementById('retracted-list').innerHTML = rows.length ? `
    <table class="prov-table">
      <thead><tr><th>Candidate</th><th>Asserted ΔG</th><th>Asserted K<sub>d</sub></th>
        <th>K<sub>d</sub> implied by that ΔG</th><th>Gap</th></tr></thead>
      <tbody>${rows.map(c => {
        const a = c.retracted_claims.thermodynamic_audit;
        if (!a) return '';
        return `<tr><td>${esc(c.code)}</td>
          <td><s>${esc(a.stated_dg.value)} kcal/mol</s></td>
          <td><s>${esc(formatKd(a.stated_kd.value))}</s></td>
          <td>${esc(a.kd_implied_by_stated_dg.value)}</td>
          <td class="gap">${esc(a.discrepancy.value)} kcal/mol</td></tr>`;
      }).join('')}</tbody>
    </table>` : '<p>None.</p>';
}

function formatKd(m) {
  if (m == null) return '—';
  const units = [['M', 1], ['mM', 1e-3], ['µM', 1e-6], ['nM', 1e-9], ['pM', 1e-12], ['fM', 1e-15]];
  for (const [u, f] of units) if (m / f >= 1) return `${(m / f).toPrecision(3)} ${u}`;
  return `${m.toExponential(2)} M`;
}

/* --------------------------------------------------------------------------
   Structure analysis — everything here is read from user files
   -------------------------------------------------------------------------- */

function initDropzone() {
  const dz = document.getElementById('dropzone');
  const input = document.getElementById('file-input');
  if (!dz) return;

  document.getElementById('browse-btn').addEventListener('click', () => input.click());
  input.addEventListener('change', () => handleFiles([...input.files]));

  ['dragenter', 'dragover'].forEach(e => dz.addEventListener(e, ev => {
    ev.preventDefault(); dz.classList.add('over');
  }));
  ['dragleave', 'drop'].forEach(e => dz.addEventListener(e, ev => {
    ev.preventDefault(); dz.classList.remove('over');
  }));
  dz.addEventListener('drop', ev => handleFiles([...ev.dataTransfer.files]));

  document.getElementById('load-demo').addEventListener('click', loadDemo);
}

function status(html, cls = '') {
  document.getElementById('load-status').innerHTML =
    `<div class="status ${cls}">${html}</div>`;
}

async function handleFiles(files) {
  if (!files.length) return;
  status('Reading files…');
  const bundle = { cif: null, cifName: '', jsons: {} };
  for (const f of files) {
    const text = await f.text();
    if (/\.(cif|mmcif|pdb)$/i.test(f.name)) {
      bundle.cif = text; bundle.cifName = f.name;
    } else if (/\.json$/i.test(f.name)) {
      try { bundle.jsons[f.name] = JSON.parse(text); }
      catch { status(`<strong>${esc(f.name)}</strong> is not valid JSON.`, 'error'); return; }
    }
  }
  if (!bundle.cif) {
    status('No coordinate file found. A <code>.cif</code>, <code>.mmcif</code> or '
         + '<code>.pdb</code> is required — nothing can be shown without real '
         + 'coordinates.', 'error');
    return;
  }
  buildPrediction(bundle);
}

async function loadDemo() {
  status('Fetching a genuine AlphaFold DB entry for human TrkB (Q16620) from EBI…');
  try {
    const meta = await fetch('https://alphafold.ebi.ac.uk/api/prediction/Q16620')
      .then(r => r.json());
    const e = meta[0];
    const [cif, pae] = await Promise.all([
      fetch(e.cifUrl).then(r => r.text()),
      fetch(e.paeDocUrl).then(r => r.json())
    ]);
    buildPrediction({ cif, cifName: 'AF-Q16620-F1-model.cif',
                      jsons: { 'predicted_aligned_error.json': pae } });
  } catch (err) {
    status(`Fetch failed: ${esc(err.message)}. This needs network access to `
         + `alphafold.ebi.ac.uk.`, 'error');
  }
}

function buildPrediction(bundle) {
  /* Use 3Dmol's mmCIF parser rather than hand-rolling one: it already reads the
     B-factor column, which is where AlphaFold writes pLDDT. */
  disposeViewer();
  const host = document.getElementById('viewer-3d');
  viewer3d = $3Dmol.createViewer(host, { backgroundColor: '#0b1020' });
  const fmt = /\.pdb$/i.test(bundle.cifName) ? 'pdb' : 'cif';
  viewer3d.addModel(bundle.cif, fmt);

  const model = viewer3d.getModel();
  const cas = model.selectedAtoms({ atom: 'CA' });
  if (!cas.length) {
    status('No Cα atoms found in that coordinate file.', 'error');
    disposeViewer();
    return;
  }

  const residues = cas.map(a => ({
    chain: a.chain || 'A', resi: a.resi, resn: a.resn,
    aa: AA3[(a.resn || '').toUpperCase()] || 'X',
    x: a.x, y: a.y, z: a.z, plddt: a.b
  }));

  let plddt = residues.map(r => r.plddt).filter(v => typeof v === 'number' && !isNaN(v));
  const warnings = [];
  if (plddt.length && Math.max(...plddt) <= 1.0) {
    plddt = plddt.map(v => v * 100);
    residues.forEach(r => { r.plddt *= 100; });
    warnings.push('pLDDT appeared to be on a 0–1 scale and was rescaled to 0–100.');
  }
  if (!plddt.length) {
    warnings.push('The B-factor column is empty, so no confidence values are available '
                + 'for this structure. The pLDDT panel is therefore blank.');
  }

  /* PAE from whichever confidence file was supplied. */
  let pae = null, ptm = null, iptm = null, rank = null, clash = null;
  for (const [name, j] of Object.entries(bundle.jsons)) {
    if (Array.isArray(j) && j[0] && j[0].predicted_aligned_error) {
      pae = j[0].predicted_aligned_error;                       // AlphaFold DB
    } else if (j && j.pae) {
      pae = j.pae;                                              // AF3 full_data
    }
    if (j && typeof j === 'object' && !Array.isArray(j)) {
      if ('ptm' in j) ptm = j.ptm;
      if ('iptm' in j) iptm = j.iptm;
      if ('ranking_score' in j) rank = j.ranking_score;
      if ('has_clash' in j) clash = j.has_clash;
    }
  }

  state.prediction = {
    source: detectSource(bundle), residues, plddt, pae, ptm, iptm, rank, clash,
    warnings, file: bundle.cifName
  };

  renderStructure();
  status(`Loaded <strong>${esc(bundle.cifName)}</strong> — ${residues.length} residues, `
       + `${plddt.length ? 'real pLDDT present' : 'no pLDDT in file'}, `
       + `${pae ? `PAE ${pae.length}×${pae.length}` : 'no PAE supplied'}.`, 'ok');
}

function detectSource(b) {
  const names = Object.keys(b.jsons).join(' ').toLowerCase();
  if (names.includes('summary_confidences') || names.includes('full_data')) return 'AlphaFold 3 / Server';
  if (names.includes('predicted_aligned_error')) return 'AlphaFold DB';
  if (names.includes('confidence')) return 'Boltz / Chai';
  return 'coordinates only';
}

function disposeViewer() {
  if (viewer3d) {
    try { viewer3d.clear(); } catch (_) { /* already gone */ }
    viewer3d = null;
  }
  const host = document.getElementById('viewer-3d');
  if (host) host.innerHTML = '';
  if (plddtChart) { plddtChart.destroy(); plddtChart = null; }
}

function bandFor(v) {
  return PLDDT_BANDS.find(b => v >= b.min && v < b.max) || PLDDT_BANDS[0];
}

function renderStructure() {
  const p = state.prediction;
  document.getElementById('structure-results').classList.remove('hidden');

  /* --- colour cartoon by the real per-residue pLDDT --- */
  if (p.plddt.length) {
    viewer3d.setStyle({}, { cartoon: { colorfunc: atom =>
      bandFor(typeof atom.b === 'number' ? atom.b : 0).color } });
  } else {
    viewer3d.setStyle({}, { cartoon: { color: '#7c8db5' } });
  }
  viewer3d.zoomTo();
  viewer3d.render();

  document.getElementById('plddt-legend').innerHTML = p.plddt.length
    ? PLDDT_BANDS.map(b =>
        `<span class="legend-item"><i style="background:${b.color}"></i>${esc(b.label)}</span>`
      ).join('')
    : '<span class="val-missing">no confidence values in this file</span>';

  const mean = p.plddt.length ? p.plddt.reduce((a, b) => a + b, 0) / p.plddt.length : null;
  const geo = geometryCheck(p.residues);

  stats('structure-stats', [
    ['Source', p.source, p.file],
    ['Residues', p.residues.length, `${new Set(p.residues.map(r => r.chain)).size} chain(s)`],
    ['Mean pLDDT', mean === null ? '—' : mean.toFixed(1), p.plddt.length ? 'from file' : 'unavailable'],
    ['pTM', p.ptm ?? '—', p.ptm == null ? 'not in supplied files' : 'from file'],
    ['ipTM', p.iptm ?? '—', p.iptm == null ? 'single chain or not supplied' : 'from file'],
    ['PAE', p.pae ? `${p.pae.length}×${p.pae.length}` : '—', p.pae ? 'from file' : 'not supplied']
  ]);

  document.getElementById('geometry-check').innerHTML = `
    <div class="prop-grid">
      <div><span>Mean Cα–Cα</span><strong>${geo.mean.toFixed(3)} Å</strong></div>
      <div><span>Standard deviation</span><strong>${geo.sd.toFixed(3)} Å</strong></div>
      <div><span>Range</span><strong>${geo.min.toFixed(2)} – ${geo.max.toFixed(2)} Å</strong></div>
      <div><span>Outliers beyond ±0.5 Å</span><strong>${geo.outliers} / ${geo.n}</strong></div>
    </div>
    <p class="verdict ${geo.plausible ? 'ok' : 'bad'}">
      ${geo.plausible
        ? 'Consistent with a real polypeptide backbone (expected 3.80 Å).'
        : 'NOT consistent with a polypeptide backbone. These coordinates were not produced '
          + 'by folding a protein.'}</p>`;

  renderPlddtChart(p);
  renderPae(p);
  renderLowConfidence(p);

  if (p.warnings.length) {
    document.getElementById('load-status').insertAdjacentHTML('beforeend',
      `<div class="status warn"><ul>${p.warnings.map(w => `<li>${esc(w)}</li>`).join('')}</ul></div>`);
  }
}

function geometryCheck(residues) {
  const d = [];
  for (let i = 1; i < residues.length; i++) {
    const a = residues[i - 1], b = residues[i];
    if (a.chain !== b.chain) continue;
    d.push(Math.hypot(b.x - a.x, b.y - a.y, b.z - a.z));
  }
  if (!d.length) return { n: 0, mean: 0, sd: 0, min: 0, max: 0, outliers: 0, plausible: false };
  const mean = d.reduce((x, y) => x + y, 0) / d.length;
  const sd = Math.sqrt(d.reduce((s, v) => s + (v - mean) ** 2, 0) / d.length);
  const outliers = d.filter(v => Math.abs(v - 3.80) > 0.5).length;
  return { n: d.length, mean, sd, min: Math.min(...d), max: Math.max(...d),
           outliers, plausible: outliers / d.length < 0.05 };
}

function renderPlddtChart(p) {
  if (plddtChart) { plddtChart.destroy(); plddtChart = null; }
  if (!p.plddt.length) return;
  const ctx = document.getElementById('plddt-chart');
  plddtChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: p.residues.map(r => `${r.aa}${r.resi}`),
      datasets: [{
        label: 'pLDDT (from file)',
        data: p.residues.map(r => r.plddt),
        borderColor: '#65CBF3',
        segment: { borderColor: c => bandFor(c.p1.parsed.y).color },
        borderWidth: 1.6, pointRadius: 0, tension: 0.15, fill: false
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: false },
                 tooltip: { callbacks: { title: i => `Residue ${i[0].label}` } } },
      scales: {
        x: { ticks: { maxTicksLimit: 14, color: '#7c8db5' }, grid: { display: false } },
        /* 0–100, not 50–100: clipping the axis hides exactly the low-confidence
           regions that matter most. */
        y: { min: 0, max: 100, ticks: { color: '#7c8db5' },
             grid: { color: 'rgba(255,255,255,0.05)' } }
      }
    }
  });

  const sorted = [...p.plddt].sort((a, b) => a - b);
  const pct = q => sorted[Math.floor(q * (sorted.length - 1))];
  const below70 = p.plddt.filter(v => v < 70).length / p.plddt.length;
  document.getElementById('plddt-stats').innerHTML = `
    <span>min <strong>${sorted[0].toFixed(1)}</strong></span>
    <span>median <strong>${pct(0.5).toFixed(1)}</strong></span>
    <span>max <strong>${sorted[sorted.length - 1].toFixed(1)}</strong></span>
    <span>below 70 <strong>${(below70 * 100).toFixed(1)}%</strong></span>`;
}

function renderPae(p) {
  const canvas = document.getElementById('pae-canvas');
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!p.pae) {
    ctx.fillStyle = '#7c8db5';
    ctx.font = '14px system-ui';
    ctx.fillText('No PAE matrix supplied.', 20, 40);
    document.getElementById('pae-max-label').textContent = '';
    document.getElementById('pae-mid').textContent = '';
    return;
  }
  /* Full resolution, square, no truncation. The previous version capped the grid at
     45 tokens and silently dropped the remaining residues. */
  const n = p.pae.length;
  const size = Math.min(canvas.width, canvas.height);
  const img = ctx.createImageData(size, size);
  let max = 0;
  for (const row of p.pae) for (const v of row) if (v > max) max = v;
  max = max || 31.75;

  for (let y = 0; y < size; y++) {
    const i = Math.floor(y * n / size);
    for (let x = 0; x < size; x++) {
      const j = Math.floor(x * n / size);
      const t = Math.min(p.pae[i][j] / max, 1);
      /* Monotonic sequential ramp: dark = confident, light = uncertain. */
      const r = Math.round(12 + t * 233), g = Math.round(28 + t * 210), b = Math.round(64 + t * 175);
      const k = (y * size + x) * 4;
      img.data[k] = r; img.data[k + 1] = g; img.data[k + 2] = b; img.data[k + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  document.getElementById('pae-max-label').textContent = `${max.toFixed(1)} Å`;
  document.getElementById('pae-mid').textContent = `${(max / 2).toFixed(1)} Å`;
}

function renderLowConfidence(p) {
  const el = document.getElementById('low-conf');
  if (!p.plddt.length) {
    el.innerHTML = '<p class="val-missing">No confidence values available.</p>';
    return;
  }
  const runs = [];
  let start = null;
  p.residues.forEach((r, i) => {
    const low = typeof r.plddt === 'number' && r.plddt < 70;
    if (low && start === null) start = i;
    if (!low && start !== null) { if (i - start >= 3) runs.push([start, i - 1]); start = null; }
  });
  if (start !== null && p.residues.length - start >= 3) runs.push([start, p.residues.length - 1]);

  el.innerHTML = runs.length ? `
    <table class="prov-table">
      <thead><tr><th>Residues</th><th>Length</th><th>Mean pLDDT</th><th>Sequence</th></tr></thead>
      <tbody>${runs.sort((a, b) => (b[1] - b[0]) - (a[1] - a[0])).slice(0, 12).map(([a, b]) => {
        const seg = p.residues.slice(a, b + 1);
        const m = seg.reduce((s, r) => s + r.plddt, 0) / seg.length;
        return `<tr><td>${seg[0].resi}–${seg[seg.length - 1].resi}</td>
          <td>${seg.length}</td><td>${m.toFixed(1)}</td>
          <td class="mono">${esc(seg.map(r => r.aa).join('').slice(0, 48))}</td></tr>`;
      }).join('')}</tbody>
    </table>`
    : '<p>No contiguous region of three or more residues falls below pLDDT 70.</p>';
}
