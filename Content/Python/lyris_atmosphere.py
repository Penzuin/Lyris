"""The majesty pass (T59): the sky, light, mist, grade and drifting light motes that make a Lyris map feel
like a storybook painting. Used by lyris_build_moonharbor.py (steps "sky" and "motes"); the full world map
keeps lyris_build_world's plainer sky until it adopts this.

What build_sky() places (one actor each, found by tag so T1's clock can drive them later):

    LyrisSun            golden-hour sun: soft-edged shadows, light shafts, cloud shadows drifting on the land
    LyrisMoon           a pale, oversized storybook moon over the bay mouth. Picture only: it is far too dim
                        to light or shadow anything until T1 turns the day round
    LyrisSkyAtmosphere  a hazier, deeper sky with stronger aerial perspective, so far hills fade to blue
    LyrisSkyLight       real-time sky light with a little sea-coloured bounce from below
    LyrisSeaMist        height fog in two layers (a thin haze, and a mist that hugs the water) with volumetric
                        fog, so sunlight streaks through trees and masts and every lamp wears a halo
    LyrisClouds         volumetric clouds brought lower, lit from beneath by the low sun
    LyrisGrade          the storybook grade: warm lights, cool violet-blue shadows, soft bloom, gentle vignette

What build_motes() places (tag LyrisMotes): small clouds of slowly drifting, twinkling motes of light round
every kept lamp (the Forgetting Sea: where light is kept, the world is remembered, and you can see it in the
air), and tall columns of them at the wonders (Ilwen's great lamp, the Hung Star, the water over Oruth, the
waystone ring). No Niagara and no hand-made assets: each cloud is one small static mesh of tiny orbs, moved
and twinkled by its material, so it costs almost nothing and is rebuilt by script like everything else.

Colours are the house palette only (MOONGLASS, LighthouseGlow, Sea, and the sun and mist colours the world
sky already used). Everything to tune by eye is in the tables at the top; change a number, bump the step's
version in lyris_build_moonharbor.py, run mh.build().

    import lyris_build_moonharbor as mh; mh.build(only=["sky"])      # redo the sky after changing a number
    import lyris_build_moonharbor as mh; mh.build(only=["motes"])    # redo the motes

Not run in Unreal when written (cloud agent): every property is set through _put(), which logs a warning
and carries on if this engine version names a property differently, so a wrong name costs one effect, not
the build.
"""

import array
import json
import math
import os
import random
import struct

import unreal

import lyris_build_world as w

VERSION = 1                      # versions the mote meshes and materials (assets are never edited in place)
MESH_DIR = "/Game/Lyris/Meshes/Atmosphere"
MAT_DIR = "/Game/Lyris/Materials/Atmosphere"

SKY_FOLDER = "Atmosphere/Sky"
TAG_SUN, TAG_MOON, TAG_SKY, TAG_SKYLIGHT = "LyrisSun", "LyrisMoon", "LyrisSkyAtmosphere", "LyrisSkyLight"
TAG_MIST, TAG_CLOUDS, TAG_GRADE, TAG_MOTES = "LyrisSeaMist", "LyrisClouds", "LyrisGrade", "LyrisMotes"

# House colours (no new hex values): the world sky's sun and mist, the lamp colours, the sea.
SUN_HEX = "FFE3BE"
MIST_HEX = "D8E4EC"
MOONGLASS_HEX = w.MOONGLASS          # 7AC0E6
LAMPGLOW_HEX = "FFE7A0"              # lyris_build_landmarks LIGHT_COLOURS["LighthouseGlow"]
SEA_HEX = w.PALETTE["Sea"][0]

