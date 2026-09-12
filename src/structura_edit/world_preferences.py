import json

from structura_core.nbt_io import atomic_write

from .loading import DEFAULT_RADIUS, DEFAULT_VERTICAL_RADIUS, MAX_RADIUS
from .local_store import storage_root


def load_distance():
    try:
        data = json.loads((storage_root() / "world-view.json").read_text())
        radius, vertical = data["radius"], data["vertical_radius"]
        if type(radius) is int and 0 <= radius <= MAX_RADIUS and (vertical is None or type(vertical) is int and 16 <= vertical <= 192):
            return radius, vertical if data.get("version") == 2 else None
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return DEFAULT_RADIUS, DEFAULT_VERTICAL_RADIUS


def save_distance(radius, vertical):
    root = storage_root()
    root.mkdir(parents=True, exist_ok=True)
    atomic_write(root / "world-view.json", json.dumps(dict(version=2, radius=radius, vertical_radius=vertical)).encode())
