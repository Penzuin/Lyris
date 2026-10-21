"""Places the canon landmarks and the new island chains in the Lyris map as blockouts (T36).

Reads Art/World/landmarks.json (written by Art/World/make_landmarks.py) and spawns each landmark
from engine basic shapes in the house palette, one outliner folder per landmark
(Landmarks/<Region>/<Name>/<part group>). Every actor is tagged LyrisWorldBuild, LyrisLandmark and
LM_<id>, so real art can replace one landmark by deleting its folder and its entry in the JSON.

Called by lyris_build_world.build() as one of its steps. On its own, to redo only the landmarks
(for example after the landscape is imported, so they snap to it):

    import lyris_build_landmarks as lm; lm.rebuild()

Ground: each part stores the baked ground under it. When the landscape is loaded the script traces
straight down onto it and uses that instead, so blockouts follow any sculpting; otherwise it uses
the stored height, which matches the bake the landscape was imported from.
"""

import json
import os

import unreal

LANDMARKS_JSON = "Art/World/landmarks.json"
TAG = "LyrisWorldBuild"          # same tag as lyris_build_world, so a world rebuild clears these too
LM_TAG = "LyrisLandmark"
LABEL_PREFIX = "LW_LM_"          # starts with lyris_build_world.LABEL_PREFIX ("LW_")
MAT_DIR = "/Game/Lyris/Materials/World/Landmarks"
MAT_VERSION = 1
SEA_Y = 63.0
TRACE_UP_M, TRACE_DOWN_M = 600.0, 900.0
TRACE_MAX_DELTA_M = 25.0         # a trace further than this from the bake hit something else: ignore it

# House palette only (Harbor PALETTE and ISLAND_PALETTE, plus MOONGLASS and the lighthouse glow the
# Harbor script already uses). key: (hex, roughness, metallic, emissive, opacity)
MATERIALS = {
    "Sand":          ("F1E9DC", 0.9, 0.0, 0.0, 1.0),
    "Grass":         ("8A9A48", 0.85, 0.0, 0.0, 1.0),
    "Terracotta":    ("C8643A", 0.7, 0.0, 0.0, 1.0),
    "Clay":          ("36221A", 0.8, 0.0, 0.0, 1.0),
    "Wood":          ("8B5A3A", 0.75, 0.0, 0.0, 1.0),
    "DarkWood":      ("4A2A1C", 0.8, 0.0, 0.0, 1.0),
    "Salt":          ("F1E9DC", 0.6, 0.0, 0.0, 1.0),
    "RedBand":       ("C8443A", 0.6, 0.0, 0.0, 1.0),
    "Gold":          ("E3AE45", 0.35, 0.6, 0.0, 1.0),
    "Sail":          ("F7EEDC", 0.9, 0.0, 0.0, 1.0),
    "Stone":         ("9C9488", 0.9, 0.0, 0.0, 1.0),
    "Leaf":          ("6E8A3A", 0.85, 0.0, 0.0, 1.0),
    "Path":          ("CDAE86", 0.9, 0.0, 0.0, 1.0),   # ISLAND_PALETTE path
    "Rock":          ("8E7680", 0.9, 0.0, 0.0, 1.0),   # ISLAND_PALETTE rock_shade (lavender)
    "LampGlass":     ("7AC0E6", 0.2, 0.0, 25.0, 1.0),  # MOONGLASS, lit
    "LampGlassDark": ("7AC0E6", 0.3, 0.0, 0.0, 1.0),   # an unlit lamp waiting to be relit
    "LighthouseGlow": ("FFE7A0", 0.2, 0.0, 15.0, 1.0),
    "Glass":         ("7FD0D6", 0.05, 0.0, 0.0, 0.3),  # Shallows: Oruth's dome
    "StarGlow":      ("B87C8C", 0.3, 0.0, 12.0, 1.0),  # Blossom underside: the star's violet crystal
}
LIGHT_COLOURS = {"MOONGLASS": "7AC0E6", "LighthouseGlow": "FFE7A0"}
MESHES = {"cube": "/Engine/BasicShapes/Cube", "cylinder": "/Engine/BasicShapes/Cylinder",
          "cone": "/Engine/BasicShapes/Cone", "sphere": "/Engine/BasicShapes/Sphere"}


