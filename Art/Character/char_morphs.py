"""Morph targets for the Lyris base character, as analytic warps of space.

Every morph is a function (V, N) -> D: vertex positions and normals (cm, build space) to
offsets. Because they are warps of space rather than edits of one mesh, the same morph can be
evaluated on the head, the eyes, brows, lashes and hair so they move together, and on both
body frames and the outfit.

Sizes: weight 1.0 of each morph is the guardrail end of its slider in
design/character_creator.md (section 3 Limit column and section 6), so the Player lane can use
the spec's weights as they are. Two-way sliders have `<Name>_Pos` (the slider's high end) and
`<Name>_Neg` (its low end) morphs; one-sided sliders (0..1) have a single morph.

Mirrored space: L and R morphs are built from the same definition with X flipped, so the same
value on both sides gives a symmetric face (spec section 1).
"""

import numpy as np

import char_rig as rig
import char_shapes as cs

F = np.float64


def _v(*a):
    return np.array(a, dtype=F)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


_SNAP = {}


def on_head(c):
    """Moves a face landmark onto the head surface (cached), so a bump is never centred
    inside or in front of the skin after the head shape is tuned."""
    key = tuple(np.round(np.asarray(c, F), 4))
    if key not in _SNAP:
        from char_sdf import project
        p = np.asarray(c, F)[None, :]
        _SNAP[key] = project(cs.head_sdf, p, iters=8)[0]
    return _SNAP[key]


def bump(V, c, r, snap=None):
    """Compact smooth bump: 1 at c, 0 outside the ellipsoid of radii r. Head-region centres
    (in front of the ears, above the neck) are snapped onto the skin unless snap=False."""
    c = np.asarray(c, F)
    r = np.asarray(r, F)
    if snap is None:
        snap = c[2] > 145.5 and c[1] < -1.0 and max(r) < 6.0
    if snap:
        c = on_head(c)
    q = (V - c) / r
    d2 = (q * q).sum(1)
    return np.clip(1.0 - d2, 0.0, 1.0) ** 2


def plateau(V, c, r_in, r_out, scale=(1, 1, 1)):
    q = (V - np.asarray(c, F)) / np.asarray(scale, F)
    d = np.sqrt((q * q).sum(1))
    return 1.0 - smoothstep(r_in, r_out, d)


def rodrigues(axis, deg):
    k = np.asarray(axis, F)
    k = k / np.linalg.norm(k)
    a = np.radians(deg)
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(a) * K + (1 - np.cos(a)) * K @ K


def rot_delta(V, pivot, axis, deg, w):
    R = rodrigues(axis, deg)
    p = np.asarray(pivot, F)
    return ((V - p) @ R.T + p - V) * w[:, None]


def scale_delta(V, pivot, k, w):
    return (V - np.asarray(pivot, F)) * (np.asarray(k, F) - 1.0) * w[:, None]


def move(w, d):
    return w[:, None] * np.asarray(d, F)[None, :]


def push(N, w, amount):
    return N * (w * amount)[:, None]


SIDES = (("l", 1.0), ("r", -1.0))


def m(c, s):
    c = np.asarray(c, F)
    return _v(c[0] * s, c[1], c[2])


def seam(V):
    """Head morphs fade out above the neck seam so head and body always meet."""
    return smoothstep(143.5, 146.5, V[:, 2])


# ----------------------------------------------------------------------------- registry

class Morph:
    def __init__(self, name, slider, end, fn, group, note=""):
        self.name, self.slider, self.end, self.fn, self.group, self.note = name, slider, end, fn, group, note


FACE, EYE, BROW, BODY, EAR, LASH, HAIR = "face", "eye", "brow", "body", "ear", "lash", "hair"
REG = []


def two_way(name, slider, group, pos, neg, note=""):
    REG.append(Morph(f"{name}_Pos", slider, "high", pos, group, note))
    REG.append(Morph(f"{name}_Neg", slider, "low", neg, group, note))


def one_way(name, slider, group, fn, note=""):
    REG.append(Morph(name, slider, "0..1", fn, group, note))


def sided(name, slider, group, make, two=True, note=""):
    """make(side, s, sign) -> fn. Registers <name>_L / _R (with _Pos/_Neg if two)."""
    for side, s in SIDES:
        sid = slider + side.upper()
        nm = f"{name}_{side.upper()}"
        if two:
            two_way(nm, sid, group, make(side, s, 1.0), make(side, s, -1.0), note)
        else:
            one_way(nm, sid, group, make(side, s, 1.0), note)


def both_sides(fn_side):
    """A symmetric morph made of the same edit on both sides."""
    def fn(V, N):
        return sum(fn_side(V, N, side, s) for side, s in SIDES)
    return fn


def signed(make):
    return make(1.0), make(-1.0)


# ----------------------------------------------------------------------------- face: Shape

def front(V, y0=3.0):
    return 1.0 - smoothstep(y0 - 2.0, y0 + 2.0, V[:, 1])


