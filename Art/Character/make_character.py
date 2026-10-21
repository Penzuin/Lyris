"""Generates the Lyris base character for the character creator (tasks T25, T46).

Look: storybook painterly, Genshin-like warmth with Lyris's own identity. An adult about 6.4
heads tall (176 cm, head 27.5 cm), soft round cheeks and jaw, a small button nose and mouth,
large eyes with big painted irises under a bold upper lash line, chunky readable hair locks,
and painted toon-style textures (warm lights, cool lavender shadows, soft rosiness).
Two body frames from design/character_creator.md, FrameA "Willow" (narrower, lighter) and
FrameB "Oak" (broader, sturdier). They are cosmetic only and share ONE skeleton and ONE head.

How it is made: every part is a signed distance field (char_shapes.py, char_hair.py). The head
and body are quad-remeshed (voxel remesh + QuadriFlow in Blender, char_mesh.py) for even
edge flow round the shoulders, elbows, knees and face, with real eye openings and a parted
mouth on clean loops, a mouth interior, and hands spliced in at the wrists. Hair is built from
swept, tapered locks. Textures are painted from 3D position (char_paint.py). Skin weights are
distance-based, then smoothed over the mesh at the shoulders and hips. Morph targets are
analytic warps of space (char_morphs.py for the creator sliders, char_face.py for blinks and
expressions), so one morph moves the head, eyes, brows, lashes, ears and hair together.
Blender then writes glTF 2.0 (.glb) and FBX.

The head is designed at 6.9 heads tall and grown about the neck seam by
char_shapes.HEAD_SCALE when exported (head_xform); the seam itself never moves, so head and
body always meet.

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
  SKM_Lyris_Head.glb                        shared head: sections face, ears, mouth interior
  SKM_Lyris_Eyes.glb, _Brows.glb, _Lashes.glb
  SKM_Lyris_Hair_<Style>.glb (+ _LongEar)   LamplighterBob, FallingWater, RopeBraid; the
                                            _LongEar variants leave room for elf and Deepkin ears
  SKM_Lyris_Outfit_PlainTraveller_FrameA.glb / _FrameB.glb
  fbx/*.fbx                                 the same parts as FBX
  textures/*.png                            painted base colours and masks (see README.md)
  morph_targets.md                          slider -> morph mapping for the Player lane
  character_meta.json                       triangle counts, morphs per mesh, bone list
  preview*.png                              toon-shaded EEVEE renders for review
  preview_compare_*.png                     before (T25, from before_T25/) and after, same camera

Run:  python3 make_character.py      (needs `pip install bpy` for Python 3.13: Blender 5.2)
      python3 make_character.py --fast   coarse quick look
Takes about 40 minutes on 2 cores (most of it the previews).
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

import char_face as cf  # noqa: E402
import char_hair as ch  # noqa: E402
import char_mesh as cmesh  # noqa: E402
import char_morphs as cm  # noqa: E402
import char_paint as cp  # noqa: E402
import char_rig as rig  # noqa: E402
import char_sdf as sdf  # noqa: E402
import char_shapes as cs  # noqa: E402

TEX = os.path.join(HERE, "textures")
FBX = os.path.join(HERE, "fbx")
FAST = "--fast" in sys.argv          # quick look: coarser grids, fewer renders
T0 = time.time()

# Mesh budgets. Head and body are quad-remeshed (QuadriFlow) to about QUAD faces each; the
# hands are spliced in as triangles. Body + head stays under 30k triangles.
QUAD = {"head": 5600, "body": 6600}
VOXEL = {"head": 0.10, "body": 0.20}
HAND_TRIS = 1700
BUDGET = {"hair": 9000, "shirt": 5200, "trousers": 3600, "belt": 500, "boots": 1800}
STEP = {"head": 0.14, "body": 0.4, "hair": 0.2, "outfit": 0.35}
if FAST:
    QUAD = {"head": 3000, "body": 4000}
    VOXEL = {"head": 0.15, "body": 0.3}
    HAND_TRIS = 900
    STEP = {"head": 0.25, "body": 0.7, "hair": 0.35, "outfit": 0.8}

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


def smooth_weights(V, T, weights, regions, iters=8, amount=0.5):
    """Laplacian smoothing of skin weights over the mesh, only inside `regions`
    (list of (centre, radius) in cm): soft shoulders and hips without a blur everywhere."""
    bones = sorted({b for ws in weights for b, _ in ws})
    idx = {b: i for i, b in enumerate(bones)}
    W = np.zeros((len(V), len(bones)))
    for i, ws in enumerate(weights):
        for b, w in ws:
            W[i, idx[b]] = w
    mask = np.zeros(len(V))
    for c, r in regions:
        d = np.linalg.norm(V - np.asarray(c, float), axis=1)
        mask = np.maximum(mask, 1 - cp.smoothstep(r * 0.6, r, d))
    nb = cmesh.adjacency(len(V), T.tolist())
    for _ in range(iters):
        avg = np.array([W[n].mean(0) if len(n) else W[i] for i, n in enumerate(nb)])
        W = W + (avg - W) * (amount * mask)[:, None]
    W /= np.maximum(W.sum(1, keepdims=True), 1e-9)
    out = []
    for i in range(len(V)):
        order = np.argsort(-W[i])[:4]
        top = W[i, order]
        top[top < 0.02] = 0
        top /= max(top.sum(), 1e-9)
        out.append([(bones[order[j]], float(top[j])) for j in range(4) if top[j] > 0])
    return out


SMOOTH_REGIONS = [((x * s, 0.5, 136.0), 9.0) for s in (1, -1) for x in (13.5,)] + \
    [((9.0 * s, 0.5, 92.0), 10.0) for s in (1, -1)] + [((0, 0.5, 92.0), 8.0)]


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


def head_morphs(V, N, extra=None, face_rig=True, brows=False):
    """Creator morphs + face rig morphs for a mesh on the head, in design space."""
    out = eval_morphs(V, N, HEAD_GROUPS, extra)
    if face_rig:
        fade = cm.seam(V)[:, None]
        for k, D in cf.expression_morphs(V, N).items():
            D = D * fade
            if np.abs(D).max() > 0.004:
                out[k] = D
    return out


def to_export(V, morphs):
    """Design space -> exported space (the larger storybook head) for a head-attached mesh."""
    return cs.head_xform(V), {k: cs.head_xform(V + D) - cs.head_xform(V) for k, D in morphs.items()}


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


# The morph names each mesh shipped with in T25 (the Player lane's catalog drives them by name).
STABLE_PATH = os.path.join(HERE, "morph_names_T25.json")
STABLE = {}
if os.path.exists(STABLE_PATH):
    with open(STABLE_PATH) as _f:
        STABLE = {k: set(v) for k, v in json.load(_f).items()}


def keep_stable(key, morphs, V):
    """Every morph name a mesh had in an earlier release stays on it (as a zero morph if the new
    shape no longer moves that mesh), so the Player lane's catalog never loses a target."""
    for k in STABLE.get(key, ()):
        if k not in morphs:
            morphs[k] = np.zeros_like(V)
    return morphs


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
    morphs = keep_stable(name.replace("SKM_Lyris_", ""), dict(morphs), V)
    if morphs:
        ob.shape_key_add(name="Basis", from_mix=False)
        for mname, D in sorted(morphs.items()):
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

