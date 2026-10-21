"""Painted textures for the Lyris base character.

Skin, hair and cloth are painted from 3D position: each mesh's UV layout is rasterised into a
position map (the 3D point and normal under every texel), then the paint is a function of
position, so strokes cross UV seams cleanly. Eyes, brows and lashes are painted straight in
their own simple UV layouts.

Conventions follow Art/TestIsland/paint_textures.py: soft, low-contrast, warm lights and cool
shadows, no photographic detail. Skin base colour is a neutral, lightly warm near-white so the
appearance material's `SkinTone` parameter can multiply it to any swatch; hair, eye and cloth
textures are greyscale detail plus masks, with a palette-tinted preview copy for review.
"""

import numpy as np
from PIL import Image, ImageFilter

import char_shapes as cs

F = np.float64


def hexrgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=F) / 255.0


# Palette (Content/Python/lyris_build_harbor.py PALETTE and design/character_creator.md swatches)
SAIL, SAND, OAT = hexrgb("F7EEDC"), hexrgb("F1E9DC"), hexrgb("D9C7A5")
WOOD, DARKWOOD, CLAY = hexrgb("8B5A3A"), hexrgb("4A2A1C"), hexrgb("36221A")
TERRACOTTA, REDBAND, GOLD, BRASS = hexrgb("C8643A"), hexrgb("C8443A"), hexrgb("E3AE45"), hexrgb("B8893A")
LEAF, SHALLOWS, MOONGLASS, DEEPSEA = hexrgb("6E8A3A"), hexrgb("7FD0D6"), hexrgb("7AC0E6"), hexrgb("2F4E6B")
SKIN_BASE = hexrgb("F4E8DE")   # neutral, lightly warm; multiplied by SkinTone in the material
ROSE = hexrgb("D98A7A")


# ----------------------------------------------------------------------------- noise

class Noise:
    def __init__(self, seed):
        r = np.random.default_rng(seed)
        self.g = r.normal(size=(64, 64, 64)).astype(np.float32)

    def __call__(self, P, scale):
        q = np.asarray(P, F) / scale
        i = np.floor(q).astype(int)
        f = q - i
        f = f * f * (3 - 2 * f)
        out = 0
        for dx in (0, 1):
            for dy in (0, 1):
                for dz in (0, 1):
                    w = (f[:, 0] if dx else 1 - f[:, 0]) * (f[:, 1] if dy else 1 - f[:, 1]) * \
                        (f[:, 2] if dz else 1 - f[:, 2])
                    out = out + w * self.g[(i[:, 0] + dx) % 64, (i[:, 1] + dy) % 64, (i[:, 2] + dz) % 64]
        return out

    def fbm(self, P, scale, octaves=3):
        t, a, s = 0, 1.0, scale
        for _ in range(octaves):
            t = t + a * self(P, s)
            a *= 0.5
            s *= 0.5
        return t * 0.6


NOISE = Noise(7)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def blob(P, c, r):
    q = (P - np.asarray(c, F)) / np.asarray(r, F)
    return np.clip(1 - (q * q).sum(1), 0, 1) ** 1.5


# ----------------------------------------------------------------------------- position maps

def rasterise(uv, tris, attrs, size):
    """Barycentric rasterisation of a UV layout. attrs: (V, k) per-vertex values.
    Returns (size, size, k) image and a coverage mask."""
    out = np.zeros((size, size, attrs.shape[1]), dtype=F)
    cov = np.zeros((size, size), dtype=bool)
    px = uv * size - 0.5
    px[:, 1] = size - 1 - (uv[:, 1] * size - 0.5)
    for t in tris:
        a, b, c = px[t[0]], px[t[1]], px[t[2]]
        x0, x1 = int(np.floor(min(a[0], b[0], c[0]))), int(np.ceil(max(a[0], b[0], c[0])))
        y0, y1 = int(np.floor(min(a[1], b[1], c[1]))), int(np.ceil(max(a[1], b[1], c[1])))
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, size - 1), min(y1, size - 1)
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12:
            continue
        l0 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / den
        l1 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / den
        l2 = 1 - l0 - l1
        inside = (l0 >= -0.02) & (l1 >= -0.02) & (l2 >= -0.02)
        if not inside.any():
            continue
        yy, xx = ys[inside], xs[inside]
        val = (l0[inside, None] * attrs[t[0]] + l1[inside, None] * attrs[t[1]] + l2[inside, None] * attrs[t[2]])
        out[yy, xx] = val
        cov[yy, xx] = True
    return out, cov


