"""Foliage colours (sRGB hex), shared by the Unreal materials (via species.json) and the offline previews.

Island species keep the Harbor script's FOLIAGE_COLOURS exactly. The biome species reuse hexes that are
already in the house palette (PALETTE / ISLAND_PALETTE in lyris_build_world.py and the painted ramps in
Art/TestIsland/paint_textures.py) wherever one fits. A few new tones are marked NEW: the olive/sage
silver-greens and the snow-dust tint have no existing counterpart. They should be folded into
ISLAND_PALETTE by whoever next edits lyris_build_world.py.
"""

# species: (underside / inside, sunlit top)
CANOPY = {
    "oak":        ("4F7558", "CFE08E"),   # Harbor FOLIAGE_COLOURS
    "bush":       ("547A5A", "CCDE8C"),   # Harbor
    "birch":      ("6C8C5E", "E6EFA4"),   # Harbor
    "pine":       ("36584F", "93B486"),   # Harbor
    "blossom":    ("B87C8C", "FFE6DC"),   # Harbor
    "cherry":     ("C27682", "FBC8B8"),   # blossom ramp, a deeper pink for Greengrace's groves
    "snowpine":   ("36584F", "93B486"),   # pine, plus SNOW on top
    "frostshrub": ("547A5A", "CCDE8C"),   # bush, plus SNOW on top
    "cypress":    ("36584F", "6E9061"),   # pine shade .. ISLAND_PALETTE grass_shade
    "darkwood":   ("36584F", "789A58"),   # pine shade .. leaf ramp: the dark forest
    "olive":      ("6C8650", "B4CC72"),   # grass ramp dark .. birch-leaf ramp: a soft olive green
    "sage":       ("8C9E7C", "C9D3A6"),   # NEW silver-green
    "scrub":      ("6C8650", "C9D3A6"),   # grass ramp dark .. NEW dusty sage
}
SNOW = "F7EEDC"            # PALETTE Sail / LAYER_LOOK Snow
SNOW_SHADE = "EEF3FF"      # Snow layer's cool second colour

BARK = {  # material key: (texture, tint or None)
    "bark":       ("bark", None),
    "birch_bark": ("birch_bark", None),
    "pine_bark":  ("bark", "B89A92"),     # Harbor pine bark tint
    "olive_bark": ("bark", "D6BC9F"),     # rock_lit: pale, weathered
    "dark_bark":  ("bark", "8E7680"),     # rock_shade: lavender-dark
    "char_bark":  ("char_bark", None),
}

PLAIN = {
    "berry":     "B04A6E",                # Harbor
    "mushroom_cap": "D2714E", "mushroom_stem": "F4E8D2",   # Harbor
    "crystal":   "F1E9DC", "crystal_shade": "EEF3FF",      # Salt .. Snow shade
    "vent_rock": "36221A",                # PALETTE Clay / Volcanic layer
    "moss_glow": "E3AE45",                # PALETTE Gold
    "rock_lit":  "D6BC9F", "rock_shade": "8E7680",         # ISLAND_PALETTE
    "grass":     "9DB872", "grass_shade": "6E9061",        # ISLAND_PALETTE
}

# Ground tint for the landscape grass (multiplies the blade colour): written into the grass tint map by
# scatter.py, by biome. Lush meadow 1.0; wheat-gold savanna; dusty badlands; frosted snow edges.
GRASS_TINT = {
    "meadow":   "9DB872",
    "forest":   "6E9061",
    "dry":      "E3C27A",   # NEW wheat gold (between PALETTE Gold E3AE45 and the sand ramp)
    "dusty":    "C9B98E",   # NEW: sand ramp CDB89C nudged toward sage
    "frost":    "DDE6D8",   # snow edge
}


def rgb(hex_str):
    return tuple(int(hex_str[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def as_dict():
    return {"canopy": CANOPY, "snow": SNOW, "snow_shade": SNOW_SHADE, "bark": BARK, "plain": PLAIN,
            "grass_tint": GRASS_TINT}
