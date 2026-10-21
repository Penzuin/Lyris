"""Editor viewing helper for the Lyris world: load the terrain around a place and point the camera at it.

    import lyris_view as v
    v.go("moonharbor")            # named spots below
    v.go_mc(200, -2300, 120, 300) # any Minecraft-block spot: x, z, camera height above sea (m), distance back (m)
    v.unload()                    # unload what go() loaded, to free memory

Only the landscape near the spot is loaded (World Partition), so this fits an 8 GB GPU.
"""

import math

import unreal

# name: (MC x, MC z, camera height above sea in m, distance back in m, yaw looking toward the spot)
SPOTS = {
    "moonharbor": (200, -2300, 140, 700, 0.0),
    "bay": (-150, -2700, 260, 1300, 180.0),
    "observatory": (1500, -3000, 300, 1500, 200.0),
    "north": (1500, -5200, 500, 2500, 180.0),
    "lake": (-2000, -1300, 400, 2500, 270.0),
    "saltreach": (-5650, 3975, 700, 3500, 45.0),
    "greengrace": (-1300, 3100, 400, 2500, 0.0),
    "sunreach": (4150, 5050, 600, 3500, 300.0),
    "strait": (1200, 1500, 600, 3000, 0.0),
}
_loaded = []


def _proxy_guids_near(x_ue, y_ue, radius_ue):
    lib = unreal.WorldPartitionBlueprintLibrary
    out = []
    for d in lib.get_actor_descs():
        try:
            cls = str(d.get_editor_property("native_class"))
        except Exception:
            cls = ""
        if "Landscape" not in cls:
            continue
        try:
            b = d.get_editor_property("bounds")  # a Box: min / max
            lo, hi = b.get_editor_property("min"), b.get_editor_property("max")
            cx, cy = (lo.x + hi.x) * 0.5, (lo.y + hi.y) * 0.5
        except Exception:
            continue
        if math.hypot(cx - x_ue, cy - y_ue) <= radius_ue:
            out.append(d.get_editor_property("guid"))
    return out


def go_mc(mc_x, mc_z, height_m=150, back_m=600, yaw=0.0, load_radius_m=2500):
    x, y = mc_x * 100.0, mc_z * 100.0
    guids = _proxy_guids_near(x, y, load_radius_m * 100.0)
    if guids:
        unreal.WorldPartitionBlueprintLibrary.load_actors(guids)
        _loaded.extend(guids)
    rad = math.radians(yaw)
    cam = unreal.Vector(x - math.cos(rad) * back_m * 100.0, y - math.sin(rad) * back_m * 100.0, height_m * 100.0)
    pitch = -math.degrees(math.atan2(height_m, back_m)) * 0.8
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    ues.set_level_viewport_camera_info(cam, unreal.Rotator(0.0, pitch, yaw))
    unreal.log(f"[Lyris] view: MC ({mc_x}, {mc_z}), {len(guids)} landscape pieces loaded")


def go(name):
    x, z, h, back, yaw = SPOTS[name]
    go_mc(x, z, h, back, yaw)


def unload():
    if _loaded:
        unreal.WorldPartitionBlueprintLibrary.unload_actors(list(_loaded))
        _loaded.clear()
