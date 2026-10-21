"""The world terrain's look (T50): the starter island's texturing, stretched over all 25 km of Lyris.

The world landscape is imported from the heightmap only (no paint layers), so the old layer-driven
material drew it black with roughness 0. This module builds M_LyrisWorldTerrain_v2, which needs no
paint layers at all: it reads the biome of every point from two world-space maps baked offline, and
everything else (rock, beaches, seabed, colour variation) from height, slope and painted noise.

    import lyris_world_terrain as t; t.build(); t.apply()

    t.build()               imports the textures and builds (or updates) the material
    t.build(reimport=True)  also re-imports the biome maps, after a new terrain bake
    t.build(force=True)     rebuilds the material graph even if it is up to date
    t.apply()               puts the material on the landscape (and its loaded proxies) and saves
    t.apply(load_all=True)  first loads every landscape proxy in the World Partition map (slow, RAM)

Before the first build, in a terminal at the project folder (numpy + pillow):
    python Art/World/bake_biome_maps.py        # after bake_terrain.py: Art/World/biome/*.png
The painted detail textures (Art/World/textures/) are in git; paint_world_textures.py remakes them.

The look, faithful to the starter island (the retired lyris_build_harbor.py, _material_terrain and
_rock_colour):
  * one palette (ISLAND_PALETTE and LAYER_LOOK colours from lyris_build_world.py); the textures only add
    light and dark detail around those colours, at two scales (4 m and ~15 m) so repeats never show;
  * warm stone with lavender shadows (rock_lit on top, rock_shade facing down), textured from three
    sides, on anything steeper than ~37 degrees; grass only on the flat tops of rocky ground;
  * the warm-to-cool tone drift and matte roughness (0.94; snow and salt a little glossier);
  * the biome of each point from Art/World/biome/T_LyrisBiomeA/B (Grass Forest Sand Rock /
    Snow Badlands Salt Volcanic) by world position, edges broken up with painted noise;
  * sand shelves at the waterline (by height), a wet band at the tide line, and below sea level a
    seabed of rippled sand that darkens and cools with depth (the sea surface is its own mesh);
  * large patches so 25 km never looks uniform (sunny meadows, drier hills, lush low valleys) and a
    very soft distance tint.
Cost: 11 texture samples from 5 small textures (no per-layer triplanars: one shared triplanar for the
rock, whose top face reuses the ground's own detail sample). See Art/World/README.md, section 4.

Grass (T51): a LandscapeGrassOutput with Meadow, Forest and Dune is added when the grass types
/Game/Lyris/World/Foliage/GT_Meadow, GT_Forest and GT_Dune exist; otherwise the material is built
without it and build() adds it the next time it runs after T51's assets are there.

Colours: every hex value below is from PALETTE, ISLAND_PALETTE or LAYER_LOOK in lyris_build_world.py
(the island's grass-texture highlight "D3DE8A" is from Art/TestIsland/paint_textures.py), except the
new biomes' textures in Art/World/paint_world_textures.py, whose colours never reach the game (only
their luminance does).
"""

import json
import math
import os

try:
    import unreal
except ImportError:  # the offline preview (Art/World/preview_terrain_look.py) imports the look only
    unreal = None

TERRAIN_LOOK_VERSION = 1   # bump to rebuild the material graph and re-import the textures
MAT_DIR = "/Game/Lyris/Materials/World"
MAT_NAME = "M_LyrisWorldTerrain_v2"   # v1 is lyris_build_world's paint-layer material (left untouched)
MAT_PATH = f"{MAT_DIR}/{MAT_NAME}"
TEX_DIR = "/Game/Lyris/Textures/WorldTerrain"
GRASS_DIR = "/Game/Lyris/World/Foliage"
GRASS_TYPES = ("Meadow", "Forest", "Dune")   # T51 contract: GT_<name> in GRASS_DIR
META_LOOK = "LyrisTerrainLook"
META_GRASS = "LyrisTerrainGrass"

BIOME_DIR = "Art/World/biome"
BIOME_META = "biome_maps.json"
DETAIL_DIR = "Art/World/textures"
DETAIL_META = "world_textures.json"
BIOME_MAPS = ("T_LyrisBiomeA", "T_LyrisBiomeB")
DETAIL_MAPS = ("T_LyrisDetailA", "T_LyrisDetailB", "T_LyrisWorldNoise")
# Biome maps: BC-compressed masks keep them at ~21 MB each with mips (8 GB GPUs); the material
# renormalises the eight weights, so compression never shows. True = uncompressed (~85 MB each).
BIOME_UNCOMPRESSED = False
WORLD_MIN_FALLBACK = -1250000.0
WORLD_SIZE_FALLBACK = 2500000.0

# ----------------------------------------------------------------------------- the look (shared with the preview)