SKY = {
    # The sun keeps the world sky's golden hour: 14 degrees up in the east-south-east, so the town and Keep
    # Hill are rim-lit from the pier and the bay ahead of you is front-lit.
    "sun_rot": (0.0, -14.0, 215.0),          # roll, pitch, yaw
    "sun_lux": 5.0,
    "sun_source_angle": 1.6,                 # wider than the real sun: softer, painterly shadow edges
    "sun_volumetric": 1.6,                   # how strongly the sun lights the mist (light shafts)
    "sun_shaft_bloom": 0.12,                 # screen-space glow round the sun through masts and leaves
    "cloud_shadow_strength": 0.55,
    # The moon: north-north-west over the bay mouth, 22 degrees up, about four times its real size.
    "moon_rot": (0.0, -22.0, 70.0),
    "moon_lux": 0.02,                        # sets how bright the disc looks; lights nothing
    "moon_source_angle": 2.2,
    # Sky.
    "mie_scale": 0.010,                      # engine default 0.004: more golden haze round the sun
    "mie_anisotropy": 0.82,
    "rayleigh_scale": 0.037,                 # engine default 0.0331: a slightly deeper blue overhead
    "multi_scattering": 1.25,
    "aerial_perspective": 1.6,               # far land fades to blue sooner (painterly depth at 4 km)
    "skylight": 1.2,
    "sea_bounce": 0.22,                      # sea-coloured light from below, as a share of the Sea colour
    # Mist. Densities are Unreal's fog units; the second layer hugs the water.
    "haze_density": 0.004, "haze_falloff": 0.07,
    "mist_density": 0.018, "mist_falloff": 1.4, "mist_height_cm": 0.0,
    "mist_colour_scale": 0.6,
    "mist_max_opacity": 0.9,                 # the far backdrop never disappears completely
    "sun_glow_in_mist": 0.5, "sun_glow_exponent": 6.0,
    "volumetric_distance_cm": 12000.0,       # volumetric fog out to 120 m
    "volumetric_forward": 0.75,              # forward scattering: shafts show when you face the sun
    # Clouds (km).
    "cloud_bottom_km": 3.2, "cloud_height_km": 5.5,
}

GRADE = {
    "exposure_bias": 0.3,
    "bloom": 0.9, "bloom_threshold": -1.0,
    "saturation": (1.06, 1.07, 1.05, 1.06),
    "contrast": (1.03, 1.03, 1.03, 1.04),
    "gain_shadows": (0.90, 0.94, 1.10, 1.0),        # cool violet-blue shadows
    "saturation_shadows": (1.0, 1.0, 1.0, 1.10),
    "gain_midtones": (1.01, 1.0, 0.99, 1.0),
    "gain_highlights": (1.05, 1.01, 0.94, 1.0),     # warm lights
    "film_slope": 0.86, "film_toe": 0.50, "film_shoulder": 0.30,
    "vignette": 0.30,
    "motion_blur": 0.2,
}

MOTES = {
    # kind: motes in the cloud, radius (m), how far below and above the centre (m), orb radius (cm),
    #       drift (cm), glow (emissive strength)
    "lamp":   {"count": 70, "radius_m": 5.0, "below_m": 2.5, "above_m": 3.5, "orb_cm": 2.6, "drift_cm": 45.0,
               "glow": 60.0},
    "wonder": {"count": 320, "radius_m": 28.0, "below_m": 6.0, "above_m": 32.0, "orb_cm": 5.5, "drift_cm": 120.0,
               "glow": 80.0},
}
WONDER_LIGHT_RADIUS = 3500.0     # a landmark light reaching this far (cm) or farther marks a wonder
MOTES_MAX = 90                   # clouds placed at most
SEA_SURFACE_MOTES_Z = 250.0      # motes for a light under the sea (Oruth) float this far above the water (cm)
EXTRA_WONDERS = ("16a",)         # landmarks without a light that still get a column of motes (waystone ring A)


def _log(msg):
    unreal.log("[Lyris] " + msg)


def _warn(msg):
    unreal.log_warning("[Lyris] " + msg)


def _lin(hex_str, k=1.0):
    c = w._linear(hex_str)
    return unreal.LinearColor(c.r * k, c.g * k, c.b * k, 1.0)


