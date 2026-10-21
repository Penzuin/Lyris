"""Generates the Lyris base character for the character creator (task T25).

Look: storybook painterly, Genshin-like softness with Lyris's own warmth. An adult figure about
6.9 heads tall (172 cm, head 25 cm), soft simplified forms, large readable eyes set in real
sockets, a small button nose, small soft lips, painted rosiness instead of modelled detail.
Two body frames from design/character_creator.md, FrameA "Willow" (narrower, lighter) and
FrameB "Oak" (broader, sturdier). They are cosmetic only and share ONE skeleton and ONE head.

How it is made: every part is a signed distance field (char_shapes.py) turned into a mesh by
marching cubes, cleaned and decimated in Blender (bpy), UV-unwrapped, painted from 3D
position (char_paint.py), skinned with distance-based weights and given morph targets that
are analytic warps of space (char_morphs.py), so one morph moves the head, eyes, brows,
lashes, ears and hair together. Blender then writes glTF 2.0 (.glb) and FBX.

Skeleton (char_rig.py): the UE5 mannequin's bone names and hierarchy (root, pelvis,
spine_01..05, neck_01..02, head, clavicles, arms, hands with thumb/index/middle/ring/pinky
chains and metacarpals, thighs, calves, feet, balls, plus the ik_* helper bones) in an
A-pose close to the mannequin's.

Coordinates. Built in Blender's axes, centimetres: X = the character's left, -Y = the way it
faces, Z up, feet on Z = 0. Exported in metres (glTF) / centimetres (FBX). Imported into
Unreal this is the mannequin's own asset space: Z up, the character FACES +Y and its left
is +X, exactly like SKM_Manny (which is why the template's Character Blueprint turns the
mesh -90 degrees yaw so the pawn faces +X). Use the same -90 yaw here.

Outputs (next to this script):
  SKM_Lyris_Body_FrameA.glb / _FrameB.glb   skin body per frame (neck down)
  SKM_Lyris_Head.glb                        shared head with ears (two material sections)
  SKM_Lyris_Eyes.glb, _Brows.glb, _Lashes.glb
  SKM_Lyris_Hair_<Style>.glb (+ _LongEar)   LamplighterBob, FallingWater, RopeBraid; the
                                            _LongEar variants leave room for elf and Deepkin ears
  SKM_Lyris_Outfit_PlainTraveller_FrameA.glb / _FrameB.glb
  fbx/*.fbx                                 the same parts as FBX
  textures/*.png                            painted base colours and masks (see README.md)
  morph_targets.md                          slider -> morph mapping for the Player lane
  character_meta.json                       triangle counts, morphs per mesh, bone list
  preview*.png                              Cycles renders for review

Run:  python3 make_character.py      (needs `pip install bpy` for Python 3.13: Blender 5.2)
Takes about 15 minutes on 2 cores.
"""

import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


import bpy  # noqa: E402
import bmesh  # noqa: E402  (available once bpy is imported)
from mathutils import Vector  # noqa: E402

import char_morphs as cm  # noqa: E402
import char_paint as cp  # noqa: E402
import char_rig as rig  # noqa: E402
import char_sdf as sdf  # noqa: E402
import char_shapes as cs  # noqa: E402

TEX = os.path.join(HERE, "textures")
FBX = os.path.join(HERE, "fbx")
FAST = "--fast" in sys.argv          # quick look: coarser grids, fewer renders
T0 = time.time()

# Triangle budgets (body + head stays under 30k; see README)
BUDGET = {"body": 17000, "head": 9500, "hair": 7000, "shirt": 5200, "trousers": 3600,
          "belt": 500, "boots": 1800}
STEP = {"body": 0.5, "head": 0.16, "hair": 0.2, "outfit": 0.35}
if FAST:
    STEP = {"body": 0.8, "head": 0.3, "hair": 0.4, "outfit": 0.8}

J, PARENTS, TAILS, HAND = rig.build_joints()
DEFORM = [b for b in PARENTS if b != "root" and not b.startswith("ik_")]


def log(msg):
    print(f"[{time.time() - T0:6.1f}s] {msg}", flush=True)


# ----------------------------------------------------------------------------- Blender mesh helpers

def to_blender_mesh(name, V, faces):
    me = bpy.data.meshes.new(name)
    me.from_pydata((np.asarray(V) / 100.0).tolist(), [], np.asarray(faces).tolist())
    me.update()
    return me


def read_mesh(me):
    """Triangulated mesh data back to numpy: V (cm), tris (vertex ids), corner UVs or None."""
    n = len(me.vertices)
    co = np.empty(n * 3)
    me.vertices.foreach_get("co", co)
    V = co.reshape(-1, 3) * 100.0
    me.calc_loop_triangles()
    nt = len(me.loop_triangles)
    tri = np.empty(nt * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("vertices", tri)
    loops = np.empty(nt * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("loops", loops)
    uv = None
    if me.uv_layers:
        luv = np.empty(len(me.loops) * 2)
        me.uv_layers[0].data.foreach_get("uv", luv)
        uv = luv.reshape(-1, 2)[loops].reshape(-1, 3, 2)
    return V, tri.reshape(-1, 3), uv


def tmp_object(me):
    ob = bpy.data.objects.new(me.name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def clean_cut_decimate(V, faces, target, cut=None, keep_largest=True):
    """Bisect at the neck plane (cut = ('above'|'below', z)), drop stray islands, decimate to
    `target` triangles. Returns V, tris."""
    me = to_blender_mesh("tmp", V, faces)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    if cut:
        side, z = cut
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, z / 100.0), plane_no=(0, 0, 1),
                               clear_inner=(side == "above"), clear_outer=(side == "below"))
    if keep_largest:
        bm.verts.ensure_lookup_table()
        seen, islands = set(), []
        for v in bm.verts:
            if v in seen:
                continue
            stack, isl = [v], []
            seen.add(v)
            while stack:
                x = stack.pop()
                isl.append(x)
                for e in x.link_edges:
                    o = e.other_vert(x)
                    if o not in seen:
                        seen.add(o)
                        stack.append(o)
            islands.append(isl)
        islands.sort(key=len, reverse=True)
        small = [v for isl in islands[1:] if len(isl) < 0.02 * len(islands[0]) for v in isl]
        if small:
            bmesh.ops.delete(bm, geom=small, context="VERTS")
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(me)
    bm.free()
    ob = tmp_object(me)
    ntri = len(me.polygons)
    if ntri > target:
        mod = ob.modifiers.new("dec", "DECIMATE")
        mod.decimate_type = "COLLAPSE"
        mod.ratio = target / ntri
        mod.use_collapse_triangulate = True
        dg = bpy.context.evaluated_depsgraph_get()
        me2 = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    else:
        me2 = me
    V2, tri, _ = read_mesh(me2)
    bpy.data.objects.remove(ob)
    return V2, tri


def smart_uv(V, tris, angle=66.0, margin=0.004):
    me = to_blender_mesh("uvtmp", V, tris)
    ob = tmp_object(me)
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.view_layer.objects:
        o.select_set(o == ob)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(angle), island_margin=margin, scale_to_bounds=True)
    bpy.ops.object.mode_set(mode="OBJECT")
    _, tri2, uv = read_mesh(me)
    bpy.data.objects.remove(ob)
    assert (tri2 == tris).all()
    return uv