LOOK = {
    # ISLAND_PALETTE
    "grass": "9DB872", "grass_shade": "6E9061", "sand": "EFE2C4", "path": "CDAE86",
    "rock_lit": "D6BC9F", "rock_shade": "8E7680",
    "meadow_light": "D3DE8A",     # the island grass texture's sunlit highlight
    # LAYER_LOOK
    "forest": "6E9061", "forest_deep": "4F7558",
    "sand_pale": "F1E9DC",
    "snow": "F7EEDC", "snow_cool": "EEF3FF",
    "badlands": "C8643A", "badlands_red": "C8443A",
    "salt": "F1E9DC", "salt_pale": "F7EEDC",
    "volcanic": "36221A", "volcanic_warm": "4A2A1C",
    # PALETTE: shallows and sea, for the seabed under the water
    "shallows": "7FD0D6", "sea_trough": "1F6A80",
    # the island's warm-to-cool tone
    "tone_warm": "FFF6E8", "tone_cool": "EEF3FF",
}

NEAR = 1.0 / 400.0      # detail repeats every 4 m (the island's TILE)
FAR = NEAR * 0.27       # ... and every ~15 m (the island's second grass scale)
FAR_ANGLE = 37.0        # the far scale is turned against the near one ...
DETAIL_WARP = (0.35, 0.45)  # ... and both wander by this much of a tile with the 97 m noise: no visible grid
MID = 1.0 / 30000.0     # edge-breakup noise, 300 m (soft blobs ~60-100 m) ...
MID_RATIO = 1.618       # ... plus a second sample at 1/1.618 the size,
MID_ANGLE = 53.0        # turned this far: together they never repeat
MACRO = 1.0 / 170000.0  # meadow / dry-hill / lush patches, 1.7 km
GIANT = 1.0 / 2300000.0  # warm-to-cool drift across the whole world
NOISE_CHAIN = 1.0       # tiles of offset each noise scale takes from the next larger one
WARP_M = 14.0           # biome edges wander up to this far (the maps are ~6 m per pixel)
BLEND_DEPTH = 0.25      # how close to the strongest layer another must be to show at all
EDGE_NOISE = 0.4        # per-layer noise that breaks up biome edges
# Detail strength per pack channel at the near and far scale (island: grass .55/.45, sand .5, cliff .3).
DETAIL_A = {"near": (0.55, 0.5, 0.3, 0.45), "far": (0.45, 0.3, 0.2, 0.35)}   # grass sand cliff seabed
DETAIL_B = {"near": (0.5, 0.4, 0.4, 0.4), "far": (0.35, 0.35, 0.3, 0.3)}    # snow strata salt basalt
STEEP = (-5.5, 4.4)     # steep = saturate(up * a + b): rock from ~37 degrees, all rock by ~52 (island)
FLAT_TOP = (5.0, -3.7)  # grass on rock only where saturate(up * a + b): nearly flat tops (island rock)
SHORE_M = 1.6           # sand shelf up to this height above the sea ...
SHORE_FADE_M = 1.4      # ... fading out over this much more
WET_M = (0.15, 0.7)     # wet band centre and half width (m)
SEABED_DEEP_M = 40.0    # the seabed reaches its darkest, coolest colour at this depth
BADLANDS_SOFTEN = 0.3   # terracotta is a roof colour: soften it toward warm stone for whole hillsides
STRATA_SLOPE = (0.98, 10.0)  # bands from ~11 degrees, full by ~28
SNOW_ALBEDO = 0.88      # a touch under the palette so sunlit snow keeps its painted detail
SNOW_SHADE = 0.3        # snow on slopes leans lavender (toward rock_shade), warm cream on the flat
STRATA_M = 7.0          # badlands band spacing (m)
STRATA_FADE_CM = (150000.0, 400000.0)  # bands fade to their average between 1.5 and 4 km (no shimmer far off)
ROUGH = {"base": 0.94, "snow": 0.82, "salt": 0.8, "wet": 0.6}
DISTANCE_TINT = (60000.0, 900000.0, 0.14)   # start cm, full cm, strength (very soft)

# ----------------------------------------------------------------------------- helpers


def _log(msg):
    unreal.log("[Lyris] " + msg)


def _warn(msg):
    unreal.log_warning("[Lyris] " + msg)


def _project_path(rel):
    return os.path.join(unreal.Paths.project_dir(), rel)


def srgb_to_linear(hex_str):
    def ch(v):
        c = int(v, 16) / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return tuple(ch(hex_str[i:i + 2]) for i in (0, 2, 4))


def _set(obj, prop, value, quiet=False):
    try:
        obj.set_editor_property(prop, value)
        return True
    except Exception as exc:
        if not quiet:
            _warn(f"could not set {prop} on {obj.get_name()}: {exc}")
        return False


def _read_json(rel):
    try:
        with open(_project_path(rel)) as f:
            return json.load(f)
    except Exception:
        return None


def _enum(owner, *names):
    """First enum value that exists (engine versions rename a few)."""
    for n in names:
        v = getattr(owner, n, None)
        if v is not None:
            return v
    return None


