"""Builds the Lyris world map: the real Lyris Minecraft map at full size, 25 x 25 km. This is the game's
only map (T37 retired the Harbor test map).

/Game/Lyris/Maps/Lyris (World Partition) gets: the landscape baked by Art/World/bake_terrain.py
with a painterly auto material driven by its paint layers and slope, the one sea (T17/T19: a
camera-following Gerstner clipmap reading MPC_Sea, out past the horizon from anywhere in the world),
Water plugin lakes and upland rivers, sky and golden-hour lighting, world bounds, the canon landmarks
(lyris_build_landmarks.py), and the player's start in Moonharbor: the boat moored on Lantern Pier, the
dock lamp, the step-ashore point and the harbor mooring at the T37_* markers from Art/World/landmarks.json.

The landscape itself is imported once by hand (Unreal's tiled landscape import is not exposed
to Python in a way we can rely on): build() prepares everything, then logs the exact steps.
Run build() again after the import and it finishes the landscape (material, Nanite, checks).

Rebuilds are incremental. The build is a list of steps (STEP_ORDER), each with its own version in
STEP_VERSIONS, recorded on the map's marker actor (LyrisWorld_v<BUILD_VERSION>). build() redoes only the
steps whose version changed: it loads only that step's streamed actors (by label, through the World
Partition actor descriptors), removes them DELETE_BATCH at a time behind a cancellable progress bar, spawns
the step again and saves. Everything else, and the landscape, is left alone. Each actor a step spawns is
tagged LyrisWorldBuild and LyrisStep_<step>.

init_unreal.py calls build(startup=True) each time the editor opens: that only reports what is out of
date and prints the line to run. Nothing is rebuilt until you run build() yourself.

    import lyris_build_world as w; w.build()                # build what is out of date, or finish
    import lyris_build_world as w; w.build(only=["sea"])    # redo just these steps
    import lyris_build_world as w; w.build(force=True)      # redo every step except the landmarks
    import lyris_build_world as w; w.report()               # what is out of date (changes nothing)
    import lyris_build_world as w; w.import_steps()         # print the landscape import steps again
    import lyris_build_world as w; w.streaming_done()       # after setting the runtime grid by hand

Build from Selection Mode: big edits in Landscape mode froze the editor (playtest 1), so build() refuses
to run while Landscape mode is open.

Landmarks (T36): lyris_build_landmarks.py places the canon landmarks and the new island lamps from
Art/World/landmarks.json as one of the build steps (only when that step's version changes).
lyris_build_landmarks.rebuild() redoes them on purpose, one landmark at a time, for example to snap them
onto a newly imported landscape.

Gameplay actors carry tags other lanes can find them by (so nothing needs a hardcoded position):
    LyrisPlayerBoat      the boat (ALyrisBoat) moored at T37_BoatStart
    LyrisDockPoint       a TargetPoint where you step ashore (also the boat's DockPoint)
    LyrisTideHome        the same TargetPoint: where the tide brings a drifting swimmer home
    LyrisHarborMooring   the Moonharbor ALyrisHarborMooring (T21) at T37_Mooring
    LyrisDockLamp        the dock lamp's parts and light at T37_DockLamp (T3 lamp component goes here)

Coordinates: design/world_map.md (MC X -> UE X, MC Z -> UE Y, UE Z = (MC Y - 63) * 100).
"""

import array
import json
import math
import os
import struct

import unreal

BUILD_VERSION = 6  # 6: pure landscape (landmarks hidden), player start on land, optional terrain look and
                   # foliage steps (T50/T51). 5: incremental rebuilds (per-step versions below); against a v3/v4 map only the sea is new.
                   # 4: sea builds again (struct fix). 3: one sea (T19 clipmap, no Water ocean), boat, dock point,
                   # mooring and dock lamp in Moonharbor, player start on Lantern Pier (T37). 2: landmarks and new
                   # island lamps (T36).
# Each step's own version. To change what one step places, bump that step here AND BUILD_VERSION: w.build()
# then removes and respawns only that step's actors; nothing else in the map is touched.
STEP_VERSIONS = {
    "sky": 1,           # sun, sky atmosphere, sky light, sea mist fog, clouds, storybook grade
    "sea": 1,           # the T19 clipmap sea (v3 maps never got it; v4 made it but recorded no version)
    "water_zone": 1,
    "lakes": 1,
    "rivers": 1,
    "bounds": 1,        # kill Z and the invisible world-edge walls
    "landmarks": 1,     # T36 blockouts; to snap them onto a new landscape: lyris_build_landmarks.rebuild()
    "player_start": 2,  # 2: on land at the Moonharbor spawn while landmarks are hidden (pier is a landmark)
    "boat_dock": 1,
    "landmark_visibility": 1,  # applies LANDMARKS_VISIBLE (hide/show the blockouts; never deletes them)
    "terrain_look": 1,  # T50 lyris_world_terrain (material in the starter-island style), if that module exists
    "foliage": 1,       # T51 lyris_world_foliage (trees, bushes, grass), if that module exists     # boat, dock point, mooring, dock lamp tags (after landmarks: the lamp is a landmark part)
    "streaming": 1,     # World Partition runtime grid (not recorded until it is really set)
}
STEP_ORDER = ["sky", "sea", "water_zone", "lakes", "rivers", "bounds", "landmarks", "player_start", "boat_dock",
              "landmark_visibility", "terrain_look", "foliage", "streaming"]
STEP_TITLES = {"sky": "sky and lighting", "sea": "sea", "water_zone": "water zone", "lakes": "lakes",
               "rivers": "rivers", "bounds": "world bounds", "landmarks": "landmarks", "player_start": "player start",
               "boat_dock": "boat and dock", "landmark_visibility": "landmark visibility",
               "terrain_look": "terrain look", "foliage": "foliage", "streaming": "streaming settings"}
# A map built at v3 or v4 (before per-step records): every actor step was built except the sea. Streaming is
# settings only (no actors) and playtest 1 showed it was never applied, so it is retried as well.
LEGACY_V3_STEPS = {s: v for s, v in STEP_VERSIONS.items()
                   if s in ("sky", "water_zone", "lakes", "rivers", "bounds", "landmarks", "boat_dock")}
STEP_TAG_PREFIX = "LyrisStep_"     # on every actor a step spawns
STEP_VER_TAG = "LyrisStepVer_"     # on the marker: LyrisStepVer_<step>_<version>
MARKER_TAG = "LyrisWorldMarker"
# Pure landscape for now (user decision 2026-10-20, design/DECISIONS.md): the T36 blockouts stay in the map but
# are invisible and have no collision. Set True and bump STEP_VERSIONS["landmark_visibility"] to show them again.
LANDMARKS_VISIBLE = False
VISIBILITY_BATCH = 100             # landmark actors changed per batch
DELETE_BATCH = 100                 # actors removed per destroy_actors call
LOAD_BATCH = 200                   # streamed actors loaded per call
TERRAIN_MAT_VERSION = 1  # versions the terrain material and its textures separately from the actors
MAP_PATH = "/Game/Lyris/Maps/Lyris"
MAT_DIR = "/Game/Lyris/Materials/World"
TEX_DIR = f"/Game/Lyris/Textures/World_v{TERRAIN_MAT_VERSION}"
LAYER_INFO_DIR = f"{MAT_DIR}/LayerInfo"
MARKER_PREFIX = "LyrisWorld_v"
TAG = "LyrisWorldBuild"
LABEL_PREFIX = "LW_"
LANDMARK_LABEL_PREFIX = "LW_LM_"  # lyris_build_landmarks.LABEL_PREFIX
_SKY_NAMES = ("Sun", "SkyAtmosphere", "SkyLight", "SeaMist", "Clouds", "StorybookGrade")

WORLD_DIR = "Art/World"
TILE_DIR = "Art/World/tiles"
MANIFEST = "terrain_manifest.json"
DETAIL_TEXTURES = "Art/TestIsland/textures"  # painted ground textures shared with Harbor
ISLAND_META = "Art/TestIsland/island_meta.json"

# The house palette: Storybook Painterly (sRGB hex, roughness, metallic). Moved here from the retired
# Harbor script (T37); every lane's world art takes its colours from PALETTE and ISLAND_PALETTE.
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
    # Sea (T19): painted bands from trough to crest, a cream foam that matches Salt and Sail.
    "SeaTrough":  ("1F6A80", 0.2, 0.0),
    "Sea":        ("2E8A9C", 0.18, 0.0),
    "SeaCrest":   ("5DB8C2", 0.16, 0.0),
    "SeaFoam":    ("F4EEE0", 0.8, 0.0),
}
ISLAND_PALETTE = {
    "grass": "9DB872", "grass_shade": "6E9061", "sand": "EFE2C4", "path": "CDAE86",
    "rock_lit": "D6BC9F", "rock_shade": "8E7680", "bark": "8A6A5A",
}

# Colours below are the house palette (PALETTE and ISLAND_PALETTE); no new hex values.
LAYER_LOOK = {  # layer: (colour, second colour or None, detail texture, roughness)
    "Grass":    ("9DB872", "6E9061", "grass", 0.92),
    "Forest":   ("6E9061", "4F7558", "grass", 0.95),
    "Sand":     ("EFE2C4", "F1E9DC", "sand", 0.9),
    "Rock":     ("8E7680", "D6BC9F", "cliff", 0.9),   # lavender shade .. warm lit stone
    "Snow":     ("F7EEDC", "EEF3FF", "sand", 0.75),
    "Badlands": ("C8643A", "C8443A", "path", 0.85),   # terracotta with red strata bands
    "Salt":     ("F1E9DC", "F7EEDC", "sand", 0.6),
    "Volcanic": ("36221A", "4A2A1C", "cliff", 0.88),
}
MOONGLASS = "7AC0E6"

# Streaming: landscape proxies of 4 x 4 components (127 quads at ~1.53 m, so ~775 m square),
# a 256 m main runtime grid loaded out to 1.5 km, and HLODs beyond that.
WP_LANDSCAPE_GRID = 4
WP_CELL_M = 256
WP_LOADING_RANGE_M = 1536

LAKE_MIN_AREA_M2 = 2500.0  # matches the bake
WORLD_HALF_FALLBACK_CM = 1250000.0  # MC -12500..12500; the manifest's world_bounds_ue say the same

# Boat materials: ALyrisBoat and ULyrisHullComponent load these by path in C++, so the build makes them
# (the retired Harbor script used to).
PROTO_MAT_DIR = "/Game/Lyris/Materials/Prototype"
PROTO_MATERIALS = ("Wood", "DarkWood", "Sail", "Terracotta", "Gold")

# Gameplay tags other lanes can look the T37 actors up by (see the module notes).
TAG_BOAT = "LyrisPlayerBoat"
TAG_DOCK_POINT = "LyrisDockPoint"
TAG_TIDE_HOME = "LyrisTideHome"
TAG_MOORING = "LyrisHarborMooring"
TAG_DOCK_LAMP = "LyrisDockLamp"

# The T37 dock spot on Lantern Pier's east side, read from the T37_* markers in Art/World/landmarks.json.
# These are the same spots (UE cm, yaw) as T36 placed them, used only if the markers are missing.
DOCK_MARKERS_FALLBACK = {
    "T37_BoatStart": ((14700.0, -240400.0, 0.0), -90.0),
    "T37_DockLamp": ((13950.0, -241400.0, 320.0), 0.0),
    "T37_Mooring": ((14700.0, -239800.0, 0.0), -90.0),
    "T37_StepAshore": ((13900.0, -240400.0, 360.0), 0.0),
}
BOAT_FLOAT_Z = 25.0            # cm above sea level, as on the Harbor map
STAND_Z = 60.0                 # a walker placed at a marker on the deck stands this far above it (capsule clear)
PLAYER_START_FROM_STEP = (-300.0, 1200.0)  # on the pier deck 12 m shoreward of the berth, facing the boat
BOAT_WORLD_RADIUS = 2000000.0  # ALyrisBoat clamps to this distance from the origin; past the world edges (T37 stopgap)
DOCK_LAMP_LIGHT = (8000.0, 1800.0)  # intensity, radius: the Harbor dock lamp's light


def _log(msg):
    unreal.log("[Lyris] " + msg)


def _warn(msg):
    unreal.log_warning("[Lyris] " + msg)


def _project_path(rel):
    return os.path.join(unreal.Paths.project_dir(), rel)


