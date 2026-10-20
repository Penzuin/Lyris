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

import math

import unreal

BUILD_VERSION = 2
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

# Island shape: ellipsoid domes (centre x, y, z, horizontal radius, half-height, material).
# Only the parts above sea level (z = 0) matter for walking.
DOMES = [
    ("Island_Rock",   0,    0,   -260, 2300, 220, "Stone"),
    ("Island_Beach",  0,    0,   -100, 2000, 200, "Sand"),
    ("Island_Meadow", -200, 0,   -60,  1400, 200, "Grass"),
    ("Island_Hill",   -500, 400, 0,    700,  220, "Grass"),
]
TERRACE_STEP = 20.0  # height between collider steps; the character steps up to 45

DOCK_X0, DOCK_X1, DOCK_Y, DOCK_TOP = 1150.0, 2850.0, 150.0, 72.0
BOAT_START = (2450.0, -230.0)
LAMP_POS = (2760.0, 290.0)
LIGHTHOUSE_POS = (-700.0, -600.0)
TREES = [(300, -700, 2.2), (-200, -1000, 1.8), (500, 650, 2.0), (-1100, -250, 2.5), (-250, 900, 1.9)]


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


def ground_height(x, y):
    """Top of the island at (x, y), or a value below 0 over open water."""
    best = -1000.0
    for _, cx, cy, cz, radius, half_h, _ in DOMES:
        d = math.hypot(x - cx, y - cy)
        if d < radius:
            best = max(best, cz + half_h * math.sqrt(1.0 - (d / radius) ** 2))
    return best


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
        b.shape("Shallows", "cylinder", (0, 0, 0.5), (50, 50, 0.01), "Shallows", folder="Sea", collide=False)

    def island():
        for label, cx, cy, cz, radius, half_h, material in DOMES:
            b.shape(label, "sphere", (cx, cy, cz), (radius / 50.0, radius / 50.0, half_h / 50.0),
                    material, folder="Island", collide=False)
        # Hidden stepped colliders that follow the domes, so the island is walkable
        # and the boat runs aground on the shore.
        for idx, (_, cx, cy, cz, radius, half_h, _) in enumerate(DOMES):
            top = cz + half_h
            z = max(0.0, cz)
            while z < top - 1.0:
                frac = (z - cz) / half_h
                r = radius * math.sqrt(max(0.0, 1.0 - frac * frac))
                bottom = -400.0
                height = z - bottom + TERRACE_STEP
                b.shape(f"IslandCollider_{idx}_{int(z)}", "cylinder",
                        (cx, cy, bottom + height / 2.0), (r / 50.0, r / 50.0, height / 100.0),
                        folder="Island/Colliders", visible=False)
                z += TERRACE_STEP
        for i, (x, y, s) in enumerate(TREES):
            g = ground_height(x, y)
            b.shape(f"Tree_Trunk_{i}", "cylinder", (x, y, g + 60 * s), (0.25, 0.25, 1.2 * s), "DarkWood",
                    folder="Island/Trees")
            b.shape(f"Tree_Crown_{i}", "sphere", (x, y, g + 150 * s), (1.3 * s, 1.3 * s, 1.1 * s), "Leaf",
                    folder="Island/Trees", collide=False)

    def lighthouse():
        x, y = LIGHTHOUSE_POS
        g = ground_height(x, y) - 20
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
