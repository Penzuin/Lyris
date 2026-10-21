"""Builds the Lyris world map: the real Lyris Minecraft map at full size, 25 x 25 km.

/Game/Lyris/Maps/Lyris (World Partition) gets: the landscape baked by Art/World/bake_terrain.py
with a painterly auto material driven by its paint layers and slope, a Water plugin ocean over
the whole world plus lakes and upland rivers, sky and golden-hour lighting like Harbor, world
bounds, and a PlayerStart on Moonharbor's waterfront.

The landscape itself is imported once by hand (Unreal's tiled landscape import is not exposed
to Python in a way we can rely on): build() prepares everything, then logs the exact steps.
Run build() again after the import and it finishes the landscape (material, Nanite, checks).
Rebuilds only replace actors this script made (tag LyrisWorldBuild); the landscape is kept.

    import lyris_build_world as w; w.build()            # build or finish
    import lyris_build_world as w; w.build(force=True)  # rebuild even if up to date
    import lyris_build_world as w; w.import_steps()     # print the landscape import steps again

Coordinates: design/world_map.md (MC X -> UE X, MC Z -> UE Y, UE Z = (MC Y - 63) * 100).
Not wired into init_unreal.py yet: T37 (Lead) makes Lyris the default map.
"""

import json
import os

import unreal

BUILD_VERSION = 1
MAP_PATH = "/Game/Lyris/Maps/Lyris"
MAT_DIR = "/Game/Lyris/Materials/World"
TEX_DIR = f"/Game/Lyris/Textures/World_v{BUILD_VERSION}"
LAYER_INFO_DIR = f"{MAT_DIR}/LayerInfo"
MARKER_PREFIX = "LyrisWorld_v"
TAG = "LyrisWorldBuild"
LABEL_PREFIX = "LW_"

WORLD_DIR = "Art/World"
TILE_DIR = "Art/World/tiles"
MANIFEST = "terrain_manifest.json"
DETAIL_TEXTURES = "Art/TestIsland/textures"  # painted ground textures shared with Harbor
ISLAND_META = "Art/TestIsland/island_meta.json"

# Colours are the house palette (Harbor PALETTE and ISLAND_PALETTE); no new hex values.
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

    def __init__(self, name):
        self.name = f"M_{name}_v{BUILD_VERSION}"  # versioned: a rebuild never edits a material in use
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

    def tex(self, texture, uv):
        expr = self.node(unreal.MaterialExpressionTextureSample, texture=texture)
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


# ----------------------------------------------------------------------------- actors

class _Builder:
    def __init__(self):
        self.eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    def spawn(self, cls, label, loc=(0, 0, 0), rot=(0, 0, 0), folder="Lighting", always_loaded=True):
        actor = self.eas.spawn_actor_from_class(
            cls, unreal.Vector(*loc), unreal.Rotator(roll=rot[0], pitch=rot[1], yaw=rot[2]))
        if actor is None:
            raise RuntimeError(f"could not spawn {label}")
        actor.set_actor_label(LABEL_PREFIX + label)
        actor.set_folder_path(folder)
        _set(actor, "tags", [unreal.Name(TAG)])
        if always_loaded:
            _set(actor, "is_spatially_loaded", False, quiet=True)
        return actor

    def cube(self, label, loc, scale, folder):
        mesh = unreal.load_asset("/Engine/BasicShapes/Cube")
        actor = self.eas.spawn_actor_from_object(mesh, unreal.Vector(*loc), unreal.Rotator(0, 0, 0))
        actor.set_actor_scale3d(unreal.Vector(*scale))
        actor.set_actor_label(LABEL_PREFIX + label)
        actor.set_folder_path(folder)
        _set(actor, "tags", [unreal.Name(TAG)])
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


# ----------------------------------------------------------------------------- version and cleanup

def _ours(actor):
    try:
        if unreal.Name(TAG) in list(actor.get_editor_property("tags")):
            return True
    except Exception:
        pass
    return actor.get_actor_label().startswith(LABEL_PREFIX)


def _load_our_unloaded_actors():
    """World Partition only loads actors near the camera; load everything we made before a rebuild."""
    lib = getattr(unreal, "WorldPartitionBlueprintLibrary", None)
    if lib is None or not hasattr(lib, "get_actor_descs"):
        return
    try:
        descs = lib.get_actor_descs()
        guids = [d.get_editor_property("guid") for d in descs
                 if str(d.get_editor_property("label")).startswith(LABEL_PREFIX)
                 or str(d.get_editor_property("label")).startswith(MARKER_PREFIX)]
        if guids:
            lib.load_actors(guids)
            _log(f"loaded {len(guids)} streamed actors from the last build")
    except Exception as exc:
        _warn(f"could not load streamed actors before rebuild ({exc}); duplicates may remain, "
              "load the whole map in the World Partition window and rebuild with force=True")


def _current_version(eas):
    for actor in eas.get_all_level_actors():
        label = actor.get_actor_label()
        if label.startswith(MARKER_PREFIX):
            try:
                return int(label[len(MARKER_PREFIX):])
            except ValueError:
                return 0
    return 0


def _landscape(eas):
    for actor in eas.get_all_level_actors():
        if isinstance(actor, unreal.Landscape):
            return actor
    return None


