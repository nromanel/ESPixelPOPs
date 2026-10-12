#!/usr/bin/env python3
"""ESPixel Pops, rebuilt from the rev D schematic (2017-07-19) and the v3 build guide.

The original gerbers were never published. This is the same circuit, the same
through-hole parts, and the same placement the build photos show: terminal on
the left, serial header on the top, ESP-01 socket on the right with the
antenna hanging off the board.

Y in this file increases downward, which is KiCad's board axis.
"""

from __future__ import annotations

import heapq
import math
import uuid
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent
G = 0.127  # 5 mil router grid
BOARD_W = 45.72  # 1.80 in
BOARD_H = 25.40  # 1.00 in, slides into 1 in schedule-40 PVC

# Nets. 0 is no-connect.
NETS = {
    1: "GND",
    2: "VIN",
    3: "+3V3",
    4: "V5",
    5: "GPIO2",
    6: "GPIO0",
    7: "PIX",
    8: "ESP_RX",
    9: "ESP_TX",
    10: "PROG_TX",
}


def uid() -> str:
    return str(uuid.uuid4())


def snap(v: float) -> float:
    return round(round(v / G) * G, 3)


class Pad:
    def __init__(self, num, x, y, size, drill, net, shape="circle"):
        self.num = str(num)
        self.x = snap(x)
        self.y = snap(y)
        self.size = size
        self.drill = drill
        self.net = net
        self.shape = shape


class Part:
    def __init__(self, ref, value, footprint, pads, silk=None):
        self.ref = ref
        self.value = value
        self.footprint = footprint
        self.pads = pads
        self.silk = silk or []


def P(num, x, y, size, drill, net, shape="circle"):
    return Pad(num, x, y, size, drill, net, shape)


def build_parts() -> list[Part]:
    """Placement follows the build-guide photos. Terminal pin 1 is at the top."""
    gnd, vin, v33, v5 = 1, 2, 3, 4
    gpio2, gpio0, pix = 5, 6, 7
    esp_rx, esp_tx, prog_tx = 8, 9, 10

    # 5-position 3.81 mm terminal. Wire entries face off the left edge.
    # 1 VCC, 2 GND, 3 pixel GND, 4 DATA, 5 pixel VCC.
    jy = [5.08, 8.89, 12.70, 16.51, 20.32]
    jnets = [vin, gnd, gnd, pix, vin]
    j1 = Part(
        "J1",
        "TERM_5_3.81",
        "TerminalBlock:TerminalBlock_MaiXu_MX126-5.0_1x05_P3.81mm",
        [P(i + 1, 3.81, jy[i], 1.9, 1.1, jnets[i], "rect" if i == 0 else "circle") for i in range(5)],
    )

    # SparkFun-style FTDI header. Left to right matches the silkscreen
    # GND  CTS  VCC  RX  TX  DTR. RX is the ESP RX pin (adapter TX).
    # VCC is pixel VIN. Do not power the board from the adapter.
    hx = [24.13, 26.67, 29.21, 31.75, 34.29, 36.83]
    hnets = [gnd, 0, vin, prog_tx, esp_tx, 0]
    hnames_shape = ["rect", "circle", "circle", "circle", "circle", "circle"]
    jp1 = Part(
        "JP1",
        "SERIAL_1x06",
        "Connector:PinHeader_1x06_P2.54mm_Vertical",
        [P(6 - i, hx[i], 2.54, 1.7, 1.0, hnets[i], hnames_shape[i]) for i in range(6)],
    )
    # Pin numbers: left pad is pad 6 (GND), right pad is pad 1 (DTR),
    # matching the original ESPixel 1X06_LOCK wiring.

    # LD1117V33. Tab faces the terminal (left). Pin 1 is the square pad.
    # TO-220, looking at the front with the tab behind: 1 GND, 2 OUT, 3 IN.
    # Laid with the tab to the left, pin 3 (IN) is the top pin.
    u1 = Part(
        "U1",
        "LD1117V33",
        "Package_TO_SOT_THT:TO-220-3_Vertical",
        [
            P(3, 13.97, 6.35, 1.8, 1.0, vin),
            P(2, 13.97, 8.89, 1.8, 1.0, v33),
            P(1, 13.97, 11.43, 1.8, 1.0, gnd, "rect"),
        ],
    )

    c1 = Part(
        "C1",
        "100n",
        "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P2.54mm",
        [
            P(1, 19.05, 5.08, 1.6, 0.8, vin),
            P(2, 19.05, 7.62, 1.6, 0.8, gnd),
        ],
    )
    c2 = Part(
        "C2",
        "220uF",
        "Capacitor_THT:CP_Radial_D5.0mm_P2.54mm",
        [
            P(1, 19.05, 10.16, 1.7, 0.8, v33, "rect"),
            P(2, 19.05, 12.70, 1.7, 0.8, gnd),
        ],
    )

    # 78L05, flat facing the resistors (right). Middle pin (GND) is bent
    # away from the flat, toward the terminal. Pads 1 and 3 are the 5 V jumper.
    # Looking at the flat, pins down: 1 OUT, 2 GND, 3 IN.
    # Flat-to-the-right puts pin 1 (VO) on the bottom and pin 3 (VI) on top.
    ic1 = Part(
        "IC1",
        "78L05",
        "Package_TO_SOT_THT:TO-92_Inline",
        [
            P(3, 12.70, 14.605, 1.6, 0.8, vin),
            P(2, 10.795, 15.875, 1.6, 0.8, gnd),
            P(1, 12.70, 17.145, 1.6, 0.8, v5, "rect"),
        ],
    )

    # 2N7000 level shifter. Flat faces the terminal.
    # Looking at the flat, pins down: 1 Source, 2 Gate, 3 Drain.
    # Source is the top pad, drain is the bottom pad, gate is offset right.
    q1 = Part(
        "Q1",
        "2N7000",
        "Package_TO_SOT_THT:TO-92_Inline",
        [
            P(1, 8.89, 18.415, 1.6, 0.8, gpio2, "rect"),
            P(2, 10.795, 19.685, 1.6, 0.8, v33),
            P(3, 8.89, 20.955, 1.6, 0.8, pix),
        ],
    )

    # 1/4 W resistors formed to 0.4 in. R2 is left of R1, as on the silkscreen.
    r2 = Part(
        "R2",
        "330",
        "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm",
        [
            P(1, 16.51, 15.24, 1.6, 0.8, v5),
            P(2, 16.51, 22.86, 1.6, 0.8, pix),
        ],
    )
    r1 = Part(
        "R1",
        "330",
        "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm",
        [
            # Shifted up so the bottom pad stays 0.5 mm clear of the board edge.
            P(1, 19.05, 16.256, 1.6, 0.8, v33),
            P(2, 19.05, 23.876, 1.6, 0.8, gpio2),
        ],
    )

    # 6 mm tact, 6.5 x 4.5 mm pin pitch snapped to the 5 mil grid.
    # Pins 1-2 are one contact, pins 3-4 the other.
    bx, by = 25.40, 20.32
    s1 = Part(
        "S1",
        "SW_PUSH",
        "Button_Switch_THT:SW_PUSH_6mm",
        [
            P(1, bx - 3.302, by - 2.286, 1.7, 1.0, gpio0),
            P(2, bx + 3.302, by - 2.286, 1.7, 1.0, gpio0),
            P(3, bx + 3.302, by + 2.286, 1.7, 1.0, gnd),
            P(4, bx - 3.302, by + 2.286, 1.7, 1.0, gnd),
        ],
    )

    # ESP-01 socket. Antenna hangs off the right edge.
    # Row closer to the antenna (right): GND, GPIO2, GPIO0, RX from top to bottom.
    # Other row: TX, CH_PD, RST, VCC. This is the SparkFun 2X4 used on the
    # original ESPixel, rotated so the antenna side faces +X.
    sx, sy = 33.02, 16.51
    u2 = Part(
        "U2",
        "ESP-01",
        "Connector:PinSocket_2x04_P2.54mm_Vertical",
        [
            P(1, sx - 1.27, sy - 3.81, 1.5, 0.9, esp_tx),
            P(3, sx - 1.27, sy - 1.27, 1.5, 0.9, v33),
            P(5, sx - 1.27, sy + 1.27, 1.5, 0.9, 0),
            P(7, sx - 1.27, sy + 3.81, 1.5, 0.9, v33, "rect"),
            P(2, sx + 1.27, sy - 3.81, 1.5, 0.9, gnd),
            P(4, sx + 1.27, sy - 1.27, 1.5, 0.9, gpio2),
            P(6, sx + 1.27, sy + 1.27, 1.5, 0.9, gpio0),
            P(8, sx + 1.27, sy + 3.81, 1.5, 0.9, esp_rx),
        ],
    )

    # 1N4148. Cathode (band) is the top pad, toward the serial header.
    # Anode to ESP RX, cathode to the adapter TX pin.
    d1 = Part(
        "D1",
        "1N4148",
        "Diode_THT:D_DO-35_SOD27_P7.62mm_Vertical",
        [
            P("C", 40.64, 11.43, 1.6, 0.8, prog_tx, "rect"),
            P("A", 40.64, 19.05, 1.6, 0.8, esp_rx),
        ],
    )
    return [j1, jp1, u1, c1, c2, ic1, q1, r2, r1, s1, u2, d1]