def mk_face_width(k):
    return lambda V, N: _xscale(V, bump(V, (0, -3, 153), (10, 10, 8.5)) * front(V), k)


def _xscale(V, w, k):
    D = np.zeros_like(V)
    D[:, 0] = V[:, 0] * k * w
    return D


two_way("Face_Width", "Face.Width", FACE, mk_face_width(0.08), mk_face_width(-0.08))


def mk_face_length(dz):
    def fn(V, N):
        w = smoothstep(156.5, 149.5, V[:, 2]) * bump(V, (0, -4, 150), (9, 9, 8)) * front(V, 2)
        return move(w, (0, 0, dz))
    return fn


two_way("Face_Length", "Face.Length", FACE, mk_face_length(-0.9), mk_face_length(0.7))


def face_round_pos(V, N):
    w = sum(bump(V, m((4.0, -3.8, 151.0), s), (3.0, 4.0, 3.4)) for _, s in SIDES)
    return push(N, w, 0.45) + push(N, bump(V, (0, -6.6, 148.6), (3.0, 2.5, 2.0)), 0.2)


def face_round_neg(V, N):
    hollow = sum(bump(V, m((3.9, -4.4, 152.6), s), (2.4, 3.0, 2.4)) for _, s in SIDES)
    corner = sum(bump(V, m((5.0, -0.8, 150.6), s), (1.8, 2.6, 1.8)) for _, s in SIDES)
    chin = bump(V, (0, -6.8, 148.1), (2.4, 2.0, 1.6))
    return push(N, hollow, -0.32) + push(N, corner, 0.28) + push(N, chin, -0.12)


two_way("Face_Round", "Face.Roundness", FACE, face_round_pos, face_round_neg)


def mk_side_move(c, r, d, normal=0.0):
    """Moves a mirrored region: d = (outward, y, z) in cm, plus a push along the normal."""
    def fn(V, N):
        out = np.zeros_like(V)
        for _, s in SIDES:
            w = bump(V, m(c, s), r)
            out += move(w, (d[0] * s, d[1], d[2])) + push(N, w, normal)
        return out
    return fn


two_way("Temple_Width", "Face.TempleWidth", FACE,
        mk_side_move((6.7, -2.5, 160.5), (2.6, 3.6, 3.6), (0.6, 0, 0)),
        mk_side_move((6.7, -2.5, 160.5), (2.6, 3.6, 3.6), (-0.55, 0, 0)))
two_way("Cheek_Full", "Face.CheekFullness", FACE,
        mk_side_move((3.7, -5.6, 153.0), (2.7, 2.7, 2.6), (0.1, 0, 0), 0.55),
        mk_side_move((3.7, -5.6, 153.0), (2.7, 2.7, 2.6), (-0.1, 0, 0), -0.5))
two_way("Cheekbone_Height", "Face.CheekboneHeight", FACE,
        mk_side_move((4.4, -4.6, 155.4), (2.6, 3.0, 2.2), (0, 0, 0.5), 0.12),
        mk_side_move((4.4, -4.6, 155.4), (2.6, 3.0, 2.2), (0, 0, -0.5)))
two_way("Cheekbone_Width", "Face.CheekboneWidth", FACE,
        mk_side_move((4.9, -4.4, 155.4), (2.6, 3.0, 2.3), (0.55, 0, 0)),
        mk_side_move((4.9, -4.4, 155.4), (2.6, 3.0, 2.3), (-0.5, 0, 0)))
two_way("Cheekbone_Prom", "Face.CheekboneProminence", FACE,
        mk_side_move((4.4, -7.2, 155.6), (1.9, 2.3, 1.5), (0, 0, 0), 0.4),
        mk_side_move((4.4, -7.2, 155.6), (1.9, 2.3, 1.5), (0, 0, 0), -0.3))
one_way("Cheek_Hollow", "Face.CheekHollow", FACE,
        mk_side_move((4.6, -4.5, 152.2), (2.1, 2.6, 2.0), (-0.15, 0, 0), -0.5),
        "weight 1 = 'slight hollow'; spec caps the slider at morph 0.5")
two_way("Jaw_Width", "Face.JawWidth", FACE,
        mk_side_move((4.7, -2.0, 150.4), (2.8, 4.6, 3.2), (0.75, 0, 0)),
        mk_side_move((4.7, -2.0, 150.4), (2.8, 4.6, 3.2), (-0.7, 0, 0)))
two_way("Jaw_Angle", "Face.JawAngle", FACE,
        mk_side_move((5.0, -0.7, 150.4), (1.9, 2.5, 1.9), (0.1, 0, -0.1), 0.42),
        mk_side_move((5.0, -0.7, 150.4), (1.9, 2.5, 1.9), (-0.1, 0, 0.1), -0.38))
two_way("Jaw_Height", "Face.JawHeight", FACE,
        mk_side_move((4.9, -1.2, 150.6), (2.5, 3.6, 2.6), (0, 0, 0.65)),
        mk_side_move((4.9, -1.2, 150.6), (2.5, 3.6, 2.6), (0, 0, -0.65)))