def snap_boundary(V, tris, target_loop):
    """Moves the open boundary vertices of a mesh onto a polyline (the other mesh's boundary)."""
    edges = np.sort(np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]]), axis=1)
    uniq, cnt = np.unique(edges, axis=0, return_counts=True)
    bverts = np.unique(uniq[cnt == 1])
    A = target_loop[:-1]
    B = target_loop[1:]
    for i in bverts:
        p = V[i]
        ab = B - A
        t = np.clip(((p - A) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-12), 0, 1)
        q = A + ab * t[:, None]
        V[i] = q[np.argmin(((q - p) ** 2).sum(1))]
    return V, bverts


def boundary_ids(tris):
    edges = np.sort(np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]]), axis=1)
    uniq, cnt = np.unique(edges, axis=0, return_counts=True)
    return np.unique(uniq[cnt == 1])


def project_keep_seam(fn, V, tris):
    """Snaps vertices back onto the field after decimation; the neck seam stays on its plane."""
    b = boundary_ids(tris)
    P = sdf.project(fn, V, iters=2)
    P[b, 2] = cs.NECK_CUT_Z
    return P


def boundary_polyline(V, tris):
    edges = np.sort(np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]]), axis=1)
    uniq, cnt = np.unique(edges, axis=0, return_counts=True)
    b = uniq[cnt == 1]
    nbr = {}
    for a, c in b:
        nbr.setdefault(a, []).append(c)
        nbr.setdefault(c, []).append(a)
    start = b[0][0]
    loop, prev, cur = [start], None, start
    while True:
        nxt = [x for x in nbr[cur] if x != prev]
        if not nxt or nxt[0] == start:
            break
        prev, cur = cur, nxt[0]
        loop.append(cur)
    loop.append(start)
    return V[loop]


# ----------------------------------------------------------------------------- skin weights

RADIUS = {"pelvis": 11, "spine_01": 10.5, "spine_02": 10.5, "spine_03": 11.5, "spine_04": 12,
          "spine_05": 11, "neck_01": 5, "neck_02": 5, "head": 8, "clavicle": 4.5, "upperarm": 4.6,
          "lowerarm": 3.4, "hand": 2.6, "metacarpal": 0.0, "thumb": 0.9, "index": 0.7, "middle": 0.7,
          "ring": 0.7, "pinky": 0.6, "thigh": 7.0, "calf": 4.6, "foot": 3.0, "ball": 2.8}


def bone_radius(b):
    if "metacarpal" in b:
        return RADIUS["metacarpal"]
    for k, r in RADIUS.items():
        if b == k or b.startswith(k + "_"):
            return r
    return 2.0


def seg_dist(V, a, b):
    ab = b - a
    t = np.clip(((V - a) @ ab) / max(ab @ ab, 1e-9), 0, 1)
    return np.linalg.norm(V - (a + t[:, None] * ab), axis=1)


def skin_weights(V, bones=None, power=6.0, floor=0.3, head_override=True):
    """Distance-to-bone-capsule weights, max 4 influences. Pure function of position, so the
    head and body agree exactly along the neck seam."""
    bones = [b for b in (bones or DEFORM) if "metacarpal" not in b]
    W = np.zeros((len(V), len(bones)))
    for k, b in enumerate(bones):
        d = seg_dist(V, J[b], TAILS[b]) - 0.6 * bone_radius(b)
        W[:, k] = 1.0 / np.maximum(d, floor) ** power
    # arms never take weight from the legs and the other way round (A-pose hands hang near hips)
    side_x = V[:, 0]
    for k, b in enumerate(bones):
        if b.endswith("_l"):
            W[side_x < -1.0, k] = 0.0
        if b.endswith("_r"):
            W[side_x > 1.0, k] = 0.0
        limb = b.split("_")[0]
        if limb in ("thigh", "calf", "foot", "ball"):
            W[V[:, 2] > 104, k] = 0
        if limb in ("upperarm", "lowerarm", "hand", "thumb", "index", "middle", "ring", "pinky"):
            W[np.abs(V[:, 0]) < 9.0, k] = 0
    W /= np.maximum(W.sum(1, keepdims=True), 1e-30)
    if head_override and "head" in bones:
        t = cp.smoothstep(148.5, 151.5, V[:, 2])[:, None]
        h = np.zeros_like(W)
        h[:, bones.index("head")] = 1
        W = W * (1 - t) + h * t
    order = np.argsort(-W, axis=1)[:, :4]
    top = np.take_along_axis(W, order, 1)
    top[top < 0.02] = 0
    top /= np.maximum(top.sum(1, keepdims=True), 1e-9)
    return [[(bones[order[i, j]], float(top[i, j])) for j in range(4) if top[i, j] > 0] for i in range(len(V))]


def transfer_weights(V, srcV, srcW, k=4):
    from scipy.spatial import cKDTree
    tree = cKDTree(srcV)
    d, idx = tree.query(V, k=k)
    out = []
    for i in range(len(V)):
        acc = {}
        w = 1.0 / np.maximum(d[i], 0.05) ** 2
        for j in range(k):
            for b, x in srcW[idx[i, j]]:
                acc[b] = acc.get(b, 0.0) + x * w[j]
        items = sorted(acc.items(), key=lambda t: -t[1])[:4]
        s = sum(x for _, x in items)
        out.append([(b, x / s) for b, x in items])
    return out


