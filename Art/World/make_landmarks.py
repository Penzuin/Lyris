"""Writes Art/World/landmarks.json: blockouts of the canon landmarks and the new island chains.

    python Art/World/make_landmarks.py        # about 30 s; needs the same packages as bake_terrain.py

Every landmark is a list of basic shapes (cube, cylinder, cone, sphere) in the house palette,
placed at its real spot from design/world_map.md and the server builds (lyris-server/builds).
Content/Python/lyris_build_landmarks.py spawns them in the Lyris map, one outliner folder per
landmark, so real art can replace a landmark by deleting its folder and its entry here.

Ground: each part stores the baked ground under it ("g", MC Y, from bake_terrain.terrain, so it
matches the imported landscape) and how far its base must sink so it never floats on a slope
("k", m). The editor script traces down onto the landscape when it is loaded and falls back to "g".

Part fields:
  n     name                         s   cube | cylinder | cone | sphere
  m     material key (house palette) c   [MC x, MC z] centre
  a     anchor: "g" ground (minus k) | "sea" (MC Y 63) | "abs" (MC Y 0)
  y     height of the part's CENTRE above the anchor, m
  size  [along MC x, along MC z, up] in m (a basic shape is 1 m at scale 1)
  rot   [roll, pitch, yaw] degrees (UE order); yaw 0 = east, 90 = south (MC +z)
  f     sub-folder under the landmark's folder (optional)
"""

import json
import math
import os
import random
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bake_terrain as bt  # noqa: E402

OUT = os.path.join(HERE, "landmarks.json")
SEA_Y = 63.0
SEED = 2036

# ----------------------------------------------------------------------------- Moonharbor plan
# From lyris-server/builds/moonharbor2/plan.py (kept zones and streets) and mplots.py (districts).
KEEP_ZONES = {
    "harbour": (112, 300, -2440, -2353), "market": (140, 246, -2353, -2256),
    "moonmarket": (282, 324, -2300, -2248), "library": (330, 394, -2372, -2322),
    "miners": (390, 420, -2412, -2382), "drift": (412, 424, -2432, -2412),
    "station": (498, 546, -2244, -2196), "southhall": (298, 350, -2146, -2118),
    "boatyard": (148, 182, -2158, -2127), "keep": (470, 576, -2565, -2527),
    "mainstreet": (283, 307, -2405, -2306),  # Main Street and Festival Green (builds/mainstreet)
}
MAIN, LANE, ROAD = 5, 3, 5
STREETS = [
    ("High Street", MAIN, [(246, -2284), (606, -2284)]),
    ("North Street", MAIN, [(246, -2316), (606, -2316)]),
    ("South Street", MAIN, [(166, -2250), (606, -2250)]),
    ("Lower Street", MAIN, [(166, -2192), (606, -2192)]),
    ("Wayside Street", MAIN, [(166, -2150), (606, -2150)]),
    ("Shore Road", MAIN, [(170, -2254), (170, -2124)]),
    ("Square Street", MAIN, [(250, -2352), (250, -2124)]),
    ("Mid Street", MAIN, [(326, -2376), (326, -2124)]),
    ("Guild Street", MAIN, [(395, -2380), (395, -2124)]),
    ("Rise Street", MAIN, [(455, -2318), (455, -2124)]),
    ("Station Street", MAIN, [(495, -2318), (495, -2124)]),
    ("East Street", MAIN, [(550, -2318), (550, -2124)]),
    ("Keep Road", ROAD, [(326, -2378), (440, -2378), (501, -2439), (501, -2526)]),
    ("Hill Lane", LANE, [(395, -2348), (606, -2348)]),
    ("Mill Lane", LANE, [(170, -2220), (606, -2220)]),
    ("Point Lane", LANE, [(210, -2250), (210, -2124)]),
    ("Weavers Lane", LANE, [(288, -2250), (288, -2124)]),
    ("Rope Lane", LANE, [(360, -2316), (360, -2124)]),
    ("Drovers Lane", LANE, [(575, -2316), (575, -2124)]),
    ("Crag Lane", LANE, [(455, -2350), (455, -2420), (606, -2420)]),
    ("Upper Lane", LANE, [(550, -2350), (550, -2420)]),
    ("Main Street", LANE, [(295, -2405), (295, -2333)]),
]


def district_of(x, z):
    if z < -2318 and x < 455: return "heights"
    if z < -2250 and x >= 455: return "rise"
    if 250 <= x < 395 and z < -2250: return "market"
    if x >= 395 and z < -2250: return "lamplight"
    if x < 250 and z >= -2256: return "point"
    if x < 455 and -2250 <= z < -2192: return "yards"
    if x < 455 and z >= -2192: return "weavers"
    return "wayside"


# Each quarter was once a village somewhere else, so each keeps its own look (lore.json).
# district: (display name, wall, roof, eaves m range, width m range, roof style)
DISTRICTS = {
    "market":    ("Market",    "Sail",  "Terracotta", (6, 9), (8, 11), "gable"),
    "heights":   ("The Heights", "Stone", "Clay",     (8, 12), (8, 10), "steep"),
    "lamplight": ("Lamplight", "Salt",  "DarkWood",   (5, 8), (7, 10), "gable"),
    "rise":      ("The Rise",  "Stone", "RedBand",    (6, 9), (8, 10), "gable"),
    "point":     ("The Point", "Wood",  "DarkWood",   (4, 6), (7, 9), "gable"),
    "yards":     ("Yards",     "Wood",  "Terracotta", (4, 6), (9, 13), "low"),
    "weavers":   ("Weavers",   "Sail",  "RedBand",    (5, 7), (7, 10), "gable"),
    "wayside":   ("Wayside",   "Salt",  "Wood",       (5, 7), (8, 11), "low"),
}
TOWN_BOX = (100, 620, -2565, -2112)

# ----------------------------------------------------------------------------- ground


class Ground:
    """Baked ground (MC Y) from bake_terrain, cached per point."""

    def __init__(self):
        print("[Lyris] loading the terrain fields (same as the bake) ...")
        self.F = bt.Fields(log=lambda *a: None)
        self.noise = bt.Noise(bt.SEED)
        self.cache = {}

    def many(self, xs, zs):
        xs, zs = np.asarray(xs, float), np.asarray(zs, float)
        h, _ = bt.terrain(self.F, self.noise, xs, zs)
        return h + SEA_Y

    def at(self, x, z):
        key = (round(x, 1), round(z, 1))
        if key not in self.cache:
            self.cache[key] = float(self.many([x], [z])[0])
        return self.cache[key]

    def footprint(self, x, z, sx, sz, yaw=0.0):
        """(centre ground, min corner ground, max corner ground) under a rotated rectangle."""
        a = math.radians(yaw)
        ca, sa = math.cos(a), math.sin(a)
        pts = [(x, z)]
        for u in (-0.5, 0.5):
            for v in (-0.5, 0.5):
                du, dv = u * sx, v * sz
                pts.append((x + du * ca - dv * sa, z + du * sa + dv * ca))
        hs = self.many([p[0] for p in pts], [p[1] for p in pts])
        return float(hs[0]), float(hs.min()), float(hs.max())


G = None


def r1(v):
    return round(float(v), 2)