def mk_lower_face(c, r, d, extra=None):
    def fn(V, N):
        w = bump(V, c, r) * front(V, 1)
        out = move(w, d)
        if extra:
            out += extra(V, N, w)
        return out
    return fn


two_way("Jaw_Depth", "Face.JawDepth", FACE,
        mk_lower_face((0, -4, 149.4), (7.5, 7.5, 4.2), (0, -0.55, 0)),
        mk_lower_face((0, -4, 149.4), (7.5, 7.5, 4.2), (0, 0.55, 0)))
CHIN_C = _v(0, -6.4, 148.4)
two_way("Chin_Width", "Face.ChinWidth", FACE,
        lambda V, N: _xscale(V, bump(V, CHIN_C, (3.2, 3.0, 2.4), snap=False), 0.3),
        lambda V, N: _xscale(V, bump(V, CHIN_C, (3.2, 3.0, 2.4), snap=False), -0.25))
two_way("Chin_Length", "Face.ChinLength", FACE,
        mk_lower_face(CHIN_C + (0, 0, -0.4), (3.0, 3.2, 2.3), (0, -0.05, -0.65)),
        mk_lower_face(CHIN_C + (0, 0, -0.4), (3.0, 3.2, 2.3), (0, 0, 0.5)))
two_way("Chin_Depth", "Face.ChinDepth", FACE,
        mk_lower_face(CHIN_C, (2.8, 3.2, 2.4), (0, -0.6, -0.05)),
        mk_lower_face(CHIN_C, (2.8, 3.2, 2.4), (0, 0.55, 0.05)))
two_way("Chin_Point", "Face.ChinPoint", FACE,
        lambda V, N: _xscale(V, bump(V, (0, -6.3, 147.9), (2.8, 3.0, 1.9)), -0.28)
        + move(bump(V, (0, -6.6, 147.6), (1.4, 2.0, 1.2)), (0, -0.15, -0.25)),
        lambda V, N: _xscale(V, bump(V, (0, -6.3, 147.9), (2.8, 3.0, 1.9)), 0.18)
        + move(bump(V, (0, -6.6, 147.6), (1.4, 2.0, 1.2)), (0, 0.05, 0.15)))
one_way("Chin_Cleft", "Face.ChinCleft", FACE,
        lambda V, N: push(N, bump(V, (0, -7.2, 148.3), (0.5, 1.6, 0.9)), -0.25))
one_way("Cheek_Dimple", "Face.CheekDimples", FACE,
        mk_side_move((2.4, -7.2, 151.4), (0.55, 1.4, 0.6), (0, 0, 0), -0.22),
        "only shows in smile expressions in the spec; here it is a resting dimple")

# ----------------------------------------------------------------------------- face: Forehead


def mk_forehead_height(dz):
    def fn(V, N):
        w = smoothstep(160.5, 165.0, V[:, 2]) * bump(V, (0, -4.5, 167), (8.5, 7.0, 6.5)) * front(V, 1)
        return move(w, (0, 0, dz))
    return fn


two_way("Forehead_Height", "Forehead.Height", FACE, mk_forehead_height(0.5), mk_forehead_height(-0.45))
two_way("Forehead_Width", "Forehead.Width", FACE,
        lambda V, N: _xscale(V, bump(V, (0, -3, 164.5), (10, 8, 4.6), snap=False), 0.08),
        lambda V, N: _xscale(V, bump(V, (0, -3, 164.5), (10, 8, 4.6), snap=False), -0.07))


def mk_forehead_slope(k):
    def fn(V, N):
        w = bump(V, (0, -6.0, 165.5), (8.0, 5.5, 5.0)) * front(V, -1)
        D = np.zeros_like(V)
        D[:, 1] = k * np.clip(V[:, 2] - 161.0, 0, None) * w
        return D
    return fn


two_way("Forehead_Slope", "Forehead.Slope", FACE, mk_forehead_slope(0.16), mk_forehead_slope(-0.1))
two_way("Forehead_Round", "Forehead.Roundness", FACE,
        lambda V, N: push(N, bump(V, (0, -7.0, 165.0), (5.2, 4.2, 3.4)), 0.4),
        lambda V, N: push(N, bump(V, (0, -7.0, 165.0), (5.2, 4.2, 3.4)), -0.35))
two_way("BrowRidge_Prom", "Forehead.BrowRidge", FACE,
        mk_side_move((3.1, -7.3, 161.7), (2.7, 2.2, 1.15), (0, -0.05, 0), 0.32),
        mk_side_move((3.1, -7.3, 161.7), (2.7, 2.2, 1.15), (0, 0.05, 0), -0.25))

# ----------------------------------------------------------------------------- face: Eyes

EYE_W, EYE_HU, EYE_HL = 1.98, 1.42, 0.78


def eye_local(V, side):
    R = cs.eye_rot(side).astype(F)
    q = (V - cs.EYE[side].astype(F)) @ R
    return q, R


