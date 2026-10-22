"""Builds Moonharbor (T55): the 1.0 release area as its own small, high-detail Basic level, the default map
while 1.0 is built. The full 25 km world (/Game/Lyris/Maps/Lyris and LyrisImport) stays as it is.

    import lyris_build_moonharbor as mh; mh.build()     # create the map, or bring it up to date (incremental)
    import lyris_build_moonharbor as mh; mh.finish()    # ONE CALL after importing the two landscapes: fixes their
                                                        # placement, builds every step, checks heights, saves
    import lyris_build_moonharbor as mh; mh.import_steps()   # print the landscape import steps again
    import lyris_build_moonharbor as mh; mh.check()     # trace the ground at canon spots and compare with the bake
    import lyris_build_moonharbor as mh; mh.view("pier")     # camera: pier, bay, keep, fields, shore, skerries
    import lyris_build_moonharbor as mh; mh.report()    # what is out of date (changes nothing; runs at startup)
    import lyris_build_moonharbor as mh; mh.build(only=["foliage"])   # redo some steps

Before the editor, in a terminal at the project folder (see Art/World/README.md, "Moonharbor"):
    python Art/World/bake_moonharbor.py               # the landscapes, backdrop, maps (about 6 minutes)
    python Art/World/foliage/make_species.py          # the foliage meshes (once, about 30 s)
    python Art/World/foliage/scatter_moonharbor.py    # the foliage over Moonharbor (about 2 minutes)

What the map gets (a Basic level, not World Partition: at this size everything stays loaded, which also
lets the T51 foliage go in without streaming):
  * two landscapes imported by hand from Art/World/moonharbor (the 1 m Moonharbor square, 1024 components,
    and the 2 m Lampwick Gulf with the Skerries, 128 components), with the T50 look in its Moonharbor copy
    (M_LyrisMoonharborTerrain_v1, its own 1.5 m biome maps);
  * a low-detail backdrop mesh of the whole world round them (vertex-painted, Nanite, walkable);
  * sky and golden-hour light, the T19 sea (MPC_Sea Gerstner clipmap, Moonharbor's ground map for the
    shallows, the home calm zone over Starfall Bay), lakes and upland rivers (Water plugin);
  * the 1.0 landmark blockouts (town, harbour, Lantern Pier, the lighthouse, Syrena's statue, Keep
    Elariel, Oruth, the Teeth, waystone ring A, the Lampwick lamps) and a blockout of the Mistwater Bridge;
  * the T37 gameplay actors, by tag: LyrisPlayerBoat, LyrisDockPoint + LyrisTideHome, LyrisHarborMooring,
    LyrisDockLamp, and the PlayerStart on Lantern Pier;
  * the T51 foliage (trees, bushes, flowers, rocks; Landscape Grass from the material), 512 m cells;
  * invisible walls round the 1.0 waters and land, kill Z.

Most steps reuse lyris_build_world.py's own step code (sky, sea, lakes, rivers, player start, boat and dock)
by pointing it at this map for the call (see _as_moonharbor). Each step is versioned on this map's marker
(LyrisMoonharbor_v<BUILD_VERSION>); build() redoes only what changed. Coordinates are the world's
(design/world_map.md), so tags, landmarks and positions match the full world 1:1.
"""

import contextlib
import json
import math
import os

import unreal

import lyris_build_world as w

BUILD_VERSION = 1
MAP_PATH = "/Game/Lyris/Maps/Moonharbor"
MH_DIR = "Art/World/moonharbor"
MANIFEST = "moonharbor_manifest.json"
MESH_DIR = "/Game/Lyris/Meshes/Moonharbor"
MAT_DIR = "/Game/Lyris/Materials/Moonharbor"
TERRAIN_MAT = "M_LyrisMoonharborTerrain_v1"
TERRAIN_TEX_DIR = "/Game/Lyris/Textures/MoonharborTerrain"
SCATTER_DIR = f"{MH_DIR}/scatter"

# Landmarks on: the T55 brief places the 1.0 blockouts and starts the player on Lantern Pier. (The full world
# map hides its blockouts, DECISIONS 2026-10-20; set False here to do the same: the player then starts on land.)
LANDMARKS_VISIBLE = True