def dilate(img, cov, steps=8):
    """Pushes painted texels out into the UV gutters so mips and seams do not bleed."""
    img = img.copy()
    cov = cov.copy()
    for _ in range(steps):
        acc = np.zeros_like(img)
        cnt = np.zeros(cov.shape)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            sh = np.roll(np.roll(cov, dy, 0), dx, 1)
            acc += np.roll(np.roll(img, dy, 0), dx, 1) * sh[..., None]
            cnt += sh
        grow = (~cov) & (cnt > 0)
        img[grow] = acc[grow] / cnt[grow, None]
        cov = cov | grow
    return img


class PosMap:
    def __init__(self, uv, tris, pos, nrm, size):
        data, cov = rasterise(uv, tris, np.concatenate([pos, nrm], axis=1), size)
        self.size, self.cov = size, cov
        self.P = data[cov][:, :3]
        n = data[cov][:, 3:]
        self.N = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-8)

    def image(self, values, steps=10):
        k = values.shape[1]
        img = np.zeros((self.size, self.size, k))
        img[self.cov] = values
        img = dilate(img, self.cov, steps)
        return img


def to_u8(img):
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


def save(img, path):
    Image.fromarray(to_u8(img)).save(path, optimize=True)


def soften(img, r=1.2):
    im = Image.fromarray(to_u8(img))
    return np.asarray(im.filter(ImageFilter.GaussianBlur(r)), dtype=F) / 255.0


# ----------------------------------------------------------------------------- skin

def freckle_field(P, density=1.0):
    """Soft dots: a jittered grid in 3D, kept on the nose and cheek tops (SunKissed)."""
    cell = 0.42
    q = P / cell
    i = np.floor(q)
    best = np.full(len(P), 9.0)
    rng_size = []
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                c = i + (dx, dy, dz)
                h = np.sin(c @ np.array([12.9898, 78.233, 37.719])) * 43758.5453
                j = np.stack([np.modf(h * k)[0] for k in (1.0, 1.7, 2.3)], axis=1) % 1.0
                keep = (np.modf(h * 3.1)[0] % 1.0) < 0.55 * density
                d = np.linalg.norm(q - (c + j), axis=1)
                d = np.where(keep, d, 9.0)
                best = np.minimum(best, d)
    dots = 1 - smoothstep(0.12, 0.26, best)
    region = blob(P, (0, -9.0, 156.0), (5.6, 4.0, 2.6)) + blob(P, (3.6, -6.2, 155.5), (2.6, 3.4, 2.0)) \
        + blob(P, (-3.6, -6.2, 155.5), (2.6, 3.4, 2.0))
    return np.clip(dots * np.clip(region * 1.3, 0, 1), 0, 1)