def head_closed(P):
    """The head and neck alone (no shoulders), capped below the seam: one closed surface that
    sits inside the remesh box. Above the seam it is identical to the full frame field."""
    h = cs.head_sdf(P, closed=True)
    f = cs.frame_sdf(P, "FrameA", closed=True)
    # identical to the frame above 147 cm; near the seam take the frame's neck (so the body,
    # built from the frame, meets it), and below it the bare neck, capped
    t = cp.smoothstep(146.5, 141.0, P[:, 2])
    r = np.sqrt(P[:, 0] ** 2 + (P[:, 1] - 1.2) ** 2)
    t = t * (1 - cp.smoothstep(6.5, 8.0, r))
    d = h * (1 - t) + f * t
    return cs.smax(d.astype(np.float32), 136.5 - P[:, 2], 0.5)


def head_open(P):
    return cs.frame_sdf(P, "FrameA", closed=False)


def build_head():
    """Quad-remeshed head in design space, eye openings and the parted mouth on clean loops."""
    V, F = cmesh.quad_remesh(head_closed, (-11.03, -13, 135), (11, 13, 174.5), STEP["head"],
                             VOXEL["head"], QUAD["head"])
    V, F = cmesh.bisect(V, F, cs.NECK_CUT_Z, keep="above")
    eyes = [(cs.EYE[s_].astype(float) + np.array([0, -1.2, 0.2]), 3.4) for s_ in ("l", "r")]
    mouth = [(cs.MOUTH.astype(float), 2.4)]
    V, F = cmesh.subdivide_region(V, F, eyes + mouth, 1, head_closed)
    V, F = cmesh.subdivide_region(V, F, [(cs.MOUTH.astype(float), 1.9)], 1, head_closed)
    V, F = cmesh.cut_eye_holes(V, F, head_open)
    V, F = cmesh.cut_mouth(V, F, head_open)
    nquad = sum(1 for f in F if len(f) == 4)
    V, tris = cmesh.triangulate(V, F)
    b = boundary_ids(tris)
    seam = b[np.abs(V[b, 2] - cs.NECK_CUT_Z) < 0.4]
    V[seam, 2] = cs.NECK_CUT_Z
    seam_loop = seam_polyline(V, tris, seam)
    N = vertex_normals(V, tris)
    uv = smart_uv(V, tris)
    log(f"head: {len(tris)} tris ({nquad} of {len(F)} faces quads before triangulating)")
    return V, tris, uv, N, seam_loop