STEP_VERSIONS = {
    "sky": 1, "sea": 1, "water_zone": 1, "lakes": 1, "rivers": 1, "bounds": 1, "backdrop": 1,
    "terrain_look": 1, "landmarks": 1, "bridges": 1, "player_start": 1, "boat_dock": 1, "foliage": 1,
}
STEP_ORDER = ["sky", "sea", "water_zone", "lakes", "rivers", "bounds", "backdrop", "terrain_look", "landmarks",
              "bridges", "player_start", "boat_dock", "foliage"]
WORLD_STEPS = ("sky", "sea", "lakes", "rivers", "player_start", "boat_dock")   # lyris_build_world's own code
MARKER_PREFIX = "LyrisMoonharbor_v"
MARKER_TAG = "LyrisMoonharborMarker"
STEP_VER_TAG = "LyrisMHStepVer_"
STEP_TAG = "LyrisMHStep_"
LABEL_PREFIX = "LW_MH_"
TAG = w.TAG  # LyrisWorldBuild

VIEWS = {  # name: (MC x, MC z, camera height above sea m, distance back m, yaw toward the spot)
    "pier": (140, -2404, 25, 90, 0.0),
    "town": (300, -2350, 120, 500, 300.0),
    "bay": (-170, -2650, 180, 900, 120.0),
    "keep": (480, -2560, 160, 650, 10.0),
    "fields": (700, -1700, 120, 700, 290.0),
    "shore": (-560, -3150, 140, 800, 160.0),
    "skerries": (-2500, -4560, 120, 900, -20.0),
}


def _log(msg):
    unreal.log("[Lyris] " + msg)


def _warn(msg):
    unreal.log_warning("[Lyris] " + msg)


def _project_path(rel):
    return os.path.join(unreal.Paths.project_dir(), rel)


def load_manifest():
    path = _project_path(os.path.join(MH_DIR, MANIFEST))
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _eas():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def _les():
    return unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)


def _map_is_open():
    try:
        world = w._editor_world()
        return world is not None and world.get_path_name().split(".")[0] == MAP_PATH
    except Exception:
        return False


def _open_or_create_map():
    """Opens /Game/Lyris/Maps/Moonharbor, creating it as a Basic (non World Partition) level the first time."""
    les = _les()
    if unreal.EditorAssetLibrary.does_asset_exist(MAP_PATH):
        if _map_is_open():
            return True
        unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
        return les.load_level(MAP_PATH)
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    try:
        ok = les.new_level(MAP_PATH, False)   # (asset path, is_partitioned_world): a Basic level
    except TypeError:
        ok = les.new_level(MAP_PATH)
    if ok:
        _log(f"created the Basic level {MAP_PATH}")
        les.save_current_level()
    return ok


# ----------------------------------------------------------------------------- the landscape import

def import_steps(manifest=None):
    """Logs the exact steps for the one manual part: importing the two landscapes."""
    m = manifest or load_manifest()
    if m is None:
        _warn("no Moonharbor bake found. First, in a terminal at the project folder:\n"
              "    python Art/World/bake_moonharbor.py\n"
              "then run lyris_build_moonharbor.build() again.")
        return
    folder = unreal.Paths.convert_relative_path_to_full(_project_path(MH_DIR))
    lines = ["MOONHARBOR LANDSCAPE IMPORT (once, by hand, about 5 minutes). The Moonharbor map is open; in it:"]
    if m.get("preview"):
        lines.append(" !! The bake is a PREVIEW (4 m): run  python Art/World/bake_moonharbor.py  (no --preview) first.")
    for k, L in enumerate(m["landscapes"]):
        cx, cy, cz = L["location_centre"]
        sx, sy, sz = L["scale"]
        qx, qz = L["components"]
        spc = L["sections_per_component"]
        lines += [
            f" {chr(65 + k)}. {L['name']} ({L['resolution'][0]} x {L['resolution'][1]}, {L['metres_per_vertex']:.0f} m per vertex):",
            "    Selection Mode dropdown (top left) > Landscape. Manage tab > New > Import from File.",
            f"    Heightmap File: {os.path.join(folder, L['file'])}   (answer NO if asked about a tiled image; Flip Y off)",
            "    Material: leave empty; no paint layers (the terrain look reads its own biome maps).",
            f"    Location X {cx:.0f}  Y {cy:.0f}  Z {cz:.0f}    Rotation 0 0 0    Scale X {sx:.0f}  Y {sy:.0f}  Z {sz:.0f}",
            f"    Section Size {L['quads_per_section']}x{L['quads_per_section']} Quads, Sections Per Component "
            f"{spc}x{spc}, Number of Components {qx} x {qz} (Overall Resolution {L['resolution'][0]} x {L['resolution'][1]}).",
            "    Press Import.",
        ]
    lines += [
        " C. Switch back to Selection Mode (Shift+1).",
        " D. Python:  import lyris_build_moonharbor as mh; mh.finish()",
        "    (it snaps both landscapes to their exact place if the importer moved them, builds everything, checks",
        "    the heights against the bake and saves; then press Play)",
    ]
    for line in lines:
        _log(line)


