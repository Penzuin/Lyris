"""Scatters the T51 world foliage over the Moonharbor map (T55). Deterministic (seeded).

    python Art/World/foliage/scatter_moonharbor.py     # after bake_moonharbor.py and make_species.py (~1 min)

Same species, rules and file format as scatter.py (which it imports and reuses), on Moonharbor's own
terrain: the 1 m landscape and the 2 m Lampwick landscape, through the frame bake_moonharbor.py writes
(Art/World/moonharbor/frame_height.npy, the biome maps and frame_extra.png). On top of the world's rules:
  * Wayside Fields' field terraces, the Keep Road, the Old Coast Road, the ford and the beaches stay clear;
  * the hedgerow banks between fields are planted: a dense line of bushes with an oak or birch now and then.
Cells are 512 m (a Basic level loads everything at once, so bigger cells mean fewer actors and components).

Writes Art/World/moonharbor/scatter/cells/*.bin, summary.json, grass_tint.png, density.jpg (not in git).
Content/Python/lyris_build_moonharbor.py plants them with lyris_world_foliage.
"""

import json
import os
import sys
import time

import numpy as np
from PIL import Image
from scipy import ndimage as nd

HERE = os.path.dirname(os.path.abspath(__file__))
WORLD = os.path.dirname(HERE)
MH = os.path.join(WORLD, "moonharbor")
sys.path.insert(0, HERE)
import scatter as S  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
CELL_M = 512.0
HEDGE_BUSH_EVERY_M = 2.2
HEDGE_TREE_EVERY_M = 26.0


class MoonharborTerrain:
    """Duck-types scatter.Terrain on Moonharbor's frame."""

    def __init__(self):
        with open(os.path.join(MH, "moonharbor_manifest.json")) as f:
            self.man = json.load(f)
        fr = self.man["frame_mc"]
        S.FRAME = [fr["x0"], fr["z0"], fr["size"]]
        self.H = np.load(os.path.join(MH, "frame_height.npy")).astype(np.float32)
        n = self.H.shape[0]
        S.FIELD_N = n
        self.px_m = fr["size"] / n
        a = np.asarray(Image.open(os.path.join(MH, "biome", "T_LyrisBiomeA.png")), np.float32) / 255.0
        b = np.asarray(Image.open(os.path.join(MH, "biome", "T_LyrisBiomeB.png")), np.float32) / 255.0
        self.W = {name: a[..., k] for k, name in enumerate(("Grass", "Forest", "Sand", "Rock"))}
        self.W.update({name: b[..., k] for k, name in enumerate(("Snow", "Badlands", "Salt", "Volcanic"))})
        ex = np.asarray(Image.open(os.path.join(MH, "frame_extra.png")), np.float32) / 255.0
        self.extra = {k: ex[..., i] for i, k in enumerate(("field", "hedge", "path", "beach"))}
        enc = self.man["height_encoding"]
        span = enc["max_m"] - enc["min_m"]
        self.lands = []
        for L in self.man["landscapes"]:
            path = os.path.join(MH, L["file"])
            if os.path.exists(path):
                raw = np.asarray(Image.open(path)).astype(np.float32)
                h = enc["min_m"] + raw / 65535.0 * span
            else:
                h = None   # preview bake: no heightmap files, fall back to the frame
            self.lands.append((L, h))
        self.man["bake_version"] = self.man.get("bake_version")

    def exact_height(self, x, z):
        out = S.sample(self.H, x, z)
        done = np.zeros(np.shape(x), bool)
        for L, h in self.lands:
            if h is None:
                continue
            step = L["metres_per_vertex"]
            gx = (x - L["corner_mc"][0]) / step
            gz = (z - L["corner_mc"][1]) / step
            nx, nz = L["resolution"]
            inside = (gx >= 0) & (gz >= 0) & (gx <= nx - 1) & (gz <= nz - 1) & ~done
            if inside.any():
                out[inside] = nd.map_coordinates(h, [gz[inside], gx[inside]], order=1)
                done |= inside
        return out


class MoonharborScatter(S.Scatter):
    def fields(self, x, z):
        f = super().fields(x, z)
        T = self.T
        for k in ("field", "hedge", "path", "beach"):
            f[k] = S.sample(T.extra[k], x, z)
        open_ground = np.clip(np.maximum.reduce([f["field"], f["path"] * 1.5, f["beach"]]), 0, 1)
        f["clear"] = f["clear"] * (1 - open_ground)
        f["clear_tree"] = f["clear_tree"] * (1 - np.clip(open_ground + f["hedge"], 0, 1))
        return f

    def hedges(self, box):
        """Bushes all along the hedgerow banks, with an oak or birch now and then."""
        rng = self.rng
        x, z = S.candidates(rng, *box, HEDGE_BUSH_EVERY_M)
        hedge = S.sample(self.T.extra["hedge"], x, z)
        keep = (hedge > 0.45) & (rng.random(len(x)) < 0.75)
        x, z = x[keep], z[keep]
        if not len(x):
            return
        self.place("bush", x, z, rng.uniform(0.8, 1.15, len(x)), rng.normal(0, 2.0, (len(x), 2)), align=0.35, sink=0.05)
        tx, tz = S.candidates(rng, *box, HEDGE_TREE_EVERY_M * 0.5)
        hedge = S.sample(self.T.extra["hedge"], tx, tz)
        keep = (hedge > 0.5) & (rng.random(len(tx)) < 0.22)
        tx, tz = tx[keep], tz[keep]
        if len(tx):
            k2 = S.thin_pairs(tx, tz, rng.random(len(tx)), HEDGE_TREE_EVERY_M * 0.6)
            tx, tz = tx[k2], tz[k2]
            sp = np.where(rng.random(len(tx)) < 0.7, "oak", "birch")
            for s in ("oak", "birch"):
                m = sp == s
                self.place(s, tx[m], tz[m], rng.uniform(1.0, 1.35, m.sum()), rng.normal(0, 1.5, (m.sum(), 2)), sink=0.12)


