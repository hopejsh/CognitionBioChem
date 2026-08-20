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
  slate: null,
  structures: null,
  prediction: null,
  regionFilter: 'all',
  galleryFilter: 'complex'
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
    // fetch() is blocked outright under the file: scheme, so index.html also loads
    // data/dataset.js and data/validation_gate.js with <script> tags, which that policy does
    // not restrict. Both are generated from the same object as their .json twin in the same
    // pass of build_dataset.py. fetch wins when it works, so a served page always reads the
    // canonical JSON and the shim is only a fallback.
    const grab = f => fetch(f).then(r => r.ok ? r.json() : null).catch(() => null);
    const [ds, vr, sl, st] = await Promise.all([
      grab('data/dataset.json'), grab('data/validation_gate.json'),
      grab('data/slate.json'), grab('data/structures.json')
    ]);
    state.dataset = ds || window.__CBC_DATASET__ || null;
    state.validation = vr || window.__CBC_GATE__ || null;
    state.slate = sl || window.__CBC_SLATE__ || null;
    state.structures = st || window.__CBC_STRUCTURES__ || null;
  } catch (err) {
    console.error('data load failed', err);
  }

  if (!state.dataset) {
    // Two different causes were being reported as one, and the wrong one led. Opening this
    // file with file:// blocks fetch() by origin policy no matter how complete the data is,
    // so the old card told a reader whose data/dataset.json was present and current to go
    // rebuild it. Name the cause that actually applies.
    const isFile = location.protocol === 'file:';
    document.querySelector('main').insertAdjacentHTML('afterbegin', isFile
      ? `<div class="card error"><h2>Open this over HTTP, not <code>file://</code></h2>
         <p>The page is fine and the data may well be built already — but under the
         <code>file:</code> scheme the browser refuses every <code>fetch()</code> as a
         cross-origin request, so nothing can be loaded and the page cannot tell whether
         <code>data/dataset.json</code> exists.</p>
         <p>From the repository root run <code>python3 -m http.server</code> and open
         <code>http://localhost:8000/</code>.</p></div>`
      : `<div class="card error"><h2>Data layer not built</h2>
         <p><code>data/dataset.json</code> could not be loaded from this server. Run
         <code>./.venv/bin/python platform/build_dataset.py</code> from the repository root
         to generate it, then reload.</p></div>`);
    return;
  }

  /* Each section is rendered independently. They were called in a bare sequence, and one
     TypeError inside the slate template silently took the gallery and the AlphaFold panel
     down with it -- three blank tabs and no message, from one bad field. A section that
     cannot render now says so in its own place and the rest of the page still works. */
  /* The host id must be an element that EXISTS. Six of the nine named here were invented
     from the renderer's name — `overview`, `validation`, `compounds`, `candidates`,
     `retracted`, `disclosure` — so `getElementById` returned null and those six failures
     printed to the console and blanked a tab with no message, which is the behaviour this
     list was added to prevent. verify_frontend.py now checks every id in this table. */
  const sections = [
    ['disclosure-detail', renderDisclosure], ['headline-finding', renderHeadline],
    ['overview-stats', renderOverview],
    ['validation-detail', renderValidation], ['compound-list', renderCompounds],
    ['candidate-list', renderCandidates], ['retracted-list', renderRetracted],
    ['citation-block', renderCitation],
    ['slate-detail', renderSlate], ['gallery-list', renderGallery],
    ['af-arms', renderAlphaFold]
  ];
  for (const [host, fn] of sections) {
    try {
      await fn();
    } catch (err) {
      console.error(`${host} failed to render`, err);
      const el = document.getElementById(host);
      if (el) {
        el.innerHTML = `<div class="card error"><h3>This section could not be rendered</h3>
          <p class="mono">${esc(err && err.message ? err.message : String(err))}</p>
          <p class="note">The rest of the page is unaffected. This is a front-end fault, not
          a missing result — the underlying artefact is unchanged.</p></div>`;
      }
    }
  }
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
  const tabs = [...document.querySelectorAll('.tab')];

  function select(btn, focus) {
    tabs.forEach(b => {
      const on = b === btn;
      b.classList.toggle('active', on);
      /* The markup announced role="tablist" without any of the state the role promises, so a
         screen reader was told there were eight tabs and never which one was current. */
      b.setAttribute('aria-selected', String(on));
      b.tabIndex = on ? 0 : -1;
    });
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    if (focus) btn.focus();
    if (btn.dataset.tab === 'structure' && viewer3d) viewer3d.resize();
  }

  tabs.forEach((btn, i) => {
    btn.addEventListener('click', () => select(btn, false));
    btn.addEventListener('keydown', ev => {
      const step = { ArrowRight: 1, ArrowLeft: -1, Home: -i, End: tabs.length - 1 - i }[ev.key];
      if (step === undefined) return;
      ev.preventDefault();
      select(tabs[(i + step + tabs.length) % tabs.length], true);
    });
  });
}

/* --------------------------------------------------------------------------
   Overview
   -------------------------------------------------------------------------- */

/* The headline, assembled from the two studies that carry it. Every number is read from an
   artefact; the only thing hard-coded here is which studies count as the headline. */
