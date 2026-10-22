"""Runs automatically when the Lyris project opens in the editor.

Only REPORTS, once the editor has finished loading: on the Moonharbor map (/Game/Lyris/Maps/Moonharbor, the
default map while 1.0 is built, T55) which of its build steps are out of date; on the full world map
(/Game/Lyris/Maps/Lyris) the same for the world. It never rebuilds anything by itself; you run, in the
Output Log (Python):

    import lyris_build_moonharbor as mh; mh.build()      # Moonharbor (or mh.finish() after the landscape import)
    import lyris_build_world as w; w.build()             # the full 25 km world

(Playtest 1: a silent startup rebuild of ~2,000 World Partition actors froze the editor.) It also says if
the editor viewport is on Epic scalability, which does not fit an 8 GB GPU with this world.
See lyris_build_moonharbor.py, lyris_build_world.py and Art/World/README.md.
"""

import unreal

_handle = None

# Scalability groups the editor viewport uses (Settings > Engine Scalability Settings). 3 = Epic.
_SCALABILITY_GROUPS = ("sg.ViewDistanceQuality", "sg.ShadowQuality", "sg.GlobalIlluminationQuality",
                       "sg.ReflectionQuality", "sg.TextureQuality", "sg.EffectsQuality", "sg.FoliageQuality")


def _check_scalability():
    get = getattr(unreal.SystemLibrary, "get_console_variable_int_value", None)
    if get is None:
        return
    try:
        levels = [get(name) for name in _SCALABILITY_GROUPS]
    except Exception:
        return
    if levels and min(levels) >= 3:
        unreal.log_warning("[Lyris] The editor viewport is on Epic scalability, which runs an 8 GB GPU out of "
                           "video memory with this world. Settings (viewport toolbar) > Engine Scalability "
                           "Settings > High, or type in the console:  scalability 2")


def _open_map_path():
    try:
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        return world.get_path_name().split(".")[0] if world else ""
    except Exception:
        return ""


def _report_once(_delta_seconds):
    global _handle
    unreal.unregister_slate_post_tick_callback(_handle)
    try:
        _check_scalability()
    except Exception:
        pass
    try:
        import lyris_build_moonharbor
        if _open_map_path() != "/Game/Lyris/Maps/Lyris":
            lyris_build_moonharbor.report()   # the default map (and the hint to build it if it is missing)
            return
    except Exception as exc:
        unreal.log_error(f"[Lyris] Moonharbor map check failed: {exc}")
    try:
        import lyris_build_world
        lyris_build_world.report()
    except Exception as exc:
        unreal.log_error(f"[Lyris] World map check failed: {exc}")


_handle = unreal.register_slate_post_tick_callback(_report_once)