def seam_polyline(V, tris, ids):
    ids = set(int(i) for i in ids)
    edges = np.sort(np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]]), axis=1)
    uniq, cnt = np.unique(edges, axis=0, return_counts=True)
    b = [e for e in uniq[cnt == 1] if e[0] in ids and e[1] in ids]
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


def build_mouth_interior():
    V, T, pid = cmesh.mouth_interior()
    uv = np.zeros((len(T), 3, 2))
    uv[:, :, 0] = (0.15 + 0.35 * pid)[:, None]
    uv[:, :, 1] = 0.5
    N = vertex_normals(V, T)
    return V, T, uv, N, pid


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
    """Quad-remeshed body (neck down) with full-detail hands spliced in at the wrists."""
    f = lambda P: cs.frame_sdf(P, frame_id)
    cap = lambda P: cs.smax(f(P), P[:, 2] - (cs.NECK_CUT_Z + 3.0), 0.6)
    V, F = cmesh.quad_remesh(cap, (-62.03, -26, -0.6), (62, 17, cs.NECK_CUT_Z + 4), STEP["body"],
                             VOXEL["body"], QUAD["body"])
    V, F = cmesh.bisect(V, F, cs.NECK_CUT_Z, keep="below")
    nquad = sum(1 for fc in F if len(fc) == 4)
    for side in ("l", "r"):
        wrist, d, n, w = cs.HAND[side]
        co = wrist - d * 1.2
        V, F = cmesh.cut_local(V, F, co, d, 7.0)
        parts = lambda P, side=side: cs._limb_parts(P, cs.FRAMES[frame_id], ("arm", "hand"))
        hf = lambda P, side=side: cs.smin(parts(P)[f"lowerarm_{side}"], parts(P)[f"hand_{side}"], 1.2)
        Vh, Fh = sdf.march(hf, wrist - 14, wrist + 14, 0.13 if not FAST else 0.2)
        Vh, Fh = cmesh.cut_local(Vh, Fh, co, -d, 30.0)
        Vh, Fh = cmesh.decimate(Vh, Fh, HAND_TRIS)
        Vh = sdf.project(hf, Vh, iters=2)
        V, F = cmesh.loft(V, F, Vh, Fh, co, d)
    V, tris = cmesh.triangulate(V, F)
    b = boundary_ids(tris)
    seam = b[np.abs(V[b, 2] - cs.NECK_CUT_Z) < 0.4]
    V[seam, 2] = cs.NECK_CUT_Z
    V, _ = snap_boundary(V, tris, seam_loop)
    N = vertex_normals(V, tris)
    uv = smart_uv(V, tris)
    log(f"body {frame_id}: {len(tris)} tris ({nquad} quads in the remeshed body before triangulating)")
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
    return sdf.project(head_open, P, iters=iters)


