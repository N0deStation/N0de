#!/usr/bin/env python3
"""Generates the 24 s hero-loop CSS in docs/index.html: the static (no-motion) frame, the animation bindings and every
n3-*/d3-orbit keyframe. The arm's joint angles come from a small inverse-kinematics solve, so targets can be moved freely.

    python tools/gen_hero_loop.py            # rewrite the block in docs/index.html in place
    python tools/gen_hero_loop.py --print    # print the block instead

Units are px with y pointing DOWN (the deck's top surface is y = 0); times are percent of the 24 s loop. Visit 1 lands on
pad 1 (x < 0); visit 2 is the same schedule 50% later with x mirrored and the two rack slots swapping roles.
The battery is a slide-in pack in the drone's tail: the arm grips its exposed end, slides it out toward the belt, lifts it
to the rack, and pushes the charged one back in the same way.
"""
import math
import re
import sys
from pathlib import Path

HTML = Path(__file__).resolve().parent.parent / "docs" / "index.html"
START, END = "  /* Static frame (reduced motion) */", "  /* Step pills under the illustration"

# ---- arm geometry ----
L1 = L2 = 66.0        # link lengths
SHOULDER_Y = -46.0    # shoulder pivot height
TOOL = 30.0           # wrist pivot -> centre of a gripped pack, straight down
PAD_X, PAD_Z, SLED_Z, RACK_Z = 95, 50, -50, -80
SLOT_X = 28
BAY_Y = -33.0                     # pack centre height in the drone's tail bay (and while carried)
BAY_Z_IN, BAY_Z_OUT = -27, -47    # pack centre z relative to the drone: seated in the bay (12 px showing) / slid clear of the body
RACK_PACK_Y = -26.0
GRIP_OFF = 9                      # the gripper holds the pack's exposed end, so the pack centre is 9 px further along the reach
LIFT = 30.0                       # hover height above a pack before/after gripping


def reach_at_pad(pack_z):
    return PAD_Z + pack_z - GRIP_OFF - SLED_Z   # the arm faces +z at the pads


REACH_RACK = SLED_Z - RACK_Z - GRIP_OFF         # ... and -z at the rack

# ---- flight (visit 1): the drone comes in from outboard, hovers, settles; later unsticks, then climbs out and away ----
APEX_Y = -330         # high enough that the drone is fully above the stage at the 0%/50% seams, at every camera angle
APPROACH_X, EXIT_X = -165, -150
T_HOVER, T_BOB, T_TOUCH = 5.2, 6.6, 8.2
T_LIFT, T_UNSTICK, T_GONE = 41.6, 43, 48.6
T_SPOOL = 40.6        # rotors spin up before lift-off, once the retreating arm has swung clear of the rotor discs
T_STOP = 9.6          # rotors stopped after touchdown
# (t, x, y, timing function of the segment that starts here)
FLIGHT = [
    (0, APPROACH_X, APEX_Y, "cubic-bezier(.25, .6, .35, 1)"),
    (T_HOVER, -PAD_X, -48, "ease-in-out"),
    (T_BOB, -PAD_X, -42, "cubic-bezier(.4, 0, .7, 1)"),
    (T_TOUCH, -PAD_X, 0, None),
    (T_LIFT, -PAD_X, 0, "cubic-bezier(.3, 0, .8, .2)"),
    (T_UNSTICK, -PAD_X, -14, "cubic-bezier(.5, 0, .9, .3)"),
    (T_GONE, EXIT_X, APEX_Y, None),
    (49.9, EXIT_X, APEX_Y, None),
]
SHADOW = {0: (0, .25), T_HOVER: (.32, .8), T_BOB: (.34, .82), T_TOUCH: (.5, 1), T_LIFT: (.5, 1), T_UNSTICK: (.46, .95), T_GONE: (0, .25), 49.9: (0, .25)}
BANK = [(0, 0), (1.2, 7), (4.2, 7), (5.6, 0), (T_LIFT, 0), (T_UNSTICK, 0), (44, -6), (47, -6), (T_GONE, 0), (49.9, 0)]  # deg, nose-down into travel

