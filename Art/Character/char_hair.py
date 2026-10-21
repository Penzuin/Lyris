"""Hair built from chunky swept locks (T46 art pass).

Each lock is a strand grown from the scalp: it starts on the crown, follows the skull, then
falls under gravity, pushed off the head, body and ears so it drapes naturally. The lock's
field is a flattened tube along the strand that is wide at the root and tapers to a rounded
point, so every edge, fringe tip and hem is smooth and readable in silhouette (no zigzag cuts).
Locks are blended with a small smooth-min so the grooves between them stay visible, over a
thin cap that hides the scalp.

Design space as in char_shapes (cm, X = character's left, -Y forward, Z up), before
char_shapes.head_xform grows the head.
"""

import numpy as np

import char_shapes as cs
from char_sdf import F32, ellipsoid, norm, smax, smin, v3

CRANIUM_C = np.array([0.0, 0.9, 162.6])
CRANIUM_R = np.array([8.2, 8.8, 9.4])


def scalp_point(az_deg, el_deg, lift=0.0):
    """Point on the skull at azimuth (0 = front, +90 = character's left, 180 = back) and
    elevation (90 = crown, 0 = level with the cranium centre)."""
    a, e = np.radians(az_deg), np.radians(el_deg)
    d = np.array([np.sin(a) * np.cos(e), -np.cos(a) * np.cos(e), np.sin(e)])
    return CRANIUM_C + d * (CRANIUM_R + lift)


def _keepout(P, long_ears, ears=True):
    """Distance a strand must keep: the broad frame's body and the head, plus (optionally)
    the ears. Styles that fall over the ears leave them out and cut an ear slot instead."""
    d = cs.frame_sdf(P.astype(F32), "FrameB").astype(np.float64)
    if not ears:
        return d
    e = cs._ear_keepout(P.astype(F32), 0.15, long_ears).astype(np.float64)
    return np.minimum(d, e)


def _grad(fn, P, eps=0.05):
    g = np.stack([(fn(P + e) - fn(P - e)) / (2 * eps) for e in np.eye(3) * eps], axis=1)
    return g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-9)


def grow(starts, dirs, lengths, clearance, long_ears, step=0.7, stiff=None, attract=None,
         z_stop=None, curl_in=None, ears=False):
    """Grows all strands together. Returns a list of (n_i, 3) point arrays.

    stiff: per strand, how long (cm) the strand keeps its start direction before gravity wins.
    attract: optional per-strand target point the strand bends towards (braids, buns).
    z_stop: optional per-strand height at which the strand ends.
    curl_in: optional per-strand amount the tip turns back towards the neck (bob ends)."""
    n = len(starts)
    stiff = np.full(n, 3.0) if stiff is None else np.asarray(stiff, float)
    P = np.array(starts, float)
    D = np.array([norm(d) for d in dirs], float)
    L = np.asarray(lengths, float)
    out = [[p.copy()] for p in P]
    done = np.zeros(n, bool)
    s = 0.0
    fn = lambda X: _keepout(X, long_ears, ears)
    while not done.all():
        s += step
        g = np.array([0.0, 0.0, -1.0])
        w = np.clip(s / np.maximum(stiff, 0.1), 0, 1)[:, None] * 0.35
        D = D * (1 - w) + g * w
        if attract is not None:
            for i, t in enumerate(attract):
                if t is not None:
                    to = np.asarray(t) - P[i]
                    dist = np.linalg.norm(to)
                    if dist > 1e-6:
                        D[i] = D[i] * 0.55 + to / dist * 0.45
        if curl_in is not None:
            for i, c in enumerate(curl_in):
                if c and L[i] - s < 4.0:
                    inward = np.array([-P[i, 0], 1.0 - P[i, 1], 0.0])
                    inward /= max(np.linalg.norm(inward), 1e-6)
                    D[i] = D[i] + inward * c * 0.25
        D /= np.linalg.norm(D, axis=1, keepdims=True)
        Pn = P + D * step
        for _ in range(3):
            k = fn(Pn)
            push = clearance - k
            m = push > 0
            if not m.any():
                break
            Pn[m] += _grad(fn, Pn[m]) * push[m, None]
        D = Pn - P
        D /= np.maximum(np.linalg.norm(D, axis=1, keepdims=True), 1e-9)
        P = Pn
        for i in range(n):
            if done[i]:
                continue
            out[i].append(P[i].copy())
            if s >= L[i] or (z_stop is not None and z_stop[i] is not None and P[i, 2] < z_stop[i]):
                done[i] = True
    strands = []
    for pts in out:
        pts = np.array(pts)
        for _ in range(4):
            pts[1:-1] = pts[1:-1] * 0.5 + (pts[:-2] + pts[2:]) * 0.25
        strands.append(pts)
    return strands


