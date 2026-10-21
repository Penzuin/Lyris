"""Shape fields for the Lyris base character: body frames, head, ears, outfit, hair.

Build space: centimetres, X = character's left, -Y = forward, Z up, feet on Z = 0
(Blender's axes; see char_rig.py for how this lands in Unreal).

Everything is a soft signed distance field so the forms stay rounded and simple, like a
painted figure: no anatomy beyond the big masses, no veins, no folds.
"""

import numpy as np

import char_rig as rig
from char_sdf import (F32, cone, ellipsoid, flat_cone, frame, norm, plane, smax, smin, sphere,
                      tube, v3)

J, PARENTS, TAILS, HAND = rig.build_joints()

# ----------------------------------------------------------------------------- landmarks

EYE = {"l": v3(3.38, -5.95, 158.3), "r": v3(-3.38, -5.95, 158.3)}
EYE_R = v3(2.32, 1.42, 2.08)          # eyeball half sizes (across, depth, up)
EYE_W, EYE_HU, EYE_HL = 2.30, 1.80, 0.98   # eye opening: half width, upper and lower lid heights
EYE_YAW = 16.0                        # outer side of each eye turns back with the face
EAR = {"l": v3(7.55, 1.0, 156.4), "r": v3(-7.55, 1.0, 156.4)}
NOSE_TIP = v3(0.0, -9.1, 155.0)
MOUTH = v3(0.0, -7.95, 151.95)
MOUTH_HALF = 1.12                     # half width of the mouth line
CHIN = v3(0.0, -6.5, 148.4)
BROW = {"l": v3(3.5, -7.5, 162.4), "r": v3(-3.5, -7.5, 162.4)}
NECK_CUT_Z = 142.0                    # head / body seam (a ring round the neck)

# The head is designed at 6.9 heads tall (crown 172) and then grown about the neck by
# HEAD_SCALE (T46 art pass: 6.4 heads, a storybook adult). head_xform maps design space to
# the exported mesh; below NECK_CUT_Z it is the identity, so the neck seam never moves.
HEAD_SCALE = 1.16
HEAD_PIVOT = v3(0.0, 1.0, NECK_CUT_Z)
HEAD_BLEND = (NECK_CUT_Z, NECK_CUT_Z + 5.0)


def head_k(V):
    V = np.asarray(V, dtype=np.float64)
    t = np.clip((V[:, 2] - HEAD_BLEND[0]) / (HEAD_BLEND[1] - HEAD_BLEND[0]), 0, 1)
    t = t * t * (3 - 2 * t)
    return 1.0 + (HEAD_SCALE - 1.0) * t


def head_xform(V):
    """Design space -> exported space for everything on the head."""
    V = np.asarray(V, dtype=np.float64)
    k = head_k(V)[:, None]
    return HEAD_PIVOT.astype(np.float64) + (V - HEAD_PIVOT.astype(np.float64)) * k


def head_xform_delta(V, D):
    """Morph offsets authored in design space, carried into exported space."""
    return np.asarray(D) * head_k(V)[:, None]


def eye_rot(side):
    """Columns: x across (outward), y depth (backwards into the head), z up."""
    s = 1.0 if side == "l" else -1.0
    a = np.radians(EYE_YAW)
    c, si = np.cos(a), np.sin(a)
    x = v3(s * c, si, 0)       # the outer corner turns back with the curve of the face
    y = v3(-s * si, c, 0)
    return np.stack([x, y, v3(0, 0, 1)], axis=1).astype(F32)


# ----------------------------------------------------------------------------- head

def almond(P, side, grow=0.0):
    """2D eye opening (upper and lower lid curves) in the eye's local frame, negative inside."""
    R = eye_rot(side)
    q = (P - EYE[side]) @ R            # u across (outward), depth, v up
    u, v = q[:, 0], q[:, 2]
    W = EYE_W + grow
    t = np.clip(u / W, -1, 1)
    # the upper lid peaks a little towards the nose, the outer corner sits a touch higher
    hu = (EYE_HU + grow) * np.clip(1 - t * t, 0, 1) ** 0.58 * (1 - 0.08 * t) + 0.18 * t
    hl = -(EYE_HL + grow) * np.clip(1 - t * t, 0, 1) ** 0.8 + 0.18 * t
    d = np.maximum(v - hu, hl - v)
    d = np.maximum(d, np.abs(u) - W)
    return d, q


def eyeball_sdf(P, side, grow=0.0):
    return ellipsoid(P, EYE[side], EYE_R + grow, eye_rot(side))


