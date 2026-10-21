"""Runs automatically when the Lyris project opens in the editor.

Only REPORTS on the Lyris world map (/Game/Lyris/Maps/Lyris) once the editor has finished loading: which
build steps are out of date, and the one Python line to run. It never rebuilds anything by itself; a
rebuild that removes and respawns actors happens only when you run, in the Output Log (Python):

    import lyris_build_world as w; w.build()

(Playtest 1: a silent startup rebuild of ~2,000 World Partition actors froze the editor.) It also says if
the editor viewport is on Epic scalability, which does not fit an 8 GB GPU with this world.
See lyris_build_world.py and Art/World/README.md.
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


def _report_once(_delta_seconds):
    global _handle
    unreal.unregister_slate_post_tick_callback(_handle)
    try:
        _check_scalability()
    except Exception:
        pass
    try:
        import lyris_build_world
        lyris_build_world.report()
    except Exception as exc:
        unreal.log_error(f"[Lyris] World map check failed: {exc}")


_handle = unreal.register_slate_post_tick_callback(_report_once)
