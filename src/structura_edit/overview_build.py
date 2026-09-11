from contextlib import closing
from dataclasses import asdict, replace
from pathlib import Path
from time import time
from uuid import uuid4
import json
import zlib

import numpy as np
from amulet_nbt import IntTag, from_snbt

from structura_core.world import JavaWorld
from structura_core.world_terrain import existing_chunks, terrain_sections, terrain_stamp
from structura_render.lod_geometry import colored_geometry, merge_lods, simplify_lod

from .file_state import resource_stamp
from .height_slice import HeightSlice
from .overview_maps import build_map_pyramid
from .overview_model import OverviewNode, parent_key, tile_bounds
from .overview_store import OVERVIEW_VERSION, OverviewStore, clip_overview_source, load_manifest
from .preview import build_geometry
from .resources import resolve_assets, texture_bank
from .overview_cache import snapshot_build_slot


MAX_OVERVIEW_NODES = 200_000
MAX_BUILD_GEOMETRY = 192 * 1024**2


def patch_section(section, edits):
    if not edits:
        return section
    palette = list(section.palette)
    indices = {state: index for index, state in enumerate(palette)}
    blocks = section.blocks.copy()
    entities = {tuple(int(payload[axis]) for axis in "xyz"): payload for payload in section.block_entities}
    for position, cell in edits:
        state = cell.state
        if state not in indices:
            indices[state] = len(palette)
            palette.append(state)
        blocks[tuple(p % 16 for p in position)] = -1 if state in ("minecraft:air", "minecraft:cave_air", "minecraft:void_air") else indices[state]
        entities.pop(position, None)
        if cell.keep_nbt and cell.data is not None and cell.data.nbt:
            payload = from_snbt(cell.data.nbt)
            payload.update((axis, IntTag(value)) for axis, value in zip("xyz", position))
            entities[position] = payload
    return replace(section, palette=tuple(palette), blocks=blocks, block_entities=tuple(entities.values()))


def build_overview(path, dimension, directory, *, assets=None, progress=None, chunks=None, below_y=None,
                   edits=None, document_id=None, revision=None, height=HeightSlice()):
    with snapshot_build_slot(directory) as disk_budget:
        return _build_snapshot(path, dimension, directory, assets=assets, progress=progress, chunks=chunks,
                               below_y=below_y, edits=edits, document_id=document_id, revision=revision,
                               height=height, disk_budget=disk_budget)