class LM:
    """One landmark: metadata plus its parts, lights and markers."""

    def __init__(self, lid, name, gaz, kind, x, z, region, notes, source, status="canon", y=None, folder=None):
        self.d = {"id": lid, "name": name, "gazetteer": gaz, "kind": kind, "region": region,
                  "status": status, "source": source, "notes": notes,
                  "folder": folder or f"Landmarks/{region}/{name}"}
        self.x, self.z = x, z
        self.y = y
        self.parts, self.lights, self.markers = [], [], []

    # -- parts
    def part(self, n, s, m, x, z, y, size, anchor="g", rot=(0, 0, 0), sub=None, sink=0.0, ground=None):
        p = {"n": n, "s": s, "m": m, "c": [r1(x), r1(z)], "a": anchor, "y": r1(y),
             "size": [r1(v) for v in size]}
        if any(rot):
            p["rot"] = [r1(v) for v in rot]
        if anchor == "g":
            p["g"] = r1(G.at(x, z) if ground is None else ground)
            if sink:
                p["k"] = r1(sink)
        if sub:
            p["f"] = sub
        self.parts.append(p)
        return p

    def box(self, n, m, x, z, sx, sz, h, base=0.0, yaw=0.0, sub=None, anchor="g", s="cube"):
        """A block standing on the ground (or base m above the anchor). Sinks on slopes."""
        if anchor == "g":
            c, lo, hi = G.footprint(x, z, sx, sz, yaw)
            sink = max(c - lo, 0.0) + 0.3
            return self.part(n, s, m, x, z, base + (h + sink) / 2.0, (sx, sz, h + sink), "g", (0, 0, yaw), sub,
                             sink=sink, ground=c)
        return self.part(n, s, m, x, z, base + h / 2.0, (sx, sz, h), anchor, (0, 0, yaw), sub)

    def cyl(self, n, m, x, z, r, h, base=0.0, sub=None, anchor="g", s="cylinder", rz=None):
        return self.box(n, m, x, z, 2 * r, 2 * (rz or r), h, base, 0.0, sub, anchor, s)

    def roof(self, n, m, x, z, sx, sz, eaves, style, yaw=0.0, sub=None, ground=None):
        """Gable roof: a cube turned 45 degrees about the ridge, half of it hidden in the walls."""
        long_x = sx >= sz
        span, length = (sz, sx) if long_x else (sx, sz)
        # A rotated cube is always a symmetric 45-degree diamond (scale applies before rotation), so the
        # style changes its size: "steep" is a tall hat with deep eaves, "low" a small hip on a flat ledge.
        k = {"gable": 1.08, "steep": 1.4, "low": 0.75}[style]
        side = span / math.sqrt(2.0) * k
        size = (length + 0.6, side, side) if long_x else (side, length + 0.6, side)
        rot = (45.0, 0.0, yaw) if long_x else (0.0, 45.0, yaw)
        return self.part(n, "cube", m, x, z, eaves, size, "g", rot, sub, ground=ground)

    def house(self, n, wall, roof, x, z, sx, sz, eaves, style, yaw=0.0, sub=None):
        c, lo, hi = G.footprint(x, z, sx, sz, yaw)
        sink = max(c - lo, 0.0) + 0.3
        self.part(n + "_Walls", "cube", wall, x, z, (eaves + sink) / 2.0, (sx, sz, eaves + sink), "g",
                  (0, 0, yaw), sub, sink=sink, ground=c)
        self.roof(n + "_Roof", roof, x, z, sx, sz, eaves, style, yaw, sub, ground=c)

    def path(self, n, m, pts, width, sub=None, step=18.0, thick=0.5, anchor="g", level=None):
        """A road or lane draped on the ground: short tilted pieces along a polyline."""
        k = 0
        for (ax, az), (bx, bz) in zip(pts, pts[1:]):
            L = math.hypot(bx - ax, bz - az)
            nseg = max(1, int(math.ceil(L / step)))
            yaw = math.degrees(math.atan2(bz - az, bx - ax))
            for i in range(nseg):
                t0, t1 = i / nseg, (i + 1) / nseg
                x0, z0 = ax + (bx - ax) * t0, az + (bz - az) * t0
                x1, z1 = ax + (bx - ax) * t1, az + (bz - az) * t1
                seg = L / nseg
                if anchor == "g":
                    h0, h1 = G.at(x0, z0), G.at(x1, z1)
                    pitch = math.degrees(math.atan2(h1 - h0, seg))
                    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
                    gm = (h0 + h1) / 2
                    self.part(f"{n}_{k:03d}", "cube", m, cx, cz, 0.12 - thick / 2 + 0.25, (seg + 1.0, width, thick),
                              "g", (0, pitch, yaw), sub, ground=gm)
                else:
                    self.part(f"{n}_{k:03d}", "cube", m, (x0 + x1) / 2, (z0 + z1) / 2, level, (seg + 0.2, width, thick),
                              anchor, (0, 0, yaw), sub)
                k += 1

    def wall(self, n, m, pts, thick, height, sub=None, step=16.0, anchor="g", base=None, merlons=True):
        """A curtain wall: pieces along a polyline, each standing on its own ground."""
        k = 0
        for (ax, az), (bx, bz) in zip(pts, pts[1:]):
            L = math.hypot(bx - ax, bz - az)
            nseg = max(1, int(math.ceil(L / step)))
            yaw = math.degrees(math.atan2(bz - az, bx - ax))
            for i in range(nseg):
                t = (i + 0.5) / nseg
                cx, cz = ax + (bx - ax) * t, az + (bz - az) * t
                seg = L / nseg + 0.4
                if anchor == "g":
                    self.box(f"{n}_{k:03d}", m, cx, cz, seg, thick, height, yaw=yaw, sub=sub)
                else:
                    self.part(f"{n}_{k:03d}", "cube", m, cx, cz, base + height / 2, (seg, thick, height), anchor,
                              (0, 0, yaw), sub)
                k += 1

    def tower(self, n, wall, roof, x, z, r, h, sub=None, anchor="g", base=0.0):
        self.cyl(n + "_Body", wall, x, z, r, h, base, sub, anchor)
        top = base + h
        if anchor == "g":
            c, _lo, _ = G.footprint(x, z, 2 * r, 2 * r)
            self.part(n + "_Roof", "cone", roof, x, z, top + r * 0.75, (2 * r + 1.2, 2 * r + 1.2, r * 1.5), "g",
                      sub=sub, ground=c)
        else:
            self.part(n + "_Roof", "cone", roof, x, z, top + r * 0.75, (2 * r + 1.2, 2 * r + 1.2, r * 1.5), anchor,
                      sub=sub)

    def lamp_post(self, n, x, z, lit=False, sub=None, height=4.0, anchor="g", base=0.0, colour="MOONGLASS",
                  intensity=6000.0, radius=1800.0):
        """Lamp post: dark wood pole, brass cap, cold glass. Lit ones get a point light."""
        self.cyl(n + "_Pole", "DarkWood", x, z, 0.16, height, base, sub, anchor)
        glass = "LampGlass" if lit else "LampGlassDark"
        self.box(n + "_Glass", glass, x, z, 0.6, 0.6, 0.8, base + height, sub=sub, anchor=anchor) \
            if anchor != "g" else self.part(n + "_Glass", "cube", glass, x, z, base + height + 0.4, (0.6, 0.6, 0.8),
                                            "g", sub=sub)
        cap_y = base + height + 1.0
        if anchor == "g":
            self.part(n + "_Cap", "cone", "Gold", x, z, cap_y, (0.9, 0.9, 0.5), "g", sub=sub)
        else:
            self.part(n + "_Cap", "cone", "Gold", x, z, cap_y, (0.9, 0.9, 0.5), anchor, sub=sub)
        if lit:
            self.light(n + "_Light", x, z, base + height + 0.4, colour, intensity, radius, anchor)

    def light(self, n, x, z, y, colour, intensity, radius, anchor="g", always_loaded=False):
        L = {"n": n, "c": [r1(x), r1(z)], "a": anchor, "y": r1(y), "colour": colour,
             "intensity": intensity, "radius": radius}
        if anchor == "g":
            L["g"] = r1(G.at(x, z))
        if always_loaded:
            L["always_loaded"] = True
        self.lights.append(L)

    def marker(self, n, x, z, y, anchor="sea", yaw=0.0, note=""):
        mk = {"n": n, "c": [r1(x), r1(z)], "a": anchor, "y": r1(y), "yaw": r1(yaw), "note": note}
        if anchor == "g":
            mk["g"] = r1(G.at(x, z))
        self.markers.append(mk)

    def done(self):
        xs = [p["c"][0] for p in self.parts] or [self.x]
        zs = [p["c"][1] for p in self.parts] or [self.z]
        ys = []
        for p in self.parts:
            base = {"g": p.get("g", SEA_Y) - p.get("k", 0.0), "sea": SEA_Y, "abs": 0.0}[p["a"]]
            ys.append(base + p["y"] + p["size"][2] / 2)
        ground = self.y if self.y is not None else G.at(self.x, self.z)
        self.d["mc"] = [r1(self.x), r1(ground), r1(self.z)]
        self.d["ue"] = [r1(self.x * 100), r1(self.z * 100), r1((ground - SEA_Y) * 100)]
        self.d["footprint_m"] = [r1(max(xs) - min(xs) + 2), r1(max(zs) - min(zs) + 2)]
        self.d["height_m"] = r1(max(ys) - ground) if ys else 0.0
        self.d["parts"] = self.parts
        if self.lights:
            self.d["lights"] = self.lights
        if self.markers:
            self.d["markers"] = self.markers
        return self.d


# ----------------------------------------------------------------------------- Moonharbor


def rect_hits(x0, x1, z0, z1, rects, pad=0.0):
    for a0, a1, b0, b1 in rects:
        if x0 < a1 + pad and x1 > a0 - pad and z0 < b1 + pad and z1 > b0 - pad:
            return True
    return False