def _landscapes():
    return [a for a in _eas().get_all_level_actors() if isinstance(a, unreal.LandscapeProxy)]


def _match_landscapes(m):
    """{manifest landscape name: actor} by size (the 4 km square vs the 2 x 1 km gulf)."""
    found = {}
    for actor in _landscapes():
        try:
            origin, extent = actor.get_actor_bounds(False)
        except Exception:
            continue
        for L in m["landscapes"]:
            want_x = (L["resolution"][0] - 1) * L["metres_per_vertex"] * 50.0
            want_y = (L["resolution"][1] - 1) * L["metres_per_vertex"] * 50.0
            if abs(extent.x - want_x) < 300.0 and abs(extent.y - want_y) < 300.0 and L["name"] not in found:
                found[L["name"]] = actor
                break
    return found


def place_landscapes(m=None):
    """Moves each imported landscape so its first vertex sits exactly on the manifest's corner (the import
    dialog's Location is easy to misread). Returns the matched actors."""
    m = m or load_manifest()
    found = _match_landscapes(m)
    for L in m["landscapes"]:
        actor = found.get(L["name"])
        if actor is None:
            _warn(f"landscape {L['name']} not found in the map (import it: mh.import_steps())")
            continue
        origin, extent = actor.get_actor_bounds(False)
        min_x, min_y = origin.x - extent.x, origin.y - extent.y
        want_x, want_y = L["location_corner"][0], L["location_corner"][1]
        dx, dy = want_x - min_x, want_y - min_y
        loc = actor.get_actor_location()
        dz = L["location_centre"][2] - loc.z
        if abs(dx) > 50.0 or abs(dy) > 50.0 or abs(dz) > 50.0:
            actor.set_actor_location(unreal.Vector(loc.x + dx, loc.y + dy, loc.z + dz), False, False)
            _log(f"{L['name']}: moved by ({dx / 100:.1f}, {dy / 100:.1f}, {dz / 100:.1f}) m onto its corner "
                 f"({want_x / 100:.0f}, {want_y / 100:.0f})")
        scale = actor.get_actor_scale3d()
        if abs(scale.x - L["scale"][0]) > 0.5 or abs(scale.z - L["scale"][2]) > 0.5:
            _warn(f"{L['name']}: scale is {scale.x:.1f} x {scale.y:.1f} x {scale.z:.1f}, expected "
                  f"{L['scale'][0]:.0f} x {L['scale'][1]:.0f} x {L['scale'][2]:.0f}: delete it and import again")
        try:
            actor.set_actor_label(f"Landscape_{L['name']}")
            actor.set_folder_path("Terrain")
        except Exception:
            pass
        w._set(actor, "enable_nanite", True, quiet=True)
        w._set(actor, "cast_far_shadow", True, quiet=True)
    return found


# ----------------------------------------------------------------------------- reusing lyris_build_world

