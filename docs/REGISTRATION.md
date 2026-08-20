# Registering this project: DOI and RRID

Three registries were considered. Two apply and one does not, and the one that does not is
recorded here so the question is not reopened later.

| Registry | Applies? | Why |
|---|---|---|
| **Zenodo** (DOI) | yes | archives a software release and mints a citable identifier |
| **SciCrunch** (RRID) | yes | registers research resources, software included |
| **bio.tools** | yes | the ELIXIR registry of bioinformatics software; this is squarely in scope |
| **Research Software Directory** | **check first** | see §5 — the main instance has a scoped listing policy |
| **ELN Finder** | **no** | a registry of *electronic lab notebooks*. This is a structural pharmacology workbench, not a notebook. Registering it there would return the wrong result to someone searching for an ELN. |

---

## 1. Zenodo — the order matters

The webhook only sees releases created *after* the repository is switched on. A release made
first produces no DOI, and the fix is to make another one.

1. Sign in at <https://zenodo.org> **with GitHub**.
2. Go to <https://zenodo.org/account/settings/github/>, find `hopejsh/CognitionBioChem`,
   toggle it **ON**. If it is not listed, use *Sync now*.
3. Only then publish the release:
   ```
   git tag -a v1.0.0 -m "CognitionBioChem v1.0.0"
   git push origin v1.0.0
   gh release create v1.0.0 --title "CognitionBioChem v1.0.0" --notes-file docs/RELEASE_NOTES_v1.0.0.md
   ```
4. Zenodo mints two DOIs within a few minutes. Take **both** from the record page.
5. Write them into `CITATION.cff` (`doi:` plus both `identifiers:` entries), `.zenodo.json`
   and the README badge. The **version** DOI must be redone by hand at every release; the
   concept DOI never changes.

`.zenodo.json` in the repository root is what Zenodo reads for title, authors, licence and
keywords. It is already written, so the deposit needs no manual editing on the Zenodo side.

## 2. SciCrunch — RRID

Account creation and form submission are yours to do; the content is below, ready to paste.

1. <https://scicrunch.org/resources> → *Register a resource* (free account required).
2. Resource type: **Software / Tool**.
3. Paste the fields from the block below.
4. Curation takes a few days. The result is an identifier of the form `RRID:SCR_XXXXXX`.
5. Send it back and it goes into `CITATION.cff` under `identifiers:` as `type: other`, into
   the README, and inline in any Methods section that uses the tool.

```
Resource Name:
  CognitionBioChem

Resource URL:
  https://github.com/hopejsh/CognitionBioChem

Resource Type:
  software application, data analysis software, data processing software

Description:
  A structural pharmacology workbench for cognition-related CNS targets, built so that a
  displayed number must trace to a computation. Boltz-2 v2.2.1 runs locally and produced every
  predicted structure; chemistry is validated with RDKit; every value carries a provenance
  record, and fields that were never computed render as labels rather than figures. Eight
  studies were pre-registered under content hashes before any data was seen, and their
  artefacts, analysis plans and prediction runs are held under content-addressed custody.

  The headline result is negative: across a 13-candidate screen and a 143-fold full-MSA rerun,
  designed peptides did not separate from composition-matched shuffles of their own amino
  acids (mean native ipTM 0.629 against a mean decoy of 0.628), and that hypothesis was
  falsified in all eleven retained versions of the two screening studies.

Keywords:
  structural biology, protein structure prediction, computational chemistry, drug discovery,
  reproducible research, research integrity, pre-registration, negative results, provenance,
  peptide design

License:
  Apache-2.0

Availability:
  Free, open source

Related identifiers:
  DOI: (add the Zenodo concept DOI once minted)
  ORCID: https://orcid.org/0000-0001-7914-5306
```

## 3. After a DOI or RRID is issued

Run through this list each time an identifier arrives; nothing here is automatic.

- [ ] `CITATION.cff` — `doi:`, both `identifiers:` DOI entries, and the RRID entry
- [ ] `.zenodo.json` — nothing to change; Zenodo owns the record after the first deposit
- [ ] `README.md` — DOI badge, and replace the "Not yet citable" paragraph
- [ ] `codemeta.json` — add `identifier` with the concept DOI
- [ ] `biotools.json` — add the DOI under `otherID`, once bio.tools has an entry
- [ ] `VERSION` — bump before the *next* release, not this one

One caution that applies to both registries: this repository's finding is negative. The
citation should be for what the software does, not as evidence that any candidate binds
anything.

---

## 4. bio.tools — the ELIXIR software registry

In scope: bio.tools registers bioinformatics and computational-biology software, which is what
this is. `biotools.json` in the repository root is written against biotoolsSchema and can be
pasted or imported.

1. <https://bio.tools> → sign in (ELIXIR AAI accepts ORCID and institutional logins).
2. *Add tool* → the form mirrors `biotools.json` field for field.
3. **The one part the file cannot fill in for you** is the EDAM ontology terms. bio.tools
   requires an ontology URI for every topic and operation, and those URIs are deliberately
   absent from `biotools.json`: a guessed ontology URI is worse than a blank one, because
   curators and every downstream query trust it. The file lists the term *names* under
   `_edam_terms_to_select_on_the_form`; type them into the form's autocomplete and it resolves
   the URIs against the live ontology.
4. Curation is manual and takes days to weeks. The result is a stable entry at
   `https://bio.tools/cognitionbiochem`.
5. Add that URL to `CITATION.cff` under `identifiers:` and to the README.

Note that `biotoolsID` must be unique across the registry. `cognitionbiochem` is the proposed
one; if it is taken the form will say so and a suffix is fine.

## 5. Research Software Directory — check eligibility before investing effort

The RSD is open-source software with several instances, and they do not share a listing
policy. <https://research-software-directory.org> is operated by the **Netherlands eScience
Center**, and its catalogue is scoped to software connected to that organisation and its
partners — a project with no such connection may simply not be accepted, and that is a policy
question rather than a metadata one. Other instances exist for other communities, for example
the Helmholtz **HIFIS** instance.

So, in order:

1. Read the onboarding policy on the instance you intend to use, and confirm this project is
   eligible **before** preparing anything further. If it is not, this is not a defect in the
   project and nothing needs fixing.
2. If eligible: sign in with ORCID, *Add software*, and point it at the GitHub repository. The
   RSD pulls language statistics, licence and commit activity from GitHub directly, and pulls
   releases and citation metadata from Zenodo — so **do this after the Zenodo DOI exists**, or
   the entry will show no citation.
3. `CITATION.cff` and `codemeta.json` are already in the repository root, which is where the
   RSD looks for them.
4. The RSD asks for a short "what does it do" statement separate from the description. Use:

   > Runs real structure prediction and chemical validation for cognition-related CNS targets,
   > with a provenance record on every displayed value and eight studies pre-registered under
   > content hashes. Its headline result is negative.

If the eligibility check fails, **bio.tools plus Zenodo plus an RRID already covers discovery,
citation and Methods-section identification**, which is what the registries are for.