def _log(msg):
    unreal.log("[Lyris] " + msg)


def _warn(msg):
    unreal.log_warning("[Lyris] " + msg)


def _linear(hex_str):
    def ch(v):
        c = int(v, 16) / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return unreal.LinearColor(ch(hex_str[0:2]), ch(hex_str[2:4]), ch(hex_str[4:6]), 1.0)


def _srgb(hex_str):
    return unreal.Color(r=int(hex_str[0:2], 16), g=int(hex_str[2:4], 16), b=int(hex_str[4:6], 16), a=255)


def _set(obj, prop, value):
    try:
        obj.set_editor_property(prop, value)
        return True
    except Exception:
        return False


def _editor_world():
    sub = getattr(unreal, "UnrealEditorSubsystem", None)
    if sub is not None:
        return unreal.get_editor_subsystem(sub).get_editor_world()
    return unreal.EditorLevelLibrary.get_editor_world()


def load_landmarks():
    path = os.path.join(unreal.Paths.project_dir(), LANDMARKS_JSON)
    if not os.path.exists(path):
        _warn(f"{LANDMARKS_JSON} not found; run: python Art/World/make_landmarks.py")
        return None
    with open(path) as f:
        return json.load(f)


# ----------------------------------------------------------------------------- materials

_MATS = {}


def _material(key):
    if key in _MATS:
        return _MATS[key]
    if key not in MATERIALS:
        _warn(f"material key {key} is not in the palette; using Stone")
        key = "Stone"
    hex_str, rough, metal, emissive, opacity = MATERIALS[key]
    name = f"M_LM_{key}_v{MAT_VERSION}"
    path = f"{MAT_DIR}/{name}"
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        _MATS[key] = unreal.load_asset(path)
        return _MATS[key]
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    mat = tools.create_asset(name, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    mel = unreal.MaterialEditingLibrary
    colour = mel.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -400, 0)
    colour.set_editor_property("constant", _linear(hex_str))
    mel.connect_material_property(colour, "", unreal.MaterialProperty.MP_BASE_COLOR)
    r = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -400, 200)
    r.set_editor_property("r", rough)
    mel.connect_material_property(r, "", unreal.MaterialProperty.MP_ROUGHNESS)
    if metal:
        m = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -400, 300)
        m.set_editor_property("r", metal)
        mel.connect_material_property(m, "", unreal.MaterialProperty.MP_METALLIC)
    if emissive:
        mult = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -200, 400)
        mult.set_editor_property("const_b", emissive)
        mel.connect_material_expressions(colour, "", mult, "A")
        mel.connect_material_property(mult, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    if opacity < 1.0:
        blend = getattr(unreal.BlendMode, "BLEND_TRANSLUCENT", None)
        if blend is not None and _set(mat, "blend_mode", blend):
            o = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -400, 500)
            o.set_editor_property("r", opacity)
            mel.connect_material_property(o, "", unreal.MaterialProperty.MP_OPACITY)
        else:
            _warn(f"{name}: could not make it translucent; set Blend Mode to Translucent by hand")
    mel.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat)
    _MATS[key] = mat
    return mat


# ----------------------------------------------------------------------------- ground


