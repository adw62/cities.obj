from dataclasses import dataclass


@dataclass
class CityConfig:
    # ── Randomisation ──────────────────────────────────────────────────────────
    seed: int = 42

    # ── City footprint (metres) ────────────────────────────────────────────────
    city_width: float = 200.0   # X extent
    city_depth: float = 200.0   # Z extent

    # ── Street grid ───────────────────────────────────────────────────────────
    block_width: float = 40.0   # block size along X (excluding street)
    block_depth: float = 40.0   # block size along Z (excluding street)
    street_width: float = 8.0   # street width

    # ── Lots ──────────────────────────────────────────────────────────────────
    min_lot_size: float = 8.0
    max_lot_size: float = 20.0
    lot_setback: float = 0.5    # building setback from lot edge on each side

    # ── Buildings ─────────────────────────────────────────────────────────────
    floor_height: float = 3.0   # metres per storey
    min_floors: int = 1
    max_floors: int = 18        # max storeys anywhere in the city
    downtown_boost: float = 2.5 # multiplier for max floors near city centre
    max_aspect_ratio: float = 4.0  # max height / min(footprint width, depth) at city edge
    size_scale: float = 1.0        # global multiplier on building footprint dimensions

    # ── Roof ──────────────────────────────────────────────────────────────────
    roof_pyramid_chance: float = 0.25
    roof_pyramid_height: float = 3.0

    # ── Base plate ────────────────────────────────────────────────────────────
    add_base: bool = True
    base_thickness: float = 2.0  # metres (pre-scale)
    base_margin: float = 5.0     # extra margin around city edge

    # ── Layout ────────────────────────────────────────────────────────────────
    use_triangle_blocks: bool = False  # split every block into 2 triangular lots
    diagonal_road: bool = False        # SW→NE diagonal boulevard
    voronoi_boulevards: bool = False   # Voronoi cell edges become boulevards
    voronoi_sites: int = 8             # number of Voronoi cells

    # ── Roads ─────────────────────────────────────────────────────────────────
    road_height: float = 0.5      # slab height for boulevard geometry

    # ── Building detail ───────────────────────────────────────────────────────
    window_min_floors: int = 4      # add windows to buildings with >= this many floors
    window_depth: float = 0.5       # recess depth in metres
    setback_min_floors: int = 10    # min floors before a random setback tier is applied

    # ── Highways ──────────────────────────────────────────────────────────────
    num_highways: int = 0
    highway_elevation: float = 10.0     # metres above ground
    highway_carriage_width: float = 6.0 # each carriageway deck
    highway_median_width: float = 3.0   # gap between the two decks
    highway_deck_thickness: float = 1.5
    highway_pillar_spacing: float = 30.0
    highway_pillar_size: float = 2.5

    # ── Export ────────────────────────────────────────────────────────────────
    scale: float = 0.001         # multiply all metres by this → 1:1000
    output: str = "city.obj"