HOLES = [(22.86, 8.89, 3.2), (42.545, 22.86, 3.2)]


def check_clearance(parts: list[Part]) -> None:
    pads = [(p.ref, pad) for p in parts for pad in p.pads]
    problems = []
    for i, (ra, a) in enumerate(pads):
        if not (0.8 < a.x < BOARD_W - 0.8 and 0.8 < a.y < BOARD_H - 0.8):
            problems.append(f"{ra}.{a.num} at {a.x:.2f},{a.y:.2f} is off the board")
        for rb, b in pads[i + 1 :]:
            need = (a.size + b.size) / 2 + 0.2
            dist = math.hypot(a.x - b.x, a.y - b.y)
            if dist < need - 1e-6:
                problems.append(
                    f"{ra}.{a.num} overlaps {rb}.{b.num} by {need - dist:.2f} mm"
                )
        for hx, hy, hd in HOLES:
            need = a.size / 2 + hd / 2 + 0.3
            dist = math.hypot(a.x - hx, a.y - hy)
            if dist < need:
                problems.append(f"{ra}.{a.num} collides with mounting hole")
    if problems:
        raise SystemExit("placement:\n  " + "\n  ".join(problems))


def copper_hits(x, y, px, py, size, shape, extra) -> bool:
    """True when (x, y) comes within extra of the pad copper.

    Square pads are their real outline. A circle test misses the corners and
    lets a track run beside the flat of the square with less than 0.2 mm gap.
    """
    half = size / 2
    if shape == "rect":
        dx = abs(x - px) - half
        dy = abs(y - py) - half
        if dx <= 0 and dy <= 0:
            return True
        if dx > 0 and dy > 0:
            return dx * dx + dy * dy < extra * extra - 1e-12
        return max(dx, dy) < extra - 1e-12
    return (x - px) ** 2 + (y - py) ** 2 < (half + extra) ** 2 - 1e-12


def disk_cells(ix, iy, radius_mm):
    """Grid cells whose centers lie inside a circle of radius_mm."""
    if radius_mm <= 0:
        return [(ix, iy)]
    rad = int(math.floor(radius_mm / G + 1e-9))
    limit = (radius_mm / G) ** 2 + 1e-6
    cells = []
    for dy in range(-rad, rad + 1):
        for dx in range(-rad, rad + 1):
            if dx * dx + dy * dy <= limit:
                cells.append((ix + dx, iy + dy))
    return cells


def route(parts: list[Part]) -> tuple[list[tuple], list[tuple]]:
    """Two-layer A* router. Returns (segments, vias).

    A segment is (x1, y1, x2, y2, width, layer, net).
    A via is (x, y, net).

    The search target is the centerline of copper already on the net (pad
    centers and trace centers). The clearance map is a separate disk, so a
    route cannot stop on the halo around a pad and call that a connection.
    """
    nx = int(round(BOARD_W / G)) + 1
    ny = int(round(BOARD_H / G)) + 1

    def cell(x, y):
        return int(round(x / G)), int(round(y / G))

    pads = [(p.ref, pad) for p in parts for pad in p.pads]
    pad_geom = [(a.x, a.y, a.size, a.shape, a.drill, a.net) for _, a in pads]

    def blocked(ix, iy, net, width, layer_via=False):
        x, y = ix * G, iy * G
        # 0.51 mm keeps copper 0.5 mm off the outline after KiCad's rounding.
        inset = 0.51 + (0.4 if layer_via else width / 2)
        if x < inset or y < inset or x > BOARD_W - inset or y > BOARD_H - inset:
            return True
        # 0.22 mm is the 0.2 mm rule plus a little so a grid step cannot land on 0.199.
        extra = (0.4 if layer_via else width / 2) + 0.22
        for px, py, size, shape, drill, pnet in pad_geom:
            # A through-hole already joins the layers. A via in that drill is a
            # second hole in the same spot, which KiCad rejects.
            if layer_via and (x - px) ** 2 + (y - py) ** 2 < (drill / 2 + 0.2 + 0.27) ** 2:
                return True
            if pnet == net and pnet != 0:
                continue
            if copper_hits(x, y, px, py, size, shape, extra):
                return True
        for hx, hy, hd in HOLES:
            if (x - hx) ** 2 + (y - hy) ** 2 < (hd / 2 + extra) ** 2 - 1e-9:
                return True
        if layer_via:
            for vx, vy, _vnet in vias:
                if (x - vx) ** 2 + (y - vy) ** 2 < (0.2 + 0.2 + 0.27) ** 2:
                    return True
        return False

    # keep: cells covered by this net's copper. spine: centerline cells a
    # later trace must actually reach.
    keep = [dict(), dict()]
    spine = [dict(), dict()]
    vias: list[tuple] = []
    raw_paths: list[tuple] = []

    def claim(ix, iy, net, layer, radius_mm):
        for cx, cy in disk_cells(ix, iy, radius_mm):
            prev = keep[layer].get((cx, cy))
            if prev not in (None, net):
                raise SystemExit(
                    f"route overlap {NETS[net]} and {NETS[prev]} at {cx * G:.2f},{cy * G:.2f}"
                )
            keep[layer][(cx, cy)] = net

    nets: dict[int, list[Pad]] = {}
    for _, pad in pads:
        if pad.net:
            nets.setdefault(pad.net, []).append(pad)

    # Signals first so the short pixel and serial wires keep the top layer.
    order = [9, 10, 8, 5, 6, 7, 4, 3, 2, 1]
    width_of = {1: 0.508, 2: 0.508, 3: 0.508, 4: 0.381}
    prefer = {1: 1, 2: 1, 3: 1}  # GND, VIN and 3.3 V on the back

    for net in order:
        group = nets[net]
        width = width_of.get(net, 0.254)
        sx, sy = cell(group[0].x, group[0].y)
        for layer in (0, 1):
            spine[layer][(sx, sy)] = net
            claim(sx, sy, net, layer, group[0].size / 2)

        for pad in group[1:]:
            src = cell(pad.x, pad.y)
            targets = {
                (c[0], c[1], layer)
                for layer in (0, 1)
                for c, n in spine[layer].items()
                if n == net
            }
            path = astar(
                src, targets, net, width, keep, blocked, prefer.get(net, 0), nx, ny
            )
            if path is None:
                raise SystemExit(f"no route for {NETS[net]} to pad at {pad.x:.2f},{pad.y:.2f}")
            raw_paths.append((path, width, net))
            for ix, iy, layer in path:
                spine[layer][(ix, iy)] = net
                claim(ix, iy, net, layer, width / 2)
            for a, b in zip(path, path[1:]):
                if a[2] != b[2] and a[0] == b[0] and a[1] == b[1]:
                    vias.append((a[0] * G, a[1] * G, net))
                    claim(a[0], a[1], net, 0, 0.4)
                    claim(a[0], a[1], net, 1, 0.4)
            for layer in (0, 1):
                spine[layer][src] = net
                claim(src[0], src[1], net, layer, pad.size / 2)
        print(f"  routed {NETS[net]} ({len(group)} pads)", flush=True)

    segments = []
    for path, width, net in raw_paths:
        segments.extend(collapse(path, width, net))
    return segments, vias


