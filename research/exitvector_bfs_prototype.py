"""Escape-path BFS prototype: can a linker atom leave the ligand site and reach bulk solvent?

Decisive test for MEDCHEM-IDEA-1: the AChE gorge is ~20 A deep and the bis-hupyridone
crystal structures (Wong 2003, PMID 12517147) prove a 10-12 methylene tether threads it
from the hupyridone amine. If this BFS returns NO PATH from huperzine A's N2, the method
is refuted and must not gate anything.
"""
import sys, math
import numpy as np
from scipy.spatial import cKDTree, Delaunay
from Bio.PDB import MMCIFParser

VDW = {"C": 1.70, "N": 1.55, "O": 1.52, "S": 1.80, "H": 1.20, "SE": 1.90}


def load(cif, chain_id="A", lig_resname="HUP"):
    st = MMCIFParser(QUIET=True).get_structure("x", cif)
    model = next(iter(st))
    prot, lig = [], []
    for ch in model:
        for res in ch:
            het = res.id[0]
            if res.get_resname() == lig_resname and ch.id == chain_id:
                for a in res:
                    if a.element != "H":
                        lig.append((a.get_name(), a.coord, a.element))
            elif het == " " and ch.id == chain_id:
                for a in res:
                    if a.element != "H":
                        prot.append((a.coord, a.element,
                                     f"{res.get_resname()}{res.id[1]}:{a.get_name()}"))
    return prot, lig


def escape_bfs(prot, lig, start_atom, probe, spacing=0.8, bulk_clear=7.0, verbose=True):
    pc = np.array([p[0] for p in prot], dtype=float)
    pr = np.array([VDW.get(p[1].upper(), 1.7) for p in prot], dtype=float)
    lc = np.array([l[1] for l in lig], dtype=float)

    start = None
    for name, coord, el in lig:
        if name == start_atom:
            start = np.array(coord, dtype=float)
    if start is None:
        raise SystemExit(f"atom {start_atom} not found; have {[l[0] for l in lig]}")

    # Grid box: generous, must contain the whole gorge and reach outside the protein
    centre = start
    half = 30.0
    lo = centre - half
    n = int(2 * half / spacing) + 1
    ax = [lo[i] + spacing * np.arange(n) for i in range(3)]
    G = np.stack(np.meshgrid(*ax, indexing="ij"), axis=-1).reshape(-1, 3)

    # Keep only points clear of protein vdW + probe.
    tree = cKDTree(pc)
    maxr = pr.max() + probe
    # distance to nearest protein atom surface
    d, idx = tree.query(G, k=1)
    # conservative prefilter then exact check against that atom's radius
    keep = d > (pr[idx] + probe)
    # points must also not clash with the LIGAND itself except near the start
    ltree = cKDTree(lc)
    dl, _ = ltree.query(G, k=1)
    keep &= (dl > probe + 1.2) | (np.linalg.norm(G - start, axis=1) < 3.0)

    free = G[keep]
    if verbose:
        print(f"  grid {len(G)} pts, free {len(free)} pts (probe {probe} A, spacing {spacing} A)")

    # bulk solvent = far from any protein atom AND outside the protein convex hull
    ftree = cKDTree(free)
    dfree, _ = tree.query(free, k=1)
    hull = Delaunay(pc[np.random.default_rng(0).choice(len(pc), size=min(len(pc), 4000), replace=False)])
    outside = hull.find_simplex(free) < 0
    bulk = (dfree > bulk_clear) & outside

    # seed: nearest free point to start
    ds, si = ftree.query(start.reshape(1, 3), k=1)
    if ds[0] > 3.0:
        return None, f"no free grid point within 3 A of {start_atom} (nearest {ds[0]:.2f} A) -> atom is sealed at probe {probe}"
    seed = int(si[0])

    # BFS over grid adjacency (26-connected within sqrt(3)*spacing)
    pairs = ftree.query_pairs(r=spacing * 1.7321 + 1e-6, output_type="ndarray")
    nbr = [[] for _ in range(len(free))]
    for a, b in pairs:
        nbr[a].append(b); nbr[b].append(a)

    from collections import deque
    INF = float("inf")
    dist = np.full(len(free), INF)
    prev = np.full(len(free), -1, dtype=int)
    dist[seed] = 0.0
    dq = deque([seed])
    # Dijkstra-lite via BFS on near-uniform grid: use heap for true path length
    import heapq
    h = [(0.0, seed)]
    target = -1
    while h:
        dcur, u = heapq.heappop(h)
        if dcur > dist[u]:
            continue
        if bulk[u]:
            target = u
            break
        pu = free[u]
        for v in nbr[u]:
            w = float(np.linalg.norm(free[v] - pu))
            nd = dcur + w
            if nd < dist[v]:
                dist[v] = nd; prev[v] = u
                heapq.heappush(h, (nd, v))
    if target < 0:
        return None, f"NO PATH to bulk solvent at probe {probe} A"

    path = []
    u = target
    while u != -1:
        path.append(free[u]); u = prev[u]
    path = path[::-1]
    return (dist[target], np.array(path)), "ok"


if __name__ == "__main__":
    cif = sys.argv[1] if len(sys.argv) > 1 else "/tmp/4ey5.cif"
    lig = sys.argv[2] if len(sys.argv) > 2 else "HUP"
    atom = sys.argv[3] if len(sys.argv) > 3 else "N2"
    prot, ligand = load(cif, "A", lig)
    print(f"{cif} chain A: {len(prot)} protein heavy atoms, ligand {lig} {len(ligand)} heavy atoms")
    print("ligand atoms:", [l[0] for l in ligand])
    for probe in (1.4, 1.9):
        print(f"\n--- probe {probe} A, start atom {atom} ---")
        res, msg = escape_bfs(prot, ligand, atom, probe)
        if res is None:
            print("  RESULT:", msg)
        else:
            L, path = res
            print(f"  RESULT: escape path length {L:.2f} A, {len(path)} nodes")
            print(f"  exit point {path[-1].round(2)}  straight-line start->exit "
                  f"{np.linalg.norm(path[-1]-path[0]):.2f} A")
