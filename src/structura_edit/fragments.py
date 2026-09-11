import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from structura_core.nbt import save_structure

from .cell_set import CellSet
from .changes import _position
from .local_store import list_bundles, publish_bundle, read_bundle, read_json, storage_root
from .selection_export import selected_structure
from .session import EditSession


def fragment_root():
    return storage_root() / "fragments"


def save_fragment(session, selection, name, tags=(), anchor=None, *, root=None):
    name = name.strip()
    if not name or len(name) > 120:
        raise ValueError("Fragment name must contain 1 to 120 characters")
    clipboard = session.copy(selection)
    anchor = _position(anchor or (clipboard.size[0] // 2, 0, clipboard.size[2] // 2))
    if not all(0 <= p < size for p, size in zip(anchor, clipboard.size)):
        raise ValueError("Anchor must be inside the fragment")
    tags = tuple(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))
    if len(tags) > 32 or any(len(tag) > 80 for tag in tags):
        raise ValueError("Use up to 32 short tags")
    def write(stage):
        source = selected_structure(session, selection)
        source.entities = [entity.unpack() for _, entity in clipboard.entities]
        save_structure(source, stage / "fragment.nbt", source.size)
        footprint = [[key, bits.hex()] for key, bits in clipboard.footprint.sections] if clipboard.footprint is not None else None
        (stage / "footprint.json").write_text(json.dumps(footprint))
        _thumbnail(source, stage / "thumbnail.png")
        return {"name": name, "tags": tags, "anchor": anchor, "size": clipboard.size,
                "data_version": clipboard.data_version, "updated": datetime.now(timezone.utc).isoformat()}
    return publish_bundle(root or fragment_root(), uuid4().hex, write)


def _thumbnail(source, path):
    from PIL import Image
    from structura_render.block_colours import block_color

    image = Image.new("RGB", (128, 128), (241, 238, 220))
    columns = {}
    for (x, y, z), index in source.present.items():
        name = str(source.palette_raw[index]["Name"])
        if name.endswith(":air"):
            continue
        if (x, z) not in columns or y > columns[x, z][0]:
            columns[x, z] = y, name
    for (x, z), (_, name) in columns.items():
        left, right = x * 128 // source.size[0], max(x * 128 // source.size[0] + 1, (x + 1) * 128 // source.size[0])
        top, bottom = z * 128 // source.size[2], max(z * 128 // source.size[2] + 1, (z + 1) * 128 // source.size[2])
        image.paste(tuple(block_color(name, "family")), (left, top, right, bottom))
    image.save(path)


def load_fragment(path):
    path = Path(path)
    metadata = read_bundle(path)
    session = EditSession.open(path / "fragment.nbt")
    masks = read_json(path / "footprint.json")
    selected = CellSet(tuple((tuple(key), bytes.fromhex(bits)) for key, bits in masks)) if masks is not None else session.select()
    return replace(session.copy(selected), anchor=_position(metadata["anchor"]))


def list_fragments(root=None):
    return list_bundles(root or fragment_root())
