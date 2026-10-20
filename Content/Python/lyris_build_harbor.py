"""Builds the first Lyris prototype map: Moonharbor's bay at golden hour.

/Game/Lyris/Maps/Harbor gets: sky and golden-hour lighting, a sea out to the horizon,
a small walkable island, a lighthouse, a wooden dock reaching the shore, the dock lamp
(cold moonglass light, per Lyris canon) and the sailable boat (C++ class ALyrisBoat).
Storybook Painterly palette.

init_unreal.py calls build() each time the editor opens. It does nothing if the map
already holds this BUILD_VERSION; otherwise it clears the map and rebuilds it, so
bumping BUILD_VERSION is how a new layout reaches the project.

Manual rebuild (Output Log, Python):  import lyris_build_harbor as h; h.build(force=True)
"""

import json
import math
import os

import unreal

BUILD_VERSION = 8
MAP_PATH = "/Game/Lyris/Maps/Harbor"
MAT_DIR = "/Game/Lyris/Materials/Prototype"
MARKER_PREFIX = "LyrisBuild_v"

# Storybook Painterly palette (sRGB hex, roughness, metallic) from the Lyris house style.
PALETTE = {
    "Sand":       ("F1E9DC", 0.9, 0.0),
    "Grass":      ("8A9A48", 0.85, 0.0),
    "Terracotta": ("C8643A", 0.7, 0.0),
    "Clay":       ("36221A", 0.8, 0.0),
    "Wood":       ("8B5A3A", 0.75, 0.0),
    "DarkWood":   ("4A2A1C", 0.8, 0.0),
    "Salt":       ("F1E9DC", 0.6, 0.0),
    "RedBand":    ("C8443A", 0.6, 0.0),
    "Gold":       ("E3AE45", 0.35, 0.6),
    "Sail":       ("F7EEDC", 0.9, 0.0),
    "Stone":      ("9C9488", 0.9, 0.0),
    "Leaf":       ("6E8A3A", 0.85, 0.0),
    "Shallows":   ("7FD0D6", 0.1, 0.0),
}
MOONGLASS = "7AC0E6"  # cold lamp light, Quiet Reach palette

# The island is the sculpted model from Art/TestIsland (make_island.py).
ISLAND_DIR = "Art/TestIsland"
ISLAND_GLB = "test_island.glb"
GRASS_GLB = "test_island_grass.glb"
FOLIAGE_GLB = "test_island_foliage.glb"
FOLIAGE_ASSET_DIR = "/Game/Lyris/Meshes/TestIslandFoliage_v8"
GRASS_ASSET_DIR = "/Game/Lyris/Meshes/TestIslandGrass_v8"
TEXTURE_ASSET_DIR = "/Game/Lyris/Textures/Island_v8"
ISLAND_META = "island_meta.json"
ISLAND_ASSET_DIR = "/Game/Lyris/Meshes/TestIsland_v8"

DOCK_X0, DOCK_X1, DOCK_Y, DOCK_TOP = 1150.0, 2850.0, 150.0, 72.0
BOAT_START = (2450.0, -230.0)
LAMP_POS = (2760.0, 290.0)
LIGHTHOUSE_POS = (-760.0, -660.0)


def _log(msg):
    unreal.log("[Lyris] " + msg)


def _linear(hex_str):
    def ch(v):
        c = int(v, 16) / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return unreal.LinearColor(ch(hex_str[0:2]), ch(hex_str[2:4]), ch(hex_str[4:6]), 1.0)


def _srgb_color(hex_str):
    return unreal.Color(r=int(hex_str[0:2], 16), g=int(hex_str[2:4], 16), b=int(hex_str[4:6], 16), a=255)


def _new_material(name):
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    return tools.create_asset(name, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())


def _make_material(name, hex_str, roughness, metallic, emissive=0.0):
    path = f"{MAT_DIR}/M_{name}"
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        return unreal.load_asset(path)
    mat = _new_material(f"M_{name}")
    mel = unreal.MaterialEditingLibrary
    color = mel.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -400, 0)
    color.set_editor_property("constant", _linear(hex_str))
    mel.connect_material_property(color, "", unreal.MaterialProperty.MP_BASE_COLOR)
    rough = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -400, 200)
    rough.set_editor_property("r", roughness)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    if metallic:
        metal = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -400, 300)
        metal.set_editor_property("r", metallic)
        mel.connect_material_property(metal, "", unreal.MaterialProperty.MP_METALLIC)
    if emissive:
        mult = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -200, 400)
        mult.set_editor_property("const_b", emissive)
        mel.connect_material_expressions(color, "", mult, "A")
        mel.connect_material_property(mult, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat)
    return mat


def _make_sea_material():
    """Deep teal that turns pale turquoise at glancing angles, glossy for sun glints."""
    path = f"{MAT_DIR}/M_Sea"
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        return unreal.load_asset(path)
    mat = _new_material("M_Sea")
    mel = unreal.MaterialEditingLibrary
    deep = mel.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -700, -100)
    deep.set_editor_property("constant", _linear("2E8A9C"))
    shallow = mel.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -700, 50)
    shallow.set_editor_property("constant", _linear("7FD0D6"))
    try:
        fres = mel.create_material_expression(mat, unreal.MaterialExpressionFresnel, -700, 200)
        lerp = mel.create_material_expression(mat, unreal.MaterialExpressionLinearInterpolate, -400, 0)
        mel.connect_material_expressions(deep, "", lerp, "A")
        mel.connect_material_expressions(shallow, "", lerp, "B")
        mel.connect_material_expressions(fres, "", lerp, "Alpha")
        mel.connect_material_property(lerp, "", unreal.MaterialProperty.MP_BASE_COLOR)
    except Exception:
        mel.connect_material_property(deep, "", unreal.MaterialProperty.MP_BASE_COLOR)
    rough = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -400, 300)
    rough.set_editor_property("r", 0.08)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    spec = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -400, 400)
    spec.set_editor_property("r", 0.8)
    mel.connect_material_property(spec, "", unreal.MaterialProperty.MP_SPECULAR)
    mel.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat)
    return mat


