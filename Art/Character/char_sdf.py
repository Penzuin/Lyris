"""Signed distance fields and marching cubes for the Lyris base character.

All shapes are built in centimetres in Blender's axes (X = character's left, -Y = forward,
Z = up). Distances are approximate (ellipsoids, round cones), which is all the smooth
blends need. Fields are evaluated on flat (N, 3) float32 point arrays.
"""

import numpy as np
from skimage import measure

F32 = np.float32


def v3(*a):
    return np.array(a, dtype=F32)


def length(q):
    return np.sqrt(np.einsum("ij,ij->i", q, q))


def norm(v):
    v = np.asarray(v, dtype=F32)
    return v / np.linalg.norm(v)


def frame(fwd, up):
    """Rotation matrix whose columns are local x (right), y (up), z (fwd)."""
    z = norm(fwd)
    x = norm(np.cross(up, z))
    y = np.cross(z, x)
    return np.stack([x, y, z], axis=1).astype(F32)


def smin(a, b, k):
    if k <= 0:
        return np.minimum(a, b)
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b + (a - b) * h - k * h * (1.0 - h)


def smax(a, b, k):
    return -smin(-a, -b, k)


def sphere(P, c, r):
    return length(P - c) - r


def ellipsoid(P, c, r, R=None):
    q = P - c
    if R is not None:
        q = q @ R
    r = np.asarray(r, dtype=F32)
    k0 = length(q / r)
    k1 = length(q / (r * r))
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-6)


def cone(P, a, b, ra, rb):
    """Capsule from a to b whose radius goes from ra to rb."""
    a = np.asarray(a, F32)
    b = np.asarray(b, F32)
    ba = b - a
    pa = P - a
    h = np.clip((pa @ ba) / float(ba @ ba), 0.0, 1.0)
    return length(pa - h[:, None] * ba) - (ra + (rb - ra) * h)


def flat_cone(P, a, b, ra, rb, flat_axis, flat=0.6):
    """Round cone squashed along `flat_axis` (a world direction) to `flat` of its width."""
    n = norm(flat_axis)
    d = (P @ n)[:, None] * n
    Q = P - d + d / flat
    a = np.asarray(a, F32)
    b = np.asarray(b, F32)
    a2 = a - (a @ n) * n + (a @ n) * n / flat
    b2 = b - (b @ n) * n + (b @ n) * n / flat
    return cone(Q, a2, b2, ra, rb) * flat


def bezier(p0, p1, p2, n):
    t = np.linspace(0, 1, n, dtype=F32)[:, None]
    return (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t ** 2 * p2


def tube(P, pts, radii, k=0.0, flat_axis=None, flat=1.0):
    d = None
    for i in range(len(pts) - 1):
        if flat_axis is not None:
            di = flat_cone(P, pts[i], pts[i + 1], radii[i], radii[i + 1], flat_axis, flat)
        else:
            di = cone(P, pts[i], pts[i + 1], radii[i], radii[i + 1])
        d = di if d is None else smin(d, di, k)
    return d


def plane(P, point, normal):
    """Positive on the side the normal points to."""
    return (P - np.asarray(point, F32)) @ norm(normal)


class Grid:
    def __init__(self, lo, hi, step):
        self.lo = np.asarray(lo, F32)
        self.step = float(step)
        self.shape = tuple(int(np.ceil((h - l) / step)) + 1 for l, h in zip(lo, hi))
        axes = [self.lo[i] + np.arange(self.shape[i], dtype=F32) * self.step for i in range(3)]
        X, Y, Z = np.meshgrid(*axes, indexing="ij")
        self.P = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)

    def mesh(self, d):
        vol = d.reshape(self.shape)
        verts, faces, _, _ = measure.marching_cubes(vol, 0.0, spacing=(self.step,) * 3)
        verts = verts + self.lo
        return verts.astype(np.float64), faces.astype(np.int64)


def march(fn, lo, hi, step, coarse=4, band=2.2, chunk=400_000):
    """Marching cubes of fn's zero level set. The field is evaluated exactly only in a
    narrow band near the surface (found on a grid `coarse` times coarser); elsewhere the
    trilinearly upsampled coarse field stands in, which only needs the right sign."""
    from scipy.ndimage import map_coordinates

    lo = np.asarray(lo, F32)
    shape = tuple(int(np.ceil((h - l) / step)) + 1 for l, h in zip(lo, hi))
    cstep = step * coarse
    cshape = tuple((s - 1) // coarse + 2 for s in shape)
    caxes = [lo[i] + np.arange(cshape[i], dtype=F32) * cstep for i in range(3)]
    CX, CY, CZ = np.meshgrid(*caxes, indexing="ij")
    CP = np.stack([CX.ravel(), CY.ravel(), CZ.ravel()], axis=1)
    cd = np.concatenate([fn(CP[i:i + chunk]) for i in range(0, len(CP), chunk)]).reshape(cshape)

    vol = np.empty(shape, dtype=F32)
    ii = np.arange(shape[1], dtype=F32) / coarse
    kk = np.arange(shape[2], dtype=F32) / coarse
    JJ, KK = np.meshgrid(ii, kk, indexing="ij")
    for i in range(shape[0]):
        ci = np.full(JJ.shape, i / coarse, dtype=F32)
        vol[i] = map_coordinates(cd, [ci, JJ, KK], order=1, mode="nearest")
    near = np.abs(vol) < band * cstep
    idx = np.nonzero(near)
    pts = np.stack([lo[a] + idx[a].astype(F32) * step for a in range(3)], axis=1)
    exact = np.concatenate([fn(pts[i:i + chunk]) for i in range(0, len(pts), chunk)]) if len(pts) else []
    vol[idx] = exact
    verts, faces, _, _ = measure.marching_cubes(vol, 0.0, spacing=(step,) * 3)
    return (verts + lo).astype(np.float64), faces.astype(np.int64)


def project(fn, V, iters=4, eps=0.02):
    """Moves points onto fn's zero level set along the field gradient."""
    V = np.asarray(V, F32).copy()
    for _ in range(iters):
        d = fn(V)
        g = np.stack([(fn(V + v3(*e)) - fn(V - v3(*e))) / (2 * eps)
                      for e in ((eps, 0, 0), (0, eps, 0), (0, 0, eps))], axis=1)
        gn = np.maximum((g * g).sum(1), 1e-8)
        V -= (d / gn)[:, None] * g
    return V.astype(np.float64)


def gradient(fn, V, eps=0.02):
    V = np.asarray(V, F32)
    g = np.stack([(fn(V + v3(*e)) - fn(V - v3(*e))) / (2 * eps)
                  for e in ((eps, 0, 0), (0, eps, 0), (0, 0, eps))], axis=1)
    return g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-8)