def build_brows():
    """Brow cards: thick at the inner end, tapering to the tail, laid on the skin above the eye."""
    nu, nv = 22, 4
    Vs, UVs, Ts = [], [], []
    off = 0
    for side, s in (("l", 1.0), ("r", -1.0)):
        grid = []
        for j in range(nv + 1):
            for i in range(nu + 1):
                u = i / nu
                v = j / nv
                x = 1.15 + 5.3 * u
                z = 162.1 + 0.75 * math.sin(min(u * 1.2, 1.0) * math.pi * 0.62) - 0.35 * u + (v - 0.5) * 1.3
                grid.append((x * s, -9.5, z))
        grid = np.array(grid)
        P = head_surface(grid)
        Nn = sdf.gradient(head_open, P).astype(float)
        P = P + Nn * 0.04
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


LASH_ROWS = 4


def lash_points(curl=0.0, length=1.0, lid=(0.0, 0.0)):
    """Upper lash cards on the lid edge: a bold lash line at the root that flicks out at the outer
    corner. `lid` (left, right) is the upper-lid close amount (1 = blink), so the lashes ride the
    lid in blinks and expressions."""
    nu = 28
    Vs, UVs, Ts = [], [], []
    off = 0
    for side, s in (("l", 1.0), ("r", -1.0)):
        amount = lid[0] if side == "l" else lid[1]
        R = cs.eye_rot(side).astype(float)
        us = np.linspace(-cs.EYE_W * 0.98, cs.EYE_W * 1.06, nu + 1)
        up = cm.upper_curve(us)
        meet = cf.meet_line(us)
        v_root = up - (up - meet) * amount + 0.05
        uv_root = np.stack([us, v_root], 1)
        roots = cmesh.lid_point(side, uv_root, 0.09)
        rows = []
        for k, u in enumerate(us):
            t = (u / cs.EYE_W + 1) / 2                       # 0 inner .. 1 outer
            L = (0.30 + 0.75 * t ** 1.6) * length
            closed = np.clip(amount, 0, 1)
            out = R[:, 0] * (0.2 + 0.9 * t ** 2) - R[:, 1] * 0.85 + R[:, 2] * (0.55 - 1.2 * closed)
            out /= np.linalg.norm(out)
            upv = R[:, 2] * (1 - 1.6 * closed) - R[:, 1] * 0.25
            upv /= np.linalg.norm(upv)
            pts = [roots[k]]
            dvec = out
            for r in range(1, LASH_ROWS + 1):
                a = r / LASH_ROWS
                bend = (0.25 + 0.6 * curl) * a
                dvec = out * (1 - bend) + upv * bend
                dvec /= np.linalg.norm(dvec)
                pts.append(pts[-1] + dvec * L / LASH_ROWS)
            rows.append(pts)
        P = np.array([rows[i][j] for j in range(LASH_ROWS + 1) for i in range(nu + 1)])
        uv = np.array([(i / nu, j / LASH_ROWS) for j in range(LASH_ROWS + 1) for i in range(nu + 1)])
        tris = []
        for j in range(LASH_ROWS):
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
    extra = {"Lash_Length_Pos": lash_points(length=1.35)[0] - V,
             "Lash_Length_Neg": lash_points(length=0.7)[0] - V,
             "Lash_Curl_Pos": lash_points(curl=1.0)[0] - V,
             "Lash_Curl_Neg": lash_points(curl=-0.6)[0] - V}
    for name, (al, ar) in cf.lash_upper_amounts().items():
        if al or ar:
            extra[name] = lash_points(lid=(al, ar))[0] - V
    N = vertex_normals(V, T)
    return V, T, UV[T], N, extra


