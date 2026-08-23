# Registering this project: DOI and RRID

Three registries were considered. Two apply and one does not, and the one that does not is
recorded here so the question is not reopened later.

| Registry | Applies? | Why |
|---|---|---|
| **Zenodo** (DOI) | yes | archives a software release and mints a citable identifier |
| **SciCrunch** (RRID) | yes | registers research resources, software included |
| **bio.tools** | yes | the ELIXIR registry of bioinformatics software; this is squarely in scope |
| **Research Software Directory** | **not pursued** | see §5 — the main instance's catalogue is scoped to one organisation's orbit |
| **ELN Finder** | **no** | a registry of *electronic lab notebooks*. This is a structural pharmacology workbench, not a notebook. Registering it there would return the wrong result to someone searching for an ELN. |

---

## 1. Zenodo — **done**, and a warning about how it went wrong

Concept DOI **10.5281/zenodo.22032684** · v1.0.0 DOI **10.5281/zenodo.22032685**, minted
2026-08-20.

> **Where this repository stands right now.** Version 1.1.0 is not yet deposited: it has no git
> tag and no version DOI. The most recent published release is v1.0.0, and the concept DOI
> resolves to that record until 1.1.0 is published. `VERSION`, `CITATION.cff`, `codemeta.json`,
> `.zenodo.json` and `biotools.json` all read `1.1.0` and describe this tree;
> `10.5281/zenodo.22032685`, the `v1.0.0` tag URL and the v1.0.0 tarball are pinned to a
> deposit that already exists and keep reading `1.0.0`, because a version DOI and a pushed tag
> cannot be relabelled. `platform/check_version_stamps.py` holds both halves apart and fails if
> either drifts.

> **The mistake that cost an hour.** The release command was first run from the wrong working
> directory. It tagged and released `hopejsh/aaa-rns` instead, that repository also had the
> Zenodo webhook enabled, and Zenodo immediately minted a bogus `v1.0.0` deposit whose concept
> DOI then resolved to it instead of to AAA-RNS v2.1.0 — a DOI cited in that project's README.
> Recovery: delete the Zenodo record (owners can, within 30 days of publishing; the reason to
> select is *Duplicate of another record*, **not** *Retraction/Withdrawal*, which is published
> on the tombstone and reads as a scholarly retraction), then delete the GitHub release and
> tag.
>
> The fix that followed was `release.sh`. Telling the reader to "use `git -C`" was not enough:
> the very next attempt pasted the corrected commands with their placeholders intact and
> created a tag named `vX.Y.Z`. The guard has to be in the tool, not in the instructions.

The webhook only sees releases created *after* the repository is switched on. A release made
first produces no DOI, and the fix is to make another one.

1. Sign in at <https://zenodo.org> **with GitHub**.
2. Go to <https://zenodo.org/account/settings/github/>, find `hopejsh/CognitionBioChem`,
   toggle it **ON**. If it is not listed, use *Sync now*.
3. Only then publish the release, with `./release.sh`:
   ```
   ./release.sh 1.1.0
   ```

   **Do not hand-type the git and gh commands.** This section used to show them with `vX.Y.Z`
   and `docs/...` as placeholders, and both times they were run they were run literally —
   once from the wrong directory, which released a different repository and made Zenodo mint
   a bogus DOI against a published project, and once verbatim, which created a tag actually
   named `vX.Y.Z`. A command a reader is expected to edit before running is a command that
   will eventually be run unedited.

   `release.sh` takes the version as its only argument and derives everything else. Before it
   touches anything it checks that `origin` really is `hopejsh/CognitionBioChem`, that the
   release notes exist, that the working tree is clean, that the tag is new, that `VERSION`
   agrees with the argument, and that `verify_all.py` passes — then asks for confirmation,
   noting that a Zenodo DOI cannot be un-minted. It refuses a placeholder version outright.
4. Zenodo mints two DOIs within a few minutes. Take **both** from the record page.
5. Write them into `CITATION.cff` (`doi:` plus both `identifiers:` entries), `.zenodo.json`
   and the README badge. The **version** DOI must be redone by hand at every release; the
   concept DOI never changes.

