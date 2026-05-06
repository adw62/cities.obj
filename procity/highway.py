"""Raised dual-carriageway highway splines: two elevated decks + support pillars."""

import math
import random
from typing import List, Tuple

import numpy as np

from .geometry import Mesh, box


def _sample_spline(
    control_pts: List[Tuple[float, float]], spacing: float
) -> List[Tuple[float, float]]:
    """Chord-length-parameterised cubic spline sampled at ~spacing metre intervals."""
    from scipy.interpolate import CubicSpline

    n = len(control_pts)
    xs = [p[0] for p in control_pts]
    zs = [p[1] for p in control_pts]

    t = [0.0]
    for i in range(1, n):
        t.append(t[-1] + math.hypot(xs[i] - xs[i - 1], zs[i] - zs[i - 1]))

    total = t[-1]
    if total < spacing:
        return control_pts

    cs_x = CubicSpline(t, xs)
    cs_z = CubicSpline(t, zs)
    n_pts = max(2, int(total / spacing) + 1)
    ts = np.linspace(0, total, n_pts)
    return list(zip(cs_x(ts).tolist(), cs_z(ts).tolist()))


def _tangent(polyline: List[Tuple[float, float]], i: int) -> Tuple[float, float]:
    n = len(polyline)
    if i == 0:
        dx, dz = polyline[1][0] - polyline[0][0], polyline[1][1] - polyline[0][1]
    elif i == n - 1:
        dx, dz = polyline[-1][0] - polyline[-2][0], polyline[-1][1] - polyline[-2][1]
    else:
        dx = polyline[i + 1][0] - polyline[i - 1][0]
        dz = polyline[i + 1][1] - polyline[i - 1][1]
    dist = math.hypot(dx, dz)
    return (dx / dist, dz / dist) if dist > 1e-9 else (1.0, 0.0)


def _offset_polyline(
    polyline: List[Tuple[float, float]], offset: float
) -> List[Tuple[float, float]]:
    """Shift each point laterally by *offset* (positive = left of travel direction)."""
    result = []
    for i, (x, z) in enumerate(polyline):
        tx, tz = _tangent(polyline, i)
        px, pz = -tz, tx  # left perpendicular
        result.append((x + px * offset, z + pz * offset))
    return result


def _deck_mesh(
    polyline: List[Tuple[float, float]],
    width: float,
    elevation: float,
    thickness: float,
) -> Mesh:
    """Watertight strip mesh for one elevated road deck, centred on the polyline."""
    n = len(polyline)
    hw = width / 2
    verts = []

    for i, (x, z) in enumerate(polyline):
        tx, tz = _tangent(polyline, i)
        px, pz = -tz, tx  # left perp

        verts += [
            [x - px * hw, elevation + thickness, z - pz * hw],  # 4i+0 top-left
            [x + px * hw, elevation + thickness, z + pz * hw],  # 4i+1 top-right
            [x - px * hw, elevation,             z - pz * hw],  # 4i+2 bot-left
            [x + px * hw, elevation,             z + pz * hw],  # 4i+3 bot-right
        ]

    faces = []
    for i in range(n - 1):
        a, b, c, d = i * 4, i * 4 + 1, i * 4 + 2, i * 4 + 3
        e, f, g, h = a + 4, b + 4, c + 4, d + 4
        faces += [
            [a, e, f], [a, f, b],   # top
            [c, d, h], [c, h, g],   # bottom
            [a, c, g], [a, g, e],   # left side
            [b, f, h], [b, h, d],   # right side
        ]

    # end caps
    faces += [[0, 1, 3], [0, 3, 2]]
    L = (n - 1) * 4
    faces += [[L, L + 2, L + 3], [L, L + 3, L + 1]]

    return Mesh(np.array(verts, dtype=float), np.array(faces, dtype=int))


def _pillar_mesh(x: float, z: float, elevation: float, size: float) -> Mesh:
    return box(size, elevation, size).transform(pos=(x, 0.0, z))