def rigid_weights(n, bone="head"):
    return [[(bone, 1.0)] for _ in range(n)]


# ----------------------------------------------------------------------------- morphs per mesh

def eval_morphs(V, N, groups, extra=None, region="head"):
    """Evaluates every registered morph in `groups` on these vertices; drops ones that do not
    move this mesh. Returns {name: delta (cm)}."""
    out = {}
    if region == "head":
        fade = cm.seam(V)[:, None]
    else:
        fade = (1 - cp.smoothstep(139.5, 141.5, V[:, 2]))[:, None]
    for mm in cm.by_group(*groups):
        D = mm.fn(V, N) * fade
        if np.abs(D).max() > 0.004:
            out[mm.name] = D
    if extra:
        for k, D in extra.items():
            if np.abs(D).max() > 0.004:
                out[k] = D
    return out


HEAD_GROUPS = (cm.FACE, cm.EYE, cm.BROW)


# ----------------------------------------------------------------------------- objects

ARM = None


def build_armature():
    arm_data = bpy.data.armatures.new("SK_LyrisBase")
    ob = bpy.data.objects.new("Armature", arm_data)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.view_layer.objects:
        o.select_set(o == ob)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = {}
    for name in PARENTS:  # parents always come before children in build order
        b = arm_data.edit_bones.new(name)
        b.head = Vector(J[name] / 100.0)
        tail = TAILS[name]
        if np.linalg.norm(tail - J[name]) < 0.5:
            tail = J[name] + np.array([0, 0, 3.0])
        b.tail = Vector(tail / 100.0)
        b.roll = 0.0
        b.use_deform = name in DEFORM
        if PARENTS[name]:
            b.parent = eb[PARENTS[name]]
            b.use_connect = False
        eb[name] = b
    bpy.ops.object.mode_set(mode="OBJECT")
    return ob


def image(name, arr):
    path = os.path.join(TEX, f"{name}.png")
    cp.save(arr, path)
    img = bpy.data.images.load(path, check_existing=True)
    img.name = name
    return img


def material(name, base_img=None, colour=None, rough=0.8, alpha=False, tint=None, spec=0.25):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Specular IOR Level"].default_value = spec
    if base_img is not None:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = base_img
        if tint is not None:
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.inputs["Factor"].default_value = 1.0
            mix.inputs[7].default_value = (*tint, 1.0)
            mix.name = "Tint"
            nt.links.new(tex.outputs["Color"], mix.inputs[6])
            nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
        else:
            nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        if alpha:
            nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
            try:
                mat.surface_render_method = "BLENDED"
            except AttributeError:
                mat.blend_method = "BLEND"
    elif colour is not None:
        bsdf.inputs["Base Color"].default_value = (*colour, 1.0)
    return mat


