import numpy as np
from dataclasses import dataclass


@dataclass
class Mesh:
    vertices: np.ndarray  # (N, 3) float64
    faces: np.ndarray     # (M, 3) int32

    def transform(self, pos=(0, 0, 0), scale=(1, 1, 1), rot_y=0.0) -> "Mesh":
        v = self.vertices * np.asarray(scale, float)
        if rot_y:
            c, s = np.cos(rot_y), np.sin(rot_y)
            R = np.array([[c, 0, -s], [0, 1, 0], [s, 0, c]])
            v = v @ R.T
        return Mesh(v + np.asarray(pos, float), self.faces.copy())

    def merge(self, other: "Mesh") -> "Mesh":
        offset = len(self.vertices)
        return Mesh(
            np.vstack([self.vertices, other.vertices]),
            np.vstack([self.faces, other.faces + offset]),
        )


def empty() -> Mesh:
    return Mesh(np.empty((0, 3), float), np.empty((0, 3), int))


def box(w: float, h: float, d: float) -> Mesh:
    """Axis-aligned box: width w (X), height h (Y), depth d (Z).
    Centered on X/Z, sitting on Y=0."""
    x, z = w / 2, d / 2
    v = np.array(
        [
            [-x, 0, -z], [x, 0, -z], [x, 0, z], [-x, 0, z],
            [-x, h, -z], [x, h, -z], [x, h, z], [-x, h, z],
        ],
        dtype=float,
    )
    f = np.array(
        [
            [0, 2, 1], [0, 3, 2],       # bottom  (-Y)
            [4, 5, 6], [4, 6, 7],       # top     (+Y)
            [0, 1, 5], [0, 5, 4],       # south   (-Z)
            [1, 2, 6], [1, 6, 5],       # east    (+X)
            [2, 3, 7], [2, 7, 6],       # north   (+Z)
            [3, 0, 4], [3, 4, 7],       # west    (-X)
        ]
    )
    return Mesh(v, f)


def prism(n: int, r: float, h: float) -> Mesh:
    """Regular n-gon prism: apothem radius r, height h, centered on X/Z, sitting on Y=0."""
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    bot = np.column_stack([np.cos(a) * r, np.zeros(n), np.sin(a) * r])
    top = np.column_stack([np.cos(a) * r, np.full(n, h), np.sin(a) * r])
    v = np.vstack([bot, top]).astype(float)

    f = []
    for i in range(1, n - 1):          # bottom cap fan
        f.append([0, i + 1, i])
    for i in range(1, n - 1):          # top cap fan
        f.append([n, n + i, n + i + 1])
    for i in range(n):                  # side quads → 2 tris
        j = (i + 1) % n
        f.append([i, j, n + j])
        f.append([i, n + j, n + i])
    return Mesh(v, np.array(f, int))


def cylinder(r: float, h: float, segs: int = 16) -> Mesh:
    return prism(segs, r, h)


def pyramid(w: float, h: float, d: float) -> Mesh:
    """4-sided pyramid: base w×d on Y=0, apex at (0, h, 0)."""
    x, z = w / 2, d / 2
    v = np.array(
        [
            [-x, 0, -z], [x, 0, -z], [x, 0, z], [-x, 0, z],
            [0, h, 0],
        ],
        dtype=float,
    )
    f = np.array(
        [
            [0, 2, 1], [0, 3, 2],       # base
            [0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4],  # sides
        ]
    )
    return Mesh(v, f)


def poly_prism(verts_xz: list, h: float) -> Mesh:
    """Extrude an arbitrary polygon to height h.

    verts_xz: list of (x, z) tuples in CCW order (viewed from above), world-space.
    The prism sits between Y=0 and Y=h.
    """
    n = len(verts_xz)
    bot = np.array([[x, 0.0, z] for x, z in verts_xz], dtype=float)
    top = np.array([[x, h,   z] for x, z in verts_xz], dtype=float)
    v = np.vstack([bot, top])

    f = []
    for i in range(1, n - 1):        # bottom cap
        f.append([0, i + 1, i])
    for i in range(1, n - 1):        # top cap
        f.append([n, n + i, n + i + 1])
    for i in range(n):                # side quads → 2 tris
        j = (i + 1) % n
        f.append([i, j, n + j])
        f.append([i, n + j, n + i])
    return Mesh(v, np.array(f, int))