def head_sdf(P, closed=True):
    h = ellipsoid(P, v3(0, 0.9, 162.6), v3(8.2, 8.8, 9.4))                     # cranium
    face = ellipsoid(P, v3(0, -2.2, 156.4), v3(7.0, 6.8, 7.4))
    h = smin(h, face, 3.2)
    h = smin(h, ellipsoid(P, v3(0, -4.9, 151.9), v3(3.5, 2.9, 2.7)), 2.2)                            # muzzle
    for s in (1, -1):
        h = smin(h, cone(P, v3(5.2 * s, -0.6, 155.0), v3(1.1 * s, -5.0, 149.0), 2.2, 1.45), 3.4)   # jaw, soft
        h = smin(h, ellipsoid(P, v3(3.6 * s, -4.9, 153.9), v3(2.95, 2.75, 2.65)), 2.8)               # round cheek
    h = smin(h, ellipsoid(P, CHIN + v3(0, 1.1, 0.85), v3(1.85, 1.5, 1.45)), 1.8)                   # round chin
    h = smax(h, plane(P, v3(0, -9.25, 0), v3(0, -1, 0)), 3.6)                                        # very soft front
    h = smin(h, ellipsoid(P, v3(0, -5.8, 162.7), v3(5.6, 1.05, 1.2)), 3.8)                          # brow
    # nose: small and soft, a little button tip
    nose = cone(P, v3(0, -7.3, 158.2), NOSE_TIP + v3(0, 0.6, 0.4), 0.24, 0.44)
    nose = smin(nose, ellipsoid(P, NOSE_TIP + v3(0, 0.55, 0.05), v3(0.54, 0.5, 0.46)), 0.45)
    nose = smin(nose, ellipsoid(P, NOSE_TIP + v3(0, 1.0, -0.22), v3(0.92, 0.45, 0.42)), 0.55)   # soft wings
    h = smin(h, nose, 0.95)
    # lips: two small soft pillows
    h = smin(h, ellipsoid(P, MOUTH + v3(0, 0.2, 0.27), v3(1.05, 0.28, 0.27)), 0.55)
    h = smin(h, ellipsoid(P, MOUTH + v3(0, 0.3, -0.31), v3(0.9, 0.32, 0.32)), 0.55)
    # neck (slim: the larger head is grown on top of it)
    h = smin(h, cone(P, v3(0, 1.6, 136.0), v3(0, 0.9, 151.0), 4.9, 4.2), 2.6)
    # eye sockets: the almond opening, cut down to the eyeball, plus a soft upper lid
    for side in ("l", "r"):
        s = 1 if side == "l" else -1
        h = smin(h, ellipsoid(P, EYE[side] + v3(0.1 * s, -0.85, 1.4), v3(2.5, 0.95, 0.85),
                              eye_rot(side)), 0.9)
        a, q = almond(P, side)
        slot = np.maximum(a, np.maximum(q[:, 1] - 0.15, -q[:, 1] - 4.5))
        cavity = np.minimum(slot, eyeball_sdf(P, side, 0.06))
        h = smax(h, -cavity, 0.22)
        if closed:
            # the opening is filled by the eyeball's own surface, so the head stays one closed
            # surface for quad remeshing; char_mesh.cut_eye_holes then opens it on a clean loop
            h = smin(h, eyeball_sdf(P, side, 0.06), 0.04)
    return h


# ----------------------------------------------------------------------------- body frames

FRAMES = {
    # Willow: narrower and lighter. Oak: broader and sturdier. Cosmetic only, same skeleton.
    "FrameA": dict(rib=12.4, chest=13.2, waist=10.4, hip=13.4, depth=1.0, chest_full=1.0,
                   delt=4.55, ua=(4.15, 3.25), fa=(3.25, 2.25), thigh=(7.5, 4.8), calf=4.45,
                   ankle=2.45, trap=4.4, neckbase=5.6, glute=1.0, hand=1.0),
    "FrameB": dict(rib=14.6, chest=15.8, waist=12.8, hip=14.4, depth=1.08, chest_full=0.35,
                   delt=5.55, ua=(5.0, 3.9), fa=(3.85, 2.65), thigh=(8.1, 5.35), calf=5.0,
                   ankle=2.75, trap=5.2, neckbase=5.9, glute=0.8, hand=1.07),
}