def srgb_to_lin(c):
    c = np.asarray(c, dtype=float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def make_object(name, V, tris, uv, normals, weights, morphs, mats, mat_idx=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata((V / 100.0).tolist(), [], tris.tolist())
    me.update()
    uvl = me.uv_layers.new(name="UVMap")
    # loops follow polygon order for from_pydata triangles
    uvl.data.foreach_set("uv", uv.reshape(-1).astype(np.float32))
    for m in mats:
        me.materials.append(m)
    if mat_idx is not None:
        me.polygons.foreach_set("material_index", np.asarray(mat_idx, dtype=np.int32))
    me.polygons.foreach_set("use_smooth", np.ones(len(tris), dtype=bool))
    if normals is not None:
        me.normals_split_custom_set_from_vertices([tuple(n) for n in normals])
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = ARM
    mod = ob.modifiers.new("Armature", "ARMATURE")
    mod.object = ARM
    groups = {}
    for i, ws in enumerate(weights):
        for b, w in ws:
            g = groups.get(b) or ob.vertex_groups.new(name=b)
            groups[b] = g
            g.add([i], w, "REPLACE")
    if morphs:
        ob.shape_key_add(name="Basis", from_mix=False)
        for mname, D in morphs.items():
            sk = ob.shape_key_add(name=mname, from_mix=False)
            sk.data.foreach_set("co", ((V + D) / 100.0).reshape(-1).astype(np.float32))
            sk.slider_min, sk.slider_max = 0.0, 1.0
    return ob


def corner_paintmap(V, tris, uv, N, size):
    pos = V[tris].reshape(-1, 3)
    nrm = N[tris].reshape(-1, 3)
    cuv = uv.reshape(-1, 2)
    ct = np.arange(len(pos)).reshape(-1, 3)
    return cp.PosMap(cuv, ct, pos, nrm, size)


# ----------------------------------------------------------------------------- parts

def build_head():
    fa = lambda P: cs.frame_sdf(P, "FrameA")
    V, Fc = sdf.march(fa, (-10.5, -13, 140.5), (10.5, 12.5, 174.5), STEP["head"])
    V, tris = clean_cut_decimate(V, Fc, BUDGET["head"], cut=("above", cs.NECK_CUT_Z))
    V = project_keep_seam(fa, V, tris)
    seam_loop = boundary_polyline(V, tris)
    N = sdf.gradient(fa, V).astype(np.float64)
    uv = smart_uv(V, tris)
    log(f"head: {len(tris)} tris")
    return V, tris, uv, N, seam_loop


def build_ears():
    faces, nv = cs.ear_topology()
    tris = []
    for f in faces:
        if len(f) == 3:
            tris.append(f)
        else:
            tris.append((f[0], f[1], f[2]))
            tris.append((f[0], f[2], f[3]))
    tris = np.array(tris, dtype=np.int64)
    parts = []
    for k, side in enumerate(("l", "r")):
        P = cs.ear_points(side, {})
        t = tris.copy()
        if side == "r":
            t = t[:, [0, 2, 1]]    # mirrored winding
        parts.append((P, t + k * nv))
    V = np.concatenate([p[0] for p in parts])
    T = np.concatenate([p[1] for p in parts])
    uv1 = cs.ears_uv()
    uvv = np.concatenate([uv1 * [0.5, 1] + [0.0, 0], uv1 * [0.5, 1] + [0.5, 0]])
    uv = uvv[T]
    # ear morphs: same topology evaluated with other parameters
    base = {"l": cs.ear_points("l", {}), "r": cs.ear_points("r", {})}

    def delta(side_params):
        out = []
        for side in ("l", "r"):
            kw, shape = side_params.get(side, ({}, {}))
            if not kw and not shape:
                out.append(np.zeros_like(base[side]))
            else:
                out.append(cs.ear_points(side, shape, **kw) - base[side])
        return np.concatenate(out)

    ear_m = {}
    for side in ("l", "r"):
        S = side.upper()
        ear_m[f"Ear_Size_{S}_Pos"] = delta({side: ({"size": 1.15}, {})})
        ear_m[f"Ear_Size_{S}_Neg"] = delta({side: ({"size": 0.85}, {})})
        ear_m[f"Ear_Angle_{S}_Pos"] = delta({side: ({"angle": 22.0}, {})})
        ear_m[f"Ear_Angle_{S}_Neg"] = delta({side: ({"angle": -7.0}, {})})
        ear_m[f"Ear_Tip_{S}"] = delta({side: ({}, {"tip": 1.0})})
        ear_m[f"Ear_Point_{S}"] = delta({side: ({}, {"point": 1.0})})
        pt = cs.ear_points(side, {"point": 1.0})
        for nm, up in (("Pos", math.radians(25)), ("Neg", -math.radians(25))):
            d = cs.ear_points(side, {"point": 1.0}, point_up=up) - pt
            z = np.zeros_like(base[side])
            ear_m[f"Ear_PointAngle_{S}_{nm}"] = np.concatenate([d, z] if side == "l" else [z, d])
        d = cs.ear_points(side, {"point": 1.0}, droop=1.0) - pt
        z = np.zeros_like(base[side])
        ear_m[f"Ear_Droop_{S}"] = np.concatenate([d, z] if side == "l" else [z, d])
        ear_m[f"Ear_Fin_{S}"] = delta({side: ({}, {"fin": 1.0})})
    ear_m["Ear_Height_Pos"] = delta({"l": ({"height": 0.6}, {}), "r": ({"height": 0.6}, {})})
    ear_m["Ear_Height_Neg"] = delta({"l": ({"height": -0.6}, {}), "r": ({"height": -0.6}, {})})
    ear_m["Ear_Lobe_Pos"] = delta({"l": ({}, {"lobe": 1.0}), "r": ({}, {"lobe": 1.0})})
    ear_m["Ear_Lobe_Neg"] = delta({"l": ({}, {"lobe": -1.0}), "r": ({}, {"lobe": -1.0})})
    # normals from the triangles (the ear is a thin shell)
    N = vertex_normals(V, T)
    return V, T, uv, N, ear_m


def vertex_normals(V, T):
    fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    N = np.zeros_like(V)
    for k in range(3):
        np.add.at(N, T[:, k], fn)
    return N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)


def build_body(frame_id, seam_loop):
    f = lambda P: cs.frame_sdf(P, frame_id)
    V, Fc = sdf.march(f, (-62, -26, -0.6), (62, 17, 144.0), STEP["body"])
    V, tris = clean_cut_decimate(V, Fc, BUDGET["body"], cut=("below", cs.NECK_CUT_Z))
    V = project_keep_seam(f, V, tris)
    V, _ = snap_boundary(V, tris, seam_loop)
    N = sdf.gradient(f, V).astype(np.float64)
    uv = smart_uv(V, tris)
    log(f"body {frame_id}: {len(tris)} tris")
    return V, tris, uv, N


def build_eyes():
    """Two eyeballs (lat-long ellipsoids) with a front-projected UV."""
    nu, nv = 28, 18
    Vs, Ts, UVs = [], [], []
    off = 0
    for side in ("l", "r"):
        R = cs.eye_rot(side).astype(np.float64)
        c = cs.EYE[side].astype(np.float64)
        r = cs.EYE_R.astype(np.float64) - 0.02
        pts, uvs = [], []
        for i in range(nv + 1):
            th = math.pi * i / nv
            for j in range(nu):
                ph = 2 * math.pi * j / nu
                q = np.array([math.sin(th) * math.cos(ph), -math.cos(th), math.sin(th) * math.sin(ph)])
                # q[1] = -1 at i=0: the front pole (towards -depth)
                local = q * r
                pts.append(c + R @ local)
                uvs.append((0.5 + 0.5 * q[0], 0.5 + 0.5 * q[2]))
        pts, uvs = np.array(pts), np.array(uvs)
        if side == "r":
            uvs[:, 0] = 1 - uvs[:, 0]   # the same texture reads the same on both eyes (nose side inward)
        tris = []
        for i in range(nv):
            for j in range(nu):
                a = i * nu + j
                b = i * nu + (j + 1) % nu
                c2 = (i + 1) * nu + j
                d = (i + 1) * nu + (j + 1) % nu
                tris += [(a, c2, d), (a, d, b)]
        tris = np.array(tris)
        Vs.append(pts)
        Ts.append(tris + off)
        UVs.append(uvs)
        off += len(pts)
    V = np.concatenate(Vs)
    T = np.concatenate(Ts)
    UV = np.concatenate(UVs)
    N = vertex_normals(V, T)
    if (N * (V - np.concatenate([np.repeat(cs.EYE[s][None].astype(float), len(Vs[0]), 0) for s in "lr"]))).sum() < 0:
        T = T[:, [0, 2, 1]]
        N = -N
    return V, T, UV[T], N


def head_surface(P, iters=5):
    return sdf.project(lambda X: cs.frame_sdf(X, "FrameA"), P, iters=iters)


def build_brows():
    nu, nv = 22, 4
    Vs, UVs, Ts = [], [], []
    off = 0
    for side, s in (("l", 1.0), ("r", -1.0)):
        grid = []
        for j in range(nv + 1):
            for i in range(nu + 1):
                u = i / nu
                v = j / nv
                x = 1.05 + 5.0 * u
                z = 160.95 + 0.85 * math.sin(min(u * 1.25, 1.0) * math.pi * 0.62) - 0.25 * u + (v - 0.5) * 1.15
                grid.append((x * s, -9.5, z))
        grid = np.array(grid)
        # project onto the head from the front, then lift a little off the skin
        P = head_surface(grid)
        Nn = sdf.gradient(lambda X: cs.frame_sdf(X, "FrameA"), P).astype(float)
        P = P + Nn * 0.035
        uv = np.array([(i / nu, j / nv) for j in range(nv + 1) for i in range(nu + 1)])
        tris = []
        for j in range(nv):
            for i in range(nu):
                a = j * (nu + 1) + i
                b, c, d = a + 1, a + nu + 1, a + nu + 2
                tris += [(a, b, d), (a, d, c)] if s > 0 else [(a, d, b), (a, c, d)]
        Vs.append(P)
        UVs.append(uv)
        Ts.append(np.array(tris) + off)
        off += len(P)
    V, UV, T = np.concatenate(Vs), np.concatenate(UVs), np.concatenate(Ts)
    N = vertex_normals(V, T)
    return V, T, UV[T], N


def lash_points(curl=0.0, length=1.0):
    nu = 24
    Vs, UVs, Ts = [], [], []
    off = 0
    for side, s in (("l", 1.0), ("r", -1.0)):
        R = cs.eye_rot(side).astype(float)
        c = cs.EYE[side].astype(float)
        us = np.linspace(-cm.EYE_W * 0.97, cm.EYE_W * 1.02, nu + 1)
        roots = []
        for u in us:
            v = cm.upper_curve(np.array([u]))[0] + 0.03
            roots.append(c + R @ np.array([u, -1.6, v]))
        roots = np.array(roots)
        roots = head_surface(roots) + np.array([0, -0.02, 0])
        # step back onto the lid edge: move each root down onto the opening along the lid
        rows = []
        for k, u in enumerate(us):
            t = (u / cm.EYE_W + 1) / 2                       # 0 inner .. 1 outer
            L = (0.42 + 0.55 * t ** 1.3) * length
            out = R[:, 0] * (0.25 + 0.6 * t) + np.array([0, -1.0, 0]) * 0.9 + np.array([0, 0, 1.0]) * 0.55
            out /= np.linalg.norm(out)
            up = np.array([0, 0.3, 1.0])
            up /= np.linalg.norm(up)
            d = out * (1 - curl * 0.3) + up * (0.35 + curl * 0.6)
            d /= np.linalg.norm(d)
            mid = roots[k] + out * L * 0.5
            tip = mid + d * L * 0.5
            rows.append((roots[k], mid, tip))
        P = np.array([r[j] for j in range(3) for r in rows])
        uv = np.array([(i / nu, j / 2) for j in range(3) for i in range(nu + 1)])
        if s < 0:
            uv[:, 0] = uv[:, 0]
        tris = []
        for j in range(2):
            for i in range(nu):
                a = j * (nu + 1) + i
                b, cc, d = a + 1, a + nu + 1, a + nu + 2
                tris += [(a, b, d), (a, d, cc)] if s > 0 else [(a, d, b), (a, cc, d)]
        Vs.append(P)
        UVs.append(uv)
        Ts.append(np.array(tris) + off)
        off += len(P)
    return np.concatenate(Vs), np.concatenate(Ts), np.concatenate(UVs)


def build_lashes():
    V, T, UV = lash_points()
    extra = {"Lash_Length_Pos": lash_points(length=1.4)[0] - V,
             "Lash_Length_Neg": lash_points(length=0.7)[0] - V,
             "Lash_Curl_Pos": lash_points(curl=1.0)[0] - V,
             "Lash_Curl_Neg": lash_points(curl=-0.8)[0] - V}
    N = vertex_normals(V, T)
    return V, T, UV[T], N, extra


HAIRS = {
    "LamplighterBob": dict(fn="bob", top=171.5, bottom=147.0, flow="vertical", root="6F4128", tip="8E3B26"),
    "FallingWater": dict(fn="long", top=171.5, bottom=113.0, flow="vertical", root="3B2419", tip="553322"),
    "RopeBraid": dict(fn="braid", top=171.5, bottom=108.0, flow="braid", root="D4A55A", tip="E3C27E"),
}


def build_hair(style, long_ears):
    spec = HAIRS[style]
    body = lambda P: cs.frame_sdf(P, "FrameB")   # the broader frame, so hair clears both
    if spec["fn"] == "bob":
        f = lambda P: cs.hair_bob(P, body(P), long_ears)
        lo, hi = (-13, -12.5, 143), (13, 14, 175)
    elif spec["fn"] == "long":
        f = lambda P: cs.hair_long(P, body(P), long_ears)
        lo, hi = (-15, -12, 109), (15, 16, 175)
    else:
        path = cs.braid_path(body)

        def f(P):
            h, _ = cs.hair_braid(P, body(P), path, long_ears)
            return h
        lo, hi = (-13, -15, 104), (16, 14, 175)
        tie_fn = lambda P: cs.hair_braid(P, np.full(len(P), 10.0, np.float32), path)[1]
    V, Fc = sdf.march(f, lo, hi, STEP["hair"])
    V, tris = clean_cut_decimate(V, Fc, BUDGET["hair"], keep_largest=True)
    V = sdf.project(f, V, iters=2)
    N = sdf.gradient(f, V).astype(float)
    mat_idx = np.zeros(len(tris), dtype=int)
    if spec["fn"] == "braid":
        Vt, Ft = sdf.march(tie_fn, (5, -15, 104), (14, -6, 120), 0.12)
        Vt, Tt = clean_cut_decimate(Vt, Ft, 400)
        Nt = sdf.gradient(tie_fn, Vt).astype(float)
        tris = np.concatenate([tris, Tt + len(V)])
        mat_idx = np.concatenate([mat_idx, np.ones(len(Tt), dtype=int)])
        V = np.concatenate([V, Vt])
        N = np.concatenate([N, Nt])
    uv = smart_uv(V, tris, angle=70)
    log(f"hair {style}{' long-ear' if long_ears else ''}: {len(tris)} tris")
    return V, tris, uv, N, mat_idx


def hair_extra_morphs(V, N, bottom):
    span = max(153.0 - bottom, 4.0)
    below = np.clip(153.0 - V[:, 2], 0, None)
    lenD = np.zeros_like(V)
    lenD[:, 2] = -below * (0.25 if span > 12 else 0.18)
    vol = cp.smoothstep(145.0, 158.0, V[:, 2]) * 0.6 + 0.4
    return {"Hair_Length_Pos": lenD, "Hair_Length_Neg": -lenD * 0.8,
            "Hair_Volume_Pos": N * (0.5 * vol)[:, None], "Hair_Volume_Neg": N * (-0.3 * vol)[:, None]}


def build_outfit(frame_id):
    def piece(name):
        def f(P):
            return cs.outfit_sdfs(P, frame_id)[name]
        return f

    Vs, Ts, Ns, ids = [], [], [], []
    off = 0
    boxes = {"shirt": ((-40, -22, 83), (40, 16, 145)), "trousers": ((-22, -18, 22), (22, 18, 104)),
             "belt": ((-18, -14, 96.5), (18, 14, 103)), "boots": ((-18, -24, -1.2), (18, 12, 33))}
    for k, name in enumerate(("shirt", "trousers", "belt", "boots")):
        f = piece(name)
        V, Fc = sdf.march(f, *boxes[name], STEP["outfit"] if name != "belt" else 0.3)
        V, tris = clean_cut_decimate(V, Fc, BUDGET[name], keep_largest=(name in ("shirt", "belt")))
        V = sdf.project(f, V, iters=2)
        Vs.append(V)
        Ts.append(tris + off)
        Ns.append(sdf.gradient(f, V).astype(float))
        ids.append(np.full(len(tris), k))
        off += len(V)
    V, T, N, pid = np.concatenate(Vs), np.concatenate(Ts), np.concatenate(Ns), np.concatenate(ids)
    uv = smart_uv(V, T)
    log(f"outfit {frame_id}: {len(T)} tris")
    return V, T, uv, N, pid


# ----------------------------------------------------------------------------- export

def export(name, objs):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ARM.select_set(True)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = ARM
    glb = os.path.join(HERE, f"{name}.glb")
    bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True, export_skins=True,
                              export_morph=True, export_morph_normal=False, export_animations=False,
                              export_yup=True, export_apply=False, export_def_bones=False,
                              export_image_format="NONE", export_try_sparse_sk=True)
    bpy.ops.export_scene.fbx(filepath=os.path.join(FBX, f"{name}.fbx"), use_selection=True,
                             object_types={"ARMATURE", "MESH"}, add_leaf_bones=False,
                             apply_unit_scale=True, apply_scale_options="FBX_SCALE_ALL",
                             use_armature_deform_only=False, bake_anim=False, mesh_smooth_type="FACE",
                             primary_bone_axis="Y", secondary_bone_axis="X", use_tspace=False,
                             path_mode="STRIP", embed_textures=False)


