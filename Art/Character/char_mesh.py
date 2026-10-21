"""Mesh building for the Lyris base character (T46): quad remeshing, real eye and mouth
openings with clean edge loops, and the wrist bridge between the quad body and the hands.

All work is in centimetres (QuadriFlow's tolerances are absolute, so it fails on the same
mesh in metres). Needs bpy (Blender as a Python module).
"""

import numpy as np

import bmesh
import bpy

import char_sdf as sdf
import char_shapes as cs


def _obj(name, V, faces):
    me = bpy.data.meshes.new(name)
    me.from_pydata(np.asarray(V, float).tolist(), [], [list(map(int, f)) for f in faces])
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    for o in list(bpy.context.scene.objects):
        if o is not None:
            o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    return ob


def largest_component(V, F):
    """Keeps only the biggest connected piece (drops slivers left by local cuts)."""
    nv = len(V)
    parent = np.arange(nv)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for f in F:
        r0 = find(f[0])
        for v in f[1:]:
            r = find(v)
            if r != r0:
                parent[r] = r0
    roots = np.array([find(i) for i in range(nv)])
    used = np.zeros(nv, bool)
    for f in F:
        used[f] = True
    vals, counts = np.unique(roots[used], return_counts=True)
    keep_root = vals[counts.argmax()]
    F = [f for f in F if roots[f[0]] == keep_root]
    return _compact(np.asarray(V), F)


def decimate(V, F, target):
    ob = _obj("dec", V, F)
    mod = ob.modifiers.new("dec", "DECIMATE")
    mod.ratio = min(1.0, target / max(len(F), 1))
    mod.use_collapse_triangulate = True
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    V2 = np.array([v.co[:] for v in me.vertices])
    F2 = [list(p.vertices) for p in me.polygons]
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)
    return V2, F2


def bm_from(V, faces):
    bm = bmesh.new()
    vs = [bm.verts.new(tuple(p)) for p in np.asarray(V, float)]
    for f in faces:
        try:
            bm.faces.new([vs[i] for i in f])
        except ValueError:
            pass
    bm.verts.ensure_lookup_table()
    return bm


def bm_arrays(bm):
    bm.verts.index_update()
    V = np.array([v.co[:] for v in bm.verts])
    F = [[v.index for v in f.verts] for f in bm.faces]
    return V, F


def quad_remesh(fn, lo, hi, step, voxel, target, symmetry=True):
    """Marching cubes -> voxel remesh (manifold) -> QuadriFlow -> snapped back onto the field.
    Returns V (cm) and quad faces."""
    V, F = sdf.march(fn, lo, hi, step)
    # QuadriFlow refuses meshes it judges non-manifold; the voxel remesh is manifold for most
    # voxel sizes but not all, so try a few nearby sizes (and seeds) until one works.
    for k, (vs, seed) in enumerate([(voxel, 1), (voxel * 0.93, 1), (voxel * 1.07, 2), (voxel * 0.86, 3),
                                     (voxel * 1.15, 4), (voxel * 0.8, 5)]):
        ob = _obj("qr", V, F)
        ob.data.remesh_voxel_size = vs
        bpy.ops.object.voxel_remesh()
        r = bpy.ops.object.quadriflow_remesh(target_faces=int(target), seed=seed, use_mesh_symmetry=symmetry)
        if "FINISHED" in r:
            break
        me = ob.data
        bpy.data.objects.remove(ob)
        bpy.data.meshes.remove(me)
    else:
        raise RuntimeError("QuadriFlow failed for every voxel size")
    me = ob.data
    V = np.array([v.co[:] for v in me.vertices])
    F = [list(p.vertices) for p in me.polygons]
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)
    V = sdf.project(fn, V, iters=4)
    return V, F


def bisect(V, F, z, keep="above"):
    bm = bm_from(V, F)
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, z), plane_no=(0, 0, 1),
                           clear_inner=(keep == "above"), clear_outer=(keep == "below"))
    V, F = bm_arrays(bm)
    bm.free()
    return V, F


def bisect_plane(V, F, co, no, keep_positive=True):
    bm = bm_from(V, F)
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=tuple(co), plane_no=tuple(no),
                           clear_inner=keep_positive, clear_outer=not keep_positive)
    V, F = bm_arrays(bm)
    bm.free()
    return V, F


def triangulate(V, F):
    bm = bm_from(V, F)
    bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method="BEAUTY", ngon_method="BEAUTY")
    V, F = bm_arrays(bm)
    bm.free()
    return V, np.array(F, dtype=np.int64)


def adjacency(nv, F):
    nbr = [set() for _ in range(nv)]
    for f in F:
        for i in range(len(f)):
            a, b = f[i], f[(i + 1) % len(f)]
            nbr[a].add(b)
            nbr[b].add(a)
    return [np.array(sorted(s), dtype=np.int64) for s in nbr]