function renderHeadline() {
  const sl = state.slate;
  if (!sl) return;
  const s10 = sl.studies.find(x => x.study_id.startsWith('msa-specificity'));
  const s9 = sl.studies.find(x => x.study_id.startsWith('candidate-screen'));
  if (!s10 || !s9) return;
  const m10 = s10.metrics || {}, m9 = s9.metrics || {};
  const nul = (s10.exploratory_metrics || {}).beats_all_decoys_null
            || m10.beats_all_decoys_null || {};
  const h1 = s10.hypotheses.find(h => h.name.startsWith('H1'));

  /* The robustness clause used to read "every correction that enlarged or cleaned the
     candidate set made the separation smaller, not larger". The retained artefacts refute
     it — the screen's separation ran −0.006, −0.015, −0.045, −0.041, −0.012, +0.001 across
     its six versions — and it was the one sentence in this card not read from a file, on a
     page that advertises the opposite. What IS true of every version is the verdict, and
     that is now counted from the artefacts. */
  const ver = sl.separation_across_versions || {};
  setText('headline-finding',
    `Across ${s9.n_observed} folds in study #${s9.slate_number} and ${s10.n_observed} in `
    + `study #${s10.slate_number}, the designed peptides did not separate from `
    + `composition-matched shuffles of their own amino acids. With a full MSA the mean `
    + `native ipTM is ${m10.mean_native_iptm} against a mean decoy of `
    + `${m10.mean_decoy_iptm}.`
    + (ver.all_falsified
        ? ` H1 has been falsified in all ${ver.n_versions} retained versions of these two `
          + `studies, across candidate sets from `
          + `${Math.min(...ver.versions.map(v => v.n_candidates))} to `
          + `${Math.max(...ver.versions.map(v => v.n_candidates))} designs — the verdict is `
          + `what survived every correction, not the size of the gap, which has moved in `
          + `both directions and has never left the sampler-noise floor.`
        : ''));

  stats('headline-stats', [
    ['Mean native ipTM', m10.mean_native_iptm, `vs ${m10.mean_decoy_iptm} for their own shuffles`],
    ['Beat all their decoys', `${nul.observed} of ${s10.n_candidates}`,
      `${nul.expected_under_null} expected by chance · P(X ≥ ${nul.observed}) = ${nul.p_at_least_observed}`],
    ['H1 natives separate', h1 ? h1.verdict : '—',
      h1 && h1.p_holm != null ? `paired t-test p = ${fmtP(h1.p_holm)}` : ''],
    ['Study #' + s9.slate_number + ' without an MSA', m9.native_minus_decoy_mean,
      `mean native minus decoy, over ${s9.n_candidates} candidates`]
  ]);
  setText('headline-note', nul.interpretation || '');

  /* Slate #11 DID compute a free energy, so the "it does not" bullet has to say so, and
     every number in that sentence has to come from the artefact. Writing them into the
     static markup made the page contradict its own promise that nothing on it is typed by
     hand, two cards below the promise. */
  const s11 = sl.studies.find(x => x.study_id.startsWith('prodigy'));
  const el = document.getElementById('prodigy-caveat');
  if (s11 && el) {
    const m = s11.metrics || {};
    const ci = m.discrimination_ratio_ci95_bootstrap || [];
    el.innerHTML = `Slate&nbsp;#${s11.slate_number} did compute them: PRODIGY returned a ΔG
      and a K<sub>d</sub> for ${s11.n_observed} of
      ${s11.n_observed + s11.n_failures} attempts, and the predicted range collapsed to
      ${(m.fraction_of_fit_range_occupied * 100).toFixed(0)}% of the reference span. Its
      discrimination ratio is ${m.discrimination_ratio}${ci.length === 2
        ? ` with a bootstrap 95% CI of [${ci[0]}, ${ci[1]}], which straddles the threshold`
        : ''}, while a one-way ANOVA on candidate identity gives p = ${
        fmtP(m.anova_candidate_identity_p)} — candidate identity <em>is</em> detectable, so
      the honest statement is that this design cannot resolve whether PRODIGY discriminates
      here, not that it does not. Either way no value from it is rendered.`;
  }
}

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
  /* The same counts the disclosure carries, read from the dataset rather than repeated in
     the markup — the markup's copy said "16 attributed motifs" and "14 of 35", and both were
     wrong while the record said otherwise a few hundred lines away. */
  setText('candidate-attribution', (state.dataset.disclosure || {}).sequences || '');
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
                data-code="${esc(c.code)}">Copy FASTA</button>
        ${structureButtons(c.code)}`
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
  document.querySelectorAll('#candidate-list button[data-structure]').forEach(b =>
    b.addEventListener('click', () => loadIndexedStructure(b.dataset.structure)));


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

/* The identifiers lived in the README and nowhere the page could show them, so a reader who
   never opened the repository could not cite the work. Everything here comes from
   dataset.citation, which build_dataset.py reads out of CITATION.cff — the same file the
   registries read, so the page cannot fall out of step with them. */
function renderCitation() {
  const c = (state.dataset || {}).citation;
  const host = document.getElementById('citation-block');
  if (!host) return;
  if (!c) {
    host.innerHTML = '<p class="val-missing">CITATION.cff was not read at build time.</p>';
    return;
  }
  const concept = (c.identifiers || []).find(i => i.type === 'doi');
  host.innerHTML = `
    <blockquote class="seq" style="font-family:inherit">
      ${esc(c.authors.join(', '))} (${esc((c.date_released || '').slice(0, 4))}).
      <em>${esc(c.title)}</em> (Version ${esc(c.version)}) [Computer software]. Zenodo.
      ${concept ? `https://doi.org/${esc(concept.value)}` : ''}
    </blockquote>
    <table class="prov-table">
      <thead><tr><th>Identifier</th><th>What it names</th></tr></thead>
      <tbody>${(c.identifiers || []).map(i => `
        <tr><td class="mono">${esc(i.value)}</td>
            <td>${esc(i.description || '')}</td></tr>`).join('')}</tbody>
    </table>
    <div class="prop-grid">
      <div><span>Version</span><strong>${esc(c.version)}</strong></div>
      <div><span>Released</span><strong>${esc(c.date_released)}</strong></div>
      <div><span>ORCID</span><strong class="mono">${
        esc((c.orcid[0] || '').replace('https://orcid.org/', ''))}</strong></div>
      <div><span>Licences</span><strong>${esc(c.licenses.join(', '))}</strong></div>
    </div>
    <p class="note"><strong>${esc(c.note)}</strong></p>
    <p class="hint">The code is Apache-2.0. The other four cover third-party data this
      repository redistributes, and CC-BY-SA-3.0 is share-alike — see <code>NOTICE</code>
      for which files fall under which.</p>`;
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
  /* Matches .viewer's CSS ground. Not pure white: two of AlphaFold's four published pLDDT
     band colours are light enough to wash out against #fff, and those colours are a standard
     a reader arrives already knowing, so the background moves rather than the ramp. */
  viewer3d = $3Dmol.createViewer(host, { backgroundColor: '#f2f4f7' });
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
    } else if (j && Array.isArray(j.matrix)) {
      pae = j.matrix;                                           // data/pae/*.json
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

  /* A gallery entry carries its own confidence JSON in the run directory, which is not
     fetched: the numbers are already in the index and were copied there from that same
     file. Preferring the index avoids a second request that could disagree with it. */
  const entry = bundle.entry || null;
  if (entry && entry.metrics) {
    if (ptm == null && entry.metrics.ptm != null) ptm = entry.metrics.ptm;
    if (iptm == null && entry.metrics.iptm != null) iptm = entry.metrics.iptm;
  }

  state.prediction = {
    source: entry ? entry.provenance.predictor : detectSource(bundle),
    residues, plddt, pae, ptm, iptm, rank, clash,
    warnings, file: entry ? entry.label : bundle.cifName, entry
  };

  renderStructure();
  renderStructureProvenance(entry);
  renderOverview();          // the "Predictions loaded" tile reads state.prediction
  ['src-badge-a', 'src-badge-b', 'src-badge-c'].forEach(id =>
    setText(id, entry ? 'from this repository' : 'from your file'));
  status(`Loaded <strong>${esc(entry ? entry.label : bundle.cifName)}</strong> — `
       + `${residues.length} residues, `
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
    viewer3d.setStyle({}, { cartoon: { color: '#64748b' } });
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
  const nChains = new Set(p.residues.map(r => r.chain)).size;

  stats('structure-stats', [
    ['Source', p.source, p.file],
    ['Residues', p.residues.length, `${nChains} chain(s)`],
    /* Every complex is 83-94% receptor by residue count, so one pooled mean is the
       receptor's mean wearing the complex's name: BasalAChE-Abeta-B4 reads 92.4 while its
       designed peptide is at 53.5. The per-chain split is the number that matters. */
    /* For a complex the per-chain split IS the value; the pooled mean is 90-94% receptor
       and demoting it to the sub-label is the only honest arrangement. */
    nChains < 2
      ? ['Mean pLDDT', mean === null ? '—' : mean.toFixed(1), 'from file']
      : ['Mean pLDDT per chain',
         chainMeans(p.residues).map(c => `${c.id} ${c.mean.toFixed(0)}`).join(' · '),
         `pooled ${mean === null ? '—' : mean.toFixed(1)}, which is ${
           Math.round(100 * p.residues.filter(r => r.chain === 'A').length
                      / p.residues.length)}% chain A by residue count`],
    ['pTM', p.ptm ?? '—', p.ptm == null ? 'not in supplied files' : 'from file'],
    /* A one-chain model has no interface, so a predictor's iptm: 0.0 is an absence rather
       than a score and is not shown as one. */
    ['ipTM', nChains < 2 ? '—' : (p.iptm ?? '—'),
      nChains < 2 ? 'undefined — one chain, no interface'
        : (p.iptm == null ? 'not in supplied files' : 'from file')],
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
        x: { ticks: { maxTicksLimit: 14, color: '#5a6678' }, grid: { display: false } },
        /* 0–100, not 50–100: clipping the axis hides exactly the low-confidence
           regions that matter most. */
        y: { min: 0, max: 100, ticks: { color: '#5a6678' },
             grid: { color: 'rgba(15,23,42,0.08)' } }
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
    ctx.fillStyle = '#5a6678';
    ctx.font = '14px system-ui';
    ctx.fillText('No PAE matrix supplied.', 20, 40);
    document.getElementById('pae-max-label').textContent = '';
    document.getElementById('pae-mid').textContent = '';
    const alt0 = document.getElementById('pae-alt');
    if (alt0) alt0.textContent = 'No predicted aligned error matrix accompanies this model.';
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
      /* Dark = confident, light = uncertain, as before — but the light end now stops at a
         visible neutral instead of near-white, which on a white page would have made the
         high-error regions indistinguishable from the background. */
      const r = Math.round(16 + t * 210), g = Math.round(46 + t * 183), b = Math.round(110 + t * 125);
      const k = (y * size + x) * 4;
      img.data[k] = r; img.data[k + 1] = g; img.data[k + 2] = b; img.data[k + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  document.getElementById('pae-max-label').textContent = `${max.toFixed(1)} Å`;
  document.getElementById('pae-mid').textContent = `${(max / 2).toFixed(1)} Å`;
  /* A heat map with no text alternative made the entire panel unavailable to a non-visual
     reader. The interface block is the part that carries meaning here, so it is what the
     description states. */
  const alt = document.getElementById('pae-alt');
  if (alt) {
    const ent = p.entry;
    const iface = ent && ent.interface_pae;
    alt.textContent = `Predicted aligned error matrix, ${n} by ${n} tokens, `
      + `ranging from 0 to ${max.toFixed(1)} angstrom. `
      + (iface
          ? `Across the ${iface.chain_pair} interface the mean is ${iface.mean_pae} and the `
            + `minimum ${iface.min_pae} angstrom, over ${iface.n_pairs} residue pairs.`
          : 'Dark regions off the diagonal mean two parts of the structure are confidently '
            + 'placed relative to each other.');
  }
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

/* --------------------------------------------------------------------------
   The pre-registered slate

   Read from data/slate.json, which platform/build_slate.py assembles out of the
   frozen plans and the study artefacts. Nothing here recomputes a verdict; a
   number that appears on this page appears in an artefact under runs/ custody.
   -------------------------------------------------------------------------- */

/* Not `ok`/`bad`. See the note beside .pill-met in styles.css: a verdict says whether a
   pre-registered rule fired, and several of the confirmations here are unwelcome news while
   the study's central falsification is the finding the project exists to report. Colouring
   them good and bad told a colour-scanning reader the opposite. */
const VERDICT_CLASS = { CONFIRMED: 'met', FALSIFIED: 'unmet', NOT_TESTED: 'warn' };

function renderSlate() {
  const sl = state.slate;
  const host = document.getElementById('slate-table');
  if (!sl) {
    if (host) host.innerHTML = '<p class="val-missing">data/slate.json is not built. '
      + 'Run <code>platform/build_slate.py</code>.</p>';
    return;
  }
  const c = sl.counts;
  stats('slate-stats', [
    ['Studies', c.studies, `${c.studies_confirmatory} confirmatory — see below`],
    ['Hypotheses', c.hypotheses, `${c.decided} decided, ${c.not_tested} not tested`],
    ['Falsified', c.falsified, 'kept and reported, not withdrawn'],
    ['Confirmed', c.confirmed, `only ${c.decided_by_a_test} of all `
      + `${c.hypotheses} were decided by a test at all`],
    ['Decided by a threshold', c.decided_by_a_threshold, 'a criterion, not a test result']
  ]);
  setText('slate-reading-note', sl.reading_note);
  setText('slate-numbering-note', sl.numbering_note || '');
  const leg = document.getElementById('slate-legend');
  if (leg) leg.innerHTML =
    `<span class="legend-item"><i style="background:#14508f"></i>criterion met or test
       significant</span>
     <span class="legend-item"><i style="background:#6b21a8"></i>not met</span>
     <span class="hint">These two colours say whether a pre-registered rule fired. They do
       NOT say whether the result is good news: several confirmations here confirm unwelcome
       statements, and the falsification in studies #9 and #10 is the finding this project
       exists to report.</span>`;
  /* Every study in this slate deviated from its registered plan, so every study's own audit
     records confirmatory = false. The panel headline says the plans were frozen before the
     data; without this the reader is not told that the freezing did not make the results
     confirmatory, it made the deviations visible. */
  const cf = document.getElementById('slate-confirmatory');
  if (cf) cf.innerHTML = `<strong>Not one study in this slate is confirmatory.</strong>
    <p>${esc(sl.confirmatory_note)}</p>`;

  host.innerHTML = `
    <table class="prov-table">
      <thead><tr><th>Study</th><th>Plan</th><th>n</th><th>Hypotheses</th></tr></thead>
      <tbody>${sl.studies.map(st => {
        const label = st.slate_number ? `#${st.slate_number}` : '—';
        return `<tr>
          <td><strong>${esc(label)}</strong> ${esc(st.title)}<br>
              <span class="hint mono">${esc(st.study_id)}</span></td>
          <td class="mono">${esc(st.plan_hash)}</td>
          <td>${st.n_observed ?? '—'}</td>
          <td>${st.hypotheses.map(h => `<span class="pill ${
                VERDICT_CLASS[h.verdict] === 'met' ? 'pill-met'
                : VERDICT_CLASS[h.verdict] === 'unmet' ? 'pill-unmet' : ''
              }" title="${esc(h.statement || '')}">${esc(
                h.name.replace(/^H\d+_/, '').replace(/_/g, ' '))} — ${
                esc((h.verdict || 'undecided').toLowerCase().replace(/_/g, ' '))}<em class="kind"> · ${
                h.kind === 'test' ? 'decided by a test' : 'decided by a threshold'}</em>${
                h.registered === false ? '<em class="kind"> · unregistered</em>' : ''
              }</span>`).join(' ')}</td>
        </tr>`;
      }).join('')}</tbody>
    </table>`;

  document.getElementById('slate-detail').innerHTML = sl.studies.map(st => `
    <div class="card">
      <h3>${st.slate_number ? `Slate #${st.slate_number} — ` : ''}${esc(st.title)}
        <span class="badge database mono">${esc(st.plan_hash)}</span></h3>
      <p>${esc(st.question || '')}</p>
      <div class="prop-grid">
        <div><span>Primary metric</span><strong class="mono">${esc(st.primary_metric || '—')}</strong></div>
        <div><span>Registered</span><strong>${esc((st.registered_utc || '').slice(0, 10))}</strong></div>
        <div><span>Observations</span><strong>${st.n_observed ?? '—'}</strong></div>
        <div><span>Technical failures</span><strong>${st.n_failures}</strong>
          ${st.n_failures && st.n_failures_detail ? (() => {
            const d = st.n_failures_detail;
            const sum = d.listed_in_failures + d.rows_marked_not_ok;
            /* Only say the two records overlap when they actually do. Study #1 has 0 listed
               and 2 rows, which do not overlap; #6 has 3 listed and 1 row that IS one of the
               three. Asserting an overlap in both cases produced "0 and 2 overlap, so 2". */
            return `<span class="hint">${d.listed_in_failures} in the failures list, ${
              d.rows_marked_not_ok} row${d.rows_marked_not_ok === 1 ? '' : 's'} marked not ok${
              sum === d.distinct ? '' : `; ${sum - d.distinct} counted in both`}, ${
              d.distinct} distinct</span>`;
          })() : ''}</div>
      </div>
      ${st.supersedes ? `<p class="note"><strong>Supersedes</strong>
        <code>${esc(st.supersedes)}</code> — ${esc(st.supersedes_reason || '')}</p>` : ''}
      ${(st.excluded_from_correction || []).length ? `<p class="note">
        <strong>Outside the multiplicity correction:</strong>
        ${st.excluded_from_correction.map(n => `<code>${esc(n)}</code>`).join(', ')} —
        threshold criteria, so no p-value was corrected for them.</p>` : ''}
      <table class="prov-table">
        <thead><tr><th>Hypothesis</th><th>Decided by</th><th>Observed</th><th>Verdict</th></tr></thead>
        <tbody>${st.hypotheses.map(h => `
          <tr>
            <td>${esc(h.statement || h.name)}<br>
                <span class="hint">confirmed if ${esc(h.confirmed_if || '—')}</span></td>
            <td>${h.kind === 'test'
                  ? `<span class="badge computed">test</span>`
                  : h.kind === 'criterion'
                    ? `<span class="badge database">threshold</span>`
                    : `<span class="val-missing">—</span>`}</td>
            <td class="mono">${observedCell(h)}</td>
            <td><span class="verdict ${VERDICT_CLASS[h.verdict] || ''}">${
                  esc((h.verdict || 'undecided').replace(/_/g, ' '))}</span>
                ${h.interval_contains_the_threshold
                  ? `<br><span class="warn-inline">this study's own interval contains the
                     threshold</span>` : ''}</td>
          </tr>
          ${h.confirmed_by_absence_note
            ? `<tr><td colspan="4" class="hint">${esc(h.confirmed_by_absence_note)}</td></tr>`
            : ''}
          ${h.unregistered_note
            ? `<tr><td colspan="4" class="warn-inline">${esc(h.unregistered_note)}</td></tr>`
            : ''}
          ${h.interval_contains_the_threshold
            ? `<tr><td colspan="4" class="warn-inline">${
               esc(h.interval_contains_the_threshold.note)}</td></tr>`
            : ''}`).join('')}</tbody>
      </table>
      ${(st.prespec_audit && st.prespec_audit.deviations || []).some(d => /metric/i.test(String(d)))
        ? `<div class="notice">
             <strong>Metrics the audit flagged as unregistered</strong>
             <p class="note">Named in the deviation list below, and shown here with their
               values — naming a metric without printing it tells a reader that something
               qualifies the verdict and withholds what.</p>
             <div class="prop-grid">${Object.entries(st.metrics || {})
               .filter(([k]) => (st.prespec_audit.deviations || [])
                 .some(d => String(d).includes(k)))
               .map(([k, v]) => `<div><span>${esc(k.replace(/_/g, ' '))}</span>
                 <strong>${esc(Array.isArray(v) ? `[${v.join(', ')}]`
                   : typeof v === 'object' && v ? (v.interpretation || JSON.stringify(v))
                   : String(v))}</strong></div>`).join('')}</div>
           </div>`
        : ''}
      ${Object.keys(st.exploratory_metrics || {}).length ? `
        <div class="notice">
          <strong>Measured after the fact, and it changes the reading</strong>
          <ul>${Object.entries(st.exploratory_metrics).map(([k, v]) => `
            <li><code>${esc(k)}</code> — ${esc((v && v.interpretation)
              || JSON.stringify(v))}</li>`).join('')}</ul>
        </div>` : ''}
      ${(st.known_confounds || []).length ? `<details class="liabilities">
        <summary>${st.known_confounds.length} confound${
          st.known_confounds.length === 1 ? '' : 's'} registered before the run</summary>
        <ul>${st.known_confounds.map(x => `<li>${esc(typeof x === 'string' ? x
              : (x.confound || JSON.stringify(x)))}</li>`).join('')}</ul></details>` : ''}
      ${st.prespec_audit && st.prespec_audit.deviations && st.prespec_audit.deviations.length
        ? `<div class="status warn"><strong>Protocol audit: deviations</strong>
           <ul>${st.prespec_audit.deviations.map(d => `<li>${esc(String(d))}</li>`).join('')}</ul>
           </div>`
        : '<p class="note">Protocol audit: no deviation from the registered plan.</p>'}
      <p class="hint">Artefact <code>${esc(st.artefact)}</code> ·
         plan <code>${esc(st.plan_file)}</code></p>
    </div>`).join('');
}

/* One cell, three cases, none of which may be silently conflated.

   A hypothesis decided by a threshold shows its observed value against that threshold. A
   hypothesis decided by a test shows its p. And a THRESHOLD hypothesis that happens to sit in
   a correction family shows its observed value AND says that the p-value beside it decided
   nothing — the ache study's H3 was rendered as `test / p = 0.814 / CONFIRMED`, so a reader
   saw a hypothesis confirmed at p = 0.814 by a rule that contains no p-value at all. */
function observedCell(h) {
  const bits = [];
  if (h.observed_text != null) {
    bits.push(`${esc(h.observed_text)}`
      + (h.threshold ? ` <span class="hint">vs ${esc(String(h.threshold))}</span>` : ''));
  }
  if (h.p_holm != null) {
    const p = `p = ${fmtP(h.p_holm)}`
      + (h.p_raw != null && h.p_raw !== h.p_holm
          ? ` <span class="hint">(raw ${fmtP(h.p_raw)})</span>` : '');
    bits.push(h.p_is_incidental
      ? `<span class="hint">${p} — reported, but did not decide this hypothesis</span>` : p);
  }
  /* A threshold hypothesis with no observed value has nothing behind its verdict, and an
     incidental p-value in the cell does not fill that gap — the ache study's H3 renders a
     green CONFIRMED whose own artefact carries an empty `criteria` block. Say so wherever
     the decision rule was a threshold and no observed value reached the page. */
  if (h.kind !== 'test' && h.observed_text == null && h.verdict) {
    bits.push('<span class="warn-inline">the artefact records this verdict with no observed '
            + 'value or threshold beside it</span>');
  }
  return bits.length ? bits.join('<br>') : '—';
}

function fmtP(v) {
  if (v == null) return '—';
  return v < 1e-4 ? v.toExponential(2) : v.toPrecision(3);
}

/* --------------------------------------------------------------------------
   AlphaFold DB against Boltz-2
   -------------------------------------------------------------------------- */

async function renderAlphaFold() {
  const d = await fetch('data/alphafold_db_comparison.json')
    .then(r => r.ok ? r.json() : null).catch(() => null);
  const host = document.getElementById('af-arms');
  if (!d) {
    if (host) host.innerHTML = '<p class="val-missing">data/alphafold_db_comparison.json '
      + 'could not be loaded. Under <code>file://</code> this is expected — serve the page '
      + 'over HTTP. Otherwise run <code>platform/studies/alphafold_db_compare.py</code>.</p>';
    return;
  }
  setText('af-question', d.question);
  document.getElementById('af-status').innerHTML =
    `<strong>${esc(d.status)}</strong><p>${esc(d.method)}</p>`;
  setText('af-source-note', d.source.note);
  setText('af-licence', d.source.licence);
  setText('af-cite', d.source.cite);
  document.getElementById('af-source-link').href = d.source.url;

  const arms = d.arms;
  const b = arms.boltz_full_msa;
  stats('af-stats', [
    ['Targets downloaded', d.coverage.downloaded, `of ${d.coverage.registry_targets} in the registry`],
    ['Targets compared', b.n_compared, 'those with a Boltz-2 receptor fold'],
    ['Median r (full MSA)', b.pearson_r_median, `range ${b.pearson_r_min} – ${b.pearson_r_max}`],
    ['Mean pLDDT offset', b.mean_offset_afdb_minus_boltz, 'AlphaFold DB minus Boltz-2'],
    ['Shift when Boltz gets an MSA',
      d.arm_agreement.median_shift_in_r_when_boltz_gets_an_msa,
      `median over ${d.arm_agreement.n_targets_in_both} targets`]
  ]);

  host.innerHTML = Object.entries(arms).map(([name, arm]) => `
    <h3>${esc(name.replace(/_/g, ' '))}</h3>
    <p class="note">${esc(arm.note)} — plan <code>${esc(arm.plan || '')}</code>,
       artefact <code>${esc(arm.study)}</code>.</p>
    <table class="prov-table">
      <thead><tr><th>Target</th><th>Residues</th><th>AlphaFold DB pLDDT</th>
        <th>Boltz-2 pLDDT</th><th>Pearson r</th><th>vs a mis-registered null</th></tr></thead>
      <tbody>${arm.rows.map(r => `<tr>
        <td><strong>${esc(r.target)}</strong>
            <span class="hint mono">${esc(r.uniprot)}</span></td>
        <td>${r.n_residues_compared}
            <span class="hint">${r.construct_span_canonical.join('–')}</span><br>
            <span class="hint">effective n ${r.effective_n_after_autocorrelation}
            after autocorrelation</span></td>
        <td>${r.afdb_mean_plddt}</td>
        <td>${r.boltz_mean_plddt}</td>
        <td><strong>${r.pearson_r}</strong>${(r.other_native_folds_of_this_receptor || []).length
          ? `<br><span class="hint">other folds of this receptor:
             ${r.other_native_folds_of_this_receptor.map(a => a.pearson_r).join(', ')}</span>`
          : ''}</td>
        <td>${r.shift_null
          ? `<span class="hint">95% of ${r.shift_null.n_shifts} shifted comparisons stay
             below |r| ${r.shift_null.null_abs_r_p95}; ${
             fmtFraction(r.shift_null.fraction_of_shifts_reaching_observed_r)} reach
             the observed value</span>`
          : '<span class="val-missing">chain too short to shift</span>'}</td></tr>`).join('')}</tbody>
    </table>
    <p class="hint">${arm.not_compared.length} target(s) not compared in this arm:
      ${esc(arm.not_compared.map(x => x.target).join(', ') || 'none')}.</p>`).join('');

  /* `what_this_does_support` ends "It is not a check on the peptide, on the interface, or on
     any claim in the slate" — the sentence a reader of a tab called "AlphaFold vs Boltz-2"
     most needs. Prepending it as the first item of a ul.crosses put a positive conclusion
     behind a red cross under a heading reading "What this cannot support", which inverted
     it; it gets its own paragraph. */
  setText('af-supports', d.what_this_does_support);
  document.getElementById('af-confounds').innerHTML =
    d.confounds.map(c => `<li>${esc(c)}</li>`).join('');
  setText('af-coverage', d.coverage.note);
  const ag = document.getElementById('af-agreement');
  if (ag) ag.innerHTML = `<p class="note">${esc(d.arm_agreement.reading)}</p>
    <div class="prop-grid">
      <div><span>Median shift</span><strong>${
        d.arm_agreement.median_shift_in_r_when_boltz_gets_an_msa}</strong></div>
      <div><span>Mean shift</span><strong>${
        d.arm_agreement.mean_shift_in_r_when_boltz_gets_an_msa}</strong></div>
      <div><span>Positive shifts</span><strong>${d.arm_agreement.n_positive_shifts} of ${
        d.arm_agreement.n_targets_in_both}</strong></div>
      <div><span>Sign test</span><strong>p = ${
        d.arm_agreement.sign_test_two_sided_p}</strong></div>
    </div>`;
}

/* --------------------------------------------------------------------------
   Structure gallery — the folds this repository computed

   The viewer could previously only show a file the reader supplied, while the
   repository held hundreds of its own under runs/ that nothing could reach.
   Every entry here loads a real coordinate file by fetch; under file:// that
   fetch is refused by origin policy, and the gallery says so rather than
   failing silently.
   -------------------------------------------------------------------------- */

const GALLERY_GROUPS = [
  ['complex', 'Candidate + receptor', 'Folded together with a full MSA — the models study #10 scored'],
  ['peptide_monomer', 'Peptide alone', 'The designed sequence folded by itself, single sequence'],
  ['receptor_afdb', 'Receptor (AlphaFold DB)', 'Deposited AlphaFold monomer, downloaded under CC BY 4.0']
];

function renderGallery() {
  const st = state.structures;
  const list = document.getElementById('gallery-list');
  if (!list) return;
  if (!st) {
    list.innerHTML = '<p class="val-missing">data/structures.json is not built. Run '
      + '<code>platform/build_structures.py</code>.</p>';
    return;
  }
  stats('gallery-stats', [
    ['Candidate + receptor', st.groups.complex, 'full MSA, study #10'],
    ['Peptide alone', st.groups.peptide_monomer, 'single sequence'],
    ['AlphaFold DB receptors', st.groups.receptor_afdb, 'downloaded, not computed here'],
    ['Candidates with a complex', st.coverage.candidates_with_a_complex,
      `of ${st.coverage.candidates_in_dataset} catalogued`]
  ]);

  document.getElementById('gallery-filters').innerHTML = GALLERY_GROUPS.map(([g, label]) =>
    `<button class="chip ${state.galleryFilter === g ? 'active' : ''}" data-group="${g}">
       ${esc(label)} <span class="count-pill">${st.groups[g]}</span></button>`).join('');
  document.querySelectorAll('#gallery-filters .chip').forEach(b =>
    b.addEventListener('click', () => {
      state.galleryFilter = b.dataset.group;
      renderGallery();
    }));

  const group = GALLERY_GROUPS.find(g => g[0] === state.galleryFilter);
  const rows = st.entries.filter(e => e.group === state.galleryFilter);
  list.innerHTML = `<p class="note">${esc(group ? group[2] : '')}</p>
    <table class="prov-table">
      <thead><tr><th>Structure</th><th>Chains</th><th>Confidence</th><th></th></tr></thead>
      <tbody>${rows.map(e => `
        <tr>
          <td><strong>${esc(e.label)}</strong><br>
              <span class="hint mono">${esc(e.provenance.predictor)} ·
              MSA ${esc(e.provenance.msa)}</span></td>
          <td>${e.chains.map(c => `${esc(c.id)} <span class="hint">${c.length} aa,
              pLDDT ${c.mean_plddt ?? '—'}</span>`).join('<br>')}</td>
          <td>${galleryConfidence(e)}</td>
          <td><button class="btn" data-structure="${esc(e.id)}">View</button></td>
        </tr>`).join('')}</tbody>
    </table>`;
  list.querySelectorAll('button[data-structure]').forEach(b =>
    b.addEventListener('click', () => loadIndexedStructure(b.dataset.structure)));

  setText('gallery-note', `${st.coverage.note} ${st.not_indexed.decoys}`);
}

function galleryConfidence(e) {
  const bits = [];
  if (e.metrics && e.metrics.iptm != null) bits.push(`ipTM <strong>${e.metrics.iptm}</strong>`);
  if (e.metrics && e.metrics.ptm != null) bits.push(`pTM ${e.metrics.ptm}`);
  if (e.interface_pae) {
    /* Study #7 measured that interface PAE tracks DockQ, so this is the quantity that
       speaks to PLACEMENT rather than to how the complex scored. It is shown beside ipTM
       for that reason, and labelled descriptive because no plan registered it. */
    bits.push(`interface PAE mean <strong>${e.interface_pae.mean_pae} Å</strong>,
      min ${e.interface_pae.min_pae} Å
      <span class="badge computed">computed here</span>`);
  }
  if (e.screen && e.screen.decoy_max != null) {
    /* Both decoy statistics, not just the maximum. Showing the max alone let a losing native
       read as an outlier accident; for 7 of 13 the decoy MEAN also beats the native, which
       is a different and worse fact. */
    const sc = e.screen;
    const beatenMax = sc.decoy_max > sc.native_iptm;
    bits.push(`<span class="${beatenMax ? 'warn-inline' : ''}">best of ${sc.n_decoys}
      decoys ${sc.decoy_max}${beatenMax ? ' — above its native' : ''}</span>`);
    bits.push(`<span class="${sc.decoy_mean_beats_native ? 'warn-inline' : 'hint'}">mean of
      its decoys ${sc.decoy_mean}${sc.decoy_mean_beats_native
        ? ' — the typical shuffle also wins' : ''}</span>`);
    if (sc.iptm_without_msa != null) {
      bits.push(`<span class="hint">without an MSA it scored ${sc.iptm_without_msa}; the
        MSA moved it by ${sc.delta_vs_single_sequence > 0 ? '+' : ''}${
        sc.delta_vs_single_sequence}</span>`);
    }
  }
  /* Last, not first: this explains which terms are ABSENT, so putting it above the numbers
     that are present buried the headline confidence under a footnote. */
  if (e.metrics && e.metrics.terms_undefined) {
    bits.push(`<span class="hint">${esc(e.metrics.terms_undefined)}</span>`);
  }
  if (!bits.length) {
    /* This said "no confidence file was retained" and fired on all 16 AlphaFold DB rows,
       each of which ships a ~1.9 MB PAE file that the page fetches the moment you click
       View. The absence is in what AlphaFold DB publishes, not in what is on disk. */
    bits.push(e.group === 'receptor_afdb'
      ? '<span class="hint">AlphaFold DB publishes no pTM or ipTM for a monomer; its '
        + 'per-residue pLDDT and full PAE matrix are here and are shown on View.</span>'
      : '<span class="hint">no confidence file was retained for this run</span>');
  }
  return bits.join('<br>');
}

async function loadIndexedStructure(id) {
  const e = (state.structures.entries || []).find(x => x.id === id);
  if (!e) return;
  document.querySelector('.tab[data-tab="structure"]').click();
  status(`Loading <strong>${esc(e.label)}</strong> from <code>${esc(e.cif)}</code>…`);
  try {
    const cif = await fetch(e.cif).then(r => {
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      return r.text();
    });
    const jsons = {};
    if (e.pae) {
      const pae = await fetch(e.pae).then(r => r.ok ? r.json() : null).catch(() => null);
      if (pae) {
        /* Two shapes reach here. data/pae/*.json is this repository's own export and
           carries {matrix}; a deposited AlphaFold DB file is a one-element array whose
           member holds predicted_aligned_error. buildPrediction already knows the second
           shape, so only the first needs naming. */
        jsons[e.pae_format === 'alphafold_db'
          ? 'predicted_aligned_error.json' : 'cbc_pae.json'] = pae;
      }
    }
    buildPrediction({ cif, cifName: e.cif.split('/').pop(), jsons, entry: e });
  } catch (err) {
    status(location.protocol === 'file:'
      ? `<strong>${esc(e.label)}</strong> could not be loaded because this page is open `
        + `over <code>file://</code>, where the browser refuses every <code>fetch()</code> `
        + `as cross-origin. Run <code>python3 -m http.server</code> in the repository root `
        + `and open <code>http://localhost:8000/</code>.`
      : `Could not load <code>${esc(e.cif)}</code>: ${esc(err.message)}.`, 'error');
  }
}