def _put(obj, names, value, what=None):
    """Sets the first property name this engine version accepts. Warns (once per call) if none does."""
    names = (names,) if isinstance(names, str) else names
    if obj is None:
        return False
    for name in names:
        try:
            obj.set_editor_property(name, value)
            return True
        except Exception:
            continue
    _warn(f"majesty pass: could not set {what or names[0]} (tried {', '.join(names)}); that one effect is "
          "missing, the rest is fine")
    return False


def _comp(actor, cls_name):
    cls = getattr(unreal, cls_name, None)
    comp = actor.get_component_by_class(cls) if cls is not None else None
    if comp is None:
        _warn(f"majesty pass: {actor.get_actor_label()} has no {cls_name}")
    return comp


# ----------------------------------------------------------------------------- sky

def build_sky(b):
    """Spawns the seven sky actors with builder `b` (a lyris_build_world._Builder or a subclass)."""
    s = SKY

    # --- sun
    sun = b.spawn(unreal.DirectionalLight, "Sun", (0, 0, 100000), rot=s["sun_rot"], folder=SKY_FOLDER)
    w._add_tags(sun, TAG_SUN)
    sc = _comp(sun, "DirectionalLightComponent")
    _put(sc, "intensity", s["sun_lux"])
    _put(sc, "light_color", w._srgb_color(SUN_HEX))
    _put(sc, "atmosphere_sun_light", True)
    _put(sc, "atmosphere_sun_light_index", 0)
    _put(sc, "light_source_angle", s["sun_source_angle"], "the sun's soft shadow edge")
    _put(sc, "volumetric_scattering_intensity", s["sun_volumetric"], "sunlight in the mist")
    _put(sc, "enable_light_shaft_bloom", True, "light shafts")
    _put(sc, "bloom_scale", s["sun_shaft_bloom"], "light shaft strength")
    _put(sc, "bloom_tint", w._srgb_color(SUN_HEX), "light shaft colour")
    _put(sc, "cast_cloud_shadows", True, "cloud shadows on the land")
    _put(sc, "cloud_shadow_strength", s["cloud_shadow_strength"], "cloud shadow strength")
    _put(sc, "cast_shadows_on_clouds", True, "shadows on the clouds")
    _put(sc, "cast_shadows_on_atmosphere", True, "shadows in the sky haze")
    _put(sc, "per_pixel_atmosphere_transmittance", True, "sunset colour per pixel")
    w._set(sc, "dynamic_shadow_distance_movable_light", 30000.0, quiet=True)
    w._set(sc, "far_shadow_cascade_count", 2, quiet=True)
    w._set(sc, "far_shadow_distance", 300000.0, quiet=True)

    # --- moon (a second atmosphere light: the sky draws its disc; it casts nothing)
    moon = b.spawn(unreal.DirectionalLight, "Moon", (0, 0, 100000), rot=s["moon_rot"], folder=SKY_FOLDER)
    w._add_tags(moon, TAG_MOON)
    mc = _comp(moon, "DirectionalLightComponent")
    _put(mc, "intensity", s["moon_lux"])
    _put(mc, "light_color", w._srgb_color(MOONGLASS_HEX))
    _put(mc, "atmosphere_sun_light", True)
    _put(mc, "atmosphere_sun_light_index", 1, "the moon as the sky's second light")
    _put(mc, "light_source_angle", s["moon_source_angle"], "the moon's size")
    _put(mc, "cast_shadows", False)
    _put(mc, "volumetric_scattering_intensity", 0.0)
    _put(mc, "affect_translucent_lighting", False)

    # --- sky
    sky = b.spawn(unreal.SkyAtmosphere, "SkyAtmosphere", folder=SKY_FOLDER)
    w._add_tags(sky, TAG_SKY)
    ac = _comp(sky, "SkyAtmosphereComponent")
    _put(ac, "mie_scattering_scale", s["mie_scale"], "golden haze")
    _put(ac, "mie_anisotropy", s["mie_anisotropy"])
    _put(ac, "rayleigh_scattering_scale", s["rayleigh_scale"], "sky blue")
    _put(ac, "multi_scattering_factor", s["multi_scattering"])
    # (Unreal spells this one "Pespective".)
    _put(ac, ("aerial_pespective_view_distance_scale", "aerial_perspective_view_distance_scale"),
         s["aerial_perspective"], "aerial perspective")

    # --- sky light
    skylight = b.spawn(unreal.SkyLight, "SkyLight", (0, 0, 80000), folder=SKY_FOLDER)
    w._add_tags(skylight, TAG_SKYLIGHT)
    lc = _comp(skylight, "SkyLightComponent")
    _put(lc, "mobility", unreal.ComponentMobility.MOVABLE)
    _put(lc, "real_time_capture", True)
    _put(lc, "intensity", s["skylight"])
    _put(lc, "lower_hemisphere_is_black", False, "sea bounce")
    _put(lc, "lower_hemisphere_color", _lin(SEA_HEX, s["sea_bounce"]), "sea bounce colour")

    # --- mist
    fog = b.spawn(unreal.ExponentialHeightFog, "SeaMist", (0, 0, 0), folder=SKY_FOLDER)
    w._add_tags(fog, TAG_MIST)
    fc = _comp(fog, "ExponentialHeightFogComponent")
    _put(fc, "fog_density", s["haze_density"])
    _put(fc, "fog_height_falloff", s["haze_falloff"])
    _put(fc, "fog_inscattering_luminance", _lin(MIST_HEX, s["mist_colour_scale"]))
    _put(fc, "fog_max_opacity", s["mist_max_opacity"])
    try:
        second = fc.get_editor_property("second_fog_data")
        second.set_editor_property("fog_density", s["mist_density"])
        second.set_editor_property("fog_height_falloff", s["mist_falloff"])
        second.set_editor_property("fog_height_offset", s["mist_height_cm"])
        fc.set_editor_property("second_fog_data", second)
    except Exception as exc:
        _warn(f"majesty pass: no second fog layer ({exc}); the mist that hugs the water is missing")
    _put(fc, ("directional_inscattering_luminance", "directional_inscattering_color"),
         _lin(SUN_HEX, s["sun_glow_in_mist"]), "sun glow in the mist")
    _put(fc, "directional_inscattering_exponent", s["sun_glow_exponent"])
    _put(fc, "directional_inscattering_start_distance", 3000.0)
    _put(fc, ("enable_volumetric_fog", "volumetric_fog"), True, "volumetric fog (light shafts, lamp halos)")
    _put(fc, "volumetric_fog_scattering_distribution", s["volumetric_forward"])
    _put(fc, "volumetric_fog_distance", s["volumetric_distance_cm"])

    # --- clouds
    clouds = b.spawn(unreal.VolumetricCloud, "Clouds", folder=SKY_FOLDER)
    w._add_tags(clouds, TAG_CLOUDS)
    cc = _comp(clouds, "VolumetricCloudComponent")
    _put(cc, "layer_bottom_altitude", s["cloud_bottom_km"], "cloud base height")
    _put(cc, "layer_height", s["cloud_height_km"], "cloud depth")
    _put(cc, ("use_per_sample_atmospheric_light_transmittance", "per_sample_atmospheric_light_transmittance"),
         True, "sunset-coloured cloud undersides")

    # --- grade
    ppv = b.spawn(unreal.PostProcessVolume, "StorybookGrade", folder=SKY_FOLDER)
    w._add_tags(ppv, TAG_GRADE)
    _put(ppv, "unbound", True)
    try:
        settings = ppv.get_editor_property("settings")
        _grade(settings)
        ppv.set_editor_property("settings", settings)
    except Exception as exc:
        _warn(f"majesty pass: could not apply the storybook grade ({exc})")
    _log("sky: golden-hour sun, moon over the bay mouth, sea mist with volumetric light, sunlit clouds, "
         "storybook grade")