class _Graph:
    """Material graph builder in the style of the island's helper, plus float4 and swizzle helpers."""

    def __init__(self, path):
        folder, name = path.rsplit("/", 1)
        self.path = path
        self.exists = unreal.EditorAssetLibrary.does_asset_exist(path)
        if self.exists:
            self.mat = unreal.load_asset(path)
        else:
            tools = unreal.AssetToolsHelpers.get_asset_tools()
            self.mat = tools.create_asset(name, folder, unreal.Material, unreal.MaterialFactoryNew())
        self.mel = unreal.MaterialEditingLibrary
        self.x, self.y = -2400, 0
        self._wp = self._nrm = self._one4 = None

    def clear(self):
        self.mel.delete_all_material_expressions(self.mat)
        self._wp = self._nrm = self._one4 = None

    def node(self, cls, **props):
        expr = self.mel.create_material_expression(self.mat, cls, self.x, self.y)
        self.y += 110
        if self.y > 9000:  # keep the graph readable: columns of nodes
            self.y = 0
            self.x += 320
        for key, value in props.items():
            expr.set_editor_property(key, value)
        return expr

    def link(self, src, dst, src_out="", dst_in=""):
        if not self.mel.connect_material_expressions(src, src_out, dst, dst_in):
            _warn(f"material link failed: {src.get_name()}.{src_out or 'out'} -> {dst.get_name()}.{dst_in or 'in'}")

    def const(self, v):
        return self.node(unreal.MaterialExpressionConstant, r=float(v))

    def colour(self, hex_str):
        r, g, b = srgb_to_linear(hex_str)
        return self.node(unreal.MaterialExpressionConstant3Vector, constant=unreal.LinearColor(r, g, b, 1.0))

    def vec4(self, v):
        return self.node(unreal.MaterialExpressionConstant4Vector,
                         constant=unreal.LinearColor(float(v[0]), float(v[1]), float(v[2]), float(v[3])))

    def op(self, cls, a, b=None, a_out="", b_out="", const_b=None):
        expr = self.node(cls) if const_b is None else self.node(cls, const_b=float(const_b))
        self.link(a, expr, a_out, "A")
        if b is not None:
            self.link(b, expr, b_out, "B")
        return expr

    def mul(self, a, b=None, a_out="", b_out="", k=None):
        return self.op(unreal.MaterialExpressionMultiply, a, b, a_out, b_out, k)

    def add(self, a, b=None, a_out="", b_out="", k=None):
        return self.op(unreal.MaterialExpressionAdd, a, b, a_out, b_out, k)

    def sub(self, a, b=None, a_out="", b_out="", k=None):
        return self.op(unreal.MaterialExpressionSubtract, a, b, a_out, b_out, k)

    def div(self, a, b, a_out="", b_out=""):
        return self.op(unreal.MaterialExpressionDivide, a, b, a_out, b_out)

    def mad(self, a, k, c):
        """a * k + c with constants (scalars)."""
        return self.add(self.mul(a, k=k), k=c)

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

    def mask(self, src, channels, src_out=None):
        if src_out is None:  # a texture sample's float4 is its "RGBA" output; other nodes have one output
            src_out = "RGBA" if isinstance(src, unreal.MaterialExpressionTextureSample) else ""
        return self.single(unreal.MaterialExpressionComponentMask, src, src_out, r="R" in channels,
                           g="G" in channels, b="B" in channels, a="A" in channels)

    def append(self, a, b):
        expr = self.node(unreal.MaterialExpressionAppendVector)
        self.link(a, expr, "", "A")
        self.link(b, expr, "", "B")
        return expr

    def saturate(self, src):
        return self.single(unreal.MaterialExpressionSaturate, src)

    def dot(self, a, b):
        expr = self.node(unreal.MaterialExpressionDotProduct)
        self.link(a, expr, "", "A")
        self.link(b, expr, "", "B")
        return expr

    def sum4(self, v):
        if self._one4 is None:
            self._one4 = self.vec4((1, 1, 1, 1))
        return self.dot(v, self._one4)

    def wp(self):
        if self._wp is None:
            self._wp = self.node(unreal.MaterialExpressionWorldPosition)
        return self._wp

    def normal(self):
        if self._nrm is None:
            self._nrm = self.node(unreal.MaterialExpressionVertexNormalWS)
        return self._nrm

    def tex(self, texture, uv, sampler):
        expr = self.node(unreal.MaterialExpressionTextureSample, texture=texture)
        if sampler is not None:
            _set(expr, "sampler_type", sampler, quiet=True)
        self.link(uv, expr, "", "UVs")
        return expr

    def proj(self, channels, scale):
        """World position projected onto two axes, scaled: texture coordinates in world space."""
        return self.mul(self.mask(self.wp(), channels), k=scale)

    def out(self, expr, prop, pin=""):
        if not self.mel.connect_material_property(expr, pin, prop):
            _warn(f"could not connect {prop}")


# ----------------------------------------------------------------------------- textures


