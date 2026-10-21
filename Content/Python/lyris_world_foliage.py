"""World foliage (T51): the starter island's Genshin-style trees, bushes, grass and flowers over the whole
Lyris world, placed by the terrain. Environment lane.

    import lyris_world_foliage as f; f.build()     # incremental: only missing or outdated cells
    import lyris_world_foliage as f; f.clear()     # removes only this script's actors, in batches
    import lyris_world_foliage as f; f.report()    # what is built, what is left

lyris_build_world.build() runs build() as its "foliage" step (after the terrain look). It needs three
offline steps first (plain Python, see Art/World/README.md, section 5):

    python Art/World/bake_terrain.py --workers 2       # the terrain tiles (also needed for the landscape)
    python Art/World/foliage/make_species.py           # meshes (LOD0..3) and painted atlases, ~1 min
    python Art/World/foliage/scatter.py                # per-cell instance files, ~5 min

What build() makes
  /Game/Lyris/World/Foliage/Textures      the island's painted tiles, the world leaf and plant atlases,
                                          the grass tint map (scatter/grass_tint.png)
  /Game/Lyris/World/Foliage/Materials     island-style materials: canopy shells (top-lit gradient, dark
                                          inside, rim and self light, wind), two-sided masked leaf cards
                                          with Two Sided Foliage (light through leaves), bark, plants,
                                          grass, rock, crystal, glow moss
  /Game/Lyris/World/Foliage/Meshes        one StaticMesh per species variant with LOD0..3
  /Game/Lyris/World/Foliage/GT_Meadow, GT_Forest, GT_Dune    Landscape Grass Types (procedural near the
                                          camera; the terrain material's LandscapeGrassOutput feeds them)
  /Game/Lyris/World/Foliage/HLOD_LyrisTrees (+ _Far)         HLOD layers for the tree actors
  In the map: per 256 m World Partition cell, up to two spatially loaded actors, LWF_<sig>_T_<x>_<y>
  (trees and boulders, in the trees HLOD layer) and LWF_<sig>_U_<x>_<y> (understory, not in HLOD), each
  holding one HierarchicalInstancedStaticMeshComponent per mesh variant, tagged LyrisWorldFoliage.

Incremental and safe for an 8 GB machine: cells already built with the same signature are skipped (read
from World Partition actor descriptors, without loading them); cells are spawned CELLS_PER_BATCH at a
time inside a cancellable progress dialog, saved and unloaded after each batch. Cancel, or close the
editor, and the next build() continues where it stopped. Bump FOLIAGE_VERSION (or rerun scatter.py, which
changes the signature) to rebuild everything.
"""

import json
import math
import os
import struct

import unreal

FOLIAGE_VERSION = 1
ROOT = "/Game/Lyris/World/Foliage"
TEX_DIR = f"{ROOT}/Textures"
MAT_DIR = f"{ROOT}/Materials"
MESH_DIR = f"{ROOT}/Meshes"
IMPORT_DIR = f"{ROOT}/_Import"
GRASS_TYPES = {"meadow": f"{ROOT}/GT_Meadow", "forest": f"{ROOT}/GT_Forest", "dune": f"{ROOT}/GT_Dune"}
HLOD_TREES = f"{ROOT}/HLOD_LyrisTrees"
HLOD_TREES_FAR = f"{ROOT}/HLOD_LyrisTreesFar"
MAP_PATH = "/Game/Lyris/Maps/Lyris"

SRC_DIR = "Art/World/foliage"
TAG = "LyrisWorldFoliage"
LABEL_PREFIX = "LWF_"
FOLDER = "WorldFoliage"
CELL_CM = 25600.0
CELLS_PER_BATCH = 12          # cells spawned between saves (each up to two actors, ~15 components)
DELETE_BATCH = 100
LOAD_BATCH = 200
WORLD_MIN_CM, WORLD_SIZE_CM = -1250000.0, 2500000.0

# Per group: where WPO (wind) stops being evaluated (cm), shadows, collision.
WPO_DISABLE_CM = {"trees": 9000, "understory": 4500}
NO_SHADOW = {"fern", "mushrooms", "pebbles", "lavender", "reeds", "ventmoss"}

_SUB = None


def _log(msg):
    unreal.log(f"[Lyris] foliage: {msg}")


def _warn(msg):
    unreal.log_warning(f"[Lyris] foliage: {msg}")


def _project_path(rel):
    return os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()), rel)