def near_foreign(copper, ix, iy, layer, net, need_mm) -> bool:
    for cx, cy in disk_cells(ix, iy, need_mm):
        prev = copper[layer].get((cx, cy))
        if prev not in (None, net):
            return True
    return False


def astar(src, targets, net, width, copper, blocked, prefer_layer, nx, ny):
    """Route from a pad center to any centerline cell of the same net.

    State is (x, y, layer, incoming_dx, incoming_dy). A turn costs extra so
    the trace runs straight until it has to go around something.
    """
    sx, sy = src
    starts = [(sx, sy, prefer_layer, 0, 0)]
    goal = set(targets)
    if not goal:
        return None

    dist = {}
    dq = deque()
    for tx, ty, _layer in targets:
        if (tx, ty) not in dist and 0 <= tx < nx and 0 <= ty < ny:
            dist[(tx, ty)] = 0
            dq.append((tx, ty))
    while dq:
        x, y = dq.popleft()
        base = dist[(x, y)]
        for nx_, ny_ in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if (nx_, ny_) in dist or not (0 <= nx_ < nx and 0 <= ny_ < ny):
                continue
            dist[(nx_, ny_)] = base + 1
            dq.append((nx_, ny_))

    def h(ix, iy):
        return dist.get((ix, iy), abs(ix - sx) + abs(iy - sy))

    open_heap = []
    seen = {}
    parent = {}
    for s in starts:
        heapq.heappush(open_heap, (h(s[0], s[1]), 0, s))
        seen[s] = 0
        parent[s] = None

    while open_heap:
        _score, cost, state = heapq.heappop(open_heap)
        if seen.get(state, 1e18) < cost:
            continue
        ix, iy, layer, pdx, pdy = state
        hit = None
        if (ix, iy, layer) in goal:
            hit = state
        else:
            for other in (0, 1):
                if other != layer and (ix, iy, other) in goal:
                    landed = (ix, iy, other, 0, 0)
                    parent[landed] = state
                    hit = landed
                    break
        if hit is not None and (ix, iy) != (sx, sy):
            path = []
            cur = hit
            while cur is not None:
                path.append((cur[0], cur[1], cur[2]))
                cur = parent[cur]
            path.reverse()
            return path
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt_xy = (ix + dx, iy + dy)
            if blocked(nxt_xy[0], nxt_xy[1], net, width):
                continue
            if near_foreign(copper, nxt_xy[0], nxt_xy[1], layer, net, width / 2 + 0.22):
                continue
            turn = 0 if (pdx, pdy) in ((0, 0), (dx, dy)) else 5
            layer_pen = 0 if layer == prefer_layer else 2
            ncost = cost + 1 + turn + layer_pen
            nxt = (nxt_xy[0], nxt_xy[1], layer, dx, dy)
            if ncost < seen.get(nxt, 1e18):
                seen[nxt] = ncost
                parent[nxt] = state
                heapq.heappush(open_heap, (ncost + h(nxt_xy[0], nxt_xy[1]), ncost, nxt))
        other_layer = 1 - layer
        if blocked(ix, iy, net, width, layer_via=True):
            continue
        if near_foreign(copper, ix, iy, 0, net, 0.6) or near_foreign(copper, ix, iy, 1, net, 0.6):
            continue
        via_state = (ix, iy, other_layer, 0, 0)
        ncost = cost + 12
        if ncost < seen.get(via_state, 1e18):
            seen[via_state] = ncost
            parent[via_state] = state
            heapq.heappush(open_heap, (ncost + h(ix, iy), ncost, via_state))
    return None


def collapse(path, width, net):
    """Merge a grid path into straight segments, splitting on layer changes."""
    if len(path) < 2:
        return []
    segs = []
    run = [path[0]]
    for prev, cur in zip(path, path[1:]):
        if cur[2] != prev[2]:
            segs.extend(_straight(run, width, net))
            run = [cur]
            continue
        run.append(cur)
    segs.extend(_straight(run, width, net))
    return segs


def _straight(run, width, net):
    if len(run) < 2:
        return []
    pts = [(p[0] * G, p[1] * G, p[2]) for p in run]
    out = []
    anchor = pts[0]
    prev_dir = None
    for a, b in zip(pts, pts[1:]):
        d = (math.copysign(1, b[0] - a[0]) if b[0] != a[0] else 0,
             math.copysign(1, b[1] - a[1]) if b[1] != a[1] else 0)
        if prev_dir is None:
            prev_dir = d
            continue
        if d != prev_dir:
            out.append((anchor[0], anchor[1], a[0], a[1], width, a[2], net))
            anchor = a
            prev_dir = d
    end = pts[-1]
    out.append((anchor[0], anchor[1], end[0], end[1], width, end[2], net))
    return [s for s in out if (s[0], s[1]) != (s[2], s[3])]