# ---- arm schedule (visit 1): (t, sled x, pose). At the drone the arm grips the pack's exposed end, slides it out of the
#      bay (pull), lifts, and later pushes the charged one back in. Holds after a grip/release let the jaws finish first. ----
ARM = [
    (0, 0, "park"), (9, 0, "park"),
    (12, -PAD_X, "hoverIn"), (14, -PAD_X, "seat"), (15, -PAD_X, "seat"), (17, -PAD_X, "pull"), (18.2, -PAD_X, "hoverOut"),
    (21, SLOT_X, "park"), (23, SLOT_X, "rack"), (23.8, SLOT_X, "rack"), (25, SLOT_X, "park"),
    (27, -SLOT_X, "park"), (29, -SLOT_X, "rack"), (29.8, -SLOT_X, "rack"), (31, -SLOT_X, "park"),
    (34.5, -PAD_X, "hoverOut"), (35.5, -PAD_X, "pull"), (37.5, -PAD_X, "seat"), (38.3, -PAD_X, "seat"), (39.2, -PAD_X, "hoverIn"),
    (41.5, 0, "park"), (49.9, 0, "park"),
]
JAW_T = 0.7                                   # a close/open takes 0.7% = 0.17 s
JAW_OPEN = 4                                  # px each jaw moves outward when open (keeps the open jaws clear of the rotor booms)
GRIP_OLD, RELEASE_OLD, GRIP_NEW, RELEASE_NEW = 14, 23, 29, 37.5   # jaw moves start here; hand-offs happen when they end
SWAP_END = RELEASE_NEW + JAW_T
CHARGE_START, CHARGE_END = 38.5, 48.5
LED_BLINK = [CHARGE_START + 1.5 * i for i in range(1, 6)]    # alternating dim / bright while charging

# ---- camera: slow drift while a drone is on the ground, swing to the other pad while it leaves ----
ORBIT = [(0, -28, 30, "ease-in-out"), (38, -26, 14, "cubic-bezier(.45, 0, .3, 1)"), (50, -28, -30, "ease-in-out"), (88, -26, -14, "cubic-bezier(.45, 0, .3, 1)"), (100, -28, 30, None)]

SUCCESS = "var(--color-success, #22a06b)"
WARNING = "var(--color-warning, #f5a524)"
ERROR = "var(--color-error, #e5484d)"
PILL_OFF = "background: var(--bg); color: var(--muted); border-color: var(--line); box-shadow: 0 0 0 0 transparent;"
PILL_ON = "background: var(--accent); color: var(--on-accent); border-color: var(--accent); box-shadow: 0 0 0 3px var(--glow);"
PAD_OFF = "--pg: 0; background-color: transparent;"  # background-color only: the ring's crosshair lives in background-image layers
PAD_APPROACH = "--pg: 1; background-color: color-mix(in oklab, var(--accent) 14%, transparent);"
PAD_OCCUPIED = "--pg: .35; background-color: color-mix(in oklab, var(--accent) 8%, transparent);"
SNAP = "cubic-bezier(.2, .8, .3, 1)"


def ik(reach, tool_y):
    """Joint angles (shoulder, elbow, wrist) in degrees that put the pack centre at (reach, tool_y) with the tool hanging down."""
    wx, wy = reach, tool_y - TOOL
    dx, dy = wx, wy - SHOULDER_Y
    d = math.hypot(dx, dy)
    el = 180 - math.degrees(math.acos((L1 * L1 + L2 * L2 - d * d) / (2 * L1 * L2)))
    sh = math.degrees(math.atan2(dy, dx)) - math.degrees(math.acos(d / (2 * L1)))
    sh, el = round(sh, 2), round(el, 2)
    return sh, el, round(90 - sh - el, 2)  # wrist from the rounded values so the tool hangs exactly straight down


POSE = {
    "park": ik(REACH_RACK, RACK_PACK_Y - LIFT),               # parked: hovering over the rack centre
    "hoverIn": ik(reach_at_pad(BAY_Z_IN), BAY_Y - LIFT),      # above the seated pack's exposed end
    "seat": ik(reach_at_pad(BAY_Z_IN), BAY_Y),                # gripping it / pack seated in the bay
    "pull": ik(reach_at_pad(BAY_Z_OUT), BAY_Y),               # pack slid clear of the body
    "hoverOut": ik(reach_at_pad(BAY_Z_OUT), BAY_Y - LIFT),    # lifted clear
    "rack": ik(REACH_RACK, RACK_PACK_Y),                      # pack in a rack slot
}
YAW = {p: (90 if p in ("park", "rack") else -90) for p in POSE}