def _grade(settings):
    g = GRADE

    def put(name, value):
        try:
            settings.set_editor_property("override_" + name, True)
            settings.set_editor_property(name, value)
        except Exception as exc:
            _warn(f"majesty pass: grade setting {name} not applied ({exc})")

    put("auto_exposure_bias", g["exposure_bias"])
    put("bloom_intensity", g["bloom"])
    put("bloom_threshold", g["bloom_threshold"])
    put("color_saturation", unreal.Vector4(*g["saturation"]))
    put("color_contrast", unreal.Vector4(*g["contrast"]))
    put("color_gain_shadows", unreal.Vector4(*g["gain_shadows"]))
    put("color_saturation_shadows", unreal.Vector4(*g["saturation_shadows"]))
    put("color_gain_midtones", unreal.Vector4(*g["gain_midtones"]))
    put("color_gain_highlights", unreal.Vector4(*g["gain_highlights"]))
    put("film_slope", g["film_slope"])
    put("film_toe", g["film_toe"])
    put("film_shoulder", g["film_shoulder"])
    put("vignette_intensity", g["vignette"])
    put("motion_blur_amount", g["motion_blur"])


# ----------------------------------------------------------------------------- motes: the mesh

_ICO_T = (1.0 + math.sqrt(5.0)) / 2.0
_ICO_VERTS = [(-1, _ICO_T, 0), (1, _ICO_T, 0), (-1, -_ICO_T, 0), (1, -_ICO_T, 0),
              (0, -1, _ICO_T), (0, 1, _ICO_T), (0, -1, -_ICO_T), (0, 1, -_ICO_T),
              (_ICO_T, 0, -1), (_ICO_T, 0, 1), (-_ICO_T, 0, -1), (-_ICO_T, 0, 1)]