HAIRS = {
    "LamplighterBob": dict(root="6F4128", tip="8E3B26", flow="vertical"),
    "FallingWater": dict(root="3B2419", tip="553322", flow="vertical"),
    "RopeBraid": dict(root="D4A55A", tip="E3C27E", flow="braid"),
}


def build_hair(style, long_ears):
    """Chunky swept locks (char_hair.py), smoothed and decimated; the braid gets its tie."""
    field, top, bottom = ch.style_locks(style, long_ears)
    lo, hi = (-15, -13, bottom - 3), (15, 16, 175)
    tie_fn = None
    if style == "RopeBraid":
        path = cs.braid_path(lambda P: cs.frame_sdf(P, "FrameB"))
        bf, tie_fn = ch.braid_field(path)
        f0 = field
        field = lambda P: cs.smin(f0(P), bf(P), 1.0)
        lo, hi = (-14, -16, 104), (17, 15, 175)
    V, Fc = sdf.march(field, lo, hi, STEP["hair"])
    V, tris = clean_cut_decimate(V, Fc, BUDGET["hair"], keep_largest=True)
    V = smooth_mesh(V, tris, iters=3)
    N = vertex_normals(V, tris)
    mat_idx = np.zeros(len(tris), dtype=int)
    if tie_fn is not None:
        Vt, Ft = sdf.march(tie_fn, (4, -17, 104), (16, -4, 125), 0.1)
        Vt, Tt = clean_cut_decimate(Vt, Ft, 400)
        Nt = vertex_normals(Vt, Tt)
        tris = np.concatenate([tris, Tt + len(V)])
        mat_idx = np.concatenate([mat_idx, np.ones(len(Tt), dtype=int)])
        V = np.concatenate([V, Vt])
        N = np.concatenate([N, Nt])
    uv = smart_uv(V, tris, angle=70)
    log(f"hair {style}{' long-ear' if long_ears else ''}: {len(tris)} tris")
    return V, tris, uv, N, mat_idx, top, bottom


