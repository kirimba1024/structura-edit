from collections import defaultdict
from contextlib import closing
from functools import lru_cache

import numpy as np

from structura_render.geometry import TexturedMesh
from structura_render.lod_geometry import merge_lods, split_lod
from structura_render.atlas import merge_mesh_atlases

from .overview_model import tile_bounds
from .overview_store import OverviewStore, texture_identity
from .render_packets import prepare_geometry


BATCH_LEVEL = 4
BATCH_BYTES = 8 * 1024**2


@lru_cache(maxsize=1)
def _snapshot(path):
    from .overview_store import load_manifest

    return load_manifest(path)


def select_batches(path, target):
    from .overview_model import select_detail

    snapshot = _snapshot(path)
    selected = select_detail(snapshot['nodes'], snapshot['roots'], target)
    return detail_batches(snapshot['nodes'], selected)


def detail_batches(nodes, selection):
    groups = defaultdict(list)
    for key in selection:
        level, *position = key
        shift = max(0, BATCH_LEVEL - level)
        groups[(max(level, BATCH_LEVEL), *(p // 2**shift for p in position))].append(key)
    result = {}
    for group, keys in sorted(groups.items()):
        batch, size = [], 0
        for key in sorted(keys):
            count = nodes[key].nbytes
            if batch and size + count > BATCH_BYTES:
                result[(group, tuple(batch))] = size
                batch, size = [], 0
            batch.append(key)
            size += count
        if batch:
            result[(group, tuple(batch))] = size
    return result


def read_batches(path, keys):
    with closing(OverviewStore(path)) as store:
        textures = {}
        return {key: read_batch(store, key, textures) for key in keys}


def read_batch(store, key, textures):
    group, tiles = key
    origin, _ = tile_bounds(group)
    lods, flat, textured = [], [], defaultdict(list)
    for tile in tiles:
        data = store.read_mesh(tile, textures)
        lower, _ = tile_bounds(tile)
        offset = np.asarray([a - b for a, b in zip(lower, origin)], np.float32)
        if "lod" in data:
            lods.append((data["lod"], offset))
        else:
            for mesh in data["meshes"]:
                textured[mesh.texture_key].append((mesh, offset))
            flat.extend((points + offset, faces, color) for points, faces, color in data["flat"])
    meshes = []
    for identity, parts in textured.items():
        points, quads, uv, modes = [], [], [], []
        count = 0
        for mesh, offset in parts:
            points.append(mesh.points + offset)
            quads.append(mesh.quads + count)
            uv.append(mesh.uv)
            modes.append(mesh.alpha_modes)
            count += len(mesh.points)
        merged = TexturedMesh(np.concatenate(points), np.concatenate(quads), np.concatenate(uv),
                              np.concatenate(modes), textures[identity])
        merged.texture_key = identity
        meshes.append(merged)
    meshes = merge_mesh_atlases(meshes)
    for mesh in meshes:
        mesh.texture_key = texture_identity(mesh.image)
    return prepare_geometry(dict(origin=origin, colored=split_lod(merge_lods(lods)), meshes=meshes, flat=flat))