def _limb_parts(P, f, which):
    out = {}
    for side, s in (("l", 1.0), ("r", -1.0)):
        sh, el, wr = J[f"upperarm_{side}"], J[f"lowerarm_{side}"], J[f"hand_{side}"]
        wrist, d, n, w = HAND[side]
        if "arm" in which:
            ua = cone(P, sh, el, f["ua"][0], f["ua"][1])
            ua = smin(ua, sphere(P, sh + v3(0.9 * s, 0.2, -1.4), f["delt"]), 2.5)   # keeps the shoulder top under the neck seam
            fa = flat_cone(P, el, wr, f["fa"][0], f["fa"][1], n, 0.78)
            fa = smin(fa, ellipsoid(P, el + (wr - el) * 0.22, v3(f["fa"][0] * 1.08, f["fa"][0], 4.5),
                                    frame(wr - el, v3(0, 0, 1))), 1.5)
            out[f"upperarm_{side}"] = ua
            out[f"lowerarm_{side}"] = fa
        if "hand" in which:
            k = f["hand"]
            R = np.stack([w, n, d], axis=1).astype(F32)
            palm = ellipsoid(P, wrist + d * 4.0 + n * 0.1, v3(3.45 * k, 1.3 * k, 4.2), R)
            palm = smin(palm, cone(P, wrist - d * 1.0, wrist + d * 1.6, f["fa"][1], 2.0 * k), 1.2)
            fingers = None
            for fn_ in rig.FINGERS:
                chain = [J[f"{fn_}_0{i}_{side}"] for i in (1, 2, 3)] + [TAILS[f"{fn_}_03_{side}"]]
                r0 = {"index": 0.64, "middle": 0.66, "ring": 0.62, "pinky": 0.55}[fn_] * k
                radii = [r0, r0 * 0.93, r0 * 0.86, r0 * 0.8]
                fd = tube(P, chain, radii, 0.25)
                fingers = fd if fingers is None else np.minimum(fingers, fd)
            thumb = [J[f"thumb_0{i}_{side}"] for i in (1, 2, 3)] + [TAILS[f"thumb_03_{side}"]]
            fingers = np.minimum(fingers, tube(P, thumb, [1.25 * k, 0.95 * k, 0.82 * k, 0.74 * k], 0.4))
            out[f"hand_{side}"] = smin(palm, fingers, 0.7)
        if "leg" in which:
            hip, knee, ank = J[f"thigh_{side}"], J[f"calf_{side}"], J[f"foot_{side}"]
            th = cone(P, hip + v3(0.6 * s, 0.4, 1.5), knee, f["thigh"][0], f["thigh"][1])
            th = smin(th, sphere(P, knee + v3(0, -0.4, 0.5), f["thigh"][1] * 0.9), 2.5)
            ca = cone(P, knee, ank, f["thigh"][1] * 0.93, f["ankle"])
            ca = smin(ca, ellipsoid(P, knee + (ank - knee) * 0.27 + v3(0.15 * s, 1.0, 0),
                                    v3(f["calf"], f["calf"] * 1.02, 8.5)), 2.5)
            out[f"thigh_{side}"] = th
            out[f"calf_{side}"] = ca
        if "foot" in which:
            ank, ball = J[f"foot_{side}"], J[f"ball_{side}"]
            heel = ellipsoid(P, v3(ank[0], 3.2, 3.6), v3(2.9, 3.2, 3.3))
            ft = cone(P, v3(ank[0], 2.0, 3.4), ball + v3(0, 0, 0.4), 2.9, 3.2)
            ft = smin(ft, ellipsoid(P, ball + v3(0.1 * s, -3.3, 0.1), v3(3.35, 3.1, 1.95)), 1.8)
            ft = smin(ft, heel, 1.5)
            ft = smin(ft, cone(P, ank + v3(0, 0, 6), ank + v3(0, 0.6, 0.6), f["ankle"], 2.7), 1.8)
            out[f"foot_{side}"] = smax(ft, 1.0 - P[:, 2], 0.6)
    return out


def torso_sdf(P, f):
    dz = f["depth"]
    t = ellipsoid(P, v3(0, 1.0, 92.0), v3(f["hip"], 9.4 * dz, 7.6))                        # pelvis
    for s in (1, -1):
        t = smin(t, ellipsoid(P, v3(5.4 * s, 4.2, 87.5), v3(6.0, 5.0 * f["glute"] + 0.4, 6.6)), 3.0)
    t = smin(t, ellipsoid(P, v3(0, -0.8, 101), v3(f["waist"] + 0.7, 8.7 * dz, 9.0)), 5.0)     # belly
    t = smin(t, ellipsoid(P, v3(0, 0.6, 107.5), v3(f["waist"], 8.2 * dz, 6.0)), 5.0)          # waist
    t = smin(t, ellipsoid(P, v3(0, 0.0, 119.5), v3(f["rib"], 9.6 * dz, 12.5)), 5.0)           # ribcage
    t = smin(t, ellipsoid(P, v3(0, -0.4, 127.8), v3(f["chest"], 9.0 * dz, 8.2)), 4.5)         # chest
    cf = f["chest_full"]
    for s in (1, -1):
        if cf > 0:
            t = smin(t, ellipsoid(P, v3(5.0 * s, -6.2 - 0.6 * cf, 124.3), v3(4.6, 2.6 + 1.0 * cf, 4.1 + 0.4 * cf)),
                     3.0)
        t = smin(t, ellipsoid(P, v3(5.8 * s, 6.3, 126.0), v3(5.8, 3.4, 7.0)), 4.0)            # shoulder blade
        t = smin(t, cone(P, v3(2.2 * s, 2.4, 137.6), v3(12.0 * s, 1.3, 135.8), 3.0, f["trap"] * 0.85), 4.0)
        t = smin(t, cone(P, v3(2.5 * s, -3.4, 135.6), v3(12.5 * s, -1.6, 136.4), 1.5, 1.9), 2.4)  # collarbone
    t = smin(t, cone(P, v3(0, 2.0, 131.0), v3(0, 1.6, 141.0), f["neckbase"] + 0.6, 5.0), 4.0)
    return t


