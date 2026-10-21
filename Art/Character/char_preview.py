"""Preview renders of the Lyris base character (T46: toon-shaded, EEVEE).

These stand in for the intended in-game look: a painterly toon shader (the light is read with
Shader to RGB and pushed through a soft two-tone ramp, warm in the light and cool lavender in
the shade, plus a soft warm rim), a thin dark-warm Freestyle outline, and the painted
textures multiplied by a skin, hair or cloth swatch (what the appearance material's SkinTone
and colour params do). The light rig is the creator's `DuskDeck` (design/character_creator.md
9.5): a low warm key, a lavender sky.

Cameras are fixed per shot (see SHOTS) so the T25 meshes in before_T25/ can be rendered with
the same cameras for the before/after sheets.
"""

import math
import os

import bpy
import numpy as np
from mathutils import Vector
from PIL import Image, ImageDraw, ImageFont

import char_paint as cp

SKIN = {"Human": "E2B48C", "Human2": "A0633F", "MoonlitElf": "D4C8E6", "Deepkin": "86B8AA"}
OUTLINE = (0.24, 0.16, 0.17)

# name -> (target (m), azimuth deg, distance (m), elevation deg, lens mm, resolution)
SHOTS = {
    "full_front": ((0, 0, 0.9), 0, 6.6, 3.0, 70, (700, 1200)),
    "full_threequarter": ((0, 0, 0.9), -35, 6.6, 3.0, 70, (700, 1200)),
    "full_side": ((0, 0, 0.9), -90, 6.6, 3.0, 70, (700, 1200)),
    "face": ((0, -0.03, 1.585), -24, 1.2, 2.0, 85, (700, 800)),
    "face_front": ((0, 0, 1.58), 0, 1.15, 0.0, 85, (600, 700)),
}


def lin(hexstr):
    c = cp.hexrgb(hexstr)
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return (*c, 1.0)


# ----------------------------------------------------------------------------- toon material