@contextlib.contextmanager
def _as_moonharbor(m, steps):
    """Points lyris_build_world at this map, its manifest and its sea ground map for one build(only=...) call."""
    fr = m["sea_ground"]
    world_manifest = dict(m)
    world_manifest["scale"] = m["landscapes"][0]["scale"]
    saved = {k: getattr(w, k) for k in ("MAP_PATH", "load_manifest", "import_steps", "_finish_landscape",
                                        "SEA_GROUND_SOURCES", "SEA_GROUND_BOUNDS_CM", "LANDMARKS_VISIBLE",
                                        "STEP_ORDER")}
    w.MAP_PATH = MAP_PATH
    w.load_manifest = lambda: world_manifest
    w.import_steps = lambda manifest=None: None   # build() prints Moonharbor's own import steps once, at the end
    w._finish_landscape = lambda *a, **k: None
    w.SEA_GROUND_SOURCES = [("Moonharbor", f"{MH_DIR}/{fr['file']}", fr["scale_m"], fr["offset_m"])]
    w.SEA_GROUND_BOUNDS_CM = (fr["min_ue"][0], fr["min_ue"][1], fr["size_ue"])
    w.LANDMARKS_VISIBLE = LANDMARKS_VISIBLE
    w.STEP_ORDER = list(steps)
    try:
        yield
    finally:
        for k, v in saved.items():
            setattr(w, k, v)


@contextlib.contextmanager
def _terrain_variant():
    import importlib
    import lyris_world_terrain as t
    importlib.reload(t)
    with t.variant(TERRAIN_MAT, f"{MH_DIR}/biome", TERRAIN_TEX_DIR):
        yield t


# ----------------------------------------------------------------------------- our own steps

class _Builder(w._Builder):
    def tag(self, actor, *extra):
        names = [TAG] + ([STEP_TAG + self.step] if self.step else []) + list(extra)
        w._set(actor, "tags", [unreal.Name(n) for n in names])

    def spawn(self, cls, label, loc=(0, 0, 0), rot=(0, 0, 0), folder="Moonharbor", always_loaded=True):
        actor = super().spawn(cls, label, loc, rot, folder, always_loaded)
        actor.set_actor_label(LABEL_PREFIX + label)
        return actor

    def cube(self, label, loc, scale, folder, rot=(0, 0, 0)):
        actor = super().cube(label, loc, scale, folder)
        actor.set_actor_label(LABEL_PREFIX + label)
        if any(rot):
            actor.set_actor_rotation(unreal.Rotator(roll=rot[0], pitch=rot[1], yaw=rot[2]), False)
        return actor


def _step_actors(step):
    out = []
    for a in _eas().get_all_level_actors():
        if f"{STEP_TAG}{step}" in w._tags(a):
            out.append(a)
    return out


def _step_water_zone(b, m):
    if not hasattr(unreal, "WaterZone"):
        raise RuntimeError("Water plugin classes not found; enable the Water plugin")
    xs, ys = [], []
    for lake in m.get("lakes", []):
        for x, y in lake["outline_ue"]:
            xs.append(x)
            ys.append(y)
    for r in m.get("rivers", []):
        for p in r["points_ue"]:
            xs.append(p[0])
            ys.append(p[1])
    if not xs:
        _log("water zone: no lakes or rivers")
        return
    pad = 50000.0
    x0, x1, y0, y1 = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
    zone = b.spawn(unreal.WaterZone, "WaterZone", ((x0 + x1) / 2, (y0 + y1) / 2, 0), folder="Water")
    if not w._set(zone, "zone_extent", unreal.Vector2D(x1 - x0, y1 - y0), quiet=True):
        _warn(f"WaterZone: set Zone Extent by hand to {x1 - x0:.0f} x {y1 - y0:.0f}")
    w._set(zone, "render_target_resolution", unreal.IntPoint(2048, 2048), quiet=True)
    _log(f"water zone {(x1 - x0) / 100000:.1f} x {(y1 - y0) / 100000:.1f} km")


