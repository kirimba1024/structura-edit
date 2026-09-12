from contextlib import closing
from itertools import product
import json
from pathlib import Path
import sqlite3

from .overview_store import OVERVIEW_VERSION, OverviewStore
from .overview_maps import MAP_MIN_LEVEL


GEOMETRY_VERSION = 7


class OverviewReuse:
    def __init__(self, store, directory):
        self.store = store
        self.nodes = {}
        self.changed = set()
        self.dirty_meshes = set()
        self.dirty_maps = set()
        self.dirty_columns = set()
        self.warnings = ()
        self.maps = False
        try:
            filename = json.loads((Path(directory) / "current.json").read_text())["file"]
            if Path(filename).name != filename:
                return
            path = Path(directory) / filename
            with closing(OverviewStore(path)) as previous:
                old, current = previous.metadata(), store.metadata()
                fields = ("world", "dimension", "assets", "resources", "height")
                if (not old.get("complete") or old.get("geometry_version", old.get("version")) != GEOMETRY_VERSION
                        or any(old.get(key) != current.get(key) for key in fields)):
                    return
                self.nodes = previous.nodes()
                self.maps = old.get("version") == OVERVIEW_VERSION and old.get("below_y") == current.get("below_y")
            store.db.execute("ATTACH DATABASE ? AS previous", (path.resolve().as_uri() + "?mode=ro",))
            store.db.execute("INSERT INTO textures SELECT * FROM previous.textures")
            rows = store.db.execute("""
                SELECT x,y,z FROM blocks AS current LEFT JOIN previous.blocks AS old USING(x,y,z)
                WHERE old.data IS NULL OR current.palette != old.palette OR current.data != old.data OR current.nbt IS NOT old.nbt
                UNION
                SELECT x,y,z FROM previous.blocks AS old LEFT JOIN blocks AS current USING(x,y,z) WHERE current.data IS NULL
            """)
            self.changed = set(map(tuple, rows))
            self.warnings = old.get("warnings", ())
            positions = {tuple(p + d for p, d in zip(position, offset)) for position in self.changed
                         for offset in product((-1, 0, 1), repeat=3)}
            for level in range(max((key[0] for key in self.nodes), default=0) + 1):
                self.dirty_meshes.update((level, *position) for position in positions)
                positions = {tuple(p // 2 for p in position) for position in positions}
            columns = {(x, z) for x, _, z in self.changed}
            columns.update(set(store.db.execute("SELECT x,z FROM columns")) ^ set(store.db.execute("SELECT x,z FROM previous.columns")))
            self.dirty_columns = {(x + dx, z + dz) for x, z in columns for dx, dz in product((0, 1), repeat=2)}
            positions = {(x * 2 + dx, z * 2 + dz) for x, z in self.dirty_columns for dx, dz in product((0, 1), repeat=2)}
            for level in range(MAP_MIN_LEVEL, old["map_level"] + 1):
                self.dirty_maps.update((level, *position) for position in positions)
                positions = {(x // 2, z // 2) for x, z in positions}
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
            self.nodes = {}
            self.maps = False

    def mesh(self, key, children=()):
        node = self.nodes.get(key)
        if node is None or node.children != tuple(children) or key in self.dirty_meshes:
            return None
        self.store.db.execute("INSERT INTO meshes SELECT * FROM previous.meshes WHERE key=?", (json.dumps(key),))
        return node

    def map(self, key):
        if not self.maps or key in self.dirty_maps:
            return False
        old = self.store.db.execute("SELECT image FROM previous.maps WHERE level=? AND x=? AND z=?", key).fetchone()
        if old is None:
            return False
        self.store.db.execute("INSERT INTO maps VALUES (?,?,?,?)", (*key, old[0]))
        return True

    def column(self, cx, cz):
        if not self.maps or (cx, cz) in self.dirty_columns:
            return False
        count = self.store.db.execute("SELECT COUNT(*) FROM previous.maps WHERE level=? AND x BETWEEN ? AND ? AND z BETWEEN ? AND ?",
                                      (MAP_MIN_LEVEL, cx * 2, cx * 2 + 1, cz * 2, cz * 2 + 1)).fetchone()[0]
        surface = self.store.db.execute("SELECT data FROM previous.surfaces WHERE x=? AND z=?", (cx, cz)).fetchone()
        if count != 4 or surface is None:
            return False
        for dx, dz in product(range(2), repeat=2):
            self.map((MAP_MIN_LEVEL, cx * 2 + dx, cz * 2 + dz))
        self.store.db.execute("INSERT INTO surfaces VALUES (?,?,?)", (cx, cz, surface[0]))
        return True