def smooth_mesh(V, T, iters=3, lam=0.5, mu=-0.53):
    """Taubin smoothing: removes marching-cubes ripples without shrinking the locks."""
    nb = cmesh.adjacency(len(V), T.tolist())
    V = V.copy()
    for _ in range(iters):
        for k in (lam, mu):
            avg = np.array([V[n].mean(0) if len(n) else V[i] for i, n in enumerate(nb)])
            V = V + (avg - V) * k
    return V


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
        V = smooth_mesh(V, tris, iters=2)          # soft hems and collar instead of voxel steps
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

    # ---- head + ears + mouth interior (one skeletal mesh, three sections)
    Vh, Th, UVh, Nh, seam_loop = build_head()
    Ve, Te, UVe, Ne, ear_m = build_ears()
    Vm, Tm, UVm, Nm, mpid = build_mouth_interior()
    pm = corner_paintmap(Vh, Th, UVh, Nh, 1024 if not FAST else 512)
    base, prev, masks = cp.paint_skin(pm, "head")
    img_head = image("T_Head_BaseColor", base)
    image("T_Head_Preview", prev)
    image("T_Head_Masks", masks)
    pme = corner_paintmap(Ve, Te, UVe, Ne, 256)
    ebase, eprev, emasks = cp.paint_skin(pme, "ears")
    img_ears = image("T_Ears_BaseColor", ebase)
    image("T_Ears_Masks", emasks)
    img_mouth = image("T_Mouth_BaseColor", cp.paint_mouth())
    m_head = material("M_Lyris_Head", img_head, rough=0.75)
    m_ears = material("M_Lyris_Ears", img_ears, rough=0.75)
    m_mouth = material("M_Lyris_Mouth", img_mouth, rough=0.6)
    Vhe = np.concatenate([Vh, Ve, Vm])
    The = np.concatenate([Th, Te + len(Vh), Tm + len(Vh) + len(Ve)])
    UVhe = np.concatenate([UVh, UVe, UVm])
    Nhe = np.concatenate([Nh, Ne, Nm])
    mi = np.concatenate([np.zeros(len(Th), int), np.ones(len(Te), int), np.full(len(Tm), 2)])
    zh, zm = np.zeros_like(Vh), np.zeros_like(Vm)
    ear_full = {k: np.concatenate([zh, D, zm]) for k, D in ear_m.items()}
    morphs = head_morphs(Vhe, Nhe, ear_full)
    Vx, morphs = to_export(Vhe, morphs)
    w_head = skin_weights(cs.head_xform(Vh))
    w = w_head + rigid_weights(len(Ve)) + rigid_weights(len(Vm))
    objs["Head"] = make_object("SKM_Lyris_Head", Vx, The, UVhe, Nhe, w, morphs, [m_head, m_ears, m_mouth], mi)
    meta["meshes"]["Head"] = {"tris": int(len(The)), "head_tris": int(len(Th)), "ear_tris": int(len(Te)),
                              "mouth_tris": int(len(Tm)), "morphs": sorted(morphs)}
    seam_x = seam_loop                       # the seam is below the head blend: unchanged by head_xform
    log(f"head morphs {len(morphs)}")

    # ---- bodies
    body_data = {}
    for frame_id in ("FrameA", "FrameB"):
        Vb, Tb, UVb, Nb = build_body(frame_id, seam_x)
        pmb = corner_paintmap(Vb, Tb, UVb, Nb, 1024 if not FAST else 512)
        base, prev, masks = cp.paint_skin(pmb, "body")
        img = image(f"T_Body_{frame_id}_BaseColor", base)
        image(f"T_Body_{frame_id}_Masks", masks)
        mb = material(f"M_Lyris_Body_{frame_id}", img, rough=0.75)
        wb = skin_weights(Vb)
        wb = smooth_weights(Vb, Tb, wb, SMOOTH_REGIONS)
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
    mor = eval_morphs(Vy, Ny, HEAD_GROUPS)       # eyes follow the creator morphs, never the lids
    Vyx, mor = to_export(Vy, mor)
    objs["Eyes"] = make_object("SKM_Lyris_Eyes", Vyx, Ty, UVy, Ny, rigid_weights(len(Vy)), mor, [m_eye])
    meta["meshes"]["Eyes"] = {"tris": int(len(Ty)), "morphs": sorted(mor)}

    Vbr, Tbr, UVbr, Nbr = build_brows()
    brow = cp.paint_brow(256, 64)
    img_brow = image("T_Brows_Natural", brow)
    m_brow = material("M_Lyris_Brows", img_brow, alpha=True, rough=0.9)
    mor = head_morphs(Vbr, Nbr)
    mor = {k: D for k, D in mor.items() if not k.startswith(("Eye_Blink", "Eye_Squint", "Eye_Wide", "Mouth_"))}
    Vbx, mor = to_export(Vbr, mor)
    objs["Brows"] = make_object("SKM_Lyris_Brows", Vbx, Tbr, UVbr, Nbr, rigid_weights(len(Vbr)), mor, [m_brow])
    meta["meshes"]["Brows"] = {"tris": int(len(Tbr)), "morphs": sorted(mor)}

    Vl, Tl, UVl, Nl, lash_m = build_lashes()
    lash = cp.paint_lash(256, 64)
    img_lash = image("T_Lashes_Natural", lash)
    m_lash = material("M_Lyris_Lashes", img_lash, alpha=True, rough=0.9)
    mor = eval_morphs(Vl, Nl, HEAD_GROUPS, lash_m)
    # expression brow/mouth parts do not touch the lashes; their lid part is in lash_m
    Vlx, mor = to_export(Vl, mor)
    objs["Lashes"] = make_object("SKM_Lyris_Lashes", Vlx, Tl, UVl, Nl, rigid_weights(len(Vl)), mor, [m_lash])
    meta["meshes"]["Lashes"] = {"tris": int(len(Tl)), "morphs": sorted(mor)}
    log("eyes, brows, lashes done")

    # ---- hair
    hair_bones = ["head", "neck_02", "neck_01", "spine_05", "spine_04", "spine_03", "clavicle_l", "clavicle_r"]
    for style, spec in HAIRS.items():
        for long_ears in (False, True):
            if FAST and long_ears:
                continue
            Vr, Tr, UVr, Nr, mi, top, bottom = build_hair(style, long_ears)
            tag = f"Hair_{style}" + ("_LongEar" if long_ears else "")
            pmh = corner_paintmap(Vr, Tr, UVr, Nr, 1024 if not FAST else 512)
            mask = cp.paint_hair(pmh, top, bottom, spec["flow"])
            if not long_ears:
                image(f"T_{tag}_Masks", mask)
            prevh = cp.hair_preview(mask, cp.hexrgb(spec["root"]), cp.hexrgb(spec["tip"]))
            img = image(f"T_{tag}_BaseColor", prevh)
            mats = [material(f"M_Lyris_{tag}", img, rough=0.55, spec=0.4)]
            if style == "RopeBraid":
                mats.append(material(f"M_Lyris_{tag}_Tie", colour=tuple(srgb_to_lin(cp.REDBAND)), rough=0.7))
            mor = eval_morphs(Vr, Nr, HEAD_GROUPS, hair_extra_morphs(Vr, Nr, bottom))
            Vrx, mor = to_export(Vr, mor)
            wr = skin_weights(Vrx, hair_bones)
            objs[tag] = make_object(f"SKM_Lyris_{tag}", Vrx, Tr, UVr, Nr, wr, mor, mats, mi)
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
        meta["meshes"][key]["morphs"] = object_morphs(ob)
    for key, ob in objs.items():
        export(f"SKM_Lyris_{key}", [ob])
    log("exported")
    with open(os.path.join(HERE, "character_meta.json"), "w") as f:
        json.dump(meta, f, indent=1)
    write_morph_table(meta)
    for k, v in meta["meshes"].items():
        print(f"  {k:40s} {v['tris']:6d} tris  {len(v['morphs']):3d} morphs")

    cache = os.environ.get("LYRIS_SCENE_CACHE")
    if cache:          # optional: keep the built scene to re-render previews (--previews-only)
        bpy.ops.wm.save_as_mainfile(filepath=cache)
    render_previews(objs)