def _import_texture(filename, destination, name, data_settings):
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", filename)
    task.set_editor_property("destination_path", destination)
    task.set_editor_property("destination_name", name)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", False)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    tex = unreal.load_asset(f"{destination}/{name}")
    if tex is None:
        raise RuntimeError(f"texture import failed: {filename}")
    compression, clamp = data_settings
    _set(tex, "srgb", False)  # weights and detail are data, not colour
    _set(tex, "compression_settings", compression)
    addr = _enum(unreal.TextureAddress, "TA_CLAMP" if clamp else "TA_WRAP")
    _set(tex, "address_x", addr)
    _set(tex, "address_y", addr)
    unreal.EditorAssetLibrary.save_loaded_asset(tex)
    return tex


def _sampler_for(compression):
    st = unreal.MaterialSamplerType
    if compression == unreal.TextureCompressionSettings.TC_MASKS:
        return _enum(st, "SAMPLERTYPE_MASKS")
    return _enum(st, "SAMPLERTYPE_LINEAR_COLOR")


def _textures(reimport=False):
    """Imports the biome maps and the detail/noise packs. Returns ({name: texture}, {name: sampler})."""
    tcs = unreal.TextureCompressionSettings
    masks = tcs.TC_MASKS
    raw = _enum(tcs, "TC_VECTOR_DISPLACEMENTMAP", "TC_HDR")
    biome_comp = raw if BIOME_UNCOMPRESSED else masks
    sources = {}
    for n in BIOME_MAPS:
        sources[n] = (os.path.join(_project_path(BIOME_DIR), n + ".png"), (biome_comp, True))
    for n in DETAIL_MAPS:
        sources[n] = (os.path.join(_project_path(DETAIL_DIR), n + ".png"), (masks, False))
    tex, samplers = {}, {}
    for n, (src, settings) in sources.items():
        path = f"{TEX_DIR}/{n}"
        stale = (reimport and n in BIOME_MAPS) or not unreal.EditorAssetLibrary.does_asset_exist(path)
        if stale:
            if not os.path.exists(src):
                if n in BIOME_MAPS:
                    raise RuntimeError(f"{src} is missing. In a terminal at the project folder run "
                                       "`python Art/World/bake_biome_maps.py` (after bake_terrain.py), then build() again")
                raise RuntimeError(f"{src} is missing: run `python Art/World/paint_world_textures.py`")
            _log(f"importing {n}")
            tex[n] = _import_texture(src, TEX_DIR, n, settings)
        else:
            tex[n] = unreal.load_asset(path)
        samplers[n] = _sampler_for(settings[0])
    return tex, samplers


def _world_bounds():
    meta = _read_json(os.path.join(BIOME_DIR, BIOME_META)) or {}
    lo = float(meta.get("world_min_ue", WORLD_MIN_FALLBACK))
    size = float(meta.get("world_size_ue", WORLD_SIZE_FALLBACK))
    if meta.get("row_axis", "UE Y").split()[1:2] != ["Y"]:
        _warn(f"biome_maps.json row axis is '{meta.get('row_axis')}', expected UE Y: the biomes may be mirrored")
    return lo, size


def _grass_types():
    found = {}
    for n in GRASS_TYPES:
        path = f"{GRASS_DIR}/GT_{n}"
        if unreal.EditorAssetLibrary.does_asset_exist(path):
            found[n] = unreal.load_asset(path)
    return found if len(found) == len(GRASS_TYPES) else {}


# ----------------------------------------------------------------------------- the material