class _Ground:
    """Traces down onto the landscape; falls back to the baked height stored in the JSON."""

    def __init__(self):
        self.world = _editor_world()
        self.cache = {}
        self.traced = self.fallback = 0
        self.lib = unreal.SystemLibrary
        self.can_trace = hasattr(self.lib, "line_trace_multi") and self.world is not None
        if not self.can_trace:
            _warn("line traces are not available from Python here; landmarks use the baked ground heights")

    @staticmethod
    def _hit_parts(hit):
        """(location, actor) from a HitResult across engine versions."""
        try:
            t = hit.to_tuple()
            # (blocking_hit, initial_overlap, time, distance, location, impact_point, normal, impact_normal,
            #  phys_mat, hit_actor, hit_component, ...)
            return t[5], t[9]
        except Exception:
            pass
        try:
            return hit.get_editor_property("impact_point"), hit.get_editor_property("hit_actor")
        except Exception:
            return None, None

    def mc_y(self, x, z, baked):
        key = (round(x, 1), round(z, 1))
        if key in self.cache:
            return self.cache[key]
        y = None
        if self.can_trace:
            start = unreal.Vector(x * 100.0, z * 100.0, (baked - SEA_Y + TRACE_UP_M) * 100.0)
            end = unreal.Vector(x * 100.0, z * 100.0, (baked - SEA_Y - TRACE_DOWN_M) * 100.0)
            try:
                hits = self.lib.line_trace_multi(self.world, start, end, unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
                                                 True, [], unreal.DrawDebugTrace.NONE, True)
            except Exception as exc:
                _warn(f"line trace failed ({exc}); using the baked ground from here on")
                self.can_trace, hits = False, []
            for hit in hits or []:
                loc, actor = self._hit_parts(hit)
                if loc is not None and actor is not None and isinstance(actor, unreal.LandscapeProxy):
                    cand = loc.z / 100.0 + SEA_Y
                    if abs(cand - baked) <= TRACE_MAX_DELTA_M:
                        y = cand
                    break
        if y is None:
            y = baked
            self.fallback += 1
        else:
            self.traced += 1
        self.cache[key] = y
        return y


def _z_of(item, ground):
    """UE Z (cm) of an item's centre."""
    a = item.get("a", "g")
    if a == "g":
        base = ground.mc_y(item["c"][0], item["c"][1], item["g"]) - item.get("k", 0.0)
    elif a == "sea":
        base = SEA_Y
    else:
        base = 0.0
    return (base + item["y"] - SEA_Y) * 100.0


# ----------------------------------------------------------------------------- spawning


class _Spawner:
    def __init__(self):
        self.eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        self.meshes = {k: unreal.load_asset(v) for k, v in MESHES.items()}
        self.ground = _Ground()
        self.count = 0

    def _tag(self, actor, lm_id):
        tags = [unreal.Name(TAG), unreal.Name(LM_TAG), unreal.Name("LM_" + lm_id)]
        _set(actor, "tags", tags)

    def part(self, lm, p):
        x, z = p["c"]
        loc = unreal.Vector(x * 100.0, z * 100.0, _z_of(p, self.ground))
        roll, pitch, yaw = p.get("rot", [0.0, 0.0, 0.0])
        actor = self.eas.spawn_actor_from_object(self.meshes[p["s"]], loc,
                                                 unreal.Rotator(roll=roll, pitch=pitch, yaw=yaw))
        if actor is None:
            _warn(f"could not spawn {lm['id']} {p['n']}")
            return None
        sx, sz, sh = p["size"]
        actor.set_actor_scale3d(unreal.Vector(sx, sz, sh))  # basic shapes are 1 m across at scale 1
        actor.set_actor_label(f"{LABEL_PREFIX}{lm['id']}_{p['n']}")
        actor.set_folder_path(lm["folder"] + ("/" + p["f"] if p.get("f") else ""))
        self._tag(actor, lm["id"])
        comp = actor.get_component_by_class(unreal.StaticMeshComponent)
        if comp:
            comp.set_material(0, _material(p["m"]))
            if p["m"] in ("Glass",):
                comp.set_editor_property("cast_shadow", False)
        self.count += 1
        return actor

    def light(self, lm, L):
        x, z = L["c"]
        loc = unreal.Vector(x * 100.0, z * 100.0, _z_of(L, self.ground))
        actor = self.eas.spawn_actor_from_class(unreal.PointLight, loc, unreal.Rotator(0, 0, 0))
        actor.set_actor_label(f"{LABEL_PREFIX}{lm['id']}_{L['n']}")
        actor.set_folder_path(lm["folder"] + "/Lights")
        self._tag(actor, lm["id"])
        comp = actor.get_component_by_class(unreal.PointLightComponent)
        _set(comp, "mobility", unreal.ComponentMobility.MOVABLE)
        comp.set_editor_property("light_color", _srgb(LIGHT_COLOURS.get(L["colour"], "7AC0E6")))
        comp.set_editor_property("intensity", float(L["intensity"]))
        comp.set_editor_property("attenuation_radius", float(L["radius"]))
        if L.get("always_loaded"):
            _set(actor, "is_spatially_loaded", False)  # the great lamps are seen from far out at sea
        return actor

    def marker(self, lm, mk):
        x, z = mk["c"]
        loc = unreal.Vector(x * 100.0, z * 100.0, _z_of(mk, self.ground))
        actor = self.eas.spawn_actor_from_class(unreal.TargetPoint, loc, unreal.Rotator(0, 0, mk.get("yaw", 0.0)))
        actor.set_actor_label(f"{LABEL_PREFIX}{lm['id']}_{mk['n']}")
        actor.set_folder_path(lm["folder"] + "/Markers")
        _set(actor, "tags", [unreal.Name(TAG), unreal.Name(LM_TAG), unreal.Name("LM_" + lm["id"]),
                             unreal.Name(mk["n"])])
        return actor