`.zenodo.json` in the repository root is what Zenodo reads for title, authors, licence and
keywords. It is already written, so the deposit needs no manual editing on the Zenodo side.

> **`.zenodo.json` governs the NEXT deposit; it cannot change the one already published.**
> The v1.0.0 record was minted on 2026-08-20 from the description as it stood then, and that
> description counted the slate at **eight**, which is what the repository held that day.
> Study #12, `interface-null-positive-control-v1`, was registered on
> **2026-08-22T06:43:11Z** — two days
> after the deposit — so the published record describes a slate that does not contain the
> study which forced this project's central retraction. Editing this file corrects every
> future deposit and nothing on Zenodo today.
>
> Two ways to correct the existing record, and the choice is the author's:
>
> 1. **Edit the published record's metadata in place.** Zenodo allows the description of a
>    published record to be edited after publication (the *files* are frozen; the metadata is
>    not), through the record's own edit form on zenodo.org. Both DOIs keep resolving. This is
>    the only route that fixes what someone citing 10.5281/zenodo.22032685 reads today.
> 2. **Leave it and let the next release supersede it.** Publishing v1.1.0 creates a new
>    version of the record from the corrected `.zenodo.json`, and the concept DOI
>    10.5281/zenodo.22032684 resolves to it. The v1.0.0 version DOI keeps its original
>    description, which is defensible — a version DOI is meant to be frozen to what that
>    release said — but anyone citing the version DOI still reads the superseded count.
>
> Whichever is chosen, the tagged v1.0.0 release and the working tree disagree about the size
> of the slate, because #12 arrived after the tag. `VERSION` now reads `1.1.0` and
> `docs/RELEASE_NOTES_v1.1.0.md` — generated from the artefacts by
> `platform/build_release_notes.py` — describes the slate that contains #12, so route 2 is
> prepared and `./release.sh 1.1.0` is the command that takes it. The v1.0.0 note is frozen to
> what that release said and marked as such at the top of the file; it is not edited to match
> today. All four metadata files now read `1.1.0` and say plainly that 1.1.0 is undeposited, so
> the disagreement is disclosed rather than silent — but it is not resolved. It resolves only
> when v1.1.0 is actually cut and the **new version DOI** the webhook mints is written back
> into `CITATION.cff`, `biotools.json` and the README, and the disclosure sentence is removed
> from the five surfaces that carry it. Both steps are hand work; `platform/check_version_stamps.py`
> fails until they are done, which is the point of it.

**What the author has to do, and what is deliberately left undone here.** No Zenodo deposit was
created and no tag was pushed in preparing this. Three things remain, in this order:

1. **Decide route 1 or route 2 above for the already-published v1.0.0 record.** Only route 1 —
   editing the published record's metadata on zenodo.org — changes what someone citing
   `10.5281/zenodo.22032685` reads today. Nothing in this repository can do it.
2. **Cut v1.1.0**: `./release.sh 1.1.0`, from this directory, after reading the confirmation
   prompt. The Zenodo webhook must be switched on for `hopejsh/CognitionBioChem` first (§1
   step 2) or the release mints no DOI at all.
3. **Write the minted version DOI back**, by hand, into `CITATION.cff` (`identifiers:`),
   `biotools.json` (`otherID` and `download`), and the README's version-DOI paragraph; replace
   `RELEASE-NOTE-GENERATED` with `RELEASE-NOTE-FROZEN` at the top of
   `docs/RELEASE_NOTES_v1.1.0.md`; then bump `VERSION` for the next cycle. Only after step 3
   does `check_version_stamps.py` go green again — until then it names each surface that still
   points at v1.0.0.

## 2. SciCrunch — **done**

**RRID:SCR_028851**, assigned 2026-08-20. Cite it inline in a Methods section; the DOI goes
in the reference list.

**Assignment and resolution are two different events.** SciCrunch hands out the ID at the end
of the submit flow, but the record only becomes resolvable after a curator approves it. On the
day of submission `scicrunch.org/resolver/SCR_028851` answered *"RRID:SCR_028851 was not found
in our database"*, which is the expected state, not an error. Check it again before using the
RRID in a manuscript:

```
open https://scicrunch.org/resolver/SCR_028851
```

If it still does not resolve after a few weeks, `info@rrid.site` is the contact SciCrunch's own
page gives.

