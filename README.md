# procity

Procedural 3D city generator that exports `.obj` files ready for 3D printing, with a browser-based 3D viewer.

Builds a full city from scratch — street grid or Voronoi boulevard network, zoned building heights, raised highways, rooftop clutter, windows, spires — and writes a single watertight mesh scaled for a 1:1000 print.

## Project layout

```
procity/
├── main.py            # generator CLI
├── index.html         # browser-based 3D viewer
├── generator.js       # in-browser generator (Web Worker)
├── procity/           # generator Python package
├── music/             # background music (MP3 + manifest.json)
└── output/
    ├── manifest.json  # list of .obj files shown in the viewer dropdown
    └── *.obj / *_traffic.json
```

## Quick start

```bash
pip install numpy scipy
python main.py --voronoi --city-size 600 --dist gumbel --seed 7 --output output/city_big.obj
```

This produces a 600 × 600 mm (at 1:1000) city with organic Voronoi boulevards, a right-skewed height distribution (mostly low buildings, rare towers), and one raised highway. The mesh is written to `output/`. Load it into a slicer or open it in the viewer (see below).

## Viewer

The renderer is a single-page Three.js app. It must be served over HTTP — opening `index.html` directly as a `file://` URL will fail due to browser CORS restrictions on loading `.obj` files.

**Start a local server from the project root:**

```bash
python -m http.server 8000
```

Then open `http://localhost:8000/` in your browser.

The first city found in `output/manifest.json` loads automatically.

### Top bar

| Control | Description |
|---------|-------------|
| **⏸ / ▶** | Pause / resume all time-based animation (sun, planets, rotation) |
| **Free Cam** | Toggle FPS free camera — WASD move, mouse look, Q/E up/down, Shift slow, Esc exit |
| Music controls | Play/pause background music, track skip, volume |

### Left panels (all collapsible)

**Generate City** — build a city directly in the browser without running Python. All generator options available; result can be downloaded as an `.obj`.

**Events**

| Control | Description |
|---------|-------------|
| **Cars** | Toggle traffic simulation; slider sets vehicle count |
| **Rain** | Particle rain |
| **Fire** | Fire event on a random building |
| **UFO** | UFO abduction event |
| **Tornado** | Tornado sweeping through the city |
| **Birds** | Flocking boid bird simulation |

**Sky**

| Control | Description |
|---------|-------------|
| **Sky** | Toggle the full skybox — animated sun arc, dynamic sky colour, stars, and planets |
| **Clouds** | Slider (0–60) spawns billboard sprite clouds that drift slowly; independent of Sky toggle |
| **Planets** | Slider (0–12) spawns randomly coloured orbiting planets |
| **Time of Day** | Scrub the sun position manually |
| **Time of Year** | Scrub planet orbital positions |

**Scene**

| Control | Description |
|---------|-------------|
| **Base / Building / Road Color** | Per-layer colour pickers |
| **Fog** | Toggle exponential depth fog; density slider |
| **Rotation Speed** | City auto-rotation speed |
| **Ambient Light** | Scene ambient intensity |
| **Wireframe** | Toggle edge wireframe overlay; opacity slider |

### In-browser generator

Click **Generate City** in the left panel to build a city directly in the browser without running Python. All options are available, and the result can be downloaded as an `.obj` file. Generated cities support traffic simulation on all surface types including sphere, hemisphere, and torus.

### Traffic simulation

Cities generated with `--traffic` (CLI) or via the browser generator export a `_traffic.json` file alongside the `.obj`. When the viewer loads a city that has a matching traffic file it enables a car spawner — use the slider in the right panel to set the number of vehicles. Cars follow road segments and pick random turns at intersections. On curved surfaces (sphere, hemisphere, torus) cars are lifted along the surface normal and oriented correctly relative to the road and surface.

## All options

| Flag | Default | Description |
|------|---------|-------------|
| `--seed N` | `42` | Random seed for reproducibility |
| `--output FILE` | `output/city.obj` | Output OBJ filename |
| `--city-size M` | `400` | City width and depth in metres |
| `--scale F` | `0.001` | Multiplier applied to all metres (0.001 = 1:1000) |
| `--max-floors N` | `18` | Maximum storeys anywhere in the city |
| `--dist` | `uniform` | Height distribution: `uniform`, `gumbel` (right-skewed), `normal` |
| `--no-base` | off | Omit the ground base plate |
| `--diagonal-road` | off | Add a SW→NE diagonal boulevard |
| `--voronoi` | off | Use Voronoi cell edges as the boulevard network |
| `--highways N` | `1` | Number of raised dual-carriageway highway splines |
| `--no-windows` | off | Omit window indentations (faster, smaller file) |
| `--city-width M` | `--city-size` | City width (X) in metres, overrides `--city-size` |
| `--city-depth M` | `--city-size` | City depth (Z) in metres, overrides `--city-size` |
| `--voronoi-sites N` | `8` | Number of Voronoi cells |
| `--surface` | `flat` | Project onto a curved surface: `flat`, `sphere`, `hemisphere`, `torus` |
| `--sphere-radius F` | `city_size/2` | Sphere / hemisphere radius in metres |
| `--pole-offset F` | auto | Hemisphere only: degrees from pole to city centre (auto keeps pole clear) |
| `--torus-major F` | `city_size*1.5` | Torus major radius (centre to tube centre) in metres |
| `--torus-minor F` | `city_size*0.3` | Torus tube radius in metres |

## Building grammar

Each lot is assigned one of several procedural styles, weighted by downtown proximity:

