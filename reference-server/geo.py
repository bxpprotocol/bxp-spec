"""
Geohash and great-circle helpers for the BXP reference node.

Pure functions, standard library only. The Python SDK (sdk/python/bxp_sdk.py)
and TypeScript SDK ship their own geohash encoders because they are separately
installable packages; tests/test_geo.py and conformance/geohash_vectors.json pin
all implementations to the same outputs so they cannot silently drift apart.
"""

import math

BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"
_BASE32_INDEX = {c: i for i, c in enumerate(BASE32)}
_BITS = (16, 8, 4, 2, 1)

# Readings are stored with a geohash of at most this many characters for
# anonymous submissions (SPEC.md section 9.1: personal precision defaults to 5),
# so spatial prefix queries must never use a longer prefix than this.
STORED_PRECISION_FLOOR = 5

_M_PER_DEG_LAT = 111_320.0  # metres per degree of latitude (and of longitude at the equator)


def is_valid_geohash(value: str, min_len: int = 1, max_len: int = 12) -> bool:
    """True if `value` is a lowercase base-32 geohash of an acceptable length."""
    return (
        isinstance(value, str)
        and min_len <= len(value) <= max_len
        and all(c in _BASE32_INDEX for c in value)
    )


def encode_geohash(lat: float, lon: float, precision: int = 7) -> str:
    lat_range, lon_range = [-90.0, 90.0], [-180.0, 180.0]
    out, bit, ch, even = [], 0, 0, True
    while len(out) < precision:
        rng, val = (lon_range, lon) if even else (lat_range, lat)
        mid = (rng[0] + rng[1]) / 2
        if val >= mid:
            ch |= _BITS[bit]
            rng[0] = mid
        else:
            rng[1] = mid
        even = not even
        if bit < 4:
            bit += 1
        else:
            out.append(BASE32[ch])
            bit = ch = 0
    return "".join(out)


def decode_bbox(geohash: str) -> tuple[tuple[float, float], tuple[float, float]]:
    """Return ((lat_min, lat_max), (lon_min, lon_max)). Raises ValueError on bad input."""
    lat_range, lon_range = [-90.0, 90.0], [-180.0, 180.0]
    even = True
    for char in geohash:
        idx = _BASE32_INDEX.get(char)
        if idx is None:
            raise ValueError(f"invalid geohash character {char!r}")
        for bit in _BITS:
            rng = lon_range if even else lat_range
            mid = (rng[0] + rng[1]) / 2
            if idx & bit:
                rng[0] = mid
            else:
                rng[1] = mid
            even = not even
    return (lat_range[0], lat_range[1]), (lon_range[0], lon_range[1])


def cell_center(geohash: str) -> tuple[float, float]:
    (lat_min, lat_max), (lon_min, lon_max) = decode_bbox(geohash)
    return (lat_min + lat_max) / 2, (lon_min + lon_max) / 2


def snap_to_cell_center(lat: float, lon: float, precision: int) -> tuple[float, float]:
    """Coarsen a coordinate to the centre of its geohash cell (privacy floor)."""
    return cell_center(encode_geohash(lat, lon, precision))


def neighbors(geohash: str) -> set[str]:
    """The cell itself plus its 8 neighbours at the same precision (wraps the antimeridian)."""
    (lat_min, lat_max), (lon_min, lon_max) = decode_bbox(geohash)
    lat_c, lon_c = (lat_min + lat_max) / 2, (lon_min + lon_max) / 2
    dlat, dlon = lat_max - lat_min, lon_max - lon_min
    cells = set()
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            nlat = max(-90.0, min(90.0, lat_c + i * dlat))
            nlon = ((lon_c + j * dlon + 180.0) % 360.0) - 180.0
            cells.add(encode_geohash(nlat, nlon, len(geohash)))
    return cells


def cell_size_m(precision: int, at_lat: float) -> tuple[float, float]:
    """(width_m, height_m) of a geohash cell of `precision`, with width measured at `at_lat`."""
    lon_bits = (5 * precision + 1) // 2
    lat_bits = (5 * precision) // 2
    width_deg = 360.0 / (1 << lon_bits)
    height_deg = 180.0 / (1 << lat_bits)
    cos_lat = max(math.cos(math.radians(min(abs(at_lat), 89.9))), 1e-6)
    return width_deg * _M_PER_DEG_LAT * cos_lat, height_deg * _M_PER_DEG_LAT


def precision_for_radius(lat: float, radius_m: float,
                         max_precision: int = STORED_PRECISION_FLOOR) -> int:
    """
    Largest geohash precision (<= max_precision) whose 3x3 neighbourhood is
    guaranteed to contain every point within `radius_m` of a point at `lat`.

    A circle of radius r around a point inside the centre cell stays inside the
    3x3 block iff r <= min(cell width, cell height). Cell width shrinks with
    cos(latitude), so the fixed "precision 5 covers ~4.9 km" rule of thumb is
    wrong away from the equator; this measures the narrowest edge the block can
    reach instead. Returns 1 if even the coarsest cells are too small.
    """
    for precision in range(max_precision, 0, -1):
        _, height_m = cell_size_m(precision, 0.0)
        height_deg = height_m / _M_PER_DEG_LAT
        worst_lat = min(abs(lat) + height_deg, 89.9)  # pole-most edge of the 3x3 block
        width_m, _ = cell_size_m(precision, worst_lat)
        if radius_m <= min(width_m, height_m):
            return precision
    return 1


def prefix_bounds(prefix: str) -> tuple[str, str]:
    """
    [lo, hi) bounds such that `lo <= geohash < hi` matches exactly the strings
    starting with `prefix`. Unlike `LIKE 'prefix%'`, this range form is served
    by a plain B-tree index (SQLite only optimises LIKE under NOCASE collation)
    and treats '%' / '_' in user input as ordinary characters.
    """
    if not prefix:
        raise ValueError("prefix must be non-empty")
    return prefix, prefix[:-1] + chr(ord(prefix[-1]) + 1)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))