def upper_curve(u):
    t = np.clip(u / EYE_W, -1, 1)
    return EYE_HU * np.clip(1 - t * t, 0, 1) ** 0.62 * (1 - 0.10 * t) + 0.16 * t


def lower_curve(u):
    t = np.clip(u / EYE_W, -1, 1)
    return -EYE_HL * np.clip(1 - t * t, 0, 1) ** 0.85 + 0.16 * t


def eye_core(V, side):
    """1 over the eye, its lids and socket; fades out before the brow and cheek."""
    q, _ = eye_local(V, side)
    d = np.sqrt((q[:, 0] / 1.0) ** 2 + (q[:, 1] / 1.4) ** 2 + (q[:, 2] / 0.95) ** 2)
    return 1.0 - smoothstep(2.35, 3.8, d)


def mk_eye(op):
    """op(V, side, s, w) -> D for one eye; returns an L or R morph builder."""
    def make(side, s, sign):
        return lambda V, N: op(V, N, side, s, sign, eye_core(V, side))
    return make


def eye_size(V, N, side, s, sign, w):
    return scale_delta(V, cs.EYE[side], 1.15 if sign > 0 else 0.90, w)


sided("Eye_Size", "Eyes.Size", EYE, mk_eye(eye_size))


def eye_spacing(sign):
    def fn(V, N):
        return sum(move(eye_core(V, side), (0.4 * sign * s, 0, 0)) for side, s in SIDES)
    return fn


two_way("Eye_Spacing", "Eyes.Spacing", EYE, eye_spacing(1.0), eye_spacing(-1.0))
sided("Eye_Height", "Eyes.Height", EYE, mk_eye(lambda V, N, side, s, sign, w: move(w, (0, 0, 0.4 * sign))))


def eye_tilt(V, N, side, s, sign, w):
    R = cs.eye_rot(side).astype(F)
    axis = np.cross(R[:, 0], _v(0, 0, 1))      # turns the outer corner up
    return rot_delta(V, cs.EYE[side], axis, 12.0 * sign, w)


sided("Eye_Tilt", "Eyes.Tilt", EYE, mk_eye(eye_tilt))


def eye_depth(sign):
    def fn(V, N):
        out = np.zeros_like(V)
        for side, s in SIDES:
            R = cs.eye_rot(side).astype(F)
            out += move(eye_core(V, side), R[:, 1] * (0.35 if sign > 0 else -0.3))
        return out
    return fn


two_way("Eye_Depth", "Eyes.Depth", EYE, eye_depth(1.0), eye_depth(-1.0))


def eye_round(sign):
    ku, kv = (0.96, 1.14) if sign > 0 else (1.05, 0.88)

    def fn(V, N):
        out = np.zeros_like(V)
        for side, s in SIDES:
            q, R = eye_local(V, side)
            w = eye_core(V, side)
            dq = np.stack([q[:, 0] * (ku - 1), np.zeros(len(q)), q[:, 2] * (kv - 1)], axis=1) * w[:, None]
            out += dq @ R.T
        return out
    return fn


two_way("Eye_Round", "Eyes.Roundness", EYE, eye_round(1.0), eye_round(-1.0))


def lid_band(V, side, upper=True, width=0.55):
    q, R = eye_local(V, side)
    u, dep, v = q[:, 0], q[:, 1], q[:, 2]
    curve = upper_curve(u) if upper else lower_curve(u)
    off = (v - curve) if upper else (curve - v)
    # strongest at the lid edge, fading into the skin away from the eye, nothing behind it
    band = np.exp(-(np.clip(off, 0, None) / (width * 1.6)) ** 2) * (1 - smoothstep(-0.05, -0.45, off))
    along = 1.0 - smoothstep(EYE_W * 0.95, EYE_W * 1.45, np.abs(u))
    depth = 1.0 - smoothstep(0.3, 1.2, dep)
    return band * along * depth, q, R


def lid_upper(V, N, side, s, sign, w):
    band, q, R = lid_band(V, side, True)
    t = np.clip(q[:, 0] / EYE_W, -1, 1)
    shape = (1 - t * t) ** 0.5
    return move(band * shape, R[:, 2] * (0.22 if sign > 0 else -0.34))


sided("Lid_Upper", "Eyes.UpperLid", EYE, mk_eye(lid_upper))


def lid_crease(sign):
    def fn(V, N):
        out = np.zeros_like(V)
        for side, s in SIDES:
            q, R = eye_local(V, side)
            crease = upper_curve(q[:, 0] * 0.92) + 0.55
            w = np.exp(-((q[:, 2] - crease) / 0.2) ** 2) * (1 - smoothstep(EYE_W * 0.8, EYE_W * 1.3, np.abs(q[:, 0])))
            w *= 1 - smoothstep(0.0, 1.0, q[:, 1])
            out += push(N, w, -0.2 if sign > 0 else 0.14)
        return out
    return fn