def _graph(g, tex, smp, grass_types):
    P = LOOK
    lo, size = _world_bounds()
    wp = g.wp()
    xy = g.mask(wp, "RG")
    z_m = g.mul(g.mask(wp, "B"), k=0.01)                          # metres above the sea (sea level is Z 0)
    up = g.mask(g.normal(), "B")
    up01 = g.saturate(g.mad(up, 0.5, 0.5))
    steep = g.saturate(g.mad(up, STEEP[0], STEEP[1]))
    flat_top = g.saturate(g.mad(up, FLAT_TOP[0], FLAT_TOP[1]))

    # Noise: mid (edge breakup), macro (patches), giant (warm/cool drift). One small texture, three scales.
    noise, noise_s = tex["T_LyrisWorldNoise"], smp["T_LyrisWorldNoise"]
    # Each scale's UV is pushed around by the larger one, so no scale ever repeats as a grid.
    giant = g.tex(noise, g.mul(xy, k=GIANT), noise_s)
    macro = g.tex(noise, g.add(g.mul(xy, k=MACRO), g.mul(g.mask(giant, "RG"), k=NOISE_CHAIN)), noise_s)
    # The mid scale is two samples, turned and at a golden-ratio scale to each other: their sum never
    # repeats, so the 97 m tile can't show as a lattice where two biomes are evenly mixed.
    chain = g.mul(g.mask(macro, "BA"), k=NOISE_CHAIN)
    mid_a = g.tex(noise, g.add(g.mul(xy, k=MID), chain), noise_s)
    cb, sb = math.cos(math.radians(MID_ANGLE)), math.sin(math.radians(MID_ANGLE))
    k2 = MID * MID_RATIO
    mid_uv2 = g.append(g.dot(xy, g.node(unreal.MaterialExpressionConstant2Vector, r=cb * k2, g=-sb * k2)),
                       g.dot(xy, g.node(unreal.MaterialExpressionConstant2Vector, r=sb * k2, g=cb * k2)))
    mid_b = g.tex(noise, g.sub(mid_uv2, chain), noise_s)
    mid = g.add(g.mul(g.add(g.mask(mid_a, "RGBA"), g.mask(mid_b, "RGBA")), k=0.7071),
                k=0.5 - 0.7071)
    mid4 = g.mask(mid, "RGBA")

    # Biome weights by world position, the UV wandering a little so pixel steps never show.
    uv = g.mul(g.sub(xy, k=lo), k=1.0 / size)
    warp = g.mul(g.add(g.mask(mid, "RG"), k=-0.5), k=2.0 * WARP_M * 100.0 / size)
    uvw = g.add(uv, warp)
    bA = g.tex(tex["T_LyrisBiomeA"], uvw, smp["T_LyrisBiomeA"])
    bB = g.tex(tex["T_LyrisBiomeB"], uvw, smp["T_LyrisBiomeB"])
    # Per-layer noise (a different channel order for B) sharpens and breaks up every edge, then the
    # eight weights are renormalised (this also absorbs any compression error).
    nA = g.add(mid4, k=-0.5)
    nB = g.add(g.append(g.append(g.append(g.mask(mid, "B"), g.mask(mid, "A")),
                                 g.mask(mid, "R")), g.mask(mid, "G")), k=-0.5)

    # Height-blend style: a layer shows only where it is within BLEND_DEPTH of the strongest one, so
    # faint layers (a little snow on a volcano) never come through as spots.
    sA = g.add(g.mask(bA, "RGBA"), g.mul(nA, k=EDGE_NOISE))
    sB = g.add(g.mask(bB, "RGBA"), g.mul(nB, k=EDGE_NOISE))
    mx = g.op(unreal.MaterialExpressionMax, sA, sB)
    mx = g.op(unreal.MaterialExpressionMax, g.op(unreal.MaterialExpressionMax, g.mask(mx, "R"), g.mask(mx, "G")),
              g.op(unreal.MaterialExpressionMax, g.mask(mx, "B"), g.mask(mx, "A")))

    def sharpen(s):
        return g.add(g.saturate(g.add(g.div(g.sub(s, mx), g.const(BLEND_DEPTH)), k=1.0)), k=0.002)
    wA, wB = sharpen(sA), sharpen(sB)
    total = g.add(g.sum4(wA), g.sum4(wB))
    wA, wB = g.div(wA, total), g.div(wB, total)
    w = {n: g.mask(wA, c) for n, c in zip(("Grass", "Forest", "Sand", "Rock"), "RGBA")}
    w.update({n: g.mask(wB, c) for n, c in zip(("Snow", "Badlands", "Salt", "Volcanic"), "RGBA")})

    # Light/dark detail, two scales, eight patterns in four samples: detail = 1 + (2 s - 1) k.
    # The UVs wander with the 97 m noise and the far scale is turned, so the 4 m and 15 m tiles never
    # line up into a grid across a hillside.
    uv_near = g.add(g.mul(xy, k=NEAR), g.mul(g.add(g.mask(mid, "RG"), k=-0.5), k=DETAIL_WARP[0]))
    ca, sa = math.cos(math.radians(FAR_ANGLE)), math.sin(math.radians(FAR_ANGLE))
    rot = g.append(g.dot(xy, g.node(unreal.MaterialExpressionConstant2Vector, r=ca * FAR, g=-sa * FAR)),
                   g.dot(xy, g.node(unreal.MaterialExpressionConstant2Vector, r=sa * FAR, g=ca * FAR)))
    uv_far = g.add(rot, g.mul(g.add(g.mask(mid, "BA"), k=-0.5), k=DETAIL_WARP[1]))
    def detail(name, coeffs):
        t, s = tex[name], smp[name]
        near = g.tex(t, uv_near, s)
        far = g.tex(t, uv_far, s)

        def scale(sample, k):
            return g.add(g.mul(g.mask(sample, "RGBA"), g.vec4([2 * v for v in k])), g.vec4([1 - v for v in k]))
        return g.mul(scale(near, coeffs["near"]), scale(far, coeffs["far"])), near
    dA, dA_near = detail("T_LyrisDetailA", DETAIL_A)
    dB, _ = detail("T_LyrisDetailB", DETAIL_B)
    d = {"grass": g.mask(dA, "R"), "sand": g.mask(dA, "G"), "seabed": g.mask(dA, "A"),
         "snow": g.mask(dB, "R"), "strata": g.mask(dB, "G"), "salt": g.mask(dB, "B"), "basalt": g.mask(dB, "A")}

    # Rock: one triplanar of the cliff channel; its top face reuses the ground's near sample.
    nrm = g.normal()
    tw = g.single(unreal.MaterialExpressionPower, g.single(unreal.MaterialExpressionAbs, nrm), const_exponent=4.0)
    tw = g.div(tw, g.dot(tw, g.colour("FFFFFF")))
    detA = tex["T_LyrisDetailA"]
    sx = g.tex(detA, g.proj("GB", NEAR), smp["T_LyrisDetailA"])
    sy = g.tex(detA, g.proj("RB", NEAR), smp["T_LyrisDetailA"])
    cliff = g.dot(g.append(g.append(g.mask(sx, "B"), g.mask(sy, "B")),
                           g.mask(dA_near, "B")), tw)
    rock_detail = g.mad(cliff, 2 * DETAIL_A["near"][2], 1 - DETAIL_A["near"][2])
    rock = g.mul(g.lerp(g.colour(P["rock_shade"]), g.colour(P["rock_lit"]), up01), rock_detail)

    m_r, m_g, m_b, m_a = (g.mask(macro, c) for c in "RGBA")
    # Grass: lush and darker in low valleys, drier toward high or dry ground, sunny meadow patches.
    lowland = g.saturate(g.mad(z_m, -1.0 / 50.0, 1.0))
    lush = g.saturate(g.add(g.mad(m_r, 1.5, -0.45), g.mul(lowland, k=0.45)))
    grass = g.lerp(g.colour(P["grass"]), g.colour(P["grass_shade"]), g.mul(lush, k=0.55))
    meadow = g.saturate(g.mad(m_b, 2.2, -1.2))
    grass = g.lerp(grass, g.colour(P["meadow_light"]), g.mul(meadow, k=0.35))
    dry = g.saturate(g.add(g.mad(m_g, 2.5, -1.4), g.mad(z_m, 1.0 / 140.0, -0.5)))
    grass = g.lerp(grass, g.colour(P["path"]), g.mul(dry, k=0.5))
    grass = g.mul(grass, d["grass"])
    forest = g.mul(g.lerp(g.colour(P["forest"]), g.colour(P["forest_deep"]), g.mul(g.saturate(g.mad(m_r, 1.2, -0.1)), k=0.6)),
                   d["grass"])
    sand = g.lerp(g.colour(P["sand"]), g.colour(P["sand_pale"]), m_b)
    dunes = g.mul(g.saturate(g.mad(z_m, 1.0 / 12.0, -0.25)), g.mad(m_g, 0.3, 0.15))   # golden away from the sea
    sand = g.mul(g.lerp(sand, g.colour(P["path"]), dunes), d["sand"])
    rock_flat = g.lerp(rock, grass, flat_top)
    snow_shade = g.lerp(g.colour(P["snow_cool"]), g.colour(P["rock_shade"]), g.const(SNOW_SHADE))
    snow = g.mul(g.mul(g.lerp(snow_shade, g.colour(P["snow"]), g.saturate(g.mad(up, 4.0, -3.0))), d["snow"]),
                 k=SNOW_ALBEDO)
    pixel_depth = g.node(unreal.MaterialExpressionPixelDepth)
    strata = g.single(unreal.MaterialExpressionFrac,
                      g.add(g.mul(z_m, k=1.0 / STRATA_M), g.mul(g.mask(mid, "B"), k=0.6)))
    near_bands = g.saturate(g.mad(pixel_depth, -1.0 / (STRATA_FADE_CM[1] - STRATA_FADE_CM[0]),
                                  STRATA_FADE_CM[1] / (STRATA_FADE_CM[1] - STRATA_FADE_CM[0])))
    # Bands show on slopes (where layers are cut open), not as contour lines across gentle ground.
    near_bands = g.mul(near_bands, g.saturate(g.mad(up, -STRATA_SLOPE[1], STRATA_SLOPE[0] * STRATA_SLOPE[1])))
    bad = g.lerp(g.colour(P["badlands"]), g.colour(P["badlands_red"]),
                 g.mul(g.saturate(g.mad(strata, 6.0, -3.6)), near_bands))
    bad = g.lerp(bad, g.colour(P["path"]), g.mul(g.saturate(g.mad(strata, -5.0, 0.75)), near_bands))
    bad = g.mul(g.lerp(bad, g.colour(P["rock_lit"]), g.const(BADLANDS_SOFTEN)), d["strata"])
    salt = g.mul(g.lerp(g.colour(P["salt"]), g.colour(P["salt_pale"]), m_a), d["salt"])
    volc = g.lerp(g.colour(P["volcanic"]), g.colour(P["volcanic_warm"]), m_r)
    volc = g.mul(g.lerp(volc, g.colour(P["rock_shade"]), g.const(0.3)), d["basalt"])

    land = None
    for name, col in (("Grass", grass), ("Forest", forest), ("Sand", sand), ("Rock", rock_flat),
                      ("Snow", snow), ("Badlands", bad), ("Salt", salt), ("Volcanic", volc)):
        term = g.mul(col, w[name])
        land = term if land is None else g.add(land, term)

    # Steep ground is stone whatever the biome: strata in the badlands, dark basalt on the volcano.
    cliff_col = g.lerp(rock, g.mul(bad, rock_detail), w["Badlands"])
    cliff_col = g.lerp(cliff_col, g.mul(volc, rock_detail), w["Volcanic"])
    base = g.lerp(land, cliff_col, steep)

    # Sand shelf at the waterline (not on salt flats or cliffs), then the wet band at the tide line.
    shore_line = g.add(g.mul(g.mask(mid, "A"), k=1.5), k=SHORE_M - 0.75)
    shore = g.saturate(g.mul(g.sub(shore_line, z_m), k=1.0 / SHORE_FADE_M))
    shore = g.mul(g.mul(shore, g.sub(g.const(1.0), steep)), g.sub(g.const(1.0), w["Salt"]))
    base = g.lerp(base, sand, shore)
    wet = g.saturate(g.mad(g.single(unreal.MaterialExpressionAbs, g.add(z_m, k=-WET_M[0])), -1.0 / WET_M[1], 1.0))
    base = g.mul(base, g.mad(wet, -0.18, 1.0))

    # Under the sea: rippled sand that darkens and cools with depth.
    under = g.saturate(g.mul(z_m, k=-2.0))
    depth = g.saturate(g.mul(z_m, k=-1.0 / SEABED_DEEP_M))
    bed = g.mul(g.colour(P["sand"]), d["seabed"])
    base = g.lerp(base, bed, g.mul(under, g.sub(g.const(1.0), g.mul(steep, k=0.6))))
    deep = g.single(unreal.MaterialExpressionSquareRoot, depth)     # quick at first, then slower
    deep_col = g.lerp(g.colour(P["shallows"]), g.colour(P["sea_trough"]), deep)
    base = g.lerp(base, g.mul(base, deep_col), g.mul(under, g.mad(deep, 0.65, 0.35)))
    base = g.mul(base, g.mad(g.mul(deep, under), -0.55, 1.0))

    # The island's warm-to-cool tone, very large light/dark patches, and a soft distance tint.
    base = g.mul(base, g.lerp(g.colour(P["tone_warm"]), g.colour(P["tone_cool"]), g.mask(giant, "A")))
    base = g.mul(base, g.mad(m_a, 0.12, 0.94))
    far = g.saturate(g.mad(pixel_depth,
                           1.0 / (DISTANCE_TINT[1] - DISTANCE_TINT[0]), -DISTANCE_TINT[0] / (DISTANCE_TINT[1] - DISTANCE_TINT[0])))
    base = g.lerp(base, g.mul(g.colour(P["tone_cool"]), k=0.78), g.mul(far, k=DISTANCE_TINT[2]))
    g.out(base, unreal.MaterialProperty.MP_BASE_COLOR)

    rough = g.add(g.add(g.mul(w["Snow"], k=ROUGH["snow"] - ROUGH["base"]),
                        g.mul(w["Salt"], k=ROUGH["salt"] - ROUGH["base"])), k=ROUGH["base"])
    rough = g.lerp(rough, g.const(ROUGH["wet"]), g.mul(wet, g.sub(g.const(1.0), under)))
    g.out(rough, unreal.MaterialProperty.MP_ROUGHNESS)

    if grass_types:
        flat_g = g.saturate(g.mad(up, 1.0 / 0.06, -0.88 / 0.06))       # under ~25 degrees
        dry_land = g.mul(g.mul(flat_g, g.saturate(g.mad(z_m, 1.0, -1.2))), g.sub(g.const(1.0), shore))
        weights = {
            "Meadow": g.mul(g.saturate(g.add(w["Grass"], g.mul(w["Rock"], flat_top))), dry_land),
            "Forest": g.mul(w["Forest"], dry_land),
            "Dune": g.mul(g.mul(w["Sand"], flat_g), g.saturate(g.mad(z_m, 1.25, -1.0))),
        }
        return _grass_output(g, grass_types, weights)
    return False