class _BakedGround:
    """Ground from the heights stored in the JSON only (no traces)."""

    def mc_y(self, x, z, baked):
        return baked


def markers(prefix="", data=None):
    """{name: ((x, y, z) UE cm, yaw deg)} for every landmark marker whose name starts with `prefix`,
    without spawning anything. lyris_build_world uses this for the T37 dock spot (T37_BoatStart,
    T37_DockLamp, T37_Mooring, T37_StepAshore on Lantern Pier)."""
    data = data or load_landmarks()
    found = {}
    if data is None:
        return found
    ground = _BakedGround()
    for lm in data.get("landmarks", []):
        for mk in lm.get("markers", []):
            if not mk["n"].startswith(prefix):
                continue
            x, z = mk["c"]
            found[mk["n"]] = ((x * 100.0, z * 100.0, _z_of(mk, ground)), float(mk.get("yaw", 0.0)))
    return found


def _ours(actor):
    try:
        if unreal.Name(LM_TAG) in list(actor.get_editor_property("tags")):
            return True
    except Exception:
        pass
    return actor.get_actor_label().startswith(LABEL_PREFIX)


def build_landmarks(manifest=None):
    """Spawns every landmark. Assumes the old ones were removed (lyris_build_world does that)."""
    data = load_landmarks()
    if data is None:
        return 0
    if manifest is not None and manifest.get("bake_version") != data.get("bake_version"):
        _warn(f"landmarks.json was made against terrain bake v{data.get('bake_version')}, the tiles are "
              f"v{manifest.get('bake_version')}: rebake (python Art/World/bake_terrain.py) and rerun "
              "python Art/World/make_landmarks.py so blockouts sit on the ground")
    sp = _Spawner()
    with unreal.ScopedSlowTask(len(data["landmarks"]), "Lyris: placing landmarks") as task:
        task.make_dialog(True)
        for lm in data["landmarks"]:
            if task.should_cancel():
                _warn("landmark placement cancelled")
                break
            task.enter_progress_frame(1, lm["name"])
            for p in lm["parts"]:
                try:
                    sp.part(lm, p)
                except Exception as exc:
                    _warn(f"{lm['id']} {p['n']}: {exc}")
            for L in lm.get("lights", []):
                try:
                    sp.light(lm, L)
                except Exception as exc:
                    _warn(f"{lm['id']} light {L['n']}: {exc}")
            for mk in lm.get("markers", []):
                try:
                    sp.marker(lm, mk)
                except Exception as exc:
                    _warn(f"{lm['id']} marker {mk['n']}: {exc}")
    g = sp.ground
    _log(f"{len(data['landmarks'])} landmarks, {sp.count} blockout parts; ground traced at {g.traced} spots, "
         f"baked height used at {g.fallback} (landscape not loaded or not imported there)")
    return sp.count


def rebuild():
    """Removes this script's actors and places the landmarks again, leaving the rest of the map alone."""
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    try:
        import lyris_build_world as world
        world._load_our_unloaded_actors()
        manifest = world.load_manifest()
    except Exception as exc:
        _warn(f"could not load streamed landmark actors first ({exc})")
        manifest = None
    old = [a for a in eas.get_all_level_actors() if _ours(a)]
    eas.destroy_actors(old)
    _log(f"removed {len(old)} old landmark actors")
    build_landmarks(manifest)
    les.save_current_level()
    unreal.EditorAssetLibrary.save_directory(MAT_DIR, only_if_is_dirty=True, recursive=True)