def street_dist(x, z):
    """Distance from a point to the nearest street edge (negative inside a street)."""
    best = 1e9
    for _n, w, pts in STREETS:
        for (ax, az), (bx, bz) in zip(pts, pts[1:]):
            dx, dz = bx - ax, bz - az
            t = max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / (dx * dx + dz * dz)))
            d = math.hypot(x - ax - t * dx, z - az - t * dz) - w / 2.0
            best = min(best, d)
    return best


def moonharbor_districts():
    """House blocks for every district, along its streets, in its own style."""
    rng = random.Random(SEED)
    blocked = [(a - 2, b + 2, c - 2, d + 2) for a, b, c, d in KEEP_ZONES.values()]
    blocked += [(100, 140, -2360, -2320)]          # lighthouse headland and the Chapel of Lamps
    placed = []
    houses = {k: [] for k in DISTRICTS}
    for name, w, pts in STREETS:
        if name in ("Keep Road", "Main Street"):
            continue
        for (ax, az), (bx, bz) in zip(pts, pts[1:]):
            if ax != bx and az != bz:
                continue
            along_x = az == bz
            L = abs(bx - ax) + abs(bz - az)
            sgn = 1 if (bx - ax + bz - az) > 0 else -1
            for side in (-1, 1):
                s = rng.uniform(2, 8)
                while s < L - 4:
                    t = s
                    px = ax + sgn * t if along_x else ax
                    pz = az if along_x else az + sgn * t
                    dist = district_of(px, pz)
                    _dn, wall, roof, eaves_r, width_r, style = DISTRICTS[dist]
                    wid = rng.uniform(*width_r)
                    dep = rng.uniform(7.0, 10.0)
                    off = w / 2.0 + 1.5 + dep / 2.0
                    if along_x:
                        cx, cz, sx, sz = px + sgn * wid / 2, pz + side * off, wid, dep
                    else:
                        cx, cz, sx, sz = px + side * off, pz + sgn * wid / 2, dep, wid
                    x0, x1, z0, z1 = cx - sx / 2, cx + sx / 2, cz - sz / 2, cz + sz / 2
                    ok = (TOWN_BOX[0] < x0 and x1 < TOWN_BOX[1] and TOWN_BOX[2] < z0 and z1 < TOWN_BOX[3]
                          and not rect_hits(x0, x1, z0, z1, blocked)
                          and not rect_hits(x0, x1, z0, z1, placed, pad=1.5)
                          and min(street_dist(px_, pz_) for px_, pz_ in
                                  ((x0, z0), (x0, z1), (x1, z0), (x1, z1), (cx, cz))) > 0.8)
                    if ok:
                        c, lo, hi = G.footprint(cx, cz, sx, sz)
                        ok = lo > SEA_Y + 1.0 and hi - lo < 7.0
                    if ok:
                        placed.append((x0, x1, z0, z1))
                        houses[district_of(cx, cz)].append((cx, cz, sx, sz, rng.uniform(*eaves_r)))
                        s += wid + rng.uniform(2.0, 5.0)
                    else:
                        s += rng.uniform(3.0, 6.0)
    out = []
    for key, items in houses.items():
        dn, wall, roof, _e, _w, style = DISTRICTS[key]
        lm = LM(f"1i-{key}", f"Moonharbor {dn}", "1i", "district", float(np.mean([h[0] for h in items])),
                float(np.mean([h[1] for h in items])), "Moonharbor",
                f"{len(items)} house blocks along the district's own streets in its own style "
                f"({wall} walls, {roof} roofs). Districts as in moonharbor2/mplots.py; house plots are ours, "
                "the server's own plots are not exported yet.", "moonharbor2/plan.py, mplots.py",
                folder=f"Landmarks/Moonharbor/Districts/{dn}")
        for i, (cx, cz, sx, sz, eaves) in enumerate(items):
            lm.house(f"House_{i:03d}", wall, roof, cx, cz, sx, sz, eaves, style)
        out.append(lm.done())
    return out