function renderStructureProvenance(e) {
  const host = document.getElementById('structure-provenance');
  if (!host) return;
  if (!e) { host.innerHTML = ''; return; }
  const p = e.provenance || {};
  const s = e.screen;
  host.innerHTML = `
    <div class="card">
      <h3>Where this structure came from</h3>
      <div class="prop-grid">
        <div><span>Predictor</span><strong>${esc(p.predictor || '—')}</strong></div>
        <div><span>MSA</span><strong>${esc(p.msa || '—')}</strong></div>
        <div><span>Held at</span><strong class="mono">${esc(p.run || p.source || '—')}</strong></div>
        ${p.plan ? `<div><span>Registered plan</span><strong class="mono">${
            esc(p.plan.slice(0, 12))}</strong></div>` : ''}
        ${e.construct ? `<div><span>Construct</span><strong>${esc(e.construct.basis)}
            ${e.construct.canonical_span.join('–')}</strong></div>` : ''}
        ${e.uniprot ? `<div><span>UniProt</span><strong class="mono">${esc(e.uniprot)}</strong></div>` : ''}
      </div>
      <p class="note">${esc(p.note || '')}</p>
      ${e.interface_pae ? `
        <h3>Interface PAE <span class="badge computed">computed here</span></h3>
        <div class="prop-grid">
          <div><span>Chain pair</span><strong>${esc(e.interface_pae.chain_pair)}</strong></div>
          <div><span>Mean</span><strong>${e.interface_pae.mean_pae} Å</strong></div>
          <div><span>Minimum</span><strong>${e.interface_pae.min_pae} Å</strong></div>
          <div><span>Residue pairs</span><strong>${e.interface_pae.n_pairs}</strong></div>
        </div>
        <p class="note">${esc(e.interface_pae.note)} Study #7 found interface PAE tracks
          DockQ on an X-ray benchmark, so this says something about where the peptide is
          placed — but a confident placement against a decoy scores just as well, and
          several decoys here do.</p>` : ''}
      ${s && s.native_iptm != null ? `
        <h3>How study #10 scored it</h3>
        <div class="prop-grid">
          <div><span>Native ipTM</span><strong>${s.native_iptm}</strong></div>
          <div><span>Decoy mean</span><strong>${s.decoy_mean}</strong></div>
          <div><span>Decoy max</span><strong class="${
            s.decoy_max > s.native_iptm ? 'bad' : ''}">${s.decoy_max}</strong></div>
          <div><span>Beats all ${s.n_decoys} decoys</span><strong>${
            s.beats_all_decoys ? 'yes' : 'no'}</strong></div>
        </div>
        <p class="verdict ${!s.beats_all_decoys ? 'bad'
          : (s.empirical_p != null && s.empirical_p >= 0.05) ? 'warn' : 'ok'}">${s.beats_all_decoys
          ? 'This candidate outscored every composition-matched shuffle of its own residues — '
            + `and its own empirical p is ${s.empirical_p}, which clears no conventional `
            + 'threshold. ' + esc(screenLevelNull())
          : 'At least one shuffle of this candidate’s own amino acids scored as high or '
            + 'higher. Confidence here is not evidence of a designed interaction.'}</p>` : ''}
      ${e.comparison ? `
        <h3>AlphaFold DB against Boltz-2 on this receptor</h3>
        <div class="prop-grid">
          <div><span>Pearson r</span><strong>${e.comparison.pearson_r}</strong></div>
          <div><span>Residues compared</span><strong>${e.comparison.n_residues_compared}</strong></div>
          <div><span>AlphaFold mean pLDDT</span><strong>${e.comparison.afdb_mean_plddt}</strong></div>
          <div><span>Boltz-2 mean pLDDT</span><strong>${e.comparison.boltz_mean_plddt}</strong></div>
        </div>` : ''}
      ${p.url ? `<p class="hint"><a href="${esc(p.url)}" target="_blank" rel="noopener">${
        esc(p.url)}</a> — ${esc(p.licence || '')}</p>` : ''}
    </div>`;
}

