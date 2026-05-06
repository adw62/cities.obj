"""City-level grid layout: generates a list of building lots."""

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple
import random

from .config import CityConfig
from .sampler import Sampler


@dataclass
class Lot:
    cx: float       # lot centre X
    cz: float       # lot centre Z
    width: float    # X extent
    depth: float    # Z extent
    # normalised distance from city centre [0..1] – drives style selection only
    centrality: float = 0.0
    # flat per-block floor cap assigned at layout time (0 = use config default)
    height_cap: int = 0
    # polygon footprint (x, z) tuples, CCW – set for non-rectangular lots
    verts: Optional[List[Tuple[float, float]]] = None
    # parent block boundary – used for 80 % containment check
    block_verts: Optional[List[Tuple[float, float]]] = None


def generate_voronoi_boulevards(cfg: "CityConfig", rng: random.Random):
    """Return list of (x1, z1, x2, z2) segments — one per Voronoi cell edge."""
    from scipy.spatial import Voronoi as _Voronoi
    import numpy as _np

    w, d = cfg.city_width, cfg.city_depth
    x0, z0, x1, z1 = -w / 2, -d / 2, w / 2, d / 2
    n = cfg.voronoi_sites

    # Jittered grid seeds for a natural but even distribution
    cols = max(1, round(n ** 0.5))
    rows = max(1, math.ceil(n / cols))
    seeds = []
    for r in range(rows):
        for c in range(cols):
            if len(seeds) >= n:
                break
            cx = x0 + (c + 0.5) * w / cols + rng.uniform(-w / cols * 0.35, w / cols * 0.35)
            cz = z0 + (r + 0.5) * d / rows + rng.uniform(-d / rows * 0.35, d / rows * 0.35)
            seeds.append([max(x0, min(x1, cx)), max(z0, min(z1, cz))])
    seeds = _np.array(seeds[:n])

    # Mirror points across each bbox edge so all cells are bounded
    mirrors = _np.vstack([
        _np.column_stack([2 * x0 - seeds[:, 0], seeds[:, 1]]),
        _np.column_stack([2 * x1 - seeds[:, 0], seeds[:, 1]]),
        _np.column_stack([seeds[:, 0], 2 * z0 - seeds[:, 1]]),
        _np.column_stack([seeds[:, 0], 2 * z1 - seeds[:, 1]]),
    ])
    vor = _Voronoi(_np.vstack([seeds, mirrors]))

    segments = []
    for ridge_verts, ridge_pts in zip(vor.ridge_vertices, vor.ridge_points):
        if ridge_pts[0] >= n or ridge_pts[1] >= n:
            continue  # skip ridges involving mirror seeds
        if -1 in ridge_verts:
            continue  # shouldn't happen with mirrors
        ax, az = vor.vertices[ridge_verts[0]]
        bx, bz = vor.vertices[ridge_verts[1]]
        clipped = _clip_segment_to_bbox(ax, az, bx, bz, x0, z0, x1, z1)
        if clipped:
            segments.append(clipped)

    # Pick the seed closest to the geometric city centre as the Voronoi downtown
    center_idx = int(_np.argmin(_np.hypot(seeds[:, 0], seeds[:, 1])))
    voronoi_center = (float(seeds[center_idx, 0]), float(seeds[center_idx, 1]))

    return segments, voronoi_center


def _clip_segment_to_bbox(ax, az, bx, bz, x0, z0, x1, z1):
    """Liang-Barsky clip of segment A→B to bbox. Returns (ax,az,bx,bz) or None."""
    dx, dz = bx - ax, bz - az
    tmin, tmax = 0.0, 1.0
    for p, q in [(-dx, ax - x0), (dx, x1 - ax), (-dz, az - z0), (dz, z1 - az)]:
        if abs(p) < 1e-10:
            if q < 0:
                return None
        else:
            r = q / p
            if p < 0:
                tmin = max(tmin, r)
            else:
                tmax = min(tmax, r)
    if tmin >= tmax:
        return None
    return (ax + tmin * dx, az + tmin * dz, ax + tmax * dx, az + tmax * dz)


def boulevard_polygon(x1: float, z1: float, x2: float, z2: float, width: float):
    """Return 4 CCW vertices of a road strip from (x1,z1) to (x2,z2)."""
    dx, dz = x2 - x1, z2 - z1
    dist = math.hypot(dx, dz)
    px, pz = -dz / dist, dx / dist   # unit perpendicular (CCW)
    hw = width / 2
    return [
        (x1 - px * hw, z1 - pz * hw),
        (x2 - px * hw, z2 - pz * hw),
        (x2 + px * hw, z2 + pz * hw),
        (x1 + px * hw, z1 + pz * hw),
    ]


def _line_crosses_aabb(ax, az, bx, bz, x0, x1, z0, z1) -> bool:
    """True if segment A→B intersects the axis-aligned rectangle [x0,x1]×[z0,z1]."""
    def _inside(px, pz):
        return x0 <= px <= x1 and z0 <= pz <= z1

    if _inside(ax, az) or _inside(bx, bz):
        return True

    def _seg_cross(p1x, p1z, p2x, p2z, q1x, q1z, q2x, q2z):
        dx, dz = p2x - p1x, p2z - p1z
        ex, ez = q2x - q1x, q2z - q1z
        denom = dx * ez - dz * ex
        if abs(denom) < 1e-10:
            return False
        fx, fz = q1x - p1x, q1z - p1z
        t = (fx * ez - fz * ex) / denom
        u = (fx * dz - fz * dx) / denom
        return 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0

    edges = [(x0, z0, x1, z0), (x1, z0, x1, z1),
             (x1, z1, x0, z1), (x0, z1, x0, z0)]
    return any(_seg_cross(ax, az, bx, bz, ex, ez, fx, fz)
               for ex, ez, fx, fz in edges)