def _linear(hex_str):
    c = [int(hex_str[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    c = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return unreal.LinearColor(c[0], c[1], c[2], 1.0)


def _set(obj, prop, value, quiet=False):
    try:
        obj.set_editor_property(prop, value)
        return True
    except Exception as exc:
        if not quiet:
            _warn(f"could not set {prop} on {obj.get_name()}: {exc}")
        return False


def _get(obj, prop):
    try:
        return obj.get_editor_property(prop)
    except Exception:
        return None


def _sub():
    global _SUB
    if _SUB is None:
        cls = getattr(unreal, "StaticMeshEditorSubsystem", None)
        _SUB = unreal.get_editor_subsystem(cls) if cls else unreal.EditorStaticMeshLibrary
    return _SUB


def _save_asset(asset):
    try:
        unreal.EditorAssetLibrary.save_loaded_asset(asset, False)
    except Exception as exc:
        _warn(f"could not save {asset.get_name()}: {exc}")


class _Cancelled(Exception):
    pass


# ----------------------------------------------------------------------------- inputs

def _read_json(rel):
    path = _project_path(rel)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _inputs():
    species = _read_json(f"{SRC_DIR}/species.json")
    summary = _read_json(f"{SRC_DIR}/scatter/summary.json")
    missing = []
    if species is None:
        missing.append("python Art/World/foliage/make_species.py")
    if summary is None:
        missing.append("python Art/World/foliage/scatter.py")
    if missing:
        raise RuntimeError("foliage data not generated yet; from the project folder run: " + "  then  ".join(missing)
                           + "  (after the terrain bake), then w.build() again")
    if summary.get("preview_bake"):
        _warn("the scatter was made from a PREVIEW terrain bake: trees may float or sink on the real landscape. "
              "Rerun scatter.py after the full bake (the next build() then rebuilds every cell)")
    return species, summary


def _signature(summary):
    """Short id of this scatter + script version, part of every actor label (so a rerun rebuilds cells)."""
    key = f"{FOLIAGE_VERSION}:{summary.get('scatter_version')}:{summary.get('seed')}:{summary.get('total')}:" \
          f"{summary.get('bake_version')}:{summary.get('preview_bake')}"
    h = 2166136261
    for ch in key.encode():
        h = ((h ^ ch) * 16777619) & 0xFFFFFFFF
    return f"v{FOLIAGE_VERSION}{h % 46656:03x}"


def _read_cell(path):
    """{variant name: list of (x, y, z, yaw, pitch, roll, scale)} from a scatter cell file."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"LYF1":
        raise RuntimeError(f"{path} is not a foliage cell file")
    n = struct.unpack_from("<I", data, 16)[0]
    off, out = 20, {}
    for _ in range(n):
        ln = struct.unpack_from("<H", data, off)[0]
        name = data[off + 2:off + 2 + ln].decode()
        cnt = struct.unpack_from("<I", data, off + 2 + ln)[0]
        off += 6 + ln
        vals = struct.unpack_from(f"<{cnt * 7}f", data, off)
        off += cnt * 28
        out[name] = [vals[i:i + 7] for i in range(0, len(vals), 7)]
    return out


# ----------------------------------------------------------------------------- material graphs

class _Graph:
    """Material graph helper (same pattern as the Harbor and world scripts)."""

    def __init__(self, name):
        self.name = f"M_Foliage_{name}_v{FOLIAGE_VERSION}"
        self.path = f"{MAT_DIR}/{self.name}"
        self.exists = unreal.EditorAssetLibrary.does_asset_exist(self.path)
        if self.exists:
            self.mat = unreal.load_asset(self.path)
        else:
            tools = unreal.AssetToolsHelpers.get_asset_tools()
            self.mat = tools.create_asset(self.name, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
        self.mel = unreal.MaterialEditingLibrary
        self.y = 0
        self._wp = self._nrm = None

    def node(self, cls, **props):
        expr = self.mel.create_material_expression(self.mat, cls, -1000, self.y)
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

    def sub(self, a, b, a_out="", b_out=""):
        return self.op(unreal.MaterialExpressionSubtract, a, b, a_out, b_out)

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

    def mask(self, src, channels, src_out=""):
        return self.single(unreal.MaterialExpressionComponentMask, src, src_out, r="R" in channels,
                           g="G" in channels, b="B" in channels, a="A" in channels)

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

    def up(self):
        return self.mask(self.normal(), "B")

    def uv(self, channel=0):
        return self.node(unreal.MaterialExpressionTextureCoordinate, coordinate_index=channel)

    def tex(self, texture, uv=None, linear=False):
        expr = self.node(unreal.MaterialExpressionTextureSample, texture=texture)
        if linear:
            expr.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        if uv is not None:
            self.link(uv, expr, "", "UVs")
        return expr

    def world_uv(self, scale):
        return self.mul(self.mask(self.wp(), "RG"), k=scale)

    def fresnel(self, exponent=3.0):
        return self.node(unreal.MaterialExpressionFresnel, exponent=exponent, base_reflect_fraction=0.0)

    def triplanar(self, texture, scale):
        w = self.single(unreal.MaterialExpressionPower, self.single(unreal.MaterialExpressionAbs, self.normal()),
                        const_exponent=4.0)
        total = self.add(self.add(self.mask(w, "R"), self.mask(w, "G")), self.mask(w, "B"))
        wn = self.op(unreal.MaterialExpressionDivide, w, total)
        sx = self.tex(texture, self.mul(self.mask(self.wp(), "GB"), k=scale))
        sy = self.tex(texture, self.mul(self.mask(self.wp(), "RB"), k=scale))
        sz = self.tex(texture, self.mul(self.mask(self.wp(), "RG"), k=scale))
        return self.add(self.add(self.mul(sx, self.mask(wn, "R"), "RGB"), self.mul(sy, self.mask(wn, "G"), "RGB")),
                        self.mul(sz, self.mask(wn, "B"), "RGB"))

    def detail(self, sample, luma_mean, strength, pin="RGB"):
        lum = self.node(unreal.MaterialExpressionDotProduct)
        self.link(sample, lum, pin, "A")
        self.link(self.node(unreal.MaterialExpressionConstant3Vector,
                            constant=unreal.LinearColor(0.299, 0.587, 0.114, 1.0)), lum, "", "B")
        rel = self.mul(lum, k=1.0 / max(luma_mean, 0.05))
        return self.lerp(self.const(1.0), rel, self.const(strength))

    def foliage_gradient(self):
        """0 underneath .. 1 sunlit top: canopy-wide normal blended with height up the canopy (UV1.y)."""
        up = self.saturate(self.add(self.mul(self.up(), k=0.5), k=0.5))
        height = self.mask(self.uv(1), "G")
        return self.saturate(self.add(self.mul(up, k=0.6), self.mul(height, k=0.55)))

    def wind(self, weight, strength=1.0):
        """A slow travelling wave (Harbor wind); `weight` is 0 at the root, 1 at the tip."""
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

    def world_map_uv(self):
        """UV of the whole-world maps (grass tint): (world XY + 12.5 km) / 25 km."""
        return self.mul(self.add(self.mask(self.wp(), "RG"), k=-WORLD_MIN_CM), k=1.0 / WORLD_SIZE_CM)

    def collapse(self, keep):
        """World offset that shrinks the instance to its pivot where `keep` is 0 (patches, dry/lush ground).
        Uses the vertex's local position, so it works per instance in landscape grass."""
        cls = getattr(unreal, "MaterialExpressionLocalPosition", None)
        tr = getattr(unreal, "MaterialExpressionTransform", None)
        if cls is None or tr is None:
            return None
        local = self.node(cls)
        world = self.node(tr)
        _set(world, "transform_source_type", unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_LOCAL, True)
        _set(world, "transform_type", unreal.MaterialVectorCoordTransform.TRANSFORM_WORLD, True)
        self.link(local, world)
        shrink = self.add(self.mul(self.saturate(keep), k=-1.0), k=1.0)
        return self.mul(self.mul(world, k=-1.0), shrink)

    def out(self, expr, prop, pin=""):
        self.mel.connect_material_property(expr, pin, prop)

    def foliage_shading(self, two_sided=True, masked=False):
        self.mat.set_editor_property("two_sided", two_sided)
        if masked:
            self.mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
        self.mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE)
        _set(self.mat, "used_with_instanced_static_meshes", True, quiet=True)

    def done(self):
        _set(self.mat, "used_with_instanced_static_meshes", True, quiet=True)
        self.mel.recompile_material(self.mat)
        _save_asset(self.mat)
        return self.mat


def _snow(g, base, palette, amount=1.0):
    """Snow on up-facing canopy tops (snow pines, frosted shrubs): cream with its cool shade below."""
    up = g.saturate(g.mul(g.add(g.up(), k=-0.55), k=3.0))
    top = g.saturate(g.mul(g.add(g.mask(g.uv(1), "G"), k=-0.4), k=2.0))
    snow_col = g.lerp(g.colour(palette["snow_shade"]), g.colour(palette["snow"]), top)
    return g.lerp(base, snow_col, g.mul(g.mul(up, top), k=amount))


def _material_shell(species, palette, tex, luma):
    g = _Graph(f"Shell_{species}")
    if g.exists:
        return g.mat
    lo, hi = palette["canopy"][species]
    colour = g.lerp(g.colour(lo), g.colour(hi), g.foliage_gradient())
    leaf_tex = {"pine": "needles", "snowpine": "needles", "cypress": "needles", "darkwood": "leaf",
                "blossom": "blossom", "cherry": "blossom"}.get(species, "leaf")
    detail = g.detail(g.tex(tex[leaf_tex], g.world_uv(1.0 / 150.0)), luma.get(leaf_tex, 0.6), 0.35)
    depth = g.lerp(g.const(0.6), g.const(1.0), g.mask(g.uv(1), "R"))
    vary = g.add(g.mul(g.mask(g.uv(2), "R"), k=0.12), k=0.94)
    base = g.mul(g.mul(g.mul(colour, detail), depth), vary)
    if species in ("snowpine", "frostshrub"):
        base = _snow(g, base, palette)
    g.out(base, unreal.MaterialProperty.MP_BASE_COLOR)
    rim = g.mul(g.mul(g.fresnel(3.0), g.colour(hi)), k=0.22)
    g.out(g.add(g.mul(base, k=0.18), rim), unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    g.out(g.const(0.85), unreal.MaterialProperty.MP_ROUGHNESS)
    g.out(g.wind(g.mul(g.mask(g.uv(1), "G"), k=0.6), 0.45), unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    return g.done()


def _material_cards(species, palette, atlas, luma):
    """Leaf-clump fringe cards in exactly the shell's colours (the atlas gives shape and light/dark only)."""
    g = _Graph(f"Cards_{species}")
    if g.exists:
        return g.mat
    g.foliage_shading(masked=True)
    lo, hi = palette["canopy"][species]
    sample = g.tex(atlas, g.uv(0))
    colour = g.lerp(g.colour(lo), g.colour(hi), g.foliage_gradient())
    vary = g.add(g.mul(g.mask(g.uv(2), "R"), k=0.12), k=0.94)
    base = g.mul(g.mul(colour, g.detail(sample, luma, 0.35)), vary)
    if species in ("snowpine", "frostshrub"):
        base = _snow(g, base, palette, 0.8)
    g.out(base, unreal.MaterialProperty.MP_BASE_COLOR)
    g.out(sample, unreal.MaterialProperty.MP_OPACITY_MASK, "A")
    g.out(g.mul(g.colour(hi), k=0.25), unreal.MaterialProperty.MP_SUBSURFACE_COLOR)
    rim = g.mul(g.mul(g.fresnel(3.0), g.colour(hi)), k=0.22)
    g.out(g.add(g.mul(base, k=0.18), rim), unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    g.out(g.const(0.85), unreal.MaterialProperty.MP_ROUGHNESS)
    g.out(g.wind(g.mul(g.mask(g.uv(1), "G"), k=0.6), 0.45), unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    return g.done()


def _material_bark(key, palette, tex):
    g = _Graph(f"Bark_{key}")
    if g.exists:
        return g.mat
    tex_name, tint = palette["bark"][key]
    bark = g.triplanar(tex[tex_name], 1.0 / 140.0)
    if tint:
        bark = g.mul(bark, g.colour(tint))
    if key == "char_bark":  # embers in the cracks glow faintly
        g.out(g.mul(bark, k=0.25), unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    g.out(bark, unreal.MaterialProperty.MP_BASE_COLOR)
    g.out(g.const(0.9), unreal.MaterialProperty.MP_ROUGHNESS)
    return g.done()


def _material_cutout(name, atlas, sway, top_from_uv1=True, glow=0.0, tint_map=None, keep=None):
    """Upright plant cards from an atlas: two-sided, masked, swaying from the base.
    keep: "dry" shows the instance only on dry ground (wheat), "lush" only in lush flower patches."""
    g = _Graph(name)
    if g.exists:
        return g.mat
    g.foliage_shading(masked=True)
    sample = g.tex(atlas, g.uv(0))
    g.out(sample, unreal.MaterialProperty.MP_BASE_COLOR, "RGB")
    g.out(sample, unreal.MaterialProperty.MP_OPACITY_MASK, "A")
    g.out(g.mul(sample, None, "RGB", k=0.25), unreal.MaterialProperty.MP_SUBSURFACE_COLOR)
    g.out(g.mul(sample, None, "RGB", k=0.25 + glow), unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    if top_from_uv1:
        top = g.mask(g.uv(1), "G")
    else:  # flowers.png is 2 x 2: 1 - frac(v * 2) is 0 at a flower's base, 1 at its top
        in_cell = g.single(unreal.MaterialExpressionFrac, g.mul(g.mask(g.uv(0), "G"), k=2.0))
        top = g.add(g.mul(in_cell, k=-1.0), k=1.0)
    wpo = g.wind(g.mul(top, top), sway)
    if keep and tint_map is not None:
        dry = g.mask(g.tex(tint_map, g.world_map_uv(), linear=True), "A")
        if keep == "dry":
            vis = g.saturate(g.mul(g.add(dry, k=-0.45), k=6.0))
        else:
            noise_cls = getattr(unreal, "MaterialExpressionNoise", None)
            lush = g.saturate(g.mul(g.add(dry, k=-0.4), k=-6.0))
            if noise_cls is not None:
                noise = g.node(noise_cls, scale=0.0004, levels=2, output_min=0.0, output_max=1.0)
                g.link(g.wp(), noise, "", "Position")
                patches = g.saturate(g.mul(g.add(noise, k=-0.55), k=5.0))
                vis = g.mul(lush, patches)
            else:
                vis = lush
        shrink = g.collapse(vis)
        if shrink is not None:
            wpo = g.add(wpo, shrink)
    g.out(wpo, unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    return g.done()


def _material_grass(palette, tex, luma, tint_map):
    """Island grass blades in the ground's own colour, tinted per biome by the grass tint map
    (wheat gold on Sunreach's plains, dusty in the badlands, frosted near snow)."""
    g = _Graph("Grass")
    if g.exists:
        return g.mat
    g.foliage_shading(masked=False)
    v = g.mask(g.uv(0), "G")
    ground = g.mul(g.colour(palette["plain"]["grass"]),
                   g.detail(g.tex(tex["grass"], g.world_uv(1.0 / 1480.0)), luma.get("grass", 0.6), 0.45))
    if tint_map is not None:
        tint = g.mul(g.mask(g.tex(tint_map, g.world_map_uv(), linear=True), "RGB"), k=2.0)
        ground = g.mul(ground, tint)
    colour = g.mul(ground, g.lerp(g.const(0.8), g.const(1.15), v))
    g.out(colour, unreal.MaterialProperty.MP_BASE_COLOR)
    g.out(g.mul(colour, k=0.2), unreal.MaterialProperty.MP_SUBSURFACE_COLOR)
    g.out(g.mul(colour, k=0.15), unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    g.out(g.const(0.85), unreal.MaterialProperty.MP_ROUGHNESS)
    g.out(g.wind(g.mul(v, v)), unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    return g.done()


def _material_rock(palette, tex, luma):
    """Warm stone lit from above, lavender below, grass on flat tops (vertex colour R from the generator)."""
    g = _Graph("Rock")
    if g.exists:
        return g.mat
    P = palette["plain"]
    up = g.saturate(g.add(g.mul(g.up(), k=0.5), k=0.5))
    rock = g.lerp(g.colour(P["rock_shade"]), g.colour(P["rock_lit"]), up)
    rock = g.mul(rock, g.detail(g.triplanar(tex["cliff"], 1.0 / 400.0), luma.get("cliff", 0.6), 0.3, pin=""))
    grass = g.mul(g.colour(P["grass"]), g.detail(g.tex(tex["grass"], g.world_uv(1.0 / 400.0)), luma.get("grass", 0.6), 0.5))
    vc = g.node(unreal.MaterialExpressionVertexColor)
    g.out(g.lerp(rock, grass, g.mask(vc, "R")), unreal.MaterialProperty.MP_BASE_COLOR)
    g.out(g.const(0.92), unreal.MaterialProperty.MP_ROUGHNESS)
    return g.done()


def _material_plain(name, hex_str, roughness=0.6, glow=0.1, rim=0.0, rim_hex=None):
    g = _Graph(name)
    if g.exists:
        return g.mat
    colour = g.colour(hex_str)
    g.out(colour, unreal.MaterialProperty.MP_BASE_COLOR)
    emissive = g.mul(colour, k=glow)
    if rim:
        emissive = g.add(emissive, g.mul(g.mul(g.fresnel(2.5), g.colour(rim_hex or hex_str)), k=rim))
    g.out(emissive, unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    g.out(g.const(roughness), unreal.MaterialProperty.MP_ROUGHNESS)
    return g.done()


def _material_mushroom(palette):
    g = _Graph("Mushroom")
    if g.exists:
        return g.mat
    P = palette["plain"]
    cap = g.saturate(g.add(g.mul(g.up(), k=2.0), k=-0.4))
    colour = g.lerp(g.colour(P["mushroom_stem"]), g.colour(P["mushroom_cap"]), cap)
    g.out(colour, unreal.MaterialProperty.MP_BASE_COLOR)
    g.out(g.mul(colour, k=0.12), unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    g.out(g.const(0.7), unreal.MaterialProperty.MP_ROUGHNESS)
    return g.done()


# ----------------------------------------------------------------------------- assets

def _import_file(filename, destination):
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", filename)
    task.set_editor_property("destination_path", destination)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])


def _assets_of(folder, cls):
    found = []
    for path in unreal.EditorAssetLibrary.list_assets(folder, recursive=True):
        asset = unreal.load_asset(path)
        if isinstance(asset, cls):
            found.append(asset)
    return found


def _textures(species_json):
    src = _project_path(f"{SRC_DIR}/textures")
    names = sorted(f[:-4] for f in os.listdir(src) if f.endswith(".png"))
    for n in names:
        if not unreal.EditorAssetLibrary.does_asset_exist(f"{TEX_DIR}/{n}"):
            _import_file(os.path.join(src, n + ".png"), TEX_DIR)
    tex = {n: unreal.load_asset(f"{TEX_DIR}/{n}") for n in names}
    tint_png = _project_path(f"{SRC_DIR}/scatter/grass_tint.png")
    tint = None
    if os.path.exists(tint_png):
        name = f"T_LyrisGrassTint_v{FOLIAGE_VERSION}"
        path = f"{TEX_DIR}/{name}"
        if not unreal.EditorAssetLibrary.does_asset_exist(path):
            tmp = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()),
                               "LyrisFoliage")
            os.makedirs(tmp, exist_ok=True)
            dst = os.path.join(tmp, name + ".png")
            with open(tint_png, "rb") as fi, open(dst, "wb") as fo:
                fo.write(fi.read())
            _import_file(dst, TEX_DIR)
        tint = unreal.load_asset(path)
        if tint:  # data, not colour: linear, clamped at the world's edge
            _set(tint, "srgb", False, True)
            _set(tint, "address_x", unreal.TextureAddress.TA_CLAMP, True)
            _set(tint, "address_y", unreal.TextureAddress.TA_CLAMP, True)
            _save_asset(tint)
    else:
        _warn("scatter/grass_tint.png missing: grass keeps its meadow green everywhere")
    missing = [n for n, t in tex.items() if t is None]
    if missing:
        raise RuntimeError(f"foliage textures missing after import: {missing}")
    return tex, tint


def _materials(species_json, tex, tint):
    pal = species_json["palette"]
    luma = species_json.get("texture_luma", {})
    mats = {}
    leaves, plants, flowers = tex["world_leaves"], tex["world_plants"], tex["flowers"]
    for sp in pal["canopy"]:
        mats[f"shell_{sp}"] = _material_shell(sp, pal, tex, luma)
        mats[f"cards_{sp}"] = _material_cards(sp, pal, leaves, luma.get("world_leaves", 0.6))
    for key in pal["bark"]:
        mats[key] = _material_bark(key, pal, tex)
    mats["plant"] = _material_cutout("Plants", plants, 0.7)
    mats["moss"] = _material_cutout("GlowMoss", plants, 0.3, glow=1.4)
    mats["wheat"] = _material_cutout("Wheat", plants, 0.9, tint_map=tint, keep="dry")
    mats["flower"] = _material_cutout("Flowers", flowers, 0.6, top_from_uv1=False, tint_map=tint, keep="lush")
    mats["grass"] = _material_grass(pal, tex, luma, tint)
    mats["rock"] = _material_rock(pal, tex, luma)
    P = pal["plain"]
    mats["vent_rock"] = _material_plain("VentRock", P["vent_rock"], 0.9, 0.05)
    mats["crystal"] = _material_plain("Crystal", P["crystal"], 0.25, 0.15, rim=0.6, rim_hex=P["crystal_shade"])
    mats["berry"] = _material_plain("Berry", P["berry"], 0.6, 0.2)
    mats["mushroom"] = _material_mushroom(pal)
    return mats


def _mesh_material_key(slot_name, mats):
    """'M_Island_shell_oak' -> 'shell_oak'; the longest key that ends the slot name wins."""
    n = slot_name.lower()
    matches = [k for k in mats if n.endswith(k)]
    return max(matches, key=len) if matches else None


def _import_variant(variant, spec, mats):
    """Imports LOD0..n of one variant into Meshes/<name> with our materials, LODs, Nanite and collision."""
    name = variant["name"]
    final = f"{MESH_DIR}/{name}"
    if unreal.EditorAssetLibrary.does_asset_exist(final):
        return unreal.load_asset(final)
    src = _project_path(f"{SRC_DIR}/meshes")
    lods = []
    for k, fname in enumerate(variant["lods"]):
        folder = f"{IMPORT_DIR}/{name}_LOD{k}"
        _import_file(os.path.join(src, fname), folder)
        found = _assets_of(folder, unreal.StaticMesh)
        if not found:
            raise RuntimeError(f"{fname}: no static mesh after import")
        lods.append(found[0])
    base = lods[0]
    if not unreal.EditorAssetLibrary.rename_loaded_asset(base, final):
        raise RuntimeError(f"could not move {base.get_name()} to {final}")
    mesh = unreal.load_asset(final)
    sub = _sub()
    if spec.get("nanite"):
        lods = lods[:1]  # Nanite builds its own detail levels
    for k, lod_mesh in enumerate(lods[1:], start=1):
        ok = False
        if hasattr(sub, "set_lod_from_static_mesh"):
            try:
                ok = sub.set_lod_from_static_mesh(mesh, k, lod_mesh, 0, True) >= 0
            except Exception as exc:
                _warn(f"{name} LOD{k}: {exc}")
        if not ok:
            _warn(f"{name}: could not attach LOD{k}; using automatic LODs instead")
            _auto_lods(mesh, sub)
            break
    for index, slot in enumerate(mesh.get_editor_property("static_materials")):
        names = [str(slot.get_editor_property("material_slot_name"))]
        cur = slot.get_editor_property("material_interface")
        if cur:
            names.append(cur.get_name())
        key = next(filter(None, (_mesh_material_key(n, mats) for n in names)), None)
        if key is None:
            _warn(f"{name}: no material for slot {names[0]}")
            continue
        mesh.set_material(index, mats[key])
    ns = _get(mesh, "nanite_settings")
    if ns is not None:
        _set(ns, "enabled", bool(spec.get("nanite")), True)
        _set(mesh, "nanite_settings", ns, True)
    _collision(mesh, spec, sub)
    _save_asset(mesh)
    return mesh


def _auto_lods(mesh, sub):
    try:
        opts = unreal.EditorScriptingMeshReductionOptions()
        settings = []
        for pct, screen in ((1.0, 1.0), (0.4, 0.25), (0.18, 0.08), (0.05, 0.025)):
            s = unreal.EditorScriptingMeshReductionSettings()
            s.set_editor_property("percent_triangles", pct)
            s.set_editor_property("screen_size", screen)
            settings.append(s)
        opts.set_editor_property("reduction_settings", settings)
        sub.set_lods(mesh, opts)
    except Exception as exc:
        _warn(f"automatic LODs failed on {mesh.get_name()}: {exc}")


def _collision(mesh, spec, sub):
    body = _get(mesh, "body_setup")
    mode = spec.get("collision")
    if body is None:
        return
    if mode is None:
        _set(body, "collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX, True)
        return
    _set(body, "collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE, True)
    if mode != "trunk" or not hasattr(sub, "enable_section_collision"):
        return
    # Only the bark sections block: you bump into trunks, not into leaves.
    try:
        slots = [str(s.get_editor_property("material_slot_name")).lower() for s in mesh.get_editor_property("static_materials")]
        n_sections = mesh.get_num_sections(0)
        for section in range(n_sections):
            slot = sub.get_lod_material_slot(mesh, 0, section) if hasattr(sub, "get_lod_material_slot") else section
            bark = 0 <= slot < len(slots) and slots[slot].endswith("bark")
            sub.enable_section_collision(mesh, bark, 0, section)
    except Exception as exc:
        _warn(f"{mesh.get_name()}: trunk-only collision not set ({exc}); the whole tree blocks")


def _meshes(species_json, mats):
    out = {}
    variants = [(v, spec) for spec in species_json["species"].values() for v in spec["variants"]]
    with unreal.ScopedSlowTask(len(variants), "Lyris: importing foliage meshes") as task:
        task.make_dialog(True)
        for k, (v, spec) in enumerate(variants):
            if task.should_cancel():
                raise _Cancelled("cancelled while importing meshes")
            task.enter_progress_frame(1, f"foliage mesh {v['name']} ({k + 1}/{len(variants)})")
            out[v["name"]] = _import_variant(v, spec, mats)
    if unreal.EditorAssetLibrary.does_directory_exist(IMPORT_DIR):
        try:
            unreal.EditorAssetLibrary.delete_directory(IMPORT_DIR)  # the per-LOD import copies, now merged
        except Exception as exc:
            _warn(f"could not remove {IMPORT_DIR} ({exc}); it only holds import leftovers")
    return out


# ----------------------------------------------------------------------------- grass types

GRASS_SPEC = {
    # density: instances per 10 x 10 m; cull in cm (start fade, end)
    "meadow": [("SM_Grass_A", 260, (2800, 4500), (0.8, 1.25)), ("SM_Grass_B", 110, (3500, 5500), (0.8, 1.2)),
               ("SM_Wheat_A", 45, (3500, 5500), (0.8, 1.2)),
               ("SM_Flower_A", 7, (2500, 4000), (0.8, 1.2)), ("SM_Flower_B", 7, (2500, 4000), (0.8, 1.2)),
               ("SM_Flower_C", 7, (2500, 4000), (0.8, 1.2)), ("SM_Flower_D", 7, (2500, 4000), (0.8, 1.2))],
    "forest": [("SM_Groundfern_A", 35, (2500, 4000), (0.8, 1.4)), ("SM_Clover_A", 90, (1800, 3000), (0.8, 1.3)),
               ("SM_Grass_A", 60, (2500, 4000), (0.7, 1.1))],
    "dune":   [("SM_Dune_A", 45, (3500, 6000), (0.8, 1.3)), ("SM_Dune_B", 25, (3500, 6000), (0.8, 1.3))],
}


def _set_number(obj, prop, value, integer=False):
    """Plain number, or a PerPlatformFloat / PerPlatformInt (UE 5 grass varieties use those)."""
    if _set(obj, prop, int(value) if integer else float(value), quiet=True):
        return True
    for cls_name in (("PerPlatformInt",) if integer else ("PerPlatformFloat",)):
        cls = getattr(unreal, cls_name, None)
        if cls is None:
            continue
        try:
            pp = cls()
            pp.set_editor_property("default", int(value) if integer else float(value))
            if _set(obj, prop, pp, quiet=True):
                return True
        except Exception:
            pass
    _warn(f"grass: could not set {prop}")
    return False


def _grass_types(meshes):
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    factory_cls = getattr(unreal, "LandscapeGrassTypeFactory", None)
    made = []
    for key, path in GRASS_TYPES.items():
        folder, name = path.rsplit("/", 1)
        gt = unreal.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else None
        if gt is None:
            gt = tools.create_asset(name, folder, unreal.LandscapeGrassType, factory_cls() if factory_cls else None)
        if gt is None:
            _warn(f"could not create {path}; create a Landscape Grass Type there by hand")
            continue
        varieties = []
        for mesh_name, density, (start, end), (smin, smax) in GRASS_SPEC[key]:
            mesh = meshes.get(mesh_name)
            if mesh is None:
                continue
            v = unreal.GrassVariety()
            _set(v, "grass_mesh", mesh)
            _set_number(v, "grass_density", density)
            _set_number(v, "start_cull_distance", start, integer=True)
            _set_number(v, "end_cull_distance", end, integer=True)
            _set(v, "use_grid", True, quiet=True)
            _set(v, "placement_jitter", 1.0, quiet=True)
            scaling = getattr(unreal, "GrassScaling", None)
            if scaling is not None:
                _set(v, "scaling", scaling.UNIFORM, quiet=True)
            _set(v, "scale_x", unreal.FloatInterval(smin, smax), quiet=True)
            _set(v, "random_rotation", True, quiet=True)
            _set(v, "align_to_surface", True, quiet=True)
            _set(v, "receives_decals", False, quiet=True)
            _set(v, "cast_dynamic_shadow", key == "meadow" and mesh_name.startswith("SM_Grass"), quiet=True)
            _set(v, "cast_contact_shadow", True, quiet=True)
            varieties.append(v)
        _set(gt, "grass_varieties", varieties)
        _save_asset(gt)
        made.append(name)
    _log(f"grass types {made}: meadow grass + wildflower patches + wheat on dry ground, fern and forest floor, "
         "dune grass. They grow where the terrain material's LandscapeGrassOutput says (T50)")


def _wire_terrain_grass():
    """T50's terrain material adds its LandscapeGrassOutput once GT_Meadow/Forest/Dune exist; its build()
    is idempotent (it checks its own metadata), so ask it now rather than waiting for its next version."""
    try:
        import importlib
        terrain = importlib.import_module("lyris_world_terrain")
    except ImportError:
        _warn("lyris_world_terrain.py is not here: the grass types exist but nothing feeds them yet")
        return
    try:
        terrain.build()
    except Exception as exc:
        _warn(f"could not let the terrain material wire the grass ({exc}); run lyris_world_terrain.build()")


# ----------------------------------------------------------------------------- HLOD layers

def _hlod_layers():
    """Trees use an Instancing HLOD layer (cheap far trees with their own LOD3) out to ~4 km, then a
    MeshApproximate parent (one simplified Nanite mesh per big cell) for the rest of the world."""
    cls = getattr(unreal, "HLODLayer", None)
    types = getattr(unreal, "HLODLayerType", None)
    if cls is None or types is None:
        _warn("HLOD layers are not reachable from Python here: trees stream with their cells only. "
              f"By hand: create HLOD layers at {HLOD_TREES} (Instancing) and {HLOD_TREES_FAR} (Mesh Approximate)")
        return None
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    factory_cls = getattr(unreal, "HLODLayerFactory", None)

    def layer(path, kind, parent=None):
        if unreal.EditorAssetLibrary.does_asset_exist(path):
            return unreal.load_asset(path)
        folder, name = path.rsplit("/", 1)
        lay = tools.create_asset(name, folder, cls, factory_cls() if factory_cls else None)
        if lay is None:
            return None
        _set(lay, "layer_type", kind, quiet=True)
        if parent is not None:
            _set(lay, "parent_layer", parent, quiet=True)
        for prop, val in (("cell_size", 102400 if parent else 409600), ("loading_range", 409600.0 if parent else 3000000.0)):
            _set(lay, prop, val, quiet=True)  # moved to the runtime grid's HLOD settings in newer engines
        _save_asset(lay)
        return lay

    far = layer(HLOD_TREES_FAR, getattr(types, "MESH_APPROXIMATE", getattr(types, "MESH_SIMPLIFY", None)))
    near = layer(HLOD_TREES, types.INSTANCING, far)
    if near is None:
        _warn(f"could not create {HLOD_TREES}; trees stream with their cells only")
    return near


# ----------------------------------------------------------------------------- spawning

def _editor_world():
    sub = getattr(unreal, "UnrealEditorSubsystem", None)
    if sub is not None:
        return unreal.get_editor_subsystem(sub).get_editor_world()
    return unreal.EditorLevelLibrary.get_editor_world()


def _ensure_map():
    world = _editor_world()
    if world and world.get_path_name().startswith(MAP_PATH):
        return
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not unreal.EditorAssetLibrary.does_asset_exist(MAP_PATH):
        raise RuntimeError(f"{MAP_PATH} does not exist yet: run lyris_build_world.build() first")
    les.load_level(MAP_PATH)


def _descs():
    lib = getattr(unreal, "WorldPartitionBlueprintLibrary", None)
    if lib is None or not hasattr(lib, "get_actor_descs"):
        return None
    try:
        return lib.get_actor_descs()
    except Exception as exc:
        _warn(f"could not read World Partition actor descriptors ({exc})")
        return None


def _our_labels(descs, eas):
    """{label: guid or actor} of every foliage actor, loaded or not."""
    found = {}
    if descs is not None:
        for d in descs:
            label = str(_get(d, "label") or "")
            if label.startswith(LABEL_PREFIX):
                found[label] = _get(d, "guid")
    for a in eas.get_all_level_actors():
        try:
            label = a.get_actor_label()
        except Exception:
            continue
        if label.startswith(LABEL_PREFIX):
            found[label] = a
    return found


def _label(sig, group, ix, iy):
    return f"{LABEL_PREFIX}{sig}_{group}_{ix}_{iy}"


def _parse_label(label):
    try:
        sig, group, ix, iy = label[len(LABEL_PREFIX):].rsplit("_", 3)
        return sig, group, int(ix), int(iy)
    except ValueError:
        return None


def _load(guids):
    lib = getattr(unreal, "WorldPartitionBlueprintLibrary", None)
    guids = [g for g in guids if g is not None and not isinstance(g, unreal.Actor)]
    if not guids or lib is None or not hasattr(lib, "load_actors"):
        return
    for i in range(0, len(guids), LOAD_BATCH):
        lib.load_actors(guids[i:i + LOAD_BATCH])


def _unload(actors):
    lib = getattr(unreal, "WorldPartitionBlueprintLibrary", None)
    if lib is None or not hasattr(lib, "unload_actors"):
        return False
    guids = [_get(a, "actor_guid") for a in actors]
    guids = [g for g in guids if g is not None]
    if not guids:
        return False
    try:
        lib.unload_actors(guids)
        return True
    except Exception:
        return False


def _save_dirty():
    try:
        unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    except Exception as exc:
        _warn(f"could not save ({exc}); File > Save All")


def _destroy_labels(eas, labels, what):
    """Loads (from descriptors) and destroys the actors with these labels, DELETE_BATCH at a time."""
    labels = list(labels)
    if not labels:
        return 0
    with unreal.ScopedSlowTask(len(labels), f"Lyris: removing {what}") as task:
        task.make_dialog(True)
        for i in range(0, len(labels), DELETE_BATCH):
            if task.should_cancel():
                raise _Cancelled(f"cancelled while removing {what}")
            chunk = labels[i:i + DELETE_BATCH]
            task.enter_progress_frame(len(chunk), f"{what}: {min(i + DELETE_BATCH, len(labels))}/{len(labels)}")
            entries = _our_labels(_descs(), eas)
            _load([entries.get(l) for l in chunk])
            want = set(chunk)
            actors = [a for a in eas.get_all_level_actors() if a.get_actor_label() in want]
            if actors:
                eas.destroy_actors(actors)
            _save_dirty()
            _log(f"{what}: removed {min(i + DELETE_BATCH, len(labels))}/{len(labels)}")
    return len(labels)


def _add_hism(actor, root_handle, mesh, name):
    """Adds a HierarchicalInstancedStaticMeshComponent to a placed actor (saved with it)."""
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    params = unreal.AddNewSubobjectParams(parent_handle=root_handle,
                                          new_class=unreal.HierarchicalInstancedStaticMeshComponent,
                                          blueprint_context=None)
    handle, fail = sds.add_new_subobject(params)
    if not unreal.SubobjectDataBlueprintFunctionLibrary.is_handle_valid(handle):
        raise RuntimeError(f"could not add a component: {fail}")
    try:
        sds.rename_subobject(handle, unreal.Text(name))
    except Exception:
        pass
    data = unreal.SubobjectDataBlueprintFunctionLibrary.get_data(handle)
    comp = unreal.SubobjectDataBlueprintFunctionLibrary.get_object(data)
    comp.set_static_mesh(mesh)
    return comp


def _configure(comp, species, spec, group):
    start, end = spec.get("cull_m", [0, 0])
    if end:
        _set(comp, "instance_start_cull_distance", int(start * 100), quiet=True)
        _set(comp, "instance_end_cull_distance", int(end * 100), quiet=True)
    _set(comp, "world_position_offset_disable_distance", WPO_DISABLE_CM["trees" if group == "T" else "understory"],
         quiet=True)
    _set(comp, "mobility", unreal.ComponentMobility.STATIC, quiet=True)
    _set(comp, "receives_decals", False, quiet=True)
    if species in NO_SHADOW:
        _set(comp, "cast_shadow", False, quiet=True)
    if spec.get("collision") is None:
        comp.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        _set(comp, "can_ever_affect_navigation", False, quiet=True)
    else:
        comp.set_collision_profile_name("BlockAll")


def _transform(v):
    x, y, z, yaw, pitch, roll, s = v
    return unreal.Transform(unreal.Vector(x, y, z), unreal.Rotator(roll=roll, pitch=pitch, yaw=yaw),
                            unreal.Vector(s, s, s))


def _spawn_actor(eas, sig, group, ix, iy, entries, meshes, catalogue, hlod_layer):
    cx, cy = (ix + 0.5) * CELL_CM, (iy + 0.5) * CELL_CM
    z = sum(v[2] for vals in entries.values() for v in vals) / max(1, sum(len(v) for v in entries.values()))
    actor = eas.spawn_actor_from_class(unreal.Actor, unreal.Vector(cx, cy, z))
    label = _label(sig, group, ix, iy)
    actor.set_actor_label(label)
    actor.set_folder_path(f"{FOLDER}/{'Trees' if group == 'T' else 'Understory'}")
    actor.set_editor_property("tags", [unreal.Name(TAG), unreal.Name(f"{TAG}_{group}")])
    _set(actor, "is_spatially_loaded", True, quiet=True)
    if group == "T" and hlod_layer is not None:
        _set(actor, "hlod_layer", hlod_layer, quiet=True)
    elif group == "U":
        _set(actor, "enable_auto_lod_generation", False, quiet=True)  # "Include Actor in HLOD": off
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    handles = sds.k2_gather_subobject_data_for_instance(actor)
    if not handles:
        raise RuntimeError("could not read the new actor's components")
    root = handles[0]
    first = True
    for name in sorted(entries):
        mesh = meshes.get(name)
        species = catalogue["variant_species"].get(name)
        if mesh is None or species is None:
            continue
        comp = _add_hism(actor, root, mesh, name.replace("SM_", "HISM_"))
        if first:
            # The first scene component became the root; later ones attach under it.
            handles = sds.k2_gather_subobject_data_for_instance(actor)
            root = handles[1] if len(handles) > 1 else root
            first = False
        _configure(comp, species, catalogue["species"][species], group)
        comp.add_instances([_transform(v) for v in entries[name]], False, True)
    return actor


def report():
    species_json, summary = _inputs()
    sig = _signature(summary)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    labels = _our_labels(_descs(), eas)
    current = [l for l in labels if (_parse_label(l) or ("",))[0] == sig]
    cells = os.listdir(_project_path(f"{SRC_DIR}/scatter/cells"))
    _log(f"signature {sig}: {len(current)} actors built, {len(labels) - len(current)} outdated, "
         f"{len(cells)} cells in the scatter; {summary.get('total')} instances ({summary.get('by_group')})")
    return len(current), len(labels) - len(current)


def build(force=False):
    """Incremental: imports what is missing, then spawns the cells not built with this scatter's signature."""
    species_json, summary = _inputs()
    sig = _signature(summary)
    _ensure_map()
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    _log(f"building (signature {sig}, {summary.get('total')} instances in {summary.get('cells')} cells)")

    tex, tint = _textures(species_json)
    mats = _materials(species_json, tex, tint)
    try:
        meshes = _meshes(species_json, mats)
    except _Cancelled as exc:
        raise RuntimeError(f"{exc}; run build() again to continue")
    _grass_types(meshes)
    _wire_terrain_grass()
    hlod = _hlod_layers()

    catalogue = {"species": species_json["species"], "variant_species": {}}
    for s, spec in species_json["species"].items():
        for v in spec["variants"]:
            catalogue["variant_species"][v["name"]] = s

    existing = _our_labels(_descs(), eas)
    outdated = [l for l in existing if force or (_parse_label(l) or ("",))[0] != sig]
    try:
        _destroy_labels(eas, outdated, "outdated foliage cells")
    except _Cancelled as exc:
        raise RuntimeError(f"{exc}; run build() again to continue")
    done = {(p[1], p[2], p[3]) for p in map(_parse_label, existing) if p and p[0] == sig and not force}

    cells_dir = _project_path(f"{SRC_DIR}/scatter/cells")
    files = sorted(f for f in os.listdir(cells_dir) if f.endswith(".bin"))
    todo = []
    for fname in files:
        ix, iy = (int(v) for v in fname[2:-4].split("_"))
        if ("T", ix, iy) in done and ("U", ix, iy) in done:
            continue
        todo.append((ix, iy, fname))
    # Nearest Moonharbor first: the area you play in is ready soonest if the build is stopped.
    todo.sort(key=lambda c: math.hypot((c[0] + 0.5) * 256 - 200, (c[1] + 0.5) * 256 + 2300))
    _log(f"{len(files) - len(todo)} cells already built, {len(todo)} to build")
    if not todo:
        return True

    spawned = 0
    with unreal.ScopedSlowTask(len(todo), "Lyris: planting the world foliage") as task:
        task.make_dialog(True)
        for b in range(0, len(todo), CELLS_PER_BATCH):
            batch_actors = []
            for ix, iy, fname in todo[b:b + CELLS_PER_BATCH]:
                if task.should_cancel():
                    _save_dirty()
                    raise RuntimeError(f"cancelled after {spawned} of {len(todo)} cells (saved); run build() again "
                                       "to continue")
                task.enter_progress_frame(1, f"foliage cell {ix},{iy} ({spawned + 1}/{len(todo)})")
                entries = _read_cell(os.path.join(cells_dir, fname))
                groups = {"T": {}, "U": {}}
                for name, vals in entries.items():
                    species = catalogue["variant_species"].get(name)
                    if species is None:
                        continue
                    g = "T" if catalogue["species"][species]["group"] == "trees" else "U"
                    groups[g][name] = vals
                for g, ent in groups.items():
                    if ent and (g, ix, iy) not in done:
                        batch_actors.append(_spawn_actor(eas, sig, g, ix, iy, ent, meshes, catalogue, hlod))
                spawned += 1
            _save_dirty()
            _unload(batch_actors)  # keep editor memory flat on an 8 GB machine
            _log(f"planted {spawned}/{len(todo)} cells")
    _log(f"done: {spawned} cells planted. Build > Build HLODs to make the distant forests")
    return True


def clear():
    """Removes every actor this script made (and only those), in batches."""
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    labels = list(_our_labels(_descs(), eas))
    try:
        n = _destroy_labels(eas, labels, "world foliage")
    except _Cancelled as exc:
        _warn(f"{exc}; run clear() again to finish")
        return False
    _log(f"cleared {n} foliage actors")
    return True
