# Study inputs

Curated input sets for the pre-registered studies. These were previously written to `/tmp`,
which meant the studies could not be re-run from a clean checkout — the curation step depends
on live database queries whose results change over time, so regenerating them would not
reproduce the registered analysis.

| File | Used by | Contents |
|---|---|---|
| `posebench_set.json` | `pose_accuracy.py` (#6) | 16 PDB protein–ligand complexes, temporally stratified |
| `ache_bench.json` | `ache_affinity_benchmark.py` | 17 AChE compounds with structures and reference potencies |
| `ache_mature.txt` | `inference_variance.py`, `ache_affinity_benchmark.py` | human AChE P22303 mature chain, residues 32–614 |

Derived from RCSB PDB (CC0), ChEMBL (CC BY-SA 3.0) and UniProt (CC BY 4.0). See `/NOTICE`.
