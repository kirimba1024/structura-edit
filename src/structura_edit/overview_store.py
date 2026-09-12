from contextlib import closing
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import zlib

import numpy as np
from PIL import Image
from amulet_nbt import CompoundTag, IntTag, ListTag, NamedTag

from structura_core.block_array import BlockArray
from structura_core.blockstates import parse_state
from structura_core.nbt_io import read_root
from structura_render.geometry import TexturedMesh
from structura_render.lod_geometry import LodMesh

from .overview_model import OverviewNode, TILE_SPAN
from .array_codec import encode_arrays as encode_arrays


OVERVIEW_VERSION = 6
MAX_SNAPSHOT_BYTES = 8 * 1024**3
MAP_SPAN = 128


def decode_arrays(data):
    with np.load(BytesIO(data), allow_pickle=False) as archive:
        return {name: archive[name] for name in archive.files}


def encode_image(array):
    stream = BytesIO()
    Image.fromarray(array).save(stream, format="PNG")
    return stream.getvalue()


def decode_image(data):
    with Image.open(BytesIO(data)) as image:
        return np.array(image.convert("RGBA"))


def texture_identity(image):
    return sha256(repr(image.shape).encode() + image.tobytes()).hexdigest()


def snapshot_directory(root, world, dimension):
    identity = json.dumps((str(Path(world).resolve()), dimension)).encode()
    return Path(root) / "overviews" / sha256(identity).hexdigest()