# ----------------------------------------------------------------------------- main

PEOPLE_LOOKS = {
    # preview looks: skin swatch, iris, hair, ear morphs
    "Human": dict(skin="E2B48C", iris="7A4A2A", ears={}),
    "MoonlitElf": dict(skin="D4C8E6", iris="7AC0E6", ears={"Ear_Point_L": 0.85, "Ear_Point_R": 0.85,
                                                            "Ear_PointAngle_L_Neg": 0.25, "Ear_PointAngle_R_Neg": 0.25}),
    "Deepkin": dict(skin="86B8AA", iris="7FD0D6", ears={"Ear_Point_L": 0.45, "Ear_Point_R": 0.45,
                                                         "Ear_Fin_L": 1.0, "Ear_Fin_R": 1.0}),
}


def main():
    global ARM
    os.makedirs(TEX, exist_ok=True)
    os.makedirs(FBX, exist_ok=True)
    for d in (TEX, FBX):
        for old in os.listdir(d):
            os.remove(os.path.join(d, old))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    ARM = build_armature()
    meta = {"bones": list(PARENTS), "deform_bones": DEFORM, "meshes": {}}
    objs = {}

    # ---- head + ears (one skeletal mesh, two sections)
    Vh, Th, UVh, Nh, seam_loop = build_head()
    Ve, Te, UVe, Ne, ear_m = build_ears()
    pm = corner_paintmap(Vh, Th, UVh, Nh, 1024 if not FAST else 512)
    base, prev, masks = cp.paint_skin(pm, "head")
    img_head = image("T_Head_BaseColor", base)
    image("T_Head_Preview", prev)
    image("T_Head_Masks", masks)
    pme = corner_paintmap(Ve, Te, UVe, Ne, 256)
    ebase, eprev, emasks = cp.paint_skin(pme, "ears")
    img_ears = image("T_Ears_BaseColor", ebase)
    image("T_Ears_Masks", emasks)
    m_head = material("M_Lyris_Head", img_head, rough=0.75)
    m_ears = material("M_Lyris_Ears", img_ears, rough=0.75)
    Vhe = np.concatenate([Vh, Ve])
    The = np.concatenate([Th, Te + len(Vh)])
    UVhe = np.concatenate([UVh, UVe])
    Nhe = np.concatenate([Nh, Ne])
    mi = np.concatenate([np.zeros(len(Th), int), np.ones(len(Te), int)])
    zeros_h = np.zeros_like(Vh)
    ear_full = {k: np.concatenate([zeros_h, D]) for k, D in ear_m.items()}
    morphs = eval_morphs(Vhe, Nhe, HEAD_GROUPS, ear_full)
    w_head = skin_weights(Vh)
    w = w_head + rigid_weights(len(Ve))
    objs["Head"] = make_object("SKM_Lyris_Head", Vhe, The, UVhe, Nhe, w, morphs, [m_head, m_ears], mi)
    meta["meshes"]["Head"] = {"tris": int(len(The)), "head_tris": int(len(Th)), "ear_tris": int(len(Te)),
                              "morphs": sorted(morphs)}
    log(f"head morphs {len(morphs)}")

    # ---- bodies
    body_data = {}
    for frame_id in ("FrameA", "FrameB"):
        Vb, Tb, UVb, Nb = build_body(frame_id, seam_loop)
        pmb = corner_paintmap(Vb, Tb, UVb, Nb, 1024 if not FAST else 512)
        base, prev, masks = cp.paint_skin(pmb, "body")
        img = image(f"T_Body_{frame_id}_BaseColor", base)
        image(f"T_Body_{frame_id}_Masks", masks)
        mb = material(f"M_Lyris_Body_{frame_id}", img, rough=0.75)
        wb = skin_weights(Vb)
        mor = eval_morphs(Vb, Nb, (cm.BODY,), region="body")
        objs[f"Body_{frame_id}"] = make_object(f"SKM_Lyris_Body_{frame_id}", Vb, Tb, UVb, Nb, wb, mor, [mb])
        meta["meshes"][f"Body_{frame_id}"] = {"tris": int(len(Tb)), "morphs": sorted(mor)}
        body_data[frame_id] = (Vb, wb)
        log(f"body {frame_id} morphs {len(mor)}")

    # ---- eyes, brows, lashes
    Vy, Ty, UVy, Ny = build_eyes()
    eye_col, eye_mask = cp.paint_eye_cm(512 if not FAST else 256, cs.EYE_R, "3F9A93")
    img_eye = image("T_Eyes_BaseColor", eye_col)
    image("T_Eyes_Masks", eye_mask)
    m_eye = material("M_Lyris_Eyes", img_eye, rough=0.15, spec=0.6)
    mor = eval_morphs(Vy, Ny, HEAD_GROUPS)
    objs["Eyes"] = make_object("SKM_Lyris_Eyes", Vy, Ty, UVy, Ny, rigid_weights(len(Vy)), mor, [m_eye])
    meta["meshes"]["Eyes"] = {"tris": int(len(Ty)), "morphs": sorted(mor)}

    Vbr, Tbr, UVbr, Nbr = build_brows()
    brow = cp.paint_brow(256, 64)
    img_brow = image("T_Brows_Natural", brow)
    m_brow = material("M_Lyris_Brows", img_brow, alpha=True, rough=0.9)
    mor = eval_morphs(Vbr, Nbr, HEAD_GROUPS)
    objs["Brows"] = make_object("SKM_Lyris_Brows", Vbr, Tbr, UVbr, Nbr, rigid_weights(len(Vbr)), mor, [m_brow])
    meta["meshes"]["Brows"] = {"tris": int(len(Tbr)), "morphs": sorted(mor)}

    Vl, Tl, UVl, Nl, lash_m = build_lashes()
    lash = cp.paint_lash(256, 64)
    img_lash = image("T_Lashes_Natural", lash)
    m_lash = material("M_Lyris_Lashes", img_lash, alpha=True, rough=0.9)
    mor = eval_morphs(Vl, Nl, HEAD_GROUPS, lash_m)
    objs["Lashes"] = make_object("SKM_Lyris_Lashes", Vl, Tl, UVl, Nl, rigid_weights(len(Vl)), mor, [m_lash])
    meta["meshes"]["Lashes"] = {"tris": int(len(Tl)), "morphs": sorted(mor)}
    log("eyes, brows, lashes done")

    # ---- hair
    hair_bones = ["head", "neck_02", "neck_01", "spine_05", "spine_04", "spine_03", "clavicle_l", "clavicle_r"]
    for style, spec in HAIRS.items():
        for long_ears in (False, True):
            if FAST and long_ears:
                continue
            Vr, Tr, UVr, Nr, mi = build_hair(style, long_ears)
            tag = f"Hair_{style}" + ("_LongEar" if long_ears else "")
            pmh = corner_paintmap(Vr, Tr, UVr, Nr, 512)
            mask = cp.paint_hair(pmh, spec["top"], spec["bottom"], spec["flow"])
            if not long_ears:
                image(f"T_{tag}_Masks", mask)
            prevh = cp.hair_preview(mask, cp.hexrgb(spec["root"]), cp.hexrgb(spec["tip"]))
            img = image(f"T_{tag}_BaseColor", prevh)
            mats = [material(f"M_Lyris_{tag}", img, rough=0.55, spec=0.4)]
            if spec["fn"] == "braid":
                mats.append(material(f"M_Lyris_{tag}_Tie", colour=tuple(srgb_to_lin(cp.REDBAND)), rough=0.7))
            mor = eval_morphs(Vr, Nr, HEAD_GROUPS, hair_extra_morphs(Vr, Nr, spec["bottom"]))
            wr = skin_weights(Vr, hair_bones)
            objs[tag] = make_object(f"SKM_Lyris_{tag}", Vr, Tr, UVr, Nr, wr, mor, mats, mi)
            meta["meshes"][tag] = {"tris": int(len(Tr)), "morphs": sorted(mor)}

    # ---- outfit
    for frame_id in ("FrameA", "FrameB"):
        Vo, To, UVo, No, pid = build_outfit(frame_id)
        pmo = corner_paintmap(Vo, To, UVo, No, 1024 if not FAST else 512)
        col, det, masks = cp.paint_outfit(pmo, paint_piece_ids(pmo, To, pid, UVo))
        img = image(f"T_Outfit_PlainTraveller_{frame_id}_BaseColor", col)
        image(f"T_Outfit_PlainTraveller_{frame_id}_Masks", masks)
        mo = material(f"M_Lyris_Outfit_PlainTraveller_{frame_id}", img, rough=0.85)
        Vb, wb = body_data[frame_id]
        wo = transfer_weights(Vo, Vb, wb)
        mor = eval_morphs(Vo, No, (cm.BODY,), region="body")
        tag = f"Outfit_PlainTraveller_{frame_id}"
        objs[tag] = make_object(f"SKM_Lyris_{tag}", Vo, To, UVo, No, wo, mor, [mo])
        meta["meshes"][tag] = {"tris": int(len(To)), "morphs": sorted(mor)}

    # ---- export
    for key, ob in objs.items():
        export(f"SKM_Lyris_{key}", [ob])
    log("exported")
    with open(os.path.join(HERE, "character_meta.json"), "w") as f:
        json.dump(meta, f, indent=1)
    write_morph_table(meta)

    import char_preview
    char_preview.render_all(objs, ARM, PEOPLE_LOOKS, HERE, TEX, fast=FAST)
    log("previews done")
    for k, v in meta["meshes"].items():
        print(f"  {k:40s} {v['tris']:6d} tris  {len(v['morphs']):3d} morphs")