def _linear(hex_str):
    def ch(v):
        c = int(v, 16) / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return unreal.LinearColor(ch(hex_str[0:2]), ch(hex_str[2:4]), ch(hex_str[4:6]), 1.0)


def _srgb_color(hex_str):
    return unreal.Color(r=int(hex_str[0:2], 16), g=int(hex_str[2:4], 16), b=int(hex_str[4:6], 16), a=255)


def _set(obj, prop, value, quiet=False):
    """set_editor_property that logs instead of failing when a property is missing."""
    try:
        obj.set_editor_property(prop, value)
        return True
    except Exception as exc:
        if not quiet:
            _warn(f"could not set {prop} on {obj.get_name()}: {exc}")
        return False


def _editor_world():
    sub = getattr(unreal, "UnrealEditorSubsystem", None)
    if sub is not None:
        return unreal.get_editor_subsystem(sub).get_editor_world()
    return unreal.EditorLevelLibrary.get_editor_world()


def _set_water(actor, prop, value):
    """Sets a Water plugin property on the actor or, failing that, its water body component."""
    if _set(actor, prop, value, quiet=True):
        return True
    comp_cls = getattr(unreal, "WaterBodyComponent", None)
    comp = actor.get_component_by_class(comp_cls) if comp_cls else None
    return bool(comp) and _set(comp, prop, value, quiet=True)


def load_manifest():
    path = _project_path(os.path.join(TILE_DIR, MANIFEST))
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


# ----------------------------------------------------------------------------- material graphs

class _Graph:
    """Small helper for building material graphs from Python (same pattern as the Harbor script)."""

    def __init__(self, name, version=TERRAIN_MAT_VERSION, folder=MAT_DIR):
        self.name = f"M_{name}_v{version}"  # versioned: a rebuild never edits a material in use
        self.path = f"{folder}/{self.name}"
        self.exists = unreal.EditorAssetLibrary.does_asset_exist(self.path)
        if self.exists:
            self.mat = unreal.load_asset(self.path)
        else:
            tools = unreal.AssetToolsHelpers.get_asset_tools()
            self.mat = tools.create_asset(self.name, folder, unreal.Material, unreal.MaterialFactoryNew())
        self.mel = unreal.MaterialEditingLibrary
        self.y = 0
        self._wp = self._nrm = None

    def node(self, cls, **props):
        expr = self.mel.create_material_expression(self.mat, cls, -1200, self.y)
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

    def up(self):
        if self._nrm is None:
            self._nrm = self.node(unreal.MaterialExpressionVertexNormalWS)
        return self.mask(self._nrm, "B")

    def tex(self, texture, uv, linear=False):
        expr = self.node(unreal.MaterialExpressionTextureSample, texture=texture)
        if linear:
            expr.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        self.link(uv, expr, "", "UVs")
        return expr

    def world_uv(self, scale):
        return self.mul(self.mask(self.wp(), "RG"), k=scale)

    def detail(self, sample, luma_mean, strength):
        """Light/dark detail from a texture, centred on 1.0 (its colour is ignored)."""
        lum = self.node(unreal.MaterialExpressionDotProduct)
        self.link(sample, lum, "RGB", "A")
        self.link(self.node(unreal.MaterialExpressionConstant3Vector,
                            constant=unreal.LinearColor(0.299, 0.587, 0.114, 1.0)), lum, "", "B")
        rel = self.mul(lum, k=1.0 / max(luma_mean, 0.05))
        return self.lerp(self.const(1.0), rel, self.const(strength))

    def layer(self, name):
        return self.node(unreal.MaterialExpressionLandscapeLayerSample, parameter_name=name, preview_weight=0.0)

    def out(self, expr, prop, pin=""):
        self.mel.connect_material_property(expr, pin, prop)

    def done(self):
        self.mel.recompile_material(self.mat)
        unreal.EditorAssetLibrary.save_loaded_asset(self.mat)
        return self.mat


def _import_file(filename, destination):
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", filename)
    task.set_editor_property("destination_path", destination)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])


def _detail_textures():
    names = sorted({look[2] for look in LAYER_LOOK.values()})
    src = _project_path(DETAIL_TEXTURES)
    for name in names:
        if not unreal.EditorAssetLibrary.does_asset_exist(f"{TEX_DIR}/{name}"):
            _import_file(os.path.join(src, name + ".png"), TEX_DIR)
    tex = {n: unreal.load_asset(f"{TEX_DIR}/{n}") for n in names}
    missing = [n for n, t in tex.items() if t is None]
    if missing:
        raise RuntimeError(f"detail textures missing after import: {missing}")
    luma = {}
    try:
        with open(_project_path(ISLAND_META)) as f:
            luma = json.load(f).get("texture_luma", {})
    except Exception:
        pass
    return tex, {n: luma.get(n, 0.6) for n in names}


def _material_terrain():
    """Painterly auto material. Each paint layer gives a palette colour with soft light/dark
    texture detail; slope pushes toward rock (lavender shadows, warm tops); badlands get red
    strata bands by height; a very large, gentle tone drift keeps 25 km from looking flat."""
    g = _Graph("LyrisWorldTerrain")
    if g.exists:
        return g.mat
    tex, luma = _detail_textures()
    near = 1.0 / 400.0     # detail repeats every 4 m
    far = 1.0 / 2600.0     # a second, larger scale so the repeat never shows
    up = g.saturate(g.add(g.mul(g.up(), k=0.5), k=0.5))
    total = None
    weights = {}
    for name, (hex_a, hex_b, texture, _rough) in LAYER_LOOK.items():
        w = g.layer(name)
        weights[name] = w
        d = g.mul(g.detail(g.tex(tex[texture], g.world_uv(near)), luma[texture], 0.45),
                  g.detail(g.tex(tex[texture], g.world_uv(far)), luma[texture], 0.35))
        if name == "Rock":
            colour = g.lerp(g.colour(hex_a), g.colour(hex_b), up)
        elif name == "Badlands":
            strata = g.single(unreal.MaterialExpressionFrac, g.mul(g.mask(g.wp(), "B"), k=1.0 / 900.0))
            band = g.saturate(g.mul(g.add(strata, k=-0.62), k=6.0))
            colour = g.lerp(g.colour(hex_a), g.colour(hex_b), band)
        else:
            vary = g.mask(g.tex(tex[texture], g.world_uv(1.0 / 9000.0)), "R")
            colour = g.lerp(g.colour(hex_a), g.colour(hex_b), g.saturate(g.mul(vary, k=0.8)))
        term = g.mul(g.mul(colour, d), w)
        total = term if total is None else g.add(total, term)
    # Anything steeper than ~40 degrees reads as rock whatever the paint says (the bake already
    # paints rock there; this keeps sculpted edits honest too).
    steep = g.saturate(g.add(g.mul(g.up(), k=-6.0), k=4.75))
    rock_hex_a, rock_hex_b, rock_tex, _ = LAYER_LOOK["Rock"]
    rock = g.mul(g.lerp(g.colour(rock_hex_a), g.colour(rock_hex_b), up),
                 g.detail(g.tex(tex[rock_tex], g.world_uv(near)), luma[rock_tex], 0.35))
    base = g.lerp(total, rock, steep)
    # Warm in the light, a touch cooler across the far distance of the world (house style).
    drift = g.mask(g.tex(tex["grass"], g.world_uv(1.0 / 60000.0)), "R")
    tone = g.lerp(g.colour("FFF6E8"), g.colour("EEF3FF"), g.saturate(drift))
    g.out(g.mul(base, tone), unreal.MaterialProperty.MP_BASE_COLOR)
    rough = None
    for name, (_a, _b, _t, r) in LAYER_LOOK.items():
        term = g.mul(weights[name], k=r)
        rough = term if rough is None else g.add(rough, term)
    g.out(rough, unreal.MaterialProperty.MP_ROUGHNESS)
    return g.done()


def _layer_infos():
    """LandscapeLayerInfoObject per paint layer, so the import dialog can use them directly."""
    infos = {}
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    cls = getattr(unreal, "LandscapeLayerInfoObject", None)
    if cls is None:
        _warn("LandscapeLayerInfoObject is not exposed to Python; create layer infos in the import dialog (+)")
        return infos
    for name in LAYER_LOOK:
        path = f"{LAYER_INFO_DIR}/LI_{name}"
        if unreal.EditorAssetLibrary.does_asset_exist(path):
            infos[name] = unreal.load_asset(path)
            continue
        try:
            info = tools.create_asset(f"LI_{name}", LAYER_INFO_DIR, cls, None)
        except Exception as exc:
            _warn(f"could not create layer info {name}: {exc}")
            continue
        if info is None:
            _warn(f"could not create layer info {name}; create it in the import dialog (+)")
            continue
        if not _set(info, "layer_name", name, quiet=True):
            # Newer engines set the layer name through a function instead of the property.
            setter = getattr(info, "set_layer_name", None)
            if setter:
                try:
                    setter(name, True)
                except Exception as exc:
                    _warn(f"layer info {name}: could not set its layer name ({exc})")
        unreal.EditorAssetLibrary.save_loaded_asset(info)
        infos[name] = info
    _log(f"layer infos ready: {', '.join(infos) or 'none'}")
    return infos


# ----------------------------------------------------------------------------- boat materials

def _plain_material(name, hex_str, roughness, metallic, emissive=0.0, folder=PROTO_MAT_DIR):
    """A flat palette material, as the Harbor script made them (the boat loads these by path)."""
    path = f"{folder}/M_{name}"
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        return unreal.load_asset(path)
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    mat = tools.create_asset(f"M_{name}", folder, unreal.Material, unreal.MaterialFactoryNew())
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


def _prototype_materials():
    made = {}
    for name in PROTO_MATERIALS:
        hex_str, rough, metal = PALETTE[name]
        made[name] = _plain_material(name, hex_str, rough, metal)
    made["LampGlass"] = _plain_material("LampGlass", MOONGLASS, 0.2, 0.0, emissive=25.0)
    return made


# ----------------------------------------------------------------------------- the sea (T17 / T19)
# One sea for the whole world. The surface draws the same Gerstner waves the boat and swimmer feel (T17,
# Source/Lyris/World/OCEAN_CONTRACT.md): ULyrisOceanSubsystem writes the wave values into MPC_Sea every
# tick and the material reads them from there, so visuals never drift from physics. Ported from the
# retired Harbor script (T19, Harbor v9) and widened to the whole world by T37.
#
#   MPC_Sea   the contract's names; defaults = the contract's calm waves and the Moonharbor calm zone,
#             so the sea already has its shape before the C++ is compiled.
#   mesh      a generated square clipmap that follows the camera: a 64 m core at 50 cm cells, then
#             SEA_RINGS rings, each twice as coarse and twice as wide, out to about 65 km from the
#             camera, so from anywhere in the 25 km world the sea runs past the horizon. Ring seams are
#             stitched (no cracks). The material slides it under the camera in 32 m steps: the inner
#             six rings stay exactly on their lattice, so the waves never swim; the outer rings are
#             beyond every wave's distance fade (flat water), so their coarser lattice never shows.
#   shading   painted bands from trough to crest, pale shallows and a lapping foam band from a
#             world ground-height map, soft broken foam where crests get steep.

SEA_VERSION = 1
SEA_MPC_PATH = "/Game/Lyris/Materials/MPC_Sea"   # fixed by the ocean contract; the C++ loads it by path
SEA_MAT_DIR = MAT_DIR
SEA_MESH_DIR = f"/Game/Lyris/Meshes/WorldSea_v{SEA_VERSION}"
SEA_TEXTURE_DIR = f"/Game/Lyris/Textures/WorldSeaGround_v{SEA_VERSION}"
SEA_UNIT = 50.0             # cm: cell size of the core grid
SEA_CORE_CELLS = 64         # core half-size in cells (64 x 50 cm = 32 m)
SEA_SNAP_RINGS = 6          # rings that keep their exact lattice as the mesh follows the camera
SEA_RINGS = 11              # all rings: the outer five are flat, distant water out to the horizon
SEA_SNAP = SEA_UNIT * 2 ** SEA_SNAP_RINGS                # 32 m
SEA_HALF = SEA_UNIT * SEA_CORE_CELLS * 2 ** SEA_RINGS    # 65.5 km from the camera to the mesh edge
SEA_BOUNDS_EXTENSION = 2000000.0  # the mesh slides with the camera anywhere in the world (+-12.5 km and more)
SEA_FADE_VERTEX = 8.0       # a wave shrinks away between 8 and 16 wavelengths from the camera in the mesh ...
SEA_FADE_PIXEL = 16.0       # ... and between 16 and 32 in the shading normal (no shimmer, no aliasing)
SEA_DEEP = -40000.0         # cm: ground beyond the ground map counts as open, deep sea