two_way("Lid_Crease", "Eyes.LidCrease", EYE, lid_crease(1.0), lid_crease(-1.0))


def lid_lower(V, N, side, s, sign, w):
    band, q, R = lid_band(V, side, False, 0.45)
    t = np.clip(q[:, 0] / EYE_W, -1, 1)
    shape = (1 - t * t) ** 0.7
    return move(band * shape, R[:, 2] * (0.24 if sign > 0 else -0.2))


sided("Lid_Lower", "Eyes.LowerLid", EYE, mk_eye(lid_lower))


def eye_corner(inner):
    def op(V, N, side, s, sign, w):
        q, R = eye_local(V, side)
        u0 = -EYE_W if inner else EYE_W
        c = cs.EYE[side].astype(F) + R @ _v(u0, -0.3, 0.16 if not inner else -0.05)
        b = bump(V, c, (0.95, 1.6, 0.9), snap=False)
        if inner:
            d = R[:, 2] * 0.22 - R[:, 0] * 0.18 if sign > 0 else -R[:, 2] * 0.2 + R[:, 0] * 0.12
        else:
            d = R[:, 0] * 0.34 + R[:, 2] * 0.08 if sign > 0 else -R[:, 0] * 0.2 - R[:, 2] * 0.05
        return move(b, d)
    return op


sided("Eye_Inner", "Eyes.InnerCorner", EYE, mk_eye(eye_corner(True)))
sided("Eye_Outer", "Eyes.OuterCorner", EYE, mk_eye(eye_corner(False)))


def under_eye(V, N):
    out = np.zeros_like(V)
    for side, s in SIDES:
        q, R = eye_local(V, side)
        c = cs.EYE[side].astype(F) + R @ _v(0.1, -0.6, -1.35)
        out += push(N, bump(V, c, (1.7, 1.6, 0.65), snap=False), 0.25)
    return out


one_way("UnderEye_Full", "Eyes.UnderEyeFullness", EYE, under_eye)

# ----------------------------------------------------------------------------- face: Brows

BROW_C = {"l": _v(3.5, -7.4, 161.4), "r": _v(-3.5, -7.4, 161.4)}


def brow_w(V, side):
    return bump(V, BROW_C[side], (3.0, 2.4, 1.3))


def mk_brow(op):
    def make(side, s, sign):
        return lambda V, N: op(V, N, side, s, sign, brow_w(V, side))
    return make


sided("Brow_Height", "Brows.Height", BROW, mk_brow(lambda V, N, side, s, sign, w: move(w, (0, 0, 0.5 * sign))))


def brow_tilt(V, N, side, s, sign, w):
    axis = np.cross(_v(s, 0, 0), _v(0, 0, 1))
    return rot_delta(V, on_head(BROW_C[side]) - _v(0.3 * s, 0, 0), axis, 10.0 * sign, w)


sided("Brow_Tilt", "Brows.Tilt", BROW, mk_brow(brow_tilt))


def brow_arch(V, N, side, s, sign, w):
    mid = bump(V, BROW_C[side] + _v(0.7 * s, 0, 0.3), (1.4, 2.4, 1.1))
    if sign > 0:
        return move(mid, (0, 0, 0.32)) + move(w * (1 - mid), (0, 0, -0.06))
    return move(mid, (0, 0, -0.22))


sided("Brow_Arch", "Brows.Arch", BROW, mk_brow(brow_arch))


def brow_spacing(sign):
    def fn(V, N):
        return sum(move(brow_w(V, side), (0.35 * sign * s, 0, 0)) for side, s in SIDES)
    return fn


two_way("Brow_Spacing", "Brows.Spacing", BROW, brow_spacing(1.0), brow_spacing(-1.0))

# ----------------------------------------------------------------------------- face: Nose

TIP = cs.NOSE_TIP.astype(F) + _v(0, 0.7, 0.05)
BRIDGE = _v(0, -8.0, 157.6)
NOSE_C = _v(0, -8.2, 155.9)


def nose_w(V):
    return bump(V, NOSE_C, (2.1, 2.6, 3.2)) * front(V, -5)


def fwdness(V):
    return np.clip((-7.4 - V[:, 1]) / 2.0, 0, 1)


two_way("NoseBridge_Height", "Nose.BridgeHeight", FACE,
        lambda V, N: move(bump(V, BRIDGE, (1.3, 2.0, 1.8)), (0, -0.35, 0)),
        lambda V, N: move(bump(V, BRIDGE, (1.3, 2.0, 1.8)), (0, 0.33, 0)))
two_way("NoseBridge_Width", "Nose.BridgeWidth", FACE,
        lambda V, N: _xscale(V, bump(V, BRIDGE, (1.9, 2.2, 2.2), snap=False), 0.45),
        lambda V, N: _xscale(V, bump(V, BRIDGE, (1.9, 2.2, 2.2), snap=False), -0.3))