def boundary_loops(F):
    """Ordered boundary loops (lists of vertex ids)."""
    cnt = {}
    nxt = {}
    for f in F:
        for i in range(len(f)):
            a, b = f[i], f[(i + 1) % len(f)]
            key = (min(a, b), max(a, b))
            cnt[key] = cnt.get(key, 0) + 1
            nxt[(a, b)] = True
    bedges = [(a, b) for (a, b) in nxt if cnt[(min(a, b), max(a, b))] == 1]
    succ = {}
    for a, b in bedges:
        succ.setdefault(b, []).append(a)  # reversed direction so loops run along the boundary
    loops, seen = [], set()
    for a, b in bedges:
        if a in seen:
            continue
        loop = [a]
        seen.add(a)
        cur = a
        while True:
            options = [x for x in succ.get(cur, []) if x not in seen]
            if not options:
                break
            cur = options[0]
            seen.add(cur)
            loop.append(cur)
        loops.append(loop)
    return loops


def relax(V, F, movable, iters=6, fn=None, amount=0.5):
    nb = adjacency(len(V), F)
    V = V.copy()
    idx = np.nonzero(movable)[0]
    for _ in range(iters):
        avg = np.array([V[nb[i]].mean(0) if len(nb[i]) else V[i] for i in idx])
        V[idx] = V[idx] * (1 - amount) + avg * amount
        if fn is not None:
            V[idx] = sdf.project(fn, V[idx], iters=2)
    return V


def subdivide_region(V, F, centres, levels, fn):
    """Subdivides the faces near `centres` ([(point, radius), ...]) `levels` times and snaps the
    new vertices onto the field: extra density only where the lids and lips need it."""
    V = np.asarray(V, float)
    for _ in range(levels):
        bm = bm_from(V, F)
        sel = set()
        for f in bm.faces:
            c = np.array(f.calc_center_median())
            if any(np.linalg.norm(c - np.asarray(p, float)) < r for p, r in centres):
                sel.update(f.edges)
        n0 = len(bm.verts)
        bmesh.ops.subdivide_edges(bm, edges=list(sel), cuts=1, use_grid_fill=True)
        V, F = bm_arrays(bm)
        bm.free()
        new = np.arange(n0, len(V))
        if len(new):
            V[new] = sdf.project(fn, V[new], iters=3)
    return V, F


# ----------------------------------------------------------------------------- eyes

def almond_uv(n=160):
    """Outline of the eye opening in the eye's (u, v) plane, as a closed polyline."""
    t = np.linspace(-1, 1, n)
    u = t * cs.EYE_W
    up = cs.EYE_HU * np.clip(1 - t * t, 0, 1) ** 0.58 * (1 - 0.08 * t) + 0.18 * t
    lo = -cs.EYE_HL * np.clip(1 - t * t, 0, 1) ** 0.8 + 0.18 * t
    return np.concatenate([np.stack([u, up], 1), np.stack([u[::-1], lo[::-1]], 1)[1:-1]])


def lid_point(side, uv, grow=0.06):
    """3D point on the eyeball shell (grown by `grow`) under eye-plane coordinates (u, v)."""
    R = cs.eye_rot(side).astype(float)
    c = cs.EYE[side].astype(float)
    r = cs.EYE_R.astype(float) + grow
    uv = np.atleast_2d(uv)
    u, v = uv[:, 0], uv[:, 1]
    s = np.clip(1 - (u / r[0]) ** 2 - (v / r[2]) ** 2, 0.0, None)
    depth = -np.sqrt(s) * r[1]
    q = np.stack([u, depth, v], 1)
    return c + q @ R.T


def eye_local(V, side):
    R = cs.eye_rot(side).astype(float)
    return (np.asarray(V, float) - cs.EYE[side].astype(float)) @ R