def body_sdf(P, frame_id, with_head=True, closed=True):
    f = FRAMES[frame_id]
    d = torso_sdf(P, f)
    parts = _limb_parts(P, f, ("arm", "hand", "leg", "foot"))
    for side in ("l", "r"):
        arm = smin(parts[f"upperarm_{side}"], parts[f"lowerarm_{side}"], 1.6)
        arm = smin(arm, parts[f"hand_{side}"], 1.2)
        d = smin(d, arm, 3.0)
        leg = smin(parts[f"thigh_{side}"], parts[f"calf_{side}"], 2.0)
        leg = smin(leg, parts[f"foot_{side}"], 1.5)
        d = smin(d, leg, 4.0)
    # shoulders and traps stay below the head/body seam (NECK_CUT_Z) so the cut only rings the neck
    r = np.sqrt(P[:, 0] ** 2 + (P[:, 1] - 1.2) ** 2)
    t = np.clip((r - 6.2) / 1.6, 0, 1)
    capped = smax(d, P[:, 2] - (NECK_CUT_Z - 1.6), 1.4)
    d = d * (1 - t) + capped * t
    if with_head:
        d = smin(d, head_sdf(P, closed), 1.5)
    return d


def shared_neck_weight(P):
    """1 where every frame must match exactly (round the head seam)."""
    z = P[:, 2]
    r = np.sqrt(P[:, 0] ** 2 + (P[:, 1] - 1.2) ** 2)
    a = np.clip((z - 138.5) / 1.5, 0, 1)
    b = np.clip((8.5 - r) / 1.5, 0, 1)
    return (a * a * (3 - 2 * a)) * (b * b * (3 - 2 * b))


def frame_sdf(P, frame_id, closed=True):
    d = body_sdf(P, frame_id, closed=closed)
    if frame_id == "FrameA":
        return d
    w = shared_neck_weight(P)
    m = w > 0
    if m.any():
        d[m] = d[m] * (1 - w[m]) + body_sdf(P[m], "FrameA", closed=closed) * w[m]
    return d


# ----------------------------------------------------------------------------- ears

def ear_frame(side):
    """Ear-local axes: b = back along the head, a = up, n = outward."""
    s = 1.0 if side == "l" else -1.0
    n = norm(v3(s * 0.96, -0.28, 0.0))       # ears turn a little to face forward; the back rim flares out
    a = v3(0, 0, 1)
    b = norm(np.cross(a, n)) * s
    if b[1] < 0:
        b = -b
    return b, a, n


POINT_THETA = 1.05                            # direction of an elf point: back and up


def ear_outline(theta, shape):
    """Outline radius (cm) of the ear at angle theta (0 = back, pi/2 = up) in the ear plane.
    shape keys: tip (0..1 slight human point), point (0..1 long point, up to +6 cm),
    point_theta (direction of the point), fin (0..1 Deepkin fin), lobe (-1..1)."""
    th = np.asarray(theta, dtype=np.float64)
    r = 2.0 + 0.55 * np.sin(th) + 0.22 * np.cos(2 * th) + 0.2 * np.cos(th)
    lobe_dir = -np.pi / 2 - 0.25
    dl = np.angle(np.exp(1j * (th - lobe_dir)))          # wrapped angle difference
    r = r + shape.get("lobe", 0.0) * 0.45 * np.exp(-(dl / 0.45) ** 2)
    pt = shape.get("point_theta", POINT_THETA)
    up = np.exp(-((th - pt) / 0.42) ** 2)
    r = r + shape.get("tip", 0.0) * 0.6 * up
    p = shape.get("point", 0.0)
    r = r + p * (6.0 * np.exp(-((th - pt) / 0.24) ** 2) + 0.7 * up)
    fin = shape.get("fin", 0.0)
    if fin > 0:
        env = np.exp(-((th - 0.65) / 1.0) ** 2)
        ribs = 0.45 * np.cos(4.5 * (th - 0.65)) ** 2
        r = r + fin * (2.6 * env + ribs * env)
    return r


