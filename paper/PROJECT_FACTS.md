# CognitionBioChem — what the study actually did and found

This is the ground truth. Every number below is read from the repository's artefacts.
Nothing here may be contradicted by the paper; nothing may be added to it by invention.

## Targets in the registry (16)

| UniProt | Gene | Protein | Genetic support for cognition | Domain of interest |
| --- | --- | --- | --- | --- |
| Q16620 | NTRK2 | BDNF/NT-3 growth factors receptor (TrkB) | weak | Ig-like C2-type 2 domain (Ig2, the domain the Trk field calls 'd5'), t |
| P22303 | ACHE | Acetylcholinesterase | none | The catalytic gorge of the carboxylesterase type-B domain: the catalyt |
| P49841 | GSK3B | Glycogen synthase kinase-3 beta | none | Protein kinase domain, specifically the ATP-binding pocket |
| Q14145 | KEAP1 | Kelch-like ECH-associated protein 1 | contradictory | Kelch six-bladed beta-propeller domain - the Nrf2 Neh2 ETGE/DLG degron |
| Q16236 | NFE2L2 | Nuclear factor erythroid 2-related factor 2 (Nrf2) | contradictory | Neh2 degron - the ETGE/DLG motifs that bind the KEAP1 Kelch propeller  |
| Q9NZC2 | TREM2 | Triggering receptor expressed on myeloid cells 2 | strong | Ig-like V-type ectodomain |
| Q9H461 | FZD8 | Frizzled-8 | none | Frizzled cysteine-rich domain (CRD), the Wnt/palmitoleate-binding modu |
| P36544 | CHRNA7 | Neuronal acetylcholine receptor subunit alpha-7 (alpha-7 nAChR) | weak | Extracellular ligand-binding domain (ECD) containing the agonist site  |
| Q12879 | GRIN2A | Glutamate receptor ionotropic, NMDA 2A (GluN2A) | moderate | Amino-terminal domain (ATD, also called NTD), the allosteric modulator |
| Q13224 | GRIN2B | Glutamate receptor ionotropic, NMDA 2B (GluN2B) | moderate | Amino-terminal domain (ATD/NTD); the ifenprodil allosteric site lies a |
| P43004 | SLC1A2 | Excitatory amino acid transporter 2 (EAAT2 / GLT-1) | weak | Transport (core) domain - the substrate and sodium translocation machi |
| P29474 | NOS3 | Nitric oxide synthase 3, endothelial (eNOS) | weak | Oxygenase domain - the heme, BH4 and L-arginine binding module |
| P25105 | PTAFR | Platelet-activating factor receptor (PAF-R) | none | Seven-transmembrane orthosteric ligand-binding pocket |
| P11229 | CHRM1 | Muscarinic acetylcholine receptor M1 | none | Seven-transmembrane orthosteric acetylcholine-binding pocket |
| P04629 | NTRK1 | High affinity nerve growth factor receptor (TrkA) | none | Ig-like C2-type 2 domain (Ig2, 'd5'), the NGF-binding domain |
| O00206 | TLR4 | Toll-like receptor 4 | none | Leucine-rich-repeat ectodomain and the MD-2 (LY96)/LPS interface |

## The 13 designed peptides that were screened

| Code | Target | native ipTM | best of 10 decoys | decoy mean | beats all decoys |
| --- | --- | --- | --- | --- | --- |
| MicroDual-Trem2-Nrf2-M5 | TREM2 | 0.9025 | 0.9724 | 0.9258 | False |
| HippoDual-TrkB-AMPK-X5 | NTRK2 | 0.8314 | 0.8754 | 0.7776 | False |
| BasalNgf-TrkA-B3 | NTRK1 | 0.818 | 0.7498 | 0.4952 | True |
| BasalAChE-Abeta-B4 | ACHE | 0.8105 | 0.7969 | 0.6612 | True |
| PfcDual-nACh-GluN2A-P5 | CHRNA7 | 0.7461 | 0.8658 | 0.5935 | False |
| MicroTlr4-Antagonist-M3 | TLR4 | 0.7223 | 0.9341 | 0.8528 | False |
| MicroTrem2-Agonist-M1 | TREM2 | 0.6929 | 0.9625 | 0.8483 | False |
| HippoTrk-Saponin-X1 | NTRK2 | 0.5408 | 0.566 | 0.4211 | False |
| PfcTrk-ErkEnhancer-P2 | NTRK2 | 0.5405 | 0.8037 | 0.5744 | False |
| PfcGluN2A-LTP-P3 | GRIN2A | 0.4953 | 0.7704 | 0.468 | False |
| BasalSuper-AChE-TrkA-B5 | ACHE | 0.4895 | 0.6963 | 0.5053 | False |
| PfcACh-PAM-P1 | CHRNA7 | 0.3567 | 0.7603 | 0.5978 | False |
| HippoAChE-AlkaPept-X2 | ACHE | 0.2265 | 0.7911 | 0.4401 | False |

## Headline results