def _grass_output(g, grass, weights):
    """LandscapeGrassOutput with one named entry per grass type. Returns True when wired."""
    cls = getattr(unreal, "MaterialExpressionLandscapeGrassOutput", None)
    struct = getattr(unreal, "GrassInput", None)
    if cls is None or struct is None:
        _warn("LandscapeGrassOutput / GrassInput are not exposed to Python here: add a Grass Output node by hand "
              "(entries Meadow, Forest, Dune -> GT_Meadow, GT_Forest, GT_Dune); see Art/World/README.md")
        return False
    node = g.node(cls)
    entries = []
    for name in GRASS_TYPES:
        entry = struct()
        ok = _set(entry, "name", name, quiet=True)
        ok = _set(entry, "grass_type", grass[name], quiet=True) and ok
        if not ok:
            _warn("could not fill GrassInput (name / grass_type not editable from Python); add the Grass Output "
                  "node by hand, see Art/World/README.md")
            return False
        entries.append(entry)
    if not _set(node, "grass_types", entries):
        return False
    ok = True
    for name in GRASS_TYPES:
        ok = g.mel.connect_material_expressions(weights[name], "", node, name) and ok
    if not ok:
        _warn("grass output: could not connect its inputs by name; check the Grass Output node in the material")
    return ok