The submit flow assigns the ID at the end of *Basic Information*. Step 2, *Additional
Information*, is optional enrichment and most of its fields are for **data repositories** and
for **RIN Community Authorities** — registries that issue their own identifiers. This is
neither. What was filled in, and what was deliberately left blank:

| Field | Value |
|---|---|
| Terms Of Use URLs | `https://github.com/hopejsh/CognitionBioChem/blob/main/NOTICE` |
| Supercategory | `resource` |
| License | Apache-2.0 for the code, plus the mixed-licence paragraph below |
| Data Access Information URL | `https://doi.org/10.5281/zenodo.22032684` |
| Located In | *blank* — software has no physical location |
| Processing, Repository Guidelines (+URL), Data Submission URL, Data size limits, Data storage fee/costs | *blank* — for repositories that accept deposits; this accepts none |
| RIN Description, RRID Identifier Pattern, ES Index | *blank* — for Community Authorities that mint their own RRIDs |
| FAIRSharing URL | *blank* — not registered there |
| Specification URL | *blank* — no PDF specification exists |
| Resource Status | *blank* — the field is for a resource no longer in service |

The rule is the same one applied to bio.tools' EDAM terms: **a blank field is better than a
plausible wrong one**, because a curator and every downstream query treat what is there as
true. Nothing was invented to make the entry look complete.

### The original submission content



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
  record, and fields that were never computed render as labels rather than figures. Nine
  studies were pre-registered under content hashes before any data was seen, under 27
  registered analysis plans counting every superseded version, and their artefacts, analysis
  plans and prediction runs are held under content-addressed custody.

  The headline result is negative: across a screen of 13 candidate-receptor constructs covering
  12 distinct peptides (one 41-mer is screened against two different receptors, so it is
  counted twice in every mean and count) and a 143-fold full-MSA rerun,
  designed peptides did not separate from composition-matched shuffles of their own amino
  acids (mean native ipTM 0.629 against a mean decoy of 0.628), and that hypothesis was
  falsified in all eleven retained versions of the two screening studies. A registered positive
  control then folded sixteen deposited X-ray peptide-receptor complexes against ten uniform
  random permutations of each peptide: the natives separate from their own permutations in
  aggregate (+0.0895 ipTM, Holm p = 0.0148), but only 4 of 16 beat all ten permutations of
  themselves against a threshold of 5 registered in advance, so the composition-matched null
  licenses no verdict on any single case and the per-candidate reading of it is withdrawn. That
  control is the only study in the slate whose protocol audit records no deviation from its
  registered plan.

Keywords:
  structural biology, protein structure prediction, computational chemistry, drug discovery,
  reproducible research, research integrity, pre-registration, negative results, provenance,
  peptide design

