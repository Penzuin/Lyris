"""Preview renders of the Lyris base character (Cycles, in bpy).

Like the island previews these only stand in for the Unreal materials: the skin texture is
multiplied by a skin swatch (what the appearance material's SkinTone does), brows and lashes
by a hair swatch, and the light is a warm dusk key with lavender fill (the creator's
`DuskDeck` rig in design/character_creator.md 9.5).
"""

import math
import os

import bpy
import numpy as np
from mathutils import Vector
from PIL import Image, ImageDraw, ImageFont

import char_paint as cp

SKIN = {"Human": "E2B48C", "Human2": "A0633F", "MoonlitElf": "D4C8E6", "Deepkin": "86B8AA"}


def lin(hexstr):
    c = cp.hexrgb(hexstr)
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return (*c, 1.0)


def tint_material(mat, hexstr):
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tex = next(n for n in nt.nodes if n.type == "TEX_IMAGE")
    mix = nt.nodes.get("PreviewTint")
    if mix is None:
        mix = nt.nodes.new("ShaderNodeMix")
        mix.name = "PreviewTint"
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 1.0
        nt.links.new(tex.outputs["Color"], mix.inputs[6])
        nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
    mix.inputs[7].default_value = lin(hexstr)


def skin_material_setup(mat, hexstr):
    """Skin preview: tint, a little subsurface warmth and a soft emission lift so shadows stay
    warm and painterly, never muddy."""
    tint_material(mat, hexstr)
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Subsurface Weight"].default_value = 0.12
    bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.45, 0.3)
    bsdf.inputs["Subsurface Scale"].default_value = 0.006
    nt = mat.node_tree
    mix = nt.nodes["PreviewTint"]
    nt.links.new(mix.outputs[2], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 0.10


def lift(mat, k=0.08):
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    src = nt.nodes.get("PreviewTint") or next((n for n in nt.nodes if n.type == "TEX_IMAGE"), None)
    if src is not None:
        out = src.outputs[2] if src.type == "MIX" else src.outputs["Color"]
        nt.links.new(out, bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = k


def setup_scene(res=(900, 1200), samples=48):
    s = bpy.context.scene
    s.render.engine = "CYCLES"
    s.cycles.samples = samples
    s.cycles.use_denoising = True
    s.render.resolution_x, s.render.resolution_y = res
    s.render.film_transparent = False
    s.view_settings.view_transform = "AgX"
    s.view_settings.look = "AgX - Medium High Contrast"
    s.view_settings.look = "None"
    w = bpy.data.worlds.get("PreviewWorld") or bpy.data.worlds.new("PreviewWorld")
    s.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    # vertical gradient: peach horizon to lavender-blue sky (dusk deck)
    if "grad" not in nt.nodes:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.name = "grad"
        nt.links.new(tc.outputs["Generated"], sep.inputs[0])
        nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
        ramp.color_ramp.elements[0].position = 0.45
        ramp.color_ramp.elements[0].color = lin("E8C3A8")
        ramp.color_ramp.elements[1].position = 0.75
        ramp.color_ramp.elements[1].color = lin("9FA6CF")
        nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.9
    for name, kind, energy, rot, col, size in (
            ("Key", "SUN", 3.2, (52, 0, -38), "FFE2C0", 8),
            ("Rim", "SUN", 2.6, (60, 0, 160), "FFD6A8", 3),
            ("Fill", "SUN", 0.8, (70, 0, 70), "B8B6E8", 30)):
        ob = bpy.data.objects.get(name)
        if ob is None:
            ld = bpy.data.lights.new(name, kind)
            ob = bpy.data.objects.new(name, ld)
            s.collection.objects.link(ob)
        ob.data.energy = energy
        ob.data.color = lin(col)[:3]
        ob.data.angle = math.radians(size)
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
    cam = bpy.data.objects.get("PreviewCam")
    if cam is None:
        cd = bpy.data.cameras.new("PreviewCam")
        cam = bpy.data.objects.new("PreviewCam", cd)
        s.collection.objects.link(cam)
    s.camera = cam
    # a soft ground disc to stand on
    if bpy.data.objects.get("Ground") is None:
        bpy.ops.mesh.primitive_circle_add(vertices=64, radius=1.4, fill_type="NGON", location=(0, 0, 0))
        g = bpy.context.active_object
        g.name = "Ground"
        m = bpy.data.materials.new("GroundMat")
        m.use_nodes = True
        b = m.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = lin("D9C7A5")
        b.inputs["Roughness"].default_value = 0.95
        g.data.materials.append(m)
    return cam


def aim(cam, target, azim_deg, dist, elev_deg=4.0, lens=85, ortho=None):
    t = Vector(target)
    a, e = math.radians(azim_deg), math.radians(elev_deg)
    # azimuth 0 = in front of the character (character faces -Y)
    cam.location = t + Vector((math.sin(a) * math.cos(e) * dist, -math.cos(a) * math.cos(e) * dist, math.sin(e) * dist))
    cam.rotation_euler = (t - cam.location).to_track_quat("-Z", "Y").to_euler()
    if ortho:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = ortho
    else:
        cam.data.type = "PERSP"
        cam.data.lens = lens
    cam.data.clip_start = 0.01
    cam.data.clip_end = 100


def show(objs, names):
    for k, o in objs.items():
        o.hide_render = k not in names
    g = bpy.data.objects.get("Ground")


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
    d = ImageDraw.Draw(img)
    d.text(pos, text, font=font(size), fill=fill)
    return img


def render_all(objs, arm, looks, out_dir, tex_dir, fast=False):
    tmp = os.path.join(out_dir, ".preview_tmp")
    os.makedirs(tmp, exist_ok=True)
    samples = 16 if fast else 40
    cam = setup_scene(samples=samples)
    mats = {m.name: m for m in bpy.data.materials}
    hair_colour = {"LamplighterBob": "6F4128", "FallingWater": "3B2419", "RopeBraid": "D4A55A"}

    def skin(tone):
        for name in ("M_Lyris_Head", "M_Lyris_Ears", "M_Lyris_Body_FrameA", "M_Lyris_Body_FrameB"):
            skin_material_setup(mats[name], tone)

    def brows(hexstr):
        tint_material(mats["M_Lyris_Brows"], hexstr)
        tint_material(mats["M_Lyris_Lashes"], "2A1E1E")

    for m in mats.values():
        if m.name.startswith(("M_Lyris_Outfit", "M_Lyris_Hair")) and m.node_tree.nodes.get("Principled BSDF"):
            if any(n.type == "TEX_IMAGE" for n in m.node_tree.nodes):
                lift(m, 0.07)
    lift(mats["M_Lyris_Eyes"], 0.18)

    def outfit(frame):
        return {f"Body_{frame}", f"Outfit_PlainTraveller_{frame}", "Head", "Eyes", "Brows", "Lashes"}

    s = bpy.context.scene
    # ---- full body: front / three-quarter / side (Willow, bob, plain traveller)
    skin(SKIN["Human"])
    brows("553322")
    set_morphs(objs, {})
    full = []
    s.render.resolution_x, s.render.resolution_y = 700, 1200
    for name, az in (("front", 0), ("threequarter", -35), ("side", -90)):
        show(objs, outfit("FrameA") | {"Hair_LamplighterBob"})
        aim(cam, (0, 0, 0.88), az, 6.5, 3.0, lens=70)
        p = os.path.join(tmp, f"full_{name}.png")
        render(p)
        full.append(p)
    sheet = Image.new("RGB", (2100, 1200))
    for k, p in enumerate(full):
        sheet.paste(Image.open(p).convert("RGB"), (700 * k, 0))
    label(sheet, "Lyris base character: FrameA (Willow), Hair.LamplighterBob, Outfit.PlainTraveller - front / three-quarter / side", 24)
    sheet.save(os.path.join(out_dir, "preview.png"))
    for k, name in enumerate(("front", "threequarter", "side")):
        Image.open(full[k]).convert("RGB").save(os.path.join(out_dir, f"preview_{name}.png"))

    # ---- both frames, three hairstyles, skin tones
    s.render.resolution_x, s.render.resolution_y = 600, 1100
    combos = [("FrameA", "LamplighterBob", SKIN["Human"], "553322"),
              ("FrameB", "RopeBraid", SKIN["Human2"], "8E6A3A"),
              ("FrameA", "FallingWater", SKIN["MoonlitElf"], "3B2419"),
              ("FrameB", "LamplighterBob", SKIN["Deepkin"], "553322")]
    elf = looks["MoonlitElf"]["ears"]
    deep = looks["Deepkin"]["ears"]
    tiles = []
    for k, (frame, hair, tone, brow) in enumerate(combos):
        skin(tone)
        brows(brow)
        ears = {}
        hair_name = f"Hair_{hair}"
        if k == 2:
            ears, hair_name = elf, f"Hair_{hair}_LongEar"
        if k == 3:
            ears, hair_name = deep, f"Hair_{hair}_LongEar"
        if hair_name not in objs:
            hair_name = f"Hair_{hair}"
        set_morphs(objs, ears)
        show(objs, outfit(frame) | {hair_name})
        aim(cam, (0, 0, 0.88), -22, 6.6, 3.0, lens=70)
        p = os.path.join(tmp, f"combo_{k}.png")
        render(p)
        tiles.append((p, f"{frame} / {hair}"))
    sheet = Image.new("RGB", (2400, 1100))
    for k, (p, t) in enumerate(tiles):
        im = Image.open(p).convert("RGB")
        label(im, t, 20)
        sheet.paste(im, (600 * k, 0))
    sheet.save(os.path.join(out_dir, "preview_frames.png"))

    # ---- nude base, both frames (what the mesh itself is), front and side
    skin(SKIN["Human"])
    brows("553322")
    set_morphs(objs, {})
    s.render.resolution_x, s.render.resolution_y = 500, 1000
    tiles = []
    for frame in ("FrameA", "FrameB"):
        for az in (0, -90):
            show(objs, {f"Body_{frame}", "Head", "Eyes", "Brows", "Lashes"})
            aim(cam, (0, 0, 0.88), az, 6.5, 2.0, lens=70)
            p = os.path.join(tmp, f"base_{frame}_{az}.png")
            render(p)
            tiles.append(p)
    sheet = Image.new("RGB", (2000, 1000))
    for k, p in enumerate(tiles):
        sheet.paste(Image.open(p).convert("RGB"), (500 * k, 0))
    label(sheet, "Base bodies: FrameA (Willow) front, side; FrameB (Oak) front, side. 172 cm, 6.9 heads", 20)
    sheet.save(os.path.join(out_dir, "preview_bodies.png"))

    # ---- face close-up and Peoples
    s.render.resolution_x, s.render.resolution_y = 700, 800
    tiles = []
    for people, hair, brow in (("Human", "LamplighterBob", "553322"), ("MoonlitElf", "FallingWater", "3B2419"),
                               ("Deepkin", "RopeBraid", "8E6A3A")):
        skin(SKIN[people])
        brows(brow)
        set_morphs(objs, looks[people]["ears"])
        hn = f"Hair_{hair}" + ("" if people == "Human" else "_LongEar")
        if hn not in objs:
            hn = f"Hair_{hair}"
        show(objs, outfit("FrameA") | {hn})
        aim(cam, (0, -0.02, 1.575), -28, 1.25, 2.0, lens=85)
        p = os.path.join(tmp, f"face_{people}.png")
        render(p)
        tiles.append((p, people))
    sheet = Image.new("RGB", (2100, 800))
    for k, (p, t) in enumerate(tiles):
        im = Image.open(p).convert("RGB")
        label(im, t, 24)
        sheet.paste(im, (700 * k, 0))
    sheet.save(os.path.join(out_dir, "preview_peoples.png"))
    Image.open(tiles[0][0]).convert("RGB").save(os.path.join(out_dir, "preview_face.png"))

    # ---- face morphs at min and max (bald head, front, so the shape reads)
    skin(SKIN["Human"])
    brows("553322")
    s.render.resolution_x, s.render.resolution_y = 360, 420
    s.cycles.samples = max(12, samples // 2)
    tests = [("Face.JawWidth", "Jaw_Width"), ("Face.Length", "Face_Length"), ("Face.CheekFullness", "Cheek_Full"),
             ("Eyes.Size", "Eye_Size"), ("Eyes.Tilt", "Eye_Tilt"), ("Nose.Length", "Nose_Length"),
             ("Nose.TipSize", "NoseTip_Size"), ("Mouth.Width", "Mouth_Width"), ("Brows.Height", "Brow_Height"),
             ("Face.ChinPoint", "Chin_Point")]
    if fast:
        tests = tests[:4]
    rows = []
    neutral = os.path.join(tmp, "morph_neutral.png")
    show(objs, {"Head", "Eyes", "Brows", "Lashes", "Body_FrameA"})
    set_morphs(objs, {})
    aim(cam, (0, 0, 1.565), 0, 1.25, 0.0, lens=110)
    render(neutral)
    for slider, base in tests:
        imgs = []
        for end in ("Neg", "Pos"):
            names = [f"{base}_{end}"] if f"{base}_{end}" in all_keys(objs) else \
                [f"{base}_L_{end}", f"{base}_R_{end}"]
            set_morphs(objs, {n: 1.0 for n in names})
            p = os.path.join(tmp, f"morph_{base}_{end}.png")
            render(p)
            imgs.append(p)
        rows.append((slider, imgs))
    set_morphs(objs, {})
    cols = 2
    per = len(rows) // cols + (len(rows) % cols)
    W, H = 360, 420
    sheet = Image.new("RGB", (cols * (3 * W + 20), per * H + 50), (245, 238, 226))
    label(sheet, "Face morphs at slider min / neutral / max (weight 1 = the spec's guardrail end)", 24, (14, 12))
    for k, (slider, (lo, hi)) in enumerate(rows):
        cx, cy = (k // per) * (3 * W + 20), 50 + (k % per) * H
        for j, p in enumerate((lo, neutral, hi)):
            im = Image.open(p).convert("RGB")
            if j == 0:
                label(im, slider + "  -1", 18)
            if j == 2:
                label(im, "+1", 18)
            sheet.paste(im, (cx + j * W, cy))
    sheet.save(os.path.join(out_dir, "preview_morphs.png"))

    # ---- ear shapes
    s.render.resolution_x, s.render.resolution_y = 420, 420
    ear_sets = [("Human (none)", {}), ("Ears.Tip 1", {"Ear_Tip_L": 1, "Ear_Tip_R": 1}),
                ("Ears.Point 1 (elf)", {"Ear_Point_L": 1, "Ear_Point_R": 1}),
                ("Point + Droop", {"Ear_Point_L": 1, "Ear_Point_R": 1, "Ear_Droop_L": 1, "Ear_Droop_R": 1}),
                ("Point + angle up", {"Ear_Point_L": 1, "Ear_Point_R": 1, "Ear_PointAngle_L_Pos": 1, "Ear_PointAngle_R_Pos": 1}),
                ("Deepkin fin", {"Ear_Fin_L": 1, "Ear_Fin_R": 1, "Ear_Point_L": 0.45, "Ear_Point_R": 0.45})]
    if fast:
        ear_sets = ear_sets[:3]
    show(objs, {"Head", "Eyes", "Brows", "Lashes", "Body_FrameA"})
    aim(cam, (0.03, 0.0, 1.585), -62, 1.1, 4.0, lens=100)
    tiles = []
    for t, vals in ear_sets:
        set_morphs(objs, vals)
        p = os.path.join(tmp, f"ear_{len(tiles)}.png")
        render(p)
        tiles.append((p, t))
    set_morphs(objs, {})
    sheet = Image.new("RGB", (420 * len(tiles), 420))
    for k, (p, t) in enumerate(tiles):
        im = Image.open(p).convert("RGB")
        label(im, t, 18)
        sheet.paste(im, (420 * k, 0))
    sheet.save(os.path.join(out_dir, "preview_ears.png"))

    for f in os.listdir(tmp):
        os.remove(os.path.join(tmp, f))
    os.rmdir(tmp)


def all_keys(objs):
    out = set()
    for o in objs.values():
        if o.data.shape_keys:
            out.update(kb.name for kb in o.data.shape_keys.key_blocks)
    return out
