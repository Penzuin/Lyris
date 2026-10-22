"""Offline preview of the world terrain look (T50): approximates M_LyrisWorldTerrain_v2 in numpy.

    python Art/World/preview_terrain_look.py              # whole world + the three close-ups (~5 min)
    python Art/World/preview_terrain_look.py --only world # or moonharbor / saltreach / north

Needs the full bake (Art/World/tiles), the biome maps (bake_biome_maps.py) and the painted textures
(paint_world_textures.py). It evaluates the same formulas and constants as the material
(Content/Python/lyris_world_terrain.py: LOOK, scales, strengths) on the baked heights, then lights them
with a simple golden-hour sun and sky, height-field shadows and a stand-in sea, and writes:

    Art/World/preview_look.jpg              the whole world from above (12 m per pixel, map light from the NW)
    Art/World/preview_moonharbor.jpg        2 km close-ups at 1 m: a 3/4 view in the game's golden-hour
    Art/World/preview_saltreach.jpg         sun (lyris_build_world: yaw 215, 14 degrees up) with the same
    Art/World/preview_north.jpg             2 km seen from above in the corner

Only a preview: Unreal's lighting, fog, sea and foliage will differ; the colours, the biome layout, the
rock on slopes, shores and seabed are the material's own.
"""

import argparse
import json
import math
import os
import sys
import time

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as nd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "Content", "Python"))
import lyris_world_terrain as L  # noqa: E402

TILES = os.path.join(HERE, "tiles")
BIOME = os.path.join(HERE, "biome")
TEXDIR = os.path.join(HERE, "textures")

# Close-ups: centre (UE metres; +X east, +Y south), view heading (degrees from +X toward +Y), label.
CLOSEUPS = {
    "moonharbor": ((150.0, -2300.0), 110.0, "Moonharbor and its bay"),
    "saltreach": ((-5450.0, 3600.0), 110.0, "Saltreach badlands and the West Volcano"),
    "north": ((-1450.0, -5650.0), -40.0, "The snowy north"),
}
GAME_SUN = (215.0, 14.0)  # lyris_build_world sky(): DirectionalLight yaw 215, pitch -14


def lin(hex_str):
    return np.array(L.srgb_to_linear(hex_str), np.float32)