EAR_NT, EAR_NR = 40, 5


def ear_topology():
    """Quads/tris for the parametric ear: front sheet rings, a rim, back sheet rings,
    a pole at the centre of each sheet. Returns faces (index lists) and vertex count."""
    nt, nr = EAR_NT, EAR_NR
    # vertex order: front pole, front rings (nr), rim ring, back rings (nr, outer to inner), back pole
    rings = 2 * nr + 1
    def idx(ring, j):
        return 1 + ring * nt + (j % nt)
    back_pole = 1 + rings * nt
    faces = []
    for j in range(nt):
        faces.append((0, idx(0, j), idx(0, j + 1)))
    for r in range(rings - 1):
        for j in range(nt):
            faces.append((idx(r, j), idx(r + 1, j), idx(r + 1, j + 1), idx(r, j + 1)))
    for j in range(nt):
        faces.append((back_pole, idx(rings - 1, j + 1), idx(rings - 1, j)))
    return faces, back_pole + 1


def ear_points(side, shape, size=1.0, angle=0.0, height=0.0, droop=0.0, point_up=0.0):
    """Vertex positions of one ear for a set of morph parameters (same topology always)."""
    b, a, n = ear_frame(side)
    c = EAR[side] + v3(0, 0, height)
    nt, nr = EAR_NT, EAR_NR
    th = np.linspace(0, 2 * np.pi, nt, endpoint=False)
    sh = dict(shape)
    if point_up:
        sh["point_theta"] = POINT_THETA + point_up
    R = ear_outline(th, sh)
    rhos = np.linspace(1.0 / nr, 0.97, nr)

    def sheet_offset(rho, front):
        # outward offset of the sheet: the front edge (towards the face) sinks into the head,
        # the back rim stands out; a soft bowl (concha) inside a raised rim (helix)
        qb = np.cos(th)
        cn = -0.45 + 0.9 * (qb * rho + 1) * 0.5 + 0.3 * rho
        t = 0.26 * (1 - 0.6 * rho ** 3) + 0.06
        if front:
            bowl = 0.42 * np.exp(-((rho - 0.42) / 0.3) ** 2) * (0.6 + 0.4 * np.sin(th + 0.3) ** 2)
            helix = 0.12 * np.exp(-((rho - 0.86) / 0.08) ** 2)
            return cn + t - bowl + helix
        return cn - t

    pts = [c + n * 0.10]                                  # centre of the front sheet
    for rho in rhos:
        off = sheet_offset(rho, True)
        p = c[None, :] + (b[None, :] * np.cos(th)[:, None] + a[None, :] * np.sin(th)[:, None]) * (rho * R)[:, None] \
            + n[None, :] * off[:, None]
        pts.extend(p)
    rim = c[None, :] + (b[None, :] * np.cos(th)[:, None] + a[None, :] * np.sin(th)[:, None]) * R[:, None] \
        + n[None, :] * ((-0.45 + 0.9 * (np.cos(th) + 1) * 0.5 + 0.3) + 0.02)[:, None]
    pts.extend(rim)
    for rho in rhos[::-1]:
        off = sheet_offset(rho, False)
        p = c[None, :] + (b[None, :] * np.cos(th)[:, None] + a[None, :] * np.sin(th)[:, None]) * (rho * R)[:, None] \
            + n[None, :] * off[:, None]
        pts.extend(p)
    pts.append(c - n * 0.50)                              # centre of the back sheet
    P = np.array(pts, dtype=np.float64)
    root = c - b * 1.6                                    # front edge, where the ear meets the head
    if droop:
        th = POINT_THETA + point_up
        d = norm(b * np.cos(th) + a * np.sin(th))
        along = (P - c) @ d
        w = np.clip((along - 2.4) / 4.5, 0, 1) ** 1.5      # only the long point bends
        k = norm(np.cross(d, -a))                         # folds the tip down
        P = _rotate_about(P, c + d * 2.4, k, -np.radians(40.0) * droop * w)
    if angle:
        k = norm(np.cross(b, n))                          # swings the back rim outward
        P = _rotate_about(P, root, k, np.full(len(P), np.radians(angle)))
    if size != 1.0:
        P = root + (P - root) * size
    return P


def _rotate_about(P, pivot, k, ang):
    k = np.asarray(k, dtype=np.float64)
    q = P - pivot
    cosv, sinv = np.cos(ang)[:, None], np.sin(ang)[:, None]
    return pivot + q * cosv + np.cross(k, q) * sinv + k * (q @ k)[:, None] * (1 - cosv)