def build(force=False, reimport=False):
    """Imports the textures and builds M_LyrisWorldTerrain_v2. Re-runnable: it rebuilds the graph when
    TERRAIN_LOOK_VERSION changes, when T51's grass types have appeared since the last build, or on force."""
    if unreal is None:
        raise RuntimeError("build() runs inside the Unreal editor")
    tex, smp = _textures(reimport=reimport or force)
    g = _Graph(MAT_PATH)
    eal = unreal.EditorAssetLibrary
    grass = _grass_types()
    built_look = eal.get_metadata_tag(g.mat, META_LOOK) if g.exists else None
    built_grass = eal.get_metadata_tag(g.mat, META_GRASS) if g.exists else None
    up_to_date = (built_look == str(TERRAIN_LOOK_VERSION)) and (built_grass == "1" or not grass)
    if g.exists and up_to_date and not force:
        _log(f"{MAT_NAME} is up to date (look v{TERRAIN_LOOK_VERSION}, grass {'on' if built_grass == '1' else 'off'})")
        return g.mat
    if g.exists:
        g.clear()
    _log(f"building {MAT_NAME} (look v{TERRAIN_LOOK_VERSION})")
    wired = _graph(g, tex, smp, grass)
    if not grass:
        _log(f"grass output skipped: {GRASS_DIR}/GT_Meadow, GT_Forest, GT_Dune do not exist yet (T51). "
             "Run build() again once they do; it adds the grass output then.")
    g.mel.recompile_material(g.mat)
    eal.set_metadata_tag(g.mat, META_LOOK, str(TERRAIN_LOOK_VERSION))
    eal.set_metadata_tag(g.mat, META_GRASS, "1" if wired else "0")
    eal.save_loaded_asset(g.mat)
    _log(f"{MAT_NAME} ready: {MAT_PATH} (grass output {'on' if wired else 'off'})")
    return g.mat