_ICO_TRIS = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2),
             (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5),
             (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]


def mote_cloud(kind, seed=None):
    """The orbs of one cloud, in Unreal space (cm, Z up, centred on the lamp).

    Returns (positions, normals, phases, triangles, half_extent_cm). Every vertex of an orb carries the same
    two random numbers (its `phase`), which the material turns into that orb's own drift and twinkle."""
    spec = MOTES[kind]
    rng = random.Random(seed if seed is not None else f"lyris-motes-{kind}-{VERSION}")
    norm = math.sqrt(1.0 + _ICO_T * _ICO_T)
    unit = [(x / norm, y / norm, z / norm) for x, y, z in _ICO_VERTS]
    pos, nrm, phase, tris = [], [], [], []
    radius = spec["radius_m"] * 100.0
    below, above = spec["below_m"] * 100.0, spec["above_m"] * 100.0
    for _ in range(spec["count"]):
        # Denser toward the middle, thinning out; taller than wide for the wonders.
        r = radius * rng.random() ** 0.75
        ang = rng.random() * math.tau
        up = rng.random()
        z = -below + (below + above) * up * up if kind == "wonder" else rng.uniform(-below, above)
        r *= 1.0 - 0.45 * max(0.0, z / above) if above > 0 else 1.0     # the column narrows as it rises
        cx, cy = r * math.cos(ang), r * math.sin(ang)
        size = spec["orb_cm"] * rng.choice((0.55, 0.7, 0.85, 1.0, 1.0, 1.25, 1.7))
        ph = (rng.random(), rng.random())
        base = len(pos)
        for ux, uy, uz in unit:
            pos.append((cx + ux * size, cy + uy * size, z + uz * size))
            nrm.append((ux, uy, uz))
            phase.append(ph)
        tris.extend((base + a, base + c, base + d) for a, c, d in _ICO_TRIS)
    half = max(max(abs(p[0]), abs(p[1])) for p in pos)
    return pos, nrm, phase, tris, half