def paint_skin(pm, part):
    """Returns (base colour, preview colour, masks RGBA) for 'head', 'body' or 'ears'.
    Masks: R rosiness (cheeks, nose, ears, knuckles, knees, elbows), G freckles (SunKissed set),
    B lips, A blush (Blush.Apples)."""
    P, N = pm.P, pm.N
    n = NOISE.fbm(P, 6.0)
    up = N[:, 2]
    # value: a touch lighter on top planes and cheek tops, a touch deeper and cooler underneath
    val = 1.0 + 0.035 * up + 0.02 * n
    base = SKIN_BASE[None, :] * val[:, None]
    under = np.clip(-up, 0, 1)
    base = base * (1 - 0.06 * under[:, None]) + hexrgb("C9B4C8")[None, :] * 0.06 * under[:, None]
    ros = np.zeros(len(P))
    lips = np.zeros(len(P))
    blush = np.zeros(len(P))
    frk = np.zeros(len(P))
    if part == "head":
        for s in (1, -1):
            ros += blob(P, (3.7 * s, -6.6, 153.6), (2.4, 2.4, 1.8))
            blush += blob(P, (3.6 * s, -6.8, 153.4), (1.9, 2.0, 1.4))
            # soft warm shadow round the eye socket, a little pink at the inner corner
            e = cs.EYE["l" if s > 0 else "r"].astype(F)
            ring = blob(P, e + (0.0, -0.6, 0.4), (2.9, 2.0, 2.3)) * (1 - blob(P, e, (1.7, 1.4, 1.2)))
            base = base * (1 - 0.07 * ring[:, None]) + hexrgb("D7A6A0")[None, :] * 0.07 * ring[:, None]
        ros += 0.8 * blob(P, cs.NOSE_TIP.astype(F) + (0, 0.5, 0), (1.3, 1.2, 1.1))
        ros += 0.5 * blob(P, cs.CHIN.astype(F) + (0, 0, 0.2), (1.8, 1.6, 1.2))
        mouth = cs.MOUTH.astype(F)
        lu = blob(P, mouth + (0, 0.0, 0.3), (1.45, 1.2, 0.42))
        ll = blob(P, mouth + (0, 0.1, -0.38), (1.25, 1.2, 0.48))
        lips = np.clip((lu + ll) * 2.2, 0, 1) * (N[:, 1] < 0.2)
        lips = smoothstep(0.15, 0.6, lips)
        base = base * (1 - 0.28 * lips[:, None]) + ROSE[None, :] * 0.28 * lips[:, None]
        # parting line between the lips, painted not modelled
        part_line = np.exp(-((P[:, 2] - (mouth[2] - 0.02 + 0.06 * (P[:, 0] / 1.3) ** 2)) / 0.07) ** 2) \
            * (1 - smoothstep(1.0, 1.45, np.abs(P[:, 0]))) * (P[:, 1] < -7.0)
        base = base * (1 - 0.35 * part_line[:, None]) + hexrgb("9A5A55")[None, :] * 0.35 * part_line[:, None]
        frk = freckle_field(P)
        # nostrils: a soft warm shadow
        for s in (1, -1):
            nos = blob(P, (0.55 * s, -9.2, 154.0), (0.45, 0.6, 0.32))
            base = base * (1 - 0.3 * nos[:, None]) + hexrgb("B07F72")[None, :] * 0.3 * nos[:, None]
    elif part == "body":
        for s in (1, -1):
            hand = cs.HAND["l" if s > 0 else "r"]
            wrist, d = hand[0], hand[1]
            ros += 0.8 * blob(P, wrist + d * 8.0, (3.0, 3.0, 3.0))          # knuckles
            ros += 0.6 * blob(P, cs.J[f"calf_{'l' if s > 0 else 'r'}"] + (0, -3.5, 0), (3.5, 3, 3.5))  # knees
            ros += 0.5 * blob(P, cs.J[f"lowerarm_{'l' if s > 0 else 'r'}"] + (0, 2.5, 0), (3, 3, 3))  # elbows
    elif part == "ears":
        ros += 0.9 * np.ones(len(P))
    ros = np.clip(ros, 0, 1)
    preview = base * (1 - 0.25 * ros[:, None]) + ROSE[None, :] * 0.25 * ros[:, None]
    masks = np.stack([ros, frk, lips, np.clip(blush, 0, 1)], axis=1)
    return pm.image(base), pm.image(preview), pm.image(masks)


# ----------------------------------------------------------------------------- hair

def paint_hair(pm, top_z, bottom_z, flow="vertical"):
    """Greyscale strand detail (R), root-to-tip gradient (G), shine band (B), highlight streaks (A)."""
    P, N = pm.P, pm.N
    c = np.array([0, 1.3, 160.0])
    q = P - c
    ang = np.arctan2(q[:, 0], q[:, 1])
    if flow == "braid":
        coord = P[:, 0] * 2.1 + P[:, 2] * 0.9
    else:
        coord = ang * 14.0 + 0.6 * NOISE(P, 2.0)
    strands = 0.5 + 0.5 * np.sin(coord) * (0.6 + 0.4 * np.sin(coord * 2.7 + 1.3))
    detail = 0.78 + 0.22 * strands + 0.06 * NOISE.fbm(P, 1.5)
    # soft occlusion deeper in the hair: darker towards the head
    detail *= 0.86 + 0.14 * np.clip(N[:, 2] * 0.5 + 0.6, 0, 1)
    grad = np.clip((top_z - P[:, 2]) / max(top_z - bottom_z, 1.0), 0, 1)
    # storybook shine ribbon: a band round the crown, broken by the strands
    band_z = top_z - 5.5
    shine = np.exp(-((P[:, 2] - band_z - 0.8 * np.sin(ang * 3)) / 0.9) ** 2) * np.clip(N[:, 2] + 0.4, 0, 1)
    shine *= 0.6 + 0.4 * np.sin(coord * 0.5 + 0.5) ** 2
    streak = smoothstep(0.55, 0.85, 0.5 + 0.5 * np.sin(ang * 5.0 + 0.4 * NOISE(P, 3.0)))
    img = np.stack([detail, grad, np.clip(shine, 0, 1), streak], axis=1)
    return pm.image(img)