# ----------------------------------------------------------------------------- putting it on the landscape


def _load_all_landscape_proxies():
    lib = getattr(unreal, "WorldPartitionBlueprintLibrary", None)
    if lib is None or not hasattr(lib, "get_actor_descs"):
        _warn("WorldPartitionBlueprintLibrary.get_actor_descs is not available; only loaded proxies are updated")
        return
    try:
        guids = []
        for d in lib.get_actor_descs():
            cls = ""
            for prop in ("native_class", "class"):
                try:
                    cls = str(d.get_editor_property(prop))
                    break
                except Exception:
                    continue
            if "Landscape" in cls:
                guids.append(d.get_editor_property("guid"))
        if guids:
            lib.load_actors(guids)
            _log(f"loaded {len(guids)} landscape actors")
    except Exception as exc:
        _warn(f"could not load the landscape proxies ({exc}); only loaded proxies are updated")


def apply(load_all=False, save=True):
    """Puts M_LyrisWorldTerrain_v2 on the world landscape and saves. The material is a shared landscape
    property: proxies that are not loaded now pick it up from the landscape when they next load."""
    if unreal is None:
        raise RuntimeError("apply() runs inside the Unreal editor")
    mat = unreal.load_asset(MAT_PATH) if unreal.EditorAssetLibrary.does_asset_exist(MAT_PATH) else None
    if mat is None:
        mat = build()
    if load_all:
        _load_all_landscape_proxies()
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors = eas.get_all_level_actors()
    landscapes = [a for a in actors if isinstance(a, unreal.Landscape)]
    proxy_cls = getattr(unreal, "LandscapeProxy", None)
    proxies = [a for a in actors if proxy_cls and isinstance(a, proxy_cls) and not isinstance(a, unreal.Landscape)]
    if not landscapes and not proxies:
        _warn("no landscape in the open level: open /Game/Lyris/Maps/Lyris (after the landscape import) and apply() again")
        return False
    done = 0
    for actor in landscapes + proxies:  # the landscape first: proxies inherit its material
        if _set(actor, "landscape_material", mat, quiet=actor not in landscapes):
            done += 1
    _log(f"terrain look v{TERRAIN_LOOK_VERSION}: {MAT_NAME} set on {len(landscapes)} landscape(s) and "
         f"{done - len(landscapes)} of {len(proxies)} loaded proxies")
    if save:
        saver = getattr(unreal, "EditorLoadingAndSavingUtils", None)
        if saver is not None and hasattr(saver, "save_dirty_packages"):
            saver.save_dirty_packages(True, True)
        else:
            unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
        _log("saved the landscape and its proxies")
    return True