def verify(parts, segments, vias) -> None:
    """Flood-fill each net. A through-hole pad joins the two layers at its center."""
    pads = [pad for p in parts for pad in p.pads if pad.net]
    occ = [dict(), dict()]

    def add(layer, ix, iy, net):
        occ[layer].setdefault((ix, iy), set()).add(net)

    pad_centers = []
    for pad in pads:
        ix, iy = int(round(pad.x / G)), int(round(pad.y / G))
        pad_centers.append((pad, ix, iy))
        for layer in (0, 1):
            if pad.shape == "rect":
                half = pad.size / 2
                reach = int(math.ceil(half / G)) + 1
                cells = [
                    (ix + dx, iy + dy)
                    for dx in range(-reach, reach + 1)
                    for dy in range(-reach, reach + 1)
                    if abs(dx * G) <= half + 1e-6 and abs(dy * G) <= half + 1e-6
                ]
            else:
                cells = disk_cells(ix, iy, pad.size / 2)
            for cx, cy in cells:
                add(layer, cx, cy, pad.net)
    for x1, y1, x2, y2, width, layer, net in segments:
        steps = int(max(abs(x2 - x1), abs(y2 - y1)) / G) + 1
        for i in range(steps + 1):
            t = i / max(steps, 1)
            ix = int(round((x1 + (x2 - x1) * t) / G))
            iy = int(round((y1 + (y2 - y1) * t) / G))
            for cx, cy in disk_cells(ix, iy, width / 2):
                add(layer, cx, cy, net)
    for x, y, net in vias:
        ix, iy = int(round(x / G)), int(round(y / G))
        for layer in (0, 1):
            for cx, cy in disk_cells(ix, iy, 0.4):
                add(layer, cx, cy, net)

    shorts = []
    for layer in (0, 1):
        for cell, nets in occ[layer].items():
            real = {n for n in nets if n}
            if len(real) > 1:
                shorts.append((cell, sorted(NETS[n] for n in real)))
    if shorts:
        sample = ", ".join(f"{names} @ {c}" for c, names in shorts[:8])
        raise SystemExit(f"{len(shorts)} shorted cells, e.g. {sample}")

    cells_of = defaultdict(set)
    for layer in (0, 1):
        for cell, nets in occ[layer].items():
            for n in nets:
                cells_of[n].add((layer, cell[0], cell[1]))
    # Vias and plated pad holes are the only places the two layers meet.
    for x, y, net in vias:
        ix, iy = int(round(x / G)), int(round(y / G))
        cells_of[net].add((2, ix, iy))
    for pad, ix, iy in pad_centers:
        cells_of[pad.net].add((2, ix, iy))

    def neighbors(node):
        layer, x, y = node
        if layer == 2:
            return ((0, x, y), (1, x, y))
        return (
            (layer, x + 1, y),
            (layer, x - 1, y),
            (layer, x, y + 1),
            (layer, x, y - 1),
            (2, x, y),
        )

    for net, cells in cells_of.items():
        pads_n = [(pad, ix, iy) for pad, ix, iy in pad_centers if pad.net == net]
        _pad, ix, iy = pads_n[0]
        stack = [(0, ix, iy)]
        seen = set()
        while stack:
            c = stack.pop()
            if c in seen or c not in cells:
                continue
            seen.add(c)
            stack.extend(neighbors(c))
        for pad, px, py in pads_n[1:]:
            if (2, px, py) not in seen and (0, px, py) not in seen and (1, px, py) not in seen:
                raise SystemExit(f"{NETS[net]} pad at {pad.x:.2f},{pad.y:.2f} is not connected")
    print(f"routed {len(segments)} segments, {len(vias)} vias, {len(cells_of)} nets, no shorts")


def build_silk(parts):
    """Body outlines and BOM reference designators, broken where they meet a pad."""
    texts = []
    segs = []
    pads = [pad for part in parts for pad in part.pads]

    def clear_of_copper(x, y, extra=0.4):
        # 0.4 mm clears the pad, the 0.05 mm mask swell, and the 0.12 mm silk stroke.
        if not (0.2 < x < BOARD_W - 0.2 and 0.2 < y < BOARD_H - 0.2):
            return False
        for pad in pads:
            if copper_hits(x, y, pad.x, pad.y, pad.size, pad.shape, extra):
                return False
        for hx, hy, hd in HOLES:
            if (x - hx) ** 2 + (y - hy) ** 2 < (hd / 2 + extra) ** 2:
                return False
        return True

    def silk_line(x1, y1, x2, y2):
        length = math.hypot(x2 - x1, y2 - y1)
        steps = max(2, int(length / 0.12))
        run = None
        for i in range(steps + 1):
            t = i / steps
            x = x1 + (x2 - x1) * t
            y = y1 + (y2 - y1) * t
            if clear_of_copper(x, y):
                if run is None:
                    run = (x, y)
                end = (x, y)
            elif run is not None:
                if math.hypot(end[0] - run[0], end[1] - run[1]) > 0.25:
                    segs.append((run[0], run[1], end[0], end[1]))
                run = None
        if run is not None and math.hypot(end[0] - run[0], end[1] - run[1]) > 0.25:
            segs.append((run[0], run[1], end[0], end[1]))

    def box(x0, y0, x1, y1):
        silk_line(x0, y0, x1, y0)
        silk_line(x1, y0, x1, y1)
        silk_line(x1, y1, x0, y1)
        silk_line(x0, y1, x0, y0)

    def circle(cx, cy, r, steps=20):
        for i in range(steps):
            a0 = 2 * math.pi * i / steps
            a1 = 2 * math.pi * (i + 1) / steps
            silk_line(cx + r * math.cos(a0), cy + r * math.sin(a0), cx + r * math.cos(a1), cy + r * math.sin(a1))

    def to92(flat_x, y0, y1, bulge_x, steps=10):
        silk_line(flat_x, y0, flat_x, y1)
        cy = (y0 + y1) / 2
        ry = (y1 - y0) / 2
        sign = 1 if bulge_x > flat_x else -1
        rx = abs(bulge_x - flat_x)
        for i in range(steps):
            t0 = -math.pi / 2 + math.pi * i / steps
            t1 = -math.pi / 2 + math.pi * (i + 1) / steps
            silk_line(
                flat_x + sign * rx * math.cos(t0),
                cy + ry * math.sin(t0),
                flat_x + sign * rx * math.cos(t1),
                cy + ry * math.sin(t1),
            )

    def label(text, x, y, size=0.8, rot=0):
        texts.append((text, x, y, size, rot))

    # J1, 5-position terminal. Wire entries face the left edge.
    box(0.55, 3.3, 7.15, 22.15)
    label("J1", 2.15, 3.9, 0.7)
    label("Power", 1.25, 8.2, 0.55, 90)
    label("Pixels", 1.25, 17.4, 0.55, 90)
    # Turned so the words stay inside the outline. Upright, they cross the box.
    for y, name in (
        (5.08, "1 VCC"),
        (8.89, "2 GND"),
        (12.70, "3 GND"),
        (16.51, "4 DAT"),
        (20.32, "5 VCC"),
    ):
        label(name, 6.15, y, 0.48, 90)

    # U1 LD1117V33. Tab (3.3 V) faces the terminal.
    box(10.3, 4.7, 16.4, 13.1)
    box(7.7, 6.5, 10.3, 11.3)
    label("U1", 13.3, 3.9, 0.85)
    label("3.3V", 8.95, 8.9, 0.5)

    # C1 0.1 uF disc between its leads.
    circle(19.05, 6.35, 2.35)
    label("C1", 23.15, 5.55, 0.75)
    label("100n", 23.2, 6.45, 0.42)

    # C2 220 uF. Square pad is the positive lead (the upper one).
    circle(19.05, 11.43, 2.55)
    # Positive mark, up and left of the square pad so it stays off the mask opening.
    silk_line(16.80, 9.15, 17.50, 9.15)
    silk_line(17.15, 8.80, 17.15, 9.50)
    label("C2", 23.15, 12.15, 0.8)
    label("220u", 23.3, 13.05, 0.45)

    # IC1 78L05. Flat faces the resistors. The bracket marks the 5 V jumper, pads 1 and 3.
    to92(14.45, 13.3, 18.3, 9.0)
    silk_line(14.9, 14.55, 15.4, 14.55)
    silk_line(15.4, 14.55, 15.4, 17.2)
    silk_line(15.4, 17.2, 14.9, 17.2)
    label("IC1", 8.15, 15.9, 0.75)
    label("1-3", 8.35, 14.55, 0.48)

    # Q1 2N7000. Flat faces the terminal. Square pad is the source.
    to92(7.55, 17.2, 22.05, 12.15)
    label("Q1", 13.5, 22.7, 0.7)
    label("S", 12.55, 18.35, 0.48)
    label("D", 12.55, 21.05, 0.48)

    # R2 is the left resistor, R1 the right. Both 330 ohm.
    box(15.35, 16.55, 17.65, 21.55)
    label("330", 16.5, 19.05, 0.5)
    label("R2", 14.2, 19.05, 0.75)
    box(17.95, 17.60, 20.15, 22.80)
    label("330", 19.05, 20.07, 0.5)
    label("R1", 21.15, 16.15, 0.75)

    # S1 6 mm tact. The frame sits outside the four pins.
    box(20.75, 16.75, 30.05, 23.95)
    label("S1", 25.4, 20.32, 0.85)

    # JP1 serial header.
    box(22.9, 0.45, 38.05, 1.55)
    silk_line(22.9, 1.55, 22.9, 3.55)
    silk_line(38.05, 1.55, 38.05, 3.55)
    label("JP1", 20.4, 1.15, 0.65)
    for text, x in (("GND", 24.13), ("CTS", 26.67), ("VCC", 29.21), ("RX", 31.75), ("TX", 34.29), ("DTR", 36.83)):
        label(text, x, 4.35, 0.5)

    # U2 ESP-01 socket. Antenna hangs off the right edge.
    box(30.35, 11.35, 35.7, 21.55)
    label("U2", 33.02, 22.55, 0.8)
    label("ESP-01", 33.02, 23.45, 0.5)
    label("ANT", 38.4, 9.3, 0.55)

    # D1 1N4148. The bar is the cathode and faces the header. The triangle points at the bar.
    silk_line(39.75, 12.85, 41.55, 12.85)
    silk_line(39.75, 16.15, 40.64, 13.2)
    silk_line(41.55, 16.15, 40.64, 13.2)
    silk_line(39.75, 16.15, 41.55, 16.15)
    label("D1", 43.15, 15.2, 0.8)
    label("K", 43.0, 12.7, 0.5)

    label("ESPixel Pops", 11.2, 1.7, 1.0)
    for hx, hy in ((26.3, 8.89), (39.2, 24.15)):
        label("M3", hx, hy, 0.5)

    problems = []
    for text, x, y, size, rot in texts:
        width = size * 0.62 * len(text)
        height = size
        if rot % 180 == 90:
            width, height = height, width
        for px, py in (
            (x, y),
            (x - width / 2, y),
            (x + width / 2, y),
            (x, y - height / 2),
            (x, y + height / 2),
        ):
            if not (0.15 < px < BOARD_W - 0.15 and 0.15 < py < BOARD_H - 0.15):
                problems.append(f"{text} hangs off the board")
                break
            hit = False
            for pad in pads:
                if (px - pad.x) ** 2 + (py - pad.y) ** 2 < (pad.size / 2 + 0.12) ** 2:
                    problems.append(f"{text} overlaps a pad at {pad.x:.2f},{pad.y:.2f}")
                    hit = True
                    break
            if hit:
                break
            for hx, hy, hd in HOLES:
                if (px - hx) ** 2 + (py - hy) ** 2 < (hd / 2 + 0.2) ** 2:
                    problems.append(f"{text} overlaps a mounting hole")
                    hit = True
                    break
            if hit:
                break
    if problems:
        raise SystemExit("silkscreen:\n  " + "\n  ".join(problems))
    return texts, segs