def hair_preview(mask, root, tip, gs=0.7, soft=0.5):
    det, grad, shine, _ = [mask[..., i] for i in range(4)]
    t = smoothstep(gs - soft * 0.5, gs + soft * 0.5, grad)
    col = root[None, None, :] * (1 - t[..., None]) + tip[None, None, :] * t[..., None]
    col = col * det[..., None]
    col = col + (np.array([1.0, 0.96, 0.88]) - col) * (0.35 * shine[..., None])
    return col


# ----------------------------------------------------------------------------- cloth

def paint_outfit(pm, piece_ids):
    """Plain traveller: oat shirt, wood-brown trousers, dark leather belt and boots, brass
    buckle. piece_ids: per-texel piece index (0 shirt, 1 trousers, 2 belt, 3 boots).
    Returns (preview colour, detail grey, masks RGBA: R primary cloth, G secondary cloth,
    B trim/metal, A leather)."""
    P, N = pm.P, pm.N
    n = NOISE.fbm(P, 5.0)
    weave = 0.5 + 0.5 * np.sin(P[:, 0] * 9.0 + P[:, 2] * 0.7) * np.sin(P[:, 2] * 9.0 + P[:, 1] * 0.5)
    detail = 0.9 + 0.05 * n + 0.04 * weave
    # painted fold shadows: soft vertical strokes from the noise, stronger at the waist and knees
    folds = NOISE(P * np.array([1.0, 1.0, 0.25]), 2.5)
    detail *= 1.0 - 0.05 * np.clip(folds, 0, 1)
    detail *= 0.93 + 0.07 * np.clip(N[:, 2] * 0.5 + 0.6, 0, 1)
    pid = piece_ids
    col = np.zeros((len(P), 3))
    shirt, trousers, belt, boots = (pid == 0), (pid == 1), (pid == 2), (pid == 3)
    col[shirt] = OAT * 1.06
    col[trousers] = WOOD * 0.95
    col[belt] = DARKWOOD * 1.1
    col[boots] = WOOD * 0.85
    # hem and cuff stitching: a dashed trim line
    stitch = np.zeros(len(P))
    hem = np.exp(-((P[:, 2] - 125.0) / 0.18) ** 2) * shirt * 0  # (shirt is tucked: no hem line)
    dash = (np.sin(np.arctan2(P[:, 0], P[:, 1]) * 90) > 0.2)
    stitch += hem * dash
    buckle = belt & (np.abs(P[:, 0]) < 2.2) & (P[:, 1] < -6) & (np.abs(P[:, 2] - 99.6) < 1.5)
    ring = buckle & ((np.abs(P[:, 0]) > 1.3) | (np.abs(P[:, 2] - 99.6) > 0.85))
    col[ring] = BRASS * 1.15
    sole = boots & (P[:, 2] < 2.6)
    col[sole] = DARKWOOD
    cuffb = boots & (P[:, 2] > 26.5)
    col[cuffb] = WOOD * 1.05
    col = col * (1 - 0.6 * stitch[:, None]) + SAIL[None, :] * 0.6 * stitch[:, None]
    col = col * detail[:, None]
    masks = np.stack([shirt.astype(F), trousers.astype(F), (ring | (stitch > 0.3)).astype(F),
                      (belt | boots).astype(F) * (~ring)], axis=1)
    return pm.image(col), pm.image(detail[:, None].repeat(3, 1)), pm.image(masks)


# ----------------------------------------------------------------------------- eyes