def generate_lots(cfg: CityConfig, rng: random.Random, sampler: Sampler = None,
                  downtown_centers: Optional[List[Tuple[float, float]]] = None) -> List[Lot]:
    lots: List[Lot] = []

    pitch_x = cfg.block_width + cfg.street_width
    pitch_z = cfg.block_depth + cfg.street_width

    n_blocks_x = max(1, int(cfg.city_width / pitch_x))
    n_blocks_z = max(1, int(cfg.city_depth / pitch_z))

    # Actual occupied footprint, centred on origin
    total_w = n_blocks_x * pitch_x - cfg.street_width
    total_d = n_blocks_z * pitch_z - cfg.street_width
    origin_x = -total_w / 2
    origin_z = -total_d / 2

    city_half_diag = math.hypot(total_w, total_d) / 2
    smp = sampler or Sampler(rng, "uniform")

    centers = downtown_centers or []
    city_radius = math.hypot(total_w, total_d) * 0.4
    max_cap = int(cfg.max_floors * cfg.downtown_boost * 0.7)

    for bx in range(n_blocks_x):
        for bz in range(n_blocks_z):
            block_cx = origin_x + bx * pitch_x + cfg.block_width / 2
            block_cz = origin_z + bz * pitch_z + cfg.block_depth / 2

            centrality = 1.0 - min(
                1.0, math.hypot(block_cx, block_cz) / (city_half_diag * 0.6)
            )

            # Height cap: power-law random, exponent shrinks near any downtown center.
            if centers:
                dist = min(math.hypot(block_cx - cx, block_cz - cz) for cx, cz in centers)
            else:
                dist = city_radius  # no centers → treat everything as edge
            proximity = max(0.0, 1.0 - dist / city_radius)
            exponent = 0.5 + 3.5 * (1.0 - proximity)  # 0.5 near center → 4.0 at edge
            block_cap = max(cfg.min_floors, int(max_cap * smp.random() ** exponent))

            if cfg.use_triangle_blocks:
                block_lots = _triangulate_block(
                    block_cx, block_cz,
                    cfg.block_width, cfg.block_depth,
                    cfg, smp, centrality, block_cap,
                )
            else:
                block_lots = _subdivide_block(
                    block_cx, block_cz,
                    cfg.block_width, cfg.block_depth,
                    cfg, smp, centrality, block_cap,
                )
            lots.extend(block_lots)

    return lots


def _triangulate_block(
    cx: float, cz: float,
    bw: float, bd: float,
    cfg: "CityConfig",
    smp: "Sampler",
    centrality: float,
    height_cap: int = 0,
) -> List[Lot]:
    """Split a rectangular block into 2 triangular zones along the main diagonal.

    Lots are still rectangular (normal buildings), but each lot's block_verts is
    set to the triangle it falls in so the 80 % containment filter can cull
    buildings that straddle the diagonal boundary.
    """
    x0, x1 = cx - bw / 2, cx + bw / 2
    z0, z1 = cz - bd / 2, cz + bd / 2

    tri_lower = [(x0, z0), (x1, z0), (x1, z1)]   # below diagonal
    tri_upper = [(x0, z0), (x1, z1), (x0, z1)]   # above diagonal

    sub_lots = _subdivide_block(cx, cz, bw, bd, cfg, smp, centrality, height_cap)

    for lot in sub_lots:
        # Assign each lot to whichever triangle its centre falls in.
        # Diagonal runs (x0,z0)→(x1,z1); lower side: bd*(lx-x0) - bw*(lz-z0) >= 0
        if bd * (lot.cx - x0) - bw * (lot.cz - z0) >= 0:
            lot.block_verts = tri_lower
        else:
            lot.block_verts = tri_upper

    return sub_lots


def _subdivide_block(
    cx: float, cz: float,
    bw: float, bd: float,
    cfg: CityConfig,
    smp: Sampler,
    centrality: float,
    height_cap: int = 0,
) -> List[Lot]:
    """Subdivide a block into lots by slicing along one or both axes."""
    lots: List[Lot] = []

    if bw >= bd:
        cols = _slice(bw, cfg.min_lot_size, cfg.max_lot_size, smp)
        rows = _slice(bd, cfg.min_lot_size, cfg.max_lot_size, smp)
    else:
        rows = _slice(bd, cfg.min_lot_size, cfg.max_lot_size, smp)
        cols = _slice(bw, cfg.min_lot_size, cfg.max_lot_size, smp)

    x0 = cx - bw / 2
    z0 = cz - bd / 2

    for col_w, col_x in _offsets(cols, x0):
        for row_d, row_z in _offsets(rows, z0):
            lots.append(
                Lot(
                    cx=col_x + col_w / 2,
                    cz=row_z + row_d / 2,
                    width=col_w,
                    depth=row_d,
                    centrality=centrality,
                    height_cap=height_cap,
                )
            )
    return lots


def _slice(total: float, lo: float, hi: float, smp: Sampler) -> List[float]:
    """Divide 'total' into segments sized between lo and hi."""
    sizes: List[float] = []
    remaining = total
    while remaining > lo:
        seg = min(remaining, smp.uniform(lo, hi))
        sizes.append(seg)
        remaining -= seg
    if not sizes:
        sizes = [total]
    # Normalise so they sum to exactly total
    factor = total / sum(sizes)
    return [s * factor for s in sizes]


def _offsets(sizes: List[float], start: float):
    """Yield (size, start_coord) for each segment."""
    pos = start
    for s in sizes:
        yield s, pos
        pos += s