# ----------------------------------------------------------------------------- island materials
# The island's look is computed in world space inside the materials, so it never depends on
# extra data surviving the import:
#   terrain  grass / sand / worn path from the island splat map (Art/TestIsland/textures/splat.png),
#            rock wherever the ground is steep, textures wrapped from three sides on cliffs
#            (triplanar) so nothing stretches, and a soft warm-to-cool tone across the island.
#   rock     triplanar stone with grass only on its flat tops.
#   leaves   one soft gradient across each canopy (dark underneath, sunlit on top) plus a little
#            self-light so trees never go muddy in shadow.
#   grass    darker root to light tip along the blade, tinted by the large-scale ground colour,
#            swaying in a slow travelling wind; wildflowers are masked cards that sway gently.

# One palette for everything on the island, so ground, rock, grass and trees always agree.
# Textures only add light/dark detail around these colours.
ISLAND_PALETTE = {
    "grass": "9DB872",          # meadow ground and grass blades
    "grass_shade": "6E9061",
    "sand": "EFE2C4",
    "path": "CDAE86",
    "rock_lit": "D6BC9F",       # muted warm stone ...
    "rock_shade": "8E7680",     # ... with lavender shadows
    "bark": "8A6A5A",
}
FOLIAGE_COLOURS = {  # species: (underside, sunlit top)
    "Oak": ("4F7558", "CFE08E"),
    "Bush": ("547A5A", "CCDE8C"),
    "Birch": ("6C8C5E", "E6EFA4"),
    "Pine": ("36584F", "93B486"),
    "Blossom": ("B87C8C", "FFE6DC"),
}

SPLAT_EXTENT = 3200.0  # the splat map covers -3200..3200 cm on X and Y (see island_meta.json)
TILE = 1.0 / 400.0     # ground textures repeat every 4 m