def moonharbor():
    out = []
    # --- 1: streets and the town walls
    lm = LM("1", "Moonharbor", "1", "town", 360, -2330, "Moonharbor",
            "Streets from moonharbor2/plan.py (5 m streets, 3 m lanes, the Keep Road climbing to the gate). "
            "Waterfront curtain (Witch's Wall) and quay curtain are canon (seawall/walls.py); the landward "
            "wall and its gates around the core box are placed by us so the town reads as walled.",
            "moonharbor2/plan.py; seawall/walls.py", y=65.0, folder="Landmarks/Moonharbor/Town")
    for name, w, pts in STREETS:
        lm.path(name.replace(" ", ""), "Path", pts, w, sub="Streets")
    # Waterfront curtain: walk Y79, sea face on z -2361, from x 132 to 244 (towers and stair cut out).
    for x0, x1 in ((132, 186), (222, 244)):
        lm.wall("HarbourCurtain", "Stone", [(x0, -2359.5), (x1, -2359.5)], 4.0, 80 - 52, sub="Walls",
                anchor="abs", base=52.0)
    lm.wall("CornerLink", "Stone", [(244, -2367), (268, -2367)], 3.0, 75 - 52, sub="Walls", anchor="abs", base=52.0)
    lm.tower("CornerKeep", "Stone", "Clay", 238, -2367, 5.0, 26.0, sub="Walls", anchor="abs", base=52.0)
    lm.wall("QuayCurtain", "Stone", [(268, -2368), (268, -2527)], 3.0, 75 - 52, sub="Walls", anchor="abs", base=52.0)
    # Landward wall (placed by us): south and east of the core, up to Keep Elariel; gates at roads.
    land_wall = [[(150, -2116), (488, -2116)], [(502, -2116), (612, -2116), (612, -2214)],
                 [(612, -2226), (612, -2560), (576, -2560)]]
    for i, run in enumerate(land_wall):
        lm.wall(f"LandWall{i}", "Stone", run, 2.5, 8.0, sub="Walls")
    for i, (tx, tz) in enumerate([(150, -2116), (330, -2116), (488, -2116), (502, -2116), (612, -2116),
                                  (612, -2214), (612, -2226), (612, -2330), (612, -2440), (612, -2560)]):
        lm.tower(f"WallTower{i}", "Stone", "Terracotta", tx, tz, 4.0, 12.0, sub="Walls")
    lm.box("SouthGate_Arch", "Stone", 495, -2116, 16, 4, 11, sub="Gates")
    lm.box("SouthGate_Opening", "Clay", 495, -2116, 6, 4.4, 6, sub="Gates")
    lm.box("EastGate_Arch", "Stone", 612, -2220, 4, 16, 11, sub="Gates")
    lm.box("EastGate_Opening", "Clay", 612, -2220, 4.4, 6, 6, sub="Gates")
    out.append(lm.done())

    # --- 1b: harbour, promenade and finger piers
    lm = LM("1b", "The Harbour", "1b", "harbour", 200, -2380, "Moonharbor",
            "Promenade along the seawall (deck Y 64), four finger piers and the east quay (Net Lane). "
            "The quay is the deep-water berth; the Seawall Stair, Lantern Pier and the statue are their own landmarks.",
            "moonharbor2/plan.py KEEP harbour; seawall/gen.py PIERS", y=64.0,
            folder="Landmarks/Moonharbor/Harbour")
    lm.part("Promenade", "cube", "Stone", 190, -2355, 64.0 - 1.0, (124, 5, 2.0), "abs", sub="Promenade")
    lm.part("EastQuay", "cube", "Stone", 284, -2445, 64.0 - 3.0, (30, 170, 6.0), "abs", sub="Quay")
    for i, (x0, x1) in enumerate([(155, 162), (170, 179), (220, 227), (244, 254)]):
        cx, w = (x0 + x1) / 2, x1 - x0 + 1
        lm.part(f"Pier{i}_Deck", "cube", "Wood", cx, -2378, 65.2, (w * 0.6, 34, 0.5), "abs", sub="Piers")
        for k, pz in enumerate(range(-2365, -2396, 8)):
            for px in (cx - w * 0.3 + 0.3, cx + w * 0.3 - 0.3):
                lm.part(f"Pier{i}_Pile{k}{'ab'[px > cx]}", "cylinder", "DarkWood", px, pz, 59.0, (0.5, 0.5, 13),
                        "abs", sub="Piers")
    for i, z in enumerate((-2372, -2392, -2412, -2432)):  # Net Lane: fisher sheds on the quay
        lm.house(f"NetLane_{i}", "Wood", "DarkWood", 288, z, 9, 12, 4.5, "gable", sub="NetLane")
    for i, z in enumerate((-2380, -2440, -2500)):
        lm.lamp_post(f"QuayLamp{i}", 276, z, lit=True, sub="Lamps", anchor="abs", base=64.0)
    out.append(lm.done())

    # --- 1a: Market Square and the Moonwell
    lm = LM("1a", "Market Square and the Moonwell", "1a", "plaza", 200.5, -2299.5, "Moonharbor",
            "Square paving, the Moonwell pool (water Y 65.9), Town Hall, Museum and the clock tower. "
            "Building spots inside the square are ours (canon gives the square, not each building).",
            "moonharbor2/plan.py; moonwell/moonwell.py", folder="Landmarks/Moonharbor/MarketSquare")
    lm.box("Paving", "Path", 193, -2304, 106, 97, 0.6, sub="Square")
    lm.cyl("Moonwell_Basin", "Stone", 200.5, -2299.5, 5.0, 1.2, sub="Moonwell")
    lm.cyl("Moonwell_Water", "LampGlass", 200.5, -2299.5, 4.3, 0.2, base=1.0, sub="Moonwell")
    lm.cyl("Moonwell_Spire", "Sail", 200.5, -2299.5, 0.8, 4.5, sub="Moonwell")
    lm.light("Moonwell_Light", 200.5, -2299.5, 3.0, "MOONGLASS", 3000.0, 1500.0)
    lm.house("TownHall", "Sail", "Clay", 195, -2340, 32, 14, 10, "steep", sub="TownHall")
    lm.house("Museum", "Stone", "Terracotta", 153, -2296, 14, 26, 8, "gable", sub="Museum")
    lm.box("ClockTower", "Stone", 236, -2340, 7, 7, 24, sub="ClockTower")
    lm.part("ClockTower_Face", "cylinder", "Gold", 236, -2343.6, 19.0, (3.2, 0.3, 3.2), "g", (90, 0, 0), "ClockTower")
    lm.part("ClockTower_Spire", "cone", "Clay", 236, -2340, 24 + 3.5, (8, 8, 7), "g", sub="ClockTower")
    out.append(lm.done())

    # --- 1c: Main Street, Festival Green and the Bright Cask
    lm = LM("1c", "Main Street and the Bright Cask", "1c", "street", 295, -2360, "Moonharbor",
            "Shop row (hatter, dressmaker, bakery, apothecary, library) on both sides of Main Street; "
            "the Bright Cask tavern at its head by Festival Green.", "mainstreet/doc.md",
            folder="Landmarks/Moonharbor/MainStreet")
    lm.box("FestivalGreen", "Grass", 296, -2319, 44, 26, 0.4, sub="FestivalGreen")
    for i, z in enumerate(range(-2398, -2340, 12)):
        lm.house(f"Shop_W{i}", "Sail", "Terracotta", 285, z, 7, 10, 7, "gable", sub="Shops")
        lm.house(f"Shop_E{i}", "Salt", "RedBand", 305, z, 7, 10, 7, "gable", sub="Shops")
    lm.house("BrightCask", "Wood", "Clay", 296, -2338, 16, 9, 8, "steep", sub="BrightCask")
    lm.lamp_post("CaskLamp", 296, -2332, lit=True, sub="BrightCask", colour="LighthouseGlow")
    out.append(lm.done())

    # --- the other kept buildings, each its own landmark
    kept = [
        ("1d", "Moonmarket and the Constabulary", "market", "moonmarket", "Moonmarket plaza; the Lamp Seller's stall sells the first lamp oil",
         [("Plaza", "Path", 303, -2274, 42, 52, 0.5, None), ("Constabulary", "Stone", 314, -2290, 16, 14, 8, "Clay"),
          ("LampSeller", "Wood", 296, -2266, 5, 4, 3, "Terracotta")]),
        ("1e", "Grand Library", "library", "library", "The town's great library and its court",
         [("Hall", "Sail", 362, -2350, 52, 30, 14, "Clay"), ("Dome", None, 362, -2350, 0, 0, 0, None)]),
        ("1f", "Miners' Guild", "guild", "miners", "Deepkin miners; their deep chapel lies under the Guild. Drift mouth at x 412-424, z -2432..-2412",
         [("Guild", "Stone", 405, -2397, 28, 28, 9, "DarkWood"), ("DriftMouth", "Clay", 418, -2422, 10, 18, 5, None)]),
        ("1g", "Carriage Station", "station", "station", "Where the roads leave town (the North Road starts here); the Wayfarers' shrine stands by it",
         [("Hall", "Wood", 522, -2232, 44, 20, 8, "Terracotta"), ("Yard", "Path", 522, -2206, 44, 18, 0.4, None),
          ("WayfarersShrine", "Stone", 549, -2196, 3, 3, 3, "Gold")]),
        ("1h", "Boatyard at the Point", "boatyard", "boatyard", "The shipwright's shore building",
         [("Shed", "Wood", 165, -2142, 32, 18, 9, "DarkWood"), ("Slipway", "Path", 150, -2142, 14, 6, 0.4, None)]),
        ("1j", "South Hall", "hall", "southhall", "The big hall on the south edge of town",
         [("Hall", "Salt", 324, -2132, 50, 26, 11, "Clay")]),
    ]
    for lid, name, kind, zone, notes, items in kept:
        x0, x1, z0, z1 = KEEP_ZONES[zone]
        lm = LM(lid, name, lid, kind, (x0 + x1) / 2, (z0 + z1) / 2, "Moonharbor", notes,
                "moonharbor2/plan.py KEEP", folder=f"Landmarks/Moonharbor/{name}")
        for n, wall, cx, cz, sx, sz, h, roof in items:
            if n == "Dome":
                lm.part("Dome", "sphere", "Clay", cx, cz, 14.0, (18, 18, 14), "g")
                continue
            if roof:
                if n == "WayfarersShrine":
                    lm.box(n, wall, cx, cz, sx, sz, h)
                    lm.part(n + "_Flame", "sphere", roof, cx, cz, h + 0.5, (1, 1, 1), "g")
                else:
                    lm.house(n, wall, roof, cx, cz, sx, sz, h, "gable")
            else:
                lm.box(n, wall, cx, cz, sx, sz, h)
        out.append(lm.done())

    # --- 3: the Seawall Stair and the Stair Towers
    lm = LM("3", "The Seawall Stair", "3", "stair", 204, -2364, "Moonharbor",
            "Seven steps down from the promenade (Y 63 at z -2358 to Y 57), the landing at Y 56 under water, "
            "broken steps on into the deep. Top step XLI at z -2357 carries the 41 notches: never repair it. "
            "Stair Towers either side.", "seawall/gen.py", y=64.0, folder="Landmarks/Moonharbor/SeawallStair")
    lm.part("TopStep_XLI", "cube", "RedBand", 204, -2357, 63.25, (9, 1, 0.5), "abs", sub="Stair")
    for k in range(7):
        z, y = -2358 - k, 63 - k
        lm.part(f"Step{k}", "cube", "Stone", 204, z, (y + 50) / 2.0, (9, 1, y - 50), "abs", sub="Stair")
    lm.part("Landing", "cube", "Stone", 204, -2368, 53.0, (9, 7, 6), "abs", sub="Stair")
    for side, x in (("W", 199), ("E", 209)):
        lm.part(f"Cheek{side}", "cube", "Stone", x, -2364, 57.0, (1, 14, 14), "abs", sub="Stair")
    for name, (tx, tz) in (("StairTowerW", (193, -2363)), ("StairTowerE", (215, -2363))):
        lm.part(name + "_Base", "cylinder", "Stone", tx, tz, 56.5, (12, 12, 13), "abs", sub=name)
        lm.part(name + "_Body", "cylinder", "Stone", tx, tz, 71.0, (10, 10, 14), "abs", sub=name)
        lm.part(name + "_Battlement", "cylinder", "Stone", tx, tz, 79.0, (12, 12, 2), "abs", sub=name)
        lm.part(name + "_Upper", "cylinder", "Stone", tx, tz, 84.5, (8, 8, 9), "abs", sub=name)
        lm.part(name + "_Roof", "cone", "Clay", tx, tz, 94.0, (9, 9, 10), "abs", sub=name)
        lm.light(name + "_Lamp", tx, tz, 90.0, "MOONGLASS", 4000.0, 2000.0, "abs")
    out.append(lm.done())

    # --- 8: Lantern Pier, the Tide Mother shrine, and the T37 dock spot
    lm = LM("8", "Lantern Pier", "8", "pier", 136, -2390, "Moonharbor",
            "Pier from the promenade out to the Tide Mother's driftwood shrine under whale-rib arches "
            "(pier end 136, 66.6, -2418). T37: the player boat, dock and dock lamp move here; the berth is "
            "on the pier's east side (markers T37_*).", "hungstar/build.py", y=66.6,
            folder="Landmarks/Moonharbor/LanternPier")
    lm.part("Deck", "cube", "Wood", 136, -2389, 65.9, (6, 62, 0.6), "abs", sub="Pier")
    for k, pz in enumerate(range(-2362, -2420, 8)):
        for px in (133.6, 138.4):
            lm.part(f"Pile{k}{'ab'[px > 136]}", "cylinder", "DarkWood", px, pz, 59.0, (0.6, 0.6, 14), "abs", sub="Pier")
    lm.part("Shrine", "cube", "DarkWood", 136, -2418, 66.2 + 1.5, (4, 4, 3), "abs", sub="Shrine")
    for i, z in enumerate((-2410, -2414, -2422)):
        for sx in (-1, 1):
            lm.part(f"WhaleRib{i}{'ab'[sx > 0]}", "cylinder", "Sail", 136 + sx * 2.6, z, 66.2 + 3.0, (0.5, 0.5, 6),
                    "abs", (0, sx * 12.0, 90), "Shrine")
        lm.part(f"WhaleRibTop{i}", "cube", "Sail", 136, z, 66.2 + 6.0, (5.6, 0.5, 0.5), "abs", sub="Shrine")
    # T37 hand-off: where the Harbor map's dock, boat and lamp go.
    lm.part("T37_Berth", "cube", "Wood", 141.5, -2404, 65.4, (5, 22, 0.5), "abs", sub="T37_Dock")
    lm.lamp_post("T37_DockLamp", 139.5, -2414, lit=True, sub="T37_Dock", anchor="abs", base=66.2)
    lm.marker("T37_BoatStart", 147.0, -2404.0, 0.0, "sea", yaw=-90.0,
              note="Player boat start: moored on Lantern Pier's east side, bow north toward the bay mouth")
    lm.marker("T37_DockLamp", 139.5, -2414.0, 66.2, "abs", note="ALyrisDockLamp / T3 lamp component goes here")
    lm.marker("T37_Mooring", 147.0, -2398.0, 0.0, "sea", yaw=-90.0, note="ALyrisHarborMooring (T41) for swamped boats")
    lm.marker("T37_StepAshore", 139.0, -2404.0, 66.6, "abs", note="Where the player steps from the boat onto the pier")
    out.append(lm.done())

    # --- 5: Ilwen's Lighthouse (lit) and 5a the Chapel of Lamps
    lm = LM("5", "Ilwen's Lighthouse", "5", "lighthouse", 127, -2343, "Moonharbor",
            "Terrace floor Y 70 (r 13.5), the keeper's hall drum (r 10), a slender calcite shaft to the gallery "
            "deck at Y 127 and the great lamp. Cold light only (Elven Night). The copper oil cistern: "
            "'Pour a tin. Keep her lit.' A sweeping beam is World lane work (T3).",
            "lighthouse/ilwen.py", y=70.0, folder="Landmarks/Moonharbor/Lighthouse")
    lm.part("Terrace", "cylinder", "Stone", 127, -2343, 70.0 - 4.0, (27, 27, 8), "abs", sub="Tower")
    lm.part("Drum", "cylinder", "Stone", 127, -2343, 75.0, (20, 20, 9), "abs", sub="Tower")
    lm.part("ShaftLow", "cylinder", "Sail", 127, -2343, 79 + 12.0, (14.6, 14.6, 24), "abs", sub="Tower")
    lm.part("ShaftHigh", "cylinder", "Sail", 127, -2343, 103 + 12.0, (11.0, 11.0, 24), "abs", sub="Tower")
    lm.part("Gallery", "cylinder", "Clay", 127, -2343, 127.5, (17, 17, 1.0), "abs", sub="Lamp")
    lm.part("LanternRoom", "cylinder", "LampGlass", 127, -2343, 131.0, (8, 8, 6), "abs", sub="Lamp")
    lm.part("Roof", "cone", "Clay", 127, -2343, 137.0, (10, 10, 6), "abs", sub="Lamp")
    lm.part("Finial", "sphere", "Gold", 127, -2343, 140.5, (1.2, 1.2, 1.2), "abs", sub="Lamp")
    lm.light("GreatLamp", 127, -2343, 131.0, "MOONGLASS", 60000.0, 20000.0, "abs", always_loaded=True)
    lm.part("OilCistern", "cylinder", "Terracotta", 142, -2338, 72.0, (3, 3, 4), "abs", sub="Cistern")
    out.append(lm.done())

    lm = LM("5a", "Chapel of Lamps", "5a", "chapel", 132, -2322, "Moonharbor",
            "Home of the Lantern Covenant, with the Lamp Tree over the altar. Between the town and the "
            "lighthouse; spot placed by us.", "lore.json lighthouse", status="placed by us",
            folder="Landmarks/Moonharbor/ChapelOfLamps")
    lm.house("Chapel", "Sail", "Clay", 132, -2322, 9, 16, 7, "steep")
    lm.box("Belfry", "Sail", 132, -2331, 4, 4, 13)
    lm.lamp_post("LampTree", 132, -2311, lit=True, colour="LighthouseGlow", height=3.0)
    out.append(lm.done())

    # --- 4: Syrena's statue and the Hung Star
    lm = LM("4", "Syrena's statue and the Hung Star", "4", "statue", 247, -2462, "Moonharbor",
            "The statue on its islet in the bay, sword (Ysolde's Thorn) pointing due north 40 degrees up "
            "at the pole star; the false star hangs at the tip (245.5, 139.5, -2510.5) and never turns. "
            "She wears a wide witch's hat where her crown should be.",
            "syrena/export_live.py; syrena/statue.py; hungstar/build.py", y=64.0,
            folder="Landmarks/Moonharbor/SyrenaStatue")
    lm.part("Islet", "cylinder", "Stone", 247, -2462, 60.0, (18, 18, 8), "abs", sub="Plinth")
    lm.part("Plinth", "cube", "Stone", 247, -2462, 66.5, (8, 8, 5), "abs", sub="Plinth")
    lm.part("Legs", "cylinder", "Sail", 247, -2462, 69 + 7.5, (3.6, 3.0, 15), "abs", sub="Figure")
    lm.part("Body", "cylinder", "Sail", 247, -2462, 84 + 6.0, (4.8, 3.4, 12), "abs", sub="Figure")
    lm.part("Head", "sphere", "Sail", 247, -2462, 98.5, (3.0, 3.0, 3.4), "abs", sub="Figure")
    lm.part("HatBrim", "cylinder", "Clay", 247, -2462, 100.3, (8, 8, 0.4), "abs", sub="Figure")
    lm.part("HatCone", "cone", "Clay", 248, -2462, 103.5, (3.6, 3.6, 6.5), "abs", (0, 12, 0), sub="Figure")
    tip = np.array([245.5, 139.5, -2510.5])
    d = np.array([0.0, math.sin(math.radians(40)), -math.cos(math.radians(40))])  # (x, y, z) north and up
    guard = tip - d * (44.0 + 4.6)
    mid = (guard + tip) / 2
    lm.part("Sword_Blade", "cube", "Salt", mid[0], mid[2], mid[1], (1.0, 1.6, 44.0 + 4.6), "abs", (-50.0, 0, 0),
            sub="Sword")  # UE roll: looking along +X, positive is clockwise, tipping up toward +Y (south)
    lm.part("Sword_Guard", "cube", "Gold", guard[0], guard[2], guard[1], (6, 1.0, 1.0), "abs", sub="Sword")
    lm.part("HungStar", "sphere", "LampGlass", tip[0], tip[2] - 1.7, tip[1] + 1.4, (1.6, 1.6, 1.6), "abs", sub="HungStar")
    lm.light("HungStar_Light", tip[0], tip[2] - 1.7, tip[1] + 1.4, "MOONGLASS", 8000.0, 4000.0, "abs",
             always_loaded=True)
    out.append(lm.done())

    # --- 2: Keep Elariel and the Moon Window
    lm = LM("2", "Keep Elariel and the Moon Window", "2", "castle", 523, -2546, "Moonharbor",
            "Walls x 470-576, z -2565..-2527, gate at (501, 138, -2526) facing the Keep Road; four front towers; "
            "the keep and cathedral (Moonwake) inside; the Moon Window garden with its lamp kept lit by Syrena "
            "and Sir Cog kneeling there; the Moon Chapel on a terrace west of the keep (spot ours).",
            "moonharbor2/plan.py KEEP; keepfront/README.md", y=138.0, folder="Landmarks/Moonharbor/KeepElariel")
    for nm, pts in (("WallN", [(470, -2565), (576, -2565)]), ("WallW", [(470, -2565), (470, -2527)]),
                    ("WallE", [(576, -2565), (576, -2527)]), ("WallS_W", [(470, -2527), (495, -2527)]),
                    ("WallS_E", [(507, -2527), (576, -2527)])):
        lm.wall(nm, "Stone", pts, 3.0, 14.0, sub="Curtain")
    for i, (tx, tz) in enumerate([(470, -2565), (576, -2565), (470, -2527), (576, -2527)]):
        lm.tower(f"CornerTower{i}", "Stone", "Clay", tx, tz, 5.0, 20.0, sub="Towers")
    for i, tx in enumerate((482, 494, 508, 520)):
        lm.tower(f"FrontTower{i}", "Stone", "Clay", tx, -2524, 3.5, 18.0, sub="Towers")
    lm.box("Gate", "Clay", 501, -2526.5, 6, 4, 7, sub="Gate")
    lm.part("Gate_Doors", "cube", "Gold", 501, -2524.4, 3.5, (5, 0.3, 6.5), "g", sub="Gate")
    lm.box("Bailey", "Grass", 523, -2546, 102, 34, 0.4, sub="Bailey")
    lm.house("Keep", "Stone", "Clay", 540, -2552, 30, 18, 24, "steep", sub="Keep")
    lm.tower("KeepTower", "Sail", "Clay", 556, -2556, 5.0, 36.0, sub="Keep")
    lm.house("Cathedral", "Sail", "Clay", 503, -2554, 14, 20, 18, "steep", sub="Cathedral")
    lm.box("MoonWindow_Frame", "Sail", 522, -2537, 4, 1, 6, sub="MoonWindow")
    lm.part("MoonWindow_Glass", "cylinder", "LampGlass", 522, -2536.4, 4.5, (3, 0.3, 3), "g", (90, 0, 0), "MoonWindow")
    lm.light("MoonWindow_Light", 522, -2535.5, 4.5, "MOONGLASS", 5000.0, 2500.0)
    lm.box("SirCog", "Gold", 528, -2536, 1.6, 2.2, 1.8, sub="MoonWindow")
    lm.box("MoonChapel_Terrace", "Stone", 452, -2546, 18, 26, 2.0, sub="MoonChapel")
    lm.house("MoonChapel", "Sail", "Clay", 452, -2546, 10, 16, 7, "steep", sub="MoonChapel")
    out.append(lm.done())
    return out