def cut_eye_holes(V, F, fn):
    """Removes the skin over each eye opening and snaps the new boundary onto the almond
    outline on the eyeball shell: a clean lid edge loop that seals against the eyeball."""
    V = np.asarray(V, float)
    F = [list(f) for f in F]
    outline = almond_uv()
    from matplotlib.path import Path
    poly = Path(outline)
    keep = np.ones(len(F), bool)
    for side in ("l", "r"):
        q = eye_local(V, side)
        cen = np.array([q[f].mean(0) for f in F])
        inside = poly.contains_points(cen[:, [0, 2]] * np.array([1.04, 1.04]))
        keep &= ~(inside & (cen[:, 1] < 0.8) & (np.abs(cen[:, 0]) < 3.5))
    F = [f for f, k in zip(F, keep) if k]
    V, F = _compact(V, F)
    loops = boundary_loops(F)
    near = np.zeros(len(V), bool)
    for side in ("l", "r"):
        c = cs.EYE[side].astype(float)
        best = min(loops, key=lambda L: np.linalg.norm(V[L].mean(0) - c))
        q = eye_local(V[best], side)
        uv = q[:, [0, 2]]
        # nearest point on the outline, in order along the loop
        d = ((uv[:, None, :] - outline[None, :, :]) ** 2).sum(2)
        j = d.argmin(1)
        snapped = outline[j]
        V[best] = lid_point(side, snapped, 0.05)
        qa = eye_local(V, side)
        near |= (np.abs(qa[:, 0]) < 4.2) & (np.abs(qa[:, 2]) < 3.4) & (qa[:, 1] < 2.0)
        near[best] = False
    V = relax(V, F, near, iters=5, fn=fn, amount=0.45)
    return V, F


# ----------------------------------------------------------------------------- mouth

def mouth_line(x):
    u = np.clip(np.asarray(x) / cs.MOUTH_HALF, -1, 1)
    return cs.MOUTH[2] - 0.02 - 0.06 * u * u


def cut_mouth(V, F, fn):
    """Opens the mouth line into a real lip loop (closed at rest; the Mouth_Open morph parts it)."""
    V = np.asarray(V, float)
    F = [list(f) for f in F]
    cen = np.array([V[f].mean(0) for f in F])
    x, y, z = cen[:, 0], cen[:, 1], cen[:, 2]
    hole = (np.abs(x) < cs.MOUTH_HALF * 0.92) & (np.abs(z - mouth_line(x)) < 0.2) & (y < cs.MOUTH[1] + 0.8)
    if not hole.any():
        return V, F
    F = [f for f, h in zip(F, hole) if not h]
    V, F = _compact(V, F)
    loops = boundary_loops(F)
    best = min(loops, key=lambda L: np.linalg.norm(V[L].mean(0) - cs.MOUTH.astype(float)))
    P = V[best]
    xs = np.clip(P[:, 0], -cs.MOUTH_HALF, cs.MOUTH_HALF)
    line = mouth_line(xs)
    upper = P[:, 2] >= line
    u = xs / cs.MOUTH_HALF
    gap = 0.012 * np.clip(1 - u * u, 0, 1)
    P[:, 0] = xs
    P[:, 2] = np.where(upper, line + gap, line - gap)
    P = sdf.project(fn, P, iters=3)
    nrm = sdf.gradient(fn, P).astype(float)
    P = P - nrm * 0.06                       # the lip edge rolls in a little
    V[best] = P
    near = (np.abs(V[:, 0]) < cs.MOUTH_HALF + 1.2) & (np.abs(V[:, 2] - cs.MOUTH[2]) < 1.2) & \
        (V[:, 1] < cs.MOUTH[1] + 0.9)
    near[best] = False
    V = relax(V, F, near, iters=4, fn=fn, amount=0.4)
    return V, F


def _compact(V, F):
    used = np.zeros(len(V), bool)
    for f in F:
        used[f] = True
    remap = -np.ones(len(V), dtype=np.int64)
    remap[used] = np.arange(used.sum())
    return V[used], [[int(remap[i]) for i in f] for f in F]


def mouth_interior(n=14):
    """A small mouth bag, upper and lower teeth bands and a tongue, kept behind the lips.
    Returns (V, tris, part id per tri: 0 bag, 1 teeth, 2 tongue)."""
    parts = []

    def ellipsoid_mesh(c, r, nu=n, nv=n // 2 + 2):
        Vs, Ts = [], []
        for i in range(nv + 1):
            th = np.pi * i / nv
            for j in range(nu):
                ph = 2 * np.pi * j / nu
                Vs.append(c + r * np.array([np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)]))
        for i in range(nv):
            for j in range(nu):
                a, b = i * nu + j, i * nu + (j + 1) % nu
                c2, d = a + nu, b + nu
                Ts += [(a, c2, d), (a, d, b)]
        return np.array(Vs), np.array(Ts)

    M = cs.MOUTH.astype(float)
    bag = ellipsoid_mesh(M + np.array([0, 2.05, -0.35]), np.array([1.25, 1.35, 1.0]))
    parts.append((bag[0], bag[1], 0))
    for k, (dz, h) in enumerate(((0.32, 0.32), (-0.42, 0.28))):
        nu = 12
        Vs, Ts = [], []
        for j in range(nu + 1):
            t = j / nu * 2 - 1
            x = t * 0.85
            y = M[1] + 0.55 + 0.45 * t * t
            for zz in (dz - h / 2, dz + h / 2):
                Vs.append([x, y, M[2] + zz])
        for j in range(nu):
            a = 2 * j
            Ts += [(a, a + 2, a + 3), (a, a + 3, a + 1)]
        parts.append((np.array(Vs), np.array(Ts), 1))
    tongue = ellipsoid_mesh(M + np.array([0, 1.6, -0.75]), np.array([0.85, 1.05, 0.32]), 12, 7)
    parts.append((tongue[0], tongue[1], 2))
    Vall, Tall, Pall = [], [], []
    off = 0
    for Vp, Tp, pid in parts:
        Vall.append(Vp)
        Tall.append(Tp + off)
        Pall.append(np.full(len(Tp), pid))
        off += len(Vp)
    return np.concatenate(Vall), np.concatenate(Tall), np.concatenate(Pall)


