"""Short editor commands for the landscape import workaround (UE 5.7/5.8 World Partition import bug).

    import lyris_go as g
    g.new()      # create and open the Basic (non World Partition) level /Game/Lyris/Maps/LyrisImport
    g.check()    # trace the ground at known spots and compare with the bake (run after the import)
    g.view()     # camera over Moonharbor

Why: in UE 5.7+ a heightmap imported into a World Partition level repeats one corner tile everywhere
(forums.unrealengine.com/t/2745963, also reported in 5.8.0). Importing into a Basic level and then
Tools > Convert Level to World Partition avoids it.
"""

import unreal

IMPORT_MAP = "/Game/Lyris/Maps/LyrisImport"
# name: (MC x, MC z, expected metres above sea from the bake)
SPOTS = {"moonharbor": (200.5, -2287.5, 1.4), "keep": (600, -2600, 68.1), "obs_hill": (1500, -3000, 167.3),
         "bay": (-150, -2700, -100.6), "high_table": (6400, -1300, 108.0)}


def new():
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    ok = les.new_level(IMPORT_MAP, False)
    unreal.log(f"[Lyris] new Basic level {IMPORT_MAP}: {ok}")
    if ok:
        eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        eas.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 50000), unreal.Rotator(0, -40, 0))
        eas.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 40000))
        eas.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector(0, 0, 0))
        unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)


def _ground(x_ue, y_ue):
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    hit = unreal.SystemLibrary.line_trace_single(
        world, unreal.Vector(x_ue, y_ue, 60000), unreal.Vector(x_ue, y_ue, -60000),
        unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [], unreal.DrawDebugTrace.NONE, True)
    return None if hit is None else hit.to_tuple()[4].z / 100.0


def check():
    rows = []
    for name, (mx, mz, want) in SPOTS.items():
        got = _ground(mx * 100.0, mz * 100.0)
        rows.append(f"{name}: got {got if got is None else round(got, 1)} m, bake {want} m")
    unreal.log("[Lyris] CHECK " + " | ".join(rows))


def view(name="moonharbor"):
    import lyris_view
    lyris_view.go(name)


def finish():
    """Makes the imported (non World Partition) map the playable Lyris world, in one call.

    The World Partition conversion ran out of memory on a 16641-component landscape (2+ hours, 99% RAM),
    so the Basic level is used as it is: the build steps go into it, without the World Partition-only
    steps (landmarks, streaming) and the HISM tree foliage (that needs World Partition cells to unload;
    the procedural Landscape Grass still runs near the camera).
    """
    import lyris_build_world as w
    w.MAP_PATH = IMPORT_MAP
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    # new() placed three plain lights; the sky step brings its own tuned sun, atmosphere and sky light
    plain = [a for a in eas.get_all_level_actors()
             if a.get_class().get_name() in ("DirectionalLight", "SkyLight", "SkyAtmosphere")
             and not any(str(t).startswith(w.STEP_TAG_PREFIX) for t in a.tags)]
    if plain:
        eas.destroy_actors(plain)
    w.build(only=["sky", "sea", "water_zone", "lakes", "rivers", "bounds", "player_start", "terrain_look"])
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    check()
    view()
    unreal.log("[Lyris] FINISH done: press Play (Alt+P) to walk the world")