def toon_material(mat, tint_hex=None, shade_hex="B9A9CF", rim=0.35, alpha=False, gloss=0.0):
    """Rebuilds a material's node tree as the painterly toon shader, keeping its base texture."""
    nt = mat.node_tree
    tex = next((n for n in nt.nodes if n.type == "TEX_IMAGE"), None)
    img = tex.image if tex else None
    bsdf = nt.nodes.get("Principled BSDF")
    flat = tuple(bsdf.inputs["Base Color"].default_value) if bsdf else (0.8, 0.8, 0.8, 1)
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    if img is not None:
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = img
        base = t.outputs["Color"]
        alpha_out = t.outputs["Alpha"]
    else:
        rgb = nt.nodes.new("ShaderNodeRGB")
        rgb.outputs[0].default_value = flat
        base = rgb.outputs[0]
        alpha_out = None
    if tint_hex:
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 1.0
        mix.inputs[7].default_value = lin(tint_hex)
        mix.name = "Tint"
        nt.links.new(base, mix.inputs[6])
        base = mix.outputs[2]
    diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
    s2r = nt.nodes.new("ShaderNodeShaderToRGB")
    nt.links.new(diff.outputs[0], s2r.inputs[0])
    bw = nt.nodes.new("ShaderNodeRGBToBW")
    nt.links.new(s2r.outputs["Color"], bw.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "EASE"
    e = ramp.color_ramp.elements
    e[0].position, e[0].color = 0.10, lin(shade_hex)
    e[1].position, e[1].color = 0.26, (1.0, 0.97, 0.92, 1)
    nt.links.new(bw.outputs[0], ramp.inputs["Fac"])
    lit = nt.nodes.new("ShaderNodeMix")
    lit.data_type = "RGBA"
    lit.blend_type = "MULTIPLY"
    lit.inputs["Factor"].default_value = 1.0
    nt.links.new(base, lit.inputs[6])
    nt.links.new(ramp.outputs["Color"], lit.inputs[7])
    col = lit.outputs[2]
    if rim:
        lw = nt.nodes.new("ShaderNodeLayerWeight")
        lw.inputs["Blend"].default_value = 0.35
        rr = nt.nodes.new("ShaderNodeValToRGB")
        rr.color_ramp.elements[0].position = 0.62
        rr.color_ramp.elements[0].color = (0, 0, 0, 1)
        rr.color_ramp.elements[1].position = 0.8
        rr.color_ramp.elements[1].color = (1, 1, 1, 1)
        nt.links.new(lw.outputs["Facing"], rr.inputs["Fac"])
        add = nt.nodes.new("ShaderNodeMix")
        add.data_type = "RGBA"
        add.blend_type = "SCREEN"
        mul = nt.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = rim
        nt.links.new(rr.outputs["Color"], mul.inputs[0])
        nt.links.new(mul.outputs[0], add.inputs["Factor"])
        nt.links.new(col, add.inputs[6])
        add.inputs[7].default_value = lin("FFD8B8")
        col = add.outputs[2]
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(col, em.inputs["Color"])
    shader = em.outputs[0]
    if gloss:
        g = nt.nodes.new("ShaderNodeBsdfGlossy")
        g.inputs["Roughness"].default_value = 0.08
        ad = nt.nodes.new("ShaderNodeAddShader")
        mixs = nt.nodes.new("ShaderNodeMixShader")
        mixs.inputs[0].default_value = gloss
        nt.links.new(shader, mixs.inputs[1])
        nt.links.new(g.outputs[0], mixs.inputs[2])
        shader = mixs.outputs[0]
    if alpha and alpha_out is not None:
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mixa = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(alpha_out, mixa.inputs[0])
        nt.links.new(tr.outputs[0], mixa.inputs[1])
        nt.links.new(shader, mixa.inputs[2])
        shader = mixa.outputs[0]
        try:
            mat.surface_render_method = "BLENDED"
        except AttributeError:
            mat.blend_method = "BLEND"
    nt.links.new(shader, out.inputs["Surface"])


def set_tint(mat, hexstr):
    mix = mat.node_tree.nodes.get("Tint")
    if mix is not None:
        mix.inputs[7].default_value = lin(hexstr)


# ----------------------------------------------------------------------------- scene

def setup_scene():
    s = bpy.context.scene
    s.render.engine = "BLENDER_EEVEE"
    s.render.film_transparent = False
    s.view_settings.view_transform = "Standard"
    s.view_settings.look = "None"
    s.render.use_freestyle = True
    s.render.line_thickness_mode = "ABSOLUTE"
    s.render.line_thickness = 1.25
    vl = s.view_layers[0]
    fs = vl.freestyle_settings
    ls = fs.linesets[0] if fs.linesets else fs.linesets.new("Lines")
    ls.select_by_visibility = True
    ls.select_silhouette = True
    ls.select_border = False          # open seams (neck) and card edges draw no line
    ls.select_crease = False
    nolines = bpy.data.collections.get("NoOutline")
    if nolines is None:
        nolines = bpy.data.collections.new("NoOutline")
        s.collection.children.link(nolines)
    ls.select_by_collection = True
    ls.collection = nolines
    ls.collection_negation = "EXCLUSIVE"
    if ls.linestyle is None:
        ls.linestyle = bpy.data.linestyles.new("LyrisOutline")
    ls.linestyle.color = OUTLINE
    ls.linestyle.thickness = 1.25
    w = bpy.data.worlds.get("PreviewWorld") or bpy.data.worlds.new("PreviewWorld")
    s.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    if "grad" not in nt.nodes:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.name = "grad"
        nt.links.new(tc.outputs["Window"], sep.inputs[0])
        nt.links.new(sep.outputs["Y"], ramp.inputs["Fac"])
        ramp.color_ramp.elements[0].position = 0.0
        ramp.color_ramp.elements[0].color = lin("EBC8AE")
        ramp.color_ramp.elements[1].position = 1.0
        ramp.color_ramp.elements[1].color = lin("A9AED6")
        nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.0
    key = bpy.data.objects.get("Key")
    if key is None:
        ld = bpy.data.lights.new("Key", "SUN")
        key = bpy.data.objects.new("Key", ld)
        s.collection.objects.link(key)
    key.data.energy = 4.0
    key.data.color = lin("FFE6CC")[:3]
    key.rotation_euler = (math.radians(52), 0, math.radians(-32))
    cam = bpy.data.objects.get("PreviewCam")
    if cam is None:
        cd = bpy.data.cameras.new("PreviewCam")
        cam = bpy.data.objects.new("PreviewCam", cd)
        s.collection.objects.link(cam)
    s.camera = cam
    if bpy.data.objects.get("Ground") is None:
        bpy.ops.mesh.primitive_circle_add(vertices=64, radius=1.4, fill_type="NGON", location=(0, 0, 0))
        g = bpy.context.active_object
        g.name = "Ground"
        m = bpy.data.materials.new("GroundMat")
        m.use_nodes = True
        m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = lin("E3D2B4")
        g.data.materials.append(m)
        toon_material(m, rim=0, shade_hex="C9B9D2")
    return cam


def aim(cam, shot):
    target, azim, dist, elev, lens, res = SHOTS[shot] if isinstance(shot, str) else shot
    s = bpy.context.scene
    s.render.resolution_x, s.render.resolution_y = res
    t = Vector(target)
    a, e = math.radians(azim), math.radians(elev)
    cam.location = t + Vector((math.sin(a) * math.cos(e) * dist, -math.cos(a) * math.cos(e) * dist,
                               math.sin(e) * dist))
    cam.rotation_euler = (t - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.type = "PERSP"
    cam.data.lens = lens
    cam.data.clip_start = 0.01
    cam.data.clip_end = 100


def show(objs, names):
    for k, o in objs.items():
        o.hide_render = k not in names


def set_morphs(objs, values):
    for o in objs.values():
        keys = o.data.shape_keys
        if not keys:
            continue
        for kb in keys.key_blocks[1:]:
            kb.value = values.get(kb.name, 0.0)


def render(path):
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def font(size):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def label(img, text, size=22, pos=(14, 10), fill=(60, 45, 50)):
    ImageDraw.Draw(img).text(pos, text, font=font(size), fill=fill)
    return img


def sheet(paths, cols, title=None, labels=None, tile=None):
    ims = [Image.open(p).convert("RGB") for p in paths]
    w, h = tile or ims[0].size
    rows = (len(ims) + cols - 1) // cols
    top = 46 if title else 0
    out = Image.new("RGB", (cols * w, rows * h + top), (245, 238, 226))
    for k, im in enumerate(ims):
        if im.size != (w, h):
            im = im.resize((w, h))
        if labels:
            label(im, labels[k], 20)
        out.paste(im, ((k % cols) * w, top + (k // cols) * h))
    if title:
        label(out, title, 24, (14, 10))
    return out


def all_keys(objs):
    out = set()
    for o in objs.values():
        if o.data.shape_keys:
            out.update(kb.name for kb in o.data.shape_keys.key_blocks)
    return out


# ----------------------------------------------------------------------------- the previews

def prepare_materials(mats):
    for name, m in mats.items():
        if not m.use_nodes or name in ("GroundMat",):
            continue
        if name.startswith(("M_Lyris_Head", "M_Lyris_Ears", "M_Lyris_Body")):
            toon_material(m, SKIN["Human"], shade_hex="D9A7A6", rim=0.4)
        elif name.startswith("M_Lyris_Eyes"):
            toon_material(m, None, shade_hex="CFC6DD", rim=0, gloss=0.0)
        elif name.startswith(("M_Lyris_Brows", "M_Lyris_Lashes")):
            toon_material(m, "3B2419", shade_hex="8A7A90", rim=0, alpha=True)
        elif name.startswith("M_Lyris_Mouth"):
            toon_material(m, None, shade_hex="9A7A90", rim=0)
        elif name.startswith("M_Lyris_Hair") and name.endswith("_Tie"):
            toon_material(m, None, shade_hex="B08AAE", rim=0.2)
        elif name.startswith("M_Lyris_Hair"):
            toon_material(m, None, shade_hex="A896C2", rim=0.3)
        elif name.startswith("M_Lyris_Outfit"):
            toon_material(m, None, shade_hex="B9A9CF", rim=0.25)





def exclude_from_outline(objs):
    """Eyes, brows, lashes and the ground draw no Freestyle outline."""
    coll = bpy.data.collections["NoOutline"]
    for k, o in objs.items():
        if k.split(":")[-1] in ("Eyes", "Brows", "Lashes") and o.name not in coll.objects:
            coll.objects.link(o)
    g = bpy.data.objects.get("Ground")
    if g is not None and g.name not in coll.objects:
        coll.objects.link(g)


def render_all(objs, arm, looks, out_dir, tex_dir, fast=False, before=None):
    tmp = os.path.join(out_dir, ".preview_tmp")
    os.makedirs(tmp, exist_ok=True)
    cam = setup_scene()
    exclude_from_outline(objs)
    mats = {m.name: m for m in bpy.data.materials}
    prepare_materials(mats)
    s = bpy.context.scene
    s.eevee.taa_render_samples = 16 if fast else 48

    def skin(tone):
        for name in ("M_Lyris_Head", "M_Lyris_Ears", "M_Lyris_Body_FrameA", "M_Lyris_Body_FrameB"):
            set_tint(mats[name], tone)

    def brows(hexstr):
        set_tint(mats["M_Lyris_Brows"], hexstr)
        set_tint(mats["M_Lyris_Lashes"], "2A1C1C")

    def outfit(frame):
        return {f"Body_{frame}", f"Outfit_PlainTraveller_{frame}", "Head", "Eyes", "Brows", "Lashes"}

    def hair_of(style, long_ears=False):
        n = f"Hair_{style}" + ("_LongEar" if long_ears else "")
        return n if n in objs else f"Hair_{style}"

    out = {}

    # ---- full body: front / three-quarter / side (Willow, bob, plain traveller)
    skin(SKIN["Human"])
    brows("553322")
    set_morphs(objs, {"Expr_Calm": 1.0})
    full = []
    for shot in ("full_front", "full_threequarter", "full_side"):
        show(objs, outfit("FrameA") | {hair_of("LamplighterBob")})
        aim(cam, shot)
        p = os.path.join(tmp, f"{shot}.png")
        render(p)
        full.append(p)
        Image.open(p).convert("RGB").save(os.path.join(out_dir, f"preview_{shot.split('_', 1)[1]}.png"))
    sheet(full, 3, "Lyris base character (T46): FrameA (Willow), Hair.LamplighterBob, Outfit.PlainTraveller").save(
        os.path.join(out_dir, "preview.png"))

    # ---- both frames, three hairstyles, skin tones across the Peoples
    elf, deep = looks["MoonlitElf"]["ears"], looks["Deepkin"]["ears"]
    combos = [("FrameA", "LamplighterBob", SKIN["Human"], "553322", {}, False),
              ("FrameB", "RopeBraid", SKIN["Human2"], "8E6A3A", {}, False),
              ("FrameA", "FallingWater", SKIN["MoonlitElf"], "3B2419", elf, True),
              ("FrameB", "LamplighterBob", SKIN["Deepkin"], "553322", deep, True)]
    tiles, labels = [], []
    for k, (frame, hair, tone, brow, ears, le) in enumerate(combos):
        skin(tone)
        brows(brow)
        set_morphs(objs, dict(ears, Expr_Calm=1.0))
        show(objs, outfit(frame) | {hair_of(hair, le)})
        aim(cam, ((0, 0, 0.9), -22, 6.6, 3.0, 70, (600, 1100)))
        p = os.path.join(tmp, f"combo_{k}.png")
        render(p)
        tiles.append(p)
        labels.append(f"{frame} / {hair}")
    sheet(tiles, 4, None, labels).save(os.path.join(out_dir, "preview_frames.png"))

    # ---- the bare base bodies
    skin(SKIN["Human"])
    brows("553322")
    set_morphs(objs, {})
    tiles = []
    for frame in ("FrameA", "FrameB"):
        for az in (0, -90):
            show(objs, {f"Body_{frame}", "Head", "Eyes", "Brows", "Lashes"})
            aim(cam, ((0, 0, 0.9), az, 6.6, 2.0, 70, (500, 1000)))
            p = os.path.join(tmp, f"base_{frame}_{az}.png")
            render(p)
            tiles.append(p)
    sheet(tiles, 4, "Base bodies: FrameA (Willow) front, side; FrameB (Oak) front, side. 176 cm, 6.4 heads").save(
        os.path.join(out_dir, "preview_bodies.png"))

    # ---- face close-ups for the three Peoples
    tiles, labels = [], []
    for people, hair, brow in (("Human", "LamplighterBob", "553322"), ("MoonlitElf", "FallingWater", "3B2419"),
                               ("Deepkin", "RopeBraid", "8E6A3A")):
        skin(SKIN[people])
        brows(brow)
        set_morphs(objs, dict(looks[people]["ears"], Expr_Calm=1.0))
        show(objs, outfit("FrameA") | {hair_of(hair, people != "Human")})
        aim(cam, "face")
        p = os.path.join(tmp, f"face_{people}.png")
        render(p)
        tiles.append(p)
        labels.append(people)
    sheet(tiles, 3, None, labels).save(os.path.join(out_dir, "preview_peoples.png"))
    Image.open(tiles[0]).convert("RGB").save(os.path.join(out_dir, "preview_face.png"))

    # ---- expressions and blinks
    skin(SKIN["Human"])
    brows("553322")
    exprs = ["Calm", "Bright", "Laugh", "Wry", "Shy", "Surprised", "Sleepy", "Determined"]
    extra = [("Blink", {"Eye_Blink_L": 1.0, "Eye_Blink_R": 1.0}), ("Mouth open", {"Mouth_Open": 1.0}),
             ("Smile", {"Mouth_Smile": 1.0})]
    if fast:
        exprs = exprs[:3]
        extra = extra[:1]
    tiles, labels = [], []
    show(objs, outfit("FrameA") | {hair_of("LamplighterBob")})
    for e in exprs:
        set_morphs(objs, {f"Expr_{e}": 1.0})
        aim(cam, ((0, -0.02, 1.58), -15, 1.0, 1.0, 85, (420, 480)))
        p = os.path.join(tmp, f"expr_{e}.png")
        render(p)
        tiles.append(p)
        labels.append(f"Expr_{e}")
    for name, vals in extra:
        set_morphs(objs, vals)
        p = os.path.join(tmp, f"expr_{name}.png")
        render(p)
        tiles.append(p)
        labels.append(name)
    set_morphs(objs, {})
    sheet(tiles, 4 if not fast else 4, "Face rig: expression presets (Expr_*), blink, mouth open, smile",
          labels).save(os.path.join(out_dir, "preview_expressions.png"))

    # ---- creator face morphs at min / neutral / max
    s.eevee.taa_render_samples = 12 if fast else 24
    tests = [("Face.JawWidth", "Jaw_Width"), ("Face.Length", "Face_Length"), ("Face.CheekFullness", "Cheek_Full"),
             ("Eyes.Size", "Eye_Size"), ("Eyes.Tilt", "Eye_Tilt"), ("Nose.Length", "Nose_Length"),
             ("Nose.TipSize", "NoseTip_Size"), ("Mouth.Width", "Mouth_Width"), ("Brows.Height", "Brow_Height"),
             ("Face.ChinPoint", "Chin_Point")]
    if fast:
        tests = tests[:4]
    show(objs, {"Head", "Eyes", "Brows", "Lashes", "Body_FrameA"})
    shot = ((0, 0, 1.575), 0, 1.25, 0.0, 110, (360, 420))
    aim(cam, shot)
    neutral = os.path.join(tmp, "morph_neutral.png")
    set_morphs(objs, {})
    render(neutral)
    keys = all_keys(objs)
    rows = []
    for slider, base in tests:
        pair = []
        for end in ("Neg", "Pos"):
            names = [f"{base}_{end}"] if f"{base}_{end}" in keys else [f"{base}_L_{end}", f"{base}_R_{end}"]
            set_morphs(objs, {n: 1.0 for n in names})
            p = os.path.join(tmp, f"morph_{base}_{end}.png")
            render(p)
            pair.append(p)
        rows.append((slider, pair))
    set_morphs(objs, {})
    cols = 2
    per = (len(rows) + 1) // cols
    W, H = 360, 420
    sh = Image.new("RGB", (cols * (3 * W + 20), per * H + 50), (245, 238, 226))
    label(sh, "Face morphs at slider min / neutral / max (weight 1 = the spec's guardrail end)", 24, (14, 12))
    for k, (slider, (lo, hi)) in enumerate(rows):
        cx, cy = (k // per) * (3 * W + 20), 50 + (k % per) * H
        for j, p in enumerate((lo, neutral, hi)):
            im = Image.open(p).convert("RGB")
            if j == 0:
                label(im, slider + "  -1", 18)
            if j == 2:
                label(im, "+1", 18)
            sh.paste(im, (cx + j * W, cy))
    sh.save(os.path.join(out_dir, "preview_morphs.png"))

    # ---- ear shapes
    ear_sets = [("Human (none)", {}), ("Ears.Tip 1", {"Ear_Tip_L": 1, "Ear_Tip_R": 1}),
                ("Ears.Point 1 (elf)", {"Ear_Point_L": 1, "Ear_Point_R": 1}),
                ("Point + Droop", {"Ear_Point_L": 1, "Ear_Point_R": 1, "Ear_Droop_L": 1, "Ear_Droop_R": 1}),
                ("Point + angle up", {"Ear_Point_L": 1, "Ear_Point_R": 1, "Ear_PointAngle_L_Pos": 1,
                                      "Ear_PointAngle_R_Pos": 1}),
                ("Deepkin fin", {"Ear_Fin_L": 1, "Ear_Fin_R": 1, "Ear_Point_L": 0.45, "Ear_Point_R": 0.45})]
    if fast:
        ear_sets = ear_sets[:3]
    show(objs, {"Head", "Eyes", "Brows", "Lashes", "Body_FrameA"})
    aim(cam, ((0.03, 0.0, 1.6), -62, 1.15, 4.0, 100, (420, 420)))
    tiles, labels = [], []
    for t, vals in ear_sets:
        set_morphs(objs, vals)
        p = os.path.join(tmp, f"ear_{len(tiles)}.png")
        render(p)
        tiles.append(p)
        labels.append(t)
    set_morphs(objs, {})
    sheet(tiles, len(tiles), None, labels).save(os.path.join(out_dir, "preview_ears.png"))

    for f in os.listdir(tmp):
        os.remove(os.path.join(tmp, f))
    os.rmdir(tmp)


def render_compare(objs, before_objs, out_dir, fast=False):
    """Before (T25 meshes) and after (T46) with the same cameras, both toon-shaded."""
    tmp = os.path.join(out_dir, ".preview_tmp")
    os.makedirs(tmp, exist_ok=True)
    cam = setup_scene()
    s = bpy.context.scene
    s.eevee.taa_render_samples = 16 if fast else 40
    mats = {m.name: m for m in bpy.data.materials}
    prepare_materials(mats)
    for m in mats.values():
        if m.name.startswith(("M_Lyris_Head", "M_Lyris_Ears", "M_Lyris_Body")):
            set_tint(m, SKIN["Human"])
        if m.name.startswith(("M_Lyris_Brows",)):
            set_tint(m, "553322")
        if m.name.startswith(("M_Lyris_Lashes",)):
            set_tint(m, "2A1C1C")
    every = dict(objs)
    every.update({f"before:{k}": o for k, o in before_objs.items()})
    exclude_from_outline(every)
    after_names = {"Body_FrameA", "Outfit_PlainTraveller_FrameA", "Head", "Eyes", "Brows", "Lashes",
                   "Hair_LamplighterBob"}
    before_names = {f"before:{k}" for k in after_names if f"before:{k}" in every}
    results = {}
    for shot in ("face", "face_front", "full_threequarter"):
        pair = []
        for tag, names in (("before", before_names), ("after", after_names)):
            show(every, names)
            set_morphs(every, {"Expr_Calm": 1.0} if tag == "after" else {})
            aim(cam, shot)
            p = os.path.join(tmp, f"cmp_{shot}_{tag}.png")
            render(p)
            pair.append(p)
        im = sheet(pair, 2, f"Before (T25) / after (T46), same camera: {shot.replace('_', ' ')}",
                   ["Before: T25", "After: T46"])
        path = os.path.join(out_dir, f"preview_compare_{shot}.png")
        im.save(path)
        results[shot] = path
    for f in os.listdir(tmp):
        os.remove(os.path.join(tmp, f))
    os.rmdir(tmp)
    return results
