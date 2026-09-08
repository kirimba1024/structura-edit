from collections import Counter

from .picking import EMPTY
from .resources import refresh_resources, texture_bank


def selection_materials(session, selection, assets=None):
    from structura_core import parse_state
    from structura_render.block_colours import block_color
    from structura_render.block_model import block_elements
    from structura_render.textures import tint_for
    from PIL import Image

    counts, states = Counter(), {}
    for state, count in session.palette_counts(selection).items():
        name = state.split("[", 1)[0]
        if name not in EMPTY:
            counts[name] += count
            states.setdefault(name, state)
    refresh_resources(assets)
    bank = texture_bank(assets)
    rows = []
    with bank.context.activate():
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
            pixels = None
            if bank.available():
                props = {key: str(value) for key, value in parse_state(states[name]).get("Properties", {}).items()}
                elements = block_elements(name, props) or []
                face = next((element["faces"][side] for side in ("up", "north", "south", "east", "west", "down")
                             for element in elements if side in element["faces"]), None)
                if face:
                    tint = tint_for(name, props) if face["tinted"] else None
                    image = bank.read_texture(face["texture"], tint)
                    if image is not None:
                        pixels = image.convert("RGBA").resize((16, 16), Image.Resampling.NEAREST).tobytes()
            rows.append((name, count, pixels, block_color(name, "family")))
    return rows