two_way("NoseBridge_Curve", "Nose.BridgeCurve", FACE,
        lambda V, N: move(bump(V, (0, -8.8, 156.6), (0.95, 1.6, 0.95)), (0, -0.22, 0)),
        lambda V, N: move(bump(V, (0, -8.8, 156.6), (0.95, 1.6, 0.95)), (0, 0.22, 0)))
two_way("Nose_Length", "Nose.Length", FACE,
        lambda V, N: move(bump(V, TIP, (1.6, 2.0, 1.5)), (0, -0.12, -0.45)),
        lambda V, N: move(bump(V, TIP, (1.6, 2.0, 1.5)), (0, 0.05, 0.35)))
two_way("Nose_Height", "Nose.Height", FACE,
        lambda V, N: move(nose_w(V), (0, 0, 0.4)),
        lambda V, N: move(nose_w(V), (0, 0, -0.4)))
two_way("Nose_Projection", "Nose.Projection", FACE,
        lambda V, N: move(nose_w(V) * fwdness(V), (0, -0.45, 0)),
        lambda V, N: move(nose_w(V) * fwdness(V), (0, 0.4, 0)))
two_way("NoseTip_Size", "Nose.TipSize", FACE,
        lambda V, N: scale_delta(V, TIP + (0, 0.25, 0), 1.25, bump(V, TIP, (1.4, 1.6, 1.3), snap=False))
        + push(N, bump(V, TIP, (1.0, 1.3, 1.0), snap=False), 0.12),
        lambda V, N: scale_delta(V, TIP + (0, 0.25, 0), 0.82, bump(V, TIP, (1.4, 1.6, 1.3), snap=False))
        + push(N, bump(V, TIP, (1.0, 1.3, 1.0), snap=False), -0.08))
two_way("NoseTip_Lift", "Nose.TipLift", FACE,
        lambda V, N: move(bump(V, TIP + (0, -0.3, 0), (1.1, 1.3, 1.0)), (0, 0.1, 0.3)),
        lambda V, N: move(bump(V, TIP + (0, -0.3, 0), (1.1, 1.3, 1.0)), (0, -0.05, -0.3)))
two_way("NoseTip_Shape", "Nose.TipShape", FACE,
        lambda V, N: _xscale(V, bump(V, TIP, (1.3, 1.5, 1.2), snap=False), -0.3)
        + move(bump(V, TIP + (0, -0.5, 0), (0.9, 1.1, 0.9), snap=False), (0, -0.22, 0)),
        lambda V, N: _xscale(V, bump(V, TIP, (1.3, 1.5, 1.2), snap=False), 0.25)
        + push(N, bump(V, TIP, (1.1, 1.3, 1.1), snap=False), 0.08))
WING = (1.0, -8.4, 154.45)
two_way("Nostril_Width", "Nose.NostrilWidth", FACE,
        mk_side_move(WING, (0.85, 1.1, 0.85), (0.25, 0, 0)),
        mk_side_move(WING, (0.85, 1.1, 0.85), (-0.22, 0, 0)))
two_way("Nostril_Flare", "Nose.NostrilFlare", FACE,
        mk_side_move(WING, (0.8, 1.0, 0.75), (0.05, 0, 0), 0.2),
        mk_side_move(WING, (0.8, 1.0, 0.75), (-0.05, 0, 0), -0.15))
two_way("Nostril_Height", "Nose.NostrilHeight", FACE,
        mk_side_move(WING, (0.85, 1.1, 0.8), (0, 0, 0.22)),
        mk_side_move(WING, (0.85, 1.1, 0.8), (0, 0, -0.2)))
two_way("Nose_Bend", "Nose.Bend", FACE,
        lambda V, N: move(nose_w(V) * fwdness(V), (-0.4, 0, 0)),
        lambda V, N: move(nose_w(V) * fwdness(V), (0.4, 0, 0)),
        "_Pos bends to the character's right (high end of the slider)")

# ----------------------------------------------------------------------------- face: Mouth

MO = cs.MOUTH.astype(F)


def mouth_w(V):
    return bump(V, MO, (2.7, 2.4, 1.7), snap=False) * front(V, -4)


two_way("Mouth_Width", "Mouth.Width", FACE,
        lambda V, N: _xscale(V, mouth_w(V), 0.22), lambda V, N: _xscale(V, mouth_w(V), -0.18))
two_way("Mouth_Height", "Mouth.Height", FACE,
        lambda V, N: move(mouth_w(V), (0, 0, 0.35)), lambda V, N: move(mouth_w(V), (0, 0, -0.35)))
two_way("Mouth_Depth", "Mouth.Depth", FACE,
        lambda V, N: move(mouth_w(V), (0, -0.3, 0)), lambda V, N: move(mouth_w(V), (0, 0.3, 0)))