def ears_uv():
    """Planar UV per ear (left ear in the left half, right in the right half)."""
    nt, nr = EAR_NT, EAR_NR
    th = np.linspace(0, 2 * np.pi, nt, endpoint=False)
    rhos = np.linspace(1.0 / nr, 0.97, nr)
    uv = [(0.5, 0.5)]
    for rho in rhos:
        uv.extend(zip(0.5 + 0.22 * rho * np.cos(th), 0.5 + 0.22 * rho * np.sin(th)))
    uv.extend(zip(0.5 + 0.24 * np.cos(th), 0.5 + 0.24 * np.sin(th)))
    for rho in rhos[::-1]:
        uv.extend(zip(0.5 + 0.26 * (2 - rho) * np.cos(th) * 0.5 + 0.0, 0.5 + 0.26 * (2 - rho) * np.sin(th) * 0.5))
    uv.append((0.5, 0.5))
    return np.array(uv, dtype=np.float64)


# ----------------------------------------------------------------------------- outfit

def outfit_sdfs(P, frame_id):
    """Plain traveller (Outfit.PlainTraveller): loose shirt with rolled sleeves, belted
    trousers, soft boots. Returns dict piece -> field."""
    f = FRAMES[frame_id]
    torso = torso_sdf(P, f)
    parts = _limb_parts(P, f, ("arm", "leg", "foot"))
    out = {}
    # shirt: torso and upper arms, hem over the hips, open collar, sleeves rolled below the elbow
    shirt = torso - 1.15
    for side, s in (("l", 1.0), ("r", -1.0)):
        el, wr = J[f"lowerarm_{side}"], J[f"hand_{side}"]
        sleeve = smin(parts[f"upperarm_{side}"] - 1.0, parts[f"lowerarm_{side}"] - 1.1, 1.5)
        cuff_at = el + (wr - el) * 0.42
        sleeve = smax(sleeve, plane(P, cuff_at, wr - el), 0.3)
        roll = cone(P, cuff_at - norm(wr - el) * 1.6, cuff_at, f["fa"][0] * 0.95 + 1.5, f["fa"][0] * 0.92 + 1.5)
        sleeve = smin(sleeve, smax(roll, plane(P, cuff_at, wr - el), 0.2), 0.6)
        shirt = smin(shirt, sleeve, 3.0)
    shirt = smax(shirt, 98.0 - P[:, 2], 0.6)                                         # tucked in under the belt
    neck_hole = cone(P, v3(0, 1.4, 133.0), v3(0, 1.0, 150.0), 6.3, 6.0)
    vee = ellipsoid(P, v3(0, -8.5, 133.8), v3(2.4, 6.0, 5.5))
    shirt = smax(shirt, -smin(neck_hole, vee, 1.5), 1.1)
    out["shirt"] = shirt
    # trousers: pelvis to the boot tops, a little loose at the knee
    legs = None
    for side in ("l", "r"):
        lg = smin(parts[f"thigh_{side}"] - 1.1, parts[f"calf_{side}"] - 1.3, 2.5)
        legs = lg if legs is None else np.minimum(legs, lg)
    pelv = torso - 1.25
    pelv = smax(pelv, P[:, 2] - 101.5, 0.6)
    trousers = smin(pelv, smax(legs, P[:, 2] - 95.0, 2.0), 3.5)
    # follow the actual body (its hip and thigh blends) so no skin shows at the hips
    whole = body_sdf(P, frame_id, with_head=False) - 1.1
    whole = smax(whole, np.abs(P[:, 0]) - 21.0, 0.5)
    whole = smax(whole, P[:, 2] - 101.5, 0.6)
    trousers = smin(trousers, whole, 0.6)
    trousers = smax(trousers, 24.0 - P[:, 2], 0.5)
    out["trousers"] = trousers
    # belt over the trouser waist
    belt = smax(torso - 1.6, np.abs(P[:, 2] - 99.6) - 1.5, 0.3)
    out["belt"] = belt
    # boots: foot and lower calf, a turned-down cuff at the top
    boots = None
    for side in ("l", "r"):
        bt = smin(parts[f"calf_{side}"] - 1.45, parts[f"foot_{side}"] - 1.05, 2.0)
        bt = smax(bt, P[:, 2] - 30.0, 0.4)
        cuff = smax(parts[f"calf_{side}"] - 2.1, np.abs(P[:, 2] - 28.8) - 1.6, 0.4)
        bt = smin(bt, cuff, 0.5)
        boots = bt if boots is None else np.minimum(boots, bt)
    out["boots"] = smax(boots, -P[:, 2], 0.3)
    return out


# ----------------------------------------------------------------------------- hair

def _zigzag(x, period, depth, sharp=0.55, phase=0.0):
    """Points for lock tips along an edge: 0 at the tip, `depth` between tips."""
    s = np.abs(np.sin((x / period + phase) * np.pi))
    return depth * (1 - s ** sharp)


