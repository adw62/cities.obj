"""Procedural city generator → .obj files for 3D printing.

Usage:
    python main.py
    python main.py --seed 7 --output my_city.obj
    python main.py --dist gumbel --output city_gumbel.obj
    python main.py --scale 0.0005 --city-size 300
    python main.py --no-base --max-floors 30
"""

import argparse
import math
import random

from procity.config import CityConfig
from procity.layout import generate_lots, boulevard_polygon, generate_voronoi_boulevards
from procity.buildings import generate_building, lot_boulevard_overlap
from procity.geometry import base_plate, empty, road_strip
from procity.export import write_obj, write_traffic_json
from procity.sampler import Sampler
from procity.highway import generate_highway


def parse_args():
    p = argparse.ArgumentParser(description="Procedural 3D city → OBJ")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--output", type=str, default="output/city.obj")
    p.add_argument("--scale", type=float, default=0.001,
                   help="Multiply all metres by this (default 0.001 = 1:1000, "
                        "200m city → 200mm print)")
    p.add_argument("--city-size", type=float, default=400.0,
                   help="City width and depth in metres (square shorthand)")
    p.add_argument("--city-width", type=float, default=None,
                   help="City width (X) in metres; overrides --city-size")
    p.add_argument("--city-depth", type=float, default=None,
                   help="City depth (Z) in metres; overrides --city-size")
    p.add_argument("--max-floors", type=int, default=18)
    p.add_argument("--no-base", action="store_true",
                   help="Omit the ground base plate")
    p.add_argument("--dist", choices=["uniform", "gumbel", "normal"],
                   default="uniform",
                   help="Sampling distribution for heights/lot sizes. "
                        "gumbel = right-skewed (mostly short buildings, rare tall ones). "
                        "normal = bell curve centred in the range. "
                        "uniform = equal probability (default).")
    p.add_argument("--triangle-blocks", action="store_true",
                   help="Split each city block into 2 triangular lots.")
    p.add_argument("--diagonal-road", action="store_true",
                   help="Add a SW→NE diagonal boulevard.")
    p.add_argument("--voronoi", action="store_true",
                   help="Use Voronoi cell edges as boulevards.")
    p.add_argument("--voronoi-sites", type=int, default=None,
                   help="Number of Voronoi cells (default: 8).")
    p.add_argument("--highways", type=int, default=1, metavar="N",
                   help="Number of raised highway splines (default 1, 0 to disable).")
    p.add_argument("--no-windows", action="store_true",
                   help="Omit window indentations (faster, smaller file).")
    p.add_argument("--surface", choices=["flat", "sphere", "hemisphere", "torus"], default="flat",
                   help="Project city onto a curved surface (default: flat).")
    p.add_argument("--sphere-radius", type=float, default=None,
                   help="Sphere radius in metres (default: city_size/2).")
    p.add_argument("--pole-offset", type=float, default=None,
                   help="Hemisphere only: degrees from pole to the city centre "
                        "(default: auto, keeps pole clear of buildings).")
    p.add_argument("--torus-major", type=float, default=None,
                   help="Torus major radius in metres (default: city_size*1.5).")
    p.add_argument("--torus-minor", type=float, default=None,
                   help="Torus minor radius in metres (default: city_size*0.3).")
    return p.parse_args()