UPPER = MO + (0, -0.1, 0.32)
LOWER = MO + (0, 0.0, -0.38)
two_way("LipUpper_Full", "Mouth.UpperLipFullness", FACE,
        lambda V, N: push(N, bump(V, UPPER, (1.8, 1.4, 0.6), snap=False), 0.26)
        + move(bump(V, UPPER, (1.8, 1.4, 0.6), snap=False), (0, 0, 0.06)),
        lambda V, N: push(N, bump(V, UPPER, (1.8, 1.4, 0.6), snap=False), -0.18))
two_way("LipLower_Full", "Mouth.LowerLipFullness", FACE,
        lambda V, N: push(N, bump(V, LOWER, (1.6, 1.4, 0.65), snap=False), 0.28),
        lambda V, N: push(N, bump(V, LOWER, (1.6, 1.4, 0.65), snap=False), -0.18))


def cupids(sign):
    def fn(V, N):
        peaks = sum(bump(V, MO + (0.42 * s, -0.1, 0.6), (0.42, 1.4, 0.4), snap=False) for _, s in SIDES)
        dip = bump(V, MO + (0, -0.1, 0.6), (0.28, 1.4, 0.34), snap=False)
        k = 1.0 if sign > 0 else -0.6
        return move(peaks, (0, -0.06 * k, 0.2 * k)) + move(dip, (0, 0.03 * k, -0.1 * k))
    return fn


two_way("Lip_CupidsBow", "Mouth.CupidsBow", FACE, cupids(1.0), cupids(-1.0))


def lip_offset(sign):
    def fn(V, N):
        up = bump(V, UPPER, (1.7, 1.3, 0.5))
        lo = bump(V, LOWER, (1.5, 1.3, 0.55))
        if sign > 0:
            return move(up, (0, -0.2, 0)) + move(lo, (0, 0.12, 0))
        return move(up, (0, 0.12, 0)) + move(lo, (0, -0.2, 0))
    return fn


two_way("Lip_Offset", "Mouth.LipOffset", FACE, lip_offset(1.0), lip_offset(-1.0),
        "_Pos = upper lip forward (slider high end), _Neg = lower lip forward")


def mk_corner(side, s, sign):
    return lambda V, N: move(bump(V, m((1.35, -7.9, 151.75), s), (0.8, 1.5, 0.8), snap=False),
                             (0, 0.05 * sign, 0.26 * sign))


sided("MouthCorner", "Mouth.CornerLift", FACE, mk_corner)


def philtrum(sign):
    def fn(V, N):
        groove = bump(V, (0, -8.0, 152.9), (0.36, 1.4, 0.7), snap=False)
        ridges = sum(bump(V, (0.42 * s, -8.0, 152.85), (0.24, 1.4, 0.7), snap=False) for _, s in SIDES)
        if sign > 0:
            return push(N, groove, -0.16) + push(N, ridges, 0.08)
        return push(N, groove, 0.1)
    return fn


two_way("Philtrum_Depth", "Mouth.PhiltrumDepth", FACE, philtrum(1.0), philtrum(-1.0))


def philtrum_len(dz):
    def fn(V, N):
        w = bump(V, MO + (0, 0, -0.2), (2.6, 2.2, 1.8)) * (1 - smoothstep(152.4, 153.4, V[:, 2])) * front(V, -4)
        return move(w, (0, 0, dz))
    return fn


two_way("Philtrum_Length", "Mouth.PhiltrumLength", FACE, philtrum_len(-0.3), philtrum_len(0.25))

# ----------------------------------------------------------------------------- body

J = rig.build_joints()[0]
TAILS = rig.build_joints()[2]


def body_both(c, r, d=(0, 0, 0), normal=0.0):
    return mk_side_move(c, r, d, normal)


def chest(amount):
    return mk_side_move((5.0, -6.2, 124.3), (5.2, 4.6, 5.0), (0, -0.25 * np.sign(amount), 0), amount)


two_way("Chest_Full", "Body.ChestShape", BODY, chest(0.95), chest(-0.65))


def _limb_point(a, b, t, off=(0, 0, 0)):
    return J[a] + (J[b] - J[a]) * t + np.asarray(off, F)


def muscle(sign):
    sites = [(_limb_point("upperarm_l", "lowerarm_l", 0.02, (0.6, 0.2, 0.8)), (4.4, 4.6, 4.4), 0.4),  # deltoid
             (_limb_point("upperarm_l", "lowerarm_l", 0.5, (0, -2.6, 0.6)), (3.0, 2.8, 4.5), 0.35),    # biceps
             (_v(6.0, -6.5, 129.5), (5.0, 3.5, 3.5), 0.25),                                           # chest
             (_limb_point("calf_l", "foot_l", 0.27, (0, 3.2, 0)), (3.4, 3.0, 7.0), 0.35),             # calf
             (_limb_point("thigh_l", "calf_l", 0.5, (0, -4.5, 0)), (4.2, 3.6, 9.0), 0.3)]             # thigh

    def fn(V, N):
        out = np.zeros_like(V)
        for c, r, a in sites:
            for _, s in SIDES:
                out += push(N, bump(V, m(c, s), r), a * (1.0 if sign > 0 else -0.5))
        waist = bump(V, (0, 0, 106.0), (13, 11, 5))
        out += push(N, waist, -0.35 if sign > 0 else 0.3)
        return out
    return fn