def paint_eye(size=512, iris_hex="3F9A93", iris_r=0.62, pupil_r=0.26):
    """Eye texture in the eyeball's front projection: (u, v) in -1..1 covers the eye opening.
    Returns (preview colour, masks RGBA: R iris, G pupil, B catchlight, A iris detail grey)."""
    y, x = np.mgrid[0:size, 0:size]
    u = (x + 0.5) / size * 2 - 1
    v = 1 - (y + 0.5) / size * 2
    # the iris is a tall soft oval, as in painted storybook faces
    ru = u / iris_r
    rv = (v + 0.02) / (iris_r * 1.08)
    r = np.sqrt(ru * ru + rv * rv)
    ang = np.arctan2(rv, ru)
    iris = 1 - smoothstep(0.96, 1.02, r)
    pupil = 1 - smoothstep(pupil_r / iris_r - 0.04, pupil_r / iris_r + 0.02, r)
    # iris detail: darker rim and top (lid shadow), a warm light pooling at the bottom
    rays = 0.5 + 0.5 * np.sin(ang * 22 + 2 * np.sin(ang * 5))
    det = 0.62 + 0.18 * rays * smoothstep(0.35, 0.9, r)
    det *= 1 - 0.5 * smoothstep(0.78, 1.0, r)                           # limbal ring
    det *= 1 - 0.35 * smoothstep(0.0, 0.9, rv) * (rv > 0)               # top shadow
    det += 0.45 * np.exp(-((rv + 0.55) / 0.3) ** 2) * (1 - smoothstep(0.6, 0.95, r))  # bottom glow
    catch = np.exp(-(((u - 0.22) / 0.11) ** 2 + ((v - 0.28) / 0.13) ** 2) * 1.0)
    catch = smoothstep(0.35, 0.6, catch) + 0.6 * smoothstep(0.4, 0.6, np.exp(-(((u + 0.22) / 0.05) ** 2 + ((v + 0.3) / 0.05) ** 2)))
    sclera = SAIL * (1 - 0.12 * smoothstep(0.2, 1.0, v)[..., None])     # lid shadow on the white
    ic = hexrgb(iris_hex)
    iris_col = ic[None, None, :] * np.clip(det, 0, 1.3)[..., None]
    col = sclera * (1 - iris[..., None]) + iris_col * iris[..., None]
    col = col * (1 - pupil[..., None]) + hexrgb("1E1820")[None, None, :] * pupil[..., None]
    col = col + (1 - col) * np.clip(catch, 0, 1)[..., None]
    masks = np.stack([iris, pupil, np.clip(catch, 0, 1), np.clip(det, 0, 1)], axis=-1)
    return col, masks


# ----------------------------------------------------------------------------- cards

def paint_brow(w=512, h=128, thick=1.0):
    """Brow card alpha: tapered feathered strokes (u along the brow inner->outer, v across)."""
    y, x = np.mgrid[0:h, 0:w]
    u = (x + 0.5) / w
    v = 1 - (y + 0.5) / h
    centre = 0.5 + 0.08 * np.sin(u * np.pi) - 0.05
    width = (0.30 * (1 - u) + 0.12 * u) * thick
    rng = np.random.default_rng(3)
    a = np.zeros((h, w))
    for k in range(70):
        u0 = rng.uniform(0, 0.95)
        L = rng.uniform(0.08, 0.16)
        off = rng.normal(0, 0.45)
        tt = np.clip((u - u0) / L, 0, 1)
        inside = (u >= u0) & (u <= u0 + L)
        cy = 0.5 + 0.08 * np.sin(u0 * np.pi) - 0.05 + off * (0.3 * (1 - u0) + 0.12 * u0) * thick * 0.7 + tt * 0.05
        line = np.exp(-((v - cy) / (0.03 + 0.02 * (1 - u0))) ** 2) * inside * np.sin(np.pi * tt) ** 0.5
        a = np.maximum(a, line)
    body = np.exp(-((v - centre) / (width * 0.75)) ** 2) * smoothstep(0.0, 0.08, u) * (1 - smoothstep(0.85, 1.0, u))
    a = np.clip(0.75 * body + 0.6 * a, 0, 1)
    rgb = np.ones((h, w, 3)) * (0.75 + 0.25 * (1 - a))[..., None]
    return np.concatenate([rgb, a[..., None]], axis=-1)


