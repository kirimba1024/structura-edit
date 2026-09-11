import warnings
from time import perf_counter

import numpy as np

from .loading import MAX_GEOMETRY_BYTES, check_preview_budget, geometry_bytes
from .resources import texture_bank
from .section_cache import SectionCache


_sections = SectionCache()


def build_preview(session, change=None, assets=None, include_entities=True):
    check_preview_budget(session.size)
    source = session._render_source(change, include_entities=include_entities)
    return build_geometry(source, assets)


def build_geometry(source, assets=None, emit_bounds=None, *, bank=None):
    from structura_render.mesh import build_textured_geometry, flat_block_groups, flat_entity_groups, voxel_state

    start = perf_counter()
    with warnings.catch_warnings(record=True) as notices:
        warnings.simplefilter("always")
        state, solid, names, properties = voxel_state(source)
        emit_mask = getattr(source, "emit_mask", None)
        bank = bank if bank is not None else texture_bank(assets)
        textured = bank.available()
        meshes, entities, indices, occluder = [], [], set(), solid
        if textured:
            meshes, entities, indices, occluder = build_textured_geometry(
                source, solid, state, names, properties, bank, emit_bounds=emit_bounds, emit_mask=emit_mask)
        flat = []
        groups = flat_block_groups(state, names, indices, occluder, emit_bounds=emit_bounds, emit_mask=emit_mask)
        if not textured:
            with bank.context.activate():
                groups.extend(flat_entity_groups(source))
        for color, points, faces in groups:
            quads = np.asarray(faces, dtype=np.int64)
            vtk_faces = np.column_stack((np.full(len(quads), 4), quads)).ravel()
            flat.append((np.asarray(points, dtype=np.float32), vtk_faces, color))
        flat.extend((points, faces, (*color, alpha)) for points, faces, color, alpha in entities)
    result = {
        "meshes": meshes, "flat": flat, "textured": textured,
        "seconds": perf_counter() - start,
        "warnings": list(dict.fromkeys(str(w.message) for w in notices)),
    }
    result["geometry_bytes"] = geometry_bytes(result)
    if result["geometry_bytes"] > MAX_GEOMETRY_BYTES:
        raise ValueError("Scene geometry exceeds 192 MiB; reduce the loaded area or schematic size")
    return result


def build_sections(sections, *, reset, assets=None, ghosts=None, progress=None):
    start = perf_counter()
    results, notices = {}, []
    total = 0
    for index, (key, (source, origin, bounds)) in enumerate(sections.items()):
        signature = _sections.key(source, origin, bounds, texture_bank(assets)) if not ghosts else None
        cached = _sections.get(signature) if signature is not None else None
        if cached is not None:
            results[key] = cached
            notices.extend(cached["warnings"])
            total += cached["geometry_bytes"]
            if total > MAX_GEOMETRY_BYTES:
                raise ValueError("Scene geometry exceeds 192 MiB; reduce the loaded area or schematic size")
            if progress:
                progress("Sections", index + 1, len(sections))
            continue
        data = build_geometry(source, assets, bounds)
        if hasattr(source, "entity_keys"):
            from .entity_picking import entity_bounds

            data["entity_bounds"] = entity_bounds(source.entities, source.entity_keys, texture_bank(assets))
            data["entity_markers"] = [(tuple(float(v) for v in record["pos"]), str(record["nbt"].get("id", "")) == "minecraft:player")
                                      for record in source.entities]
        data["layers"] = {name: build_geometry(layer, assets, bounds)
                          for name, layer in zip(("added", "removed"), (ghosts or {}).get(key, ()))
                          if layer is not None and layer.present}
        layers = [data, *data["layers"].values()]
        for layer in layers:
            for mesh in layer["meshes"]:
                mesh.points += origin
            for points, faces, color in layer["flat"]:
                points += origin
            notices.extend(layer["warnings"])
            total += layer["geometry_bytes"]
        data["geometry_bytes"] = sum(layer["geometry_bytes"] for layer in layers)
        data["signature"] = signature
        if signature is not None:
            _sections.put(signature, data)
        results[key] = data
        if total > MAX_GEOMETRY_BYTES:
            raise ValueError("Scene geometry exceeds 192 MiB; reduce the loaded area or schematic size")
        if progress:
            progress("Sections", index + 1, len(sections))
    return dict(sections=results, reset=reset, geometry_bytes=total,
                textured=texture_bank(assets).available(), seconds=perf_counter() - start,
                warnings=list(dict.fromkeys(notices)))