class Lock:
    def __init__(self, pts, width, thick, taper=0.35, flat_ref=None, swell=0.15):
        self.pts = np.asarray(pts, float)
        seg = np.linalg.norm(np.diff(self.pts, axis=0), axis=1)
        self.s = np.concatenate([[0], np.cumsum(seg)])
        self.len = self.s[-1]
        t = self.s / max(self.len, 1e-6)
        # wide root, a little fuller in the middle, rounded taper to a soft point
        tip = np.clip((1 - t) / taper, 0, 1)
        prof = (0.75 + 0.25 * np.clip(t / 0.2, 0, 1)) * (1 + swell * np.sin(np.pi * t)) * np.sqrt(tip * (2 - tip))
        self.w = np.maximum(width * prof, 0.08)
        self.th = np.maximum(thick * (0.6 + 0.4 * prof / max(prof.max(), 1e-6)), 0.07)
        self.th = np.minimum(self.th, self.w)
        ref = CRANIUM_C if flat_ref is None else np.asarray(flat_ref, float)
        # flatten each lock against the head: the thin axis points away from the head centre
        self.nrm = []
        for i in range(len(self.pts)):
            a = self.pts[i] - ref
            a[2] *= 0.35 if self.pts[i, 2] < 150 else 1.0
            self.nrm.append(a / max(np.linalg.norm(a), 1e-6))
        self.nrm = np.array(self.nrm)
        pad = width + 0.6
        self.lo = self.pts.min(0) - pad
        self.hi = self.pts.max(0) + pad

    def query(self, P):
        """Distance to the lock, plus the arc-length param t (0 root .. 1 tip) and the
        normalised across-lock offset (0 centre .. 1 edge) of the closest point."""
        best = np.full(len(P), 1e9)
        bt = np.zeros(len(P))
        bx = np.zeros(len(P))
        for i in range(len(self.pts) - 1):
            a, b = self.pts[i], self.pts[i + 1]
            ab = b - a
            L2 = max(ab @ ab, 1e-12)
            h = np.clip(((P - a) @ ab) / L2, 0, 1)
            c = a + h[:, None] * ab
            q = P - c
            n = self.nrm[i] * (1 - h[:, None]) + self.nrm[i + 1] * h[:, None]
            n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
            qn = (q * n).sum(1)
            qa = q - n * qn[:, None]
            r = self.w[i] * (1 - h) + self.w[i + 1] * h
            th = self.th[i] * (1 - h) + self.th[i + 1] * h
            # ellipse cross-section: across = r, thickness = th (approximate distance)
            e = np.sqrt((np.linalg.norm(qa, axis=1) / r) ** 2 + (qn / th) ** 2)
            d = (e - 1) * np.minimum(r, th) * 1.0
            m = d < best
            best[m] = d[m]
            bt[m] = (self.s[i] + h[m] * np.sqrt(L2)) / max(self.len, 1e-6)
            bx[m] = np.clip(np.linalg.norm(qa[m], axis=1) / r[m], 0, 1)
        return best, bt, bx


class HairField:
    def __init__(self, locks, cap_fn, k_lock=0.22, k_cap=0.7, cut_fn=None):
        self.locks, self.cap_fn, self.k_lock, self.k_cap, self.cut_fn = locks, cap_fn, k_lock, k_cap, cut_fn

    def lock_field(self, P):
        P = np.asarray(P, float)
        d = np.full(len(P), 1e3)
        lid = np.full(len(P), -1)
        tt = np.zeros(len(P))
        xx = np.ones(len(P))
        for k, lk in enumerate(self.locks):
            m = np.all((P >= lk.lo) & (P <= lk.hi), axis=1)
            if not m.any():
                continue
            dk, tk, xk = lk.query(P[m])
            cur = d[m]
            closer = dk < cur
            idx = np.nonzero(m)[0]
            lid[idx[closer]] = k
            tt[idx[closer]] = tk[closer]
            xx[idx[closer]] = xk[closer]
            d[m] = smin(cur.astype(F32), dk.astype(F32), self.k_lock).astype(np.float64)
        return d, lid, tt, xx

    def __call__(self, P):
        d, _, _, _ = self.lock_field(P)
        if self.cap_fn is not None:
            d = smin(d.astype(F32), self.cap_fn(P).astype(F32), self.k_cap)
        if self.cut_fn is not None:
            d = smax(d.astype(F32), -self.cut_fn(P).astype(F32), 0.45)
        return np.asarray(d, F32)


