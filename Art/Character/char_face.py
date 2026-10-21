"""Face rig basics for the Lyris base character (T46): blinks, lid squint and widen, mouth open,
smiles and frowns, brow expressions, and the creator's expression presets built from them.

Like char_morphs, every shape is a warp of design space, so the same function moves the head
skin, the mouth interior, the brow cards and (through lash_upper_amount) the lash cards.

Lids slide over the eyeball: a lid vertex keeps its normalised distance from the eyeball
centre while it moves, so a closing upper lid wraps over the eye instead of cutting through it.
"""

import numpy as np

import char_morphs as cm
import char_shapes as cs

F = np.float64
SIDES = (("l", 1.0), ("r", -1.0))


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


# ----------------------------------------------------------------------------- lids

def meet_line(u):
    up, lo = cm.upper_curve(u), cm.lower_curve(u)
    return lo + 0.3 * (up - lo)


def lid_shift(V, side, upper, lower):
    """upper: 1 closes the upper lid down to the meeting line (negative opens it wider).
    lower: 1 lifts the lower lid up to the meeting line."""
    V = np.asarray(V, F)
    R = cs.eye_rot(side).astype(F)
    c = cs.EYE[side].astype(F)
    r = cs.EYE_R.astype(F)
    q = (V - c) @ R
    u, d, v = q[:, 0], q[:, 1], q[:, 2]
    up, lo = cm.upper_curve(u), cm.lower_curve(u)
    meet = lo + 0.3 * (up - lo)
    off_u = v - up
    wu = (1 - smoothstep(0.0, 1.8, off_u)) * (off_u > -0.12)
    off_l = lo - v
    wl = (1 - smoothstep(0.0, 1.0, off_l)) * (off_l > -0.12)
    along = 1 - smoothstep(cs.EYE_W * 0.98, cs.EYE_W * 1.5, np.abs(u))
    near = (np.abs(v) < 4.0) & (d < 1.2)
    dv = (-(up - meet) * upper * wu + (meet - lo) * lower * wl) * along * near
    v2 = v + dv
    rn2 = (u / r[0]) ** 2 + (d / r[1]) ** 2 + (v / r[2]) ** 2
    inner = rn2 - (u / r[0]) ** 2 - (v2 / r[2]) ** 2
    d2 = np.where((d < 0) & (inner > 0) & (dv != 0), -np.sqrt(np.clip(inner, 0, None)) * r[1], d)
    q2 = np.stack([u, d2, v2], axis=1)
    return (q2 - q) @ R.T


# ----------------------------------------------------------------------------- mouth

def mouth_line(x):
    u = np.clip(np.asarray(x, F) / cs.MOUTH_HALF, -1, 1)
    return cs.MOUTH[2] - 0.02 - 0.06 * u * u


def jaw_weight(V):
    """1 on the lower lip, chin and jaw; 0 above the mouth line. Sharp across the parted lips,
    soft beyond the mouth corners."""
    x, y, z = V[:, 0], V[:, 1], V[:, 2]
    ax = np.abs(x)
    line = mouth_line(x)
    eps = 0.03 + smoothstep(cs.MOUTH_HALF * 0.9, cs.MOUTH_HALF + 1.6, ax) * 1.4
    w = smoothstep(line, line - eps, z)
    w = w * (1 - smoothstep(-0.5, 2.5, y)) * smoothstep(143.0, 146.0, z)
    return w


JAW_PIVOT = np.array([0.0, 0.6, 154.6])


def mouth_open(V, N, amount=1.0):
    w = jaw_weight(V)
    D = cm.rot_delta(V, JAW_PIVOT, (1, 0, 0), 13.0 * amount, w)
    up = smoothstep(cs.MOUTH[2] - 0.05, cs.MOUTH[2] + 0.4, V[:, 2]) * cm.bump(V, cs.MOUTH + (0, 0, 0.35), (1.5, 1.8, 0.7), snap=False)
    D += cm.move(up, (0, 0, 0.08 * amount))
    narrow = cm.bump(V, cs.MOUTH, (cs.MOUTH_HALF + 0.6, 2.0, 1.2), snap=False)
    D[:, 0] += -0.08 * amount * V[:, 0] * narrow
    return D


def smile_side(V, N, s, amount=1.0):
    corner = np.array([s * cs.MOUTH_HALF, cs.MOUTH[1] + 0.25, float(mouth_line(cs.MOUTH_HALF))])
    w = cm.bump(V, corner, (1.1, 1.8, 0.95), snap=False)
    D = cm.move(w, (0.26 * s * amount, 0.2 * amount, 0.45 * amount))
    cheek = cm.bump(V, (s * 2.7, -6.6, 153.4), (2.2, 2.4, 1.9), snap=False)
    D += cm.push(N, cheek, 0.16 * amount) + cm.move(cheek, (0, 0, 0.14 * amount))
    return D


def frown(V, N, amount=1.0):
    D = np.zeros_like(V)
    for _, s in SIDES:
        corner = np.array([s * cs.MOUTH_HALF, cs.MOUTH[1] + 0.25, float(mouth_line(cs.MOUTH_HALF))])
        w = cm.bump(V, corner, (1.0, 1.7, 0.9), snap=False)
        D += cm.move(w, (-0.06 * s * amount, 0.04 * amount, -0.22 * amount))
    return D


def press(V, N, amount=1.0):
    """Lips pressed a little thinner (Determined)."""
    w = cm.bump(V, cs.MOUTH, (cs.MOUTH_HALF + 0.3, 1.4, 0.75), snap=False)
    above = V[:, 2] > mouth_line(V[:, 0])
    D = np.zeros_like(V)
    D[:, 2] = np.where(above, -0.06, 0.06) * w * amount
    D[:, 1] += 0.06 * w * amount
    return D


