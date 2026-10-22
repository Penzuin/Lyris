import json, sys, numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from scipy import ndimage
ATLAS, OUT = sys.argv[1], sys.argv[2]
data = json.load(open(f"{OUT}/chunks.json")); ch = data["chunks"]; waves = data["waves"]
lab = np.load(f"{OUT}/lab.npy"); sea = np.load(f"{OUT}/sea.npy")
WAVE_COL = {"1.0": (214, 92, 70), "1.1": (232, 160, 62), "1.2": (226, 202, 92), "1.3": (150, 186, 92),
            "1.4": (120, 170, 196), "1.5": (110, 140, 120), "2.0": (176, 124, 172), "3.0": (98, 120, 186),
            "4.0": (150, 150, 150)}
land_ids = [c for c in ch if "land_km2" in c]
F = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"; FB = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
def font(p, s):
    try: return ImageFont.truetype(p, s)
    except Exception: return ImageFont.load_default()

def draw(path, x0, x1, z0, z1, W, label_size, title, sub, focus10=False):
    base = Image.open(f"{ATLAS}/painted.jpg").convert("RGB")
    P = base.size[0]
    px = lambda b: (b + 12500) * P / 25000
    box = (int(px(x0)), int(px(z0)), int(px(x1)), int(px(z1)))
    img = base.crop(box)
    H = int(W * (z1 - z0) / (x1 - x0)); img = img.resize((W, H), Image.LANCZOS)
    # chunk ids resampled to the crop
    def crop_mask(a):
        im = Image.fromarray(a.astype(np.int16) + 1)  # -1 -> 0
        m = np.array(Image.fromarray((a + 1).astype(np.uint16)).resize((P, P), Image.NEAREST))
        return m[box[1]:box[3], box[0]:box[2]]
    L = np.array(Image.fromarray(crop_mask(lab).astype(np.int32)).resize((W, H), Image.NEAREST)) - 1
    S = np.array(Image.fromarray(crop_mask(sea).astype(np.int32)).resize((W, H), Image.NEAREST)) - 1
    a = np.array(img).astype(float)
    # tint by wave
    ids = [c["id"] for c in ch]
    for i, c in enumerate(land_ids):
        m = L == i
        col = np.array(WAVE_COL[c["wave"]])
        alpha = 0.42 if c["wave"] == "1.0" else (0.18 if focus10 else 0.32)
        a[m] = a[m] * (1 - alpha) + col * alpha
    for j, c in enumerate([c for c in ch if "water_km2" in c]):
        m = S == j
        a[m] = a[m] * 0.72 + np.array((236, 208, 140)) * 0.28
    # dim everything outside 1.0 in the focus view
    if focus10:
        w10 = np.isin(L, [i for i, c in enumerate(land_ids) if c["wave"] == "1.0"]) | (S >= 0)
        a[~w10] = a[~w10] * 0.55 + 120 * 0.45
    # subarea borders (thin) and wave borders (thick)
    wv = np.full(L.shape, -1); 
    for i, c in enumerate(land_ids): wv[L == i] = list(waves).index(c["wave"])
    wv[S >= 0] = 0
    def edges(arr):
        e = np.zeros(arr.shape, bool)
        e[1:] |= (arr[1:] != arr[:-1]) & (arr[1:] >= 0) & (arr[:-1] >= 0)
        e[:, 1:] |= (arr[:, 1:] != arr[:, :-1]) & (arr[:, 1:] >= 0) & (arr[:, :-1] >= 0)
        return e
    e1 = edges(L); e2 = edges(wv)
    e2 = ndimage.binary_dilation(e2, iterations=max(1, W // 900))
    a[e1] = a[e1] * 0.3 + np.array((255, 250, 235)) * 0.7
    a[e2] = (90, 40, 30)
    # outline of 1.0 (land + sea)
    in10 = np.isin(L, [i for i, c in enumerate(land_ids) if c["wave"] == "1.0"]) | (S >= 0)
    o = ndimage.binary_dilation(in10, iterations=max(2, W // 500)) & ~in10
    a[o] = (170, 30, 30)
    img = Image.fromarray(a.clip(0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    f = font(F, label_size); fb = font(FB, int(label_size * 1.05))
    tx = lambda b: (b - x0) / (x1 - x0) * W; tz = lambda b: (b - z0) / (z1 - z0) * H
    def label(x, z, text, fnt, fill=(40, 25, 20)):
        X, Zp = tx(x), tz(z)
        if not (0 <= X <= W and 0 <= Zp <= H): return
        bb = d.textbbox((0, 0), text, font=fnt); w, h = bb[2] - bb[0], bb[3] - bb[1]
        for dx in (-2, -1, 0, 1, 2):
            for dy in (-2, -1, 0, 1, 2):
                d.text((X - w / 2 + dx, Zp - h / 2 + dy), text, font=fnt, fill=(250, 244, 228))
        d.text((X - w / 2, Zp - h / 2), text, font=fnt, fill=fill)
    for c in ch:
        if "centre" in c:
            cx, cz = c["centre"]
        else:
            cx, cz = c["circles"][0][0], c["circles"][0][1]
        if c["id"] == "M1": cx, cz = 300, -2190
        if c["id"] == "M2" and focus10: cx, cz = 1150, -2330
        if c["id"] == "H1": cx, cz = -150, -2780
        if c["id"] == "H2": cx, cz = -1100, -4300
        txt = f'{c["id"]}  {c["name"]}' if focus10 else c["id"]
        label(cx, cz + (90 if c["id"]=="M1" and not focus10 else 0), txt, fb if c["wave"] == "1.0" else f,
              (150, 20, 20) if c["wave"] == "1.0" else (40, 25, 20))
    # pins for the 1.0 view
    if focus10:
        pins = {"Keep Elariel": (520, -2545), "Ilwen's Lighthouse": (127, -2343), "Lantern Pier": (136, -2418),
                "Syrena's islet": (247, -2462), "Oruth (under the bay)": (-119, -2611), "The Teeth": (150, -3550),
                "Lampwick Skerries": (-2400, -4450), "Carriage Station": (522, -2220), "Boatyard": (165, -2140),
                "Waystone ring": (725, -2650), "Observatory (1.1)": (1326, -2980)}
        fp = font(F, int(label_size * 0.8))
        for n, (x, z) in pins.items():
            X, Zp = tx(x), tz(z); r = 5
            d.ellipse([X - r, Zp - r, X + r, Zp + r], fill=(255, 214, 90), outline=(60, 30, 20))
            d.text((X + 8, Zp - 8), n, font=fp, fill=(30, 20, 15), stroke_width=2, stroke_fill=(250, 244, 228))
    # title + legend
    pad = int(W * 0.012)
    tf = font(FB, int(label_size * 1.9)); sf = font(F, int(label_size * 0.95))
    d.rectangle([pad, pad, pad + int(W * 0.36), pad + int(label_size * 4.3)], fill=(246, 238, 220), outline=(90, 60, 40), width=2)
    d.text((pad * 2, pad * 1.6), title, font=tf, fill=(60, 30, 20))
    d.text((pad * 2, pad * 1.6 + label_size * 2.2), sub, font=sf, fill=(80, 55, 40))
    if not focus10:
        lf = font(F, int(label_size * 0.95)); y = H - pad - len(waves) * label_size * 1.45 - pad
        d.rectangle([pad, y - pad, pad + int(W * 0.25), H - pad], fill=(246, 238, 220), outline=(90, 60, 40), width=2)
        for k, (w, n) in enumerate(waves.items()):
            yy = y + k * label_size * 1.45
            d.rectangle([pad * 2, yy, pad * 2 + label_size, yy + label_size], fill=WAVE_COL[w], outline=(60, 40, 30))
            d.text((pad * 2 + label_size * 1.6, yy - 2), f"{w}  {n}", font=lf, fill=(40, 25, 20))
    img.save(path, quality=90)
    print(path, img.size)

draw(f"{OUT}/map_world.jpg", -12000, 12000, -7200, 7600, 2400, 22,
     "Lyris in chunks", "Release waves, Genshin-style. Red line: 1.0 Moonharbor")
draw(f"{OUT}/map_moonharbor.jpg", -3400, 2000, -5100, -1150, 2000, 24,
     "1.0  Moonharbor", "4 land chunks + 2 sea chunks. Everything else waits", focus10=True)