def generate_highway(cfg, rng: random.Random):
    """Generate one raised dual-carriageway highway.

    Returns ``(meshes, boulevard_entries)`` where *meshes* is a list of
    ``(name, mesh)`` pairs and *boulevard_entries* is a list of
    ``(x1,z1,x2,z2,poly,angle)`` tuples for building clearance.
    """
    from .layout import boulevard_polygon

    hw, hd = cfg.city_width / 2, cfg.city_depth / 2

    def _edge_pt(e):
        sx, sz = hw * 0.8, hd * 0.8
        if e == 0: return (-hw, rng.uniform(-sz, sz))
        if e == 1: return ( hw, rng.uniform(-sz, sz))
        if e == 2: return (rng.uniform(-sx, sx), -hd)
        return          (rng.uniform(-sx, sx),  hd)

    edge = rng.randint(0, 3)
    opp  = (edge + 2) % 4
    entry   = _edge_pt(edge)
    exit_pt = _edge_pt(opp)

    # Single gentle waypoint: near midpoint, offset perpendicular by ≤15% of city width
    mid_x = (entry[0] + exit_pt[0]) / 2
    mid_z = (entry[1] + exit_pt[1]) / 2
    dx, dz = exit_pt[0] - entry[0], exit_pt[1] - entry[1]
    length = math.hypot(dx, dz)
    if length > 1e-9:
        perp_x, perp_z = -dz / length, dx / length
    else:
        perp_x, perp_z = 1.0, 0.0
    nudge = rng.uniform(-cfg.city_width * 0.12, cfg.city_width * 0.12)
    waypoint = (mid_x + perp_x * nudge, mid_z + perp_z * nudge)

    ctrl = [entry, waypoint, exit_pt]

    fine_line   = _sample_spline(ctrl, spacing=3.0)
    coarse_line = _sample_spline(ctrl, spacing=12.0)

    cw     = cfg.highway_carriage_width
    median = cfg.highway_median_width
    offset = cw / 2 + median / 2   # lateral centre of each deck from spline
    elev   = cfg.highway_elevation
    thick  = cfg.highway_deck_thickness

    left_line  = _offset_polyline(fine_line,  +offset)
    right_line = _offset_polyline(fine_line,  -offset)

    left_deck  = _deck_mesh(left_line,  cw, elev, thick)
    right_deck = _deck_mesh(right_line, cw, elev, thick)

    # Pillars: one under each carriageway at regular intervals
    pillars = []
    acc, next_drop = 0.0, cfg.highway_pillar_spacing * 0.5
    prev = fine_line[0]
    for j, pt in enumerate(fine_line[1:], 1):
        seg = math.hypot(pt[0] - prev[0], pt[1] - prev[1])
        while acc + seg >= next_drop:
            t = (next_drop - acc) / seg
            cx = prev[0] + t * (pt[0] - prev[0])
            cz = prev[1] + t * (pt[1] - prev[1])
            # perpendicular at this point
            tx, tz = _tangent(fine_line, j)
            px, pz = -tz, tx
            for side in (+offset, -offset):
                pillars.append(_pillar_mesh(
                    cx + px * side, cz + pz * side,
                    elev, cfg.highway_pillar_size,
                ))
            next_drop += cfg.highway_pillar_spacing
        acc += seg
        prev = pt

    # Building-clearance boulevard entries spanning full dual-carriageway width
    clearance_width = 2 * cw + median
    blvd_entries = []
    for i in range(len(coarse_line) - 1):
        x1, z1 = coarse_line[i]
        x2, z2 = coarse_line[i + 1]
        poly  = boulevard_polygon(x1, z1, x2, z2, clearance_width)
        angle = math.atan2(z2 - z1, x2 - x1)
        blvd_entries.append((x1, z1, x2, z2, poly, angle))

    meshes = [("left_deck",  left_deck), ("right_deck", right_deck)]
    for pi, pm in enumerate(pillars):
        meshes.append((f"pillar_{pi:03d}", pm))

    return meshes, blvd_entries
