"""Builds the first Lyris prototype map: Moonharbor's bay at golden hour.

Creates /Game/Lyris/Maps/Harbor with sky and lighting, an ocean, a small island,
a lighthouse, a wooden dock, the dock lamp (cold moonglass light, per Lyris canon)
and a simple sailboat. Uses the Storybook Painterly palette.

Runs automatically once from init_unreal.py when the map doesn't exist yet.
To rebuild by hand: delete Content/Lyris/Maps/Harbor, then in the editor's
Output Log (Python mode) run:  import lyris_build_harbor; lyris_build_harbor.build(force=True)
"""

import unreal

MAP_PATH = "/Game/Lyris/Maps/Harbor"
MAT_DIR = "/Game/Lyris/Materials/Prototype"

# Storybook Painterly palette (sRGB hex) from the Lyris house style.
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
}
MOONGLASS = "7AC0E6"  # cold lamp light, Quiet Reach palette


def _log(msg):
    unreal.log("[Lyris] " + msg)


def _linear(hex_str):
    def ch(v):
        c = int(v, 16) / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return unreal.LinearColor(ch(hex_str[0:2]), ch(hex_str[2:4]), ch(hex_str[4:6]), 1.0)


def _srgb_color(hex_str):
    return unreal.Color(r=int(hex_str[0:2], 16), g=int(hex_str[2:4], 16), b=int(hex_str[4:6], 16), a=255)