def windowed_box(w: float, h: float, d: float, n_floors: int,
                 win_depth: float = 0.5) -> Mesh:
    """Box with recessed window wells on all 4 vertical faces. Sits on Y=0.

    Each floor gets one row of windows; bays are spaced ~4 m apart.
    Winding matches box(): cross-product normals point into the solid.
    """
    hw, hd = w / 2, d / 2
    wd = win_depth

    # Each face is described by its outer and inner world-space mapping.
    # U runs along the face width, V runs upward.  Inner is recessed into the building.
    # Winding is derived so cross(B-A, C-A) points into the solid for every face.
    panels = [
        (w, lambda u, v: ( u-hw, v, -hd    ), lambda u, v: ( u-hw, v, -hd+wd)),  # south
        (w, lambda u, v: (hw-u,  v,  hd    ), lambda u, v: (hw-u,  v,  hd-wd)),  # north
        (d, lambda u, v: ( hw,   v,  u-hd  ), lambda u, v: ( hw-wd,v,  u-hd )),  # east
        (d, lambda u, v: (-hw,   v,  hd-u  ), lambda u, v: (-hw+wd,v,  hd-u )),  # west
    ]

    all_verts: list = []
    all_faces: list = []

    for panel_w, ofn, ifn in panels:
        n_bays  = max(1, round(panel_w / 4.0))
        bay_w   = panel_w / n_bays
        floor_h = h / n_floors
        mu      = bay_w   * 0.20   # horizontal margin each side
        mv_b    = floor_h * 0.15   # sill height
        wu      = bay_w   - 2 * mu
        wv      = floor_h * 0.70   # window height

        u_grid: list = []
        for b in range(n_bays):
            o = b * bay_w
            u_grid += [o, o + mu, o + mu + wu]
        u_grid.append(panel_w)

        v_grid: list = []
        for f in range(n_floors):
            o = f * floor_h
            v_grid += [o, o + mv_b, o + mv_b + wv]
        v_grid.append(h)

        nu, nv = len(u_grid), len(v_grid)
        base = len(all_verts)

        for iv in range(nv):
            for iu in range(nu):
                all_verts.append(ofn(u_grid[iu], v_grid[iv]))

        def oi(iu, iv, _b=base, _nu=nu):
            return _b + iv * _nu + iu

        inner_map: dict = {}
        for iu in range(nu - 1):
            for iv in range(nv - 1):
                if iu % 3 == 1 and iv % 3 == 1:
                    for du, dv in [(0,0),(1,0),(0,1),(1,1)]:
                        key = (iu+du, iv+dv)
                        if key not in inner_map:
                            inner_map[key] = len(all_verts)
                            all_verts.append(ifn(u_grid[iu+du], v_grid[iv+dv]))

        for iu in range(nu - 1):
            for iv in range(nv - 1):
                a  = oi(iu,   iv  )
                b_ = oi(iu+1, iv  )
                c  = oi(iu,   iv+1)
                d_ = oi(iu+1, iv+1)
                if iu % 3 == 1 and iv % 3 == 1:
                    ai = inner_map[(iu,   iv  )]
                    bi = inner_map[(iu+1, iv  )]
                    ci = inner_map[(iu,   iv+1)]
                    di = inner_map[(iu+1, iv+1)]
                    all_faces += [
                        [a,  b_, bi], [a,  bi, ai],   # bottom sill
                        [c,  ci, di], [c,  di, d_],   # top head
                        [a,  ci, c ], [a,  ai, ci],   # left jamb
                        [b_, d_, di], [b_, di, bi],   # right jamb
                        [ai, bi, di], [ai, di, ci],   # back face
                    ]
                else:
                    all_faces += [[a, b_, d_], [a, d_, c]]

    # Top and bottom caps (same winding as box())
    bv = len(all_verts)
    all_verts += [[-hw,0,-hd],[hw,0,-hd],[hw,0,hd],[-hw,0,hd],
                  [-hw,h,-hd],[hw,h,-hd],[hw,h,hd],[-hw,h,hd]]
    all_faces += [[bv,bv+2,bv+1],[bv,bv+3,bv+2],
                  [bv+4,bv+5,bv+6],[bv+4,bv+6,bv+7]]

    return Mesh(np.array(all_verts, float), np.array(all_faces, int))


def road_strip(x1: float, z1: float, x2: float, z2: float,
               width: float, height: float = 0.5,
               max_seg: float = 0.0) -> Mesh:
    """Shallow road slab between two world-space XZ points, sitting on Y=0.

    If max_seg > 0 the strip is divided into segments of at most that length
    so it follows curved surfaces smoothly after warping.
    """
    dx, dz = x2 - x1, z2 - z1
    length = float(np.hypot(dx, dz))
    angle = float(np.arctan2(dz, dx))
    cx, cz = (x1 + x2) / 2, (z1 + z2) / 2

    if max_seg > 0.0 and length > max_seg:
        n = int(np.ceil(length / max_seg))
        seg_len = length / n
        acc = empty()
        for i in range(n):
            ox = -length / 2 + (i + 0.5) * seg_len
            acc = acc.merge(box(seg_len, height, width).transform(pos=(ox, 0.0, 0.0)))
        return acc.transform(pos=(cx, 0.0, cz), rot_y=angle)

    return box(length, height, width).transform(pos=(cx, 0.0, cz), rot_y=angle)


def base_plate(w: float, d: float, thickness: float = 1.0) -> Mesh:
    """Flat rectangular base for the city, sitting below Y=0."""
    return box(w, thickness, d).transform(pos=(0, -thickness, 0))
