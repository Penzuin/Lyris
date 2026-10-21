"""Generates the world foliage meshes and textures (T51). Deterministic; about a minute.

    python Art/World/foliage/make_species.py

Needs Python 3.9+ with numpy and Pillow (the same as the terrain bake).

Output (not in git; rebuilt by this script):
  meshes/SM_<Species>_<Variant>_LOD<k>.glb   one file per LOD (LOD0..3; grass meshes LOD0..1)
  textures/*.png                             the island's painted tiles plus the world atlases
  species.json                               every variant: LOD files, triangle counts, size,
                                             group, cull distances, Nanite, collision; texture luma
Content/Python/lyris_world_foliage.py imports these into /Game/Lyris/World/Foliage.
"""

import argparse
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import species as sp  # noqa: E402
import palette  # noqa: E402
import textures as tx  # noqa: E402
from make_island import write_glb  # noqa: E402  (same glTF layout the island used)

SPECIES_VERSION = 1
UPWARD = ("cards_", "plant", "moss", "flower", "grass", "wheat")  # thin two-sided parts keep their winding


def tri_count(mesh):
    return sum(len(p.idx) for p in mesh.parts.values()) // 3


def bounds(mesh):
    pos = np.concatenate([np.array(p.pos) for p in mesh.parts.values() if p.pos])
    lo, hi = pos.min(0), pos.max(0)
    radius = float(np.sqrt((pos[:, 0] ** 2 + pos[:, 1] ** 2).max()))
    return lo.tolist(), hi.tolist(), radius


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated species to build (default: all)")
    args = ap.parse_args(argv)
    t0 = time.time()
    mesh_dir, tex_dir = os.path.join(HERE, "meshes"), os.path.join(HERE, "textures")
    os.makedirs(mesh_dir, exist_ok=True)
    print("[Lyris] painting foliage textures ...", flush=True)
    tex = tx.write_all(tex_dir)
    luma = {name: round(tx.texture_luma(arr), 4) for name, arr in tex.items()}

    catalogue = {}
    wanted = args.only.split(",") if args.only else list(sp.SPECIES)
    for name in wanted:
        spec = sp.SPECIES[name]
        n_lods = spec.get("lods", 4)
        variants = []
        for k in range(len(spec["variants"])):
            vname = sp.variant_name(name, k)
            lods, tris, parts = [], [], set()
            info = None
            for lod in range(n_lods):
                mesh = sp.build(name, k, lod)
                fname = f"{vname}_LOD{lod}.glb"
                ups = tuple(p for p in mesh.parts if p.startswith(UPWARD))
                write_glb(os.path.join(mesh_dir, fname), mesh, f"{vname}_LOD{lod}", upward_parts=ups)
                lods.append(fname)
                tris.append(tri_count(mesh))
                parts |= set(mesh.parts)
                if lod == 0:
                    info = bounds(mesh)
            lo, hi, radius = info
            variants.append({"name": vname, "lods": lods, "triangles": tris, "materials": sorted(parts),
                             "bounds_min_cm": [round(v, 1) for v in lo], "bounds_max_cm": [round(v, 1) for v in hi],
                             "radius_cm": round(radius, 1)})
            print(f"[Lyris] {vname:18s} tris per LOD {tris}  height {hi[2] / 100:5.1f} m  "
                  f"radius {radius / 100:4.1f} m", flush=True)
        catalogue[name] = {"group": spec["group"], "cull_m": list(spec.get("cull", (0, 0))),
                           "nanite": bool(spec.get("nanite", False)), "collision": spec.get("collision"),
                           "variants": variants}
    out = {"species_version": SPECIES_VERSION, "coordinates": "UE cm, Z up, pivot on the ground",
           "lod_screen_sizes": [1.0, 0.25, 0.08, 0.025], "texture_luma": luma, "palette": palette.as_dict(),
           "species": catalogue}
    path = os.path.join(HERE, "species.json")
    if args.only and os.path.exists(path):
        with open(path) as f:
            old = json.load(f)
        old["species"].update(catalogue)
        old["texture_luma"] = luma
        out = old
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    size = sum(os.path.getsize(os.path.join(mesh_dir, f)) for f in os.listdir(mesh_dir))
    print(f"[Lyris] {sum(len(s['variants']) for s in out['species'].values())} variants, meshes {size / 1e6:.1f} MB, "
          f"done in {time.time() - t0:.0f}s -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
