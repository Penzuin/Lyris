"""Divide the Lyris map into Genshin-style chunks: regions -> areas -> subareas, each with a release wave."""
import json, sys, numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from scipy import ndimage

ATLAS = sys.argv[1]; OUT = sys.argv[2]
N = 1000; M = 25.0  # px, metres per px
hm = np.array(Image.open(f"{ATLAS}/hmap.png").convert("L")).astype(float)
Y = hm * 1.5 - 64
land = Y > 63.5
reg = np.array(Image.open(f"{ATLAS}/regions.png"))
xs = (np.arange(N) + 0.5) * M - 12500
X, Z = np.meshgrid(xs, xs)

# Release waves (Genshin-style versions). 1.0 is Moonharbor only.
WAVES = {
    "1.0": "Moonharbor",
    "1.1": "The North Road",
    "1.2": "The River Country",
    "1.3": "The West Mountains",
    "1.4": "The White North",
    "1.5": "The East Cape",
    "2.0": "Saltreach and Greengrace",
    "3.0": "Sunreach",
    "4.0": "The Outer Isles",
}

# (id, name, region, wave, seed X, seed Z, server regions it may take land from)
# Names marked * in the doc are new working names.
SUB = [
    # ---- 1.0 Moonharbor ----
    ("M1", "Moonharbor (the town)",        "Quiet Reach", "1.0",   360, -2340, [0, 4, 6]),
    ("M2", "Keep Hill",                    "Quiet Reach", "1.0",   780, -2620, [0, 4]),
    ("M3", "Wayside Fields",               "Quiet Reach", "1.0",   420, -1750, [0]),
    ("M4", "Mistwater Shore",              "Quiet Reach", "1.0",  -520, -2350, [0, 6]),
    # ---- 1.1 North Road ----
    ("N1", "Observatory Rise",             "Quiet Reach", "1.1",  1350, -3000, [4, 0]),
    ("N2", "The Delvers' Uplands",         "Quiet Reach", "1.1",  1600, -3850, [4, 5]),
    # ---- 1.2 River country (heart of the Reach) ----
    ("R1", "Hollowmere and the Herring Road", "Quiet Reach", "1.2", -500, -1050, [0]),
    ("R2", "The Strait Shore",             "Quiet Reach", "1.2",   650,  -150, [0]),
    ("R3", "The Heartland",                "Quiet Reach", "1.2",  2300, -1700, [1]),
    ("R4", "Glowmere",                     "Quiet Reach", "1.2",  3000, -2700, [1, 3]),
    ("R5", "The Steaming Fields",          "Quiet Reach", "1.2",  3700,  -650, [1]),
    # ---- 1.3 West mountains (region 6) ----
    ("W1", "The Great Lake",               "Quiet Reach", "1.3", -1650, -1900, [6]),
    ("W2", "The Ladder Lakes",             "Quiet Reach", "1.3", -3300, -3300, [6]),
    ("W3", "The Mistwall Coast",           "Quiet Reach", "1.3", -4500, -2200, [6]),
    ("W4", "The Grey Peaks",               "Quiet Reach", "1.3", -2900,  -500, [6]),
    # ---- 1.4 White north (region 5, 3) ----
    ("F1", "The Sisterfjord",              "Quiet Reach", "1.4", -1700, -5700, [5]),
    ("F2", "The Glacier Ridge",            "Quiet Reach", "1.4",  1500, -5000, [5, 4]),
    ("F3", "Skyshoals",                    "Quiet Reach", "1.4",  4300, -4100, [3]),
    # ---- 1.5 East cape (region 1 east, 2) ----
    ("E1", "Elderheart",                   "Quiet Reach", "1.5",  5300, -2600, [1, 3]),
    ("E2", "The High Table",               "Quiet Reach", "1.5",  6500, -1100, [2]),
    ("E3", "The Long Door Cape",           "Quiet Reach", "1.5",  7600,   300, [2]),
    # ---- 2.0 Saltreach and Greengrace ----
    ("S1", "The Crater Lake",              "Greengrace",  "2.0", -1100,  3200, [7]),
    ("S2", "Greengrace Meadows",           "Greengrace",  "2.0", -2500,  2500, [7, 8]),
    ("S3", "The Southern Greenwood",       "Greengrace",  "2.0", -2600,  4400, [7, 8]),
    ("S4", "The Glass Dunes",              "Saltreach",   "2.0", -4200,  1800, [8]),
    ("S5", "The Skyfall Spine",            "Saltreach",   "2.0", -5500,  3700, [8]),
    ("S6", "The Badlands",                 "Saltreach",   "2.0", -4300,  5000, [8]),
    ("S7", "The Hexstone Cape",            "Saltreach",   "2.0", -7300,  1900, [9]),
    # ---- 3.0 Sunreach ----
    ("U1", "The Sunreach Plains",          "Sunreach",    "3.0",  2600,  2400, [10]),
    ("U2", "The Thunder Curtain",          "Sunreach",    "3.0",  1300,  4200, [11, 10]),
    ("U3", "The Sunstair Volcano",         "Sunreach",    "3.0",  4000,  4600, [12]),
    ("U4", "The Jungle Coast",             "Sunreach",    "3.0",  4800,  2600, [12]),
    # ---- 4.0 Outer isles (existing islands on the map) ----
    ("O1", "Westwatch",                    "Outer Isles", "4.0", -9360, -2546, [13]),
    ("O2", "The Birchholms",               "Outer Isles", "4.0", -6400, -1300, [14]),
    ("O3", "Snowcap",                      "Outer Isles", "4.0", -4500, -5500, [15]),
    ("O4", "The Flowerholms",              "Outer Isles", "4.0", 10000, -4400, [16]),
    ("O6", "Blossom Isle",                 "Outer Isles", "4.0",  9429,  3610, [17]),
    ("O7", "The Bamboo Isles",             "Outer Isles", "4.0",  8500,  5700, [18]),
    ("O8", "Glowcap Hollow",               "Outer Isles", "4.0",-10717,  5862, [19]),
]
# The town is an exact box from the gazetteer, not a Voronoi cell.
TOWN = (100, 620, -2565, -2120)