License:
  Apache-2.0 (this project's own code)

  NOTE — the resource is not single-licensed, and a submission that says only "Apache-2.0"
  understates a reuser's obligations. The repository redistributes third-party scientific
  data, each source keeping its own terms:

    Apache-2.0    this project's code, and the vendored .agents/skills/ software
    CC BY 4.0     UniProt records, AlphaFold DB models, .agents/skills/ documentation
    CC BY-SA 3.0  ChEMBL-derived data files -- SHARE-ALIKE, and therefore the one that
                  actually constrains reuse: it covers data/corpus_ACHE.json, three study
                  artefacts, and the 17 runs/*/input.yaml whose job is a CHEMBL accession
    CC0 1.0       RCSB PDB crystal depositions used as experimental ground truth
    MIT           Boltz-2 model outputs (the predicted structures under runs/)

  If the form takes only one value, enter Apache-2.0 and put the paragraph above in the
  comments or description field. The full per-file breakdown is in NOTICE at the repository
  root.

Availability:
  Free, open source

Related identifiers:
  DOI: (add the Zenodo concept DOI once minted)
  ORCID: https://orcid.org/0000-0001-7914-5306
```

## 3. After a DOI or RRID is issued

Run through this list each time an identifier arrives; nothing here is automatic.

- [x] `CITATION.cff` — `doi:` and both `identifiers:` DOI entries (RRID still pending)
- [ ] `.zenodo.json` — governs the *next* deposit only. Its description is kept current with
      `data/slate.json`, but a published record does not change when this file does; see the
      note in §1 for what correcting an already-minted record costs
- [x] `README.md` — DOI badge and citation block
- [x] `codemeta.json` — `identifier` set to the concept DOI
- [x] `biotools.json` — both DOIs under `otherID`
- [x] `VERSION` — reads `1.1.0`, the version being prepared. It is not a claim that 1.1.0
      exists as a deposit; `platform/check_version_stamps.py` requires every metadata
      surface that describes *this tree* to agree with it, and every surface pinned to a
      *published* deposit to keep naming the release it actually belongs to

One caution that applies to both registries: this repository's finding is negative. The
citation should be for what the software does, not as evidence that any candidate binds
anything.

---

## 4. bio.tools — **done**

**biotools:cognitionbiochem** — <https://bio.tools/cognitionbiochem>, registered 2026-08-20.
The stored record carries all four topics, three function graphs, both DOIs, the RRID, the
ORCID and the licensing note; verified through `bio.tools/api/tool/cognitionbiochem/`.

### How it was submitted

In scope: bio.tools registers bioinformatics and computational-biology software, which is what
this is. `biotools.json` in the repository root is written against biotoolsSchema and can be
pasted or imported.

1. <https://bio.tools> → sign in (ELIXIR AAI accepts ORCID and institutional logins).
2. *Add tool* → the form mirrors `biotools.json` field for field.
3. The form has a **JSON tab** — paste `biotools.json` there rather than filling nine tabs
   by hand. It arrives complete: every EDAM ontology URI in it was resolved against the live
   ontology through EBI OLS rather than written from memory, because a wrong ontology URI is
   worse than a missing one (curators and every downstream query treat it as true).

   ```
   https://www.ebi.ac.uk/ols4/api/search?q=<term>&ontology=edam&exact=true
   ```

   The editor starts with `{"owner": "seung"}`. `biotools.json` carries that field too, so
   there is nothing to merge: click in the editor, select all, paste over it, then press
   **Validate** before **Save**.

   ```
   pbcopy < biotools.json
   ```

   An earlier version of this file left `owner` out, on the grounds that a bio.tools account
   name is not something the project asserts about itself. That was a distinction that cost
   more than it bought — it made the repository's own file unusable as-is and pushed the
   working copy into a scratch directory. `owner` is a biotoolsSchema field and is public the
   moment the entry is registered.
4. Curation is manual and takes days to weeks. The result is a stable entry at
   `https://bio.tools/cognitionbiochem`.
5. Add that URL to `CITATION.cff` under `identifiers:` and to the README.

Note that `biotoolsID` must be unique across the registry. `cognitionbiochem` is the proposed
one; if it is taken the form will say so and a suffix is fine.

## 5. Research Software Directory — **not pursued**

Decided against on 2026-08-20, and recorded here so the question is not reopened.

The main instance, <https://research-software-directory.org>, is operated by the Netherlands
eScience Center and its catalogue is scoped to software connected to that organisation and its
partners. This project has no such connection, so the eligibility question would have been
answered by someone else's policy rather than by anything about the software. Preparing
metadata against a catalogue that may not accept it is effort spent on a coin flip.

**The three registries already in place cover what registries are for**, and each answers a
different question:

| Identifier | Answers |
|---|---|
| `10.5281/zenodo.22032684` | how to cite the archived release |
| `RRID:SCR_028851` | how to name the tool in a Methods section |
| `biotools:cognitionbiochem` | how someone looking for a structure-prediction tool finds it |

If an RSD listing is ever wanted, `CITATION.cff` and `codemeta.json` are already in the
repository root, which is where the RSD looks — so the preparation is done either way. Other
instances exist for other communities, for example the Helmholtz HIFIS one.

### The original notes, kept for whoever revisits this

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
   > with a provenance record on every displayed value and nine studies pre-registered under
   > content hashes. Its headline result is negative, and a registered positive control on
   > sixteen X-ray peptide-receptor complexes establishes that the screen's null licenses no
   > verdict on any single case.

If the eligibility check fails, **bio.tools plus Zenodo plus an RRID already covers discovery,
citation and Methods-section identification**, which is what the registries are for.