def to_srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def aces(x):
    return np.clip((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0, 1)


def sat(x):
    return np.clip(x, 0.0, 1.0)


def mix(a, b, t):
    """lerp; a scalar-per-pixel t (H, W) is broadcast over colour channels."""
    t = np.asarray(t, np.float32)
    if t.ndim >= 1 and t.shape[-1] not in (1, 3):
        t = t[..., None]
    return a + (b - a) * t


# ----------------------------------------------------------------------------- textures with mips


class Tex:
    def __init__(self, path, wrap=True):
        a = np.asarray(Image.open(path).convert("RGBA"), np.float32) / 255.0
        self.levels = [a]
        while min(a.shape[:2]) > 1:
            h, w = a.shape[0] // 2 * 2, a.shape[1] // 2 * 2
            a = a[:h, :w].reshape(h // 2, 2, w // 2, 2, 4).mean(axis=(1, 3))
            self.levels.append(a)
        self.wrap = wrap

    def sample(self, u, v, footprint):
        """Bilinear sample at UV (any shape); footprint = texels per output pixel (picks the mip)."""
        lv = int(np.clip(round(math.log2(max(footprint, 1.0))), 0, len(self.levels) - 1))
        t = self.levels[lv]
        h, w = t.shape[:2]
        x = u * w - 0.5
        y = v * h - 0.5
        x0 = np.floor(x)
        y0 = np.floor(y)
        fx = (x - x0)[..., None].astype(np.float32)
        fy = (y - y0)[..., None].astype(np.float32)
        x0 = x0.astype(np.int64)
        y0 = y0.astype(np.int64)
        if self.wrap:
            xa, xb, ya, yb = x0 % w, (x0 + 1) % w, y0 % h, (y0 + 1) % h
        else:
            xa, xb = np.clip(x0, 0, w - 1), np.clip(x0 + 1, 0, w - 1)
            ya, yb = np.clip(y0, 0, h - 1), np.clip(y0 + 1, 0, h - 1)
        top = t[ya, xa] * (1 - fx) + t[ya, xb] * fx
        bot = t[yb, xa] * (1 - fx) + t[yb, xb] * fx
        return top * (1 - fy) + bot * fy


class Look:
    """numpy twin of lyris_world_terrain._graph (base colour only)."""

    def __init__(self, biome_dir=BIOME):
        with open(os.path.join(biome_dir, "biome_maps.json")) as f:
            bm = json.load(f)
        self.lo, self.size, self.res = bm["world_min_ue"], bm["world_size_ue"], bm["res"]
        # Moonharbor's maps (T55) start at different X and Y; the world's start at the same value.
        self.lo_x, self.lo_y = bm.get("world_min_ue_xy", [self.lo, self.lo])
        self.bA = Tex(os.path.join(biome_dir, "T_LyrisBiomeA.png"), wrap=False)
        self.bB = Tex(os.path.join(biome_dir, "T_LyrisBiomeB.png"), wrap=False)
        self.dA = Tex(os.path.join(TEXDIR, "T_LyrisDetailA.png"))
        self.dB = Tex(os.path.join(TEXDIR, "T_LyrisDetailB.png"))
        self.noise = Tex(os.path.join(TEXDIR, "T_LyrisWorldNoise.png"))
        self.c = {k: lin(v) for k, v in L.LOOK.items()}

    def albedo(self, X, Y, Z, N, px_m, view_cm=0.0):
        """X, Y in UE cm, Z in metres above the sea, N (...,3) unit normals, px_m metres per pixel,
        view_cm the camera distance (for the distance fades)."""
        c = self.c
        cm = px_m * 100.0
        up = N[..., 2]
        up01 = sat(up * 0.5 + 0.5)
        steep = sat(up * L.STEEP[0] + L.STEEP[1])
        flat_top = sat(up * L.FLAT_TOP[0] + L.FLAT_TOP[1])
        giant = self.noise.sample(X * L.GIANT, Y * L.GIANT, cm * L.GIANT * 512)
        k = L.NOISE_CHAIN
        macro = self.noise.sample(X * L.MACRO + giant[..., 0] * k, Y * L.MACRO + giant[..., 1] * k, cm * L.MACRO * 512)
        ou, ov = macro[..., 2] * k, macro[..., 3] * k
        mid_a = self.noise.sample(X * L.MID + ou, Y * L.MID + ov, cm * L.MID * 512)
        cb, sb = math.cos(math.radians(L.MID_ANGLE)), math.sin(math.radians(L.MID_ANGLE))
        k2 = L.MID * L.MID_RATIO
        mid_b = self.noise.sample((X * cb - Y * sb) * k2 - ou, (X * sb + Y * cb) * k2 - ov, cm * k2 * 512)
        mid = (mid_a + mid_b) * 0.7071 + (0.5 - 0.7071)

        k = 2.0 * L.WARP_M * 100.0 / self.size
        u = (X - self.lo_x) / self.size + (mid[..., 0] - 0.5) * k
        v = (Y - self.lo_y) / self.size + (mid[..., 1] - 0.5) * k
        fp = cm / (self.size / self.res)
        bA, bB = self.bA.sample(u, v, fp), self.bB.sample(u, v, fp)
        nA = mid - 0.5
        nB = mid[..., [2, 3, 0, 1]] - 0.5
        sA = bA + nA * L.EDGE_NOISE
        sB = bB + nB * L.EDGE_NOISE
        mx = np.maximum(sA.max(-1), sB.max(-1))[..., None]
        wA = sat((sA - mx) / L.BLEND_DEPTH + 1.0) + 0.002
        wB = sat((sB - mx) / L.BLEND_DEPTH + 1.0) + 0.002
        tot = (wA.sum(-1) + wB.sum(-1))[..., None]
        wA, wB = wA / tot, wB / tot
        w = dict(zip(("Grass", "Forest", "Sand", "Rock"), np.moveaxis(wA, -1, 0)))
        w.update(zip(("Snow", "Badlands", "Salt", "Volcanic"), np.moveaxis(wB, -1, 0)))

        un = X * L.NEAR + (mid[..., 0] - 0.5) * L.DETAIL_WARP[0]
        vn = Y * L.NEAR + (mid[..., 1] - 0.5) * L.DETAIL_WARP[0]
        ca, sa = math.cos(math.radians(L.FAR_ANGLE)), math.sin(math.radians(L.FAR_ANGLE))
        uf = (X * ca - Y * sa) * L.FAR + (mid[..., 2] - 0.5) * L.DETAIL_WARP[1]
        vf = (X * sa + Y * ca) * L.FAR + (mid[..., 3] - 0.5) * L.DETAIL_WARP[1]

        def detail(tex, coeffs):
            near = tex.sample(un, vn, cm * L.NEAR * 512)
            far = tex.sample(uf, vf, cm * L.FAR * 512)
            kn, kf = np.array(coeffs["near"], np.float32), np.array(coeffs["far"], np.float32)
            return (near * 2 * kn + 1 - kn) * (far * 2 * kf + 1 - kf), near
        dA, dAn = detail(self.dA, L.DETAIL_A)
        dB, _ = detail(self.dB, L.DETAIL_B)
        d = {"grass": dA[..., 0], "sand": dA[..., 1], "seabed": dA[..., 3],
             "snow": dB[..., 0], "strata": dB[..., 1], "salt": dB[..., 2], "basalt": dB[..., 3]}

        Zc = Z * 100.0
        tw = np.abs(N) ** 4
        tw = tw / tw.sum(-1, keepdims=True)
        fpz = cm * L.NEAR * 512
        sx = self.dA.sample(Y * L.NEAR, Zc * L.NEAR, fpz)[..., 2]
        sy = self.dA.sample(X * L.NEAR, Zc * L.NEAR, fpz)[..., 2]
        cliff = sx * tw[..., 0] + sy * tw[..., 1] + dAn[..., 2] * tw[..., 2]
        kr = L.DETAIL_A["near"][2]
        rock_detail = cliff * 2 * kr + 1 - kr
        rock = mix(c["rock_shade"], c["rock_lit"], up01) * rock_detail[..., None]

        m_r, m_g, m_b, m_a = np.moveaxis(macro, -1, 0)
        lowland = sat(Z * (-1.0 / 50.0) + 1.0)
        lush = sat(m_r * 1.5 - 0.45 + lowland * 0.45)
        grass = mix(c["grass"], c["grass_shade"], lush * 0.55)
        meadow = sat(m_b * 2.2 - 1.2)
        grass = mix(grass, c["meadow_light"], meadow * 0.35)
        dry = sat(m_g * 2.5 - 1.4 + Z / 140.0 - 0.5)
        grass = mix(grass, c["path"], dry * 0.5) * d["grass"][..., None]
        forest = mix(c["forest"], c["forest_deep"], sat(m_r * 1.2 - 0.1) * 0.6) * d["grass"][..., None]
        sand = mix(c["sand"], c["sand_pale"], m_b)
        dunes = sat(Z / 12.0 - 0.25) * (m_g * 0.3 + 0.15)
        sand = mix(sand, c["path"], dunes) * d["sand"][..., None]
        rock_flat = mix(rock, grass, flat_top)
        snow_shade = mix(c["snow_cool"], c["rock_shade"], L.SNOW_SHADE)
        snow = mix(snow_shade, c["snow"], sat(up * 4.0 - 3.0)) * d["snow"][..., None] * L.SNOW_ALBEDO
        strata = np.mod(Z / L.STRATA_M + mid[..., 2] * 0.6, 1.0)
        # Bands fade with distance (PixelDepth in the material); a top-down grid of px_m stands in for it.
        near_bands = sat((L.STRATA_FADE_CM[1] - view_cm) / (L.STRATA_FADE_CM[1] - L.STRATA_FADE_CM[0]))
        near_bands = near_bands * sat(up * -L.STRATA_SLOPE[1] + L.STRATA_SLOPE[0] * L.STRATA_SLOPE[1])
        bad = mix(c["badlands"], c["badlands_red"], sat(strata * 6.0 - 3.6) * near_bands)
        bad = mix(bad, c["path"], sat(strata * -5.0 + 0.75) * near_bands)
        bad = mix(bad, c["rock_lit"], L.BADLANDS_SOFTEN) * d["strata"][..., None]
        salt = mix(c["salt"], c["salt_pale"], m_a) * d["salt"][..., None]
        volc = mix(c["volcanic"], c["volcanic_warm"], m_r)
        volc = mix(volc, c["rock_shade"], 0.3) * d["basalt"][..., None]

        land = (grass * w["Grass"][..., None] + forest * w["Forest"][..., None] + sand * w["Sand"][..., None]
                + rock_flat * w["Rock"][..., None] + snow * w["Snow"][..., None] + bad * w["Badlands"][..., None]
                + salt * w["Salt"][..., None] + volc * w["Volcanic"][..., None])
        cliff_col = mix(rock, bad * rock_detail[..., None], w["Badlands"])
        cliff_col = mix(cliff_col, volc * rock_detail[..., None], w["Volcanic"])
        base = mix(land, cliff_col, steep)

        shore_line = mid[..., 3] * 1.5 + L.SHORE_M - 0.75
        shore = sat((shore_line - Z) / L.SHORE_FADE_M) * (1 - steep) * (1 - w["Salt"])
        base = mix(base, sand, shore)
        wet = sat(np.abs(Z - L.WET_M[0]) * (-1.0 / L.WET_M[1]) + 1.0)
        base = base * (1 - 0.18 * wet)[..., None]

        under = sat(Z * -2.0)
        depth = sat(Z * (-1.0 / L.SEABED_DEEP_M))
        bed = c["sand"] * d["seabed"][..., None]
        base = mix(base, bed, under * (1 - steep * 0.6))
        deep = np.sqrt(depth)
        deep_col = mix(c["shallows"], c["sea_trough"], deep)
        base = mix(base, base * deep_col, under * (deep * 0.65 + 0.35))
        base = base * (1 - 0.55 * deep * under)[..., None]

        base = base * mix(c["tone_warm"], c["tone_cool"], giant[..., 3])
        base = base * (m_a * 0.12 + 0.94)[..., None]
        return base.astype(np.float32)


# ----------------------------------------------------------------------------- heights, water


def manifest():
    with open(os.path.join(TILES, "terrain_manifest.json")) as f:
        return json.load(f)


def tile(name, tx, ty):
    return np.asarray(Image.open(os.path.join(TILES, f"World_{name}_x{tx}_y{ty}.png")))


def world_heights(down):
    m = manifest()
    n, t = m["tiles_x"], m["tile_resolution"]
    per = t // down
    out = np.zeros((n * per, n * per), np.float32)
    for ty in range(n):
        for tx in range(n):
            a = tile("Height", tx, ty).astype(np.float32)
            out[ty * per:(ty + 1) * per, tx * per:(tx + 1) * per] = a.reshape(per, down, per, down).mean(axis=(1, 3))
    return (out - 16384.0) / 128.0


def region_heights(x0, y0, size_m, res_m):
    """Heights (m) on a grid of res_m cells covering [x0, x0+size) x [y0, y0+size) (UE metres)."""
    m = manifest()
    mpv, t = m["metres_per_vertex"], m["tile_resolution"]
    cx, cy = m["location_corner"][0] / 100.0, m["location_corner"][1] / 100.0
    i0, i1 = int(math.floor((x0 - cx) / mpv)) - 3, int(math.ceil((x0 + size_m - cx) / mpv)) + 4
    j0, j1 = int(math.floor((y0 - cy) / mpv)) - 3, int(math.ceil((y0 + size_m - cy) / mpv)) + 4
    raw = np.zeros((j1 - j0, i1 - i0), np.float32)
    total = m["total_resolution"]
    for ty in range(max(j0, 0) // t, min(j1, total - 1) // t + 1):
        for tx in range(max(i0, 0) // t, min(i1, total - 1) // t + 1):
            a = tile("Height", tx, ty)
            gi0, gj0 = tx * t, ty * t
            si0, si1 = max(i0, gi0), min(i1, gi0 + t)
            sj0, sj1 = max(j0, gj0), min(j1, gj0 + t)
            raw[sj0 - j0:sj1 - j0, si0 - i0:si1 - i0] = a[sj0 - gj0:sj1 - gj0, si0 - gi0:si1 - gi0]
    raw = (raw - 16384.0) / 128.0
    n = int(round(size_m / res_m))
    xs = (x0 + (np.arange(n) + 0.5) * res_m - cx) / mpv - i0
    ys = (y0 + (np.arange(n) + 0.5) * res_m - cy) / mpv - j0
    gy, gx = np.meshgrid(ys, xs, indexing="ij")
    return nd.map_coordinates(raw, [gy, gx], order=3, mode="nearest").astype(np.float32)


def water_levels(x0, y0, size_m, res_m, shape):
    """Lake and river water surface (m) on the grid, NaN where there is none (sea handled separately)."""
    m = manifest()
    img = Image.new("F", (shape[1], shape[0]), float("nan"))
    dr = ImageDraw.Draw(img)

    def px(p):
        return ((p[0] / 100.0 - x0) / res_m, (p[1] / 100.0 - y0) / res_m)
    for river in m.get("rivers", []):
        pts = river["points_ue"]
        width = max(1, int(round(river["width_m"] / res_m)))
        for a, b in zip(pts[:-1], pts[1:]):
            dr.line([px(a), px(b)], fill=float((a[2] + b[2]) / 200.0), width=width)
    for lake in m.get("lakes", []):
        poly = [px(p) for p in lake["outline_ue"]]
        dr.polygon(poly, fill=float(lake["level_m"]))
    return np.asarray(img, np.float32)


def normals(h, res_m):
    gy, gx = np.gradient(h, res_m)
    n = np.stack([-gx, -gy, np.ones_like(h)], -1)
    return (n / np.linalg.norm(n, axis=-1, keepdims=True)).astype(np.float32)


def sun_vector(yaw_deg, elev_deg):
    """Unit vector toward the sun for a DirectionalLight with this yaw and pitch -elev (UE axes)."""
    y, e = math.radians(yaw_deg), math.radians(elev_deg)
    return np.array([-math.cos(e) * math.cos(y), -math.cos(e) * math.sin(y), math.sin(e)], np.float32)


def shadows(h, res_m, sun, max_m):
    """1 lit, 0 in shadow: marches toward the sun over the height field (grid rows = +Y)."""
    hor = math.hypot(sun[0], sun[1])
    dx, dy, rise = sun[0] / hor, sun[1] / hor, sun[2] / hor
    lit = np.ones_like(h, bool)
    H, W = h.shape
    dist = res_m
    while dist < max_m:
        ox, oy = int(round(dx * dist / res_m)), int(round(dy * dist / res_m))
        if abs(ox) >= W or abs(oy) >= H:
            break
        src = h[max(oy, 0):H + min(oy, 0), max(ox, 0):W + min(ox, 0)]
        dst = (slice(max(-oy, 0), H + min(-oy, 0)), slice(max(-ox, 0), W + min(-ox, 0)))
        lit[dst] &= src <= h[dst] + dist * rise
        dist += res_m * (1 if dist < 200 else 2 if dist < 600 else 4)
    return nd.gaussian_filter(lit.astype(np.float32), 1.2)


def shade(albedo, h, N, res_m, sun, water, sky_scale=1.0):
    """Golden-hour light: warm sun with shadows, lavender sky fill, soft occlusion; then a stand-in sea
    and lakes over the water. Returns linear radiance."""
    sun_col = lin("FFE3BE") * 3.2
    sky_col = np.array([0.42, 0.47, 0.66], np.float32) * sky_scale
    sh = shadows(h, res_m, sun, max_m=1600.0)
    ndl = np.clip((N * sun).sum(-1), 0, 1) * sh
    blur = nd.gaussian_filter(h, 25.0 / res_m)
    ao = np.clip(1.0 - np.maximum(blur - h, 0) / 40.0, 0.65, 1.0)
    sky = (0.6 + 0.4 * N[..., 2]) * ao
    light = sun_col * ndl[..., None] + sky_col * sky[..., None]
    rad = albedo * light
    # Sea (the real one is its own mesh) and lakes/rivers: palette water over the ground.
    level = np.where(np.isnan(water), 0.0, water)
    depth = level - h
    wet = depth > 0
    if wet.any():
        dpt = np.clip(depth, 0, None)
        shallows, sea, trough = lin("7FD0D6"), lin("2E8A9C"), lin("1F6A80")
        wcol = mix(shallows, sea, sat(dpt / 4.0))
        wcol = mix(wcol, trough, sat((dpt - 8.0) / 40.0) * 0.6)
        flat_ndl = max(float(sun[2]), 0.0)
        wrad = wcol * (sun_col * flat_ndl * sh[..., None] * 0.9 + sky_col * 1.1)
        alpha = (0.55 + 0.4 * sat(dpt / 10.0))[..., None]
        foam = (sat(1.0 - dpt / 0.35) * 0.35 * (wet & np.isnan(water)))[..., None]  # surf on the sea only
        rad = np.where(wet[..., None], mix(rad, wrad, alpha) + foam * sun_col * 0.12, rad)
    return rad.astype(np.float32), np.maximum(h, level)


# ----------------------------------------------------------------------------- 3/4 view (voxel space)


def oblique(rad, surf, x0, y0, res_m, centre, heading_deg, W=1280, H=720, fov=58.0, back_m=1000.0, height_m=280.0):
    """Front-to-back height-field render of the radiance grid (classic voxel-space)."""
    hd = math.radians(heading_deg)
    fwd = np.array([math.cos(hd), math.sin(hd)])
    right = np.array([-math.sin(hd), math.cos(hd)])  # +90 degrees toward +Y; screen right
    cam = np.array(centre) - fwd * back_m
    gi = lambda x, y: ((y - y0) / res_m - 0.5, (x - x0) / res_m - 0.5)  # noqa: E731
    cj, ci = gi(*cam)
    ground = nd.map_coordinates(surf, [[cj], [ci]], order=1, mode="nearest")[0]
    cam_z = max(ground, 0.0) + height_m
    focal = W / 2 / math.tan(math.radians(fov) / 2)
    horizon = H * 0.16
    cols = np.arange(W) - W / 2 + 0.5
    ybuf = np.full(W, H, np.int64)
    ev_col, ev_top, ev_len, ev_rgb = [], [], [], []
    sky_top, sky_hor = np.array([0.36, 0.45, 0.72]), np.array([1.25, 0.95, 0.72])
    far_m = 3200.0
    d = 20.0
    while d < far_m:
        wx = cam[0] + fwd[0] * d + right[0] * cols / focal * d
        wy = cam[1] + fwd[1] * d + right[1] * cols / focal * d
        j, i = gi(wx, wy)
        inside = (i >= 0) & (j >= 0) & (i < surf.shape[1] - 1) & (j < surf.shape[0] - 1)
        hz = nd.map_coordinates(surf, [j, i], order=1, mode="nearest")
        y = horizon + (cam_z - hz) / d * focal
        yt = np.maximum(np.ceil(y).astype(np.int64), 0)
        draw = inside & (yt < ybuf)
        if draw.any():
            rgb = np.stack([nd.map_coordinates(rad[..., k], [j[draw], i[draw]], order=1, mode="nearest")
                            for k in range(3)], -1)
            haze = sat((d - 1200.0) / 2400.0)[None, None] * 0.3
            rgb = mix(rgb, sky_hor * 0.85, haze)
            ev_col.append(np.nonzero(draw)[0])
            ev_top.append(yt[draw])
            ev_len.append(ybuf[draw] - yt[draw])
            ev_rgb.append(rgb)
            ybuf[draw] = yt[draw]
        d += max(0.35, d * 0.0025)
    img = np.zeros((H, W, 3), np.float32)
    t = (np.arange(H) / H)[:, None]
    img[:] = (sky_top * (1 - t * 2.2).clip(0, 1) + sky_hor * (t * 2.2).clip(0, 1))[:, None, :] * np.ones((1, W, 1))
    if ev_col:
        col, top, ln, rgb = (np.concatenate(a) for a in (ev_col, ev_top, ev_len, ev_rgb))
        keep = ln > 0
        col, top, ln, rgb = col[keep], top[keep], ln[keep], rgb[keep]
        starts = np.repeat(np.cumsum(ln) - ln, ln)
        rows = np.repeat(top, ln) + (np.arange(ln.sum()) - starts)
        img[rows, np.repeat(col, ln)] = np.repeat(rgb, ln, axis=0)
    return img


def finish(rad, exposure=0.85):
    return (to_srgb(aces(rad * exposure)) * 255).round().astype(np.uint8)


# ----------------------------------------------------------------------------- the previews


def evaluate(look, h, x0, y0, res_m, view_cm, chunk=256):
    """Albedo on the grid, in row chunks to keep memory small."""
    H, W = h.shape
    N = normals(h, res_m)
    out = np.zeros((H, W, 3), np.float32)
    xs = (x0 + (np.arange(W) + 0.5) * res_m) * 100.0
    for r in range(0, H, chunk):
        rr = slice(r, min(r + chunk, H))
        ys = (y0 + (np.arange(rr.start, rr.stop) + 0.5) * res_m) * 100.0
        Y, X = np.meshgrid(ys, xs, indexing="ij")
        out[rr] = look.albedo(X, Y, h[rr], N[rr], res_m, view_cm=view_cm)
    return out, N


def render_world(look, path):
    t0 = time.time()
    down = 8
    h = world_heights(down)
    m = manifest()
    res = m["metres_per_vertex"] * down
    x0 = y0 = m["location_corner"][0] / 100.0
    alb, N = evaluate(look, h, x0, y0, res, view_cm=1e9)  # seen from far above
    water = water_levels(x0, y0, res * h.shape[0], res, h.shape)
    sun = sun_vector(45.0, 35.0)  # a map light from the north-west, so relief reads as relief
    rad, _ = shade(alb, h, N, res, sun, water)
    Image.fromarray(finish(rad, 0.9)).save(path, quality=90)
    print(f"[Lyris] {path} ({time.time() - t0:.0f} s)")


def render_closeup(look, key, path, size_m=2000.0, pad_m=700.0, res_m=1.0):
    t0 = time.time()
    (cx, cy), heading, label = CLOSEUPS[key]
    span = size_m + 2 * pad_m
    x0, y0 = cx - span / 2, cy - span / 2
    h = region_heights(x0, y0, span, res_m)
    alb, N = evaluate(look, h, x0, y0, res_m, view_cm=130000.0)  # about the 3/4 camera's distance
    water = water_levels(x0, y0, span, res_m, h.shape)
    sun = sun_vector(*GAME_SUN)
    rad, surf = shade(alb, h, N, res_m, sun, water)
    view = oblique(rad, surf, x0, y0, res_m, (cx, cy), heading)
    img = Image.fromarray(finish(view))
    # Inset: the same 2 km from above (north up), with the same material and light.
    p = int(pad_m / res_m)
    top = finish(rad[p:p + int(size_m / res_m), p:p + int(size_m / res_m)])
    inset = Image.fromarray(top).resize((300, 300), Image.LANCZOS)
    frame = Image.new("RGB", (306, 306), (247, 238, 220))
    frame.paste(inset, (3, 3))
    img.paste(frame, (img.width - 318, img.height - 318))
    ImageDraw.Draw(img).text((16, 14), f"{label}  (2 km; golden-hour sun, preview)", fill=(250, 244, 232))
    img.save(path, quality=90)
    print(f"[Lyris] {path} ({time.time() - t0:.0f} s)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=["world"] + list(CLOSEUPS), help="render just one preview")
    args = ap.parse_args()
    look = Look()
    if args.only in (None, "world"):
        render_world(look, os.path.join(HERE, "preview_look.jpg"))
    for key in CLOSEUPS:
        if args.only in (None, key):
            render_closeup(look, key, os.path.join(HERE, f"preview_{key}.jpg"))


if __name__ == "__main__":
    main()
