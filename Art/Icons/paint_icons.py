"""Storybook item icons for the Lyris inventory (T16).

Every built-in item in Source/Lyris/Items/LyrisItemCatalog.cpp gets a 128 x 128 RGBA icon here,
named by its item id (e.g. tool_pickaxe.png). The game loads them at runtime from Art/Icons/ until
items get proper texture assets (ULyrisItemDefinition::Icon), which then take priority.

Style: soft painted shapes with a warm dark ink outline, a gentle top-left light, a highlight
stroke and a soft drop shadow, drawn at 4x and scaled down so the edges stay smooth.

Run:  python3 Art/Icons/paint_icons.py
"""

import math
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
S = 4            # supersampling
N = 128 * S      # canvas size while painting
INK = (58, 40, 38, 255)


def hexc(h, a=255):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


def mix(a, b, t):
    return tuple(int(round(a[i] * (1 - t) + b[i] * t)) for i in range(len(a)))


class Icon:
    def __init__(self):
        self.img = Image.new("RGBA", (N, N), (0, 0, 0, 0))

    # -- primitives ----------------------------------------------------------------------------
    def _mask(self, draw_fn):
        m = Image.new("L", (N, N), 0)
        draw_fn(ImageDraw.Draw(m))
        return m

    def shape(self, draw_fn, light, dark, outline=INK, width=5, shade_dir=(-0.6, -0.8), gloss=True):
        """Fills a shape with a light-to-dark gradient along shade_dir, an ink outline and a gloss."""
        mask = self._mask(draw_fn)
        bbox = mask.getbbox()
        if not bbox:
            return mask
        x0, y0, x1, y1 = bbox
        grad = Image.new("RGBA", (N, N))
        gp = grad.load()
        dx, dy = shade_dir
        length = math.hypot(dx, dy)
        dx, dy = dx / length, dy / length
        cx, cy, half = (x0 + x1) / 2, (y0 + y1) / 2, max(x1 - x0, y1 - y0) / 2 + 1
        for y in range(y0, y1):
            for x in range(x0, x1):
                t = ((x - cx) * dx + (y - cy) * dy) / half  # -1 dark side .. 1 lit side
                gp[x, y] = mix(dark, light, min(1.0, max(0.0, 0.5 + 0.55 * t)))
        if outline:
            ring = mask.filter(ImageFilter.MaxFilter(width * S // 2 * 2 + 1))
            ink = Image.new("RGBA", (N, N), outline)
            self.img.paste(ink, (0, 0), ring)
        self.img.paste(grad, (0, 0), mask)
        if gloss:
            g = ImageChops.offset(mask, int(-dx * 6 * S), int(-dy * 6 * S))
            g = ImageChops.subtract(mask, g).filter(ImageFilter.GaussianBlur(2 * S))
            g = g.point(lambda v: int(v * 0.55))
            self.img.paste(Image.new("RGBA", (N, N), (255, 252, 236, 255)), (0, 0), g)
        return mask

    def stroke(self, pts, colour, width):
        d = ImageDraw.Draw(self.img)
        d.line([(x * S, y * S) for x, y in pts], fill=colour, width=int(width * S), joint="curve")
        for x, y in (pts[0], pts[-1]):
            r = width * S / 2
            d.ellipse([x * S - r, y * S - r, x * S + r, y * S + r], fill=colour)

    def sparkle(self, x, y, r, colour=(255, 250, 225, 255)):
        d = ImageDraw.Draw(self.img)
        x, y, r = x * S, y * S, r * S
        d.polygon([(x, y - r), (x + r * 0.22, y - r * 0.22), (x + r, y), (x + r * 0.22, y + r * 0.22),
                   (x, y + r), (x - r * 0.22, y + r * 0.22), (x - r, y), (x - r * 0.22, y - r * 0.22)], fill=colour)

    def finish(self, path):
        # Soft shadow under the whole item, then scale down.
        alpha = self.img.split()[3]
        shadow = Image.new("RGBA", (N, N), (40, 24, 30, 0))
        sh = ImageChops.offset(alpha, 3 * S, 5 * S).filter(ImageFilter.GaussianBlur(4 * S)).point(lambda v: int(v * 0.35))
        shadow.putalpha(sh)
        out = Image.alpha_composite(shadow, self.img)
        out = out.resize((128, 128), Image.LANCZOS)
        out.save(path)


def P(*pts):
    return [(x * S, y * S) for x, y in pts]


def E(x0, y0, x1, y1):
    return [x0 * S, y0 * S, x1 * S, y1 * S]


def rotated_rect(cx, cy, w, h, deg):
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    pts = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        x, y = sx * w / 2, sy * h / 2
        pts.append((cx + x * ca - y * sa, cy + x * sa + y * ca))
    return P(*pts)


WOOD_L, WOOD_D = hexc("D9A066"), hexc("8A5634")
IRON_L, IRON_D = hexc("DCE3EA"), hexc("7C8796")


def handle(ic, x0, y0, x1, y1, w=11):
    ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
    length = math.hypot(x1 - x0, y1 - y0)
    ic.shape(lambda d: d.polygon(rotated_rect((x0 + x1) / 2, (y0 + y1) / 2, length, w, ang), fill=255), WOOD_L, WOOD_D)
    ic.stroke([(x0 + (x1 - x0) * 0.08, y0 + (y1 - y0) * 0.08), (x0 + (x1 - x0) * 0.28, y0 + (y1 - y0) * 0.28)],
              hexc("6E4128", 200), 3)  # grip wrap


# ----------------------------------------------------------------------------- icons

def tool_pickaxe(ic):
    handle(ic, 34, 104, 88, 36)
    ic.shape(lambda d: d.polygon(P((24, 44), (52, 22), (84, 18), (110, 34), (118, 52), (100, 40),
                                     (82, 34), (62, 40), (40, 56)), fill=255), IRON_L, IRON_D)


def tool_axe(ic):
    handle(ic, 36, 108, 84, 30)
    ic.shape(lambda d: d.polygon(P((70, 30), (96, 16), (112, 34), (108, 62), (90, 56), (80, 46)), fill=255),
             IRON_L, IRON_D)
    ic.stroke([(98, 22), (110, 38), (106, 58)], hexc("FFFFFF", 170), 2.5)


def tool_hoe(ic):
    handle(ic, 30, 110, 86, 26)
    ic.shape(lambda d: d.polygon(P((78, 22), (96, 26), (112, 52), (100, 58), (88, 40), (76, 36)), fill=255),
             IRON_L, IRON_D)


def tool_watering_can(ic):
    teal_l, teal_d = hexc("8FD3C6"), hexc("3D8C88")
    ic.shape(lambda d: d.polygon(P((80, 68), (106, 40), (111, 46), (88, 80)), fill=255), teal_l, teal_d)  # spout
    ic.shape(lambda d: d.ellipse(E(100, 30, 116, 46), fill=255), hexc("B9E6DA"), teal_d)               # rose
    ic.shape(lambda d: d.arc(E(26, 22, 74, 78), 180, 360, fill=255, width=9 * S), teal_l, teal_d, gloss=False)
    ic.shape(lambda d: d.rounded_rectangle(E(16, 46, 84, 108), radius=16 * S, fill=255), teal_l, teal_d)
    ic.shape(lambda d: d.rounded_rectangle(E(12, 44, 88, 54), radius=5 * S, fill=255), hexc("D9A066"), hexc("9A6640"))
    ic.stroke([(26, 62), (26, 96)], hexc("FFFFFF", 120), 4)


def stone(ic, streaks=None):
    ic.shape(lambda d: d.polygon(P((20, 86), (28, 54), (52, 34), (82, 32), (106, 50), (112, 82), (92, 104),
                                     (46, 106)), fill=255), hexc("D4CCC2"), hexc("857A78"))
    ic.stroke([(40, 56), (56, 44)], hexc("FFFFFF", 150), 3)
    if streaks:
        for pts, col in streaks:
            ic.stroke(pts, col, 6)


def copper_ore(ic):
    stone(ic, [([(36, 80), (52, 72), (64, 82)], hexc("5FB394")), ([(66, 52), (82, 48), (94, 60)], hexc("D98A52")),
               ([(58, 92), (78, 88)], hexc("5FB394")), ([(84, 76), (96, 84)], hexc("D98A52"))])


def star_crystal(ic):
    def crystal(pts, l, dk):
        ic.shape(lambda d: d.polygon(P(*pts), fill=255), l, dk)
    crystal([(30, 104), (26, 66), (40, 52), (50, 70), (52, 104)], hexc("D7D3FF"), hexc("7C77C9"))
    crystal([(78, 106), (80, 60), (96, 46), (104, 66), (100, 106)], hexc("CFF4FF"), hexc("6AA4C9"))
    crystal([(46, 108), (50, 40), (64, 16), (78, 40), (82, 108)], hexc("F1EDFF"), hexc("9089DA"))
    ic.stroke([(58, 42), (60, 92)], hexc("FFFFFF", 170), 3)
    ic.sparkle(92, 26, 9)
    ic.sparkle(30, 40, 6)


def wood(ic):
    for (x0, y0, x1, y1) in ((14, 62, 96, 96), (34, 34, 116, 68)):
        ic.shape(lambda d, b=(x0, y0, x1, y1): d.rounded_rectangle(E(*b), radius=16 * S, fill=255), WOOD_L, WOOD_D)
        cy = (y0 + y1) / 2
        r = (y1 - y0) / 2
        ic.shape(lambda d, b=(x1 - 2 * r + 4, y0, x1, y1): d.ellipse(E(*b), fill=255),
                 hexc("F2D3A4"), hexc("C99A66"), gloss=False)
        d = ImageDraw.Draw(ic.img)
        cx = x1 - r + 2
        for k in (0.55, 0.25):
            d.ellipse(E(cx - r * k, cy - r * k, cx + r * k, cy + r * k), outline=hexc("A9743F"), width=2 * S)


def sea_herb(ic):
    ic.stroke([(64, 112), (62, 78), (56, 40), (60, 18)], hexc("4F7A4F"), 5)
    for (x, y, ang, ln) in ((62, 92, -40, 30), (62, 90, 210, 30), (59, 66, -30, 28), (58, 62, 205, 28),
                            (57, 40, -35, 22), (57, 38, 210, 22)):
        a = math.radians(ang)
        tip = (x + math.cos(a) * ln, y + math.sin(a) * ln)
        mid = ((x + tip[0]) / 2, (y + tip[1]) / 2)
        n = (-math.sin(a) * 7, math.cos(a) * 7)
        ic.shape(lambda d, pts=(x, y, tip, mid, n): d.polygon(
            P((pts[0], pts[1]), (pts[3][0] + pts[4][0], pts[3][1] + pts[4][1]), pts[2],
              (pts[3][0] - pts[4][0], pts[3][1] - pts[4][1])), fill=255), hexc("B4DA8A"), hexc("4F8A5A"), width=4)


def seed_pouch(ic, tint_l, tint_d, emblem):
    burlap_l, burlap_d = hexc("E9D3A6"), hexc("A9875C")
    ic.shape(lambda d: d.polygon(P((26, 112), (20, 70), (40, 44), (88, 44), (108, 70), (102, 112)), fill=255),
             burlap_l, burlap_d)
    ic.shape(lambda d: d.polygon(P((40, 46), (34, 28), (52, 36), (64, 22), (76, 36), (94, 28), (88, 46)), fill=255),
             burlap_l, burlap_d)
    ic.shape(lambda d: d.rounded_rectangle(E(36, 42, 92, 52), radius=4 * S, fill=255), hexc("C76E52"), hexc("8A3D33"))
    ic.shape(lambda d: d.ellipse(E(42, 62, 86, 102), fill=255), hexc("FFF6E2"), hexc("D9C7A3"), width=3, gloss=False)
    emblem(ic, 64, 82, tint_l, tint_d)


def berry_cluster(ic, cx, cy, l, dk, scale=1.0):
    for dx, dy in ((-9, 4), (9, 4), (0, -8), (0, 10)):
        r = 9 * scale
        x, y = cx + dx * scale, cy + dy * scale
        ic.shape(lambda d, b=(x - r, y - r, x + r, y + r): d.ellipse(E(*b), fill=255), l, dk, width=3)


def bell(ic, cx, cy, l, dk, scale=1.0):
    s = scale
    ic.shape(lambda d: d.polygon(P((cx - 16 * s, cy + 12 * s), (cx - 11 * s, cy - 8 * s), (cx, cy - 16 * s),
                                     (cx + 11 * s, cy - 8 * s), (cx + 16 * s, cy + 12 * s), (cx + 6 * s, cy + 8 * s),
                                     (cx, cy + 14 * s), (cx - 6 * s, cy + 8 * s)), fill=255), l, dk, width=3)


def turnip_shape(ic, cx, cy, scale=1.0, leaves=True):
    s = scale
    if leaves:
        for ang in (-115, -90, -65):
            a = math.radians(ang)
            tip = (cx + math.cos(a) * 30 * s, cy - 14 * s + math.sin(a) * 30 * s)
            ic.shape(lambda d, t=tip: d.polygon(P((cx - 4 * s, cy - 14 * s), t, (cx + 4 * s, cy - 14 * s)), fill=255),
                     hexc("A9D67E"), hexc("4F8A5A"), width=3)
    ic.shape(lambda d: d.polygon(P((cx, cy + 30 * s), (cx - 20 * s, cy + 2 * s), (cx - 18 * s, cy - 14 * s),
                                     (cx, cy - 20 * s), (cx + 18 * s, cy - 14 * s), (cx + 20 * s, cy + 2 * s)), fill=255),
             hexc("F7F0F4"), hexc("B9A3C2"))
    ic.shape(lambda d: d.polygon(P((cx - 18 * s, cy - 13 * s), (cx, cy - 20 * s), (cx + 18 * s, cy - 13 * s),
                                     (cx + 14 * s, cy - 4 * s), (cx - 14 * s, cy - 4 * s)), fill=255),
             hexc("C99BD6"), hexc("7E5A9A"), width=2, gloss=False)


def seed_mistberry(ic):
    seed_pouch(ic, None, None, lambda ic, x, y, l, dk: berry_cluster(ic, x, y, hexc("A7B8F2"), hexc("5560A8"), 0.8))


def seed_moonbell(ic):
    seed_pouch(ic, None, None, lambda ic, x, y, l, dk: bell(ic, x, y, hexc("FFFBE8"), hexc("C9C0A0"), 0.8))


def seed_harbor_turnip(ic):
    seed_pouch(ic, None, None, lambda ic, x, y, l, dk: turnip_shape(ic, x, y - 2, 0.42, leaves=False))


def mistberry(ic):
    ic.shape(lambda d: d.polygon(P((62, 40), (70, 24), (86, 14), (104, 12), (98, 28), (84, 40)), fill=255),
             hexc("B4DA8A"), hexc("4F8A5A"))
    ic.stroke([(66, 38), (96, 16)], hexc("4F8A5A", 200), 2)
    ic.stroke([(64, 40), (62, 54)], hexc("5C7A44"), 4)
    berry_cluster(ic, 60, 80, hexc("B3C3FA"), hexc("4D569E"), 2.0)
    ic.sparkle(44, 66, 5)


def moonbell(ic):
    ic.stroke([(64, 112), (60, 70), (70, 40)], hexc("5C8A50"), 5)
    ic.shape(lambda d: d.polygon(P((60, 92), (34, 84), (48, 98)), fill=255), hexc("B4DA8A"), hexc("4F8A5A"), width=3)
    glow = Image.new("L", (N, N), 0)
    ImageDraw.Draw(glow).ellipse(E(28, 20, 104, 96), fill=110)
    ic.img.paste(Image.new("RGBA", (N, N), hexc("FFF4C4")), (0, 0), glow.filter(ImageFilter.GaussianBlur(10 * S)))
    bell(ic, 70, 58, hexc("FFFDF0"), hexc("D8CBA0"), 2.0)
    ic.sparkle(100, 30, 6)


def harbor_turnip(ic):
    turnip_shape(ic, 64, 70, 1.35)


ICONS = {
    "tool_pickaxe": tool_pickaxe, "tool_axe": tool_axe, "tool_hoe": tool_hoe,
    "tool_watering_can": tool_watering_can, "stone": stone, "copper_ore": copper_ore,
    "star_crystal": star_crystal, "wood": wood, "sea_herb": sea_herb,
    "seed_mistberry": seed_mistberry, "seed_moonbell": seed_moonbell,
    "seed_harbor_turnip": seed_harbor_turnip, "mistberry": mistberry, "moonbell": moonbell,
    "harbor_turnip": harbor_turnip,
}


def main():
    for name, fn in ICONS.items():
        ic = Icon()
        fn(ic)
        ic.finish(os.path.join(HERE, f"{name}.png"))
    # A contact sheet for review.
    sheet = Image.new("RGBA", (128 * 5 + 60, 128 * 3 + 40), hexc("F3E6C8"))
    for k, name in enumerate(ICONS):
        im = Image.open(os.path.join(HERE, f"{name}.png"))
        sheet.alpha_composite(im, (10 + (k % 5) * 130, 10 + (k // 5) * 130))
    sheet.save(os.path.join(HERE, "_sheet.png"))
    print(len(ICONS), "icons")


if __name__ == "__main__":
    main()