def render_previews(objs):
    import char_preview
    char_preview.render_all(objs, ARM, PEOPLE_LOOKS, HERE, TEX, fast=FAST)
    log("previews done")
    before = load_before()
    if before:
        char_preview.render_compare(objs, before, HERE, fast=FAST)
        log("before/after comparisons done")


def previews_only():
    """Re-renders the previews from a scene saved by a full run with LYRIS_SCENE_CACHE set."""
    global ARM
    bpy.ops.wm.open_mainfile(filepath=os.environ["LYRIS_SCENE_CACHE"])
    ARM = bpy.data.objects["Armature"]
    objs = {o.name.replace("SKM_Lyris_", ""): o for o in bpy.data.objects if o.name.startswith("SKM_Lyris_")}
    render_previews(objs)


BEFORE_DIR = os.environ.get("LYRIS_BEFORE_DIR", os.path.join(HERE, "before_T25"))


def load_before():
    """Imports the T25 meshes (for the before/after sheets) if a copy of them is in BEFORE_DIR
    (default Art/Character/before_T25/, not committed): SKM_Lyris_*.glb plus textures/."""
    if not os.path.isdir(BEFORE_DIR):
        return {}
    out = {}
    names = ["Head", "Eyes", "Brows", "Lashes", "Body_FrameA", "Outfit_PlainTraveller_FrameA", "Hair_LamplighterBob"]
    for key in names:
        path = os.path.join(BEFORE_DIR, f"SKM_Lyris_{key}.glb")
        if not os.path.exists(path):
            continue
        before_objs = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=path)
        new = [o for o in bpy.data.objects if o not in before_objs]
        for o in new:
            if o.type == "MESH":
                o.data.materials.clear()
                tex = os.path.join(BEFORE_DIR, "textures")
                img_name = {"Head": "T_Head_BaseColor", "Eyes": "T_Eyes_BaseColor", "Brows": "T_Brows_Natural",
                            "Lashes": "T_Lashes_Natural", "Body_FrameA": "T_Body_FrameA_BaseColor",
                            "Outfit_PlainTraveller_FrameA": "T_Outfit_PlainTraveller_FrameA_BaseColor",
                            "Hair_LamplighterBob": "T_Hair_LamplighterBob_BaseColor"}[key]
                img = bpy.data.images.load(os.path.join(tex, img_name + ".png"))
                prefix = {"Head": "M_Lyris_Head", "Eyes": "M_Lyris_Eyes", "Brows": "M_Lyris_Brows",
                          "Lashes": "M_Lyris_Lashes", "Body_FrameA": "M_Lyris_Body_FrameA",
                          "Outfit_PlainTraveller_FrameA": "M_Lyris_Outfit_PlainTraveller_FrameA",
                          "Hair_LamplighterBob": "M_Lyris_Hair_LamplighterBob"}[key]
                m = material(prefix + "_Before", img, alpha=key in ("Brows", "Lashes"))
                for _ in range(max(1, len(o.data.polygons) and 3)):
                    o.data.materials.append(m)
                out[key] = o
            else:
                o.hide_render = True
    log(f"loaded {len(out)} T25 meshes for the before/after sheets")
    return out


