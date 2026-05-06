"""Procedural building generation.

Three styles generated via a simple hierarchical rule:
  Lot → mass(es) → roof

  simple       – single extruded box or prism, flat or pyramid roof
  stepped      – 2-4 diminishing tiers stacked vertically
  tower_podium – wide low podium + narrow tall tower
"""

import random
import math
from typing import List, Tuple

from .config import CityConfig
from .geometry import Mesh, box, prism, pyramid, cylinder, empty, poly_prism, windowed_box
from .layout import Lot
from .sampler import Sampler


# ── polygon geometry helpers ──────────────────────────────────────────────────

def _poly_area(verts):
    """Signed area via shoelace; positive means CCW."""
    n = len(verts)
    a = 0.0
    for i in range(n):
        x1, z1 = verts[i]
        x2, z2 = verts[(i + 1) % n]
        a += x1 * z2 - x2 * z1
    return abs(a) * 0.5


def _poly_centroid(verts):
    n = len(verts)
    return (sum(v[0] for v in verts) / n, sum(v[1] for v in verts) / n)


def _shrink_poly(verts, amount):
    """Move each vertex toward the centroid by `amount` units."""
    cx, cz = _poly_centroid(verts)
    result = []
    for x, z in verts:
        dx, dz = x - cx, z - cz
        dist = math.hypot(dx, dz)
        if dist <= amount:
            result.append((cx, cz))
        else:
            f = (dist - amount) / dist
            result.append((cx + dx * f, cz + dz * f))
    return result


def _clip_polygon(subject, clip_poly):
    """Sutherland-Hodgman clip of `subject` against a convex CCW `clip_poly`."""
    def _inside(p, a, b):
        return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= 0

    def _intersect(p1, p2, a, b):
        dx1, dz1 = p2[0] - p1[0], p2[1] - p1[1]
        dx2, dz2 = b[0] - a[0], b[1] - a[1]
        denom = dx1 * dz2 - dz1 * dx2
        if abs(denom) < 1e-10:
            return p1
        t = ((a[0] - p1[0]) * dz2 - (a[1] - p1[1]) * dx2) / denom
        return (p1[0] + t * dx1, p1[1] + t * dz1)

    output = list(subject)
    n = len(clip_poly)
    for i in range(n):
        if not output:
            break
        a, b = clip_poly[i], clip_poly[(i + 1) % n]
        inp = output
        output = []
        for j in range(len(inp)):
            curr, prev = inp[j], inp[j - 1]
            if _inside(curr, a, b):
                if not _inside(prev, a, b):
                    output.append(_intersect(prev, curr, a, b))
                output.append(curr)
            elif _inside(prev, a, b):
                output.append(_intersect(prev, curr, a, b))
    return output


def _containment_ratio(building_verts, block_verts):
    """Fraction of building footprint area that lies inside block_verts."""
    clipped = _clip_polygon(building_verts, block_verts)
    if not clipped:
        return 0.0
    return _poly_area(clipped) / max(_poly_area(building_verts), 1e-6)


def _rect_footprint(cx, cz, w, d):
    hw, hd = w / 2, d / 2
    return [(cx - hw, cz - hd), (cx + hw, cz - hd),
            (cx + hw, cz + hd), (cx - hw, cz + hd)]


# ── helpers ──────────────────────────────────────────────────────────────────

def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _stacked(parts: List[Mesh]) -> Mesh:
    """Merge a list of meshes into one."""
    result = empty()
    for m in parts:
        if len(m.vertices):
            result = result.merge(m)
    return result


def _place(mesh: Mesh, cx: float, y: float, cz: float) -> Mesh:
    """Translate so the mesh centre (X/Z) is at (cx, cz) and base is at y."""
    return mesh.transform(pos=(cx, y, cz))


# ── floor count helpers ───────────────────────────────────────────────────────

def _lot_dims(lot: Lot, cfg: CityConfig):
    """Building footprint (w, d) after setback and size_scale."""
    sb = cfg.lot_setback
    return (max(1.0, (lot.width  - 2 * sb) * cfg.size_scale),
            max(1.0, (lot.depth  - 2 * sb) * cfg.size_scale))