def paint_piece_ids(pm, T, pid, uv):
    """Per-texel piece id for the outfit (rasterised alongside the position map)."""
    cuv = uv.reshape(-1, 2)
    ct = np.arange(len(cuv)).reshape(-1, 3)
    attr = np.repeat(pid.astype(float), 3)[:, None]
    img, cov = cp.rasterise(cuv, ct, attr, pm.size)
    return np.rint(img[pm.cov][:, 0]).astype(int)


# ----------------------------------------------------------------------------- morph table

def write_morph_table(meta):
    present = {}
    for mesh, info in meta["meshes"].items():
        for mname in info["morphs"]:
            present.setdefault(mname, []).append(mesh)

    def where(names):
        meshes = set()
        for n in names:
            meshes.update(present.get(n, []))
        order = ["Head", "Eyes", "Brows", "Lashes", "Body_FrameA", "Body_FrameB"]
        short = [m for m in order if m in meshes]
        if any(m.startswith("Hair_") for m in meshes):
            short.append("Hair_*")
        if any(m.startswith("Outfit_") for m in meshes):
            short.append("Outfit_*")
        return ", ".join(short) or "-"

    rows = []
    seen = set()
    for mm in cm.REG:
        if mm.slider in seen:
            continue
        seen.add(mm.slider)
        names = [x.name for x in cm.REG if x.slider == mm.slider]
        hi = [x.name for x in cm.REG if x.slider == mm.slider and x.end in ("high", "0..1")]
        lo = [x.name for x in cm.REG if x.slider == mm.slider and x.end == "low"]
        note = next((x.note for x in cm.REG if x.slider == mm.slider and x.note), "")
        rows.append((mm.slider, ", ".join(f"`{n}`" for n in hi), ", ".join(f"`{n}`" for n in lo) or "-",
                     where(names), note))
    ear_rows = []
    for slider, base, is_sided, two in cm.EAR_SLIDERS:
        for side in (("L", "R") if is_sided else ("",)):
            sid = slider + side
            nm = base + (f"_{side}" if side else "")
            if two:
                ear_rows.append((sid, f"`{nm}_Pos`", f"`{nm}_Neg`", "Head (ear section)", ""))
            else:
                ear_rows.append((sid, f"`{nm}`", "-", "Head (ear section)", ""))
    for i, r in enumerate(ear_rows):
        if r[0].startswith(("Ears.PointAngle", "Ears.Droop")):
            ear_rows[i] = r[:4] + ("authored on a full point: weight = this slider x `Ears.Point` value",)
    lash_rows = [("Lashes.Length", "`Lash_Length_Pos`", "`Lash_Length_Neg`", "Lashes", ""),
                 ("Lashes.Curl", "`Lash_Curl_Pos`", "`Lash_Curl_Neg`", "Lashes", ""),
                 ("Hair.Length (part scalar)", "`Hair_Length_Pos`", "`Hair_Length_Neg`", "Hair_*", ""),
                 ("Hair.Volume (part scalar)", "`Hair_Volume_Pos`", "`Hair_Volume_Neg`", "Hair_*", "")]
    lines = [
        "# Morph targets (T25)",
        "",
        "Generated by `make_character.py` (do not edit by hand). Names follow the **Morph** column of",
        "`design/character_creator.md` section 3: `Area_Name`, `_L` / `_R` for sides, and for two-way",
        "(-1..1) sliders a `_Pos` morph for the slider's high end and a `_Neg` morph for its low end.",
        "One-sided (0..1) sliders have a single morph.",
        "",
        "## How to drive them",
        "",
        "- Slider value `v` in -1..1: set `<Name>_Pos` = max(v, 0) x Weight and `<Name>_Neg` = max(-v, 0) x Weight,",
        "  where Weight is the spec's Limit column (\"morph 0.8\" -> 0.8). Weight 1.0 of every morph already *is* the",
        "  spec's guardrail end (e.g. `Eye_Size_L_Pos` = +15%, `Eye_Size_L_Neg` = -10%, `Ear_Point_L` = +6 cm).",
        "- Mirrored space is built in: the same value on `_L` and `_R` gives a symmetric face (no axis flips needed).",
        "- A morph lives on every mesh it moves, under the same name, so the head, eyes, brows, lashes and hair move",
        "  together. Set it by name on **each** skeletal mesh component listed in the Meshes column",
        "  (`SetMorphTarget` on each; Leader Pose does not forward morph weights to followers).",
        "  `character_meta.json` lists the exact morphs on every mesh.",
        "- Ears are one section of the Head mesh (not separate parts). Humans use no ear morph (or `Ear_Tip`),",
        "  Moonlit elves `Ear_Point` (+ angle/droop), Deepkin `Ear_Point` + `Ear_Fin`. Long-ear Peoples should",
        "  wear the `_LongEar` hair variants, which leave a slot for the point.",
        "- Body sliders that are bone scales or rotations in the spec stay bones; only the morph rows below are morphs.",
        "",
        "## Face, eyes, brows, nose, mouth",
        "",
        "| Slider | Morph at high end | Morph at low end | Meshes | Note |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        if r[0].startswith("Body."):
            continue
        lines.append("| `%s` | %s | %s | %s | %s |" % r)
    lines += ["", "## Ears", "", "| Slider | Morph at high end | Morph at low end | Meshes | Note |", "|---|---|---|---|---|"]
    for r in ear_rows:
        lines.append("| `%s` | %s | %s | %s | %s |" % r)
    lines += ["", "## Body", "", "| Slider | Morph at high end | Morph at low end | Meshes | Note |", "|---|---|---|---|---|"]
    for r in rows:
        if r[0].startswith("Body."):
            lines.append("| `%s` | %s | %s | %s | %s |" % r)
    lines += ["", "## Lashes and hair", "", "| Slider / scalar | Morph at high end | Morph at low end | Meshes | Note |",
              "|---|---|---|---|---|"]
    for r in lash_rows:
        lines.append("| `%s` | %s | %s | %s | %s |" % r)
    lines += ["", "## Not morphs", "", "| Slider | Why |", "|---|---|"]
    for k, v in cm.MATERIAL_SLIDERS.items():
        lines.append(f"| `{k}` | {v} (spec) |")
    for k, v in cm.NOT_DONE.items():
        lines.append(f"| `{k}` | not done: {v} |")
    lines += ["| `Body.*` bone sliders | bone scale / offset / rotation, as in the spec's Targets column |", ""]
    total = len(present)
    lines.insert(2, f"{total} morph targets in all.\n")
    with open(os.path.join(HERE, "morph_targets.md"), "w") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