# ----------------------------------------------------------------------------- the rest of the Reach


def observatory():
    cx, cz = 1326.0, -2980.0
    lm = LM("9", "The Grand Observatory", "9", "observatory", cx, cz, "QuietReach",
            "Aurenn star platform (terraces r 32, 27, 21 at +0, +2, +3 m), the drum (r 14) to the wall plate at "
            "+23 m, a pointed dome (r 15, 1.3 taller than wide) with its slit on the south meridian, twelve "
            "peristyle columns (r 19). The Great Refractor looks out of the slit at 65 degrees. Half ruined: the "
            "restoration scaffold stands against the west wall. Hoarfeather's perch nearby. The academy hub.",
            "observatory/README.md, obs.py", y=263.0, folder="Landmarks/QuietReach/Observatory")
    base = 263.0
    for i, (r, top) in enumerate(((32, 0.0), (27, 2.0), (21, 3.0))):
        lm.part(f"Terrace{i}", "cylinder", "Stone", cx, cz, base + top - 3.0, (2 * r, 2 * r, 6.0), "abs", sub="Platform")
    for k in range(12):  # the Aurenn meridian lines
        a = math.radians(k * 30)
        lm.part(f"Meridian{k:02d}", "cube", "Gold", cx + math.sin(a) * 24, cz - math.cos(a) * 24, base + 2.1,
                (0.5, 12, 0.2), "abs", (0, 0, -k * 30), "Platform")
    lm.part("Drum", "cylinder", "Sail", cx, cz, base + 3 + 10.0, (28, 28, 20), "abs", sub="Temple")
    lm.part("Dome", "sphere", "Clay", cx, cz, base + 23.0, (30, 30, 39), "abs", sub="Temple")
    lm.part("Slit", "cube", "Gold", cx, cz + 13.5, base + 30.0, (1.2, 4, 18), "abs", (0, -30, 90), "Temple")
    lm.part("Door", "cube", "Clay", cx, cz + 14.0, base + 6.0, (4, 1.2, 6), "abs", sub="Temple")
    for k in range(12):
        a = math.radians(k * 30 + 15)
        lm.part(f"Column{k:02d}", "cylinder", "Sail", cx + math.sin(a) * 19, cz - math.cos(a) * 19, base + 3 + 9.0,
                (1.6, 1.6, 18), "abs", sub="Peristyle")
    lm.part("Refractor", "cylinder", "Gold", 1326.5, -2966.0, 286.0, (1.2, 1.2, 10), "abs", (0, 0, 0), "Refractor")
    lm.parts[-1]["rot"] = [r1(25.0), 0.0, 0.0]  # tube 65 degrees up toward the south slit (+Y)
    for k in range(4):  # scaffold against the west wall
        lm.part(f"Scaffold{k}", "cube", "Wood", cx - 15.5, cz - 6 + k * 4, base + 3 + 8.0, (0.4, 0.4, 16), "abs",
                sub="Scaffold")
    lm.part("ScaffoldDeck", "cube", "Wood", cx - 15.5, cz, base + 3 + 12.0, (2, 14, 0.3), "abs", sub="Scaffold")
    lm.part("FundSign", "cube", "Wood", cx - 17.5, cz + 8, base + 1.5, (0.2, 2, 1.2), "abs", sub="Scaffold")
    lm.part("Hoarfeather_Perch", "cylinder", "DarkWood", cx + 26, cz + 22, base + 1.5, (0.4, 0.4, 5), "abs",
            sub="Hoarfeather")
    lm.part("Hoarfeather_Bar", "cube", "DarkWood", cx + 26, cz + 22, base + 4.0, (2.5, 0.3, 0.3), "abs",
            sub="Hoarfeather")
    lm.light("Lantern", cx, cz + 15, base + 7.0, "MOONGLASS", 2500.0, 1500.0, "abs")
    return lm.done()


