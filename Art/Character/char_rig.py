"""The shared skeleton: UE5 mannequin bone names and hierarchy in a mannequin-like A-pose.

Build space is Blender's: X = the character's left, -Y = the way the character faces, Z up,
centimetres, feet on Z = 0. Exported to glTF / FBX and imported into Unreal this becomes
the mannequin's own asset space: facing +Y, the character's left on +X, Z up (see README).
"""

import numpy as np

F = np.float64


def _n(v):
    v = np.asarray(v, F)
    return v / np.linalg.norm(v)


def _rot(v, axis, deg):
    """Rotate v about a unit axis (Rodrigues)."""
    a = np.radians(deg)
    k = _n(axis)
    v = np.asarray(v, F)
    return v * np.cos(a) + np.cross(k, v) * np.sin(a) + k * (k @ v) * (1 - np.cos(a))


# Overall height 172 cm, head 25 cm (chin 147, crown 172): 6.9 heads tall.
HEIGHT = 172.0
HEAD_TOP = 172.0
CHIN_Z = 147.0

FINGERS = ("index", "middle", "ring", "pinky")


def build_joints():
    """Returns (joints, parents, tails, hand_frames).

    joints: name -> head position. parents: name -> parent name (None for root).
    tails: name -> tail position (for the Blender bone; the next joint or a short stub).
    """
    J, P, T = {}, {}, {}

    def add(name, pos, parent, tail=None):
        J[name] = np.asarray(pos, F)
        P[name] = parent
        if tail is not None:
            T[name] = np.asarray(tail, F)

    add("root", (0, 0, 0), None, (0, -12, 0))
    add("pelvis", (0, 0.5, 93.0), "root")
    add("spine_01", (0, 0.2, 99.0), "pelvis")
    add("spine_02", (0, -0.2, 106.0), "spine_01")
    add("spine_03", (0, -0.4, 114.0), "spine_02")
    add("spine_04", (0, -0.2, 123.0), "spine_03")
    add("spine_05", (0, 0.4, 132.0), "spine_04")
    add("neck_01", (0, 1.2, 141.0), "spine_05")
    add("neck_02", (0, 0.9, 145.0), "neck_01")
    add("head", (0, 0.6, 149.5), "neck_02", (0, 0.6, 166.0))

    frames = {}
    for side, s in (("l", 1.0), ("r", -1.0)):
        def m(v):
            v = np.asarray(v, F)
            return np.array([v[0] * s, v[1], v[2]])

        clav = m((2.0, -1.5, 137.5))
        shoulder = m((16.0, 1.0, 137.0))
        d1 = _n(m((0.675, -0.095, -0.731)))
        elbow = shoulder + d1 * 27.0
        d2 = _n(m((0.66, -0.20, -0.72)))
        wrist = elbow + d2 * 24.5
        add(f"clavicle_{side}", clav, "spine_05")
        add(f"upperarm_{side}", shoulder, f"clavicle_{side}")
        add(f"lowerarm_{side}", elbow, f"upperarm_{side}")
        add(f"hand_{side}", wrist, f"lowerarm_{side}")

        # Hand frame: d along the hand, n out of the palm (palm faces the thigh), w across
        # the knuckles towards the thumb (forward).
        d = d2
        n = _n(m((-1, 0, 0)) - (m((-1, 0, 0)) @ d) * d)
        w = _n(np.cross(d, n))
        if w[1] > 0:  # thumb must point forward (-Y)
            w = -w
        frames[side] = (wrist, d, n, w)

        spread = {"index": 2.55, "middle": 0.85, "ring": -0.85, "pinky": -2.5}
        lengths = {"index": (3.5, 2.3, 1.9), "middle": (3.8, 2.5, 2.0),
                   "ring": (3.5, 2.3, 1.9), "pinky": (2.8, 1.9, 1.7)}
        knuckle_d = {"index": 7.9, "middle": 8.1, "ring": 7.8, "pinky": 7.2}
        splay = {"index": 5.0, "middle": 0.0, "ring": -5.0, "pinky": -10.0}
        for f in FINGERS:
            meta = wrist + d * 1.6 + w * spread[f] * 0.55 + n * 0.2
            knuckle = wrist + d * knuckle_d[f] + w * spread[f] + n * 0.1
            add(f"{f}_metacarpal_{side}", meta, f"hand_{side}")
            fd = _rot(d, n, splay[f] * (1 if s > 0 else -1) * (1 if w[1] < 0 else -1))
            fd = _n(fd)
            pos = knuckle
            parent = f"{f}_metacarpal_{side}"
            for i, L in enumerate(lengths[f]):
                name = f"{f}_0{i + 1}_{side}"
                add(name, pos, parent)
                fd = _n(fd + n * 0.16)  # relaxed curl towards the palm
                pos = pos + fd * L
                parent = name
            T[f"{f}_03_{side}"] = pos
        # Thumb: from the heel of the hand, angled forward and towards the palm.
        tpos = wrist + d * 1.9 + w * 1.5 + n * 0.9
        td = _n(d * 0.65 + w * 0.6 + n * 0.45)
        parent = f"hand_{side}"
        for i, L in enumerate((3.2, 2.6, 2.1)):
            name = f"thumb_0{i + 1}_{side}"
            add(name, tpos, parent)
            td = _n(td + n * 0.12 + d * 0.05)
            tpos = tpos + td * L
            parent = name
        T[f"thumb_03_{side}"] = tpos

        hip = m((9.0, 0.5, 90.5))
        knee = m((9.6, -0.8, 49.5))
        ankle = m((10.0, 1.8, 8.5))
        ball = m((11.0, -10.5, 2.0))
        add(f"thigh_{side}", hip, "pelvis")
        add(f"calf_{side}", knee, f"thigh_{side}")
        add(f"foot_{side}", ankle, f"calf_{side}")
        add(f"ball_{side}", ball, f"foot_{side}", m((11.3, -15.5, 2.0)))

    # Mannequin IK helper bones (no skin weights), kept so retargets and IK rigs find them.
    add("ik_foot_root", (0, 0, 0), "root", (0, 0, 10))
    add("ik_foot_l", J["foot_l"], "ik_foot_root", J["foot_l"] + (0, 0, 6))
    add("ik_foot_r", J["foot_r"], "ik_foot_root", J["foot_r"] + (0, 0, 6))
    add("ik_hand_root", (0, 0, 0), "root", (0, 0, 10))
    add("ik_hand_gun", J["hand_r"], "ik_hand_root", J["hand_r"] + (0, 0, 6))
    add("ik_hand_l", J["hand_l"], "ik_hand_gun", J["hand_l"] + (0, 0, 6))
    add("ik_hand_r", J["hand_r"], "ik_hand_gun", J["hand_r"] + (0, 0, 6))

    children = {}
    for name, par in P.items():
        if par:
            children.setdefault(par, []).append(name)
    for name in J:
        if name in T:
            continue
        kids = [c for c in children.get(name, []) if not c.startswith("ik_")]
        if name.startswith("clavicle"):
            T[name] = J[f"upperarm_{name[-1]}"]
        elif name.startswith("hand_"):
            T[name] = J[f"middle_01_{name[-1]}"]
        elif name.startswith("spine_05"):
            T[name] = J["neck_01"]
        elif name == "pelvis":
            T[name] = J["spine_01"]
        elif len(kids) == 1:
            T[name] = J[kids[0]]
        else:
            T[name] = J[name] + np.array([0, 0, 5.0])
    return J, P, T, frames


DEFORM_EXCLUDE = ("root", "ik_")


def deform_bones(P):
    return [b for b in P if not b.startswith(DEFORM_EXCLUDE) and b != "root"]


def segments(J, T, names):
    """Bone segments used for distance-based skin weights."""
    return {b: (J[b], T[b]) for b in names}