def _build_snapshot(path, dimension, directory, *, assets, progress, chunks, below_y,
                    edits, document_id, revision, height, disk_budget):
    import meshoptimizer

    if not hasattr(meshoptimizer, "simplify_with_attributes"):
        raise RuntimeError("Mesh simplification is unavailable")
    progress = progress or (lambda *args: None)
    world = JavaWorld(path)
    region = world.dimensions[dimension] / "region"
    initial_stamp = terrain_stamp(region)
    columns = existing_chunks(region) if chunks is None else tuple(sorted(chunks))
    if not columns:
        raise ValueError("This dimension has no saved chunks")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / (uuid4().hex + ".sqlite")
    assets_option = str(Path(assets).expanduser().resolve()) if assets else None
    assets = resolve_assets(assets)
    resources = resource_stamp(assets)
    changes = {}
    for (space, x, y, z), (_, after) in (edits or {}).items():
        if space == dimension:
            changes.setdefault((x // 16, y // 16, z // 16), []).append(((x, y, z), after))
    try:
        with closing(OverviewStore(destination, create=True)) as store:
            store.db.execute(f"PRAGMA max_page_count={disk_budget // 4096}")
            store.set_metadata(version=OVERVIEW_VERSION, complete=False, world=str(world.path), dimension=dimension,
                               created=time(), assets=str(assets), resources=resources, below_y=below_y,
                               name=world.name, chunks=len(columns), document_id=document_id, revision=revision,
                               height=asdict(height), assets_option=assets_option, volatile=bool(edits))
            for done, (cx, cz) in enumerate(columns, 1):
                store.db.execute("INSERT INTO columns VALUES (?,?)", (cx, cz))
                for section in terrain_sections(region, cx, cz, world.data_version):
                    store.add_section(patch_section(section, changes.pop(section.position, ())))
                progress("Reading chunks", done, len(columns))
                if done % 64 == 0:
                    store.db.commit()
            if changes:
                raise ValueError("Edited sections are absent from this snapshot; load them again before refreshing the overview")
            keys = [tuple(row) for row in store.db.execute("SELECT x,y,z FROM blocks ORDER BY x,y,z")]
            if len(keys) > MAX_OVERVIEW_NODES:
                raise ValueError("This overview exceeds the tile index budget")
            if not keys:
                raise ValueError("The saved chunks contain no supported block sections")
            lower = tuple(min(key[axis] for key in keys) * 16 for axis in range(3))
            upper = tuple((max(key[axis] for key in keys) + 1) * 16 for axis in range(3))
            nodes, notices = {}, set()
            occupied = [tuple(row[:3]) for row in store.db.execute("SELECT x,y,z,data FROM blocks ORDER BY x,y,z")
                        if np.any(np.frombuffer(zlib.decompress(row[3]), np.int32) >= 0)]
            for done, key in enumerate(occupied, 1):
                origin = tuple(value * 16 for value in key)
                source = store.read_region(tuple(v - 1 for v in origin), tuple(v + 17 for v in origin))
                clip_overview_source(source, origin[1] - 1, height)
                if not np.any(source.present.array[1:17, 1:17, 1:17] >= 0):
                    progress("Building detail", done, len(occupied))
                    continue
                geometry = build_geometry(source, assets, ((1, 1, 1), (17, 17, 17)))
                if len(notices) < 32:
                    notices.update(geometry["warnings"][:32 - len(notices)])
                for mesh in geometry["meshes"]:
                    mesh.points -= 1
                for points, _, _ in geometry["flat"]:
                    points -= 1
                lod = colored_geometry(geometry["meshes"], geometry["flat"])
                if len(lod.triangles):
                    node = OverviewNode((0, *key), (), 0.0, geometry["geometry_bytes"])
                    nodes[node.key] = node
                    store.put_mesh(node, geometry, lod)
                progress("Building detail", done, len(occupied))
                if done % 64 == 0:
                    store.db.commit()
            maximum = max(1, ((max(hi - lo for lo, hi in zip(lower, upper)) // 16) - 1).bit_length())
            children = set(nodes)
            for level in range(1, maximum + 1):
                groups = {}
                for child in sorted(children):
                    groups.setdefault(parent_key(child), []).append(child)
                parents = set()
                for done, (key, keys) in enumerate(sorted(groups.items()), 1):
                    origin, _ = tile_bounds(key)
                    parts, size = [], 0
                    for child in keys:
                        lod = store.read_lod(child)
                        size += lod.nbytes
                        if size > MAX_BUILD_GEOMETRY:
                            raise ValueError("A distant tile exceeds the build memory budget")
                        child_origin, _ = tile_bounds(child)
                        parts.append((lod, tuple(p - o for p, o in zip(child_origin, origin))))
                    lod, error = simplify_lod(merge_lods(parts), 16 * 2**level, error=max(0.5, 2**(level - 2)))
                    error += max(nodes[child].error for child in keys) + (2.0 if level == 1 else 0.0)
                    node = OverviewNode(key, tuple(keys), error, lod.nbytes)
                    nodes[key] = node
                    if len(nodes) > MAX_OVERVIEW_NODES:
                        raise ValueError("This overview exceeds the tile index budget")
                    store.put_mesh(node, {}, lod)
                    parents.add(key)
                    progress(f"Building distance {level}/{maximum}", done, len(groups))
                children = parents
                store.db.commit()
            map_level = build_map_pyramid(store, columns, texture_bank(assets), progress, below_y, height)
            if initial_stamp != terrain_stamp(region) or resources != resource_stamp(assets):
                raise ValueError("World or textures changed during preparation; refresh the overview")
            store.set_metadata(complete=True, bounds=(lower, upper), map_level=map_level, tiles=len(nodes), warnings=sorted(notices))
            store.db.commit()
        result = load_manifest(destination)
        temporary = directory / "current.json.tmp"
        temporary.write_text(json.dumps({"file": destination.name}), encoding="utf-8")
        temporary.replace(directory / "current.json")
        return result
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