NORTH_ROAD = [(546, -2220), (640, -2240), (700, -2330), (760, -2520), (860, -2720), (980, -2905),
              (1080, -3060), (1200, -3260), (1380, -3480), (1520, -3720), (1620, -3900), (1660, -3950)]


def north_road():
    lm = LM("10", "The North Road", "10", "road", 980, -2905, "QuietReach",
            "From the Carriage Station north past the Observatory spur to the Delvers' Gate, about 2.1 km here, "
            "lamp-lined with pilgrims' cairns. Lantern V (Tobin Marsh's last) at (980, -2905). Route is ours "
            "between the canon ends.", "atlas note in index.html", folder="Landmarks/QuietReach/NorthRoad")
    lm.path("Road", "Path", NORTH_ROAD, 4.0, sub="Road", step=24.0)
    lm.path("ObservatorySpur", "Path", [(1080, -3060), (1180, -3020), (1270, -2990), (1294, -2982)], 3.0,
            sub="Road", step=24.0)
    # A lantern every ~250 m; numbered from the town, lantern V is canon.
    d_acc, nxt, k = 0.0, 120.0, 1
    pts = NORTH_ROAD
    for (ax, az), (bx, bz) in zip(pts, pts[1:]):
        L = math.hypot(bx - ax, bz - az)
        while nxt <= d_acc + L:
            t = (nxt - d_acc) / L
            x, z = ax + (bx - ax) * t, az + (bz - az) * t
            nx, nz = (bz - az) / L, -(bx - ax) / L  # beside the road
            if k == 5:
                x, z = 980.0, -2905.0
            lm.lamp_post(f"Lantern{k:02d}", x + nx * 3.5, z + nz * 3.5, lit=(k != 5), sub="Lanterns")
            lm.box(f"Cairn{k:02d}", "Stone", x - nx * 3.5, z - nz * 3.5, 1.4, 1.4, 1.2, sub="Cairns")
            k += 1
            nxt += 250.0
        d_acc += L
    lm.d["notes"] += " Lantern V is placed dark: it went out when Tobin vanished."
    return lm.done()