def _num_floors(lot: Lot, cfg: CityConfig, smp: Sampler) -> int:
    # Flat per-block cap assigned at layout time; fall back to config max
    ceiling = lot.height_cap if lot.height_cap > 0 else cfg.max_floors

    # Aspect ratio: still prevents needle buildings
    footprint = max(1.0, min(lot.width, lot.depth) * cfg.size_scale)
    ceiling = int(_clamp(ceiling, cfg.min_floors,
                         footprint * cfg.max_aspect_ratio / cfg.floor_height))

    # Exponential draw within the block's cap for within-block variety
    exp_mult = -math.log(max(1e-9, smp.random()))
    floors = int(_clamp(exp_mult * ceiling * 0.7, cfg.min_floors, ceiling))
    return max(cfg.min_floors, floors)


# ── roof ─────────────────────────────────────────────────────────────────────

def _rooftop_clutter(w: float, d: float, cx: float, y: float, cz: float,
                     smp: Sampler) -> Mesh:
    """Random mechanical objects on a flat roof: AC units, ducts, tanks, masts."""
    parts = []
    n = min(10, smp.randint(2, max(3, int(w * d / 25))))
    margin = 0.5

    for _ in range(n):
        r = smp.random()
        if r < 0.45 or (r < 0.68 and y <= 15):
            # Flat box: AC unit, duct, equipment housing
            ow = smp.uniform(0.5, min(3.5, w * 0.28))
            oh = smp.uniform(0.4, min(2.0, ow * 1.2))
            od = smp.uniform(0.5, min(3.5, d * 0.28))
        elif r < 0.68:
            # Tall narrow: antenna mast, vent pipe (tall buildings only)
            ow = smp.uniform(0.15, 0.45)
            oh = smp.uniform(2.0, min(6.0, w * 0.4))
            od = ow
        elif r < 0.83:
            # Cylinder: water tank, cooling tower
            rad = smp.uniform(0.3, min(1.5, min(w, d) * 0.12))
            oh  = smp.uniform(1.0, 3.0)
            hpw = w / 2 - margin - rad
            hpd = d / 2 - margin - rad
            if hpw > 0 and hpd > 0:
                parts.append(_place(cylinder(rad, oh, segs=8),
                                    cx + smp.uniform(-hpw, hpw),
                                    y,
                                    cz + smp.uniform(-hpd, hpd)))
            continue
        else:
            # Stairwell exit / lift overrun
            ow = smp.uniform(1.5, min(4.0, w * 0.35))
            oh = smp.uniform(2.5, 4.5)
            od = smp.uniform(1.5, min(4.0, d * 0.35))

        hpw = max(0.0, w / 2 - margin - ow / 2)
        hpd = max(0.0, d / 2 - margin - od / 2)
        parts.append(_place(box(ow, oh, od),
                            cx + smp.uniform(-hpw, hpw),
                            y,
                            cz + smp.uniform(-hpd, hpd)))
    return _stacked(parts)


def _roof(w: float, d: float, cx: float, y: float, cz: float,
          cfg: CityConfig, smp: Sampler, allow_pyramid: bool = True) -> Mesh:
    parts = []
    r = smp.random()
    flat = True
    if allow_pyramid and r < cfg.roof_pyramid_chance and w > 4 and d > 4:
        h = cfg.roof_pyramid_height * smp.uniform(0.6, 1.4)
        parts.append(_place(pyramid(w, h, d), cx, y, cz))
        flat = False
    elif allow_pyramid and r < cfg.roof_pyramid_chance + 0.15 and w > 6 and d > 6:
        t = smp.uniform(0.5, 1.2)
        border = max(1.0, min(w, d) * 0.12)
        parts += [
            _place(box(w, t, border), cx, y, cz - d / 2 + border / 2),
            _place(box(w, t, border), cx, y, cz + d / 2 - border / 2),
            _place(box(border, t, d - 2 * border), cx - w / 2 + border / 2, y, cz),
            _place(box(border, t, d - 2 * border), cx + w / 2 - border / 2, y, cz),
        ]

    # Rooftop clutter on flat / parapet roofs
    if flat and w > 5 and d > 5 and smp.random() < 0.72:
        parts.append(_rooftop_clutter(w, d, cx, y, cz, smp))

    # Spire: reduced probability, only on tall buildings
    if y > 30 and smp.random() < 0.15:
        sp_h = y * smp.uniform(0.10, 0.20)
        sp_r = smp.uniform(0.25, 0.55)
        parts.append(_place(prism(4, sp_r, sp_h), cx, y, cz))
    return _stacked(parts)