def main():
    args = parse_args()

    _dist_size_scales = {"uniform": 1.0, "gumbel": 1.2, "normal": 1.0}

    city_width = args.city_width or args.city_size
    city_depth = args.city_depth or args.city_size

    cfg = CityConfig(
        seed=args.seed,
        city_width=city_width,
        city_depth=city_depth,
        scale=args.scale,
        max_floors=args.max_floors,
        add_base=not args.no_base,
        output=args.output,
        use_triangle_blocks=args.triangle_blocks,
        diagonal_road=args.diagonal_road,
        voronoi_boulevards=args.voronoi,
        voronoi_sites=args.voronoi_sites or 8,
        size_scale=_dist_size_scales.get(args.dist, 1.0),
        num_highways=args.highways,
        window_min_floors=999 if args.no_windows else 4,
    )

    rng = random.Random(cfg.seed)
    smp = Sampler(rng, args.dist)

    print(f"Generating city  seed={cfg.seed}  size={cfg.city_width}×{cfg.city_depth}m  dist={args.dist} …")

    # ── Pick 0–3 random downtown centres for height zoning ───────────────────
    n_centers = rng.randint(0, 3)
    half_w, half_d = cfg.city_width * 0.4, cfg.city_depth * 0.4
    downtown_centers = [
        (rng.uniform(-half_w, half_w), rng.uniform(-half_d, half_d))
        for _ in range(n_centers)
    ]
    print(f"  {n_centers} downtown centre{'s' if n_centers != 1 else ''}" +
          (f": {[(round(x,1),round(z,1)) for x,z in downtown_centers]}" if n_centers else ""))

    # ── Build boulevard descriptor list: (x1,z1,x2,z2, poly, angle) ─────────
    boulevards = []

    if cfg.voronoi_boulevards:
        voronoi_segs, _vcenter = generate_voronoi_boulevards(cfg, rng)
        for seg in voronoi_segs:
            bx1, bz1, bx2, bz2 = seg
            boulevards.append((bx1, bz1, bx2, bz2,
                               boulevard_polygon(bx1, bz1, bx2, bz2, cfg.street_width),
                               math.atan2(bz2 - bz1, bx2 - bx1)))

    if cfg.diagonal_road:
        pitch_x = cfg.block_width + cfg.street_width
        pitch_z = cfg.block_depth + cfg.street_width
        n_x = max(1, int(cfg.city_width / pitch_x))
        n_z = max(1, int(cfg.city_depth / pitch_z))
        total_w = n_x * pitch_x - cfg.street_width
        total_d = n_z * pitch_z - cfg.street_width
        bx1, bz1 = -total_w / 2, -total_d / 2
        bx2, bz2 = total_w / 2, total_d / 2
        boulevards.append((bx1, bz1, bx2, bz2,
                           boulevard_polygon(bx1, bz1, bx2, bz2, cfg.street_width),
                           math.atan2(bz2 - bz1, bx2 - bx1)))

    # ── Raised highways ───────────────────────────────────────────────────────
    n_street_blvd = len(boulevards)   # only street-level entries get road_strip geometry
    highway_objects = []
    for hi in range(cfg.num_highways):
        hw_meshes, hw_blvd = generate_highway(cfg, rng)
        boulevards.extend(hw_blvd)    # used for building clearance only
        for part_name, part_mesh in hw_meshes:
            highway_objects.append((f"highway_{hi:02d}_{part_name}", part_mesh))

    lots = generate_lots(cfg, rng, smp, downtown_centers=downtown_centers)
    print(f"  {len(lots)} lots generated")

    print(f"  {len(boulevards)} boulevard segments  "
          f"({cfg.num_highways} highway{'s' if cfg.num_highways != 1 else ''})")

    def _nearest_blvd(lot):
        best_dist, best_angle = float("inf"), 0.0
        for bx1, bz1, bx2, bz2, _poly, angle in boulevards:
            dx, dz = bx2 - bx1, bz2 - bz1
            lsq = dx * dx + dz * dz
            t = max(0.0, min(1.0, ((lot.cx - bx1) * dx + (lot.cz - bz1) * dz) / lsq))
            dist = math.hypot(lot.cx - (bx1 + t * dx), lot.cz - (bz1 + t * dz))
            if dist < best_dist:
                best_dist, best_angle = dist, angle
        return best_dist, best_angle

    def _rotate_to(mesh, lot, angle):
        cx, cz = lot.cx, lot.cz
        return (mesh.transform(pos=(-cx, 0.0, -cz))
                    .transform(rot_y=angle)
                    .transform(pos=(cx, 0.0, cz)))

    def _any_overlap(lot, angle):
        return any(lot_boulevard_overlap(lot, cfg, poly, angle) > 0.01
                   for *_, poly, _ in boulevards)

    rotate_threshold = cfg.block_width

    placed = []
    for i, lot in enumerate(lots):
        mesh = generate_building(lot, cfg, smp)
        if not len(mesh.vertices):
            continue
        rot_angle = None
        if boulevards:
            dist, blvd_angle = _nearest_blvd(lot)
            if dist < rotate_threshold and rng.random() < 0.70:
                mesh = _rotate_to(mesh, lot, blvd_angle)
                rot_angle = blvd_angle
        placed.append((f"building_{i:04d}", mesh, lot, rot_angle))

    objects = []
    removed = 0
    for name, mesh, lot, rot_angle in placed:
        if boulevards and _any_overlap(lot, rot_angle or 0.0):
            removed += 1
            continue
        objects.append((name, mesh))

    print(f"  {len(objects)} buildings placed" +
          (f"  ({removed} cleared for boulevards)" if removed else ""))

    blvd_max_seg = 10.0 if args.surface != "flat" else 0.0
    for i, (bx1, bz1, bx2, bz2, *_) in enumerate(boulevards[:n_street_blvd]):
        objects.append((f"boulevard_{i:03d}", road_strip(bx1, bz1, bx2, bz2, cfg.street_width, cfg.road_height, blvd_max_seg)))

    objects.extend(highway_objects)

    wfn = None
    if args.surface != "flat":
        from procity.warp import (sphere_warp, sphere_mesh,
                                   hemisphere_warp, hemisphere_mesh,
                                   torus_warp, torus_mesh)
        from procity.geometry import Mesh as _Mesh

        if args.surface == "sphere":
            radius = args.sphere_radius or args.city_size / 2
            print(f"  Sphere warp  radius={radius:.1f} m …")
            wfn = lambda v: sphere_warp(v, radius)
            if cfg.add_base:
                objects.insert(0, ("base_plate", sphere_mesh(radius)))
        elif args.surface == "hemisphere":
            radius = args.sphere_radius or args.city_size / 2
            # Auto offset: city_depth/(2R) puts the near edge at the pole;
            # add 15° buffer so the pole stays visibly clear.
            auto_offset = math.degrees(city_depth / (2 * radius)) + 15
            pole_deg = args.pole_offset if args.pole_offset is not None else auto_offset
            lat_offset = math.radians(pole_deg)
            print(f"  Hemisphere warp  radius={radius:.1f} m  pole_offset={pole_deg:.1f}° …")
            wfn = lambda v: hemisphere_warp(v, radius, lat_offset)
            if cfg.add_base:
                objects.insert(0, ("base_plate", hemisphere_mesh(radius)))
        else:
            major = args.torus_major or args.city_size * 1.5
            minor = args.torus_minor or args.city_size * 0.3
            print(f"  Torus warp  major={major:.1f} m  minor={minor:.1f} m …")
            wfn = lambda v: torus_warp(v, major, minor)
            if cfg.add_base:
                objects.insert(0, ("base_plate", torus_mesh(major, minor)))

        objects = [(n, m if n == "base_plate" else _Mesh(wfn(m.vertices), m.faces))
                   for n, m in objects]
    else:
        if cfg.add_base:
            bw = cfg.city_width + 2 * cfg.base_margin
            bd = cfg.city_depth + 2 * cfg.base_margin
            objects.insert(0, ("base_plate", base_plate(bw, bd, cfg.base_thickness)))

    # ── Traffic JSON (road segments for viewer car simulation) ────────────────
    # Build segments in unscaled metres, then warp (if curved) and scale.
    traffic_segs_raw = []
    road_y_raw = cfg.road_height

    pitch_x = cfg.block_width + cfg.street_width
    pitch_z = cfg.block_depth + cfg.street_width
    n_bx = max(1, int(cfg.city_width / pitch_x))
    n_bz = max(1, int(cfg.city_depth / pitch_z))
    total_w = n_bx * pitch_x - cfg.street_width
    total_d = n_bz * pitch_z - cfg.street_width
    ox, oz = -total_w / 2, -total_d / 2

    for bx in range(n_bx - 1):
        x = ox + (bx + 1) * pitch_x - cfg.street_width / 2
        traffic_segs_raw.append({"start": [x, road_y_raw, oz], "end": [x, road_y_raw, oz + total_d], "type": "street"})
    for bz in range(n_bz - 1):
        z = oz + (bz + 1) * pitch_z - cfg.street_width / 2
        traffic_segs_raw.append({"start": [ox, road_y_raw, z], "end": [ox + total_w, road_y_raw, z], "type": "street"})
    for bx1, bz1, bx2, bz2, *_ in boulevards[:n_street_blvd]:
        traffic_segs_raw.append({"start": [bx1, road_y_raw, bz1], "end": [bx2, road_y_raw, bz2], "type": "boulevard"})

    s = cfg.scale
    traffic_segs = []
    if wfn is not None:
        import numpy as _np
        for seg in traffic_segs_raw:
            p0 = _np.array([seg["start"]], float)
            p1 = _np.array([seg["end"]], float)
            seg_len_m = float(_np.hypot(p1[0, 0] - p0[0, 0], p1[0, 2] - p0[0, 2]))
            n_sub = max(1, math.ceil(seg_len_m / 10.0))
            for i in range(n_sub):
                t0, t1 = i / n_sub, (i + 1) / n_sub
                q0 = p0 + (p1 - p0) * t0
                q1 = p0 + (p1 - p0) * t1
                w0 = (wfn(q0)[0] * s).tolist()
                w1 = (wfn(q1)[0] * s).tolist()
                traffic_segs.append({"start": w0, "end": w1, "type": seg["type"]})
    else:
        for seg in traffic_segs_raw:
            traffic_segs.append({
                "start": [v * s for v in seg["start"]],
                "end":   [v * s for v in seg["end"]],
                "type":  seg["type"],
            })

    traffic_path = args.output.replace(".obj", "_traffic.json")
    write_traffic_json(traffic_segs, traffic_path, cfg.street_width * s)
    print(f"Traffic JSON  → {traffic_path}  ({len(traffic_segs)} segments)")

    print(f"Writing {args.output} …")
    write_obj(objects, args.output, scale=cfg.scale)

    total_verts = sum(len(m.vertices) for _, m in objects)
    total_faces = sum(len(m.faces) for _, m in objects)
    print(f"Done.  {total_verts:,} vertices  {total_faces:,} faces  → {args.output}")
    print(f"Print size at 1:{int(round(1/cfg.scale))}: "
          f"{cfg.city_width * cfg.scale * 1000:.0f} × "
          f"{cfg.city_depth * cfg.scale * 1000:.0f} mm")


if __name__ == "__main__":
    main()