/* A candidate card offers a structure only when one actually exists. 22 of the 35 catalogued
   candidates were ever folded and 13 were folded with a receptor, so a button on every card
   would promise a file for cases where there is none. */
function structureButtons(code) {
  const st = state.structures;
  if (!st || !st.by_candidate || !st.by_candidate[code]) return '';
  return st.by_candidate[code].map(id => {
    const e = st.entries.find(x => x.id === id);
    if (!e) return '';
    const label = e.group === 'complex' ? `View complex with ${e.target}` : 'View peptide fold';
    return ` <button class="btn small" data-structure="${esc(id)}">${esc(label)}</button>`;
  }).join('');
}

/* The screen-level null, read from study #10's artefact rather than typed here. A literal
   "Two of thirteen did, and 1.18 are expected to by chance" sat in this file under a page
   that promises no number on it is hand-typed; it was correct, and it would have gone stale
   in silence the first time the candidate set changed size. */
function screenLevelNull() {
  const st = (state.slate && state.slate.studies || [])
    .find(x => x.study_id.startsWith('msa-specificity'));
  const n = st && (st.exploratory_metrics || {}).beats_all_decoys_null;
  return n ? n.interpretation : '';
}

function chainMeans(residues) {
  const by = new Map();
  residues.forEach(r => {
    if (typeof r.plddt !== 'number' || isNaN(r.plddt)) return;
    if (!by.has(r.chain)) by.set(r.chain, []);
    by.get(r.chain).push(r.plddt);
  });
  return [...by.entries()].map(([id, v]) => ({ id, mean: v.reduce((a, b) => a + b, 0) / v.length }));
}

/* The generator reports this as a NUMBER when some shift reaches the observed r and as a
   STRING upper bound ("<0.0019") when none does — because zero out of a few hundred heavily
   overlapping shifts is a bound, not a probability of zero. Multiplying the string by 100
   rendered a literal "NaN%" on all fourteen AlphaFold rows. */
function fmtFraction(v) {
  if (typeof v === 'number') return `${(v * 100).toFixed(1)}%`;
  const m = /^<\s*([\d.eE+-]+)$/.exec(String(v));
  return m ? `under ${(parseFloat(m[1]) * 100).toPrecision(2)}%` : esc(String(v));
}