# ----------------------------------------------------------------------------- styles

def cap(P, grow=0.85, hairline_z=163.2, back_open=False):
    """Thin hair cap over the cranium, ending at a soft hairline above the forehead and in
    front of the ears."""
    P = np.asarray(P, F32)
    c = ellipsoid(P, v3(*CRANIUM_C) + v3(0, 0.25, 0.25), v3(*(CRANIUM_R + grow)))
    shell = smax(c, -(c + 1.4), 0.3)
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    # hairline: a curve from the temples over the forehead
    hl = hairline_z + 0.03 * x * x
    front = np.maximum(hl - z, -(y + 1.0))           # in front of y = -1 and below the hairline
    shell = smax(shell, -front, 0.8)
    shell = smax(shell, 152.0 - z, 1.0)
    return shell


def _fan(az_list, el, lift=0.2):
    return [scalp_point(a, el, lift) for a in az_list]


def _tangent_down(p, az_deg, forward=0.0):
    """Direction along the skull from p towards the nape/sides, with some forward push."""
    a = np.radians(az_deg)
    out = np.array([np.sin(a), -np.cos(a), 0.0])
    return norm(out * (0.65 + forward) + np.array([0, 0, -0.75]))


def style_locks(style, long_ears):
    clearance = 1.0
    if style == "LamplighterBob":
        back = np.linspace(66, 294, 17)
        starts = _fan(back, 60)
        dirs = [_tangent_down(p, a) for p, a in zip(starts, back)]
        lens = [22.0] * len(back)
        zst = [148.4 + 0.5 * np.cos(np.radians(a)) for a in back]
        locks_a = grow(starts, dirs, lens, 1.35, long_ears, stiff=[4.0] * len(back), z_stop=zst,
                       curl_in=[0.6] * len(back))
        sides = [40, 50, 60, -40, -50, -60]
        s2 = _fan(sides, 60)
        d2 = [_tangent_down(p, a, -0.1) for p, a in zip(s2, sides)]
        locks_b = grow(s2, d2, [24] * 6, 1.1, long_ears, stiff=[2.5] * 6,
                       z_stop=[149.6, 149.0, 148.6, 149.6, 149.0, 148.6], curl_in=[0.5] * 6)
        # the fringe sweeps from a side part (character's left) across the brow
        fr = [-40, -28, -16, -4, 8, 20, 32, 44]
        s3 = [scalp_point(a, 66 - 0.06 * abs(a), 0.3) for a in fr]
        d3 = [norm(np.array([np.sin(np.radians(a)) * 0.45 - 0.15, -1.0, 0.15])) for a in fr]
        locks_c = grow(s3, d3, [24] * 8, 0.8, long_ears, stiff=[5.0] * 8,
                       z_stop=[163.0 + 0.0013 * a * a + 0.008 * a for a in fr])
        L = [Lock(p, 1.7, 0.75) for p in locks_a] + [Lock(p, 1.5, 0.65) for p in locks_b] + \
            [Lock(p, 2.0 if abs(a) < 25 else 1.7, 0.6, taper=0.3, swell=0.25) for p, a in zip(locks_c, fr)]
        return HairField(L, lambda P: cap(P, 0.8), cut_fn=lambda P: cs._ear_keepout(P, 0.2, long_ears)), 171.5, 148.0
    if style == "FallingWater":
        back = np.linspace(66, 294, 17)
        starts = _fan(back, 60)
        dirs = [_tangent_down(p, a) for p, a in zip(starts, back)]
        zst = [114.5 + 1.2 * np.cos(np.radians(a * 4)) + 0.02 * abs(180 - a) for a in back]
        locks_a = grow(starts, dirs, [62.0] * len(back), 1.35, long_ears, stiff=[4.0] * len(back), z_stop=zst)
        sides = [40, 50, 60, -40, -50, -60]
        s2 = _fan(sides, 60)
        d2 = [_tangent_down(p, a, -0.1) for p, a in zip(s2, sides)]
        locks_b = grow(s2, d2, [44] * 6, 1.1, long_ears, stiff=[2.5] * 6,
                       z_stop=[128, 125, 122, 128, 125, 122])
        fr = [-40, -28, -16, -4, 8, 20, 32, 44]
        s3 = [scalp_point(a, 66 - 0.06 * abs(a), 0.3) for a in fr]
        d3 = [norm(np.array([np.sin(np.radians(a)) * 0.3 + 0.2, -1.0, 0.15])) for a in fr]
        locks_c = grow(s3, d3, [24] * 8, 0.8, long_ears, stiff=[5.0] * 8,
                       z_stop=[162.2 + 0.0011 * a * a - 0.01 * a for a in fr])
        L = [Lock(p, 1.8, 0.75, taper=0.16) for p in locks_a] + [Lock(p, 1.5, 0.65, taper=0.18) for p in locks_b] + \
            [Lock(p, 2.0 if abs(a) < 25 else 1.7, 0.6, taper=0.3, swell=0.25) for p, a in zip(locks_c, fr)]
        return HairField(L, lambda P: cap(P, 0.8), cut_fn=lambda P: cs._ear_keepout(P, 0.2, long_ears)), 171.5, 113.0
    if style == "RopeBraid":
        # hair swept back off the face along the skull into a low knot behind the left ear
        knot = np.array([2.6, 8.4, 152.6])
        k_az, k_el = 165.0, -38.0
        L = []
        for a0 in np.linspace(-70, 70, 11):
            for e0 in (38.0, 62.0):
                n = 26
                t = np.linspace(0, 1, n)
                if a0 >= 0:
                    az = a0 + (k_az - a0) * t
                else:
                    az = a0 + ((k_az - 360) - a0) * t
                el = e0 + (k_el - e0) * t + 18 * np.sin(np.pi * t) * (1 if e0 > 50 else 0.4)
                pts = np.array([scalp_point(azi, eli, 0.55) for azi, eli in zip(az, el)])
                pts = np.concatenate([pts, (pts[-1] + (knot - pts[-1]) * 0.5)[None, :], knot[None, :]])
                L.append(Lock(pts, 1.6, 0.45, taper=0.15, swell=0.1))
        wisp = [scalp_point(a, 18, 0.1) for a in (-58, 58)]
        locks_c = grow(wisp, [norm(np.array([np.sign(x[0]) * 0.2, -0.4, -1.0])) for x in wisp], [11, 11], 0.8,
                       long_ears, stiff=[3, 3], z_stop=[152.0, 152.0])
        L += [Lock(p, 0.6, 0.32, taper=0.6) for p in locks_c]
        L.append(Lock(np.array([knot + (0, -0.6, 0.8), knot, knot + (0.6, 0.4, -1.2)]), 2.4, 1.6, taper=0.5))
        return HairField(L, lambda P: cap(P, 0.6, 163.6), k_lock=0.3,
                         cut_fn=lambda P: cs._ear_keepout(P, 0.3, long_ears)), 171.5, 108.0
    raise KeyError(style)