def _step_bounds(b, m):
    ws = w._editor_world().get_world_settings()
    w._set(ws, "enable_world_bounds_checks", True, quiet=True)
    w._set(ws, "kill_z", -20000.0, quiet=True)   # 200 m under the sea; Oruth's pit floor is 103 m down
    x0, y0, x1, y1 = m["bounds_ue"]
    t = 1000.0
    for name, loc, scale in (("North", ((x0 + x1) / 2, y0, 40000), ((x1 - x0) / 100.0, t / 100.0, 1000)),
                             ("South", ((x0 + x1) / 2, y1, 40000), ((x1 - x0) / 100.0, t / 100.0, 1000)),
                             ("West", (x0, (y0 + y1) / 2, 40000), (t / 100.0, (y1 - y0) / 100.0, 1000)),
                             ("East", (x1, (y0 + y1) / 2, 40000), (t / 100.0, (y1 - y0) / 100.0, 1000))):
        wall = b.cube(f"Edge_{name}", loc, scale, "Moonharbor/Bounds")
        comp = wall.get_component_by_class(unreal.StaticMeshComponent)
        comp.set_visibility(False)
        comp.set_editor_property("cast_shadow", False)
        comp.set_collision_profile_name("BlockAll")
        wall.set_actor_hidden_in_game(True)
    _log(f"bounds: walls round X {x0 / 100:.0f}..{x1 / 100:.0f}, Z {y0 / 100:.0f}..{y1 / 100:.0f} (MC); kill Z -200 m")


def _backdrop_material():
    g = w._Graph("LyrisBackdrop", version=1, folder=MAT_DIR)
    if g.exists:
        return g.mat
    vc = g.node(unreal.MaterialExpressionVertexColor)
    g.out(vc, unreal.MaterialProperty.MP_BASE_COLOR, "")  # RGB of the vertex colour
    g.out(g.const(0.95), unreal.MaterialProperty.MP_ROUGHNESS)
    return g.done()


def _backdrop_mesh(m):
    path = f"{MESH_DIR}/SM_MoonharborBackdrop_v{STEP_VERSIONS['backdrop']}"
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        return unreal.load_asset(path)
    src = _project_path(os.path.join(MH_DIR, m["backdrop"]["file"]))
    if not os.path.exists(src):
        raise RuntimeError(f"{src} is missing: run python Art/World/bake_moonharbor.py")
    folder = f"{MESH_DIR}/_Import_v{STEP_VERSIONS['backdrop']}"
    _log(f"importing the backdrop ({m['backdrop']['vertices']} vertices; can take a few minutes)")
    w._import_file(src, folder)
    mesh = next(iter(w._assets_of(folder, unreal.StaticMesh)), None)
    if mesh is None:
        raise RuntimeError("backdrop mesh missing after import")
    unreal.EditorAssetLibrary.rename_asset(mesh.get_path_name().split(".")[0], path)
    mesh = unreal.load_asset(path)
    try:
        nanite = mesh.get_editor_property("nanite_settings")
        nanite.set_editor_property("enabled", True)
        mesh.set_editor_property("nanite_settings", nanite)
    except Exception as exc:
        _warn(f"backdrop: could not turn Nanite on ({exc}); Static Mesh editor > Nanite Settings > Enable")
    try:  # walkable: use the mesh itself as its collision
        body = mesh.get_editor_property("body_setup")
        body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    except Exception as exc:
        _warn(f"backdrop: could not set Complex as Simple collision ({exc}); set it in the Static Mesh editor")
    mesh.set_material(0, _backdrop_material())
    unreal.EditorAssetLibrary.save_loaded_asset(mesh)
    return mesh


def _trace_z(x, y, ignore_landscapes=False):
    world = w._editor_world()
    try:
        hits = unreal.SystemLibrary.line_trace_multi(world, unreal.Vector(x, y, 60000.0), unreal.Vector(x, y, -30000.0),
                                                     unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [],
                                                     unreal.DrawDebugTrace.NONE, True)
    except Exception:
        return None
    for hit in hits or []:
        try:
            t = hit.to_tuple()
            loc, actor = t[5], t[9]
        except Exception:
            continue
        if ignore_landscapes and isinstance(actor, unreal.LandscapeProxy):
            continue
        return loc.z
    return None