def write_pcb(parts, segments, vias) -> None:
    lines = [
        '(kicad_pcb (version 20240108) (generator "espixelpops")',
        "  (general (thickness 1.6) (legacy_teardrops no))",
        '  (paper "A4")',
        "  (layers",
        '    (0 "F.Cu" signal)',
        '    (31 "B.Cu" signal)',
        '    (36 "B.SilkS" user)',
        '    (37 "F.SilkS" user)',
        '    (38 "B.Mask" user)',
        '    (39 "F.Mask" user)',
        '    (44 "Edge.Cuts" user)',
        '    (46 "B.CrtYd" user)',
        '    (47 "F.CrtYd" user)',
        '    (48 "B.Fab" user)',
        '    (49 "F.Fab" user)',
        "  )",
        "  (setup",
        "    (pad_to_mask_clearance 0.05)",
        "    (allow_soldermask_bridges_in_footprints no)",
        "  )",
    ]
    lines.append('  (net 0 "")')
    for num, name in NETS.items():
        lines.append(f'  (net {num} "{name}")')

    def silkt(text, x, y, size=0.7, rot=0):
        lines.append(
            f'  (gr_text "{text}" (at {x:.3f} {y:.3f} {rot}) (layer "F.SilkS") '
            f'(uuid "{uid()}") (effects (font (size {size} {size}) (thickness {size * 0.15:.3f}))))'
        )

    def line(x1, y1, x2, y2, layer="F.SilkS", width=0.12):
        lines.append(
            f"  (gr_line (start {x1:.3f} {y1:.3f}) (end {x2:.3f} {y2:.3f}) "
            f'(stroke (width {width}) (type solid)) (layer "{layer}") (uuid "{uid()}"))'
        )

    # Outline
    corners = [(0, 0), (BOARD_W, 0), (BOARD_W, BOARD_H), (0, BOARD_H)]
    for a, b in zip(corners, corners[1:] + corners[:1]):
        line(a[0], a[1], b[0], b[1], "Edge.Cuts", 0.1)

    silk_text, silk_lines = build_silk(parts)
    for text, x, y, size, rot in silk_text:
        silkt(text, x, y, size, rot)
    for x1, y1, x2, y2 in silk_lines:
        line(x1, y1, x2, y2)

    for hx, hy, hd in HOLES:
        lines.append(
            f'  (footprint "MountingHole:MountingHole_{hd:.1f}mm" (layer "F.Cu") (uuid "{uid()}") '
            f"(at {hx:.3f} {hy:.3f}) "
            f'(pad "" np_thru_hole circle (at 0 0) (size {hd:.3f} {hd:.3f}) (drill {hd:.3f}) '
            f'(layers "*.Cu" "*.Mask") (uuid "{uid()}")))'
        )

    for part in parts:
        xs = [p.x for p in part.pads]
        ys = [p.y for p in part.pads]
        ax, ay = min(xs), min(ys)
        lines.append(f'  (footprint "{part.footprint}" (layer "F.Cu") (uuid "{uid()}") (at {ax:.3f} {ay:.3f})')
        lines.append(
            f'    (property "Reference" "{part.ref}" (at 0 -1.4) (layer "F.SilkS") (uuid "{uid()}") '
            f"(effects (font (size 0.6 0.6) (thickness 0.09)) hide))"
        )
        lines.append(
            f'    (property "Value" "{part.value}" (at 0 1.4) (layer "F.Fab") (uuid "{uid()}") '
            f"(effects (font (size 0.5 0.5) (thickness 0.08)) hide))"
        )
        for pad in part.pads:
            net = f' (net {pad.net} "{NETS[pad.net]}")' if pad.net else ""
            shape = "rect" if pad.shape == "rect" else "circle"
            lines.append(
                f'    (pad "{pad.num}" thru_hole {shape} (at {pad.x - ax:.3f} {pad.y - ay:.3f}) '
                f"(size {pad.size:.3f} {pad.size:.3f}) (drill {pad.drill:.3f}) "
                f'(layers "*.Cu" "*.Mask"){net} (uuid "{uid()}"))'
            )
        lines.append("  )")

    layer_name = {0: "F.Cu", 1: "B.Cu"}
    for x1, y1, x2, y2, width, layer, net in segments:
        lines.append(
            f"  (segment (start {x1:.3f} {y1:.3f}) (end {x2:.3f} {y2:.3f}) "
            f'(width {width:.3f}) (layer "{layer_name[layer]}") (net {net}) (uuid "{uid()}"))'
        )
    for x, y, net in vias:
        lines.append(
            f'  (via (at {x:.3f} {y:.3f}) (size 0.8) (drill 0.4) (layers "F.Cu" "B.Cu") '
            f'(net {net}) (uuid "{uid()}"))'
        )

    # Back-side ground pour. Fill it in KiCad before ordering; the GND net is
    # already traced, so the board is connected either way.
    lines.append(
        f'  (zone (net 1) (net_name "GND") (layer "B.Cu") (uuid "{uid()}") (hatch edge 0.5)'
    )
    lines.append("    (connect_pads (clearance 0.3))")
    lines.append("    (min_thickness 0.25)")
    lines.append("    (fill yes (thermal_gap 0.3) (thermal_bridge_width 0.4))")
    lines.append("    (polygon (pts")
    inset = 0.4
    for x, y in (
        (inset, inset),
        (BOARD_W - inset, inset),
        (BOARD_W - inset, BOARD_H - inset),
        (inset, BOARD_H - inset),
    ):
        lines.append(f"      (xy {x:.3f} {y:.3f})")
    lines.append("    ))")
    lines.append("  )")
    lines.append(")")
    (ROOT / "ESPixelPOPs.kicad_pcb").write_text("\n".join(lines) + "\n")