# World ground under the sea, for shallows and shore foam: (file, encoding, metres = v * scale + offset).
# The first that exists is used. A finer baked map is proposed for the Environment lane (see TASKS.md);
# until then the atlas heightmap (25 m per pixel, MC Y = value * 1.5 - 64) gives the coasts.
SEA_GROUND_SOURCES = [
    ("Baked", "Art/World/tiles/World_SeaGround.png", 512.0, -128.0),          # 16-bit, bake height encoding
    ("Atlas", "Art/World/atlas/hmap.png", 255.0 * 1.5, -64.0 - 63.0),        # 8-bit, MC Y -> metres from sea
]

# Contract defaults: (yaw deg, wavelength cm, amplitude cm, steepness) and the home calm zone. The calm
# zone is Moonharbor's bay (MC -200, -2660; 550 m, easing out over 400 m), the same as
# Config/DefaultGame.ini sets for ULyrisOceanSettings::HomeCalmZones.
SEA_DEFAULT_WAVES = [(30.0, 6000.0, 45.0, 0.35), (75.0, 3100.0, 22.0, 0.30),
                     (-20.0, 1700.0, 10.0, 0.25), (120.0, 900.0, 4.0, 0.20)]
SEA_DEFAULT_CALM_ZONES = [(-20000.0, -266000.0, 55000.0, 40000.0)]
SEA_DEFAULT_CALM_SCALE = 0.25

_SEA_INPUTS = ["P", "Cam", "OceanTime", "EngineTime", "SeaLevel", "CalmAmplitudeScale",
               "Wave0", "Wave1", "Wave2", "Wave3", "WaveSteepness",
               "CalmZone0", "CalmZone1", "CalmZone2", "CalmZone3"]


def _struct(cls, **props):
    """Make an unreal struct and set its properties one by one. Some structs (CollectionScalarParameter,
    CollectionVectorParameter, CustomInput) take no constructor arguments in UE 5.8 Python."""
    st = cls()
    for k, v in props.items():
        st.set_editor_property(k, v)
    return st


def _make_sea_collection():
    """MPC_Sea with exactly the contract's parameter names (see OCEAN_CONTRACT.md)."""
    # OceanTime -1 = "no ocean clock yet": the material then runs on engine time (see _sea_hlsl).
    scalars = [("OceanTime", -1.0), ("SeaLevel", 0.0), ("CalmAmplitudeScale", SEA_DEFAULT_CALM_SCALE)]
    vectors = []
    for i, (yaw, length, amp, _steep) in enumerate(SEA_DEFAULT_WAVES):
        rad = math.radians(yaw)
        vectors.append((f"Wave{i}", (math.cos(rad), math.sin(rad), length, amp)))
    vectors.append(("WaveSteepness", tuple(w[3] for w in SEA_DEFAULT_WAVES)))
    for i in range(4):
        zone = SEA_DEFAULT_CALM_ZONES[i] if i < len(SEA_DEFAULT_CALM_ZONES) else (0.0, 0.0, 0.0, 0.0)
        vectors.append((f"CalmZone{i}", zone))

    folder, name = SEA_MPC_PATH.rsplit("/", 1)
    if unreal.EditorAssetLibrary.does_asset_exist(SEA_MPC_PATH):
        mpc = unreal.load_asset(SEA_MPC_PATH)
        have_s = list(mpc.get_editor_property("scalar_parameters"))
        have_v = list(mpc.get_editor_property("vector_parameters"))
        names = [str(p.get_editor_property("parameter_name")) for p in have_s + have_v]
        if names == [n for n, _ in scalars] + [n for n, _ in vectors]:
            # Already right (made by the Harbor script or an earlier build): update only the defaults, in
            # place, so the parameter ids stay and nothing that uses it needs a recompile.
            try:
                for p, (_n, v) in zip(have_s, scalars):
                    p.set_editor_property("default_value", v)
                for p, (_n, v) in zip(have_v, vectors):
                    p.set_editor_property("default_value", unreal.LinearColor(*v))
                mpc.set_editor_property("scalar_parameters", have_s)
                mpc.set_editor_property("vector_parameters", have_v)
                unreal.EditorAssetLibrary.save_loaded_asset(mpc)
            except Exception as exc:
                _warn(f"MPC_Sea: could not update its defaults ({exc}); the C++ overwrites them while playing")
            return mpc
    else:
        tools = unreal.AssetToolsHelpers.get_asset_tools()
        mpc = tools.create_asset(name, folder, unreal.MaterialParameterCollection,
                                 unreal.MaterialParameterCollectionFactoryNew())
    mpc.set_editor_property("scalar_parameters", [
        _struct(unreal.CollectionScalarParameter, parameter_name=n, default_value=v) for n, v in scalars])
    mpc.set_editor_property("vector_parameters", [
        _struct(unreal.CollectionVectorParameter, parameter_name=n, default_value=unreal.LinearColor(*v)) for n, v in vectors])
    unreal.EditorAssetLibrary.save_loaded_asset(mpc)
    return mpc


def _sea_hlsl(fade, body):
    """Custom-node HLSL: evaluates the contract's Gerstner sum at the undisplaced point p, then runs
    `body`. Matches ULyrisOceanSubsystem::EvaluateAt term for term; the only addition is the distance
    fade, which leaves every wave untouched within 8 wavelengths of the camera (72 m for the shortest
    default wave) and only calms waves too small for the far rings to draw."""
    return f"""
float2 snap = floor(Cam.xy / {SEA_SNAP:.1f} + 0.5) * {SEA_SNAP:.1f};
float2 p = P.xy + snap;
// OceanTime is the clock (T17). Its default in MPC_Sea is -1, which only happens before the C++
// runs (it always writes >= 0), so until then the sea runs on engine time instead of standing still.
float t = OceanTime >= 0.0 ? OceanTime : EngineTime;

// Roughness r(p) = 1 - max over used zones of (1 - smoothstep(Radius, Radius + Falloff, |p - Center|)).
float4 zones[4] = {{ CalmZone0, CalmZone1, CalmZone2, CalmZone3 }};
float calm = 0.0;
[unroll] for (int j = 0; j < 4; j++)
{{
    float4 z = zones[j];
    if (z.z > 0.0)
    {{
        float d = length(p - z.xy);
        float u = z.w > 0.0 ? saturate((d - z.z) / z.w) : (d >= z.z ? 1.0 : 0.0);
        calm = max(calm, 1.0 - u * u * (3.0 - 2.0 * u));
    }}
}}
float rough = 1.0 - calm;
float m = lerp(saturate(CalmAmplitudeScale), 1.0, rough);

float4 waves[4] = {{ Wave0, Wave1, Wave2, Wave3 }};
float steep[4] = {{ WaveSteepness.x, WaveSteepness.y, WaveSteepness.z, WaveSteepness.w }};
float camDist = length(p - Cam.xy);
float3 off = float3(0.0, 0.0, 0.0);
float3 n = float3(0.0, 0.0, 1.0);
float jxx = 1.0, jyy = 1.0, jxy = 0.0, ampSum = 0.0;
[unroll] for (int i = 0; i < 4; i++)
{{
    float4 w = waves[i];
    float k = 6.28318530718 / max(w.z, 1.0);
    float omega = k * sqrt(980.0 / k);
    float A0 = max(w.w, 0.0);
    float Q = A0 > 1e-6 ? saturate(steep[i]) / (k * A0 * 4.0) : 0.0;
    float A = A0 * m * saturate(2.0 - camDist / ({fade:.1f} * max(w.z, 1.0)));
    float s, c;
    sincos(k * dot(w.xy, p) - omega * t, s, c);
    float kA = k * A;
    off.xy += w.xy * (Q * A * c);
    off.z += A * s;
    n.x -= w.x * kA * c;
    n.y -= w.y * kA * c;
    n.z -= Q * kA * s;
    jxx -= Q * kA * w.x * w.x * s;
    jyy -= Q * kA * w.y * w.y * s;
    jxy -= Q * kA * w.x * w.y * s;
    ampSum += A0;
}}
n = normalize(n);
{body}
"""


# World Position Offset: move the lattice under the camera, then displace it.
_SEA_OFFSET_BODY = "return float3(snap + off.xy, SeaLevel + off.z - P.z);"

# World-space shading normal (the material uses world-space normals).
_SEA_NORMAL_BODY = "return n;"


def _sea_shade_body(ground_scale_m, ground_offset_m, half_cm):
    """Base colour (rgb) and foam amount (a). Ground (0..1 from the ground map) -> cm from sea level."""
    return f"""
// Value noise for brush-like breakup (macros: a Custom node body cannot hold helper functions).
#define LYRIS_SEA_HASH(q) frac(sin(dot(fmod(q, 512.0), float2(127.1, 311.7))) * 43758.5453)
#define LYRIS_SEA_NOISE(OUT, Q) {{ float2 nq = (Q); float2 ni = floor(nq); float2 nf = frac(nq); nf = nf * nf * (3.0 - 2.0 * nf); OUT = lerp(lerp(LYRIS_SEA_HASH(ni), LYRIS_SEA_HASH(ni + float2(1, 0)), nf.x), lerp(LYRIS_SEA_HASH(ni + float2(0, 1)), LYRIS_SEA_HASH(ni + float2(1, 1)), nf.x), nf.y); }}
float nBrush, nCrest, nShore;
LYRIS_SEA_NOISE(nBrush, p / 900.0 + t * float2(0.010, 0.006))
LYRIS_SEA_NOISE(nCrest, p / 160.0 + t * float2(0.05, 0.03))
LYRIS_SEA_NOISE(nShore, p / 120.0 - t * 0.04)
#undef LYRIS_SEA_NOISE
#undef LYRIS_SEA_HASH

// Painted bands from trough to crest, with a soft brush mottling that drifts with the swell.
float h01 = saturate(0.5 + 0.8 * off.z / max(ampSum, 1.0));
float brush = nBrush - 0.5;
float tone = saturate(h01 + brush * 0.16);
tone = lerp(tone, floor(tone * 4.0 + 0.5) / 4.0, 0.3);
float3 col = lerp(lerp(Trough, Mid, saturate(tone * 2.0)), Crest, saturate(tone * 2.0 - 1.0));

// Paler toward the horizon and at grazing angles.
float fres = pow(1.0 - saturate(dot(n, normalize(CamVec))), 4.0);
col = lerp(col, Crest, fres * 0.45);

// Shallows: water depth over the world's ground, measured at the moving surface.
float inMap = all(abs(p) < {half_cm:.1f}) ? 1.0 : 0.0;  // beyond the world it is open sea
float ground = lerp({SEA_DEEP:.1f}, (Ground * {ground_scale_m:.4f} + ({ground_offset_m:.4f})) * 100.0, inMap);
float depth = SeaLevel + off.z - ground;
col = lerp(col, Shallow, (1.0 - smoothstep(30.0, 300.0, depth)) * 0.85);

// Crest foam where the surface bunches up (Jacobian of the horizontal motion), broken up like brushwork.
float jac = jxx * jyy - jxy * jxy;
float crest = saturate((0.9 - jac) / 0.12) * smoothstep(0.55, 0.8, h01);
float crestFoam = saturate((crest - nCrest * 0.6) * 2.0);

// Shoreline: a soft rim at the waterline plus lapping bands that roll in.
float rim = 1.0 - smoothstep(0.0, 45.0, depth);
float lap = smoothstep(0.62, 0.9, sin(depth * 0.05 - t * 1.4) * 0.5 + 0.5) * (1.0 - smoothstep(30.0, 170.0, depth));
float shore = saturate(rim + lap * 0.8) * saturate(depth * 0.1 + 1.0);
shore *= smoothstep(0.15, 0.55, nShore + rim * 0.5);

float foam = saturate(max(crestFoam, shore));
return float4(lerp(col, Foam, foam), foam);
"""