def braid_field(path):
    """Rope braid: alternating soft lobes along the path, a tie, and a tapered tuft."""
    s_len = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))])
    total = s_len[-1]
    lobes = []
    lobe = 2.2
    s = 1.0
    k = 0
    while s < total - 4.0:
        i = np.searchsorted(s_len, s) - 1
        i = int(np.clip(i, 0, len(path) - 2))
        h = (s - s_len[i]) / max(s_len[i + 1] - s_len[i], 1e-6)
        c = path[i] + (path[i + 1] - path[i]) * h
        fwd = norm(path[i + 1] - path[i])
        side = norm(np.cross(fwd, np.array([0, 0, 1.0])) + np.array([1e-4, 0, 0]))
        t = s / total
        r = 1.55 - 0.45 * t
        off = (1 if k % 2 else -1) * 0.5 * r
        lobes.append((c + side * off, fwd, side, r))
        s += lobe * 0.55
        k += 1
    tie_at = path[np.searchsorted(s_len, total - 3.6)]
    fwd_end = norm(path[-1] - path[-4])

    def f(P):
        P = np.asarray(P, F32)
        d = None
        for c, fwd, side, r in lobes:
            R = np.stack([side, np.cross(fwd, side), fwd], axis=1).astype(F32)
            e = ellipsoid(P, v3(*c), v3(r * 0.95, r * 0.78, r * 1.25), R)
            d = e if d is None else smin(d, e, 0.2)
        from char_sdf import cone
        tuft = cone(P, v3(*(tie_at + fwd_end * 0.2)), v3(*(path[-1] + fwd_end * 2.0)), 1.0, 0.18)
        d = smin(d, tuft, 0.35)
        return d

    def tie(P):
        from char_sdf import cone
        P = np.asarray(P, F32)
        return cone(P, v3(*(tie_at - fwd_end * 0.45)), v3(*(tie_at + fwd_end * 0.45)), 1.12, 1.08)

    return f, tie