# Sea zones (the boat needs water to sail in). Rectangles in block X, Z; water only.
SEA = [  # (id, name, wave, circles (X, Z, radius m)); water only
    ("H1", "Starfall Bay",      "1.0", [(-180, -2640, 640), (60, -2900, 420)]),
    ("H2", "The Lampwick Gulf", "1.0", [(150, -3450, 700), (-500, -3950, 900), (-1500, -4250, 1000), (-2500, -4450, 950)]),
]

# --- assign land ---
def assign(allowed):
    lab = np.full((N, N), -1, int); best = np.full((N, N), np.inf)
    for i, (cid, name, R, w, sx, sz, regs) in enumerate(SUB):
        if not allowed(i):
            continue
        ok = land & np.isin(reg, regs)
        d = np.hypot(X - sx, Z - sz) + np.where(reg == regs[0], 0, 700)
        d = np.where(ok, d, np.inf)
        m = d < best; lab[m] = i; best[m] = d[m]
    rest = land & (lab < 0)
    if rest.any():
        idx = ndimage.distance_transform_edt(lab < 0, return_distances=False, return_indices=True)
        lab[rest] = lab[idx[0][rest], idx[1][rest]]
    return lab
lab = assign(lambda i: SUB[i][0] != "M1")
# Moonharbor (1.0) stays small: its chunks keep only land within 2 km of the town square.
far = np.hypot(X - 300, Z + 2300) > 2000
other = assign(lambda i: SUB[i][3] != "1.0")
is10 = np.isin(lab, [i for i, t in enumerate(SUB) if t[3] == "1.0"])
lab[is10 & far] = other[is10 & far]
# the town is an exact box from the gazetteer
tm = land & (X >= TOWN[0]) & (X <= TOWN[1]) & (Z >= TOWN[2]) & (Z <= TOWN[3])
lab[tm] = 0

sea_lab = np.full((N, N), -1, int)
for j, (sid, name, w, circles) in enumerate(SEA):
    inside = np.zeros((N, N), bool)
    for cx, cz, rad in circles:
        inside |= np.hypot(X - cx, Z - cz) <= rad
    m = (~land) & inside & (sea_lab < 0)
    sea_lab[m] = j

# --- stats ---
px_km2 = (M * M) / 1e6
rows = []
for i, (cid, name, R, w, sx, sz, regs) in enumerate(SUB):
    m = lab == i
    if not m.any():
        print("EMPTY", cid); continue
    rows.append(dict(id=cid, name=name, region=R, wave=w, wave_name=WAVES[w],
                     land_km2=round(m.sum() * px_km2, 2),
                     centre=[int(X[m].mean()), int(Z[m].mean())],
                     bbox=[int(X[m].min()), int(X[m].max()), int(Z[m].min()), int(Z[m].max())]))
for j, (sid, name, w, r) in enumerate(SEA):
    m = sea_lab == j
    rows.append(dict(id=sid, name=name, region="Quiet Reach (sea)", wave=w, wave_name=WAVES[w],
                     water_km2=round(m.sum() * px_km2, 2), circles=r))
json.dump(dict(scale="1 px = 25 m; ids in chunks.png: land = index+1, sea = 100+index, 0 = none",
               waves=WAVES, town_box=TOWN, chunks=rows), open(f"{OUT}/chunks.json", "w"), indent=1)

# id mask for the game (same 1000 px grid as the atlas)
mask = np.zeros((N, N), np.uint8)
mask[lab >= 0] = (lab[lab >= 0] + 1).astype(np.uint8)
mask[sea_lab >= 0] = (100 + sea_lab[sea_lab >= 0]).astype(np.uint8)
Image.fromarray(mask).save(f"{OUT}/chunks.png")

tot = {}
for r in rows:
    tot.setdefault(r["wave"], [0, 0])
    tot[r["wave"]][0] += r.get("land_km2", 0); tot[r["wave"]][1] += r.get("water_km2", 0)
for w, (a, b) in sorted(tot.items()):
    print(w, WAVES[w], f"land {a:.1f} km2", f"water {b:.1f} km2" if b else "")
for r in rows:
    print(r["id"], r["name"], r.get("land_km2", r.get("water_km2")), r.get("centre", ""))
np.save(f"{OUT}/lab.npy", lab); np.save(f"{OUT}/sea.npy", sea_lab)