class _Graph:
    """Small helper for building material graphs from Python."""

    def __init__(self, name):
        self.name = f"M_{name}_v{BUILD_VERSION}"  # versioned: a rebuild never edits a material in use
        self.path = f"{MAT_DIR}/{self.name}"
        self.exists = unreal.EditorAssetLibrary.does_asset_exist(self.path)
        self.mat = unreal.load_asset(self.path) if self.exists else _new_material(self.name)
        self.mel = unreal.MaterialEditingLibrary
        self.y = 0
        self._wp = self._nrm = None

    def node(self, cls, **props):
        expr = self.mel.create_material_expression(self.mat, cls, -900, self.y)
        self.y += 120
        for key, value in props.items():
            expr.set_editor_property(key, value)
        return expr

    def link(self, src, dst, src_out="", dst_in=""):
        self.mel.connect_material_expressions(src, src_out, dst, dst_in)

    def const(self, value):
        return self.node(unreal.MaterialExpressionConstant, r=value)

    def colour(self, hex_str):
        return self.node(unreal.MaterialExpressionConstant3Vector, constant=_linear(hex_str))

    def op(self, cls, a, b=None, a_out="", b_out="", const_b=None):
        expr = self.node(cls) if const_b is None else self.node(cls, const_b=const_b)
        self.link(a, expr, a_out, "A")
        if b is not None:
            self.link(b, expr, b_out, "B")
        return expr

    def mul(self, a, b=None, a_out="", b_out="", k=None):
        return self.op(unreal.MaterialExpressionMultiply, a, b, a_out, b_out, k)

    def add(self, a, b=None, a_out="", b_out="", k=None):
        return self.op(unreal.MaterialExpressionAdd, a, b, a_out, b_out, k)

    def lerp(self, a, b, alpha, a_out="", b_out="", alpha_out=""):
        expr = self.node(unreal.MaterialExpressionLinearInterpolate)
        self.link(a, expr, a_out, "A")
        self.link(b, expr, b_out, "B")
        self.link(alpha, expr, alpha_out, "Alpha")
        return expr

    def single(self, cls, src, src_out="", **props):
        expr = self.node(cls, **props)
        self.link(src, expr, src_out, "")
        return expr

    def mask(self, src, channels):
        return self.single(unreal.MaterialExpressionComponentMask, src, r="R" in channels, g="G" in channels,
                           b="B" in channels, a="A" in channels)

    def saturate(self, src):
        return self.single(unreal.MaterialExpressionSaturate, src)

    def wp(self):
        if self._wp is None:
            self._wp = self.node(unreal.MaterialExpressionWorldPosition)
        return self._wp

    def normal(self):
        if self._nrm is None:
            self._nrm = self.node(unreal.MaterialExpressionVertexNormalWS)
        return self._nrm

    def tex(self, texture, uv=None, linear=False):
        expr = self.node(unreal.MaterialExpressionTextureSample, texture=texture)
        if linear:
            expr.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        if uv is not None:
            self.link(uv, expr, "", "UVs")
        return expr

    def world_uv(self, scale):
        return self.mul(self.mask(self.wp(), "RG"), k=scale)

    def triplanar(self, texture, scale):
        """Samples a texture from three sides and blends by the surface direction (no stretching)."""
        w = self.single(unreal.MaterialExpressionPower, self.single(unreal.MaterialExpressionAbs, self.normal()),
                        const_exponent=4.0)
        total = self.add(self.add(self.mask(w, "R"), self.mask(w, "G")), self.mask(w, "B"))
        wn = self.op(unreal.MaterialExpressionDivide, w, total)
        sx = self.tex(texture, self.mul(self.mask(self.wp(), "GB"), k=scale))
        sy = self.tex(texture, self.mul(self.mask(self.wp(), "RB"), k=scale))
        sz = self.tex(texture, self.mul(self.mask(self.wp(), "RG"), k=scale))
        return self.add(self.add(self.mul(sx, self.mask(wn, "R"), "RGB"), self.mul(sy, self.mask(wn, "G"), "RGB")),
                        self.mul(sz, self.mask(wn, "B"), "RGB"))

    def up(self):
        return self.mask(self.normal(), "B")

    def uv(self, channel=0):
        return self.node(unreal.MaterialExpressionTextureCoordinate, coordinate_index=channel)

    def fresnel(self, exponent=3.0):
        return self.node(unreal.MaterialExpressionFresnel, exponent=exponent, base_reflect_fraction=0.0)

    def detail(self, sample, luma_mean, strength, pin="RGB"):
        """Light/dark detail from a texture, centred on 1.0 (its colour is ignored)."""
        lum = self.node(unreal.MaterialExpressionDotProduct)
        self.link(sample, lum, pin, "A")
        self.link(self.node(unreal.MaterialExpressionConstant3Vector,
                            constant=unreal.LinearColor(0.299, 0.587, 0.114, 1.0)), lum, "", "B")
        rel = self.mul(lum, k=1.0 / max(luma_mean, 0.05))
        return self.lerp(self.const(1.0), rel, self.const(strength))

    def foliage_gradient(self):
        """0 underneath .. 1 sunlit top: the canopy-wide normal blended with height up the canopy (UV1.y)."""
        up = self.saturate(self.add(self.mul(self.up(), k=0.5), k=0.5))
        height = self.mask(self.uv(1), "G")
        return self.saturate(self.add(self.mul(up, k=0.6), self.mul(height, k=0.55)))

    def wind(self, weight, strength=1.0):
        """A slow travelling wave; `weight` scales it (0 at the root, 1 at the tip)."""
        wp = self.wp()
        phase = self.mul(self.add(self.mask(wp, "R"), self.mask(wp, "G")), k=0.0035)
        arg = self.add(phase, self.mul(self.node(unreal.MaterialExpressionTime), k=0.28))
        sine = self.single(unreal.MaterialExpressionSine, arg)
        cosine = self.single(unreal.MaterialExpressionCosine, self.mul(arg, k=1.37))
        dx = self.mul(self.mul(sine, k=9.0 * strength), weight)
        dy = self.mul(self.mul(cosine, k=5.0 * strength), weight)
        xy = self.node(unreal.MaterialExpressionAppendVector)
        self.link(dx, xy, "", "A")
        self.link(dy, xy, "", "B")
        xyz = self.node(unreal.MaterialExpressionAppendVector)
        self.link(xy, xyz, "", "A")
        self.link(self.const(0.0), xyz, "", "B")
        return xyz

    def out(self, expr, prop, pin=""):
        self.mel.connect_material_property(expr, pin, prop)

    def done(self):
        self.mel.recompile_material(self.mat)
        unreal.EditorAssetLibrary.save_loaded_asset(self.mat)
        return self.mat


def _splat_uv(g):
    return g.mul(g.add(g.mask(g.wp(), "RG"), k=SPLAT_EXTENT), k=1.0 / (2 * SPLAT_EXTENT))


def _material_terrain(tex, luma):
    """Meadow, sand, footpath and rock from one palette; textures add only light and dark detail."""
    g = _Graph("IslandTerrain")
    if g.exists:
        return g.mat
    P = ISLAND_PALETTE
    uv = g.world_uv(TILE)
    grass_detail = g.mul(g.detail(g.tex(tex["grass"], uv), luma["grass"], 0.55),
                         g.detail(g.tex(tex["grass"], g.world_uv(TILE * 0.27)), luma["grass"], 0.45))
    grass = g.mul(g.colour(P["grass"]), grass_detail)
    sand = g.mul(g.colour(P["sand"]), g.detail(g.tex(tex["sand"], uv), luma["sand"], 0.5))
    path = g.mul(g.colour(P["path"]), g.detail(g.tex(tex["path"], g.world_uv(TILE * 1.4)), luma["path"], 0.6))
    splat = g.tex(tex["splat"], _splat_uv(g), linear=True)
    steep = g.saturate(g.add(g.mul(g.up(), k=-5.5), k=4.4))  # 1 where steeper than ~37 degrees
    rock_w = g.op(unreal.MaterialExpressionMax, splat, steep, "G")
    rock = _rock_colour(g, tex, luma)
    base = g.lerp(grass, sand, splat, "", "", "R")
    base = g.lerp(base, path, splat, "", "", "B")
    base = g.lerp(base, rock, rock_w)
    tone = g.lerp(g.colour("FFF6E8"), g.colour("EEF3FF"), splat, alpha_out="A")
    g.out(g.mul(base, tone), unreal.MaterialProperty.MP_BASE_COLOR)
    g.out(g.const(0.94), unreal.MaterialProperty.MP_ROUGHNESS)
    return g.done()