def write_mote_glb(path, kind):
    """Writes one cloud as a glTF binary (metres, Y up), the same way the sea mesh is written."""
    pos, nrm, phase, tris, half = mote_cloud(kind)
    name = f"SM_LyrisMotes_{kind.capitalize()}"
    p, n, uv0, uv1 = array.array("f"), array.array("f"), array.array("f"), array.array("f")
    lo, hi = [1e9] * 3, [-1e9] * 3
    for (x, y, z), (nx, ny, nz), (a, c) in zip(pos, nrm, phase):
        g = (x / 100.0, z / 100.0, y / 100.0)                # Unreal (x, y, z) cm -> glTF (x, z, y) m
        p.extend(g)
        n.extend((nx, nz, ny))
        uv0.extend((a, c))
        uv1.extend((a, c))
        for i in range(3):
            lo[i], hi[i] = min(lo[i], g[i]), max(hi[i], g[i])
    idx = array.array("I")
    for a, c, d in tris:
        idx.extend((a, d, c))                                 # the axis swap mirrors the mesh: keep faces outward
    blobs = [p.tobytes(), n.tobytes(), uv0.tobytes(), uv1.tobytes(), idx.tobytes()]
    views, offset = [], 0
    for i, data in enumerate(blobs):
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(data),
                      "target": 34963 if i == 4 else 34962})
        offset += len(data)                                   # every blob is a multiple of 4 bytes
    count = len(pos)
    doc = {"asset": {"version": "2.0", "generator": "Lyris lyris_atmosphere.py"},
           "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"name": name, "mesh": 0}],
           "meshes": [{"name": name, "primitives": [{
               "attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2, "TEXCOORD_1": 3},
               "indices": 4, "material": 0}]}],
           "materials": [{"name": "M_Motes", "pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": 1.0}}],
           "accessors": [
               {"bufferView": 0, "componentType": 5126, "count": count, "type": "VEC3", "min": lo, "max": hi},
               {"bufferView": 1, "componentType": 5126, "count": count, "type": "VEC3"},
               {"bufferView": 2, "componentType": 5126, "count": count, "type": "VEC2"},
               {"bufferView": 3, "componentType": 5126, "count": count, "type": "VEC2"},
               {"bufferView": 4, "componentType": 5125, "count": len(idx), "type": "SCALAR"}],
           "bufferViews": views, "buffers": [{"byteLength": offset}]}
    js = json.dumps(doc, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    blob = b"".join(blobs)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(blob)))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        f.write(struct.pack("<II", len(blob), 0x004E4942) + blob)
    return count, len(tris), half


def _work_dir():
    path = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()),
                        "Lyris", "Atmosphere")
    os.makedirs(path, exist_ok=True)
    return path


def _mote_mesh(kind):
    """Imports (once) the cloud mesh for `kind`; returns (mesh, actor scale that makes it its true size)."""
    _pos, _nrm, _phase, _tris, half = mote_cloud(kind)
    path = f"{MESH_DIR}/SM_LyrisMotes_{kind.capitalize()}_v{VERSION}"
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        mesh = unreal.load_asset(path)
    else:
        glb = os.path.join(_work_dir(), f"motes_{kind}_v{VERSION}.glb")
        verts, tris, _half = write_mote_glb(glb, kind)
        folder = f"{MESH_DIR}/_Import_{kind}_v{VERSION}"
        w._import_file(glb, folder)
        mesh = next(iter(w._assets_of(folder, unreal.StaticMesh)), None)
        if mesh is None:
            raise RuntimeError(f"mote mesh ({kind}) missing after import")
        unreal.EditorAssetLibrary.rename_asset(mesh.get_path_name().split(".")[0], path)
        mesh = unreal.load_asset(path)
        try:    # plain triangles: the material moves every vertex, which Nanite and distance fields can't follow
            nanite = mesh.get_editor_property("nanite_settings")
            nanite.set_editor_property("enabled", False)
            mesh.set_editor_property("nanite_settings", nanite)
        except Exception as exc:
            _warn(f"motes: could not turn off Nanite on the {kind} mesh ({exc})")
        try:
            sme = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
            build = sme.get_lod_build_settings(mesh, 0)
            build.set_editor_property("distance_field_resolution_scale", 0.0)
            sme.set_lod_build_settings(mesh, 0, build)
        except Exception as exc:
            _warn(f"motes: could not turn off the {kind} mesh distance field ({exc})")
        unreal.EditorAssetLibrary.save_loaded_asset(mesh)
        _log(f"motes: {kind} cloud mesh, {verts} vertices, {tris} triangles")
    # Whatever unit scale the importer used, the cloud must come out its true size (as the sea mesh does).
    extent = mesh.get_bounds().box_extent
    got = max(extent.x, extent.y, 1.0)
    scale = half / got
    if abs(scale - 1.0) > 0.02:
        _warn(f"motes: {kind} mesh imported at {got:.0f} cm half-size (wanted {half:.0f}); scaling the actors "
              f"by {scale:.3f}")
    return mesh, scale


