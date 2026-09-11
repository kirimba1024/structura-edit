import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from structura_core.nbt import Structure, save_structure
from structura_core.schematic import Schematic
from structura_core.world import WorldRegion
from structura_core.world_backup import digest

from .document import Document
from .local_store import MAX_RECORD_BYTES, list_bundles, publish_bundle, read_bundle, read_json, storage_root
from .patch_codec import cell, encode, entity, pack_patch, unpack_patch
from .saved_changes import SavedChanges
from .session import EditSession
from .world_view import WorldView


def draft_root():
    return storage_root() / "drafts"


def save_draft(session, *, root=None):
    def write(stage):
        source = session._document.source
        save_structure(source, stage / "base.nbt", source.size)
        native = session._document.native
        if native is not None:
            native.save(stage / "native.schem")
        data = {"cells": [[point, encode(value)] for point, value in session._cells.items()],
                "entities": {key: encode(value) for key, value in session._entities.items()}}
        world = getattr(session, "world_changes", None)
        saved = world or session._saved_changes
        data.update(blocks=pack_patch(world.patch if world else saved.blocks), entities_patch=pack_patch(saved.entities))
        metadata = {"kind": "world" if world else "structure", "source": str(session.path) if session.path else None,
                    "source_hash": getattr(session._document, "source_hash", None),
                    "target": str(session.save_target) if session.save_target else None, "origin": session.origin,
                    "palette": source.palette_index, "revision": session.revision,
                    "updated": datetime.now(timezone.utc).isoformat(), "history": "Checkpoint only; earlier Undo history is unavailable"}
        if world:
            metadata["world"] = {key: getattr(session, key) for key in ("dimension", "center", "radius", "vertical_radius", "dimensions", "world_name")}
            data["loaded"] = list(session.loaded_chunks)
            data["sections"] = list(session.loaded_sections) if session.loaded_sections is not None else None
            data["base_entities"] = {key: encode(value) for key, value in session._base_entities.items()}
        else:
            metadata["saved_origin"], metadata["saved_size"] = saved.origin, saved.size
        payload = json.dumps(data)
        if len(payload.encode()) > MAX_RECORD_BYTES:
            raise ValueError("Draft patch exceeds 128 MiB")
        (stage / "patch.json").write_text(payload)
        return metadata
    return publish_bundle(root or draft_root(), session._id, write)


def restore_draft(path):
    path = Path(path)
    metadata = read_bundle(path)
    source = Structure(path / "base.nbt", palette_index=metadata["palette"])
    source.source_origin = tuple(metadata["origin"])
    data = read_json(path / "patch.json")
    original = Path(metadata["source"]) if metadata["source"] else None
    if metadata["kind"] == "world":
        info = metadata["world"]
        world = SimpleNamespace(path=original, name=info["world_name"], dimensions=dict.fromkeys(info["dimensions"]))
        region = WorldRegion(source, frozenset(map(tuple, data["loaded"])), frozenset(), (), info["dimension"],
                             tuple(info["center"]), info["radius"], info["vertical_radius"],
                             sections=frozenset(map(tuple, data["sections"])) if data["sections"] is not None else None)
        session = WorldView(world, region)
        session._base_entities = {key: entity(value) for key, value in data["base_entities"].items()}
        session.world_changes.patch = unpack_patch(data["blocks"])
        session.world_changes.entities = unpack_patch(data["entities_patch"], entity)
        session._sync_changes()
    else:
        native = Schematic(path / "native.schem") if (path / "native.schem").is_file() else None
        session = EditSession(Document(source, path=original, native=native))
        session._cells = {tuple(point): cell(value) for point, value in data["cells"]}
        session._entities = {key: entity(value) for key, value in data["entities"].items()}
        session._saved_changes = SavedChanges(tuple(metadata["saved_origin"]), tuple(metadata["saved_size"]),
                                             unpack_patch(data["blocks"]), unpack_patch(data["entities_patch"], entity))
        if original and original.is_file() and digest(original) == metadata.get("source_hash"):
            session.save_target = Path(metadata["target"]) if metadata.get("target") else None
        elif original:
            session.save_target = None
            session.requires_save_as = True
            session.notices = ("Source changed or is missing; choose a new Save as path.",)
    session.recovery_notice = metadata["history"] + " · " + metadata["updated"]
    session._document.source_hash = metadata.get("source_hash")
    session.snapshot().validate()
    return session


def list_drafts(root=None):
    return list_bundles(root or draft_root())
