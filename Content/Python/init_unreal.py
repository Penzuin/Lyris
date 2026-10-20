"""Runs automatically when the Lyris project opens in the editor.

Builds the Harbor prototype map once, after the editor has finished loading.
"""

import unreal

_handle = None


def _build_once(_delta_seconds):
    global _handle
    unreal.unregister_slate_post_tick_callback(_handle)
    try:
        import lyris_build_harbor
        lyris_build_harbor.build()
    except Exception as exc:
        unreal.log_error(f"[Lyris] Harbor build failed: {exc}")


_handle = unreal.register_slate_post_tick_callback(_build_once)