# ----------------------------------------------------------------------------- motes: the material

_DRIFT_HLSL = """float a = Ph.x * 6.2832;
float b = Ph.y * 6.2832;
float3 d;
d.x = sin(T * 0.31 + a) + 0.5 * sin(T * 0.13 + b * 3.0);
d.y = cos(T * 0.27 + b) + 0.5 * sin(T * 0.11 + a * 2.0);
d.z = 0.7 * sin(T * 0.19 + a + b) + 0.4 * sin(T * 0.43 + a * 5.0);
return d * AMP;"""

_GLOW_HLSL = """float soft = abs(dot(normalize(N), normalize(V)));
soft = soft * soft;
float tw = 0.5 + 0.5 * sin(T * (0.9 + Ph.x * 1.4) + Ph.y * 40.0);
tw = 0.15 + 0.85 * tw * tw * tw;
return soft * tw;"""


def _mote_material(kind, colour_key, hex_str):
    """Unlit, additive orbs: each drifts on its own slow path and twinkles, soft at the edge like a spark."""
    spec = MOTES[kind]
    g = w._Graph(f"LyrisMotes_{kind.capitalize()}_{colour_key}", version=VERSION, folder=MAT_DIR)
    if g.exists:
        return g.mat
    w._set(g.mat, "blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    w._set(g.mat, "shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    w._set(g.mat, "two_sided", True)

    phase = g.node(unreal.MaterialExpressionTextureCoordinate, coordinate_index=1)
    time = g.node(unreal.MaterialExpressionTime)
    ct = unreal.CustomMaterialOutputType

    def custom(desc, code, out_type, inputs):
        node = g.node(unreal.MaterialExpressionCustom)
        node.set_editor_property("description", desc)
        node.set_editor_property("output_type", out_type)
        node.set_editor_property("code", code)
        node.set_editor_property("inputs", [w._struct(unreal.CustomInput, input_name=n) for n, _ in inputs])
        for n, src in inputs:
            g.link(src, node, "", n)
        return node

    drift = custom("MoteDrift", _DRIFT_HLSL.replace("AMP", f"{spec['drift_cm']:.1f}"), ct.CMOT_FLOAT3,
                   [("Ph", phase), ("T", time)])
    glow = custom("MoteGlow", _GLOW_HLSL, ct.CMOT_FLOAT1,
                  [("Ph", phase), ("T", time), ("N", g.node(unreal.MaterialExpressionVertexNormalWS)),
                   ("V", g.node(unreal.MaterialExpressionCameraVectorWS))])
    g.out(drift, unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    g.out(g.mul(g.mul(g.colour(hex_str), k=spec["glow"]), glow), unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    return g.done()


# ----------------------------------------------------------------------------- motes: placing them

def _landmark_lights(eas):
    """(location, reach in cm, warm?) of every landmark light in the open level."""
    import lyris_build_landmarks as lm
    found = []
    for actor in eas.get_all_level_actors():
        if not isinstance(actor, unreal.PointLight) or lm.LM_TAG not in w._tags(actor):
            continue
        comp = actor.get_component_by_class(unreal.PointLightComponent)
        loc = actor.get_actor_location()
        reach, warm = 1800.0, False
        try:
            reach = float(comp.get_editor_property("attenuation_radius"))
            colour = comp.get_editor_property("light_color")
            warm = colour.r > colour.b
        except Exception:
            pass
        found.append(((loc.x, loc.y, loc.z), reach, warm))
    return found


def _extra_wonders(trace):
    """Spots from Art/World/landmarks.json that have no light of their own (EXTRA_WONDERS)."""
    spots = []
    try:
        with open(w._project_path(os.path.join("Art", "World", "landmarks.json"))) as f:
            data = json.load(f)
    except Exception as exc:
        _warn(f"motes: could not read landmarks.json ({exc})")
        return spots
    for lm_data in data.get("landmarks", []):
        if lm_data.get("id") in EXTRA_WONDERS and lm_data.get("ue"):
            x, y, z = lm_data["ue"]
            ground = trace(x, y) if trace else None
            spots.append(((x, y, (ground if ground is not None else z) + 300.0), "wonder", False))
    return spots


def mote_spots(lights, extra=()):
    """Turns landmark lights into mote clouds: (location, kind, warm?). Pure Python, so it can be tested.

    A light under the sea (Oruth, the fallen star) puts its motes on the water above it instead. Lights that
    share a spot (two lights on one star) share one cloud. Wonders first, so MOTES_MAX never drops one."""
    spots = []
    for (x, y, z), reach, warm in lights:
        kind = "wonder" if reach >= WONDER_LIGHT_RADIUS else "lamp"
        if z < 0.0:
            kind, z = "wonder", SEA_SURFACE_MOTES_Z
        spots.append(((x, y, z), kind, warm))
    spots.extend(extra)
    spots.sort(key=lambda s: (s[1] != "wonder", s[0]))
    kept = []
    for loc, kind, warm in spots:
        near = MOTES[kind]["radius_m"] * 100.0 * 0.6
        if any(math.dist(loc, other[0]) < near for other in kept):
            continue
        kept.append((loc, kind, warm))
    return kept[:MOTES_MAX]


def build_motes(b, label_prefix, trace=None):
    """Places a mote cloud at every landmark light and wonder in the open level (after the landmarks step)."""
    spots = mote_spots(_landmark_lights(b.eas), _extra_wonders(trace))
    if not spots:
        _warn("motes: no landmark lights in this map yet (build the landmarks step first); nothing placed")
        return 0
    meshes, materials = {}, {}
    rng = random.Random("lyris-motes-yaw")
    counts = {"lamp": 0, "wonder": 0}
    for i, (loc, kind, warm) in enumerate(spots):
        if kind not in meshes:
            meshes[kind] = _mote_mesh(kind)
        key = (kind, warm)
        if key not in materials:
            materials[key] = (_mote_material(kind, "Lampglow", LAMPGLOW_HEX) if warm
                              else _mote_material(kind, "Moonglass", MOONGLASS_HEX))
        mesh, scale = meshes[kind]
        actor = b.eas.spawn_actor_from_object(mesh, unreal.Vector(*loc),
                                              unreal.Rotator(roll=0.0, pitch=0.0, yaw=rng.uniform(0.0, 360.0)))
        if actor is None:
            raise RuntimeError("could not spawn a mote cloud")
        actor.set_actor_scale3d(unreal.Vector(scale, scale, scale))
        actor.set_actor_label(f"{label_prefix}Motes_{kind.capitalize()}{i:02d}")
        actor.set_folder_path("Atmosphere/Motes")
        b.tag(actor, TAG_MOTES)
        w._set(actor, "is_spatially_loaded", False, quiet=True)
        comp = actor.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_material(0, materials[key])
        comp.set_collision_profile_name("NoCollision")
        w._set(comp, "cast_shadow", False, quiet=True)
        w._set(comp, "bounds_scale", 1.5, quiet=True)          # the material drifts the orbs past the mesh's box
        w._set(comp, "affect_distance_field_lighting", False, quiet=True)
        w._set(comp, "visible_in_ray_tracing", False, quiet=True)
        counts[kind] += 1
    _log(f"motes: {counts['lamp']} lamp clouds and {counts['wonder']} wonder columns placed")
    return len(spots)