def num(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def pct(p):
    return f"{round(p, 3):g}%"


def two_visits(track):
    """Visit-1 keyframes over [0, 49.9] -> both visits; the final 99.9 becomes 100."""
    return list(track) + [(100 if t == 49.9 else t + 50, *rest) for t, *rest in track]


def events_track(initial, events, fmt):
    """Discrete track: the state holds until each event time t and flips at t + 0.01."""
    out, state = [(0, fmt(initial))], initial
    for t, new in events:
        if t >= 99.9:
            continue
        out += [(t, fmt(state)), (t + 0.01, fmt(new))]
        state = new
    return out + [(100, fmt(state))]


def vis(v):
    return f"visibility: {'visible' if v else 'hidden'};"


def keyframes(name, frames):
    body = "\n".join(f"    {pct(t)} {{ {decl} }}" for t, decl in frames)
    return f"  @keyframes {name} {{\n{body}\n  }}"


def with_ease(decl, ease):
    return f"{decl} animation-timing-function: {ease};" if ease else decl


def build():
    out = []
    sh, el, wr = POSE["park"]
    out.append(START)
    out.append(f"  .n3-drone {{ translate: {-PAD_X}px 0 {PAD_Z}px; transform-origin: 0 -36px; }}")
    out.append("  .n3-dbat-old, .n3-grip-old, .n3-grip-new, .n3-s1 { visibility: hidden; }")
    out.append("  .rotor3d > span:first-child { visibility: hidden; } .rotor3d::before { opacity: 0; } /* rotors stopped: idle blade, no blur disc */")
    out.append(f"  .pad-ring-1 {{ {PAD_OCCUPIED} }}")
    out.append(f"  .n3-slide {{ translate: 0px 0 {SLED_Z}px; }} /* the arm's sled sits on the belt */")
    out.append("  .n3-yaw { rotate: y 90deg; } .n3-roll { rotate: y -90deg; }")
    out.append(f"  .n3-sh {{ rotate: z {num(sh)}deg; }} .n3-el {{ rotate: z {num(el)}deg; }} .n3-wr {{ rotate: z {num(wr)}deg; }}")
    out.append(f"  .n3-jaw-l {{ translate: {-JAW_OPEN}px 0 0; }} .n3-jaw-r {{ translate: {JAW_OPEN}px 0 0; }}")
    out.append("")
    out.append("  /* The 24s loop: two visits, one per landing pad. Element-level timing is linear where the keyframes carry their own curves. */")
    out.append("  .world3d   { animation: d3-orbit 24s linear infinite; }")
    out.append("  .n3-drone  { animation: n3-drone 24s linear infinite, n3-bank 24s ease-in-out infinite; }")
    out.append("  .n3-dbat-old { animation: n3-dbat-old 24s linear infinite; }")
    out.append("  .n3-dbat-new { animation: n3-dbat-new 24s linear infinite; }")
    for n in ("slide", "yaw", "roll", "sh", "el", "wr"):
        out.append(f"  .n3-{n:<6} {{ animation: n3-{n} 24s ease-in-out infinite; }}")
    out.append("  .n3-jaw-l  { animation: n3-jaw-l 24s linear infinite; }")
    out.append("  .n3-jaw-r  { animation: n3-jaw-r 24s linear infinite; }")
    out.append("  .n3-grip-old { animation: n3-grip-old 24s linear infinite; }")
    out.append("  .n3-grip-new { animation: n3-grip-new 24s linear infinite; }")
    out.append("  .n3-s1     { animation: n3-s1 24s linear infinite, n3-s1-col 24s linear infinite; }")
    out.append("  .n3-s2     { animation: n3-s2 24s linear infinite, n3-s2-col 24s linear infinite; }")
    out.append("  .slot-bar-1 > b { animation: n3-s1-bar 24s linear infinite; }")
    out.append("  .slot-bar-2 > b { animation: n3-s2-bar 24s linear infinite; }")
    out.append("  .bat-fill  { animation: n3-bay 24s linear infinite; }")
    out.append("  .lbl-land   { animation: n3-lbl-land 24s linear infinite; }")
    out.append("  .lbl-ready  { animation: n3-lbl-ready 24s linear infinite; }")
    out.append("  .lbl-swap   { animation: n3-lbl-swap 24s linear infinite; }")
    out.append("  .lbl-charge { animation: n3-lbl-charge 24s linear infinite; }")
    out.append("  .led3d     { animation: n3-led 24s linear infinite; }")
    out.append("  .beam3d    { animation: n3-beam 24s ease-in-out infinite, n3-beam-pos 24s step-end infinite, d3-beam-scan .8s linear infinite; }")
    out.append("  .d3-shadow { animation: n3-shadow 24s linear infinite, n3-shadow-s 24s linear infinite, n3-shadow-pos 24s linear infinite; }")
    out.append("  .rotor3d::before { animation: n3-rotor-disc 24s linear infinite; }")
    out.append("  .rotor3d > span:first-child { animation: d3-spin .16s linear infinite, n3-rotor-fast 24s step-end infinite; }")
    out.append("  .rotor3d > span + span { animation: n3-rotor-idle 24s step-end infinite; }")
    out.append("  .pad-ring-1 { animation: n3-pad-1 24s linear infinite, d3-pad-pulse 1.4s ease-in-out infinite alternate; }")
    out.append("  .pad-ring-2 { animation: n3-pad-2 24s linear infinite, d3-pad-pulse 1.4s ease-in-out infinite alternate; }")
    out.append("  .ping3d    { animation: d3-ping 2.4s ease-out infinite; }")
    out.append("  .ping3d-2  { animation-delay: 1.2s; }")
    out.append("  @keyframes d3-spin { to { rotate: 360deg; } }")
    out.append("  @keyframes d3-ping { 0% { scale: 1; opacity: .8; } 100% { scale: 4; opacity: 0; } }")
    out.append("  @keyframes d3-pad-pulse { from { --pp: 0; } to { --pp: 1; } }")
    out.append("  @keyframes d3-beam-scan { to { background-position: 0 -32px, 0 0; } }")

    # camera
    out.append(keyframes("d3-orbit", [(t, with_ease(f"transform: rotateX({rx}deg) rotateY({ry}deg);", e)) for t, rx, ry, e in ORBIT]))

    # drone flight, bank and shadow (visit 2 mirrors x)
    flight = [(t, x, y, e) for t, x, y, e in FLIGHT] + [(100 if t == 49.9 else t + 50, -x, y, e) for t, x, y, e in FLIGHT]
    out.append(keyframes("n3-drone", [(t, with_ease(f"translate: {x}px {y}px {PAD_Z}px;", e)) for t, x, y, e in flight]))
    bank = list(BANK) + [(100 if t == 49.9 else t + 50, -a) for t, a in BANK]
    out.append(keyframes("n3-bank", [(t, f"rotate: z {a}deg;") for t, a in bank]))
    shadow = two_visits([(t, SHADOW[t][0], SHADOW[t][1], e) for t, x, y, e in FLIGHT])
    out.append(keyframes("n3-shadow", [(t, with_ease(f"opacity: {num(o)};", e)) for t, o, s, e in shadow]))
    out.append(keyframes("n3-shadow-s", [(t, with_ease(f"scale: {num(s)};", e)) for t, o, s, e in shadow]))
    out.append(keyframes("n3-shadow-pos", [(t, with_ease(f"translate: {x}px -2px {PAD_Z}px;", e)) for t, x, y, e in flight]))

    # rotors: blur disc + fast blade while flying, a still blade on the ground
    out.append(keyframes("n3-rotor-disc", [(t, f"opacity: {o};") for t, o in two_visits([(0, 1), (T_TOUCH, 1), (T_STOP, 0), (T_SPOOL, 0), (T_LIFT, 1), (49.9, 1)])]))
    rotor_events = [(T_STOP, False), (T_SPOOL, True), (T_STOP + 50, False), (T_SPOOL + 50, True)]
    out.append(keyframes("n3-rotor-fast", events_track(True, rotor_events, vis)))
    out.append(keyframes("n3-rotor-idle", events_track(False, [(t, not v) for t, v in rotor_events], vis)))

    # pads: pulsing glow while a drone approaches or leaves, soft steady glow while one sits on it
    pad = [(0, PAD_OFF), (1, PAD_APPROACH), (T_TOUCH, PAD_APPROACH), (T_STOP, PAD_OCCUPIED), (T_LIFT, PAD_OCCUPIED), (T_UNSTICK, PAD_APPROACH), (48, PAD_APPROACH), (49.9, PAD_OFF)]
    out.append(keyframes("n3-pad-1", pad + [(100, PAD_OFF)]))
    out.append(keyframes("n3-pad-2", [(0, PAD_OFF)] + [(100 if t == 49.9 else t + 50, d) for t, d in pad]))

    # pack hand-offs happen the moment the jaws finish closing or opening
    j = JAW_T
    out.append(keyframes("n3-dbat-old", events_track(True, [(GRIP_OLD + j, False), (50, True), (50 + GRIP_OLD + j, False)], vis)))
    out.append(keyframes("n3-dbat-new", events_track(False, [(RELEASE_NEW + j, True), (49.9, False), (50 + RELEASE_NEW + j, True)], vis)))

    # visit 2 mirrors x, so its yaw is mirrored too (180 - yaw): the arm swings inboard past the rack in both visits
    arm = [(t, x, p, YAW[p]) for t, x, p in ARM] + [(100 if t == 49.9 else t + 50, -x, p, 180 - YAW[p]) for t, x, p in ARM]
    out.append(keyframes("n3-slide", [(t, f"translate: {x}px 0 {SLED_Z}px;") for t, x, p, yaw in arm]))
    out.append(keyframes("n3-yaw", [(t, f"rotate: y {yaw}deg;") for t, x, p, yaw in arm]))
    out.append(keyframes("n3-roll", [(t, f"rotate: y {-yaw}deg;") for t, x, p, yaw in arm]))
    for i, n in enumerate(("sh", "el", "wr")):
        out.append(keyframes(f"n3-{n}", [(t, f"rotate: z {num(POSE[p][i])}deg;") for t, x, p, yaw in arm]))
    jaws = [(0, 1)]
    for t, o in ((GRIP_OLD, 0), (RELEASE_OLD, 1), (GRIP_NEW, 0), (RELEASE_NEW, 1)):
        jaws += [(t, 1 - o, SNAP), (t + j, o)]
    jaws.append((49.9, 1))
    jaws = [(t, *rest) for t, *rest in two_visits(jaws)]
    for n, s in (("l", -JAW_OPEN), ("r", JAW_OPEN)):
        out.append(keyframes(f"n3-jaw-{n}", [(f[0], with_ease(f"translate: {s * f[1]}px 0 0;", f[2] if len(f) > 2 else None)) for f in jaws]))
    out.append(keyframes("n3-grip-old", events_track(False, [(GRIP_OLD + j, True), (RELEASE_OLD + j, False), (50 + GRIP_OLD + j, True), (50 + RELEASE_OLD + j, False)], vis)))
    out.append(keyframes("n3-grip-new", events_track(False, [(GRIP_NEW + j, True), (RELEASE_NEW + j, False), (50 + GRIP_NEW + j, True), (50 + RELEASE_NEW + j, False)], vis)))

    # rack slots: visit 1 receives the depleted pack into slot 2 and gives the charged one from slot 1; visit 2 the other way round
    roles = {1: ("give", "receive"), 2: ("receive", "give")}
    slot_vis, slot_col, slot_bar = [], [], []
    for s in (1, 2):
        ev, col, bar = [], [], []
        occupied = roles[s][0] == "give"
        bar.append((0, 1 if occupied else 0))
        for v, role in zip((0, 50), roles[s]):
            if role == "give":
                t = v + GRIP_NEW + j
                ev.append((t, False))
                bar += [(t, 1), (t + 0.01, 0)]
            else:
                t = v + RELEASE_OLD + j
                ev.append((t, True))
                bar += [(t, 0), (t + 0.01, 0.16), (v + CHARGE_START, 0.16), (v + CHARGE_END, 1)]
                if v > 0:
                    col += [(t, SUCCESS), (t + 0.01, ERROR)]
                col += [(v + CHARGE_START, ERROR), (v + CHARGE_END, SUCCESS)]
        bar.append((100, bar[-1][1]))
        col = [(0, SUCCESS if occupied else ERROR)] + col + [(100, SUCCESS)]
        slot_vis.append(keyframes(f"n3-s{s}", events_track(occupied, ev, vis)))
        slot_col.append(keyframes(f"n3-s{s}-col", [(t, f"--c: {c};") for t, c in col]))
        slot_bar.append(keyframes(f"n3-s{s}-bar", [(t, f"transform: scaleX({num(b).replace('0.', '.')});") for t, b in bar]))
    out += slot_vis + slot_col + slot_bar

    # status panel: battery icon, labels, LED
    r = RELEASE_OLD + j
    out.append(keyframes("n3-bay", [(t, f"transform: scaleX({b});") for t, b in two_visits([(0, 1), (r, 1), (r + 0.01, 0.16), (CHARGE_START, 0.16), (CHARGE_END, 1), (49.9, 1)])]))
    labels = {
        "land": [(0, 0), (0.5, 1), (T_TOUCH, 1), (T_TOUCH + 0.5, 0), (49.9, 0)],
        "ready": [(0, 1), (0.5, 0), (T_TOUCH, 0), (T_TOUCH + 0.5, 1), (13.5, 1), (14, 0), (47.75, 0), (48.5, 1), (49.9, 1)],
        "swap": [(0, 0), (13.5, 0), (14, 1), (CHARGE_START - 0.5, 1), (CHARGE_START, 0), (49.9, 0)],
        "charge": [(0, 0), (CHARGE_START - 0.5, 0), (CHARGE_START, 1), (47.75, 1), (48.5, 0), (49.9, 0)],
    }  # each hand-over crossfades the outgoing and incoming label over the same 0.5-0.75% window
    for n, track in labels.items():
        out.append(keyframes(f"n3-lbl-{n}", [(t, f"opacity: {o};") for t, o in two_visits(track)]))
    led = [(0, "var(--accent)", 1), (T_TOUCH, "var(--accent)", 1), (T_TOUCH + 0.5, SUCCESS, 1), (13.5, SUCCESS, 1), (14, WARNING, 1), (CHARGE_START, WARNING, 1)]
    led += [(t, WARNING, 0.25 if i % 2 == 0 else 1) for i, t in enumerate(LED_BLINK)]
    led += [(47.5, WARNING, 1), (CHARGE_END, SUCCESS, 1), (49.9, SUCCESS, 1)]
    out.append(keyframes("n3-led", [(t, f"background: {c}; box-shadow: 0 0 6px 1px {c}; opacity: {o};") for t, c, o in two_visits(led)]))

    # guidance beam over the active pad
    out.append(keyframes("n3-beam", [(t, f"opacity: {o};") for t, o in two_visits([(0, 0), (1.5, 1), (7.4, 1), (9, 0), (49.9, 0)])]))
    out.append(keyframes("n3-beam-pos", [(t, f"translate: {x}px 0 {PAD_Z}px;") for t, x in ((0, -PAD_X), (49.9, -PAD_X), (50, PAD_X), (100, PAD_X))]))

    # step pills
    steps = {
        "land": [(0, 0), (0.5, 0), (1, 1), (T_STOP - 0.5, 1), (T_STOP, 0), (49.9, 0)],
        "swap": [(0, 0), (13.5, 0), (14, 1), (SWAP_END, 1), (SWAP_END + 0.5, 0), (49.9, 0)],
        "fly": [(0, 0), (T_LIFT, 0), (T_LIFT + 0.5, 1), (T_GONE, 1), (T_GONE + 0.5, 0), (49.9, 0)],
        "charge": [(0, 0), (CHARGE_START - 0.5, 0), (CHARGE_START, 1), (48, 1), (48.5, 0), (49.9, 0)],
    }
    for n, track in steps.items():
        out.append(keyframes(f"n3-step-{n}", [(t, PILL_ON if o else PILL_OFF) for t, o in two_visits(track)]))
    return "\n".join(out) + "\n\n"


def main():
    block = build()
    if "--print" in sys.argv:
        print(block, end="")
        return
    with HTML.open(encoding="utf-8", newline="") as f:  # keep the file's own line endings
        text = f.read()
    nl = "\r\n" if "\r\n" in text else "\n"
    pattern = re.compile(re.escape(START.replace("\n", nl)) + r".*?(?=" + re.escape(END) + ")", re.S)
    new, n = pattern.subn(lambda m: block.replace("\n", nl), text, count=1)
    if n != 1:
        sys.exit(f"block markers not found in {HTML}")
    HTML.write_text(new, encoding="utf-8", newline="")
    print(f"wrote {len(block.splitlines())} lines into {HTML}")


if __name__ == "__main__":
    main()