- **simple** — single box or prism, optional setback upper tier
- **stepped** — 2–4 diminishing tiers stacked vertically
- **tower\_podium** — wide low podium with a narrow tall tower offset on top
- **l\_shaped** — two rectangular wings forming an L plan
- **courtyard** — U-shaped building around an open court
- **chamfered** — faceted polygonal prism tower (6, 8, or 12 sides), tall buildings only

Tall buildings (4+ floors) get recessed window wells. Flat roofs get rooftop clutter — AC units, ducts, water tanks, vent pipes. Very tall towers get spires.

## Height zoning

The generator picks 0–3 random downtown centres per run. Each city block gets a height cap driven by its distance to the nearest centre, using a power-law falloff. Buildings within a block vary further by an exponential draw within that cap, so you get a realistic gradient from dense towers to low suburban sprawl.

## Highways

Raised dual-carriageway highways are cubic splines (via scipy) crossing the city from edge to edge with a single gentle bend. Each highway has:
- Two elevated road decks offset either side of the centreline
- Box pillars at regular intervals beneath each carriageway
- A clearance zone that removes buildings from the path

## Output

The OBJ contains named objects: `base_plate`, `building_0001` … `building_NNNN`, `boulevard_000` …, `highway_00_left_deck`, `highway_00_right_deck`, `highway_00_pillar_000` …

All geometry sits on Y = 0 (top of base plate). The base plate extends 5 m beyond the city edge on all sides and is 2 m thick (pre-scale).

## Example commands

```bash
# Compact grid city, normal height distribution
python main.py --seed 42 --city-size 300 --dist normal --output output/city_grid.obj

# Large Voronoi city, skewed heights, two highways, no windows (fast)
python main.py --voronoi --city-size 600 --dist gumbel --seed 7 --highways 2 --no-windows --output output/city_big.obj

# Diagonal boulevard across a standard grid
python main.py --seed 7 --diagonal-road --output output/city_diag.obj

# Tiny city for a quick test
python main.py --seed 7 --city-size 200 --max-floors 8 --no-base --output output/city_small.obj

# Sphere projection
python main.py --seed 7 --city-size 300 --dist gumbel --surface sphere --output output/city_sphere.obj

# Hemisphere — city band wraps around a dome, pole left clear
python main.py \
  --seed 10 \
  --surface hemisphere \
  --sphere-radius 200 \
  --city-width 1257 \
  --city-depth 250 \
  --dist gumbel \
  --max-floors 30 \
  --highways 1 \
  --output output/city_hemisphere.obj

# Hemisphere with Voronoi boulevards
python main.py \
  --seed 600 \
  --surface hemisphere \
  --sphere-radius 200 \
  --city-width 1257 \
  --city-depth 250 \
  --dist gumbel \
  --max-floors 30 \
  --highways 1 \
  --voronoi \
  --output output/city_hemisphere_voronoi.obj

# Decorated ring — city on outer face of a large torus
python main.py --seed 7 --surface torus \
  --torus-major 200 --torus-minor 80 --city-width 1257 --city-depth 200 \
  --dist gumbel --max-floors 30 --highways 0 --output output/city_ring_big.obj
```

## Surface projection

The `--surface` flag warps all generated geometry onto a curved surface after generation. The base plate is replaced with a full sphere or torus mesh so the result is always a complete closed solid with buildings on top. Boulevards are subdivided into short segments before warping so they follow the surface smoothly.

**Sphere** — maps X→longitude, Z→latitude, Y→radial offset. Building height stays perpendicular to the surface.

```bash
python main.py --seed 7 --city-size 300 --dist gumbel --surface sphere --output output/city_sphere.obj
```

**Hemisphere** — same projection as sphere but the base is a dome (flat bottom, curved top). The city centre is shifted away from the pole by `--pole-offset` degrees (auto-calculated if omitted) so buildings don't bunch at the compression point. For full longitude wrap set `city_width = 2π × radius`.

```bash
python main.py \
  --seed 10 \
  --surface hemisphere \
  --sphere-radius 200 \
  --city-width 1257 \
  --city-depth 250 \
  --dist gumbel \
  --max-floors 30 \
  --highways 1 \
  --output output/city_hemisphere.obj

python main.py \
  --seed 600 \
  --surface hemisphere \
  --sphere-radius 200 \
  --city-width 1257 \
  --city-depth 250 \
  --dist gumbel \
  --max-floors 30 \
  --highways 1 \
  --voronoi \
  --output output/city_hemisphere_voronoi.obj
```

**Torus** — maps X→angle around the major ring, Z→angle around the tube, Y→outward offset. For seamless tiling set `city_width = 2π × major` and `city_depth = 2π × minor`. For a decorated outer-ring look, keep `city_depth` small (covers only the outer arc of the tube).

```bash
# Fully wrapped torus
python main.py --seed 7 --voronoi --voronoi-sites 12 --surface torus \
  --torus-major 100 --torus-minor 40 --city-width 628 --city-depth 120 \
  --dist gumbel --max-floors 24 --highways 0 --output output/city_torus_full.obj

# Decorated ring — buildings on outer face only, bare torus underneath
python main.py --seed 7 --surface torus \
  --torus-major 200 --torus-minor 80 --city-width 1257 --city-depth 200 \
  --dist gumbel --max-floors 30 --highways 0 --output output/city_ring_big.obj
```

## Dependencies

- `numpy` — geometry and mesh operations
- `scipy` — cubic spline interpolation for highway curves (only needed when `--highways` > 0)