class OverviewStore:
    def __init__(self, path, *, create=False):
        self.path = Path(path).expanduser().resolve()
        self.db = sqlite3.connect(str(self.path) if create else self.path.as_uri() + "?mode=ro", uri=not create)
        if create:
            self.db.executescript("""
                PRAGMA page_size=4096;
                CREATE TABLE metadata (name TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE columns (x INTEGER, z INTEGER, PRIMARY KEY(x,z));
                CREATE TABLE blocks (x INTEGER, y INTEGER, z INTEGER, palette TEXT, data BLOB, nbt BLOB, PRIMARY KEY(x,y,z));
                CREATE TABLE textures (id TEXT PRIMARY KEY, data BLOB, bytes INTEGER);
                CREATE TABLE meshes (key TEXT PRIMARY KEY, children TEXT, error REAL, bytes INTEGER, data BLOB);
                CREATE TABLE maps (level INTEGER, x INTEGER, z INTEGER, image BLOB, PRIMARY KEY(level,x,z));
                CREATE TABLE surfaces (x INTEGER, z INTEGER, data BLOB, PRIMARY KEY(x,z));
            """)
            self.db.execute(f"PRAGMA max_page_count={MAX_SNAPSHOT_BYTES // 4096}")

    def close(self):
        self.db.close()

    def metadata(self):
        return {key: json.loads(value) for key, value in self.db.execute("SELECT name,value FROM metadata")}

    def set_metadata(self, **values):
        self.db.executemany("INSERT OR REPLACE INTO metadata VALUES (?,?)",
                            ((key, json.dumps(value)) for key, value in values.items()))

    def add_section(self, section):
        payload = NamedTag(CompoundTag({"entities": ListTag(section.block_entities)})).save_to() if section.block_entities else None
        self.db.execute("INSERT INTO blocks VALUES (?,?,?,?,?,?)",
                        (*section.position, json.dumps(section.palette), zlib.compress(section.blocks.tobytes(), 1), payload))

    def read_region(self, lower, upper):
        palette, indices, block_nbt = [], {}, {}
        blocks = BlockArray.empty(tuple(hi - lo for lo, hi in zip(lower, upper)))
        ranges = tuple((lo // TILE_SPAN, (hi - 1) // TILE_SPAN) for lo, hi in zip(lower, upper))
        rows = self.db.execute("SELECT x,y,z,palette,data,nbt FROM blocks WHERE x BETWEEN ? AND ? "
                               "AND y BETWEEN ? AND ? AND z BETWEEN ? AND ? ORDER BY x,y,z",
                               tuple(value for limits in ranges for value in limits))
        for x, y, z, states, data, nbt in rows:
            remap = []
            for state in json.loads(states):
                if state not in indices:
                    indices[state] = len(palette)
                    palette.append(parse_state(state))
                remap.append(indices[state])
            raw = np.frombuffer(zlib.decompress(data), np.int32).reshape((TILE_SPAN,) * 3)
            mapping = np.asarray([*remap, -1], np.int32)
            origin = tuple(p * TILE_SPAN for p in (x, y, z))
            start = tuple(max(a, b) for a, b in zip(lower, origin))
            stop = tuple(min(a, b + TILE_SPAN) for a, b in zip(upper, origin))
            crop = tuple(slice(a - b, c - b) for a, b, c in zip(start, origin, stop))
            blocks.set_region(tuple(a - b for a, b in zip(start, lower)), mapping[raw[crop]])
            if nbt is not None:
                for payload in read_root(nbt)["entities"]:
                    position = tuple(int(payload[axis]) - lo for axis, lo in zip("xyz", lower))
                    if position in blocks:
                        value = deepcopy(payload)
                        value.update((axis, IntTag(p)) for axis, p in zip("xyz", position))
                        block_nbt[position] = value
        return SimpleNamespace(size=blocks.array.shape, palette_raw=palette,
                               palette=[str(entry["Name"]) for entry in palette], present=blocks,
                               block_nbt=block_nbt, entities=[])

    def put_mesh(self, node, geometry, lod):
        arrays = dict(lod_points=lod.points, lod_triangles=lod.triangles, lod_colors=lod.colors)
        textures = []
        for index, mesh in enumerate(geometry.get("meshes", ())):
            image = mesh.image
            identity = texture_identity(image)
            self.db.execute("INSERT OR IGNORE INTO textures VALUES (?,?,?)", (identity, encode_image(image), image.nbytes))
            textures.append(identity)
            for name in ("points", "quads", "uv", "alpha_modes"):
                arrays[f"mesh_{index}_{name}"] = getattr(mesh, name)
        arrays["textures"] = np.asarray(textures, dtype="U64")
        for index, (points, faces, color) in enumerate(geometry.get("flat", ())):
            arrays[f"flat_{index}_points"] = points
            arrays[f"flat_{index}_faces"] = faces
            arrays[f"flat_{index}_color"] = np.asarray(color, np.uint8)
        self.db.execute("INSERT INTO meshes VALUES (?,?,?,?,?)", (
            json.dumps(node.key), json.dumps(node.children), node.error, node.nbytes, encode_arrays(**arrays)))

    def nodes(self):
        return {tuple(json.loads(key)): OverviewNode(tuple(json.loads(key)), tuple(map(tuple, json.loads(children))), error, size)
                for key, children, error, size in self.db.execute("SELECT key,children,error,bytes FROM meshes")}

    def read_lod(self, key):
        row = self.db.execute("SELECT data FROM meshes WHERE key=?", (json.dumps(key),)).fetchone()
        arrays = decode_arrays(row[0])
        return LodMesh(arrays["lod_points"], arrays["lod_triangles"], arrays["lod_colors"])

    def read_mesh(self, key, textures):
        row = self.db.execute("SELECT data FROM meshes WHERE key=?", (json.dumps(key),)).fetchone()
        if row is None:
            raise ValueError("Overview tile is missing; refresh the overview")
        arrays = decode_arrays(row[0])
        if key[0] or not len(arrays['textures']) and 'flat_0_points' not in arrays:
            return dict(lod=LodMesh(arrays["lod_points"], arrays["lod_triangles"], arrays["lod_colors"]))
        meshes = []
        for index, identity in enumerate(arrays["textures"]):
            if identity not in textures:
                data = self.db.execute("SELECT data FROM textures WHERE id=?", (str(identity),)).fetchone()
                textures[identity] = decode_image(data[0])
            mesh = TexturedMesh(*(arrays[f"mesh_{index}_{name}"] for name in ("points", "quads", "uv", "alpha_modes")),
                                textures[identity])
            mesh.texture_key = str(identity)
            meshes.append(mesh)
        flat = []
        while f"flat_{len(flat)}_points" in arrays:
            index = len(flat)
            flat.append((arrays[f"flat_{index}_points"], arrays[f"flat_{index}_faces"], tuple(arrays[f"flat_{index}_color"])))
        return dict(meshes=meshes, flat=flat)

    def read_map(self, key):
        row = self.db.execute("SELECT image FROM maps WHERE level=? AND x=? AND z=?", key).fetchone()
        return decode_image(row[0]) if row else None


def load_manifest(path):
    with closing(OverviewStore(path)) as store:
        metadata = store.metadata()
        if metadata.get("version") != OVERVIEW_VERSION or not metadata.get("complete"):
            raise ValueError("Overview is incomplete or outdated; refresh it")
        nodes = store.nodes()
        maps = {tuple(row[:3]): decode_image(row[3]) for row in store.db.execute(
            "SELECT level,x,z,image FROM maps WHERE level=?", (metadata["map_level"],))}
    parents = {child for node in nodes.values() for child in node.children}
    return dict(path=str(path), metadata=metadata, nodes=nodes, roots=tuple(sorted(nodes.keys() - parents)), maps=maps)


def read_meshes(path, keys):
    with closing(OverviewStore(path)) as store:
        textures = {}
        return {key: store.read_mesh(key, textures) for key in keys}


def surface_destination(path, position):
    from .overview_maps import EMPTY_HEIGHT

    x, z = position
    with closing(OverviewStore(path)) as store:
        row = store.db.execute("SELECT data FROM surfaces WHERE x=? AND z=?", (x // 16, z // 16)).fetchone()
        if row is None:
            raise ValueError("This location is outside the prepared overview")
        height = int(decode_arrays(row[0])["height"][x % 16, z % 16])
        if height == EMPTY_HEIGHT:
            raise ValueError("This location has no surface; use Go to coordinates")
        source = store.read_region((x, height, z), (x + 1, height + 4, z + 1))
        from .height_slice import HeightSlice

        clip_overview_source(source, height, HeightSlice(**store.metadata()["height"]))
        if source.present:
            raise ValueError("There is no clear viewpoint above this map surface; use Go to coordinates")
        return x + 0.5, height + 3.0, z + 0.5


def clip_overview_source(source, origin_y, height):
    if height.mode == "all":
        return
    count = source.size[1]
    lower = max(0, min(count, height.y - origin_y)) if height.mode == "layer" else 0
    upper = max(0, min(count, height.y + 1 - origin_y))
    source.present.array[:, :lower, :] = -1
    source.present.array[:, upper:, :] = -1
    source.present = BlockArray(source.present.array)
    source.block_nbt = {position: nbt for position, nbt in source.block_nbt.items() if lower <= position[1] < upper}
