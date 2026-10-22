"""Renders design/moonharbor/town_plan.png from canon coordinates (MC block X, Z; Y = height).
Sources: design/world_map.md section 3 and Art/World/landmarks.json. Run: python render_town_plan.py
Needs matplotlib. Colours here are diagram colours, not world art."""
import json, math, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
LM = json.load(open(os.path.join(ROOT, "Art/World/landmarks.json")))["landmarks"]
by_id = {l["id"]: l for l in LM}

# Tiers by ground height (MC Y). Sea level is Y 63.
TIERS = [("Waterline", 63, 70, "#9fd3d8"), ("Square", 70, 80, "#e8d9a8"),
         ("Terraces", 80, 100, "#d9b48a"), ("Crown", 100, 160, "#b98a7a")]
def tier_of(y):
    for name, lo, hi, col in TIERS:
        if lo <= y < hi:
            return name, col
    return TIERS[0][0], TIERS[0][3]

DISTRICTS = ["1i-point", "1i-market", "1i-heights", "1i-lamplight", "1i-rise", "1i-yards", "1i-weavers", "1i-wayside"]
# Canon boxes from world_map.md (x0, x1, z0, z1)
BOXES = {
    "Market Square": (140, 246, -2353, -2256),
    "Harbour": (112, 300, -2440, -2353),
    "Main Street": (289, 301, -2405, -2333),
    "Festival Green": (274, 318, -2332, -2306),
    "Moonmarket": (282, 324, -2300, -2248),
    "Grand Library": (330, 394, -2372, -2322),
    "Miners' Guild": (390, 420, -2412, -2382),
    "Carriage Station": (498, 546, -2244, -2196),
    "Boatyard": (148, 182, -2158, -2127),
    "Keep Elariel": (470, 576, -2565, -2527),
}
POINTS = {  # name: (x, z, y)
    "Lantern Pier end": (136, -2418, 66.6), "Seawall Stair (XLI)": (204, -2357, 64),
    "Moonwell": (200.5, -2299.5, 65.9), "Ilwen's Lighthouse": (127, -2343, 70),
    "Chapel of Lamps": (132, -2322, 68.8), "Syrena's islet": (247, -2462, 64),
    "Keep gate": (501, -2526, 138), "Keep Road foot": (326, -2378, 72),
}
GOLDEN = [(136, -2418), (136, -2373), (175, -2362), (204, -2357), (200.5, -2299.5),
          (296, -2319), (326, -2378), (380, -2430), (440, -2470), (501, -2526)]
TO_STATION = [(296, -2319), (303, -2274), (420, -2250), (522, -2220)]
SIGHT_FROM = (136, -2418)
SIGHT_TO = ["Keep gate", "Ilwen's Lighthouse", "Syrena's islet"]

def plen(p):
    return sum(math.dist(p[i], p[i + 1]) for i in range(len(p) - 1))

fig, ax = plt.subplots(figsize=(16, 11), dpi=130)
ax.set_facecolor("#ece6d6")
from matplotlib.patches import Polygon
# Rough sea outline for orientation only (the bay lies north and west of the quay); not surveyed.
ax.add_patch(Polygon([(90, -2600), (460, -2600), (460, -2500), (330, -2440), (112, -2440), (112, -2300),
                      (90, -2300)], fc="#bfe0e4", ec="none", zorder=0))
# districts
for did in DISTRICTS:
    l = by_id[did]; (x, y, z) = l["mc"]; (w, d) = l["footprint_m"]
    name, col = tier_of(y)
    ax.add_patch(Rectangle((x - w / 2, z - d / 2), w, d, fc=col, ec="#7a5a48", lw=1, alpha=0.75))
    ax.text(x, z, l["name"].replace("Moonharbor ", "") + f"\nY {y:.0f}", ha="center", va="center", fontsize=8, color="#3a2a20")
for n, (x0, x1, z0, z1) in BOXES.items():
    cy = {"Keep Elariel": 138, "Miners' Guild": 111, "Grand Library": 88, "Carriage Station": 87,
          "Moonmarket": 75, "Main Street": 69, "Festival Green": 70}.get(n, 65)
    ax.add_patch(Rectangle((x0, z0), x1 - x0, z1 - z0, fc=tier_of(cy)[1], ec="#3a2a20", lw=1.6))
    ax.text((x0 + x1) / 2, z0 - 4, n, ha="center", va="bottom", fontsize=8.5, weight="bold", color="#2a1a12")
for n, (x, z, y) in POINTS.items():
    ax.add_patch(Circle((x, z), 4, fc="#e3ae45", ec="#2a1a12", lw=1, zorder=5))
    ax.text(x + 6, z, n, fontsize=8, va="center", zorder=6)
for n in SIGHT_TO:
    x, z, _ = POINTS[n]
    ax.plot([SIGHT_FROM[0], x], [SIGHT_FROM[1], z], ls=":", color="#4a6a8a", lw=1.2, zorder=3)
gx, gz = zip(*GOLDEN); ax.plot(gx, gz, color="#c8443a", lw=3, zorder=4, label=f"Golden path, pier to keep gate ({plen(GOLDEN):.0f} m; Keep Road route between its canon ends is ours)")
sx, sz = zip(*TO_STATION); ax.plot(sx, sz, color="#8b5a3a", lw=2, ls="--", zorder=4, label=f"Festival Green to Carriage Station ({plen(TO_STATION):.0f} m)")
ax.plot([], [], ls=":", color="#4a6a8a", label="Sightlines from the arrival berth")
for name, lo, hi, col in TIERS:
    ax.add_patch(Rectangle((0, 0), 0, 0, fc=col, label=f"{name} tier (ground Y {lo} to {hi})"))
ax.set_xlim(90, 640); ax.set_ylim(-2120, -2590)  # north (more negative Z) at the top
ax.set_aspect("equal")
ax.set_xlabel("MC X (east →)"); ax.set_ylabel("MC Z (north ↑)")
ax.set_title("Moonharbor town plan: tiers, golden path and sightlines (canon positions; district boxes are rough bounds)")
ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=8, framealpha=0.9)
ax.text(100, -2575, "Starfall Bay (north and west)", fontsize=10, style="italic", color="#2e6a7a")
fig.tight_layout()
out = os.path.join(HERE, "town_plan.png")
fig.savefig(out, bbox_inches="tight")
print(out, "golden", round(plen(GOLDEN)), "station", round(plen(TO_STATION)))