def object_morphs(ob):
    keys = ob.data.shape_keys
    return sorted(kb.name for kb in keys.key_blocks[1:]) if keys else []


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
        "# Morph targets (T25, T46)",
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
    lines += ["", "## Face rig (T46): blinks, mouth and expressions", "",
              "Not creator sliders: these are for the creator's expression and blink previews (spec 9.6) and for",
              "animation. Each `Expr_<Name>` is a ready mix of the base shapes, so one weight plays a preset.",
              "They live on the Head, Lashes and (brow parts) Brows; the eyes never move with them.", "",
              "| Morph | What it does | Meshes |", "|---|---|---|"]
    rig_doc = {
        "Eye_Blink_L / _R": "upper lid closes down over the eye, lower lid rises to meet it",
        "Eye_Squint_L / _R": "lower lid lifts, upper lid drops a little (smiling eyes)",
        "Eye_Wide_L / _R": "lids open wider (surprise)",
        "Mouth_Open": "jaw drops about 13 degrees, lips part to show the mouth interior",
        "Mouth_Smile, Mouth_Smile_L / _R": "mouth corners rise and widen, cheeks lift",
        "Mouth_Frown": "mouth corners turn down",
        "Mouth_Press": "lips press a little thinner",
        "Brow_Raise_L / _R, Brow_InnerUp, Brow_Furrow": "brow expressions",
    }
    for k, v in rig_doc.items():
        lines.append(f"| `{k}` | {v} | Head, Lashes (lids), Brows (brows) |")
    for name, mix in cf.PRESETS.items():
        parts = ", ".join(f"{k} {w:g}" for k, w in mix.items())
        lines.append(f"| `Expr_{name}` | preset: {parts} | Head, Lashes, Brows |")
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
    if "--previews-only" in sys.argv:
        previews_only()
    else:
        main()
