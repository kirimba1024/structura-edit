import warnings
from time import perf_counter

import numpy as np

from .loading import MAX_COLUMN_CELLS, MAX_GEOMETRY_BYTES, check_preview_budget, geometry_bytes
from .resources import texture_bank
from .section_cache import SectionCache
from .render_packets import prepare_geometry


_sections = SectionCache()
_disk = None


def build_preview(session, change=None, assets=None, include_entities=True):
    check_preview_budget(session.size, world=hasattr(session, "dimension"))
    source = session._render_source(change, include_entities=include_entities)
    return prepare_geometry(build_geometry(source, assets))


def build_geometry(source, assets=None, emit_bounds=None, *, bank=None):
    from structura_render.mesh import build_textured_geometry, flat_block_groups, flat_entity_groups, voxel_state

    start = perf_counter()
    with warnings.catch_warnings(record=True) as notices:
        warnings.simplefilter("always")
        state, solid, names, properties = voxel_state(source, **({"max_voxels": MAX_COLUMN_CELLS} if getattr(source, "world", False) else {}))
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
    from .geometry_cache import GeometryCache

    global _disk
    bank = texture_bank(assets)
    if _disk is None or _disk[0] is not bank:
        _disk = bank, GeometryCache(bank)
    start = perf_counter()
    results, notices = {}, []
    total = 0
    for index, (key, (source, origin, bounds)) in enumerate(sections.items()):
        signature = _sections.key(source, bounds, bank) if not ghosts else None
        cached = _sections.get(signature) if signature is not None else None
        persistent = signature is not None and not hasattr(source, "entity_keys")
        if cached is None and persistent:
            cached = _disk[1].get(signature)
            if cached is not None:
                cached = prepare_geometry(cached)
                _sections.put(signature, cached)
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
            from .map_entities import entity_markers

            data["entity_markers"] = entity_markers(source.entities, assets)
            data["entity_marker_keys"] = source.entity_keys
        data["layers"] = {name: build_geometry(layer, assets, bounds)
                          for name, layer in zip(("added", "removed"), (ghosts or {}).get(key, ()))
                          if layer is not None and layer.present}
        layers = [data, *data["layers"].values()]
        for layer in layers:
            notices.extend(layer["warnings"])
            total += layer["geometry_bytes"]
        data["geometry_bytes"] = sum(layer["geometry_bytes"] for layer in layers)
        data["signature"] = signature
        if persistent:
            _disk[1].put(signature, data)
        data = prepare_geometry(data, position=origin)
        if signature is not None:
            _sections.put(signature, data)
        results[key] = data
        if total > MAX_GEOMETRY_BYTES:
            raise ValueError("Scene geometry exceeds 192 MiB; reduce the loaded area or schematic size")
        if progress:
            progress("Sections", index + 1, len(sections))
    prepared = {key: dict(data, position=sections[key][1]) for key, data in results.items()}
    for data in prepared.values():
        if data.get('signature') is not None:
            data['signature'] = data['signature'], data['position']
    return dict(sections=prepared, reset=reset, geometry_bytes=sum(data['geometry_bytes'] for data in prepared.values()),
                textured=texture_bank(assets).available(), seconds=perf_counter() - start,
                warnings=list(dict.fromkeys(notices)))
