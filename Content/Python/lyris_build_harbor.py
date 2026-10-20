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

BUILD_VERSION = 4
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
ISLAND_META = "island_meta.json"
ISLAND_ASSET_DIR = "/Game/Lyris/Meshes/TestIsland"

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


def _make_textured_material(name, texture, roughness=0.9):
    """A simple opaque material: the painted texture as base colour."""
    asset_name = f"M_{name}_v{BUILD_VERSION}"  # versioned, so a rebuild never edits a material in use
    path = f"{MAT_DIR}/{asset_name}"
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        return unreal.load_asset(path)
    mat = _new_material(asset_name)
    mel = unreal.MaterialEditingLibrary
    sample = mel.create_material_expression(mat, unreal.MaterialExpressionTextureSample, -400, 0)
    sample.set_editor_property("texture", texture)
    mel.connect_material_property(sample, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
    rough = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -400, 250)
    rough.set_editor_property("r", roughness)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat)
    return mat


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


def _import_island():
    """Imports the island .glb and returns its StaticMesh, set up for the game."""
    path = os.path.join(unreal.Paths.project_dir(), ISLAND_DIR, ISLAND_GLB)
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", path)
    task.set_editor_property("destination_path", ISLAND_ASSET_DIR)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])

    mesh = None
    textures = {}
    for asset_path in unreal.EditorAssetLibrary.list_assets(ISLAND_ASSET_DIR, recursive=True):
        asset = unreal.load_asset(asset_path)
        if isinstance(asset, unreal.StaticMesh) and mesh is None:
            mesh = asset
        elif isinstance(asset, unreal.Texture2D):
            textures[asset.get_name()] = asset
    if mesh is None:
        raise RuntimeError("no StaticMesh found after importing " + path)

    # The importer's own glTF materials don't show the textures, so give every slot a
    # plain material of ours that samples its painted texture directly.
    slots = mesh.get_editor_property("static_materials")
    for index, slot in enumerate(slots):
        slot_name = str(slot.get_editor_property("material_slot_name"))
        current = slot.get_editor_property("material_interface")
        candidates = [slot_name, current.get_name() if current else ""]
        key = None
        for name in candidates:
            name = name.replace("MI_", "").replace("M_Island_", "")
            if name in textures:
                key = name
                break
        if key is None:
            unreal.log_warning(f"[Lyris] no texture found for island material slot {slot_name}")
            continue
        mesh.set_material(index, _make_textured_material(f"Island_{key}", textures[key]))
        _log(f"island slot {slot_name} -> texture {key}")

    # Walk on the real shape of the island: use the visible triangles as collision.
    body = mesh.get_editor_property("body_setup")
    if body:
        body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    unreal.EditorAssetLibrary.save_loaded_asset(mesh)
    return mesh


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
        sun = b.spawn(unreal.DirectionalLight, "Sun", (0, 0, 1000), rot=(0, -14, 215))
        sc = sun.get_component_by_class(unreal.DirectionalLightComponent)
        sc.set_editor_property("intensity", 6.0)
        sc.set_editor_property("light_color", _srgb_color("FFE3BE"))
        sc.set_editor_property("atmosphere_sun_light", True)
        b.spawn(unreal.SkyAtmosphere, "SkyAtmosphere")
        skylight = b.spawn(unreal.SkyLight, "SkyLight", (0, 0, 800))
        slc = skylight.get_component_by_class(unreal.SkyLightComponent)
        slc.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
        slc.set_editor_property("real_time_capture", True)
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
        settings.set_editor_property("color_saturation", unreal.Vector4(1.05, 1.08, 1.0, 1.1))
        ppv.set_editor_property("settings", settings)

    def sea():
        # One big plane: 100 units x 4000 = 4 km across; the mist hides the edge.
        b.shape("Sea", "plane", (0, 0, 0), (4000, 4000, 1), "Sea", folder="Sea", collide=False)
        # Pale shallows ring around the island, a hair above the sea to avoid flicker.
        b.shape("Shallows", "cylinder", (0, 0, 0.5), (62, 62, 0.01), "Shallows", folder="Sea", collide=False)

    def island():
        mesh = _import_island()
        scale, yaw, z_offset = _island_transform(mesh)
        actor = b.eas.spawn_actor_from_object(mesh, unreal.Vector(0, 0, z_offset), unreal.Rotator(roll=0, pitch=0, yaw=yaw))
        actor.set_actor_scale3d(unreal.Vector(*scale))
        actor.set_actor_label("TestIsland")
        actor.set_folder_path("Island")

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