# ── shape chooser ─────────────────────────────────────────────────────────────

def _base_shape(w: float, h: float, d: float, smp: Sampler) -> Mesh:
    """Choose between a box and a prism based on lot shape and chance."""
    aspect = max(w, d) / max(min(w, d), 0.1)
    if aspect < 1.4 and smp.random() < 0.20:
        sides = smp.choice([6, 8])
        r = min(w, d) / 2
        return prism(sides, r, h)
    return box(w, h, d)


def _body(w: float, h: float, d: float, floors: int,
          cfg: CityConfig, smp: Sampler) -> tuple:
    """Return (Mesh, is_prism).  Callers use is_prism to skip rectangular roofs."""
    aspect = max(w, d) / max(min(w, d), 0.1)
    if aspect < 1.4 and floors >= 5 and smp.random() < 0.20:
        return prism(smp.choice([6, 8]), min(w, d) / 2, h), True
    if floors >= cfg.window_min_floors:
        return windowed_box(w, h, d, floors, cfg.window_depth), False
    return box(w, h, d), False


# ── building styles ──────────────────────────────────────────────────────────

def _simple(lot: Lot, cfg: CityConfig, smp: Sampler) -> Mesh:
    w, d = _lot_dims(lot, cfg)
    floors = _num_floors(lot, cfg, smp)
    h = floors * cfg.floor_height

    # Setback: tall buildings randomly get a stepped-back upper tier
    if floors >= cfg.setback_min_floors and smp.random() < 0.35:
        low_f  = int(floors * smp.uniform(0.55, 0.72))
        hi_f   = max(1, floors - low_f)
        low_h  = low_f * cfg.floor_height
        hi_h   = hi_f  * cfg.floor_height
        sb     = smp.uniform(2.0, 4.5)
        hw2    = max(3.0, w - 2 * sb)
        hd2    = max(3.0, d - 2 * sb)
        lo_mesh, _      = _body(w,   low_h, d,   low_f, cfg, smp)
        hi_mesh, hi_prism = _body(hw2, hi_h,  hd2, hi_f,  cfg, smp)
        parts  = [_place(lo_mesh, lot.cx, 0, lot.cz),
                  _place(hi_mesh, lot.cx, low_h, lot.cz)]
        parts.append(_roof(hw2, hd2, lot.cx, low_h + hi_h, lot.cz, cfg, smp,
                           allow_pyramid=not hi_prism))
        return _stacked(parts)

    body, is_prism = _body(w, h, d, floors, cfg, smp)
    parts = [_place(body, lot.cx, 0, lot.cz)]
    parts.append(_roof(w, d, lot.cx, h, lot.cz, cfg, smp, allow_pyramid=not is_prism))
    return _stacked(parts)


