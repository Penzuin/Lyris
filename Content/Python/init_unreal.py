"""Runs automatically when the Lyris project opens in the editor.

Builds the Lyris world map (/Game/Lyris/Maps/Lyris) once the editor has finished loading, if its
BUILD_VERSION is newer than the map's; otherwise it only reports what is left to do (for example the
one-time landscape import). See lyris_build_world.py and Art/World/README.md.
"""

import unreal

_handle = None


def _build_once(_delta_seconds):
    global _handle
    unreal.unregister_slate_post_tick_callback(_handle)
    try:
        import lyris_build_world
        lyris_build_world.build(startup=True)
    except Exception as exc:
        unreal.log_error(f"[Lyris] World build failed: {exc}")


_handle = unreal.register_slate_post_tick_callback(_build_once)