def delvers_gate():
    lm = LM("11", "The Delvers' Gate", "11", "dungeon", 1650, -3950, "QuietReach",
            "A winding cleft to a sunken court and the great round brass door (1820, 155, -3955): THE STAR SLEEPS "
            "UNDER THE WATER. The Remnant's rubble wall across the cleft mouth, the Lodge with the Delvers' Roll, "
            "and the lamplighter's lantern still burning by the door.", "atlas PLACES; lore.json hollowdeep",
            y=136.0, folder="Landmarks/QuietReach/DelversGate")
    a, b = np.array([1660.0, -3950.0]), np.array([1785.0, -3955.0])
    d = (b - a) / np.linalg.norm(b - a)
    nrm = np.array([-d[1], d[0]])
    for i in range(6):
        t = (i + 0.5) / 6
        p = a + (b - a) * t
        wob = 1.5 * math.sin(i * 1.7)
        for side in (-1, 1):
            q = p + nrm * side * (8.0 + wob)
            lm.box(f"CleftWall{i}{'ab'[side > 0]}", "Rock", q[0], q[1], 22, 5, 14 + 4 * (i % 2), yaw=math.degrees(
                math.atan2(d[1], d[0])), sub="Cleft")
    lm.box("RubbleWall", "Stone", 1668, -3950, 2.5, 13, 3.5, sub="RubbleWall")
    lm.cyl("Court", "Stone", 1800, -3955, 18.0, 0.6, sub="Court")
    lm.part("CourtCliff", "cube", "Rock", 1826, -3955, 13.0, (10, 44, 26), "g", sub="Court")
    lm.part("BrassDoor", "cylinder", "Gold", 1820.5, -3955, 6.0, (10, 10, 1.2), "g", (0, 90, 0), "Door")
    lm.part("DoorRunes", "cube", "Salt", 1820.6, -3955, 12.5, (0.4, 9, 1.0), "g", sub="Door")
    lm.lamp_post("LamplightersLantern", 1814, -3948, lit=True, sub="Door", height=2.0, colour="LighthouseGlow",
                 intensity=3000.0, radius=1200.0)
    lm.house("Lodge", "Wood", "DarkWood", 1640, -3928, 10, 8, 4.5, "gable", sub="Lodge")
    lm.box("DelversRoll", "DarkWood", 1648, -3934, 1.2, 0.6, 1.4, sub="Lodge")
    return lm.done()


def hollowmere():
    lm = LM("14", "Hollowmere ruins and the Herring Road bridge", "14", "ruin", -675, -950, "QuietReach",
            "The droving village that burned on the third mist night: roofless walls either side of the river, "
            "the herring-a-barrel toll bridge, a singing-stone waymark with its top chipped. Spot placed by us.",
            "lore.json hollowmere", status="placed by us", folder="Landmarks/QuietReach/Hollowmere")
    rng = random.Random(14)
    spots = [(-720, -985), (-700, -1000), (-668, -990), (-640, -982), (-735, -965),
             (-690, -880), (-655, -895), (-625, -885), (-708, -868)]
    for i, (x, z) in enumerate(spots):
        sx, sz = rng.uniform(7, 10), rng.uniform(6, 9)
        h = rng.uniform(1.2, 3.5)
        mat = "Clay" if i % 3 else "DarkWood"
        for k, (dx, dz, wx, wz) in enumerate(((0, -sz / 2, sx, 0.6), (0, sz / 2, sx * 0.6, 0.6),
                                              (-sx / 2, 0, 0.6, sz), (sx / 2, 0, 0.6, sz * 0.5))):
            lm.box(f"Ruin{i}_Wall{k}", mat, x + dx, z + dz, wx, wz, h * (1.0 - 0.25 * k), sub="Ruins")
        lm.box(f"Ruin{i}_Chimney", "Stone", x + sx / 2 - 1, z - sz / 2 + 1, 1.2, 1.2, h + 2.5, sub="Ruins")
    lm.part("Bridge_Deck", "cube", "Wood", -675, -928, 71.0, (4, 46, 0.6), "abs", sub="Bridge")
    for k, z in enumerate((-948, -936, -920, -908)):
        lm.part(f"Bridge_Pier{k}", "cube", "Stone", -675, z, 67.5, (4.6, 2, 6.5), "abs", sub="Bridge")
    lm.box("TollHut", "Wood", -680, -956, 3, 3, 2.5, sub="Bridge")
    lm.box("HerringBarrels", "Wood", -671, -957, 2, 1, 1.0, sub="Bridge")
    lm.box("SingingStone", "Stone", -640, -960, 0.9, 0.7, 1.8, sub="Waymark")
    return lm.done()


def under_halls():
    lm = LM("15", "The Under-Halls gate", "15", "gate", -3150, -950, "QuietReach",
            "The Deepkin mine-holds that shut at dusk and never lost a soul: a carved gate in the grey "
            "mountains. Spot placed by us.", "lore.json under-halls", status="placed by us",
            folder="Landmarks/QuietReach/UnderHalls")
    lm.box("PillarL", "Stone", -3158, -950, 3, 3, 14)
    lm.box("PillarR", "Stone", -3142, -950, 3, 3, 14)
    lm.box("Lintel", "Stone", -3150, -950, 20, 3.4, 3, base=14)
    lm.box("Door", "Clay", -3150, -950.6, 13, 2.4, 13)
    lm.box("Steps", "Stone", -3150, -944, 14, 6, 1.2)
    return lm.done()


def teeth():
    lm = LM("12", "The Teeth", "12", "reef", 150, -3550, "QuietReach",
            "A reef in the channel north of the bay mouth (sea Y 56 there); Syrena swims there at dawn. "
            "Spot placed by us.", "lore.json", status="placed by us", y=63.0, folder="Landmarks/QuietReach/Teeth")
    rng = random.Random(12)
    for i in range(9):
        a = i / 9 * math.pi * 1.4 - 0.7
        x, z = 150 + math.cos(a) * 70 + rng.uniform(-12, 12), -3550 + math.sin(a) * 30 + rng.uniform(-10, 10)
        h = rng.uniform(9, 14)
        lm.part(f"Tooth{i}", "cone", "Rock", x, z, 54.0 + h / 2, (rng.uniform(5, 9), rng.uniform(4, 8), h), "abs",
                (rng.uniform(-8, 8), rng.uniform(-8, 8), rng.uniform(0, 90)))
    return lm.done()


def oruth():
    cx, cz = -119.5, -2611.5
    lm = LM("6", "Oruth, the Fallen Star", "6", "underwater", cx, cz, "Moonharbor",
            "The Chamber of the Hollow Star: a glass dome (x -135..-105) on the floor of the bay pit (floor Y -39), "
            "with the singing star's crystal heart inside, breathing light every 24 s (World/Audio later). "
            "Readable from a boat over the pit on calm days.", "oruth/gen_dp.py", y=-39.0,
            folder="Landmarks/Moonharbor/Oruth")
    lm.part("Floor", "cylinder", "Stone", cx, cz, -39.0 - 1.0, (34, 34, 2), "abs", sub="Chamber")
    lm.part("Dome", "sphere", "Glass", cx, cz, -39.0, (31, 31, 30), "abs", sub="Chamber")
    lm.part("StarHeart", "sphere", "StarGlow", cx, cz, -39.0 + 4.5, (5, 5, 6), "abs", sub="Star")
    for k in range(6):
        a = math.radians(k * 60 + 10)
        lm.part(f"Crystal{k}", "cone", "StarGlow", cx + math.cos(a) * 4, cz + math.sin(a) * 4, -39 + 2.0,
                (1.6, 1.6, 4.5), "abs", (math.cos(a) * 25, math.sin(a) * 25, 0), "Star")
    lm.light("StarLight", cx, cz, -39.0 + 6.0, "MOONGLASS", 30000.0, 6000.0, "abs", always_loaded=True)
    lm.light("StarGlowUp", cx, cz, -6.0, "MOONGLASS", 4000.0, 3000.0, "abs")
    return lm.done()


WAYSTONES = [("16a", 725, -2650), ("16b", 1400, -3650), ("16c", 5725, -2200), ("16d", 7225, -1275), ("16e", -100, -4675)]