def _scalp(P, grow=1.7):
    """Hair mass on the cranium (a cap that follows the skull), with soft lock grooves."""
    c = v3(0, 0.9, 162.6)
    q = P - c
    cap = ellipsoid(P, c + v3(0, 0.25, 0.2), v3(8.2 + grow, 8.8 + grow, 9.4 + grow))
    # locks fan out from the crown: grooves by angle around the vertical axis
    ang = np.arctan2(q[:, 0], q[:, 1])
    grooves = 0.22 * np.abs(np.sin(ang * 9.0)) ** 0.8
    return cap + grooves


def _ear_keepout(P, grow=0.0, long_ears=False):
    """Space the hair leaves for the ears. With long_ears it also leaves a slot for an elf or
    Deepkin point at any point angle (the '_LongEar' hair variants, chosen automatically)."""
    d = None
    for side in ("l", "r"):
        b, a, n = ear_frame(side)
        k = cone(P, EAR[side] - n * 1.5 - a * 2.4 - b * 0.4, EAR[side] + a * 3.3 + b * 1.2 + n * 1.2,
                 2.45 + grow, 2.1 + grow)
        if long_ears:
            for dt in (-0.45, 0.0, 0.45):
                th = POINT_THETA + dt
                dvec = b * np.cos(th) + a * np.sin(th)
                k = smin(k, cone(P, EAR[side] + n * 0.3, EAR[side] + dvec * 9.5 + n * 1.2, 2.0 + grow, 1.0 + grow), 1.0)
            k = smin(k, cone(P, EAR[side] + b * 1.5, EAR[side] + b * 6.0 + a * 1.0 + n * 1.5, 2.6 + grow, 2.0 + grow), 1.0)
        d = k if d is None else np.minimum(d, k)
    return d


def _face_cut(P, fringe_z, side_y):
    """Region in front of the hairline that hair must not cover."""
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    fz = fringe_z(x)
    under = z - fz                       # negative below the fringe line
    front = y - side_y(z)                # negative in front of the side hairline
    return np.maximum(under, front)


def hair_bob(P, body, long_ears=False):
    """Hair.LamplighterBob: straight chin-length bob, pointed fringe, tucked behind the ears."""
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    cap = _scalp(P, 1.75)
    # the bob skirt: a rounded bell round the head down to the jaw
    c = v3(0, 1.6, 156.0)
    q = P - c
    rx = 9.0 + 0.012 * (162 - z).clip(0) ** 2
    ry = 10.2 + 0.012 * (162 - z).clip(0) ** 2
    bell = (np.sqrt((q[:, 0] / rx) ** 2 + (q[:, 1] / ry) ** 2) - 1.0) * 8.5
    bell = np.maximum(bell, z - 168.0)
    hem = 148.2 + _zigzag(np.arctan2(q[:, 0], q[:, 1]) * 9.0, 2.0, 1.0, 0.5) - 1.2 * (q[:, 1] > 3)
    bell = smax(bell, hem - z, 0.6)
    ang = np.arctan2(q[:, 0], q[:, 1])
    bell = bell + 0.25 * np.abs(np.sin(ang * 11.0)) ** 0.7
    h = smin(cap, bell, 2.0)
    fringe = lambda xx: 160.6 + 0.07 * xx ** 2 + _zigzag(xx, 1.25, 1.1, 0.5, 0.3)
    side = lambda zz: -3.2 + 0.0 * zz
    h = smax(h, -_face_cut(P, fringe, side), 0.35)
    h = smax(h, -_ear_keepout(P, 0.25, long_ears), 0.5)
    h = smax(h, -(body + 0.5), 0.3)
    return h


def hair_long(P, body, long_ears=False):
    """Hair.FallingWater: long, straight, loose to the middle of the back."""
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    cap = _scalp(P, 1.6)
    # a curtain that drapes over the back of the shoulders, hugging the body
    hug = smax(body - 2.9, -(body - 0.6), 0.3)
    back = 1.6 - y + 0.02 * x * x
    curtain = smax(hug, back, 0.8)
    curtain = smax(curtain, np.abs(x) - (8.8 + 0.12 * (150 - z).clip(0)), 1.0)
    tips = 113.0 + _zigzag(x, 2.2, 2.6, 0.5) + 0.03 * x * x
    curtain = smax(curtain, tips - z, 0.5)
    curtain = smax(curtain, z - 152.0, 2.0)
    # behind the head: a fall from the scalp down to the shoulders
    fall = ellipsoid(P, v3(0, 5.5, 148.0), v3(8.6, 5.4, 12.0))
    fall = smax(fall, 0.5 - y, 1.0)
    h = smin(cap, fall, 2.5)
    h = smin(h, curtain, 2.5)
    h = h + 0.28 * np.abs(np.sin(x * 1.5)) ** 0.7 * (z < 158)
    # two face-framing locks in front of the shoulders, behind the ears
    fringe = lambda xx: 161.2 + 0.05 * xx ** 2 + _zigzag(xx, 1.6, 0.9, 0.5, 0.15)
    side = lambda zz: -2.6 + 0.0 * zz
    h = smax(h, -_face_cut(P, fringe, side), 0.35)
    h = smax(h, -_ear_keepout(P, 0.25, long_ears), 0.5)
    h = smax(h, -(body + 0.45), 0.3)
    return h