def _sea_rings():
    """The clipmap lattice. Returns (points, triangles); points are (ix, iy) in SEA_UNIT steps,
    triangles index into points and face up (+Z). Ring seams get a midpoint vertex so the finer
    side's extra vertices are shared, never T-junctions."""
    index, points, tris = {}, [], []

    def vid(key):
        i = index.get(key)
        if i is None:
            i = index[key] = len(points)
            points.append(key)
        return i

    def tri(a, b, c):
        # Face up: in Unreal's left-handed XY that is clockwise seen from above.
        cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        if cross > 0:
            b, c = c, b
        tris.append((vid(a), vid(b), vid(c)))

    core = SEA_CORE_CELLS
    for x in range(-core, core):
        for y in range(-core, core):
            tri((x, y), (x + 1, y), (x + 1, y + 1))
            tri((x, y), (x + 1, y + 1), (x, y + 1))

    for ring in range(1, SEA_RINGS + 1):
        s = 2 ** ring
        inner, outer = core * 2 ** (ring - 1), core * 2 ** ring
        for x in range(-outer, outer, s):
            for y in range(-outer, outer, s):
                if x >= -inner and x + s <= inner and y >= -inner and y + s <= inner:
                    continue  # inside the finer ring
                corners = [(x, y), (x + s, y), (x + s, y + s), (x, y + s)]
                seam = None
                for e in range(4):
                    a, b = corners[e], corners[(e + 1) % 4]
                    if max(abs(a[0]), abs(a[1])) == inner and max(abs(b[0]), abs(b[1])) == inner:
                        seam = e
                if seam is None:
                    tri(corners[0], corners[1], corners[2])
                    tri(corners[0], corners[2], corners[3])
                    continue
                a, b = corners[seam], corners[(seam + 1) % 4]
                mid = ((a[0] + b[0]) // 2, (a[1] + b[1]) // 2)
                c, d = corners[(seam + 2) % 4], corners[(seam + 3) % 4]
                tri(mid, b, c)
                tri(mid, c, d)
                tri(mid, d, a)
    return points, tris


def _write_sea_glb(path):
    """Writes the clipmap as a glTF binary (metres, Y up) without numpy."""
    points, tris = _sea_rings()
    pos, nrm, uv = array.array("f"), array.array("f"), array.array("f")
    for ix, iy in points:
        x, y = ix * SEA_UNIT, iy * SEA_UNIT
        pos.extend((x / 100.0, 0.0, y / 100.0))  # Unreal (x, y, z) cm -> glTF (x, z, y) m
        nrm.extend((0.0, 1.0, 0.0))
        uv.extend((x / 1000.0, y / 1000.0))
    idx = array.array("I")
    for t in tris:
        idx.extend(t)
    half = SEA_HALF / 100.0
    blobs = [pos.tobytes(), nrm.tobytes(), uv.tobytes(), idx.tobytes()]
    views, offset = [], 0
    for i, data in enumerate(blobs):
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(data),
                      "target": 34963 if i == 3 else 34962})
        offset += len(data)  # every blob is a multiple of 4 bytes
    n = len(points)
    doc = {"asset": {"version": "2.0", "generator": "Lyris lyris_build_world.py"},
           "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"name": "SM_WorldSea", "mesh": 0}],
           "meshes": [{"name": "SM_WorldSea", "primitives": [{
               "attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2}, "indices": 3, "material": 0}]}],
           "materials": [{"name": "M_Sea", "pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": 0.2}}],
           "accessors": [
               {"bufferView": 0, "componentType": 5126, "count": n, "type": "VEC3",
                "min": [-half, 0.0, -half], "max": [half, 0.0, half]},
               {"bufferView": 1, "componentType": 5126, "count": n, "type": "VEC3"},
               {"bufferView": 2, "componentType": 5126, "count": n, "type": "VEC2"},
               {"bufferView": 3, "componentType": 5125, "count": len(idx), "type": "SCALAR"}],
           "bufferViews": views, "buffers": [{"byteLength": offset}]}
    js = json.dumps(doc, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    blob = b"".join(blobs)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(blob)))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        f.write(struct.pack("<II", len(blob), 0x004E4942) + blob)
    return len(points), len(tris)


def _assets_of(folder, cls):
    found = []
    for asset_path in unreal.EditorAssetLibrary.list_assets(folder, recursive=True):
        asset = unreal.load_asset(asset_path)
        if isinstance(asset, cls):
            found.append(asset)
    return found


def _sea_work_dir():
    path = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()), "Lyris", "Sea")
    os.makedirs(path, exist_ok=True)
    return path


def _sea_ground_source():
    for key, rel, scale, offset in SEA_GROUND_SOURCES:
        if os.path.exists(_project_path(rel)):
            return key, rel, scale, offset
    return None


def _import_sea_ground(source):
    """Imports the world ground map (shallows and shore foam) as linear, clamped data."""
    key, rel, _scale, _offset = source
    folder = f"{SEA_TEXTURE_DIR}/{key}"
    name = os.path.splitext(os.path.basename(rel))[0]
    path = f"{folder}/{name}"
    if not unreal.EditorAssetLibrary.does_asset_exist(path):
        _import_file(_project_path(rel), folder)
    tex = unreal.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else None
    if tex is None:
        tex = next(iter(_assets_of(folder, unreal.Texture2D)), None)
    if tex is None:
        raise RuntimeError(f"sea ground map {rel} missing after import")
    tcs = unreal.TextureCompressionSettings
    # 16-bit heights keep their precision as half floats; the 8-bit atlas is stored uncompressed like the
    # Harbor's ground map (both sample as linear colour, which the material expects).
    comp = getattr(tcs, "TC_HDR", None) if key == "Baked" else getattr(tcs, "TC_VECTOR_DISPLACEMENTMAP", None)
    _set(tex, "srgb", False)
    if comp is not None:
        _set(tex, "compression_settings", comp)
    _set(tex, "address_x", unreal.TextureAddress.TA_CLAMP)
    _set(tex, "address_y", unreal.TextureAddress.TA_CLAMP)
    unreal.EditorAssetLibrary.save_loaded_asset(tex)
    _log(f"sea ground map: {rel} ({key})")
    return tex


def _import_sea_mesh():
    mesh_path = f"{SEA_MESH_DIR}/SM_WorldSea"
    mesh = unreal.load_asset(mesh_path) if unreal.EditorAssetLibrary.does_asset_exist(mesh_path) else None
    if mesh is None:
        glb = os.path.join(_sea_work_dir(), "world_sea.glb")
        verts, tris = _write_sea_glb(glb)
        _log(f"sea mesh: {verts} vertices, {tris} triangles, {SEA_HALF / 100000.0:.1f} km from the camera to its edge")
        _import_file(glb, SEA_MESH_DIR)
        mesh = next(iter(_assets_of(SEA_MESH_DIR, unreal.StaticMesh)), None)
    if mesh is None:
        raise RuntimeError("sea mesh missing after import")
    # The lattice must land on SEA_UNIT steps in the world, whatever unit scale the importer used
    # (get_bounds includes the bounds extensions, so clear them first).
    mesh.set_editor_property("positive_bounds_extension", unreal.Vector(0.0, 0.0, 0.0))
    mesh.set_editor_property("negative_bounds_extension", unreal.Vector(0.0, 0.0, 0.0))
    extent = mesh.get_bounds().box_extent
    scale = SEA_HALF / max(extent.x, extent.y, 1.0)
    if abs(scale - 1.0) > 0.01:
        _warn(f"sea mesh imported at {max(extent.x, extent.y):.0f} cm half-size; scaling the actor by {scale:.4f}")
    # The waves lift and push the flat mesh, and the material slides it under the camera anywhere in the
    # world, so its bounds must cover far more than the flat grid or it gets culled.
    ext = SEA_BOUNDS_EXTENSION
    mesh.set_editor_property("positive_bounds_extension", unreal.Vector(ext, ext, 1000.0))
    mesh.set_editor_property("negative_bounds_extension", unreal.Vector(ext, ext, 1000.0))
    try:  # plain triangles: no Nanite (WPO each frame), no distance field for a sheet of water
        nanite = mesh.get_editor_property("nanite_settings")
        nanite.set_editor_property("enabled", False)
        mesh.set_editor_property("nanite_settings", nanite)
    except Exception as exc:
        _warn(f"could not turn off Nanite on the sea mesh: {exc}")
    try:
        sme = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        build = sme.get_lod_build_settings(mesh, 0)
        build.set_editor_property("distance_field_resolution_scale", 0.0)
        sme.set_lod_build_settings(mesh, 0, build)
    except Exception as exc:
        _warn(f"could not turn off the sea mesh distance field: {exc}")
    unreal.EditorAssetLibrary.save_loaded_asset(mesh)
    return mesh, scale