def paint_lash(w=512, h=128):
    """Upper lash card: a solid lash line and a few bold storybook lashes, longer at the outer
    corner (u: inner->outer, v: root->tip)."""
    y, x = np.mgrid[0:h, 0:w]
    u = (x + 0.5) / w
    v = 1 - (y + 0.5) / h
    line = (1 - smoothstep(0.16, 0.24, v)) * smoothstep(0.0, 0.05, u) * (1 - smoothstep(0.97, 1.0, u))
    a = line.copy()
    centres = [0.40, 0.55, 0.68, 0.79, 0.88, 0.95]
    for i, c in enumerate(centres):
        L = 0.45 + 0.5 * i / (len(centres) - 1)
        tt = np.clip(v / L, 0, 1)
        cx = c + 0.05 * tt ** 1.5
        width = 0.022 * (1 - tt) ** 0.8 + 0.002
        stroke = np.exp(-((u - cx) / width) ** 2) * (v < L)
        a = np.maximum(a, stroke)
    rgb = np.ones((h, w, 3)) * 0.9
    return np.concatenate([rgb, np.clip(a, 0, 1)[..., None]], axis=-1)



def paint_eye_cm(size, eye_r, iris_hex="3F9A93", iris_cm=1.22, pupil_cm=0.5, iris_up=0.18):
    """Eye texture in the eyeball's front projection, sized in centimetres: u = x / eye_r.x,
    v = z / eye_r.z (both -1..1). The iris is a tall painted oval, set a little high so the
    upper lid overlaps it (the storybook look). Returns (preview colour, masks RGBA:
    R iris, G pupil, B catchlight, A iris detail grey). The material tints by IrisColorL/R,
    ScleraColor, and scales the iris with IrisScale / PupilScale around the iris centre."""
    y, x = np.mgrid[0:size, 0:size]
    u = ((x + 0.5) / size * 2 - 1) * float(eye_r[0])
    v = (1 - (y + 0.5) / size * 2) * float(eye_r[2])
    ru = u / iris_cm
    rv = (v - iris_up) / (iris_cm * 1.12)
    r = np.sqrt(ru * ru + rv * rv)
    ang = np.arctan2(rv, ru)
    iris = 1 - smoothstep(0.95, 1.0, r)
    pr = np.sqrt((u / pupil_cm) ** 2 + ((v - iris_up) / (pupil_cm * 1.15)) ** 2)
    pupil = 1 - smoothstep(0.92, 1.0, pr)
    rays = 0.5 + 0.5 * np.sin(ang * 26 + 2.5 * np.sin(ang * 5))
    det = 0.66 + 0.14 * rays * smoothstep(0.45, 0.9, r)
    det *= 1 - 0.55 * smoothstep(0.80, 1.0, r)                       # soft limbal ring
    det *= 1 - 0.45 * np.clip(rv, 0, 1) ** 1.2                        # the upper lid's shadow
    det += 0.55 * np.exp(-((rv + 0.62) / 0.28) ** 2) * (1 - smoothstep(0.55, 0.95, r))   # light pools low
    c1 = np.exp(-(((u - 0.36) / 0.26) ** 2 + ((v - iris_up - 0.42) / 0.30) ** 2))
    c2 = np.exp(-(((u + 0.32) / 0.11) ** 2 + ((v - iris_up + 0.52) / 0.11) ** 2))
    catch = np.clip(smoothstep(0.45, 0.62, c1) + 0.8 * smoothstep(0.45, 0.62, c2), 0, 1)
    shade = smoothstep(0.1, 1.2, v / float(eye_r[2]) + 0.35)
    sclera = SAIL[None, None, :] * (1 - 0.16 * shade[..., None]) + hexrgb("C8C4D8")[None, None, :] * 0.16 * shade[..., None]
    ic = hexrgb(iris_hex)
    iris_col = ic[None, None, :] * np.clip(det, 0, 1.4)[..., None]
    col = sclera * (1 - iris[..., None]) + iris_col * iris[..., None]
    col = col * (1 - pupil[..., None]) + hexrgb("1E1820")[None, None, :] * pupil[..., None]
    col = col + (1 - col) * catch[..., None]
    masks = np.stack([iris, pupil, catch, np.clip(det, 0, 1)], axis=-1)
    return np.clip(col, 0, 1), masks