def _rock_colour(g, tex, luma):
    """Muted warm stone: lighter facing up, lavender facing down, gentle triplanar detail."""
    P = ISLAND_PALETTE
    up = g.saturate(g.add(g.mul(g.up(), k=0.5), k=0.5))
    colour = g.lerp(g.colour(P["rock_shade"]), g.colour(P["rock_lit"]), up)
    tri = g.triplanar(tex["cliff"], TILE)
    return g.mul(colour, g.detail(tri, luma["cliff"], 0.3, pin=""))


def _material_rock(tex, luma):
    g = _Graph("IslandRock")
    if g.exists:
        return g.mat
    rock = _rock_colour(g, tex, luma)
    grass = g.mul(g.colour(ISLAND_PALETTE["grass"]), g.detail(g.tex(tex["grass"], g.world_uv(TILE)), luma["grass"], 0.5))
    grass_top = g.saturate(g.add(g.mul(g.up(), k=5.0), k=-3.7))  # only nearly flat tops
    g.out(g.lerp(rock, grass, grass_top), unreal.MaterialProperty.MP_BASE_COLOR)
    g.out(g.const(0.92), unreal.MaterialProperty.MP_ROUGHNESS)
    return g.done()


def _material_bark(tex, name="IslandBark", tint=None, texture="bark"):
    g = _Graph(name)
    if g.exists:
        return g.mat
    bark = g.triplanar(tex[texture], 1.0 / 140.0)
    if tint:
        bark = g.mul(bark, g.colour(tint))
    g.out(bark, unreal.MaterialProperty.MP_BASE_COLOR)
    g.out(g.const(0.9), unreal.MaterialProperty.MP_ROUGHNESS)
    return g.done()