def density_image(T, out, path, catalogue):
    n = 1536
    fx, fz, size = S.FRAME
    H = np.asarray(Image.fromarray(T.H).resize((n, n), Image.BILINEAR))
    img = np.zeros((n, n, 3))
    img[:] = np.array([0.18, 0.54, 0.61])
    shade = np.clip(0.75 + np.gradient(H, axis=1) * 0.08 - np.gradient(H, axis=0) * 0.08, 0.5, 1.1)
    land = H > 0
    img[land] = (np.array([0.94, 0.89, 0.77]) * shade[..., None])[land]
    trees = np.zeros((n, n))
    under = np.zeros((n, n))
    group_of = {v["name"]: spec["group"] for spec in catalogue.values() for v in spec["variants"]}
    for name, chunks in out.items.items():
        arr = np.concatenate(chunks)
        i = np.clip(((arr[:, 1] / 100 - fz) / size * n).astype(int), 0, n - 1)
        j = np.clip(((arr[:, 0] / 100 - fx) / size * n).astype(int), 0, n - 1)
        np.add.at(trees if group_of.get(name) == "trees" else under, (i, j), 1)
    px_ha = (size / n) ** 2 / 10000.0
    t = np.clip(nd.gaussian_filter(trees, 1.0) / px_ha / 90.0, 0, 1) ** 0.7
    u = np.clip(nd.gaussian_filter(under, 1.0) / px_ha / 300.0, 0, 1)
    img = img * (1 - u[..., None] * 0.5) + np.array([0.62, 0.72, 0.45]) * shade[..., None] * u[..., None] * 0.5
    img = img * (1 - t[..., None] * 0.92) + np.array([0.21, 0.35, 0.31]) * shade[..., None] * t[..., None] * 0.92
    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(path, quality=88)


def main():
    t0 = time.time()

    def log(msg):
        print(f"[Lyris] {msg}  ({time.time() - t0:.0f}s)", flush=True)

    with open(os.path.join(HERE, "species.json")) as f:
        catalogue = json.load(f)["species"]
    T = MoonharborTerrain()
    S.CELL_M = CELL_M
    log(f"Moonharbor terrain: frame {S.FRAME}, {T.H.shape[0]} px ({T.px_m:.2f} m)"
        + ("  (PREVIEW bake: rerun after the full bake)" if T.man.get("preview") else ""))
    M = S.world_masks(T, log)
    clear = S.Clearings(os.path.join(WORLD, "landmarks.json"))
    sc = MoonharborScatter(T, M, clear, catalogue, S.SEED, log)
    out_dir = os.path.join(MH, "scatter")
    os.makedirs(out_dir, exist_ok=True)
    block = 512.0
    for L in T.man["landscapes"]:
        x0, z0 = L["corner_mc"]
        x1 = x0 + (L["resolution"][0] - 1) * L["metres_per_vertex"]
        z1 = z0 + (L["resolution"][1] - 1) * L["metres_per_vertex"]
        for bz in np.arange(z0, z1, block):
            for bx in np.arange(x0, x1, block):
                box = (bx, bz, min(bx + block, x1), min(bz + block, z1))
                n = T.H.shape[0]
                i0, j0 = S.to_px(box[0], box[1], n)
                i1, j1 = S.to_px(box[2], box[3], n)
                sub = T.H[max(0, int(j0)):max(0, int(j1) + 1), max(0, int(i0)):max(0, int(i1) + 1)]
                if not (sub > 0).any():
                    continue
                sc.trees(box)
                sc.boulders(box)
                sc.understory(box)
                sc.hedges(box)
        log(f"{L['name']} scattered")
    per_cell, counts = S.write_cells(sc.out, out_dir, log)
    group_of, species_of = {}, {}
    for s, spec in catalogue.items():
        for v in spec["variants"]:
            group_of[v["name"]], species_of[v["name"]] = spec["group"], s
    by_species, by_group = {}, {}
    for name, c in counts.items():
        by_species[species_of[name]] = by_species.get(species_of[name], 0) + c
        by_group[group_of[name]] = by_group.get(group_of[name], 0) + c
    cell_comps = [len(e) for e in per_cell.values()]
    land_km2 = float((T.H > 0).mean() * S.FRAME[2] ** 2 / 1e6)
    summary = {
        "scatter_version": S.SCATTER_VERSION, "seed": S.SEED, "bake_version": T.man.get("bake_version"),
        "moonharbor_version": T.man.get("moonharbor_version"), "map": "Moonharbor",
        "preview_bake": bool(T.man.get("preview")), "cell_m": CELL_M, "land_km2_frame": round(land_km2, 1),
        "total": int(sum(counts.values())), "by_group": by_group, "by_species": dict(sorted(by_species.items())),
        "by_variant": dict(sorted(counts.items())), "cells": len(per_cell),
        "per_cell": {"max_components": int(max(cell_comps or [0])), "mean_components": round(float(np.mean(cell_comps or [0])), 1),
                     "max_instances": int(max([sum(len(a) for a in e.values()) for e in per_cell.values()] or [0]))},
    }
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    S.grass_tint(T, M, os.path.join(out_dir, "grass_tint.png"))
    density_image(T, sc.out, os.path.join(out_dir, "density.jpg"), catalogue)
    log(f"done: {summary['total']} instances {by_group} in {len(per_cell)} cells of {CELL_M:.0f} m "
        f"(components per cell: max {summary['per_cell']['max_components']}, mean {summary['per_cell']['mean_components']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