def write_sch() -> None:
    """Schematic with the same nets as the rev D drawing."""
    L = []
    a = L.append
    a('(kicad_sch (version 20250114) (generator "eeschema") (generator_version "9.0")')
    a(f'  (uuid "{uid()}")')
    a('  (paper "A3")')
    a("  (title_block")
    a('    (title "ESPixel Pops")')
    a('    (date "2017-07-19")')
    a('    (rev "D")')
    a('    (comment 1 "Recreation of ESPixel Pops for 1 inch mounting. GPIO2 pixels. 5V jumper or 78L05.")')
    a("  )")
    a("  (lib_symbols")

    def pin(num, name, x, y, ang):
        return (
            f'(pin passive line (at {x:.2f} {y:.2f} {ang}) (length 2.54) '
            f'(name "{name}" (effects (font (size 1.27 1.27)))) '
            f'(number "{num}" (effects (font (size 1.27 1.27)))))'
        )

    def symbol(lib, ref, value, body_pins, w, h):
        unit = lib.split(":")[-1]
        a(f'(symbol "{lib}" (pin_names (offset 0.254)) (exclude_from_sim no) (in_bom yes) (on_board yes)')
        a(f'  (property "Reference" "{ref}" (at 0 {h + 2.54:.2f} 0) (effects (font (size 1.27 1.27))))')
        a(f'  (property "Value" "{value}" (at 0 {-2.54:.2f} 0) (effects (font (size 1.27 1.27))))')
        a(f'  (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))')
        a(f'  (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))')
        a(f'  (symbol "{unit}_1_1"')
        a(f"    (rectangle (start {-w / 2:.2f} {h / 2:.2f}) (end {w / 2:.2f} {-h / 2:.2f}) "
          f"(stroke (width 0.254) (type default)) (fill (type background)))")
        for p in body_pins:
            a("    " + p)
        a("  )")
        a("  (embedded_fonts no)")
        a(")")

    # Two-pin vertical parts: pin 1 on top.
    def twopin(lib, ref, value):
        symbol(lib, ref, value, [pin("1", "1", 0, 5.08, 270), pin("2", "2", 0, -5.08, 90)], 5.08, 7.62)

    twopin("ESPixelPOPs:R1", "R", "330")
    twopin("ESPixelPOPs:R2", "R", "330")
    twopin("ESPixelPOPs:C1", "C", "100n")
    symbol(
        "ESPixelPOPs:C2",
        "C",
        "220uF",
        [pin("1", "+", 0, 5.08, 270), pin("2", "-", 0, -5.08, 90)],
        5.08,
        7.62,
    )
    symbol(
        "ESPixelPOPs:D1",
        "D",
        "1N4148",
        [pin("A", "A", -5.08, 0, 0), pin("C", "K", 5.08, 0, 180)],
        7.62,
        5.08,
    )
    symbol(
        "ESPixelPOPs:Q1",
        "Q",
        "2N7000",
        [pin("2", "G", -7.62, 2.54, 0), pin("3", "D", 7.62, 2.54, 180), pin("1", "S", 0, -5.08, 90)],
        10.16,
        7.62,
    )
    symbol(
        "ESPixelPOPs:U1",
        "U",
        "LD1117V33",
        [pin("3", "IN", -7.62, 2.54, 0), pin("2", "OUT", 7.62, 2.54, 180), pin("1", "GND", 0, -5.08, 90)],
        12.7,
        7.62,
    )
    symbol(
        "ESPixelPOPs:IC1",
        "IC",
        "78L05",
        [pin("3", "VI", -7.62, 2.54, 0), pin("1", "VO", 7.62, 2.54, 180), pin("2", "GND", 0, -5.08, 90)],
        12.7,
        7.62,
    )
    symbol(
        "ESPixelPOPs:S1",
        "S",
        "SW_PUSH",
        [
            pin("1", "1", -5.08, 2.54, 0),
            pin("2", "2", 5.08, 2.54, 180),
            pin("4", "4", -5.08, -2.54, 0),
            pin("3", "3", 5.08, -2.54, 180),
        ],
        7.62,
        7.62,
    )
    # JP1 top to bottom: GND CTS VCC TXO RXI DTR, drawn with pin 6 at the top
    # so the sheet reads the same order as the silkscreen.
    jp_pins = []
    labels = [("6", "GND"), ("5", "CTS"), ("4", "VCC"), ("3", "TXO"), ("2", "RXI"), ("1", "DTR")]
    for i, (num, name) in enumerate(labels):
        jp_pins.append(pin(num, name, 7.62, 6.35 - i * 2.54, 180))
    symbol("ESPixelPOPs:JP1", "JP", "SERIAL", jp_pins, 10.16, 15.24)
    # U2 socket, left side TX/EN/RST/VCC, right side GND/IO2/IO0/RX.
    u2_pins = []
    left = [("1", "TX"), ("3", "EN"), ("5", "RST"), ("7", "VCC")]
    right = [("2", "GND"), ("4", "IO2"), ("6", "IO0"), ("8", "RX")]
    for i, (num, name) in enumerate(left):
        u2_pins.append(pin(num, name, -7.62, 3.81 - i * 2.54, 0))
    for i, (num, name) in enumerate(right):
        u2_pins.append(pin(num, name, 7.62, 3.81 - i * 2.54, 180))
    symbol("ESPixelPOPs:U2", "U", "ESP-01", u2_pins, 12.7, 10.16)
    j_pins = []
    for i, name in enumerate(["VIN", "GND", "GND", "DATA", "VIN"], start=1):
        j_pins.append(pin(str(i), name, -7.62, 5.08 - (i - 1) * 2.54, 0))
    symbol("ESPixelPOPs:J1", "J", "PIXEL_PWR", j_pins, 10.16, 12.7)
    a("  )")

    def place(lib, ref, value, footprint, x, y, pins):
        x, y = round(x, 2), round(y, 2)
        a(f'  (symbol (lib_id "{lib}") (at {x:.2f} {y:.2f} 0) (unit 1) (exclude_from_sim no) '
          f'(in_bom yes) (on_board yes) (dnp no) (uuid "{uid()}")')
        a(f'    (property "Reference" "{ref}" (at {x:.2f} {y + 8:.2f} 0) (effects (font (size 1.27 1.27))))')
        a(f'    (property "Value" "{value}" (at {x + 12:.2f} {y + 8:.2f} 0) (effects (font (size 1.27 1.27))))')
        a(f'    (property "Footprint" "{footprint}" (at {x:.2f} {y:.2f} 0) (effects (font (size 1.27 1.27)) (hide yes)))')
        for num in pins:
            a(f'    (pin "{num}" (uuid "{uid()}"))')
        a("  )")

    def lab(name, x, y, ang=0):
        a(f'  (label "{name}" (at {x:.2f} {y:.2f} {ang}) (effects (font (size 1.27 1.27))) (uuid "{uid()}"))')

    def wire(x1, y1, x2, y2):
        a(f'  (wire (pts (xy {x1:.2f} {y1:.2f}) (xy {x2:.2f} {y2:.2f})) '
          f'(stroke (width 0) (type default)) (uuid "{uid()}"))')

    def nc(x, y):
        a(f'  (no_connect (at {x:.2f} {y:.2f}) (uuid "{uid()}"))')

    def connect(sx, sy, px, py, name=None, length=5.08):
        """Stub a library pin. KiCad places these symbols with pin Y negated."""
        x = round(sx + px, 2)
        y = round(sy - py, 2)
        if name is None:
            nc(x, y)
            return
        if abs(px) > abs(py):
            dx = length if px > 0 else -length
            dy = 0.0
            ang = 0 if dx > 0 else 180
        else:
            dx = 0.0
            dy = -length if py > 0 else length
            ang = 90 if dy > 0 else 270
        wire(x, y, round(x + dx, 2), round(y + dy, 2))
        lab(name, round(x + dx, 2), round(y + dy, 2), ang)

    # Origins sit on the 1.27 mm connection grid. Same label connects the net.
    u1 = (59.69, 165.10)
    c1 = (35.56, 165.10)
    c2 = (90.17, 165.10)
    jp = (35.56, 119.38)
    u2 = (105.41, 119.38)
    d1 = (71.12, 95.25)
    r1 = (149.86, 144.78)
    q1 = (175.26, 129.54)
    r2 = (199.39, 144.78)
    ic = (229.87, 149.86)
    s1 = (149.86, 100.33)
    j1 = (265.43, 129.54)

    place("ESPixelPOPs:U1", "U1", "LD1117V33", "Package_TO_SOT_THT:TO-220-3_Vertical", *u1, ["1", "2", "3"])
    place("ESPixelPOPs:C1", "C1", "100n", "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P2.54mm", *c1, ["1", "2"])
    place("ESPixelPOPs:C2", "C2", "220uF", "Capacitor_THT:CP_Radial_D5.0mm_P2.54mm", *c2, ["1", "2"])
    connect(*u1, -7.62, 2.54, "VIN")    # pin 3 IN
    connect(*u1, 7.62, 2.54, "+3V3")    # pin 2 OUT
    connect(*u1, 0, -5.08, "GND")       # pin 1 GND
    connect(*c1, 0, 5.08, "VIN")
    connect(*c1, 0, -5.08, "GND")
    connect(*c2, 0, 5.08, "+3V3")       # pin 1 +
    connect(*c2, 0, -5.08, "GND")

    place("ESPixelPOPs:JP1", "JP1", "SERIAL", "Connector:PinHeader_1x06_P2.54mm_Vertical", *jp, ["1", "2", "3", "4", "5", "6"])
    place("ESPixelPOPs:U2", "U2", "ESP-01", "Connector:PinSocket_2x04_P2.54mm_Vertical", *u2, ["1", "2", "3", "4", "5", "6", "7", "8"])
    place("ESPixelPOPs:D1", "D1", "1N4148", "Diode_THT:D_DO-35_SOD27_P7.62mm_Vertical", *d1, ["A", "C"])
    # JP1 library order is GND, CTS, VCC, TXO, RXI, DTR from local +Y.
    jp_names = ["GND", None, "VIN", "PROG_TX", "ESP_TX", None]
    for i, name in enumerate(jp_names):
        connect(*jp, 7.62, 6.35 - i * 2.54, name)
    # U2 left TX, EN, RST, VCC. Right GND, IO2, IO0, RX.
    for i, name in enumerate(["ESP_TX", "+3V3", None, "+3V3"]):
        connect(*u2, -7.62, 3.81 - i * 2.54, name)
    for i, name in enumerate(["GND", "GPIO2", "GPIO0", "ESP_RX"]):
        connect(*u2, 7.62, 3.81 - i * 2.54, name)
    connect(*d1, -5.08, 0, "ESP_RX")   # anode
    connect(*d1, 5.08, 0, "PROG_TX")   # cathode

    place("ESPixelPOPs:R1", "R1", "330", "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm", *r1, ["1", "2"])
    place("ESPixelPOPs:Q1", "Q1", "2N7000", "Package_TO_SOT_THT:TO-92_Inline", *q1, ["1", "2", "3"])
    place("ESPixelPOPs:R2", "R2", "330", "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm", *r2, ["1", "2"])
    place("ESPixelPOPs:IC1", "IC1", "78L05", "Package_TO_SOT_THT:TO-92_Inline", *ic, ["1", "2", "3"])
    place("ESPixelPOPs:S1", "S1", "SW_PUSH", "Button_Switch_THT:SW_PUSH_6mm", *s1, ["1", "2", "3", "4"])
    place("ESPixelPOPs:J1", "J1", "TERM 3.81mm", "TerminalBlock:TerminalBlock_1x05_P3.81mm", *j1, ["1", "2", "3", "4", "5"])
    connect(*r1, 0, 5.08, "+3V3")
    connect(*r1, 0, -5.08, "GPIO2")
    connect(*q1, -7.62, 2.54, "+3V3")  # gate
    connect(*q1, 7.62, 2.54, "PIX")    # drain
    connect(*q1, 0, -5.08, "GPIO2")    # source
    connect(*r2, 0, 5.08, "V5")
    connect(*r2, 0, -5.08, "PIX")
    connect(*ic, -7.62, 2.54, "VIN")   # VI
    connect(*ic, 7.62, 2.54, "V5")     # VO
    connect(*ic, 0, -5.08, "GND")
    connect(*s1, -5.08, 2.54, "GPIO0")
    connect(*s1, 5.08, 2.54, "GPIO0")
    connect(*s1, -5.08, -2.54, "GND")
    connect(*s1, 5.08, -2.54, "GND")
    for i, name in enumerate(["VIN", "GND", "GND", "PIX", "VIN"]):
        connect(*j1, -7.62, 5.08 - i * 2.54, name)

    a('  (sheet_instances (path "/" (page "1")))')
    a("  (embedded_fonts no)")
    a(")")
    (ROOT / "ESPixelPOPs.kicad_sch").write_text("\n".join(L) + "\n")