# ----------------------------------------------------------------------------- hands

def cut_local(V, F, co, no, radius):
    """Removes everything on the +no side of the plane through co, but only within `radius`
    of co (a wrist cut that leaves the thigh next to the hand alone). Returns V, F."""
    co = np.asarray(co, float)
    no = np.asarray(no, float) / np.linalg.norm(no)
    bm = bm_from(V, F)
    near = [f for f in bm.faces if np.linalg.norm(np.array(f.calc_center_median()) - co) < radius]
    geom = list({v for f in near for v in f.verts}) + list({e for f in near for e in f.edges}) + near
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=tuple(co), plane_no=tuple(no))
    kill = [f for f in bm.faces
            if np.linalg.norm(np.array(f.calc_center_median()) - co) < radius
            and (np.array(f.calc_center_median()) - co) @ no > 0]
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    V, F = bm_arrays(bm)
    bm.free()
    V, F = _compact(V, F)
    return largest_component(V, F)


def _ordered_loop(V, F, near):
    loops = boundary_loops(F)
    L = min(loops, key=lambda l: np.linalg.norm(V[l].mean(0) - near))
    return np.array(L)


def loft(Va, Fa, Vb, Fb, near, axis):
    """Joins mesh b onto mesh a by triangulating a strip between the open loop of each nearest
    `near`. Both loops are walked by arc length, the same way round `axis`, from aligned starts."""
    axis = np.asarray(axis, float) / np.linalg.norm(axis)
    A = _ordered_loop(Va, Fa, near)
    B = _ordered_loop(Vb, Fb, near)

    def orient(L, P):
        c = P[L].mean(0)
        ref = P[L[0]] - c
        ref -= axis * (ref @ axis)
        ang = []
        for i in L:
            r = P[i] - c
            r -= axis * (r @ axis)
            ang.append(np.arctan2(np.cross(ref, r) @ axis, ref @ r))
        ang = np.unwrap(np.array(ang))
        if ang[-1] < ang[0]:
            L = L[::-1]
        return L

    A = orient(A, Va)
    B = orient(B, Vb)
    # start B at the vertex closest (by angle) to A's first vertex
    ca, cb = Va[A].mean(0), Vb[B].mean(0)

    def angle_of(p, c, ref):
        r = p - c
        r -= axis * (r @ axis)
        return np.arctan2(np.cross(ref, r) @ axis, ref @ r)

    ref = Va[A[0]] - ca
    ref -= axis * (ref @ axis)
    k = int(np.argmin([abs(angle_of(Vb[i], cb, ref)) for i in B]))
    B = np.roll(B, -k)

    def params(L, P):
        pts = np.concatenate([P[L], P[L[:1]]])
        seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        t = np.concatenate([[0], np.cumsum(seg)])
        return t[:-1] / t[-1]

    ta, tb = params(A, Va), params(B, Vb)
    off = len(Va)
    V = np.concatenate([Va, Vb])
    F = [list(f) for f in Fa] + [[i + off for i in f] for f in Fb]
    i = j = 0
    na, nb = len(A), len(B)
    tris = []
    while i < na or j < nb:
        a0, a1 = A[i % na], A[(i + 1) % na]
        b0, b1 = B[j % nb] + off, B[(j + 1) % nb] + off
        ta_next = ta[i + 1] if i + 1 < na else 1.0
        tb_next = tb[j + 1] if j + 1 < nb else 1.0
        if j >= nb or (i < na and ta_next <= tb_next):
            tris.append([a0, a1, b0])
            i += 1
        else:
            tris.append([a0, b1, b0])
            j += 1
    # winding: match the arm side's faces (outward normals)
    probe = np.array(V[tris[0]])
    n_strip = np.cross(probe[1] - probe[0], probe[2] - probe[0])
    out = probe.mean(0) - (Va[A].mean(0) + Vb[B].mean(0)) / 2
    out -= axis * (out @ axis)
    if n_strip @ out < 0:
        tris = [[t[0], t[2], t[1]] for t in tris]
    return V, F + tris
