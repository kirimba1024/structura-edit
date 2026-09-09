from collections import Counter
from copy import copy
from dataclasses import replace

from structura_core import state_key

from .cell_data import detached_cell
from .changes import ChangeSet, _Cell, _Delta
from .document import Document
from .session import EditSession
from .world_changes import WorldChanges
from .world_object_changes import loaded_entities, visible_entities, portable_entities, entity_patches


AIR_CELL = _Cell("minecraft:air")


class WorldView(EditSession):
    def __init__(self, world, region, changes=None):
        super().__init__(Document(region.structure, path=world.path, readonly=region.structure.data_version < 2844))
        self.dimension = region.dimension
        self.center = region.center
        self.radius = region.radius
        self.vertical_radius = region.vertical_radius
        self.loaded_chunks = region.loaded
        self.loaded_sections = region.sections
        self.missing_chunks = region.missing
        self.notices = region.notices
        self.dimensions = tuple(world.dimensions)
        self.world_name = world.name
        self._base_entities = loaded_entities(self, region.entity_locations)
        self.world_changes = changes or WorldChanges(self._id, self.history)
        self._sync_changes()

    @property
    def dirty(self):
        return bool(self.world_changes.patch or self.world_changes.entities)

    def _cell(self, position):
        return super()._cell(position) or AIR_CELL

    def _sync_changes(self):
        state = self.world_changes
        self._id, self.revision, self._state_id = state.document_id, state.revision, state.state_id
        self.history = state.history
        self._transition = None
        self._cells = {}
        self._entities = visible_entities(self)
        for (dimension, x, y, z), (_, after) in state.patch.items():
            position = tuple(p - o for p, o in zip((x, y, z), self.origin))
            if dimension == self.dimension and all(0 <= p < s for p, s in zip(position, self.size)):
                self._cells[position] = after

    def _check_change(self, change):
        super()._check_change(change)
        for delta in change.entities:
            if delta.after is not None:
                position = delta.after.unpack()["pos"]
                x, _, z = (float(p) + o for p, o in zip(position, self.origin))
                if (int(x // 16), int(z // 16)) not in self.loaded_chunks:
                    raise ValueError("Entity destination includes absent chunks; select a loaded area")

    def _check_destination(self, position):
        x, y, z = (p + o for p, o in zip(position, self.origin))
        if (x // 16, z // 16) not in self.loaded_chunks:
            raise ValueError("Placement includes absent chunks; select a loaded area")
        if self.loaded_sections is not None and (x // 16, y // 16, z // 16) not in self.loaded_sections:
            raise ValueError("Placement includes an absent section; stay within the world's existing build height")

    def _portable(self, cell, position):
        cell = detached_cell(self._document.source, cell or AIR_CELL, position)
        return replace(cell, origin=None, variant=None, keep_nbt=bool(cell.data and cell.data.nbt))

    def apply(self, change):
        if self.readonly:
            raise ValueError("Editing worlds requires Java 1.18 or newer")
        self._check_change(change)
        changes = tuple(_Delta((self.dimension, *(p + o for p, o in zip(delta.position, self.origin))),
                               self._portable(delta.before, delta.position), self._portable(delta.after, delta.position))
                        for delta in change.changes)
        changes = tuple(delta for delta in changes if delta.before != delta.after)
        result = self.world_changes.apply(ChangeSet(self._id, self.revision, change.label, changes,
                                                     portable_entities(self, change.entities)))
        self._sync_changes()
        return result

    def _step_history(self, *, undo):
        result = self.world_changes.step(undo=undo)
        self._sync_changes()
        return result

    def fork(self):
        branch = copy(self)
        branch.world_changes = self.world_changes.fork()
        branch._sync_changes()
        return branch

    def save(self, path=None):
        from pathlib import Path
        from structura_core.world_write import save_world_patch

        if self.readonly:
            raise ValueError("Editing worlds requires Java 1.18 or newer")
        if path is not None and Path(path).resolve() != self.path.resolve():
            raise ValueError("Use Export selection for a schematic; Save world writes to the opened world")
        snapshot = self.snapshot()
        patch = {position: tuple((cell.state, cell.data.nbt if cell.keep_nbt and cell.data else None) for cell in pair)
                 for position, pair in self.world_changes.patch.items()}
        self.last_backup = save_world_patch(self.path, patch, entities=entity_patches(self.world_changes))
        self._document = Document(snapshot, path=self.path)
        self._states = tuple(state_key(p) for p in snapshot.palette_raw)
        self._base_counts = Counter(snapshot.present.values())
        self._base_entities = self._entities.copy()
        self.world_changes.patch.clear()
        self.world_changes.entities.clear()
        if hasattr(self, "map_stamps"):
            from .file_state import fingerprint

            self.map_stamps = {path: fingerprint(path) for path in self.map_stamps}
        self._sync_changes()
        return self.path

    def _check_readable(self, selection):
        super()._check_readable(selection)
        lower = tuple(p + o for p, o in zip(selection.lower, self.origin))
        upper = tuple(p + o - 1 for p, o in zip(selection.upper, self.origin))
        requested = {(x, z) for x in range(lower[0] // 16, upper[0] // 16 + 1)
                     for z in range(lower[2] // 16, upper[2] // 16 + 1)}
        if not requested <= self.loaded_chunks:
            raise ValueError("Selection contains chunks absent from the save; load a complete region before copying or exporting")
