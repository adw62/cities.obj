"""Vertex warping: project flat city geometry onto curved surfaces.

The city is generated on the flat XZ plane with Y as height.  Each warp
function remaps those coordinates to a new 3D position while preserving the
building-height dimension as an outward offset from the surface.

  sphere_warp  – x → longitude, z → latitude, y → radial offset above surface
  torus_warp   – x → angle around major ring, z → angle around tube, y → radial offset
"""

import numpy as np

from .geometry import Mesh


def hemisphere_mesh(radius: float, u_res: int = 64, v_res: int = 16) -> Mesh:
    """Top hemisphere (y≥0) + flat circular cap at y=0, outward-facing normals."""
    phi   = np.linspace(0, 2 * np.pi, u_res, endpoint=False)
    theta = np.linspace(0, np.pi / 2, v_res + 1)   # 0 = pole, π/2 = equator

    T, P = np.meshgrid(theta, phi, indexing='ij')
    x = radius * np.sin(T) * np.cos(P)
    y = radius * np.cos(T)
    z = radius * np.sin(T) * np.sin(P)
    curved_verts = np.stack([x.ravel(), y.ravel(), z.ravel()], axis=1)

    nu = u_res
    faces = []
    for j in range(v_res):
        for i in range(nu):
            a = j * nu + i
            b = j * nu + (i + 1) % nu
            c = (j + 1) * nu + i
            d = (j + 1) * nu + (i + 1) % nu
            faces.extend([[a, c, d], [a, d, b]])

    # Flat disk at y=0, normal pointing -Y (downward/outward)
    equator_start = v_res * nu
    center_idx = len(curved_verts)
    for i in range(nu):
        a = equator_start + i
        b = equator_start + (i + 1) % nu
        faces.append([center_idx, a, b])

    all_verts = np.vstack([curved_verts, [[0.0, 0.0, 0.0]]])
    return Mesh(all_verts, np.array(faces, int))


def hemisphere_warp(vertices: np.ndarray, radius: float,
                    lat_offset: float = 0.0) -> np.ndarray:
    """Project flat (x, y, z) onto the top of a hemisphere.

    x → longitude  (full wrap at city_width = 2π * radius)
    z → co-latitude from the north pole, shifted by lat_offset radians
        so the city centre sits at lat_offset degrees from the pole
        rather than at the pole itself.
    y → radial offset outward from the surface

    lat_offset = 0  → city centre at pole (lots of compression)
    lat_offset > city_depth / (2*radius)  → pole is completely clear of buildings
    """
    x, y, z = vertices[:, 0], vertices[:, 1], vertices[:, 2]
    phi   = x / radius
    theta = lat_offset + z / radius   # co-latitude shifted away from pole
    r     = radius + y

    out = np.empty_like(vertices)
    out[:, 0] = r * np.sin(theta) * np.cos(phi)
    out[:, 1] = r * np.cos(theta)
    out[:, 2] = r * np.sin(theta) * np.sin(phi)
    return out


def sphere_mesh(radius: float, u_res: int = 64, v_res: int = 32) -> Mesh:
    """Full UV sphere centered at the origin, outward-facing normals."""
    phi   = np.linspace(0, 2 * np.pi, u_res, endpoint=False)   # longitude
    theta = np.linspace(0, np.pi,     v_res + 1)                # co-latitude 0=N π=S

    T, P = np.meshgrid(theta, phi, indexing='ij')   # (v_res+1, u_res)
    x = radius * np.sin(T) * np.cos(P)
    y = radius * np.cos(T)
    z = radius * np.sin(T) * np.sin(P)
    verts = np.stack([x.ravel(), y.ravel(), z.ravel()], axis=1)

    nu = u_res
    faces = []
    for j in range(v_res):
        for i in range(nu):
            a = j * nu + i
            b = j * nu + (i + 1) % nu
            c = (j + 1) * nu + i
            d = (j + 1) * nu + (i + 1) % nu
            faces.extend([[a, c, d], [a, d, b]])   # outward normals

    return Mesh(verts, np.array(faces, int))


def torus_mesh(major_radius: float, minor_radius: float,
               u_res: int = 80, v_res: int = 40) -> Mesh:
    """Full torus centered at the origin, outward-facing normals."""
    phi   = np.linspace(0, 2 * np.pi, u_res, endpoint=False)   # around major ring
    theta = np.linspace(0, 2 * np.pi, v_res, endpoint=False)   # around tube

    P, T = np.meshgrid(phi, theta, indexing='ij')   # (u_res, v_res)
    x = (major_radius + minor_radius * np.cos(T)) * np.cos(P)
    y = minor_radius * np.sin(T)
    z = (major_radius + minor_radius * np.cos(T)) * np.sin(P)
    verts = np.stack([x.ravel(), y.ravel(), z.ravel()], axis=1)

    faces = []
    for i in range(u_res):
        for j in range(v_res):
            a = i * v_res + j
            b = i * v_res + (j + 1) % v_res
            c = ((i + 1) % u_res) * v_res + j
            d = ((i + 1) % u_res) * v_res + (j + 1) % v_res
            faces.extend([[a, b, d], [a, d, c]])   # outward normals

    return Mesh(verts, np.array(faces, int))


def sphere_warp(vertices: np.ndarray, radius: float) -> np.ndarray:
    """Project flat (x, y, z) onto a sphere of the given radius.

    The flat city sits at radius R; buildings extend outward (increasing R).
    Coverage: arc = city_size / radius  radians in each direction.
    """
    x, y, z = vertices[:, 0], vertices[:, 1], vertices[:, 2]
    phi   = x / radius          # longitude
    theta = z / radius          # latitude (from equator)
    r     = radius + y          # distance from sphere centre

    out = np.empty_like(vertices)
    out[:, 0] = r * np.cos(theta) * np.sin(phi)
    out[:, 1] = r * np.sin(theta)
    out[:, 2] = r * np.cos(theta) * np.cos(phi)
    return out


def torus_warp(vertices: np.ndarray, major_radius: float, minor_radius: float) -> np.ndarray:
    """Project flat (x, y, z) onto a torus.

    x maps to the angle around the major ring (the big circle).
    z maps to the angle around the tube (the small circle).
    y becomes a radial offset outward from the tube centreline.

    For seamless tiling set city_width  = 2π * major_radius
                             city_depth = 2π * minor_radius.
    """
    x, y, z = vertices[:, 0], vertices[:, 1], vertices[:, 2]
    phi   = x / major_radius    # angle around the hole
    theta = z / minor_radius    # angle around the tube
    r     = minor_radius + y    # distance from tube centreline

    out = np.empty_like(vertices)
    out[:, 0] = (major_radius + r * np.cos(theta)) * np.cos(phi)
    out[:, 1] = r * np.sin(theta)
    out[:, 2] = (major_radius + r * np.cos(theta)) * np.sin(phi)
    return out