def _stepped(lot: Lot, cfg: CityConfig, smp: Sampler) -> Mesh:
    w0, d0 = _lot_dims(lot, cfg)
    total_floors = _num_floors(lot, cfg, smp)
    n_steps = smp.randint(2, min(4, max(2, total_floors // 3)))

    parts = []
    y = 0.0
    w, d = w0, d0
    is_prism = False

    for step in range(n_steps):
        floors_here = max(1, total_floors // n_steps + (1 if step == 0 else 0))
        h = floors_here * cfg.floor_height
        body_mesh, is_prism = _body(w, h, d, floors_here, cfg, smp)
        parts.append(_place(body_mesh, lot.cx, y, lot.cz))
        y += h
        shrink = smp.uniform(1.5, 3.5)
        w = max(2.0, w - 2 * shrink)
        d = max(2.0, d - 2 * shrink)

    parts.append(_roof(w, d, lot.cx, y, lot.cz, cfg, smp, allow_pyramid=not is_prism))
    return _stacked(parts)


def _tower_podium(lot: Lot, cfg: CityConfig, smp: Sampler) -> Mesh:
    w0, d0 = _lot_dims(lot, cfg)
    total_floors = max(4, _num_floors(lot, cfg, smp))

    podium_floors = smp.randint(1, max(1, total_floors // 4))
    tower_floors = total_floors - podium_floors

    ph = podium_floors * cfg.floor_height
    th = tower_floors * cfg.floor_height

    tw = max(2.0, w0 * smp.uniform(0.3, 0.6))
    td = max(2.0, d0 * smp.uniform(0.3, 0.6))

    max_dx = (w0 - tw) / 2 * 0.6
    max_dz = (d0 - td) / 2 * 0.6
    dx = smp.uniform(-max_dx, max_dx)
    dz = smp.uniform(-max_dz, max_dz)

    pod_mesh, _          = _body(w0, ph, d0, podium_floors, cfg, smp)
    twr_mesh, twr_prism  = _body(tw, th, td, tower_floors,  cfg, smp)
    parts = [
        _place(pod_mesh, lot.cx,      0,  lot.cz),
        _place(twr_mesh, lot.cx + dx, ph, lot.cz + dz),
    ]
    parts.append(_roof(tw, td, lot.cx + dx, ph + th, lot.cz + dz, cfg, smp,
                       allow_pyramid=not twr_prism))
    return _stacked(parts)


# ── new mass styles ──────────────────────────────────────────────────────────

def _l_shaped(lot: Lot, cfg: CityConfig, smp: Sampler) -> Mesh:
    """Two rectangular wings forming an L plan."""
    w, d = _lot_dims(lot, cfg)
    if min(w, d) < 8.0:
        return _simple(lot, cfg, smp)

    floors = _num_floors(lot, cfg, smp)
    h = floors * cfg.floor_height
    sx = smp.uniform(0.45, 0.65)   # fraction of width for upper arm
    sz = smp.uniform(0.45, 0.65)   # fraction of depth for lower arm

    x0, z0 = lot.cx - w / 2, lot.cz - d / 2

    a1_d = d * sz
    a2_w, a2_d = w * sx, d * (1 - sz)
    a2_h = h * smp.uniform(0.65, 1.0)

    parts = [
        _place(box(w, h, a1_d), lot.cx, 0, z0 + a1_d / 2),
        _place(box(a2_w, a2_h, a2_d), x0 + a2_w / 2, 0, z0 + a1_d + a2_d / 2),
    ]
    parts.append(_roof(w, a1_d, lot.cx, h, z0 + a1_d / 2, cfg, smp, allow_pyramid=False))
    return _stacked(parts)


def _courtyard(lot: Lot, cfg: CityConfig, smp: Sampler) -> Mesh:
    """U-shaped courtyard building: two side wings + back bar."""
    w, d = _lot_dims(lot, cfg)
    if min(w, d) < 12.0:
        return _l_shaped(lot, cfg, smp)

    floors = _num_floors(lot, cfg, smp)
    h = floors * cfg.floor_height
    wing_w = w * smp.uniform(0.18, 0.30)
    back_d = d * smp.uniform(0.22, 0.38)
    back_h = h * smp.uniform(0.65, 1.0)

    x0, z0 = lot.cx - w / 2, lot.cz - d / 2
    x1, z1 = lot.cx + w / 2, lot.cz + d / 2

    parts = [
        _place(box(wing_w, h, d), x0 + wing_w / 2, 0, lot.cz),
        _place(box(wing_w, h, d), x1 - wing_w / 2, 0, lot.cz),
        _place(box(w - 2 * wing_w, back_h, back_d), lot.cx, 0, z1 - back_d / 2),
    ]
    return _stacked(parts)


def _chamfered(lot: Lot, cfg: CityConfig, smp: Sampler) -> Mesh:
    """Faceted modern tower: polygonal prism base with optional slimmer crown."""
    w, d = _lot_dims(lot, cfg)
    floors = _num_floors(lot, cfg, smp)
    if floors < 5:
        return _simple(lot, cfg, smp)
    h = floors * cfg.floor_height

    sides = smp.choice([6, 8, 12])
    r = min(w, d) / 2
    parts = [_place(prism(sides, r, h), lot.cx, 0, lot.cz)]

    if h > 12 and smp.random() < 0.55:
        crown_h = h * smp.uniform(0.18, 0.35)
        crown_r = r * smp.uniform(0.35, 0.65)
        parts.append(_place(prism(sides, crown_r, crown_h), lot.cx, h, lot.cz))

    return _stacked(parts)


# ── polygon lot building styles ───────────────────────────────────────────────

def _poly_simple(lot: Lot, cfg: CityConfig, smp: Sampler) -> Mesh:
    shrunk = _shrink_poly(lot.verts, cfg.lot_setback)
    if _poly_area(shrunk) < 4.0:
        return empty()
    h = _num_floors(lot, cfg, smp) * cfg.floor_height
    return poly_prism(shrunk, h)


def _poly_stepped(lot: Lot, cfg: CityConfig, smp: Sampler) -> Mesh:
    shrunk = _shrink_poly(lot.verts, cfg.lot_setback)
    if _poly_area(shrunk) < 4.0:
        return empty()
    total_floors = _num_floors(lot, cfg, smp)
    n_steps = smp.randint(2, min(4, max(2, total_floors // 3)))

    parts = []
    y = 0.0
    current = shrunk
    floors_left = total_floors

    for step in range(n_steps):
        if _poly_area(current) < 2.0:
            break
        floors_here = max(1, floors_left // (n_steps - step))
        h = floors_here * cfg.floor_height
        parts.append(poly_prism(current, h).transform(pos=(0, y, 0)))
        y += h
        floors_left -= floors_here
        current = _shrink_poly(current, smp.uniform(1.5, 3.5))

    return _stacked(parts)


def _poly_building(lot: Lot, cfg: CityConfig, smp: Sampler) -> Mesh:
    if _poly_area(lot.verts) < cfg.min_lot_size ** 2 * 0.4:
        return empty()
    weights = [0.4, 0.6] if lot.centrality > 0.6 else [0.6, 0.4]
    style = smp.choices([_poly_simple, _poly_stepped], weights=weights, k=1)[0]
    return style(lot, cfg, smp)


def lot_boulevard_overlap(lot: Lot, cfg: CityConfig, blvd_poly: list,
                          angle: float = 0.0) -> float:
    """Fraction of building footprint that overlaps with a boulevard polygon.

    angle: optional Y-rotation applied to the footprint (for rotated buildings).
    """
    sb = cfg.lot_setback
    w = max(1.0, lot.width - 2 * sb)
    d = max(1.0, lot.depth - 2 * sb)
    if angle:
        hw, hd = w / 2, d / 2
        c, s = math.cos(angle), math.sin(angle)
        fp = [(lot.cx + x * c - z * s, lot.cz + x * s + z * c)
              for x, z in ((-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd))]
    else:
        fp = _rect_footprint(lot.cx, lot.cz, w, d)
    clipped = _clip_polygon(fp, blvd_poly)
    if not clipped:
        return 0.0
    return _poly_area(clipped) / max(_poly_area(fp), 1e-6)


# ── public API ────────────────────────────────────────────────────────────────

# weights: simple, stepped, tower_podium, l_shaped, courtyard, chamfered
_STYLES  = [_simple, _stepped, _tower_podium, _l_shaped, _courtyard, _chamfered]
_WEIGHTS = [0.20,    0.18,     0.14,          0.24,      0.12,       0.12]


def generate_building(lot: Lot, cfg: CityConfig, smp: Sampler) -> Mesh:
    """Return a Mesh for a single building placed on the given lot."""
    if lot.verts is not None:
        return _poly_building(lot, cfg, smp)

    if lot.width < cfg.min_lot_size * 0.4 or lot.depth < cfg.min_lot_size * 0.4:
        return empty()

    weights = list(_WEIGHTS)
    if lot.centrality > 0.6:
        # Downtown: more towers and chamfered, fewer L-shapes
        weights[2] += 0.10   # tower_podium
        weights[5] += 0.10   # chamfered
        weights[1] += 0.05   # stepped
        weights[3] -= 0.15   # l_shaped
        weights[4] -= 0.10   # courtyard
    elif lot.centrality < 0.3:
        # Suburbs: more L-shaped and courtyard, fewer towers
        weights[3] += 0.10   # l_shaped
        weights[4] += 0.08   # courtyard
        weights[0] += 0.07   # simple
        weights[2] -= 0.15   # tower_podium
        weights[5] -= 0.10   # chamfered

    style = smp.choices(_STYLES, weights=weights, k=1)[0]
    mesh = style(lot, cfg, smp)

    if lot.block_verts and len(mesh.vertices):
        sb = cfg.lot_setback
        fp = _rect_footprint(lot.cx, lot.cz,
                             max(1.0, lot.width - 2 * sb),
                             max(1.0, lot.depth - 2 * sb))
        if _containment_ratio(fp, lot.block_verts) < 0.80:
            return empty()

    return mesh