def _make_sea_material():
    """Gerstner sea from MPC_Sea: displacement, normal, painted colour and foam (see the notes above)."""
    source = _sea_ground_source()
    key = source[0] if source else "NoGround"
    g = _Graph(f"LyrisSea_{key}", version=SEA_VERSION, folder=SEA_MAT_DIR)
    if g.exists:
        return g.mat
    mpc = _make_sea_collection()
    g.mat.set_editor_property("two_sided", True)  # T20 swimmers see the surface from below
    g.mat.set_editor_property("tangent_space_normal", False)

    def param(name):
        node = g.node(unreal.MaterialExpressionCollectionParameter)
        node.set_editor_property("collection", mpc)
        node.set_editor_property("parameter_name", name)
        return node

    pos = g.node(unreal.MaterialExpressionWorldPosition)  # the flat lattice, before any offset
    pos.set_editor_property("world_position_shader_offset",
                            unreal.WorldPositionIncludedOffsets.WPT_EXCLUDE_ALL_SHADER_OFFSETS)
    shared = {"P": pos, "Cam": g.node(unreal.MaterialExpressionCameraPositionWS),
              "EngineTime": g.node(unreal.MaterialExpressionTime)}
    for name in _SEA_INPUTS:
        if name not in shared:
            shared[name] = param(name)

    def custom(desc, code, out_type, extra=None):
        node = g.node(unreal.MaterialExpressionCustom)
        node.set_editor_property("description", desc)
        node.set_editor_property("output_type", out_type)
        node.set_editor_property("code", code)
        wired = [(n, shared[n], "") for n in _SEA_INPUTS] + list(extra or [])
        node.set_editor_property("inputs", [_struct(unreal.CustomInput, input_name=n) for n, _, _ in wired])
        for n, src, pin in wired:
            g.link(src, node, pin, n)
        return node

    ct = unreal.CustomMaterialOutputType
    offset = custom("SeaOffset", _sea_hlsl(SEA_FADE_VERTEX, _SEA_OFFSET_BODY), ct.CMOT_FLOAT3)
    normal = custom("SeaNormal", _sea_hlsl(SEA_FADE_PIXEL, _SEA_NORMAL_BODY), ct.CMOT_FLOAT3)

    world_min = WORLD_HALF_FALLBACK_CM * -1.0
    world_size = WORLD_HALF_FALLBACK_CM * 2.0
    if source is not None:
        ground_tex = _import_sea_ground(source)
        ground_uv = custom("SeaGroundUV", f"float2 snap = floor(Cam.xy / {SEA_SNAP:.1f} + 0.5) * {SEA_SNAP:.1f};\n"
                           f"return (P.xy + snap - ({world_min:.1f})) / {world_size:.1f};", ct.CMOT_FLOAT2)
        ground = (g.tex(ground_tex, ground_uv, linear=True), "R")
        scale_m, offset_m = source[2], source[3]
    else:
        _warn("no ground map for the sea (Art/World/atlas/hmap.png missing): no shallows or shore foam")
        ground = (g.const(0.0), "")
        scale_m, offset_m = 0.0, SEA_DEEP / 100.0
    colours = [(k, g.colour(PALETTE[name][0]), "") for k, name in
               (("Trough", "SeaTrough"), ("Mid", "Sea"), ("Crest", "SeaCrest"), ("Shallow", "Shallows"),
                ("Foam", "SeaFoam"))]
    shade = custom("SeaShade", _sea_hlsl(SEA_FADE_PIXEL, _sea_shade_body(scale_m, offset_m, WORLD_HALF_FALLBACK_CM)),
                   ct.CMOT_FLOAT4,
                   [("CamVec", g.node(unreal.MaterialExpressionCameraVectorWS), ""), ("Ground", ground[0], ground[1])]
                   + colours)

    colour = g.mask(shade, "RGB")
    foam = g.mask(shade, "A")
    g.out(offset, unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    g.out(normal, unreal.MaterialProperty.MP_NORMAL)
    g.out(colour, unreal.MaterialProperty.MP_BASE_COLOR)
    g.out(g.mul(colour, k=0.05), unreal.MaterialProperty.MP_EMISSIVE_COLOR)  # never muddy in shadow
    g.out(g.lerp(g.const(PALETTE["Sea"][1]), g.const(PALETTE["SeaFoam"][1]), foam),
          unreal.MaterialProperty.MP_ROUGHNESS)
    return g.done()


# ----------------------------------------------------------------------------- actors

class _Builder:
    def __init__(self):
        self.eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        self.step = None  # the build step being run: its actors are tagged LyrisStep_<step>

    def tag(self, actor, *extra):
        names = [TAG] + ([STEP_TAG_PREFIX + self.step] if self.step else []) + list(extra)
        _set(actor, "tags", [unreal.Name(n) for n in names])

    def spawn(self, cls, label, loc=(0, 0, 0), rot=(0, 0, 0), folder="Lighting", always_loaded=True):
        actor = self.eas.spawn_actor_from_class(
            cls, unreal.Vector(*loc), unreal.Rotator(roll=rot[0], pitch=rot[1], yaw=rot[2]))
        if actor is None:
            raise RuntimeError(f"could not spawn {label}")
        actor.set_actor_label(LABEL_PREFIX + label)
        actor.set_folder_path(folder)
        self.tag(actor)
        if always_loaded:
            _set(actor, "is_spatially_loaded", False, quiet=True)
        return actor

    def cube(self, label, loc, scale, folder):
        mesh = unreal.load_asset("/Engine/BasicShapes/Cube")
        actor = self.eas.spawn_actor_from_object(mesh, unreal.Vector(*loc), unreal.Rotator(0, 0, 0))
        actor.set_actor_scale3d(unreal.Vector(*scale))
        actor.set_actor_label(LABEL_PREFIX + label)
        actor.set_folder_path(folder)
        self.tag(actor)
        _set(actor, "is_spatially_loaded", False, quiet=True)
        return actor


def _spline_of(actor):
    getter = getattr(actor, "get_water_spline", None)
    if getter:
        try:
            spline = getter()
            if spline:
                return spline
        except Exception:
            pass
    return actor.get_component_by_class(unreal.SplineComponent)


def _set_spline(actor, points, closed):
    spline = _spline_of(actor)
    if spline is None:
        raise RuntimeError(f"{actor.get_actor_label()} has no spline")
    spline.clear_spline_points(False)
    for p in points:
        spline.add_spline_point(unreal.Vector(*p), unreal.SplineCoordinateSpace.WORLD, False)
    spline.set_closed_loop(closed, False)
    spline.update_spline()
    for fn in ("on_water_body_changed", "update_all"):
        if hasattr(actor, fn):
            try:
                getattr(actor, fn)()
            except Exception:
                pass


def _water_body_common(actor):
    # The bake already carved every bed and basin, so water must not reshape the landscape.
    if not _set_water(actor, "affects_landscape", False):
        _warn(f"{actor.get_actor_label()}: turn off Affects Landscape by hand (property not found)")


# ----------------------------------------------------------------------------- steps, versions and cleanup
# Each build step owns its actors and has its own version. The map's marker (a Note labelled
# LyrisWorld_v<BUILD_VERSION>, always loaded) records the version of every step it was built with as tags
# (LyrisStepVer_<step>_<n>), so a rebuild redoes only the steps whose version changed and leaves every other
# actor alone. Every actor a step spawns is tagged LyrisStep_<step>; actors from builds before v5 are
# matched to their step by label (STEP labels below), which is also how streamed-out actors are found
# without loading them.

class _Cancelled(Exception):
    """The user pressed Cancel on a progress dialog."""


def _ours(actor):
    try:
        if unreal.Name(TAG) in list(actor.get_editor_property("tags")):
            return True
    except Exception:
        pass
    return actor.get_actor_label().startswith(LABEL_PREFIX)


def _label(actor):
    try:
        return actor.get_actor_label()
    except Exception:
        return ""


def _tags(actor):
    try:
        return [str(t) for t in actor.get_editor_property("tags")]
    except Exception:
        return []


def step_of_label(label):
    """The build step that owns an actor with this label (None if it is not one of ours)."""
    if label.startswith(LANDMARK_LABEL_PREFIX):
        return "landmarks"
    if not label.startswith(LABEL_PREFIX):
        return None
    name = label[len(LABEL_PREFIX):]
    if name in _SKY_NAMES:
        return "sky"
    if name == "Sea":
        return "sea"
    if name == "WaterZone":
        return "water_zone"
    if name.startswith("Lake_"):
        return "lakes"
    if name.startswith("River_"):
        return "rivers"
    if name.startswith("WorldEdge_"):
        return "bounds"
    if name.startswith("PlayerStart_"):
        return "player_start"
    if name in ("DockPoint", "Boat") or name.startswith(("Mooring_", "DockLamp_")):
        return "boat_dock"
    return None


def _step_of_actor(actor):
    for t in _tags(actor):
        if t.startswith(STEP_TAG_PREFIX):
            return t[len(STEP_TAG_PREFIX):]
    return step_of_label(_label(actor))


def _actor_descs():
    """World Partition actor descriptors (labels and guids of every actor, loaded or not), or None."""
    lib = getattr(unreal, "WorldPartitionBlueprintLibrary", None)
    if lib is None or not hasattr(lib, "get_actor_descs"):
        return None
    try:
        return lib.get_actor_descs()
    except Exception as exc:
        _warn(f"could not read World Partition actor descriptors ({exc})")
        return None


def load_streamed(label_test, what, descs=None):
    """Loads only the streamed-out actors whose label passes label_test, in batches. Returns how many."""
    lib = getattr(unreal, "WorldPartitionBlueprintLibrary", None)
    descs = _actor_descs() if descs is None else descs
    if not descs or lib is None or not hasattr(lib, "load_actors"):
        return 0
    try:
        guids = [d.get_editor_property("guid") for d in descs if label_test(str(d.get_editor_property("label")))]
    except Exception as exc:
        _warn(f"{what}: could not read actor descriptors ({exc})")
        return 0
    for i in range(0, len(guids), LOAD_BATCH):
        try:
            lib.load_actors(guids[i:i + LOAD_BATCH])
        except Exception as exc:
            _warn(f"{what}: could not load streamed actors ({exc}); load the area in the World Partition window "
                  "if old copies remain")
            break
    if guids:
        _log(f"{what}: loaded {len(guids)} streamed actors")
    return len(guids)


def _alive(actor):
    try:
        return actor is not None and unreal.SystemLibrary.is_valid(actor)
    except Exception:
        return actor is not None


def destroy_in_batches(eas, actors, what):
    """Destroys actors DELETE_BATCH at a time behind a cancellable progress bar, logging each batch.
    One destroy_actors call over thousands of World Partition actors froze the editor (playtest 1)."""
    actors = [a for a in actors if _alive(a)]
    n = len(actors)
    if not n:
        return 0
    with unreal.ScopedSlowTask(n, f"Lyris: removing old {what}") as task:
        task.make_dialog(True)
        for i in range(0, n, DELETE_BATCH):
            if task.should_cancel():
                raise _Cancelled(f"cancelled while removing {what} ({i}/{n} removed)")
            chunk = [a for a in actors[i:i + DELETE_BATCH] if _alive(a)]
            task.enter_progress_frame(len(actors[i:i + DELETE_BATCH]), f"{what}: {min(i + DELETE_BATCH, n)}/{n}")
            if chunk:
                eas.destroy_actors(chunk)
            _log(f"{what}: removed {min(i + DELETE_BATCH, n)}/{n}")
    return n


def _clear_step(step, eas, descs=None):
    """Loads and removes only this step's actors from earlier builds."""
    what = STEP_TITLES[step]
    load_streamed(lambda label: step_of_label(label) == step, what, descs)
    old = [a for a in eas.get_all_level_actors() if _step_of_actor(a) == step]
    return destroy_in_batches(eas, old, what)


def _clear_leftovers(eas, descs=None):
    """Maps built before v3 had actors no current step owns (the Water plugin ocean): remove those."""
    def leftover(label):
        return label.startswith(LABEL_PREFIX) and step_of_label(label) is None
    load_streamed(leftover, "leftovers from old builds", descs)
    old = [a for a in eas.get_all_level_actors()
           if leftover(_label(a)) and MARKER_TAG not in _tags(a) and not _label(a).startswith(MARKER_PREFIX)]
    return destroy_in_batches(eas, old, "leftovers from old builds")


def _marker(eas):
    for actor in eas.get_all_level_actors():
        if _label(actor).startswith(MARKER_PREFIX):
            return actor
    return None


def _version_of(marker):
    if marker is None:
        return 0
    try:
        return int(_label(marker)[len(MARKER_PREFIX):])
    except ValueError:
        return 0


def _current_version(eas):
    return _version_of(_marker(eas))


def _recorded_steps(marker):
    """{step: version} the map was built with. Maps built at v3/v4 have no record: everything but the sea
    was built (the v3 sea step failed; v4 fixed it but recorded nothing), so only the sea is redone."""
    found = {}
    for t in _tags(marker) if marker is not None else []:
        if t.startswith(STEP_VER_TAG):
            step, _, ver = t[len(STEP_VER_TAG):].rpartition("_")
            try:
                found[step] = int(ver)
            except ValueError:
                pass
    if found:
        return found
    if _version_of(marker) in (3, 4):
        return dict(LEGACY_V3_STEPS)
    return {}


def _record_step(marker, step):
    tags = [t for t in _tags(marker) if not t.startswith(f"{STEP_VER_TAG}{step}_")]
    tags.append(f"{STEP_VER_TAG}{step}_{STEP_VERSIONS[step]}")
    _set(marker, "tags", [unreal.Name(t) for t in tags])


def _record_all(marker, recorded):
    """Writes the full record (so a migrated v3/v4 map keeps its implied steps once it is saved)."""
    tags = [t for t in _tags(marker) if not t.startswith(STEP_VER_TAG)]
    tags += [f"{STEP_VER_TAG}{s}_{v}" for s, v in sorted(recorded.items())]
    _set(marker, "tags", [unreal.Name(t) for t in tags])


def outdated_steps(recorded):
    return [s for s in STEP_ORDER if recorded.get(s, 0) != STEP_VERSIONS[s]]


def _landscape(eas):
    for actor in eas.get_all_level_actors():
        if isinstance(actor, unreal.Landscape):
            return actor
    return None


def _landscape_proxies(eas):
    return [a for a in eas.get_all_level_actors() if isinstance(a, unreal.LandscapeProxy)]


def leave_editor_modes(eas=None):
    """Big deletes while Landscape mode is active froze the editor (playtest 1). Switches to the default
    (Selection) mode if this engine exposes that to Python; otherwise refuses to go on while Landscape
    mode is visibly active and says how to switch by hand. Returns True when it is safe to build."""
    eas = eas or unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    candidates = []
    les_cls = getattr(unreal, "LevelEditorSubsystem", None)
    if les_cls is not None:
        candidates.append(unreal.get_editor_subsystem(les_cls))
    for name in ("EditorModeManagerSubsystem", "EditorModeSubsystem"):  # not in 5.8 as far as we know; cheap to try
        cls = getattr(unreal, name, None)
        if cls is not None:
            try:
                candidates.append(unreal.get_editor_subsystem(cls))
            except Exception:
                pass
    for owner in candidates:
        for fn_name in ("activate_default_mode", "editor_activate_default_mode"):
            fn = getattr(owner, fn_name, None)
            if fn is None:
                continue
            try:
                fn()
                _log("switched the editor to Selection Mode for the build")
                return True
            except Exception as exc:
                _warn(f"could not switch editor mode ({exc})")
    # No Python API: the Landscape mode's gizmo actor exists while that mode is open.
    gizmo = getattr(unreal, "LandscapeGizmoActiveActor", None)
    if gizmo is not None and any(isinstance(a, gizmo) for a in eas.get_all_level_actors()):
        unreal.log_error("[Lyris] The editor is in Landscape mode. Switch to Selection Mode first (the mode "
                         "dropdown at the top left of the main toolbar > Selection, or Shift+1), then run "
                         "w.build() again. If you are sure you are already in Selection Mode: "
                         "w.build(check_mode=False)")
        return False
    _log("tip: build from Selection Mode (Shift+1); Landscape or Foliage mode makes big edits very slow")
    return True


# ----------------------------------------------------------------------------- the manual import

def import_steps(manifest=None):
    """Logs the short, exact steps for the one manual part: the tiled landscape import."""
    m = manifest or load_manifest()
    if m is None:
        _warn("no terrain bake found. First run, in a terminal at the project folder:\n"
              "    python Art/World/bake_terrain.py --workers 2\n"
              "then run lyris_build_world.build() again.")
        return
    tiles = os.path.join(unreal.Paths.convert_relative_path_to_full(_project_path(TILE_DIR)))
    sx, sy, sz = m["scale"]
    cx, cy, cz = m["location_centre"]
    comps = m.get("components_x") or "?"
    lines = [
        "LANDSCAPE IMPORT (once, by hand). The map is open; do this in it:",
        " 1. Selection Mode dropdown > Landscape. Manage tab > New > Import from File.",
        f" 2. Heightmap File: {os.path.join(tiles, m['first_heightmap'])}  (answer Yes to 'tiled image').",
        "    Leave Flip Y Axis OFF.",
        f" 3. Material: {MAT_DIR}/M_LyrisWorldTerrain_v{TERRAIN_MAT_VERSION}",
        " 4. Layers (one row each): pick the layer info from " + LAYER_INFO_DIR
        + " (or press + > Weight-Blended), then its Weightmap File:",
    ]
    for layer in m["layers"]:
        lines.append(f"      {layer['name']:9s} {os.path.join(tiles, layer['first'])}")
    lines += [
        f" 5. Location X {cx:.0f}  Y {cy:.0f}  Z {cz:.0f}   Rotation 0 0 0",
        f"    Scale X {sx:.4f}  Y {sy:.4f}  Z {sz:.1f}",
        f" 6. Section Size 127x127 Quads, Sections Per Component 1x1, Number of Components {comps} x {comps}",
        f"    (Overall Resolution {m['total_resolution']} x {m['total_resolution']}).",
        f" 7. World Partition Grid Size {WP_LANDSCAPE_GRID}. Enable Edit Layers ON. Press Import (takes minutes).",
        " 8. Python: import lyris_build_world as w; w.build()   (applies material and settings, saves)",
        " 9. Build > Build HLODs, then Build > Build Minimap.",
        "If Import stays greyed out with 'Weightmap import resolution isn't same as Heightmap' (UE-241268):",
        "    untick each weightmap, untick the heightmap, tick the weightmaps again, then the heightmap.",
        "If the result shows one tile repeated (reported for 5.7+ World Partition imports): import into a",
        "    new Basic (non World Partition) level instead, then Tools > Convert Level to World Partition.",
    ]
    for line in lines:
        _log(line)


# ----------------------------------------------------------------------------- build

def _map_is_open():
    try:
        world = _editor_world()
        return world is not None and world.get_path_name().split(".")[0] == MAP_PATH
    except Exception:
        return False


def _open_or_create_map(les):
    if unreal.EditorAssetLibrary.does_asset_exist(MAP_PATH):
        if _map_is_open():
            return True  # the editor opened it already (EditorStartupMap); do not reload it
        return les.load_level(MAP_PATH)
    try:
        ok = les.new_level(MAP_PATH, True)  # (asset_path, is_partitioned_world)
    except TypeError:
        _warn("this engine's new_level() has no World Partition flag; creating a plain level. "
              "Convert it with Tools > Convert Level to World Partition before importing the landscape.")
        ok = les.new_level(MAP_PATH)
    if ok:
        _log(f"created World Partition map {MAP_PATH}")
    return ok


def _is_partitioned():
    try:
        return bool(_editor_world().get_world_settings().get_editor_property("world_partition"))
    except Exception:
        return None


def _dock_spots():
    """The T37 dock spot on Lantern Pier: {marker: ((x, y, z) UE cm, yaw)} from landmarks.json."""
    spots = {}
    try:
        import lyris_build_landmarks
        spots = lyris_build_landmarks.markers("T37_")
    except Exception as exc:
        _warn(f"could not read the T37 markers from landmarks.json ({exc})")
    for name, value in DOCK_MARKERS_FALLBACK.items():
        if name not in spots:
            _warn(f"marker {name} missing from Art/World/landmarks.json; using the T36 spot")
            spots[name] = value
    return spots


def _add_tags(actor, *names):
    try:
        tags = list(actor.get_editor_property("tags"))
    except Exception:
        tags = []
    for n in names:
        if unreal.Name(n) not in tags:
            tags.append(unreal.Name(n))
    _set(actor, "tags", tags)


def _save(les):
    try:
        les.save_current_level()
    except Exception as exc:
        _warn(f"could not save the map ({exc}); File > Save All")


def _make_marker(b):
    b.step = None
    marker = b.spawn(unreal.Note, "Marker", (0, 0, 50000), folder="Gameplay")
    marker.set_actor_label(f"{MARKER_PREFIX}0")  # the version is set once every step is current
    _add_tags(marker, MARKER_TAG)
    _set(marker, "text", "Built by Content/Python/lyris_build_world.py from Art/World. Its tags record each "
                         "build step's version. Edits to actors a step places are lost when that step is "
                         "rebuilt; the landscape is kept.", quiet=True)
    return marker


def _state(eas):
    marker = _marker(eas)
    recorded = _recorded_steps(marker)
    return marker, _version_of(marker), recorded


def report():
    """What the editor runs at startup (init_unreal.py): says what is out of date and changes nothing."""
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    run = "import lyris_build_world as w; w.build()"
    if not unreal.EditorAssetLibrary.does_asset_exist(MAP_PATH):
        _log(f"the Lyris world map is not built on this PC yet. In the Output Log (Python), run:  {run}")
        return
    if not _map_is_open():
        _log(f"the open level is not {MAP_PATH}; open it to check its build, or run:  {run}")
        return
    marker, version, recorded = _state(eas)
    todo = outdated_steps(recorded)
    if not todo:
        if version != BUILD_VERSION:
            _log(f"World map steps are all current (map marked v{version}); w.build() marks it v{BUILD_VERSION}")
        else:
            _log(f"World map is up to date (v{version})")
        if _landscape(eas) is None:
            _log("the landscape is not imported yet: import_steps() prints how")
        if streaming_is_right() is False:
            streaming_manual_steps()
        return
    keep = [STEP_TITLES[s] for s in STEP_ORDER if s not in todo]
    _warn(f"World map v{version} is older than the build scripts (v{BUILD_VERSION}). Nothing was changed. "
          f"Steps to redo: {', '.join(STEP_TITLES[s] for s in todo)}"
          + (f"; kept as they are: {', '.join(keep)}" if keep else ""))
    _warn(f"To update, switch to Selection Mode (Shift+1) and run in the Output Log (Python):  {run}")
    if "streaming" in todo and streaming_is_right() is False:
        streaming_manual_steps()


def build(force=False, only=None, startup=False, check_mode=True):
    """Builds what is out of date, one step at a time, and finishes an imported landscape.

    force=True   redo every step except the landmarks (those: lyris_build_landmarks.rebuild())
    only=[...]   redo just these steps, e.g. only=["sea"] (names in STEP_ORDER)
    startup=True only report (what init_unreal.py does when the editor opens); never rebuilds
    check_mode   refuse to run while Landscape mode is active (big edits froze the editor there)
    """
    if startup:
        report()
        return
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    manifest = load_manifest()
    if manifest is None:
        import_steps(None)
        return
    if manifest.get("preview"):
        _warn("the terrain bake is a PREVIEW (low resolution). Rebake at full size before importing: "
              "python Art/World/bake_terrain.py --workers 2")
    if only is not None:
        only = [only] if isinstance(only, str) else list(only)
        unknown = [s for s in only if s not in STEP_VERSIONS]
        if unknown:
            unreal.log_error(f"[Lyris] unknown build steps {unknown}; the steps are: {', '.join(STEP_ORDER)}")
            return

    if not _open_or_create_map(les):
        unreal.log_error("[Lyris] could not open or create " + MAP_PATH)
        return
    if _is_partitioned() is False:
        _warn(f"{MAP_PATH} is not a World Partition map; streaming settings will not apply")
    if check_mode and not leave_editor_modes(eas):
        return

    marker, version, recorded = _state(eas)  # the marker is always loaded
    if only is not None:
        steps = [s for s in STEP_ORDER if s in only]
    elif force:
        steps = [s for s in STEP_ORDER if s != "landmarks"]
        if recorded.get("landmarks", 0) != STEP_VERSIONS["landmarks"]:
            steps = list(STEP_ORDER)  # never built: place them
    else:
        steps = outdated_steps(recorded)
    if "streaming" not in steps and streaming_is_right() is False:
        steps.append("streaming")  # settings only: re-apply whenever the runtime grid is not what we want
    landscape = _landscape(eas)
    m = manifest
    half = m["world_bounds_ue"][1]
    b = _Builder()

    try:  # idempotent: makes only the materials that do not exist yet
        _material_terrain()
        _layer_infos()
        _prototype_materials()
    except Exception as exc:
        _warn(f"could not make the world materials: {exc}")

    if not steps:
        if marker is not None and version != BUILD_VERSION:
            _record_all(marker, recorded)
            marker.set_actor_label(f"{MARKER_PREFIX}{BUILD_VERSION}")
        if landscape is None:
            _log(f"World map v{_version_of(marker)} is built; the landscape is not imported yet")
            import_steps(manifest)
            _save(les)
            return
        _finish_landscape(landscape, eas, manifest)
        _save(les)
        _log(f"World map is up to date (v{_version_of(marker)})")
        if streaming_is_right() is False:
            streaming_manual_steps()
        return

    kept = [STEP_TITLES[s] for s in STEP_ORDER if s not in steps]
    _log(f"building World map (v{version} -> v{BUILD_VERSION}): {', '.join(STEP_TITLES[s] for s in steps)}"
         + (f"; keeping {', '.join(kept)}" if kept else ""))
    if marker is None:
        marker = _make_marker(b)
    elif recorded and not any(t.startswith(STEP_VER_TAG) for t in _tags(marker)):
        _record_all(marker, recorded)  # migrate a v3/v4 marker to per-step records
    dock = _dock_spots()
    descs = _actor_descs()  # labels only; nothing is loaded until a step needs its own actors

    def sky():
        sun = b.spawn(unreal.DirectionalLight, "Sun", (0, 0, 100000), rot=(0, -14, 215))  # golden hour
        sc = sun.get_component_by_class(unreal.DirectionalLightComponent)
        sc.set_editor_property("intensity", 5.0)
        sc.set_editor_property("light_color", _srgb_color("FFE3BE"))
        sc.set_editor_property("atmosphere_sun_light", True)
        _set(sc, "dynamic_shadow_distance_movable_light", 30000.0, quiet=True)
        _set(sc, "far_shadow_cascade_count", 2, quiet=True)
        _set(sc, "far_shadow_distance", 300000.0, quiet=True)  # mountains shade valleys from afar
        b.spawn(unreal.SkyAtmosphere, "SkyAtmosphere")
        skylight = b.spawn(unreal.SkyLight, "SkyLight", (0, 0, 80000))
        slc = skylight.get_component_by_class(unreal.SkyLightComponent)
        slc.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
        slc.set_editor_property("real_time_capture", True)
        slc.set_editor_property("intensity", 1.4)
        fog = b.spawn(unreal.ExponentialHeightFog, "SeaMist", (0, 0, 0))
        fc = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
        fc.set_editor_property("fog_density", 0.0035)  # thinner than Harbor: 25 km of view
        fc.set_editor_property("fog_height_falloff", 0.05)
        fc.set_editor_property("fog_inscattering_luminance", _linear("D8E4EC"))
        b.spawn(unreal.VolumetricCloud, "Clouds")
        ppv = b.spawn(unreal.PostProcessVolume, "StorybookGrade")
        ppv.set_editor_property("unbound", True)
        settings = ppv.get_editor_property("settings")
        settings.set_editor_property("override_auto_exposure_bias", True)
        settings.set_editor_property("auto_exposure_bias", 0.3)
        settings.set_editor_property("override_color_saturation", True)
        settings.set_editor_property("color_saturation", unreal.Vector4(1.0, 1.02, 0.98, 1.04))
        settings.set_editor_property("override_color_gain_shadows", True)
        settings.set_editor_property("color_gain_shadows", unreal.Vector4(0.92, 0.94, 1.08, 1.0))
        settings.set_editor_property("override_color_gain_highlights", True)
        settings.set_editor_property("color_gain_highlights", unreal.Vector4(1.04, 1.01, 0.96, 1.0))
        ppv.set_editor_property("settings", settings)

    def water_zone():
        if not hasattr(unreal, "WaterZone"):
            raise RuntimeError("Water plugin classes not found; enable the Water plugin")
        zone = b.spawn(unreal.WaterZone, "WaterZone", (0, 0, 0), folder="Water")
        if not _set(zone, "zone_extent", unreal.Vector2D(2 * half, 2 * half), quiet=True):
            _warn("WaterZone: set Zone Extent to cover the world by hand "
                  f"({2 * half:.0f} x {2 * half:.0f})")
        _set(zone, "render_target_resolution", unreal.IntPoint(4096, 4096), quiet=True)

    def sea():
        # The one sea (T17/T19): a Gerstner clipmap that follows the camera, drawn from MPC_Sea, which the
        # ocean subsystem writes. Boats, swimmers and the hull read the same waves in C++; there is no
        # Water plugin ocean (lakes and rivers still use the Water plugin).
        _make_sea_collection()
        mesh, scale = _import_sea_mesh()
        actor = b.eas.spawn_actor_from_object(mesh, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
        actor.set_actor_scale3d(unreal.Vector(scale, scale, 1.0))
        actor.set_actor_label(LABEL_PREFIX + "Sea")
        actor.set_folder_path("Water")
        b.tag(actor)
        _set(actor, "is_spatially_loaded", False, quiet=True)  # it follows the camera everywhere
        comp = actor.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_material(0, _make_sea_material())
        comp.set_collision_profile_name("NoCollision")
        comp.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        # The mesh is re-centred on each camera (shadow views included), so it must not cast shadows.
        comp.set_editor_property("cast_shadow", False)
        _set(comp, "affect_distance_field_lighting", False, quiet=True)

    def lakes():
        made = 0
        for i, lake in enumerate(m.get("lakes", [])):
            if lake["area_m2"] < LAKE_MIN_AREA_M2 or len(lake["outline_ue"]) < 3:
                continue
            z = lake["level_m"] * 100.0
            cx, cz = lake["centre_mc"]
            actor = b.spawn(unreal.WaterBodyLake, f"Lake_{i:03d}", (cx * 100.0, cz * 100.0, z), folder="Water/Lakes",
                            always_loaded=False)
            _set_spline(actor, [(x, y, z) for x, y in lake["outline_ue"]], closed=True)
            _water_body_common(actor)
            made += 1
        _log(f"{made} lakes")

    def rivers():
        made = 0
        for i, river in enumerate(m.get("rivers", [])):
            pts = river["points_ue"]
            if len(pts) < 2:
                continue
            actor = b.spawn(unreal.WaterBodyRiver, f"River_{i:03d}", tuple(pts[0]), folder="Water/Rivers",
                            always_loaded=False)
            _set_spline(actor, [tuple(p) for p in pts], closed=False)
            _water_body_common(actor)
            made += 1
        _log(f"{made} upland river reaches (sea-level rivers are covered by the sea). River width "
             "uses the Water plugin default; per-point width needs the spline metadata (T36 follow-up)")

    def bounds():
        ws = _editor_world().get_world_settings()
        _set(ws, "enable_world_bounds_checks", True, quiet=True)
        _set(ws, "kill_z", -20000.0, quiet=True)  # 200 m below the sea; the deepest pit is ~102 m
        # Invisible walls just inside the world edge, 1 km tall, so nobody sails off the map.
        t = 1000.0  # 10 m thick
        span = 2 * half / 100.0
        for name, loc, scale in (("North", (0, -half, 40000), (span, t / 100.0, 1000)),
                                 ("South", (0, half, 40000), (span, t / 100.0, 1000)),
                                 ("West", (-half, 0, 40000), (t / 100.0, span, 1000)),
                                 ("East", (half, 0, 40000), (t / 100.0, span, 1000))):
            wall = b.cube(f"WorldEdge_{name}", loc, scale, "Bounds")
            comp = wall.get_component_by_class(unreal.StaticMeshComponent)
            comp.set_visibility(False)
            comp.set_editor_property("cast_shadow", False)
            comp.set_collision_profile_name("BlockAll")
            wall.set_actor_hidden_in_game(True)

    def player_start():
        # T37: on Lantern Pier's deck, a few steps shoreward of the moored boat and facing it (the Harbor map
        # started the player on its dock the same way). The server's spawn in Market Square is in the manifest.
        if not LANDMARKS_VISIBLE:
            # The pier is a hidden landmark: start on real ground at the server's Moonharbor spawn instead.
            sx, sy, sz = m["spawn"]["ue"]
            b.spawn(unreal.PlayerStart, "PlayerStart_Moonharbor", (sx, sy, sz + 150.0 + STAND_Z),
                    rot=(0, 0, m["spawn"].get("yaw", -90.0)), folder="Gameplay")
            return
        (x, y, z), _yaw = dock["T37_StepAshore"]
        dx, dy = PLAYER_START_FROM_STEP
        b.spawn(unreal.PlayerStart, "PlayerStart_LanternPier", (x + dx, y + dy, z + STAND_Z), rot=(0, 0, -90.0),
                folder="Gameplay")

    def boat_dock():
        # The boat, the step-ashore point, the mooring and the dock lamp, at the T37 markers on Lantern Pier.
        (sx, sy, sz), _ = dock["T37_StepAshore"]
        step = (sx, sy, sz + STAND_Z)
        point = b.spawn(unreal.TargetPoint, "DockPoint", step, folder="Gameplay/Dock")
        _add_tags(point, TAG_DOCK_POINT, TAG_TIDE_HOME)

        boat_cls = getattr(unreal, "LyrisBoat", None)
        if boat_cls is None:
            _warn("LyrisBoat class not found; build the C++ module and reopen the editor, then "
                  "w.build(only=['boat_dock'])")
        else:
            (bx, by, bz), byaw = dock["T37_BoatStart"]
            boat = b.spawn(boat_cls, "Boat", (bx, by, bz + BOAT_FLOAT_Z), rot=(0, 0, byaw), folder="Gameplay/Boat")
            _add_tags(boat, TAG_BOAT)
            if not _set(boat, "dock_point", unreal.Vector(*step)):
                _warn("Boat: set Dock Point by hand to the LW_DockPoint TargetPoint's location")
            # ALyrisBoat turns back at WorldRadius from the world origin (the Harbor island). Moonharbor is
            # 2.4 km from the origin, so widen it past the world edges until Sailing reads the world bounds.
            if not _set(boat, "world_radius", BOAT_WORLD_RADIUS):
                _warn(f"Boat: set World Radius by hand to {BOAT_WORLD_RADIUS:.0f}")

        mooring_cls = getattr(unreal, "LyrisHarborMooring", None)
        if mooring_cls is None:
            _warn("LyrisHarborMooring class not found (T21 not compiled yet); swamped boats return to their start")
        else:
            (mx, my, mz), myaw = dock["T37_Mooring"]
            mooring = b.spawn(mooring_cls, "Mooring_Moonharbor", (mx, my, mz), rot=(0, 0, myaw), folder="Gameplay/Dock")
            _add_tags(mooring, TAG_MOORING)
            text_cls = getattr(unreal, "Text", None)
            if text_cls is not None:
                _set(mooring, "harbor_name", text_cls("Moonharbor"))

        _dock_lamp(b, eas, dock["T37_DockLamp"])

    def streaming():
        _streaming_settings()

    def landmarks():
        # Canon landmarks and new island lamps from Art/World/landmarks.json (T36), replaced one landmark at a
        # time (only that landmark's actors are loaded and removed). Placed after the landscape exists they
        # trace onto it. To redo them on purpose (e.g. to snap onto a new landscape): lyris_build_landmarks.rebuild()
        import importlib
        import lyris_build_landmarks
        importlib.reload(lyris_build_landmarks)
        if lyris_build_landmarks.load_landmarks() is None:
            raise RuntimeError(f"{lyris_build_landmarks.LANDMARKS_JSON} is missing")
        if lyris_build_landmarks.place(m, descs=descs) is None:
            raise _Cancelled("cancelled while placing landmarks")
        tag_dock_lamp(eas)  # the dock lamp is a landmark part; keep its gameplay tag

    def landmark_visibility():
        set_landmarks_visible(LANDMARKS_VISIBLE, eas, descs)

    def _optional_module(name, *calls):
        import importlib
        try:
            mod = importlib.import_module(name)
        except ImportError:
            _log(f"{name}.py is not in this project yet; skipping (it is optional)")
            return
        importlib.reload(mod)
        for call in calls:
            getattr(mod, call)()

    def terrain_look():
        _optional_module("lyris_world_terrain", "build", "apply")

    def foliage():
        _optional_module("lyris_world_foliage", "build")

    fns = {"landmark_visibility": landmark_visibility, "terrain_look": terrain_look, "foliage": foliage,
           "sky": sky, "sea": sea, "water_zone": water_zone, "lakes": lakes, "rivers": rivers, "bounds": bounds,
           "landmarks": landmarks, "player_start": player_start, "boat_dock": boat_dock, "streaming": streaming}

    if version and version < 3:
        try:
            _clear_leftovers(eas, descs)
        except _Cancelled as exc:
            _warn(f"{exc}; nothing else was changed. Run w.build() again to continue")
            return

    done, failed = [], []
    for step in steps:
        title = STEP_TITLES[step]
        b.step = step
        try:
            if step not in ("landmarks", "landmark_visibility", "terrain_look", "foliage", "streaming"):
                # landmarks replace themselves one landmark at a time; the others own no step actors here
                _clear_step(step, eas, descs)
            fns[step]()
        except _Cancelled as exc:
            _warn(f"{exc}. Stopped; finished steps are saved. Run w.build() again to continue")
            break
        except Exception as exc:  # keep going so one failure doesn't stop the rest
            _warn(f"could not build {title}: {exc}")
            failed.append(step)
            continue
        _record_step(marker, step)
        recorded[step] = STEP_VERSIONS[step]
        done.append(step)
        _save(les)  # each finished step is kept even if a later one is cancelled or the editor is closed
        _log(f"built {title}")
    b.step = None

    left = outdated_steps(recorded)
    if not left:
        marker.set_actor_label(f"{MARKER_PREFIX}{BUILD_VERSION}")
    if landscape is not None:
        _finish_landscape(landscape, eas, manifest)
    _save(les)
    unreal.EditorAssetLibrary.save_directory("/Game/Lyris", only_if_is_dirty=True, recursive=True)
    if "streaming" in left or streaming_is_right() is False:
        streaming_manual_steps()
    if left:
        _warn(f"World map not finished: {', '.join(STEP_TITLES[s] for s in left)} still to do"
              + (f" ({', '.join(STEP_TITLES[s] for s in failed)} failed: see the warnings above)" if failed else "")
              + ". Run w.build() again")
    else:
        _log(f"World map v{BUILD_VERSION} ready at {MAP_PATH} (rebuilt: {', '.join(STEP_TITLES[s] for s in done)})")
    if landscape is None:
        import_steps(manifest)


def set_landmarks_visible(visible, eas=None, descs=None):
    """Shows or hides every T36 landmark blockout (label prefix LW_LM_), in batches behind a cancellable
    progress bar. Hidden means: not rendered in the editor or the game and no collision. Nothing is deleted.
    Saved with the map, so it persists. Returns how many actors were changed."""
    eas = eas or unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    what = "landmarks (show)" if visible else "landmarks (hide)"
    load_streamed(lambda label: label.startswith(LANDMARK_LABEL_PREFIX), what, descs)
    actors = [a for a in eas.get_all_level_actors() if _label(a).startswith(LANDMARK_LABEL_PREFIX)]
    n = len(actors)
    if not n:
        _log(f"{what}: no landmark actors found")
        return 0
    with unreal.ScopedSlowTask(n, f"Lyris: {what}") as task:
        task.make_dialog(True)
        for i in range(0, n, VISIBILITY_BATCH):
            if task.should_cancel():
                raise _Cancelled(f"cancelled while changing {what} ({i}/{n} done)")
            chunk = actors[i:i + VISIBILITY_BATCH]
            task.enter_progress_frame(len(chunk), f"{what}: {min(i + VISIBILITY_BATCH, n)}/{n}")
            for actor in chunk:
                if not _alive(actor):
                    continue
                try:
                    actor.modify()
                except Exception:
                    pass
                actor.set_actor_hidden_in_game(not visible)
                actor.set_actor_enable_collision(visible)
                for comp in actor.get_components_by_class(unreal.PrimitiveComponent):
                    try:
                        comp.modify()
                    except Exception:
                        pass
                    comp.set_visibility(visible, True)
                    comp.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS if visible
                                               else unreal.CollisionEnabled.NO_COLLISION)
                    if hasattr(comp, "set_cast_shadow"):
                        comp.set_cast_shadow(visible)
            _log(f"{what}: {min(i + VISIBILITY_BATCH, n)}/{n}")
    return n


def hide_landmarks():
    """Pure landscape: hide the blockout buildings (they stay in the map). See LANDMARKS_VISIBLE."""
    return set_landmarks_visible(False)


def show_landmarks():
    return set_landmarks_visible(True)


def tag_dock_lamp(eas=None):
    """Tags the T36 dock lamp blockout (landmark parts at T37_DockLamp) as LyrisDockLamp and lights it like the
    Harbor's dock lamp. Loads only those parts. Returns how many parts it found."""
    eas = eas or unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    def is_lamp(label):
        return label.startswith(LANDMARK_LABEL_PREFIX) and "T37_DockLamp" in label
    load_streamed(is_lamp, "dock lamp")
    parts = [a for a in eas.get_all_level_actors() if is_lamp(_label(a))]
    for actor in parts:
        _add_tags(actor, TAG_DOCK_LAMP)
        light = actor.get_component_by_class(unreal.PointLightComponent)
        if light:
            light.set_editor_property("light_color", _srgb_color(MOONGLASS))
            light.set_editor_property("intensity", DOCK_LAMP_LIGHT[0])
            light.set_editor_property("attenuation_radius", DOCK_LAMP_LIGHT[1])
    if parts:
        _log(f"dock lamp: {len(parts)} parts on Lantern Pier tagged {TAG_DOCK_LAMP}")
    return len(parts)


def _dock_lamp(b, eas, spot):
    """The dock lamp: the T36 blockout at T37_DockLamp, tagged and lit like the Harbor's dock lamp. If the
    landmarks did not place it, builds the Harbor's lamp there instead (owned by the boat and dock step)."""
    if tag_dock_lamp(eas):
        return
    (x, y, z), _ = spot
    mats = _prototype_materials()
    mats["Clay"] = _plain_material("Clay", *PALETTE["Clay"])
    shapes = (("Post", "Cylinder", (x, y, z + 160), (0.14, 0.14, 3.2), "DarkWood"),
              ("Arm", "Cube", (x, y - 30, z + 320), (0.08, 0.7, 0.08), "DarkWood"),
              ("Glass", "Cube", (x, y - 60, z + 280), (0.28, 0.28, 0.45), "LampGlass"),
              ("Roof", "Cone", (x, y - 60, z + 320), (0.4, 0.4, 0.3), "Clay"))
    for name, mesh, loc, scale, mat in shapes:
        actor = b.eas.spawn_actor_from_object(unreal.load_asset(f"/Engine/BasicShapes/{mesh}"), unreal.Vector(*loc),
                                              unreal.Rotator(0, 0, 0))
        actor.set_actor_scale3d(unreal.Vector(*scale))
        actor.set_actor_label(f"{LABEL_PREFIX}DockLamp_{name}")
        actor.set_folder_path("Gameplay/Dock/Lamp")
        b.tag(actor, TAG_DOCK_LAMP)
        _set(actor, "is_spatially_loaded", False, quiet=True)
        comp = actor.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_material(0, mats[mat])
        if name != "Post":
            comp.set_collision_profile_name("NoCollision")
    light = b.spawn(unreal.PointLight, "DockLamp_Light", (x, y - 60, z + 280), folder="Gameplay/Dock/Lamp")
    _add_tags(light, TAG_DOCK_LAMP)
    lc = light.get_component_by_class(unreal.PointLightComponent)
    lc.set_editor_property("light_color", _srgb_color(MOONGLASS))
    lc.set_editor_property("intensity", DOCK_LAMP_LIGHT[0])
    lc.set_editor_property("attenuation_radius", DOCK_LAMP_LIGHT[1])
    _warn("dock lamp: no T37_DockLamp blockout in landmarks.json; built the Harbor lamp at the marker instead")


def _finish_landscape(landscape, eas, manifest):
    """Applies the material and settings to an imported landscape and checks its placement."""
    mat = unreal.load_asset(f"{MAT_DIR}/M_LyrisWorldTerrain_v{TERRAIN_MAT_VERSION}")
    proxies = _landscape_proxies(eas)
    for proxy in proxies:
        if mat:
            _set(proxy, "landscape_material", mat, quiet=True)
    _set(landscape, "enable_nanite", True, quiet=True)  # big landscapes render far cheaper as Nanite
    _set(landscape, "cast_far_shadow", True, quiet=True)
    try:
        scale = landscape.get_actor_scale3d()
        want = manifest["scale"]
        if abs(scale.x - want[0]) > 0.01 or abs(scale.z - want[2]) > 0.01:
            _warn(f"landscape scale is {scale.x:.3f} x {scale.y:.3f} x {scale.z:.1f}, expected "
                  f"{want[0]:.3f} x {want[1]:.3f} x {want[2]:.1f}: re-import with the manifest values")
    except Exception:
        pass
    landscape.set_folder_path("Terrain")
    _log(f"landscape finished: material {'set' if mat else 'MISSING'}, {len(proxies)} loaded proxies "
         "(Build > Build HLODs after any terrain change)")


def _get(obj, prop):
    if obj is None:
        return None
    try:
        return obj.get_editor_property(prop)
    except Exception:
        return None


def _world_partition():
    try:
        return _get(_editor_world().get_world_settings(), "world_partition")
    except Exception:
        return None


def _runtime_hash(wp):
    """The map's runtime hash: WorldPartitionRuntimeSpatialHash (Grids) or, in newer maps,
    WorldPartitionRuntimeHashSet (Runtime Partitions)."""
    found = _get(wp, "runtime_hash")
    if found is None:
        for fn in ("get_runtime_hash",):
            getter = getattr(wp, fn, None) if wp is not None else None
            if getter:
                try:
                    found = getter()
                except Exception:
                    pass
    return found


def _main_partition(hashed):
    """The main layer (URuntimePartition, e.g. RuntimePartitionLHGrid) of a hash set's first partition."""
    parts = _get(hashed, "runtime_partitions")
    if not parts:
        return None, None
    return parts, _get(parts[0], "main_layer")


def read_runtime_grid():
    """(kind, cell size cm, loading range cm) of the main runtime grid, or None if Python cannot see it."""
    hashed = _runtime_hash(_world_partition())
    if hashed is None:
        return None
    grids = _get(hashed, "grids")
    if grids:
        cell, rng = _get(grids[0], "cell_size"), _get(grids[0], "loading_range")
        if cell is not None and rng is not None:
            return "Grids", float(cell), float(rng)
    _parts, layer = _main_partition(hashed)
    if layer is not None:
        cell, rng = _get(layer, "cell_size"), _get(layer, "loading_range")
        if rng is not None:
            return "Runtime Partitions", float(cell if cell is not None else -1), float(rng)
    return None


def streaming_is_right():
    got = read_runtime_grid()
    if got is None:
        return None  # unknown
    _kind, cell, rng = got
    return abs(cell - WP_CELL_M * 100) < 1 and abs(rng - WP_LOADING_RANGE_M * 100) < 1


def _set_number(obj, prop, value):
    for v in (int(value), float(value)):
        if _set(obj, prop, v, quiet=True):
            return True
    return False


def _apply_runtime_grid():
    """Tries every way UE 5.8 Python might reach the main runtime grid. Returns True when it was set."""
    cell, rng = WP_CELL_M * 100, WP_LOADING_RANGE_M * 100
    wp = _world_partition()
    hashed = _runtime_hash(wp)
    if hashed is None:
        _warn("streaming: the World Partition runtime hash is not reachable from Python")
        return False
    kind = hashed.get_class().get_name()
    # 1. WorldPartitionRuntimeSpatialHash: Grids[0] (a struct array: edit a copy, write the array back).
    grids = _get(hashed, "grids")
    if grids:
        try:
            grids = list(grids)
            grid = grids[0]
            _set_number(grid, "cell_size", cell)
            _set_number(grid, "loading_range", rng)
            grids[0] = grid
            hashed.set_editor_property("grids", grids)
        except Exception as exc:
            _warn(f"streaming: could not write {kind}.Grids ({exc})")
    # 2. WorldPartitionRuntimeHashSet: RuntimePartitions[0].MainLayer (an object, edited in place).
    parts, layer = _main_partition(hashed)
    if layer is not None:
        ok = _set_number(layer, "cell_size", cell) & _set_number(layer, "loading_range", rng)
        if not ok:
            _warn(f"streaming: could not write {layer.get_class().get_name()} Cell Size / Loading Range")
        try:
            hashed.set_editor_property("runtime_partitions", parts)
        except Exception:
            pass
    # 3. Console 'set' on the spatial hash class (non-shipping editors): replaces the main grid by text.
    if streaming_is_right() is not True and "SpatialHash" in kind:
        cmd = ("set WorldPartitionRuntimeSpatialHash Grids ((GridName=\"MainGrid\",CellSize=%d,LoadingRange=%.1f,"
               "DebugColor=(R=0.25,G=0.75,B=0.75,A=1.0)))" % (cell, rng))
        try:
            unreal.SystemLibrary.execute_console_command(_editor_world(), cmd)
        except Exception as exc:
            _warn(f"streaming: console set failed ({exc})")
    ok = streaming_is_right()
    if ok:
        try:  # make sure the map package is dirty so the save keeps it
            for obj in (hashed, wp, _editor_world().get_world_settings()):
                if hasattr(obj, "modify"):
                    obj.modify()
        except Exception:
            pass
    return bool(ok)


def streaming_manual_steps():
    """Logs the by-hand fix for the runtime grid, prominently."""
    got = read_runtime_grid()
    now = (f" (now: {got[0]}, Cell Size {got[1]:.0f}, Loading Range {got[2]:.0f})" if got else "")
    lines = [
        "=" * 78,
        "STREAMING NOT SET: in Play you will only see about 256 m around you" + now,
        " 1. Window > World Settings. Find World Partition Setup > Runtime Settings.",
        "    If it shows Grids:               Grids > Index [0]: Cell Size "
        f"{WP_CELL_M * 100}, Loading Range {WP_LOADING_RANGE_M * 100}",
        "    If it shows Runtime Partitions:  Index [0] > Main Layer: Cell Size "
        f"{WP_CELL_M * 100}, Loading Range {WP_LOADING_RANGE_M * 100}",
        " 2. File > Save All.",
        " 3. Python: import lyris_build_world as w; w.streaming_done()   (records it; stops this message)",
        " 4. Build > Build HLODs so the world beyond 1.5 km shows as low-detail proxies (Art/World/README.md).",
        "=" * 78,
    ]
    for line in lines:
        _warn(line)


def streaming_done():
    """Call after setting the runtime grid by hand: checks it if Python can, then records the streaming step."""
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    ok = streaming_is_right()
    if ok is False:
        streaming_manual_steps()
        return
    marker = _marker(eas)
    if marker is None:
        _warn("no build marker in this map: run w.build() first")
        return
    _record_step(marker, "streaming")
    recorded = _recorded_steps(marker)
    if not outdated_steps(recorded):
        marker.set_actor_label(f"{MARKER_PREFIX}{BUILD_VERSION}")
    _save(unreal.get_editor_subsystem(unreal.LevelEditorSubsystem))
    _log("streaming step recorded" + ("" if ok else " (Python cannot read the grid here, so it was taken on trust)"))


def _streaming_settings():
    """The main runtime grid: WP_CELL_M cells loaded to WP_LOADING_RANGE_M, HLODs beyond. Raises when it could
    not be set, so the step is not recorded and every w.build() prints the manual steps until it is right."""
    if _world_partition() is None:
        raise RuntimeError("World Partition object not reachable from Python")
    if streaming_is_right() is True or _apply_runtime_grid():
        _log(f"runtime grid: {WP_CELL_M} m cells, loaded to {WP_LOADING_RANGE_M} m; HLOD beyond")
        return
    raise RuntimeError("the runtime grid could not be set from Python; see STREAMING NOT SET below")