def write_project() -> None:
    (ROOT / "ESPixelPOPs.kicad_pro").write_text(
        """{
  "board": {
    "design_settings": {
      "rules": {
        "min_clearance": 0.2,
        "min_copper_edge_clearance": 0.5,
        "min_hole_clearance": 0.25,
        "min_hole_to_hole": 0.25,
        "min_silk_clearance": 0.0,
        "min_text_height": 0.4,
        "min_text_thickness": 0.06,
        "min_track_width": 0.2,
        "min_via_annular_width": 0.15,
        "min_via_diameter": 0.8,
        "min_through_hole_diameter": 0.3,
        "solder_mask_to_copper_clearance": 0.05
      },
      "rule_severities": {
        "lib_footprint_issues": "ignore",
        "lib_footprint_mismatch": "ignore"
      }
    }
  },
  "boards": [],
  "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
  "meta": {"filename": "ESPixelPOPs.kicad_pro", "version": 1},
  "net_settings": {"classes": [{"name": "Default", "clearance": 0.2, "track_width": 0.25, "via_diameter": 0.8, "via_drill": 0.4}], "meta": {"version": 3}},
  "erc": {
    "rule_severities": {
      "footprint_link_issues": "ignore",
      "lib_symbol_issues": "ignore"
    }
  },
  "sheets": [["ESPixelPOPs.kicad_sch", ""]],
  "text_variables": {}
}
"""
    )
    (ROOT / "bom.csv").write_text(
        """Qty,Ref,Value,Package,Notes
1,U1,LD1117V33,TO-220,"3.3 V regulator. Tab is VOUT and faces the terminal. Square pad is pin 1 GND."
1,IC1,LM78L05,TO-92,"12 V pixels only. Flat faces R1/R2. Omit for 5 V pixels and jumper pads 1 and 3."
1,Q1,2N7000,TO-92,"Flat faces the terminal. Top pad source, bottom pad drain, middle pad gate."
1,D1,1N4148,DO-35,"Band (cathode) toward the serial header."
2,"R1,R2",330 ohm 1/4W,axial 7.6 to 10 mm,"R2 is the left resistor."
1,C1,0.1 uF,ceramic 2.54 mm,50 V disc or MLCC
1,C2,220 uF 16 V,radial 5 mm,"Form leads to 2.54 mm. Square pad is positive."
1,S1,6 mm tact,6x6 mm through-hole,Fits only one way
1,JP1,1x6 male header,2.54 mm,"GND CTS VCC RX TX DTR left to right. Connect adapter GND, TXD to RX, RXD to TX."
1,U2,2x4 female socket,2.54 mm,"ESP-01. Antenna hangs off the right edge."
1,J1,5-pos screw terminal,3.81 mm,"Wire entries face off the left edge. 1 VCC, 2 GND, 3 GND, 4 DATA, 5 VCC."
1,,ESP-01,module,"1 MB flash is enough for ESPixelStick 3.2. Not supported by v4."
2,,M3 mounting hole,3.2 mm,25 mm apart, diagonally
"""
    )