# ----------------------------------------------------------------------------- brows

def brow_raise(V, N, side, amount=1.0):
    return cm.move(cm.brow_w(V, side), (0, 0, 0.55 * amount))


def brow_inner_up(V, N, amount=1.0):
    D = np.zeros_like(V)
    for side, s in SIDES:
        inner = cm.bump(V, cm.BROW_C[side] - (1.6 * s, 0, 0), (1.7, 2.4, 1.3), snap=False)
        D += cm.move(inner, (0, 0, 0.45 * amount))
    return D


def brow_furrow(V, N, amount=1.0):
    D = np.zeros_like(V)
    for side, s in SIDES:
        inner = cm.bump(V, cm.BROW_C[side] - (1.5 * s, 0, 0), (1.8, 2.4, 1.3), snap=False)
        D += cm.move(inner, (-0.22 * s * amount, -0.05 * amount, -0.32 * amount))
    return D


# ----------------------------------------------------------------------------- base shapes and presets

def base_shapes():
    """name -> (fn(V, N) -> D, upper-lid amounts (l, r) for the lashes)."""
    out = {}
    for side, s in SIDES:
        S = side.upper()
        out[f"Eye_Blink_{S}"] = (lambda V, N, side=side: lid_shift(V, side, 1.0, 1.0),
                                 (1.0, 0.0) if side == "l" else (0.0, 1.0))
        out[f"Eye_Squint_{S}"] = (lambda V, N, side=side: lid_shift(V, side, 0.18, 0.55),
                                  (0.18, 0.0) if side == "l" else (0.0, 0.18))
        out[f"Eye_Wide_{S}"] = (lambda V, N, side=side: lid_shift(V, side, -0.12, -0.25),
                                (-0.12, 0.0) if side == "l" else (0.0, -0.12))
        out[f"Mouth_Smile_{S}"] = (lambda V, N, s=s: smile_side(V, N, s), (0.0, 0.0))
        out[f"Brow_Raise_{S}"] = (lambda V, N, side=side: brow_raise(V, N, side), (0.0, 0.0))
    out["Mouth_Smile"] = (lambda V, N: smile_side(V, N, 1.0) + smile_side(V, N, -1.0), (0.0, 0.0))
    out["Mouth_Open"] = (lambda V, N: mouth_open(V, N), (0.0, 0.0))
    out["Mouth_Frown"] = (lambda V, N: frown(V, N), (0.0, 0.0))
    out["Mouth_Press"] = (lambda V, N: press(V, N), (0.0, 0.0))
    out["Brow_InnerUp"] = (lambda V, N: brow_inner_up(V, N), (0.0, 0.0))
    out["Brow_Furrow"] = (lambda V, N: brow_furrow(V, N), (0.0, 0.0))
    return out


# Expression presets (design/character_creator.md 9.6 and the Expression parts in 4.11):
# weights of the base shapes above. Each preset is also exported as its own morph `Expr_<Name>`
# so the creator can play one with a single weight.
PRESETS = {
    "Calm": {"Mouth_Smile": 0.18},
    "Bright": {"Mouth_Smile": 1.0, "Eye_Squint_L": 0.55, "Eye_Squint_R": 0.55, "Mouth_Open": 0.28,
               "Brow_Raise_L": 0.25, "Brow_Raise_R": 0.25},
    "Laugh": {"Mouth_Smile": 1.0, "Eye_Squint_L": 0.9, "Eye_Squint_R": 0.9, "Mouth_Open": 0.8,
              "Brow_Raise_L": 0.35, "Brow_Raise_R": 0.35},
    "Wry": {"Mouth_Smile_L": 0.85, "Mouth_Frown": 0.15, "Brow_Raise_L": 0.6, "Eye_Squint_R": 0.35},
    "Shy": {"Mouth_Smile": 0.4, "Brow_InnerUp": 0.7, "Eye_Blink_L": 0.3, "Eye_Blink_R": 0.3},
    "Surprised": {"Eye_Wide_L": 1.0, "Eye_Wide_R": 1.0, "Brow_Raise_L": 1.0, "Brow_Raise_R": 1.0,
                  "Mouth_Open": 0.5},
    "Sleepy": {"Eye_Blink_L": 0.6, "Eye_Blink_R": 0.6, "Brow_InnerUp": 0.2, "Mouth_Open": 0.08},
    "Dreamy": {"Eye_Blink_L": 0.35, "Eye_Blink_R": 0.35, "Mouth_Smile": 0.35, "Brow_InnerUp": 0.3},
    "Determined": {"Brow_Furrow": 1.0, "Eye_Squint_L": 0.3, "Eye_Squint_R": 0.3, "Mouth_Press": 1.0,
                   "Mouth_Frown": 0.25},
}


def expression_morphs(V, N, with_presets=True):
    """All face rig morphs evaluated on these vertices (design space): {name: D}."""
    shapes = base_shapes()
    base = {k: fn(V, N) for k, (fn, _) in shapes.items()}
    out = dict(base)
    if with_presets:
        for name, mix in PRESETS.items():
            D = np.zeros_like(V)
            for k, w in mix.items():
                D = D + base[k] * w
            out[f"Expr_{name}"] = D
    return out


def lash_upper_amounts():
    """name -> (upper lid amount left, right) for every face rig morph, for the lash cards."""
    shapes = base_shapes()
    out = {k: amt for k, (_, amt) in shapes.items()}
    for name, mix in PRESETS.items():
        l = sum(shapes[k][1][0] * w for k, w in mix.items())
        r = sum(shapes[k][1][1] * w for k, w in mix.items())
        out[f"Expr_{name}"] = (l, r)
    return out


def brow_only(name):
    return name.startswith("Brow_")