def braid_path(body_fn):
    """Centre line of the rope braid: from behind the left ear, over the left shoulder,
    down the front of the chest."""
    ctrl = [v3(3.2, 6.5, 152.5), v3(7.0, 4.5, 144.0), v3(9.5, -1.0, 140.6),
            v3(10.5, -7.6, 132.0), v3(10.2, -11.2, 120.0), v3(9.8, -11.6, 110.0)]
    pts = []
    for i in range(len(ctrl) - 1):
        a, b = ctrl[i], ctrl[i + 1]
        for t in np.linspace(0, 1, 10, endpoint=False):
            pts.append(a + (b - a) * t)
    pts.append(ctrl[-1])
    pts = np.array(pts, dtype=F32)
    # Catmull-Rom style smoothing, then push off the body
    for _ in range(6):
        pts[1:-1] = pts[1:-1] * 0.5 + (pts[:-2] + pts[2:]) * 0.25
    for _ in range(8):
        d = body_fn(pts)
        eps = 0.05
        g = np.stack([(body_fn(pts + v3(*e)) - body_fn(pts - v3(*e))) / (2 * eps)
                      for e in ((eps, 0, 0), (0, eps, 0), (0, 0, eps))], axis=1)
        g /= np.linalg.norm(g, axis=1, keepdims=True)
        want = 2.4 + 0.4 * (pts[:, 2] < 141)
        push = np.clip(want - d, 0, None)
        pts += g * push[:, None]
        pts[1:-1] = pts[1:-1] * 0.6 + (pts[:-2] + pts[2:]) * 0.2
    return pts


def hair_braid(P, body, path, long_ears=False):
    """Hair.RopeBraid: hair swept back from the face into one thick braid over the shoulder."""
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    cap = _scalp(P, 1.45)
    c = v3(0, 1.3, 161.9)
    # swept-back grooves run from the hairline to the nape
    q = P - c
    cap = cap + 0.18 * np.abs(np.sin(q[:, 0] * 1.9 + 0.4 * q[:, 2])) ** 0.7 * (y < 6)
    # gathered low at the back towards the left
    knot = ellipsoid(P, v3(2.6, 7.8, 152.8), v3(3.4, 2.8, 3.2))
    h = smin(cap, knot, 2.5)
    fringe = lambda xx: 162.2 + 0.06 * xx ** 2 + _zigzag(xx, 3.0, 0.35, 0.8)
    side = lambda zz: -2.0 + 0.0 * zz
    h = smax(h, -_face_cut(P, fringe, side), 0.4)
    h = smax(h, -_ear_keepout(P, 0.35, long_ears), 0.5)
    # the braid: alternating lobes along the path
    n = len(path)
    s_len = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))])
    total = s_len[-1]
    braid = None
    lobe = 2.15
    k = 0
    for i in range(n - 1):
        a, b = path[i], path[i + 1]
        mid_s = (s_len[i] + s_len[i + 1]) / 2
        if mid_s > total - 3.5:
            continue
        t = mid_s / total
        r = 1.6 - 0.45 * t
        fwd = norm(b - a)
        side_v = norm(np.cross(fwd, v3(0, 0, 1)) + v3(0.0001, 0, 0))
        off = np.sin(mid_s / lobe * np.pi) * 0.55 * r
        e = ellipsoid(P, (a + b) / 2 + side_v * off, v3(r * 0.95, r * 0.8, r * 1.25),
                      frame(fwd, side_v))
        braid = e if braid is None else smin(braid, e, 0.25)
        k += 1
    # tie and a soft tuft at the end
    end = path[-1]
    tie_at = path[np.searchsorted(s_len, total - 3.4)]
    fwd = norm(path[-1] - path[-4])
    tie = cone(P, tie_at - fwd * 0.4, tie_at + fwd * 0.5, 1.05, 1.0)
    tuft = cone(P, tie_at + fwd * 0.3, end + fwd * 1.8, 1.05, 0.25)
    tuft = tuft + 0.15 * np.abs(np.sin((P @ norm(np.cross(fwd, v3(0, 0, 1)))) * 5))
    braid = smin(braid, tuft, 0.4)
    h = smin(h, braid, 1.2)
    h = smax(h, -(body + 0.5), 0.3)
    return h, tie