def waystone_ring(lid, name, x, z, folder, region, status, notes, source):
    gaz = "16" if lid.startswith("16") else lid.split("-")[0]
    lm = LM(lid, name, gaz, "waystones", x, z, region, notes, source,
            status=status, folder=folder)
    for k in range(9):
        a = math.radians(k * 40)
        lm.box(f"Stone{k}", "Stone", x + math.cos(a) * 12, z + math.sin(a) * 12, 1.4, 0.9, 3.2 + (k % 3) * 0.6,
               yaw=k * 40)
    lm.box("CentreStone", "Salt", x, z, 1.8, 1.2, 4.2)
    lm.part("CentreLine", "cube", "RedBand", x, z + 0.62, 2.6, (1.4, 0.1, 0.25), "g")
    return lm.done()


def landings():
    out = []
    lm = LM("17", "Saltreach landing", "17", "landing", -2660, 2280, "Saltreach",
            "A wild landing, no town yet: a timber jetty out from the beach, a cairn and a lamp.",
            "regions/config.yml", folder="Landmarks/Saltreach/Landing")
    lm.part("Jetty", "cube", "Wood", -2660, 2318, 64.5, (4, 50, 0.5), "abs", sub="Jetty")
    for k, z in enumerate(range(2296, 2342, 9)):
        for dx in (-1.6, 1.6):
            lm.part(f"Pile{k}{'ab'[dx > 0]}", "cylinder", "DarkWood", -2660 + dx, z, 58.5, (0.5, 0.5, 12), "abs",
                    sub="Jetty")
    lm.box("Cairn", "Stone", -2655, 2352, 2, 2, 1.8, sub="Shore")
    lm.lamp_post("Lamp", -2664, 2350, lit=True, sub="Shore")
    out.append(lm.done())
    lm = LM("18", "Sunreach landing", "18", "landing", 2660, 2150, "Sunreach",
            "A wild landing, no town yet. The gazetteer spot is 230 m inland; the jetty is on the north shore "
            "below it, with a cairn path up to the waymark.", "regions/config.yml",
            folder="Landmarks/Sunreach/Landing")
    lm.part("Jetty", "cube", "Wood", 2660, 1905, 64.5, (4, 54, 0.5), "abs", sub="Jetty")
    for k, z in enumerate(range(1880, 1932, 9)):
        for dx in (-1.6, 1.6):
            lm.part(f"Pile{k}{'ab'[dx > 0]}", "cylinder", "DarkWood", 2660 + dx, z, 58.5, (0.5, 0.5, 12), "abs",
                    sub="Jetty")
    lm.path("Track", "Path", [(2660, 1934), (2660, 2150)], 3.0, sub="Track", step=24.0)
    lm.box("Cairn", "Stone", 2655, 1945, 2, 2, 1.8, sub="Shore")
    lm.lamp_post("Lamp", 2665, 1942, lit=True, sub="Shore")
    lm.box("Waymark", "Stone", 2664, 2150, 1.2, 1.2, 2.5, sub="Waymark")
    out.append(lm.done())
    return out


# ----------------------------------------------------------------------------- the new island chains

CHAIN_LAMPS = {  # chain id: (which islets get a lamp, region, extra)
    "A": ("all", "Lampwick Skerries: one dark lamp post on each islet, for new players to relight"),
    "B": ("first", "Hushed Isles: a silent bell tower beside the lamp"),
    "C": ("second", "Wickstones: the waystone ring stands in the clearing on the biggest isle"),
    "D": ("first", "Tallow Banks: a drying rack and rendering shed for lanterneel oil"),
    "E": ("first", "Southing Stones: the navigators' cairn"),
    "F": ("first", "Rime Skerries: a frozen beacon"),
    "G": ("first", "Unremembered Isles: a pale, half-drawn beacon"),
    "H": ("first", "Ember Isle: a plain beacon; no volcano (DECISIONS 2026-10-20), purpose still open"),
}


def island_chains():
    out = []
    for chain in bt.ISLANDS:
        cid = chain["id"]
        which, notes = CHAIN_LAMPS[cid]
        isl = chain["islets"]
        cx = float(np.mean([i[0] for i in isl]))
        cz = float(np.mean([i[1] for i in isl]))
        lm = LM(cid, chain["name"], cid, "island chain", cx, cz, "NewIslands",
                notes + ". Terrain from bake_terrain.ISLANDS; lamps are placed dark (relighting is World lane T3).",
                "design/world_map.md section 4", status="new, approved 2026-10-20",
                folder=f"Landmarks/NewIslands/{cid} {chain['name']}")
        idx = {"all": range(len(isl)), "first": [0], "second": [1]}[which]
        for k in idx:
            ix, iz = isl[k][0], isl[k][1]
            # the highest ground near the islet centre, so the lamp crowns it
            best = max(((G.at(ix + dx, iz + dz), ix + dx, iz + dz) for dx in (-20, 0, 20) for dz in (-20, 0, 20)))
            _, lx, lz = best
            colour_pole = "Salt" if cid == "G" else "DarkWood"
            lm.lamp_post(f"Lamp_{cid}{k + 1}", lx, lz, lit=False, sub="Lamps", height=5.0)
            if colour_pole != "DarkWood":
                lm.parts[-3]["m"] = colour_pole
            lm.box(f"LampFooting_{cid}{k + 1}", "Stone", lx, lz, 1.6, 1.6, 0.6, sub="Lamps")
        x0, z0 = isl[0][0], isl[0][1]
        if cid == "B":
            lm.box("BellTower", "Stone", x0 + 18, z0 + 6, 5, 5, 14, sub="BellTower")
            lm.part("BellTower_Roof", "cone", "Clay", x0 + 18, z0 + 6, 16.5, (6.5, 6.5, 5), "g", sub="BellTower")
        if cid == "D":
            lm.house("RenderingShed", "Wood", "DarkWood", x0 + 40, z0 - 10, 12, 7, 3.5, "low", sub="Sheds")
            for k in range(3):
                lm.box(f"DryingRack{k}", "Wood", x0 - 30 + k * 6, z0 + 15, 0.3, 5, 2.2, sub="Sheds")
        if cid == "E":
            lm.cyl("NavigatorsCairn", "Stone", x0 + 10, z0, 1.8, 2.6, sub="Cairn")
        out.append(lm.done())
        if cid == "C":
            out.append(waystone_ring("C-ring", "Wickstones waystone ring", float(isl[0][0]), float(isl[0][1]),
                                     "Landmarks/NewIslands/C Wickstones/WaystoneRing", "NewIslands",
                                     "new, approved 2026-10-20",
                                     "The ring that answers the rings on the Reach uplands, in the flat clearing the "
                                     "bake leaves on the biggest isle.", "design/world_map.md section 4"))
    return out


# ----------------------------------------------------------------------------- main


def main():
    global G
    G = Ground()
    lms = []
    lms += moonharbor()
    lms += moonharbor_districts()
    lms.append(oruth())
    lms.append(observatory())
    lms.append(north_road())
    lms.append(delvers_gate())
    lms.append(teeth())
    lms.append(hollowmere())
    lms.append(under_halls())
    for lid, x, z in WAYSTONES:
        lms.append(waystone_ring(lid, f"Waystone ring {lid[-1].upper()}", x, z,
                                 f"Landmarks/QuietReach/Waystones/Ring {lid[-1].upper()}", "QuietReach",
                                 "placed by us",
                                 "Tuned Aurenn stones that carried the star's song inland; THE STAR SLEEPS UNDER THE "
                                 "WATER cut on the centre stone (the red line). Flat upland site from the gazetteer.",
                                 "lore.json waystones; world_map.md #16"))
    lms += landings()
    lms += island_chains()
    doc = {
        "about": "Blockout landmarks for the Lyris world map (T36). Generated by Art/World/make_landmarks.py; "
                 "spawned by Content/Python/lyris_build_landmarks.py. Coordinates are MC blocks (1 m); "
                 "UE X = MC x * 100, UE Y = MC z * 100, UE Z = (MC Y - 63) * 100.",
        "bake_version": bt.BAKE_VERSION,
        "palette_note": "Material keys are the Harbor PALETTE / ISLAND_PALETTE names; see lyris_build_landmarks.MATERIALS.",
        "landmarks": lms,
    }
    with open(OUT, "w") as f:
        json.dump(doc, f, separators=(",", ":"))
    n_parts = sum(len(l["parts"]) for l in lms)
    n_lights = sum(len(l.get("lights", [])) for l in lms)
    print(f"[Lyris] {len(lms)} landmarks, {n_parts} parts, {n_lights} lights -> {OUT} "
          f"({os.path.getsize(OUT) // 1024} KB)")
    houses = sum(1 for l in lms if l["kind"] == "district" for p in l["parts"] if p["n"].endswith("_Walls"))
    print(f"[Lyris] Moonharbor: {houses} house blocks in {sum(1 for l in lms if l['kind'] == 'district')} districts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