def _make_material(name, hex_str, roughness, metallic, emissive=0.0):
    path = f"{MAT_DIR}/M_{name}"
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        return unreal.load_asset(path)
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    mat = tools.create_asset(f"M_{name}", MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
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


class _Builder:
    def __init__(self):
        self.eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        self.mats = {}
        self.meshes = {
            "cube": unreal.load_asset("/Engine/BasicShapes/Cube"),
            "cylinder": unreal.load_asset("/Engine/BasicShapes/Cylinder"),
            "sphere": unreal.load_asset("/Engine/BasicShapes/Sphere"),
            "cone": unreal.load_asset("/Engine/BasicShapes/Cone"),
        }

    def mat(self, name):
        if name not in self.mats:
            if name == "LampGlass":
                self.mats[name] = _make_material(name, MOONGLASS, 0.2, 0.0, emissive=25.0)
            elif name == "LighthouseGlow":
                self.mats[name] = _make_material(name, "FFE7A0", 0.2, 0.0, emissive=15.0)
            else:
                hex_str, rough, metal = PALETTE[name]
                self.mats[name] = _make_material(name, hex_str, rough, metal)
        return self.mats[name]

    def shape(self, label, kind, loc, scale, material, rot=(0, 0, 0), folder="Harbor"):
        actor = self.eas.spawn_actor_from_object(
            self.meshes[kind], unreal.Vector(*loc), unreal.Rotator(roll=rot[0], pitch=rot[1], yaw=rot[2]))
        actor.set_actor_scale3d(unreal.Vector(*scale))
        actor.set_actor_label(label)
        actor.set_folder_path(folder)
        comp = actor.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_material(0, self.mat(material))
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


def _step(name, fn):
    try:
        fn()
        _log(f"built {name}")
    except Exception as exc:  # keep going so one failure doesn't stop the rest
        unreal.log_warning(f"[Lyris] could not build {name}: {exc}")


def build(force=False):
    if unreal.EditorAssetLibrary.does_asset_exist(MAP_PATH) and not force:
        _log("Harbor map already exists; skipping build")
        return

    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not les.new_level(MAP_PATH):
        unreal.log_error("[Lyris] could not create " + MAP_PATH)
        return
    b = _Builder()

    def sky():
        sun = b.spawn(unreal.DirectionalLight, "Sun", (0, 0, 1000), rot=(0, -12, 215))
        sc = sun.get_component_by_class(unreal.DirectionalLightComponent)
        sc.set_editor_property("intensity", 8.0)
        sc.set_editor_property("light_color", _srgb_color("FFD9A6"))
        sc.set_editor_property("atmosphere_sun_light", True)
        b.spawn(unreal.SkyAtmosphere, "SkyAtmosphere")
        skylight = b.spawn(unreal.SkyLight, "SkyLight", (0, 0, 800))
        slc = skylight.get_component_by_class(unreal.SkyLightComponent)
        slc.set_editor_property("real_time_capture", True)
        slc.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
        fog = b.spawn(unreal.ExponentialHeightFog, "SeaMist", (0, 0, 0))
        fc = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
        fc.set_editor_property("fog_density", 0.012)
        fc.set_editor_property("fog_inscattering_luminance", _linear("F7D9A6"))
        b.spawn(unreal.VolumetricCloud, "Clouds")
        ppv = b.spawn(unreal.PostProcessVolume, "StorybookGrade")
        ppv.set_editor_property("unbound", True)
        settings = ppv.get_editor_property("settings")
        settings.set_editor_property("override_auto_exposure_bias", True)
        settings.set_editor_property("auto_exposure_bias", 0.5)
        settings.set_editor_property("override_color_saturation", True)
        settings.set_editor_property("color_saturation", unreal.Vector4(1.15, 1.1, 1.05, 1.15))
        ppv.set_editor_property("settings", settings)

    def ocean():
        zone = b.spawn(unreal.WaterZone, "WaterZone", folder="Water")
        try:
            zone.set_editor_property("zone_extent", unreal.Vector2D(400000.0, 400000.0))
        except Exception:
            pass
        b.spawn(unreal.WaterBodyOcean, "Ocean", folder="Water")

    def island():
        b.shape("Island_Rock", "sphere", (0, 0, -260), (46, 46, 6), "Stone", folder="Island")
        b.shape("Island_Beach", "sphere", (0, 0, -150), (42, 42, 4), "Sand", folder="Island")
        b.shape("Island_Meadow", "sphere", (-150, 0, -120), (32, 30, 4.2), "Grass", folder="Island")
        b.shape("Island_Hill", "sphere", (-600, 300, -60), (16, 14, 4), "Grass", folder="Island")
        for i, (x, y, s) in enumerate([(300, -700, 2.4), (-200, -900, 1.9), (700, 600, 2.1), (-1100, -300, 2.6)]):
            b.shape(f"Tree_Trunk_{i}", "cylinder", (x, y, 150 + 60 * s), (0.25, 0.25, 1.2 * s), "DarkWood", folder="Island/Trees")
            b.shape(f"Tree_Crown_{i}", "sphere", (x, y, 150 + 150 * s), (1.3 * s, 1.3 * s, 1.1 * s), "Grass", folder="Island/Trees")

    def lighthouse():
        base_z = 140
        b.shape("Lighthouse_Base", "cylinder", (-900, 700, base_z + 60), (3.4, 3.4, 1.2), "Stone", folder="Lighthouse")
        b.shape("Lighthouse_Tower", "cylinder", (-900, 700, base_z + 120 + 600), (2.6, 2.6, 12), "Salt", folder="Lighthouse")
        for i, z in enumerate((base_z + 450, base_z + 900)):
            b.shape(f"Lighthouse_Band_{i}", "cylinder", (-900, 700, z), (2.7, 2.7, 1.5), "RedBand", folder="Lighthouse")
        top = base_z + 1320
        b.shape("Lighthouse_Gallery", "cylinder", (-900, 700, top), (3.3, 3.3, 0.2), "Clay", folder="Lighthouse")
        b.shape("Lighthouse_Lamp", "cylinder", (-900, 700, top + 90), (1.8, 1.8, 1.6), "LighthouseGlow", folder="Lighthouse")
        b.shape("Lighthouse_Roof", "cone", (-900, 700, top + 230), (2.4, 2.4, 1.3), "Clay", folder="Lighthouse")
        b.point_light("Lighthouse_Light", (-900, 700, top + 90), "FFE7A0", 40000.0, 6000.0, "Lighthouse")

    def dock():
        deck_z = 60
        b.shape("Dock_Deck", "cube", (2700, 150, deck_z), (16, 3.2, 0.25), "Wood", folder="Dock")
        for i, x in enumerate(range(2000, 3500, 300)):
            for side, y in (("N", 0), ("S", 300)):
                b.shape(f"Dock_Post_{i}{side}", "cylinder", (x, y, -80), (0.35, 0.35, 3), "DarkWood", folder="Dock")
        b.shape("Dock_Bollard", "cylinder", (3400, 20, deck_z + 45), (0.3, 0.3, 0.6), "DarkWood", folder="Dock")

    def lamp():
        x, y, deck_top = 3400, 280, 75
        b.shape("Lamp_Post", "cylinder", (x, y, deck_top + 160), (0.14, 0.14, 3.2), "DarkWood", folder="Dock/Lamp")
        b.shape("Lamp_Arm", "cube", (x, y - 30, deck_top + 320), (0.08, 0.7, 0.08), "DarkWood", folder="Dock/Lamp")
        b.shape("Lamp_Glass", "cube", (x, y - 60, deck_top + 280), (0.28, 0.28, 0.45), "LampGlass", folder="Dock/Lamp")
        b.shape("Lamp_Roof", "cone", (x, y - 60, deck_top + 320), (0.4, 0.4, 0.3), "Clay", folder="Dock/Lamp")
        b.point_light("Lamp_Light", (x, y - 60, deck_top + 280), MOONGLASS, 8000.0, 1800.0, "Dock/Lamp")

    def boat():
        bx, by = 3100, -450
        b.shape("Boat_Hull", "cube", (bx, by, 25), (5.5, 1.8, 0.9), "Wood", folder="Boat")
        b.shape("Boat_Bow", "cube", (bx + 330, by, 35), (1.8, 1.8, 0.8), "Wood", rot=(0, 0, 45), folder="Boat")
        b.shape("Boat_Trim", "cube", (bx, by, 72), (5.6, 1.85, 0.08), "Gold", folder="Boat")
        b.shape("Boat_Mast", "cylinder", (bx + 30, by, 380), (0.15, 0.15, 6.5), "DarkWood", folder="Boat")
        b.shape("Boat_Sail", "cube", (bx - 80, by, 400), (2.0, 0.04, 4.6), "Sail", rot=(0, 0, 8), folder="Boat")
        b.shape("Boat_SailStripe", "cube", (bx - 80, by + 3, 430), (2.02, 0.04, 0.7), "Terracotta", rot=(0, 0, 8), folder="Boat")
        b.shape("Boat_Flag", "cube", (bx + 60, by, 720), (0.6, 0.02, 0.3), "Terracotta", folder="Boat")

    def player_start():
        b.spawn(unreal.PlayerStart, "PlayerStart", (2100, 150, 200), rot=(0, 0, 0), folder="Gameplay")

    for name, fn in [("sky and lighting", sky), ("ocean", ocean), ("island", island),
                     ("lighthouse", lighthouse), ("dock", dock), ("dock lamp", lamp),
                     ("boat", boat), ("player start", player_start)]:
        _step(name, fn)

    les.save_current_level()
    unreal.EditorAssetLibrary.save_directory("/Game/Lyris", only_if_is_dirty=True, recursive=True)
    _log("Harbor map ready at " + MAP_PATH)