two_way("Muscle_Tone", "Body.MuscleTone", BODY, muscle(1.0), muscle(-1.0),
        "painted forms only: broad soft masses, no anatomy detail")


def soft(sign):
    sites = [((0, -6.0, 103.0), (11, 7, 8), 0.7), ((11.5, 1.5, 88.0), (5.5, 7.0, 7.0), 0.55),
             (tuple(_limb_point("thigh_l", "calf_l", 0.45)), (6.0, 6.5, 11.0), 0.5),
             (tuple(_limb_point("upperarm_l", "lowerarm_l", 0.45, (0, 1.5, 0))), (3.6, 3.6, 6.0), 0.4),
             ((0, 4.0, 120.0), (11, 5, 8), 0.3), ((0, -2.0, 112.0), (12, 9, 5), 0.45)]

    def fn(V, N):
        out = np.zeros_like(V)
        for c, r, a in sites:
            for _, s in SIDES if c[0] else (("c", 1.0),):
                out += push(N, bump(V, m(c, s), r), a * (1.0 if sign > 0 else -0.55))
        return out
    return fn


two_way("Body_Soft", "Body.Softness", BODY, soft(1.0), soft(-1.0))
two_way("Belly", "Body.Belly", BODY,
        lambda V, N: push(N, bump(V, (0, -7.5, 103.0), (10.5, 7.5, 8.5)), 1.5),
        lambda V, N: push(N, bump(V, (0, -7.5, 103.0), (10.5, 7.5, 8.5)), -0.55))


def shoulder_bulk(a):
    return lambda V, N: (mk_side_move((14.5, 0.5, 136.0), (4.6, 4.8, 4.4), (0, 0, 0), a)(V, N)
                         + mk_side_move((7.5, 2.0, 138.0), (4.5, 4.0, 2.6), (0, 0, 0), a * 0.6)(V, N))


two_way("Shoulder_Bulk", "Body.ShoulderBulk", BODY, shoulder_bulk(0.75), shoulder_bulk(-0.45))


def hip_curve(sign):
    def fn(V, N):
        hips = mk_side_move((13.0, 1.0, 88.5), (5.0, 9.0, 8.0), (1.0 * sign if sign > 0 else -0.8, 0, 0))(V, N)
        waist = mk_side_move((10.5, 0.0, 108.0), (4.0, 9.0, 5.0), (-0.5 if sign > 0 else 0.4, 0, 0))(V, N)
        return hips + waist
    return fn


two_way("Hip_Curve", "Body.HipShape", BODY, hip_curve(1.0), hip_curve(-1.0))


def finger_length(k):
    def fn(V, N):
        out = np.zeros_like(V)
        for side, _ in SIDES:
            for f in rig.FINGERS + ("thumb",):
                a = J[f"{f}_01_{side}"]
                tip = TAILS[f"{f}_03_{side}"]
                d = tip - a
                L = np.linalg.norm(d)
                d /= L
                t = np.clip((V - a) @ d / L, 0, 1)
                closest = a + np.outer(t * L, d)
                dist = np.linalg.norm(V - closest, axis=1)
                w = 1 - smoothstep(1.0, 1.6, dist)
                w *= smoothstep(-0.1, 0.15, (V - a) @ d / L)
                out += np.outer(w * t * L * k, d)
        return out
    return fn


two_way("Finger_Length", "Body.FingerLength", BODY, finger_length(0.10), finger_length(-0.10))

# ----------------------------------------------------------------------------- slider map

MATERIAL_SLIDERS = {
    "Eyes.IrisSize": "material IrisScale", "Eyes.PupilSize": "material PupilScale",
    "Brows.Thickness": "material BrowThickness", "Brows.Length": "material BrowLength",
}
NOT_DONE = {
    "Body.NailLength": "no nail geometry on this base; needs a nail mask or tiny nail mesh",
}
EAR_SLIDERS = [  # (slider, morph base, sided, two-way)
    ("Ears.Size", "Ear_Size", True, True), ("Ears.Angle", "Ear_Angle", True, True),
    ("Ears.Height", "Ear_Height", False, True), ("Ears.Lobe", "Ear_Lobe", False, True),
    ("Ears.Tip", "Ear_Tip", True, False), ("Ears.Point", "Ear_Point", True, False),
    ("Ears.PointAngle", "Ear_PointAngle", True, True), ("Ears.Droop", "Ear_Droop", True, False),
    ("Ears.FinSpread", "Ear_Fin", True, False),
]
LASH_SLIDERS = [("Lashes.Length", "Lash_Length"), ("Lashes.Curl", "Lash_Curl")]
HAIR_SCALARS = [("Hair.Length", "Hair_Length"), ("Hair.Volume", "Hair_Volume")]


def by_group(*groups):
    return [mm for mm in REG if mm.group in groups]