def _landscape_proxies(eas):
    return [a for a in eas.get_all_level_actors() if isinstance(a, unreal.LandscapeProxy)]


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
        f" 3. Material: {MAT_DIR}/M_LyrisWorldTerrain_v{BUILD_VERSION}",
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

def _step(name, fn):
    try:
        fn()
        _log(f"built {name}")
    except Exception as exc:  # keep going so one failure doesn't stop the rest
        _warn(f"could not build {name}: {exc}")


def _open_or_create_map(les):
    if unreal.EditorAssetLibrary.does_asset_exist(MAP_PATH):
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


def build(force=False):
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    manifest = load_manifest()
    if manifest is None:
        import_steps(None)
        return
    if manifest.get("preview"):
        _warn("the terrain bake is a PREVIEW (low resolution). Rebake at full size before importing: "
              "python Art/World/bake_terrain.py --workers 2")

    if not _open_or_create_map(les):
        unreal.log_error("[Lyris] could not open or create " + MAP_PATH)
        return
    if _is_partitioned() is False:
        _warn(f"{MAP_PATH} is not a World Partition map; streaming settings will not apply")

    _load_our_unloaded_actors()
    version = _current_version(eas)
    landscape = _landscape(eas)
    if version >= BUILD_VERSION and not force:
        if landscape is None:
            _log(f"World map v{version} is built; the landscape is not imported yet")
            import_steps(manifest)
        else:
            _finish_landscape(landscape, eas, manifest)
            les.save_current_level()
            _log(f"World map is up to date (v{version})")
        return
    _log(f"building World map (v{version} -> v{BUILD_VERSION})")
    eas.destroy_actors([a for a in eas.get_all_level_actors() if _ours(a)])

    b = _Builder()
    m = manifest
    half = m["world_bounds_ue"][1]

    def materials():
        _material_terrain()
        _layer_infos()

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

    def ocean():
        actor = b.spawn(unreal.WaterBodyOcean, "Ocean", (0, 0, 0), folder="Water")
        e = half * 1.02
        _set_spline(actor, [(-e, -e, 0), (e, -e, 0), (e, e, 0), (-e, e, 0)], closed=True)
        _water_body_common(actor)
        for prop in ("ocean_extents", "collision_extents"):
            _set_water(actor, prop, unreal.Vector2D(2 * half * 1.2, 2 * half * 1.2))
        _set_water(actor, "height_offset", 15000.0)  # water column below the surface (150 m)

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
        _log(f"{made} upland river reaches (sea-level rivers are covered by the ocean). River width "
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
        x, y, z = m["spawn"]["ue"]
        b.spawn(unreal.PlayerStart, "PlayerStart_Moonharbor", (x, y, z), rot=(0, 0, m["spawn"].get("yaw", -90.0)),
                folder="Gameplay")

    def streaming():
        _streaming_settings()

    for name, fn in [("materials", materials), ("sky and lighting", sky), ("water zone", water_zone),
                     ("ocean", ocean), ("lakes", lakes), ("rivers", rivers), ("world bounds", bounds),
                     ("player start", player_start), ("streaming settings", streaming)]:
        _step(name, fn)

    marker = b.spawn(unreal.Note, "Marker", (0, 0, 50000), folder="Gameplay")
    marker.set_actor_label(f"{MARKER_PREFIX}{BUILD_VERSION}")  # tagged, so a rebuild removes it
    _set(marker, "text", "Built by Content/Python/lyris_build_world.py from Art/World. Edits to actors "
                         "in this build are lost on the next rebuild; the landscape is kept.", quiet=True)

    if landscape is not None:
        _finish_landscape(landscape, eas, manifest)
    les.save_current_level()
    unreal.EditorAssetLibrary.save_directory("/Game/Lyris", only_if_is_dirty=True, recursive=True)
    _log(f"World map v{BUILD_VERSION} ready at {MAP_PATH}")
    if landscape is None:
        import_steps(manifest)


def _finish_landscape(landscape, eas, manifest):
    """Applies the material and settings to an imported landscape and checks its placement."""
    mat = unreal.load_asset(f"{MAT_DIR}/M_LyrisWorldTerrain_v{BUILD_VERSION}")
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


def _streaming_settings():
    """Best-effort World Partition settings; anything not exposed is logged for the user."""
    ws = _editor_world().get_world_settings()
    wp = None
    try:
        wp = ws.get_editor_property("world_partition")
    except Exception:
        pass
    if wp is None:
        _warn("World Partition object not reachable from Python; streaming stays at engine defaults")
        return
    hashed = None
    try:
        hashed = wp.get_editor_property("runtime_hash")
    except Exception:
        pass
    applied = False
    if hashed is not None:
        try:
            grids = hashed.get_editor_property("grids")  # WorldPartitionRuntimeSpatialHash
            if grids:
                grid = grids[0]
                grid.set_editor_property("cell_size", WP_CELL_M * 100)
                grid.set_editor_property("loading_range", float(WP_LOADING_RANGE_M * 100))
                hashed.set_editor_property("grids", grids)
                applied = True
        except Exception:
            pass
    if applied:
        _log(f"runtime grid: {WP_CELL_M} m cells, loaded to {WP_LOADING_RANGE_M} m; HLOD beyond")
    else:
        _log("World Settings > World Partition Setup > Runtime Settings: set the main grid to "
             f"Cell Size {WP_CELL_M * 100} and Loading Range {WP_LOADING_RANGE_M * 100} by hand "
             "(not reachable from Python in this engine version)")