- Full-MSA screen: mean native ipTM 0.6287 vs mean decoy 0.6278; paired difference 0.0009, Cohen's dz 0.0057, paired t-test p = 0.98
- 2 of 13 candidates beat all 10 of their own decoys; 1.182 expected by chance (p per candidate 0.0909), P(X>=2) = 0.3338
- Sampler noise floor (across seeds): ipTM SD 0.14943, complex pLDDT SD 2.6615, interface PAE min SD 4.6157
- Interface benchmark (16 X-ray peptide-receptor complexes): 62% CAPRI-acceptable, median DockQ 0.36, Spearman rho(ipTM, DockQ) = 0.8, median fnat 0.518
- AChE affinity benchmark: Spearman 0.3036, MAE 1.3593 log10, fraction within 1 log 0.5333
- PRODIGY: discrimination ratio 1.4, bootstrap CI [0.9629, 3.844], occupies 18% of the reference range
- AlphaFold DB cross-check: median Pearson r 0.7154 (single sequence) -> 0.8637 (full MSA)
- Slate: 8 pre-registered studies, 25 hypotheses (13 confirmed, 11 falsified, 1 not tested); 5 decided by a test statistic, 19 by a threshold
- H1 falsified in all 11 retained versions

## Methods actually used

- Structure prediction: Boltz-2 v2.2.1 (MIT code and weights), run locally on Apple silicon MPS.
- AlphaFold 3 NOT used (request-only, non-commercial, Linux/CUDA). AlphaFold Server NOT used
  (its terms prohibit automated protein-ligand / protein-peptide binding prediction).
- AlphaFold Protein Structure Database used under CC BY 4.0 as an independent comparison.
- Decoys: composition-matched shuffles of each candidate's own residues (3 per candidate in
  study #9 without an MSA, 10 per candidate in study #10 with a full MSA).
- DockQ v2 for interface quality against X-ray complexes; PRODIGY for a contact-based dG.
- ADMET-AI for ADMET, refused outside the applicability domain. RDKit for structure validation.
- Every study pre-registered under a content hash before its data was seen; Holm correction
  applied only to genuine test statistics, never to threshold criteria.

## What the study did NOT do

- No docking, no MM-GBSA, no FEP, no molecular dynamics.
- No wet-lab validation of any kind. No binding assay, no cell assay, no animal work.
- No generative model designed the peptides: they are hand-assembled concatenations of
  published motifs, pastiche scaffolds and one de novo helix, joined by GGGGS linkers.
  Of 16 motif entries only 7 carry a UniProt accession; 31 of 35 candidates carry at least
  one of 22 fragments the record itself calls unattributed.
- No BBB permeability measurement or prediction was performed.
- No free energy is emitted anywhere: the Boltz-2 affinity head is fitted to pooled
  Ki/Kd/IC50/EC50 labels and is never rendered as a thermodynamic quantity.

## Addenda required by the audit (read from the same artefacts)

### Construct sizes

- Interface-gate benchmark (data/study_peptide_interface.json): peptide length 7 to 17
  residues; receptor length 80 to 304 residues.
- Screened candidates (data/study_candidate_screen.json, native rows): peptide length 31 to 47
  residues; receptor construct length 156 to 608 residues.

### Interface gate, stratified by the training cutoff (data/study_peptide_interface.json)

The 16 complexes were curated in two date strata: pre_cutoff = deposited 2015-01-01 to
2023-05-31 (could be in training), post_cutoff = deposited 2023-07-01 to 2026-06-30 (could not).

- pre_cutoff: n = 8, k = 7 acceptable, fraction 0.875, Wilson 95% CI [0.5291, 0.9776],
  median DockQ 0.8725
- post_cutoff: n = 8, k = 3 acceptable, fraction 0.375, Wilson 95% CI [0.1368, 0.6943],
  median DockQ 0.18
- pooled: fraction_dockq_acceptable 0.625 (reported in the headline above as 62%),
  median DockQ 0.36, mean ipTM 0.7417, median iRMSD 3.526
- Spearman rho(ipTM, DockQ) = 0.8, raw p = 0.0002
- ipTM band confusion against CAPRI acceptable: confident_and_acceptable 9,
  confident_but_wrong 1, failed_band_but_acceptable 0, failed_band_and_wrong 4,
  grey_and_acceptable 1, grey_and_wrong 1

### Thresholds applied (platform/studies/peptide_interface.py)

- DOCKQ_ACCEPTABLE = 0.23 (CAPRI acceptable landmark); DockQ 0.80 is the high-quality landmark.
- ipTM interpretation bands: confident > 0.8, failed < 0.6.

### Corrected affinity benchmark (data/study_affinity_corrected.json)

- n_observed 14
- spearman_rho_corrected 0.1912; rho_v1 recorded in this artefact as 0.304 (the uncorrected
  benchmark's own value is 0.3036); delta_rho -0.1128
- bootstrap 95% CI on the corrected rho [-0.4622, 0.7303]; p 0.51258
- median_absolute_error_log10 1.0471; median_reference_log10_sd 0.4445
- median_records_per_compound 4.5; n_compounds_with_single_record 2;
  max_reference_log10_spread 4.996
- verdicts: H1 ranking with good references FALSIFIED; H2 reference fix matters FALSIFIED;
  H3 model dominates error CONFIRMED

### Seed-variance study (data/study_inference_variance_analysis.json)

- n_observed 87 runs over 6 constructs; the reported SDs are pooled across those constructs.
- pooled across-seed SD: complex pLDDT 2.6615, ipTM 0.14943, pTM 0.02618,
  interface PAE min 4.6157
- per-construct across-seed ipTM SD (recorded for 3 of the 6 constructs):
  BasalSuper-AChE-TrkA-B5 0.2344, AstroSuper-CBF-EAAT2-A5 0.0854, MicroAutophagy-Tag-M4 0.0689
- per-construct across-seed complex pLDDT SD: 0.131 to 3.46
- same-seed determinism: for each of the 6 constructs, 3 replicates returned 1 distinct
  complex pLDDT value, spread 0.0
- MSA mean shift 0.3306, paired t-test p 0.48925