def _material_shell(species, texture, luma_mean):
    """Opaque canopy shells: soft top-lit gradient in the species colours, darker toward the
    inside (UV1.x depth), gentle per-shell variation (UV2.x), a fake rim light and self-light."""
    g = _Graph(f"Shell_{species}")
    if g.exists:
        return g.mat
    shadow_hex, sun_hex = FOLIAGE_COLOURS[species]
    colour = g.lerp(g.colour(shadow_hex), g.colour(sun_hex), g.foliage_gradient())
    detail = g.detail(g.tex(texture, g.world_uv(1.0 / 150.0)), luma_mean, 0.35)
    depth = g.lerp(g.const(0.6), g.const(1.0), g.mask(g.uv(1), "R"))
    vary = g.add(g.mul(g.mask(g.uv(2), "R"), k=0.12), k=0.94)
    base = g.mul(g.mul(g.mul(colour, detail), depth), vary)
    g.out(base, unreal.MaterialProperty.MP_BASE_COLOR)
    rim = g.mul(g.mul(g.fresnel(3.0), g.colour(sun_hex)), k=0.22)
    g.out(g.add(g.mul(base, k=0.18), rim), unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    g.out(g.const(0.85), unreal.MaterialProperty.MP_ROUGHNESS)
    g.out(g.wind(g.mul(g.mask(g.uv(1), "G"), k=0.6), 0.45), unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    return g.done()


def _material_cards(species, atlas, luma_mean):
    """Leaf-clump fringe cards in exactly the shell's colours (the atlas only gives the leaf
    shapes and a little light/dark detail), so they melt into the round canopy."""
    g = _Graph(f"Cards_{species}")
    if g.exists:
        return g.mat
    g.mat.set_editor_property("two_sided", True)
    g.mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
    g.mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE)
    shadow_hex, sun_hex = FOLIAGE_COLOURS[species]
    sample = g.tex(atlas, g.uv(0))
    colour = g.lerp(g.colour(shadow_hex), g.colour(sun_hex), g.foliage_gradient())
    vary = g.add(g.mul(g.mask(g.uv(2), "R"), k=0.12), k=0.94)
    base = g.mul(g.mul(colour, g.detail(sample, luma_mean, 0.35)), vary)
    g.out(base, unreal.MaterialProperty.MP_BASE_COLOR)
    g.out(sample, unreal.MaterialProperty.MP_OPACITY_MASK, "A")
    g.out(g.mul(g.colour(sun_hex), k=0.25), unreal.MaterialProperty.MP_SUBSURFACE_COLOR)
    rim = g.mul(g.mul(g.fresnel(3.0), g.colour(sun_hex)), k=0.22)
    g.out(g.add(g.mul(base, k=0.18), rim), unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    g.out(g.const(0.85), unreal.MaterialProperty.MP_ROUGHNESS)
    g.out(g.wind(g.mul(g.mask(g.uv(1), "G"), k=0.6), 0.45), unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    return g.done()


def _material_plain(name, hex_str, glow=0.1):
    g = _Graph(name)
    if g.exists:
        return g.mat
    colour = g.colour(hex_str)
    g.out(colour, unreal.MaterialProperty.MP_BASE_COLOR)
    g.out(g.mul(colour, k=glow), unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    g.out(g.const(0.6), unreal.MaterialProperty.MP_ROUGHNESS)
    return g.done()


def _material_mushroom():
    g = _Graph("IslandMushroom")
    if g.exists:
        return g.mat
    cap = g.saturate(g.add(g.mul(g.up(), k=2.0), k=-0.4))  # warm cap on top, cream gills and stem below
    colour = g.lerp(g.colour("F4E8D2"), g.colour("D2714E"), cap)
    g.out(colour, unreal.MaterialProperty.MP_BASE_COLOR)
    g.out(g.mul(colour, k=0.12), unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    g.out(g.const(0.7), unreal.MaterialProperty.MP_ROUGHNESS)
    return g.done()


def _material_cutout(name, atlas, sway=0.6):
    """Upright plant and flower cards: cut out of an atlas, two-sided, swaying from the base."""
    g = _Graph(name)
    if g.exists:
        return g.mat
    g.mat.set_editor_property("two_sided", True)
    g.mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
    g.mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE)
    uv = g.uv(0)
    sample = g.tex(atlas, uv)
    g.out(sample, unreal.MaterialProperty.MP_BASE_COLOR, "RGB")
    g.out(sample, unreal.MaterialProperty.MP_OPACITY_MASK, "A")
    g.out(g.mul(sample, None, "RGB", k=0.25), unreal.MaterialProperty.MP_SUBSURFACE_COLOR)
    g.out(g.mul(sample, None, "RGB", k=0.25), unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    # Atlas cells are half the texture tall: 1 - frac(v * 2) is 0 at a plant's base, 1 at its top.
    in_cell = g.single(unreal.MaterialExpressionFrac, g.mul(g.mask(uv, "G"), k=2.0))
    top = g.add(g.mul(in_cell, k=-1.0), k=1.0)
    g.out(g.wind(g.mul(top, top), sway), unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    return g.done()


def _material_grass(tex, luma):
    """Blades in the meadow's own colour (slightly darker root, lighter tip), sharing the ground's
    large colour patches, lit through like leaves so back faces never go dark."""
    g = _Graph("IslandGrass")
    if g.exists:
        return g.mat
    g.mat.set_editor_property("two_sided", True)
    g.mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE)
    v = g.mask(g.uv(0), "G")  # 0 at the root, 1 at the tip
    ground = g.mul(g.colour(ISLAND_PALETTE["grass"]),
                   g.detail(g.tex(tex["grass"], g.world_uv(TILE * 0.27)), luma["grass"], 0.45))
    colour = g.mul(ground, g.lerp(g.const(0.8), g.const(1.15), v))
    g.out(colour, unreal.MaterialProperty.MP_BASE_COLOR)
    g.out(g.mul(colour, k=0.2), unreal.MaterialProperty.MP_SUBSURFACE_COLOR)
    g.out(g.mul(colour, k=0.15), unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    g.out(g.const(0.85), unreal.MaterialProperty.MP_ROUGHNESS)
    g.out(g.wind(g.mul(v, v)), unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    return g.done()


class _Builder:
    def __init__(self):
        self.eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        self.mats = {}
        self.meshes = {
            "cube": unreal.load_asset("/Engine/BasicShapes/Cube"),
            "cylinder": unreal.load_asset("/Engine/BasicShapes/Cylinder"),
            "sphere": unreal.load_asset("/Engine/BasicShapes/Sphere"),
            "cone": unreal.load_asset("/Engine/BasicShapes/Cone"),
            "plane": unreal.load_asset("/Engine/BasicShapes/Plane"),
        }

    def mat(self, name):
        if name not in self.mats:
            if name == "Sea":
                self.mats[name] = _make_sea_material()
            elif name == "LampGlass":
                self.mats[name] = _make_material(name, MOONGLASS, 0.2, 0.0, emissive=25.0)
            elif name == "LighthouseGlow":
                self.mats[name] = _make_material(name, "FFE7A0", 0.2, 0.0, emissive=15.0)
            else:
                hex_str, rough, metal = PALETTE[name]
                self.mats[name] = _make_material(name, hex_str, rough, metal)
        return self.mats[name]

    def shape(self, label, kind, loc, scale, material=None, rot=(0, 0, 0), folder="Harbor",
              collide=True, visible=True):
        actor = self.eas.spawn_actor_from_object(
            self.meshes[kind], unreal.Vector(*loc), unreal.Rotator(roll=rot[0], pitch=rot[1], yaw=rot[2]))
        actor.set_actor_scale3d(unreal.Vector(*scale))
        actor.set_actor_label(label)
        actor.set_folder_path(folder)
        comp = actor.get_component_by_class(unreal.StaticMeshComponent)
        if material:
            comp.set_material(0, self.mat(material))
        if not collide:
            comp.set_collision_profile_name("NoCollision")
            comp.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        if not visible:
            comp.set_visibility(False)
            comp.set_editor_property("cast_shadow", False)
            actor.set_actor_hidden_in_game(True)
        return actor

    def spawn(self, cls, label, loc=(0, 0, 0), rot=(0, 0, 0), folder="Lighting"):
        actor = self.eas.spawn_actor_from_class(
            cls, unreal.Vector(*loc), unreal.Rotator(roll=rot[0], pitch=rot[1], yaw=rot[2]))
        actor.set_actor_label(label)
        actor.set_folder_path(folder)
        return actor

    def point_light(self, label, loc, hex_str, intensity, radius, folder):
        light = self.spawn(unreal.PointLight, label, loc, folder=folder)
        comp = light.get_component_by_class(unreal.PointLightComponent)
        comp.set_editor_property("light_color", _srgb_color(hex_str))
        comp.set_editor_property("intensity", intensity)
        comp.set_editor_property("attenuation_radius", radius)
        return light


_META = None


def _island_meta():
    global _META
    if _META is None:
        path = os.path.join(unreal.Paths.project_dir(), ISLAND_DIR, ISLAND_META)
        with open(path) as f:
            _META = json.load(f)
    return _META


def ground_height(x, y):
    """Top of the island at (x, y) in cm (bilinear on the grid make_island.py saved)."""
    meta = _island_meta()
    o, step, n = meta["grid_origin"], meta["grid_step"], meta["grid_size"]
    hs = meta["heights"]
    fx, fy = (x - o) / step, (y - o) / step
    i, j = int(math.floor(fx)), int(math.floor(fy))
    if not (0 <= i < n - 1 and 0 <= j < n - 1):
        return -1000.0
    tx, ty = fx - i, fy - j

    def at(a, b):
        return hs[a * n + b]

    return ((at(i, j) * (1 - tx) + at(i + 1, j) * tx) * (1 - ty)
            + (at(i, j + 1) * (1 - tx) + at(i + 1, j + 1) * tx) * ty)


def _import(filename, destination):
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", filename)
    task.set_editor_property("destination_path", destination)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])


def _assets_of(folder, cls):
    found = []
    for asset_path in unreal.EditorAssetLibrary.list_assets(folder, recursive=True):
        asset = unreal.load_asset(asset_path)
        if isinstance(asset, cls):
            found.append(asset)
    return found


def _import_island():
    """Imports the painted textures, the island and the meadow; returns (island mesh, meadow mesh)."""
    root = os.path.join(unreal.Paths.project_dir(), ISLAND_DIR)
    tex_dir = os.path.join(root, "textures")
    for png in sorted(os.listdir(tex_dir)):
        if png.endswith(".png"):
            _import(os.path.join(tex_dir, png), TEXTURE_ASSET_DIR)
    tex = {t.get_name(): t for t in _assets_of(TEXTURE_ASSET_DIR, unreal.Texture2D)}
    needed = ("grass", "sand", "cliff", "path", "bark", "birch_bark", "needles", "leaf", "blossom", "flowers",
              "leaf_atlas", "plants", "splat")
    missing = [n for n in needed if n not in tex]
    if missing:
        raise RuntimeError(f"textures missing after import: {missing}")
    # The splat map is data, not colour: keep it linear, uncompressed and clamped at the edges.
    splat = tex["splat"]
    splat.set_editor_property("srgb", False)
    splat.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
    splat.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
    splat.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
    unreal.EditorAssetLibrary.save_loaded_asset(splat)

    _import(os.path.join(root, ISLAND_GLB), ISLAND_ASSET_DIR)
    _import(os.path.join(root, GRASS_GLB), GRASS_ASSET_DIR)
    _import(os.path.join(root, FOLIAGE_GLB), FOLIAGE_ASSET_DIR)
    island = next(iter(_assets_of(ISLAND_ASSET_DIR, unreal.StaticMesh)), None)
    meadow = next(iter(_assets_of(GRASS_ASSET_DIR, unreal.StaticMesh)), None)
    foliage = next(iter(_assets_of(FOLIAGE_ASSET_DIR, unreal.StaticMesh)), None)
    if island is None:
        raise RuntimeError("island mesh missing after import")

    atlas = tex["leaf_atlas"]
    luma = _island_meta().get("texture_luma", {})
    luma = {name: luma.get(name, 0.6) for name in tex}
    materials = {
        "terrain": _material_terrain(tex, luma),
        "rock": _material_rock(tex, luma),
        "bark": _material_bark(tex),
        "birch_bark": _material_bark(tex, "IslandBirchBark", texture="birch_bark"),
        "pine_bark": _material_bark(tex, "IslandPineBark", tint="B89A92"),
        "wood": _material_bark(tex, "IslandBenchWood", tint="FFE6CC"),
        "berry": _material_plain("IslandBerry", "B04A6E", 0.2),
        "mushroom": _material_mushroom(),
        "grass": _material_grass(tex, luma),
        "flower": _material_cutout("IslandFlowers", tex["flowers"], 0.6),
        "plant": _material_cutout("IslandPlants", tex["plants"], 0.8),
    }
    shell_textures = {"Oak": "leaf", "Bush": "leaf", "Birch": "leaf", "Pine": "needles", "Blossom": "blossom"}
    for species, tex_name in shell_textures.items():
        materials[f"shell_{species.lower()}"] = _material_shell(species, tex[tex_name], luma[tex_name])
        materials[f"cards_{species.lower()}"] = _material_cards(species, atlas, luma["leaf_atlas"])
    for mesh in filter(None, (island, meadow, foliage)):
        for index, slot in enumerate(mesh.get_editor_property("static_materials")):
            names = [str(slot.get_editor_property("material_slot_name"))]
            current = slot.get_editor_property("material_interface")
            if current:
                names.append(current.get_name())
            matches = [k for k in materials for n in names if n.lower().endswith(k)]
            key = max(matches, key=len) if matches else None  # "birch_bark" beats "bark"
            if key is None:
                unreal.log_warning(f"[Lyris] no material for slot {names[0]} on {mesh.get_name()}")
                continue
            mesh.set_material(index, materials[key])
            _log(f"{mesh.get_name()} slot {names[0]} -> {key}")
        unreal.EditorAssetLibrary.save_loaded_asset(mesh)

    # Walk on the real shape of the island: use the visible triangles as collision.
    body = island.get_editor_property("body_setup")
    if body:
        body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    unreal.EditorAssetLibrary.save_loaded_asset(island)
    return island, meadow, foliage


def _island_transform(mesh):
    """Works out how the importer oriented the model by comparing its bounds with the
    bounds make_island.py recorded, and returns (scale, yaw, z_offset) to undo it."""
    meta = _island_meta()
    eo, ee = meta["bounds_origin"], meta["bounds_extent"]
    bounds = mesh.get_bounds()
    io_, ie = bounds.origin, bounds.box_extent
    k = ee[2] / ie.z if ie.z > 1 else 1.0
    best = None
    for swap in (False, True):
        for sx in (1, -1):
            for sy in (1, -1):
                if swap:
                    px, py, ex, ey = sx * io_.y * k, sy * io_.x * k, ie.y * k, ie.x * k
                    scale, yaw = (sy * k, -sx * k, k), 90.0
                else:
                    px, py, ex, ey = sx * io_.x * k, sy * io_.y * k, ie.x * k, ie.y * k
                    scale, yaw = (sx * k, sy * k, k), 0.0
                err = abs(px - eo[0]) + abs(py - eo[1]) + abs(ex - ee[0]) + abs(ey - ee[1])
                if best is None or err < best[0]:
                    best = (err, scale, yaw)
    err, scale, yaw = best
    z_offset = eo[2] - io_.z * k
    _log(f"island orientation: scale {scale}, yaw {yaw}, z offset {z_offset:.0f}, fit error {err:.0f} cm")
    if err > 200:
        unreal.log_warning("[Lyris] island orientation is uncertain; check that the dock meets the shore")
    return scale, yaw, z_offset


def _step(name, fn):
    try:
        fn()
        _log(f"built {name}")
    except Exception as exc:  # keep going so one failure doesn't stop the rest
        unreal.log_warning(f"[Lyris] could not build {name}: {exc}")


def _current_version(eas):
    for actor in eas.get_all_level_actors():
        label = actor.get_actor_label()
        if label.startswith(MARKER_PREFIX):
            try:
                return int(label[len(MARKER_PREFIX):])
            except ValueError:
                return 0
    return 0


def build(force=False):
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

    if unreal.EditorAssetLibrary.does_asset_exist(MAP_PATH):
        les.load_level(MAP_PATH)
        version = _current_version(eas)
        if version >= BUILD_VERSION and not force:
            _log(f"Harbor map is up to date (v{version})")
            return
        _log(f"rebuilding Harbor map (v{version} -> v{BUILD_VERSION})")
        doomed = [a for a in eas.get_all_level_actors()
                  if not isinstance(a, (unreal.WorldSettings, unreal.Brush))]
        eas.destroy_actors(doomed)
    elif not les.new_level(MAP_PATH):
        unreal.log_error("[Lyris] could not create " + MAP_PATH)
        return

    # Start the dock at the island's real shoreline, and keep the boat and lamp with it.
    global DOCK_X0, DOCK_X1, BOAT_START, LAMP_POS
    global LIGHTHOUSE_POS
    LIGHTHOUSE_POS = tuple(_island_meta().get("lighthouse", LIGHTHOUSE_POS))
    DOCK_X0 = float(_island_meta().get("dock_shore_x", 1700.0)) - 250.0
    DOCK_X1 = DOCK_X0 + 1700.0
    BOAT_START = (DOCK_X1 - 400.0, -230.0)
    LAMP_POS = (DOCK_X1 - 90.0, 290.0)

    b = _Builder()

    def sky():
        sun = b.spawn(unreal.DirectionalLight, "Sun", (0, 0, 1000), rot=(0, -28, 215))  # warm late afternoon
        sc = sun.get_component_by_class(unreal.DirectionalLightComponent)
        sc.set_editor_property("intensity", 5.0)
        sc.set_editor_property("light_color", _srgb_color("FFE3BE"))
        sc.set_editor_property("atmosphere_sun_light", True)
        b.spawn(unreal.SkyAtmosphere, "SkyAtmosphere")
        skylight = b.spawn(unreal.SkyLight, "SkyLight", (0, 0, 800))
        slc = skylight.get_component_by_class(unreal.SkyLightComponent)
        slc.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
        slc.set_editor_property("real_time_capture", True)
        slc.set_editor_property("intensity", 1.4)  # soft fill so shadows stay readable
        fog = b.spawn(unreal.ExponentialHeightFog, "SeaMist", (0, 0, 0))
        fc = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
        fc.set_editor_property("fog_density", 0.01)
        fc.set_editor_property("fog_inscattering_luminance", _linear("D8E4EC"))
        b.spawn(unreal.VolumetricCloud, "Clouds")
        ppv = b.spawn(unreal.PostProcessVolume, "StorybookGrade")
        ppv.set_editor_property("unbound", True)
        settings = ppv.get_editor_property("settings")
        settings.set_editor_property("override_auto_exposure_bias", True)
        settings.set_editor_property("auto_exposure_bias", 0.3)
        settings.set_editor_property("override_color_saturation", True)
        settings.set_editor_property("color_saturation", unreal.Vector4(1.0, 1.02, 0.98, 1.04))  # gentle, not punchy
        # Shadows lean blue-violet, highlights stay warm (house style; Genshin tints shadows too).
        settings.set_editor_property("override_color_gain_shadows", True)
        settings.set_editor_property("color_gain_shadows", unreal.Vector4(0.92, 0.94, 1.08, 1.0))
        settings.set_editor_property("override_color_gain_highlights", True)
        settings.set_editor_property("color_gain_highlights", unreal.Vector4(1.04, 1.01, 0.96, 1.0))
        ppv.set_editor_property("settings", settings)

    def sea():
        # One big plane: 100 units x 4000 = 4 km across; the mist hides the edge.
        b.shape("Sea", "plane", (0, 0, 0), (4000, 4000, 1), "Sea", folder="Sea", collide=False)
        # Pale shallows ring around the island, a hair above the sea to avoid flicker.
        b.shape("Shallows", "cylinder", (0, 0, 0.5), (62, 62, 0.01), "Shallows", folder="Sea", collide=False)

    def island():
        island_mesh, meadow_mesh, foliage_mesh = _import_island()
        scale, yaw, z_offset = _island_transform(island_mesh)
        rot = unreal.Rotator(roll=0, pitch=0, yaw=yaw)
        actor = b.eas.spawn_actor_from_object(island_mesh, unreal.Vector(0, 0, z_offset), rot)
        actor.set_actor_scale3d(unreal.Vector(*scale))
        actor.set_actor_label("TestIsland")
        actor.set_folder_path("Island")
        # All three files share the same conventions, so the island's transform lines them up.
        for mesh, label, shadows in ((meadow_mesh, "TestIslandMeadow", False), (foliage_mesh, "TestIslandFoliage", True)):
            if not mesh:
                continue
            extra = b.eas.spawn_actor_from_object(mesh, unreal.Vector(0, 0, z_offset), rot)
            extra.set_actor_scale3d(unreal.Vector(*scale))
            extra.set_actor_label(label)
            extra.set_folder_path("Island")
            comp = extra.get_component_by_class(unreal.StaticMeshComponent)
            comp.set_collision_profile_name("NoCollision")
            comp.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
            comp.set_editor_property("cast_shadow", shadows)

    def lighthouse():
        x, y = LIGHTHOUSE_POS
        g = max(ground_height(x, y), 0.0) - 20
        b.shape("Lighthouse_Base", "cylinder", (x, y, g + 60), (3.4, 3.4, 1.2), "Stone", folder="Lighthouse")
        b.shape("Lighthouse_Tower", "cylinder", (x, y, g + 720), (2.6, 2.6, 12), "Salt", folder="Lighthouse")
        for i, z in enumerate((g + 450, g + 900)):
            b.shape(f"Lighthouse_Band_{i}", "cylinder", (x, y, z), (2.7, 2.7, 1.5), "RedBand",
                    folder="Lighthouse", collide=False)
        top = g + 1320
        b.shape("Lighthouse_Gallery", "cylinder", (x, y, top), (3.3, 3.3, 0.2), "Clay", folder="Lighthouse")
        b.shape("Lighthouse_Lamp", "cylinder", (x, y, top + 90), (1.8, 1.8, 1.6), "LighthouseGlow",
                folder="Lighthouse", collide=False)
        b.shape("Lighthouse_Roof", "cone", (x, y, top + 230), (2.4, 2.4, 1.3), "Clay", folder="Lighthouse")
        b.point_light("Lighthouse_Light", (x, y, top + 90), "FFE7A0", 40000.0, 6000.0, "Lighthouse")

    def dock():
        length = DOCK_X1 - DOCK_X0
        centre_x = (DOCK_X0 + DOCK_X1) / 2.0
        b.shape("Dock_Deck", "cube", (centre_x, DOCK_Y, DOCK_TOP - 12.5), (length / 100.0, 3.2, 0.25), "Wood",
                folder="Dock")
        x = DOCK_X0 + 150
        i = 0
        while x < DOCK_X1:
            for side, y in (("N", DOCK_Y - 150), ("S", DOCK_Y + 150)):
                b.shape(f"Dock_Post_{i}{side}", "cylinder", (x, y, -90), (0.35, 0.35, 3.2), "DarkWood",
                        folder="Dock")
            x += 300
            i += 1
        b.shape("Dock_Bollard", "cylinder", (DOCK_X1 - 300, DOCK_Y - 140, DOCK_TOP + 30), (0.3, 0.3, 0.6),
                "DarkWood", folder="Dock")

    def lamp():
        x, y = LAMP_POS
        b.shape("Lamp_Post", "cylinder", (x, y, DOCK_TOP + 160), (0.14, 0.14, 3.2), "DarkWood", folder="Dock/Lamp")
        b.shape("Lamp_Arm", "cube", (x, y - 30, DOCK_TOP + 320), (0.08, 0.7, 0.08), "DarkWood",
                folder="Dock/Lamp", collide=False)
        b.shape("Lamp_Glass", "cube", (x, y - 60, DOCK_TOP + 280), (0.28, 0.28, 0.45), "LampGlass",
                folder="Dock/Lamp", collide=False)
        b.shape("Lamp_Roof", "cone", (x, y - 60, DOCK_TOP + 320), (0.4, 0.4, 0.3), "Clay",
                folder="Dock/Lamp", collide=False)
        b.point_light("Lamp_Light", (x, y - 60, DOCK_TOP + 280), MOONGLASS, 8000.0, 1800.0, "Dock/Lamp")

    def boat():
        boat_cls = getattr(unreal, "LyrisBoat", None)
        if boat_cls is None:
            raise RuntimeError("LyrisBoat class not found; rebuild the C++ module and reopen the editor")
        actor = b.spawn(boat_cls, "Boat", (BOAT_START[0], BOAT_START[1], 25), rot=(0, 0, 0), folder="Boat")
        actor.set_editor_property("dock_point", unreal.Vector(BOAT_START[0], DOCK_Y, DOCK_TOP + 100))

    def player_start():
        b.spawn(unreal.PlayerStart, "PlayerStart", (DOCK_X0 + 250, DOCK_Y, DOCK_TOP + 100), rot=(0, 0, 0),
                folder="Gameplay")

    for name, fn in [("sky and lighting", sky), ("sea", sea), ("island", island),
                     ("lighthouse", lighthouse), ("dock", dock), ("dock lamp", lamp),
                     ("boat", boat), ("player start", player_start)]:
        _step(name, fn)

    marker = b.spawn(unreal.Note, f"{MARKER_PREFIX}{BUILD_VERSION}", (0, 0, 2000), folder="Gameplay")
    try:
        marker.set_editor_property("text", "Built by Content/Python/lyris_build_harbor.py. "
                                           "Edits here are lost on the next rebuild.")
    except Exception:
        pass

    les.save_current_level()
    unreal.EditorAssetLibrary.save_directory("/Game/Lyris", only_if_is_dirty=True, recursive=True)
    _log(f"Harbor map v{BUILD_VERSION} ready at {MAP_PATH}")