def write_readme() -> None:
    (ROOT / "README.md").write_text(
        """# ESPixel Pops

A one-output Wi-Fi pixel controller for an ESP-01 module. The circuit is the
Ukewarrior ESPixel Pops rev D schematic of 19 July 2017. The board is 1.80 by
1.00 inch, so the 1.00 inch side slides into 1 inch schedule-40 PVC.

Every part on the board is through-hole. Open `ESPixelPOPs.kicad_pcb` in KiCad
8 and run Edit, Fill All Zones before ordering. GND is already traced on the
back; the zone is the pour.

## How it matches the build guide

J1 is the 5-position 3.81 mm terminal, wire entries facing off the left edge.

| Pin | Silk | Connect |
|---|---|---|
| 1 | VCC | supply positive |
| 2 | GND | supply negative |
| 3 | GND | pixel ground |
| 4 | DATA | pixel data |
| 5 | VCC | pixel positive |

JP1 reads GND, CTS, VCC, RX, TX, DTR from left to right. For programming,
connect adapter ground to GND, adapter TXD to RX, and adapter RXD to TX. Leave
the other three pins open. VCC on this header is the pixel supply, not 3.3 V.
Power the board from J1. The adapter cannot run the ESP-01.

The ESP-01 plugs into U2 with the antenna hanging off the right edge. D1, the
1N4148, has its band toward the header. That diode is the serial level shifter,
so a 3.3 V or a 5 V adapter can program the module.

## 5 V pixels or 12 V pixels

U1 is an LD1117V33. Its metal tab is the 3.3 V output and faces the terminal.
Do not let the tab touch the terminal screws.

| Pixels | IC1 | Silk jumper |
|---|---|---|
| 5 V | leave it empty | solder a wire between pads 1 and 3 |
| 12 V | fit the 78L05, flat side toward R1 and R2 | no jumper |

Pad 1 is the square pad. On a 12 V build the 78L05 only feeds the pixel-data
pullup. The pixels themselves still get the full 12 V from J1 pin 5. A board
built one way does not drive the other kind of pixel.

Q1 is the 2N7000 data buffer. The flat faces the terminal. The top pad is the
source, the bottom pad is the drain, and the middle pin is the gate. GPIO2
drives the pixels. Hold S1 while powering the board to enter the serial bootloader.

## Firmware

ESPixelStick 3.2 is the last release that fits an ESP-01. Pixel output is
GPIO2. Later ESPixelStick releases need a module with 4 MB of flash.
"""
    )


def write_preview(parts, segments, silk_text, silk_lines) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return
    scale = 28
    pad = 20
    w = int(BOARD_W * scale) + pad * 2
    h = int(BOARD_H * scale) + pad * 2
    img = Image.new("RGB", (w, h), (30, 30, 30))
    dr = ImageDraw.Draw(img)

    def xy(x, y):
        return pad + x * scale, pad + y * scale

    x0, y0 = xy(0, 0)
    x1, y1 = xy(BOARD_W, BOARD_H)
    dr.rectangle([x0, y0, x1, y1], fill=(140, 28, 28))
    colors = {
        1: (210, 210, 210),
        2: (220, 40, 40),
        3: (240, 180, 40),
        4: (80, 180, 80),
        5: (80, 140, 255),
        6: (180, 80, 220),
        7: (255, 120, 40),
        8: (80, 220, 220),
        9: (220, 220, 80),
        10: (255, 160, 200),
    }
    # Back copper first, dimmed, then the front copper on top.
    for layer in (1, 0):
        for x1_, y1_, x2_, y2_, width, seg_layer, net in segments:
            if seg_layer != layer:
                continue
            color = colors.get(net, (255, 255, 255))
            if layer == 1:
                color = tuple(c // 3 for c in color)
            dr.line(
                [xy(x1_, y1_), xy(x2_, y2_)],
                fill=color,
                width=max(2, int(width * scale * 0.7)),
            )
    for part in parts:
        for p in part.pads:
            r = p.size / 2 * scale
            cx, cy = xy(p.x, p.y)
            dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=colors.get(p.net, (200, 200, 200)), outline=(230, 230, 230))
    for hx, hy, hd in HOLES:
        r = hd / 2 * scale
        cx, cy = xy(hx, hy)
        dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(30, 30, 30))
    for x1_, y1_, x2_, y2_ in silk_lines:
        dr.line([xy(x1_, y1_), xy(x2_, y2_)], fill=(245, 230, 170), width=2)
    font_path = "/System/Library/Fonts/Supplemental/Arial.ttf"
    for text, x, y, size, rot in silk_text:
        px = int(size * scale * 0.85)
        try:
            font = ImageFont.truetype(font_path, max(8, px))
        except OSError:
            font = ImageFont.load_default()
        cx, cy = xy(x, y)
        dr.text((cx, cy), text, fill=(255, 245, 200), font=font, anchor="mm")
    img.save(ROOT / "preview.png")


def main() -> None:
    parts = build_parts()
    check_clearance(parts)
    segments, vias = route(parts)
    verify(parts, segments, vias)
    write_pcb(parts, segments, vias)
    write_sch()
    write_project()
    write_readme()
    silk_text, silk_lines = build_silk(parts)
    write_preview(parts, segments, silk_text, silk_lines)
    print(f"wrote {ROOT}")


if __name__ == "__main__":
    main()