def _step_backdrop(b, m):
    mesh = _backdrop_mesh(m)
    actor = b.eas.spawn_actor_from_object(mesh, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    actor.set_actor_label(LABEL_PREFIX + "Backdrop")
    actor.set_folder_path("Terrain")
    b.tag(actor)
    comp = actor.get_component_by_class(unreal.StaticMeshComponent)
    w._set(comp, "cast_shadow", True, quiet=True)
    # Units: glTF metres should arrive as cm (x100). If the importer kept metres, scale the actor.
    extent = mesh.get_bounds().box_extent
    s = 1.0 if extent.x > 500000.0 else 100.0
    if s != 1.0:
        _warn(f"backdrop imported at {extent.x:.0f} cm half size; scaling the actor x{s:.0f}")
    actor.set_actor_scale3d(unreal.Vector(s, s, s))
    # Orientation: trace three high spots whose mirror images are low; flip X or Y if the importer mirrored it.
    probes = m["backdrop"].get("probes_mc", [])
    best, best_err = (1.0, 1.0), None
    for sx, sy in ((1.0, 1.0), (1.0, -1.0), (-1.0, 1.0), (-1.0, -1.0)):
        actor.set_actor_scale3d(unreal.Vector(s * sx, s * sy, s))
        err = 0.0
        for px, pz, ph in probes:
            z = _trace_z(px * 100.0, pz * 100.0, ignore_landscapes=True)
            err += 1e4 if z is None else abs(z / 100.0 - ph)   # probes lie outside the landscapes: not sunk
        if best_err is None or err < best_err:
            best, best_err = (sx, sy), err
    actor.set_actor_scale3d(unreal.Vector(s * best[0], s * best[1], s))
    if probes:
        _log(f"backdrop: orientation {best} (probe error {best_err / max(len(probes), 1):.1f} m per probe)")
        if best_err / max(len(probes), 1) > 30.0:
            _warn("backdrop: the probe heights do not match; check the backdrop against the landscapes by eye")


def _step_terrain_look(b, m):
    with _terrain_variant() as t:
        t.build()
        t.apply()


def _step_landmarks(b, m):
    import importlib
    import lyris_build_landmarks as lm
    importlib.reload(lm)
    ids = m.get("landmarks_1_0", [])
    if lm.place({"bake_version": 2}, only=ids) is None:
        raise RuntimeError("cancelled while placing landmarks")
    w.tag_dock_lamp(_eas())
    if not LANDMARKS_VISIBLE:
        w.set_landmarks_visible(False)
    _log(f"landmarks: {len(ids)} in 1.0 ({', '.join(ids)})")


def _step_bridges(b, m):
    import lyris_build_landmarks as lm
    wood, dark = lm._material("Wood"), lm._material("DarkWood")
    for k, br in enumerate(m.get("bridges", [])):
        (ax, az), (bx, bz) = br["from_mc"], br["to_mc"]
        length = math.hypot(bx - ax, bz - az) + 4.0
        yaw = math.degrees(math.atan2(bz - az, bx - ax))
        cx, cz, deck = (ax + bx) / 2 * 100.0, (az + bz) / 2 * 100.0, br["deck_m"] * 100.0
        width = br.get("width_m", 4.0)
        parts = [("Deck", (cx, cz, deck - 25.0), (length, width, 0.5), wood)]
        nx, nz = -math.sin(math.radians(yaw)), math.cos(math.radians(yaw))
        for side in (-1, 1):
            off = side * (width / 2 - 0.15) * 100.0
            parts.append((f"Rail{side:+d}", (cx + nx * off, cz + nz * off, deck + 55.0), (length, 0.15, 0.15), dark))
        n_posts = max(2, int(length // 6))
        for i in range(n_posts + 1):
            t = i / n_posts - 0.5
            px, pz = cx + math.cos(math.radians(yaw)) * t * (length - 1) * 100.0, cz + math.sin(math.radians(yaw)) * t * (length - 1) * 100.0
            parts.append((f"Pile{i}", (px, pz, deck - 300.0), (0.4, 0.4, 5.6), dark))
        for name, loc, scale, mat in parts:
            actor = b.cube(f"Bridge{k}_{name}", loc, scale, f"Moonharbor/Bridges/{br['name']}", rot=(0, 0, yaw))
            actor.get_component_by_class(unreal.StaticMeshComponent).set_material(0, mat)
        _log(f"bridge: {br['name']}, {length:.0f} m, deck {br['deck_m']:.1f} m above the sea")


def _step_foliage(b, m):
    import importlib
    import lyris_world_foliage as f
    importlib.reload(f)
    if not os.path.exists(_project_path(f"{SCATTER_DIR}/summary.json")):
        raise RuntimeError("no Moonharbor scatter yet: run python Art/World/foliage/make_species.py, then "
                           "python Art/World/foliage/scatter_moonharbor.py")
    f.MAP_PATH = MAP_PATH
    f.SCATTER_DIR = SCATTER_DIR
    with _terrain_variant():   # the foliage step wires the grass into the terrain material: Moonharbor's copy
        f.build()


OWN_STEPS = {"water_zone": _step_water_zone, "bounds": _step_bounds, "backdrop": _step_backdrop,
             "terrain_look": _step_terrain_look, "landmarks": _step_landmarks, "bridges": _step_bridges,
             "foliage": _step_foliage}


# ----------------------------------------------------------------------------- marker and versions

def _marker():
    for a in _eas().get_all_level_actors():
        if w._label(a).startswith(MARKER_PREFIX):
            return a
    return None


def _recorded(marker):
    found = {}
    for t in w._tags(marker) if marker is not None else []:
        if t.startswith(STEP_VER_TAG):
            step, _, ver = t[len(STEP_VER_TAG):].rpartition("_")
            try:
                found[step] = int(ver)
            except ValueError:
                pass
    return found


def _record(marker, step):
    tags = [t for t in w._tags(marker) if not t.startswith(f"{STEP_VER_TAG}{step}_")]
    tags.append(f"{STEP_VER_TAG}{step}_{STEP_VERSIONS[step]}")
    w._set(marker, "tags", [unreal.Name(t) for t in tags])


def outdated(recorded):
    return [s for s in STEP_ORDER if recorded.get(s, 0) != STEP_VERSIONS[s]]


def report():
    """What init_unreal.py runs when the editor opens on this map: says what is out of date, changes nothing."""
    run = "import lyris_build_moonharbor as mh; mh.build()"
    if not unreal.EditorAssetLibrary.does_asset_exist(MAP_PATH):
        _log(f"the Moonharbor map is not built on this PC yet. In the Output Log (Python):  {run}")
        return
    if not _map_is_open():
        _log(f"the open level is not {MAP_PATH}; open it, or run:  {run}")
        return
    marker = _marker()
    todo = outdated(_recorded(marker))
    found = _match_landscapes(load_manifest() or {"landscapes": []})
    if len(found) < 2:
        _log("Moonharbor: the landscapes are not imported yet; mh.import_steps() prints how")
    if todo:
        _warn(f"Moonharbor map: steps to build: {', '.join(todo)}. Nothing was changed. Selection Mode (Shift+1), "
              f"then in the Output Log (Python):  {run}")
    else:
        _log(f"Moonharbor map is up to date (v{BUILD_VERSION})")


def build(force=False, only=None, check_mode=True):
    """Builds what is out of date, one step at a time; each finished step is saved.

    force=True  redo every step;  only=[...]  redo just these steps (names in STEP_ORDER)."""
    m = load_manifest()
    if m is None:
        import_steps(None)
        return
    if m.get("preview"):
        _warn("the Moonharbor bake is a PREVIEW (4 m per vertex). Rebake before importing: python Art/World/bake_moonharbor.py")
    if not _open_or_create_map():
        unreal.log_error(f"[Lyris] could not open or create {MAP_PATH}")
        return
    eas = _eas()
    if check_mode and not w.leave_editor_modes(eas):
        return
    marker = _marker()
    b = _Builder()
    if marker is None:
        b.step = None
        marker = b.spawn(unreal.Note, "Marker", (0, 0, 50000), folder="Moonharbor")
        marker.set_actor_label(f"{MARKER_PREFIX}0")
        w._add_tags(marker, MARKER_TAG)
        w._set(marker, "text", "Built by Content/Python/lyris_build_moonharbor.py from Art/World/moonharbor. Its tags "
                               "record each step's version; edits to actors a step places are lost when it is rebuilt.",
               quiet=True)
    recorded = _recorded(marker)
    if only is not None:
        only = [only] if isinstance(only, str) else list(only)
        bad = [s for s in only if s not in STEP_VERSIONS]
        if bad:
            unreal.log_error(f"[Lyris] unknown steps {bad}; the steps are: {', '.join(STEP_ORDER)}")
            return
        steps = [s for s in STEP_ORDER if s in only]
    elif force:
        steps = list(STEP_ORDER)
    else:
        steps = outdated(recorded)
    if len(_match_landscapes(m)) < 2:
        # Without the landscapes, traced blockouts and foliage would float: build only what does not stand on them.
        later = [s for s in steps if s in ("landmarks", "bridges", "player_start", "boat_dock", "foliage", "terrain_look")]
        steps = [s for s in steps if s not in later]
        if later:
            _log(f"waiting for the landscapes before: {', '.join(later)}")
    if not steps:
        _log(f"Moonharbor map is up to date (v{BUILD_VERSION})")
    done, failed = [], []
    for step in steps:
        try:
            if step in WORLD_STEPS:
                with _as_moonharbor(m, [step]):
                    w.build(only=[step], check_mode=False)
                ok = w._marker(eas) is not None and w._recorded_steps(w._marker(eas)).get(step) == w.STEP_VERSIONS[step]
                if not ok:
                    raise RuntimeError("lyris_build_world reported a problem (see the warnings above)")
            else:
                b.step = step
                w.destroy_in_batches(eas, _step_actors(step), step)
                OWN_STEPS[step](b, m)
                b.step = None
        except Exception as exc:
            _warn(f"could not build {step}: {exc}")
            failed.append(step)
            continue
        _record(marker, step)
        done.append(step)
        _les().save_current_level()
        _log(f"Moonharbor: built {step}")
    left = outdated(_recorded(marker))
    if not left:
        marker.set_actor_label(f"{MARKER_PREFIX}{BUILD_VERSION}")
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    if left:
        _warn(f"Moonharbor map not finished: {', '.join(left)} still to do"
              + (f" ({', '.join(failed)} failed: see the warnings above)" if failed else "") + ". Run mh.build() again")
    else:
        _log(f"Moonharbor map v{BUILD_VERSION} ready at {MAP_PATH}")
    if len(_match_landscapes(m)) < 2:
        import_steps(m)


# ----------------------------------------------------------------------------- checks and the one call

def check():
    """Traces the ground at the canon spots and compares with the bake (manifest canon_checks)."""
    m = load_manifest()
    rows, worst = [], 0.0
    for name, c in m.get("canon_checks", {}).items():
        x, z = c["mc"]
        got = _trace_z(x * 100.0, z * 100.0)
        if got is None:
            rows.append(f"{name}: no ground")
            worst = 1e9
            continue
        # The trace hits the highest thing there (a blockout can stand on the spot): report both.
        delta = got / 100.0 - c["ground_m"]
        rows.append(f"{name}: {got / 100.0 + 63.0:.1f} (bake {c['ground_mc_y']})")
        if abs(delta) > worst and abs(delta) < 15.0:
            worst = abs(delta)
    _log("CHECK MC Y (trace vs bake): " + " | ".join(rows))
    if worst > 1.0:
        _warn(f"the ground is up to {worst:.1f} m off the bake somewhere: check the landscape location and scale")
    return worst


def view(name="pier"):
    x, z, hgt, back, yaw = VIEWS[name]
    rad = math.radians(yaw)
    cam = unreal.Vector(x * 100.0 - math.cos(rad) * back * 100.0, z * 100.0 - math.sin(rad) * back * 100.0, hgt * 100.0)
    pitch = -math.degrees(math.atan2(hgt, back)) * 0.8
    try:
        unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).set_level_viewport_camera_info(cam, unreal.Rotator(0.0, pitch, yaw))
    except Exception as exc:
        _warn(f"could not move the camera ({exc})")


def finish():
    """One call after importing the two landscapes: placement, every step, checks, save, camera on the pier."""
    m = load_manifest()
    if m is None:
        import_steps(None)
        return
    if not _open_or_create_map():
        return
    found = place_landscapes(m)
    if len(found) < 2:
        _warn("import both landscapes first:")
        import_steps(m)
        return
    build()
    check()
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    view("pier")
    _log("FINISH done: press Play (Alt+P). The map opens by itself next time (Config/DefaultEngine.ini)")
