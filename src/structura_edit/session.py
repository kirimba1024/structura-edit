from collections import Counter
from contextlib import contextmanager
from copy import copy
from functools import lru_cache
from uuid import uuid4

from structura_core.nbt import parse_state, state_key

from .document import Document
from .history import DEFAULT_CACHE_BYTES, History
from .entity_data import initial_entities, write_entities
from .cell_set import CellSet
from .changes import ChangeSet, EntityDelta, Selection, StaleChangeError, _Cell, _Delta, _position
from .condition import Condition
from .mix import Mix
from .cell_data import material_data
from .saved_changes import SavedChanges


class EditSession:
    _missing_cell = None

    def __init__(self, document, *, history_cache_limit=500_000, history_cache_bytes=DEFAULT_CACHE_BYTES, operation_limit=500_000):
        if any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in (history_cache_limit, operation_limit)):
            raise ValueError("History and operation limits must be positive integers")
        self._document = document
        self._id = uuid4().hex
        self._states = tuple(state_key(p) for p in document.source.palette_raw)
        from structura_core.block_array import BlockArray

        blocks = document.source.present
        self._base_counts = Counter(blocks.counts() if isinstance(blocks, BlockArray) else blocks.values())
        self._cells = {}
        self._entities = initial_entities(document.source)
        self.history = History(history_cache_limit, cache_bytes=history_cache_bytes)
        self.operation_limit = operation_limit
        self.revision = 0
        self._state_id = uuid4().hex
        self._saved_state_id = self._state_id
        self._transition = None
        self._saved_changes = SavedChanges(self.origin, self.size)
        self.save_target = None
        self.requires_save_as = False

    @classmethod
    def open(cls, path, *, region=None, palette_index=0, source_data_version=None, target_version=None, strict=False, **limits):
        return cls(Document.open(path, region=region, palette_index=palette_index, source_data_version=source_data_version,
                                  target_version=target_version, strict=strict), **limits)

    @classmethod
    def from_structure(cls, structure, **limits):
        return cls(Document(structure), **limits)

    @property
    def size(self):
        return self._document.source.size

    @property
    def origin(self):
        return self._document.origin

    @property
    def path(self):
        return self._document.path

    @property
    def readonly(self):
        return self._document.readonly

    @property
    def dirty(self):
        return self._saved_changes.dirty(self)

    @property
    def can_undo(self):
        return self.history.cursor > 0

    @property
    def can_redo(self):
        return self.history.cursor < len(self.history.entries)

    def select(self, bounds=None):
        selection = Selection(*(bounds or ((0, 0, 0), self.size)))
        self._check_selection(selection)
        return selection

    def _check_selection(self, selection):
        if isinstance(selection, Selection):
            if any(v > s for v, s in zip(selection.upper, self.size)):
                raise ValueError("Selection is outside the document")
        elif isinstance(selection, CellSet):
            if selection and (any(v < 0 for v in selection.lower) or any(v > s for v, s in zip(selection.upper, self.size))):
                raise ValueError("Selection is outside the document")
        else:
            raise ValueError("Selection is outside the document")

    def _check_readable(self, selection):
        self._check_selection(selection)

    def _check_destination(self, position):
        return None

    def _original(self, position):
        index = self._document.source.present.get(position)
        if index is None:
            return None
        return _Cell(self._states[index], index, position in self._document.source.block_nbt, position)

    def _cell(self, position):
        cell = self._cells[position] if position in self._cells else self._original(position)
        return cell if cell is not None else self._missing_cell

    def _cell_matches(self, position, cell):
        if type(self)._cell is not EditSession._cell or type(self)._original is not EditSession._original:
            return self._cell(position) == cell
        if position in self._cells:
            current = self._cells[position]
            return (current if current is not None else self._missing_cell) == cell
        index = self._document.source.present.get(position)
        if index is None:
            return cell == self._missing_cell
        return (type(cell) is _Cell and cell.state == self._states[index] and cell.variant == index
                and cell.keep_nbt == (position in self._document.source.block_nbt)
                and cell.origin == position and cell.data is None)

    def _canonical_cell(self, position, cell):
        original = self._original(position)
        if original is None or cell.data is not None or cell.origin not in (None, position):
            return cell
        if cell.state != original.state or cell.keep_nbt != original.keep_nbt:
            return cell
        palettes = self._document.source.palettes_raw
        if all(state_key(p[original.variant]) == cell.state for p in palettes):
            return original
        return cell

    def state_at(self, position):
        position = _position(position)
        if any(v < 0 or v >= s for v, s in zip(position, self.size)):
            raise ValueError("Position is outside the document")
        cell = self._cell(position)
        return cell.state if cell else None

    def positions(self):
        yield from self._document.source.present
        yield from (p for p in self._cells if p not in self._document.source.present)

    def stored_positions(self, selection):
        self._check_selection(selection)
        base = self._document.source.present
        if selection.volume < len(base) + len(self._cells):
            yield from (p for p in selection.positions() if p in base or p in self._cells)
        else:
            yield from (p for p in self.positions() if p in selection)

    def find_objects(self, text="", **options):
        from .object_search import ObjectSearch

        return ObjectSearch().find(self, text, **options)

    def palette_counts(self, selection=None, *, by_state=True):
        if selection is not None:
            self._check_selection(selection)
        if selection is None or (isinstance(selection, Selection) and selection.lower == (0, 0, 0)
                                 and selection.upper == self.size):
            counts = Counter()
            for index, count in self._base_counts.items():
                counts[self._states[index]] += count
            for position, cell in self._cells.items():
                index = self._document.source.present.get(position)
                if index is not None:
                    counts[self._states[index]] -= 1
                counts[cell.state] += 1
        else:
            base = self._document.source.present
            positions = self.stored_positions(selection)
            counts = Counter(self._cells[p].state if p in self._cells else self._states[base[p]] for p in positions)
        if by_state:
            return +counts
        materials = Counter()
        for state, count in counts.items():
            materials[state.split("[", 1)[0]] += count
        return +materials

    def _change(self, positions, target, label):
        if self.readonly:
            raise ValueError("This source is view-only in this release")
        resolve = target if callable(target) else lambda position, before: target
        if isinstance(target, Mix):
            def resolve(position, before):
                return target.at(position, self.origin)
        canonical = lru_cache(maxsize=None)(lambda state: state_key(parse_state(state)))
        if not callable(target):
            canonical(target)
        changes = []
        for position in positions:
            before = self._cell(position)
            state = canonical(resolve(position, before))
            target_name = state.split("[", 1)[0]
            if before is not None and before.state == state:
                continue
            keep = bool(before and before.keep_nbt and before.state.split("[", 1)[0] == target_name)
            after = self._canonical_cell(position, _Cell(state, keep_nbt=keep, origin=before.origin if before else None,
                                                         data=material_data(before, keep)))
            changes.append(_Delta(position, before, after))
            if len(changes) > self.operation_limit:
                raise ValueError("Operation exceeds the changed-cell budget; select a smaller region")
        return ChangeSet(self._id, self.revision, label, tuple(changes))

    def fill(self, selection, target):
        self._check_selection(selection)
        if selection.volume > self.operation_limit:
            raise ValueError("Fill exceeds the cell budget; select a smaller region")
        return self._change(selection.positions(), target, "Fill")

    def set_block(self, position, target):
        position = _position(position)
        return self.fill(self.select((position, tuple(v + 1 for v in position))), target)

    def replace(self, selection, source, target, *, exact=False, preserve_properties=False):
        self._check_selection(selection)
        if isinstance(source, str) and not source.strip():
            source = Condition("non-air")
        if isinstance(source, Condition):
            if selection.volume > self.operation_limit:
                raise ValueError("Condition exceeds the cell budget; select a smaller region")
            positions = (p for p in selection.positions() if source.at(self, p))
        else:
            source = state_key(parse_state(source))
            exact = exact or "[" in source
            def matches(cell):
                return cell.state == source if exact else cell.state.split("[", 1)[0] == source
            matching_indices = {i for i, state in enumerate(self._states) if matches(_Cell(state))}
            base = self._document.source.present
            positions = (p for p in self.stored_positions(selection) if (
                matches(self._cells[p]) if p in self._cells else base[p] in matching_indices
            ))
        if preserve_properties:
            from structura_core.blockstates import replace_material

            if isinstance(target, Mix):
                resolve = lru_cache(maxsize=None)(lambda state, picked: replace_material(state, picked))
                return self._change(positions, lambda position, cell: resolve(cell.state if cell else "minecraft:air", target.at(position, self.origin)),
                                    "Replace")
            resolve = lru_cache(maxsize=None)(lambda state: replace_material(state, target))
            return self._change(positions, lambda position, cell: resolve(cell.state if cell else "minecraft:air"), "Replace")
        return self._change(positions, target, "Replace")

    def erase(self, selection):
        return self.fill(selection, "minecraft:air")

    def move(self, selection, offset, *, copy=False):
        from dataclasses import replace

        offset = _position(offset)
        self._check_selection(selection)
        if offset == (0, 0, 0):
            return ChangeSet(self._id, self.revision, "Duplicate" if copy else "Move blocks", ())
        change = self.paste(self.copy(selection, include_entities=False), tuple(p + d for p, d in zip(selection.lower, offset)),
                            take=not copy, include_air=True)
        return replace(change, label="Duplicate" if copy else "Move blocks")

    def copy(self, selection, *, include_blocks=True, include_entities=True):
        from .clipboard import Clipboard

        return Clipboard.capture(self, selection, include_blocks=include_blocks, include_entities=include_entities)

    def paste(self, clipboard, position, *, take=False, include_air=False, include_blocks=True, include_entities=True, destination=None):
        from .clipboard_placement import plan_placement
        from .destination_rule import DestinationRule

        return plan_placement(self, clipboard, (_position(position),), take=take, include_air=include_air,
                              include_blocks=include_blocks, include_entities=include_entities,
                              destination=destination or DestinationRule(), label="Take" if take else "Paste").change

    def stack(self, selection, copies, step, *, include_air=False, include_blocks=True, include_entities=True, destination=None):
        from .clipboard_placement import plan_stack
        from .destination_rule import DestinationRule

        return plan_stack(self, selection, copies, step, include_air=include_air, include_blocks=include_blocks, include_entities=include_entities,
                          destination=destination or DestinationRule()).change

    def shape(self, selection, target, *, form="Box", mask=None, surface=False, thickness=1):
        from .operations import shape_positions

        self._check_selection(selection)
        if selection.volume > self.operation_limit:
            raise ValueError("Shape exceeds the cell budget; select a smaller region")
        return self._change(shape_positions(self, selection, form, mask, surface, thickness), target, form)

    def export_selection(self, selection, path):
        from .selection_export import export_selection

        return export_selection(self, selection, path)

    def _check_change(self, change):
        from .change_validation import check_change

        check_change(self, change)

    def _write(self, position, cell):
        if cell is None or cell == self._original(position):
            self._cells.pop(position, None)
        else:
            self._cells[position] = cell

    def apply(self, change):
        if self.readonly:
            raise ValueError("This source is view-only in this release")
        self._check_change(change)
        if not change:
            return 0
        old_id = self._state_id
        new_id = uuid4().hex
        saved_changes = self._saved_changes.updated(self, change)
        self.history.append(change, old_id, new_id)
        self._saved_changes = saved_changes
        self._apply_cells(change, new_id)
        return len(change)

    def _apply_cells(self, change, state_id=None):
        self._transition = self._state_id, change.positions
        self._state_id = state_id or uuid4().hex
        for delta in change.changes:
            self._write(delta.position, delta.after)
        write_entities(self._entities, change.entities)
        from .document_resize import resize_document

        resize_document(self, change.resize)
        self.revision += 1

    def undo(self):
        return self._step_history(undo=True)

    def redo(self):
        return self._step_history(undo=False)

    def _step_history(self, *, undo):
        from .document_resize import resize_document

        index = self.history.cursor - 1 if undo else self.history.cursor
        if not 0 <= index < len(self.history.entries):
            return False
        entry, change = self.history.get(index)
        saved_changes = self._saved_changes.updated(self, change, reverse=undo)
        if undo:
            resize_document(self, change.resize, reverse=True)
        for delta in change.changes:
            self._write(delta.position, delta.before if undo else delta.after)
        write_entities(self._entities, change.entities, reverse=undo)
        if not undo:
            resize_document(self, change.resize)
        self.history.cursor += -1 if undo else 1
        self._transition = self._state_id, change.positions
        self._state_id = entry.before if undo else entry.after
        self.revision += 1
        self._saved_changes = saved_changes
        return True

    def fork(self):
        branch = copy(self)
        branch._cells = self._cells.copy()
        branch._entities = self._entities.copy()
        branch.history = History(self.history.cache_limit, persistent=False, cache_bytes=self.history.cache_bytes)
        return branch

    def diff(self, branch, label="Python recipe"):
        if branch._id != self._id:
            raise ValueError("Cannot compare unrelated documents")
        resize = None
        if branch.size != self.size or branch.origin != self.origin:
            from .document_resize import DocumentResize, check_resize, resize_document

            resize = DocumentResize(self.size, branch.size, tuple(old - new for old, new in zip(self.origin, branch.origin)))
            check_resize(self, resize)
            branch = branch.fork()
            resize_document(branch, resize, reverse=True)
        changes = tuple(sorted((
            _Delta(p, self._cell(p), branch._cell(p))
            for p in self._cells.keys() | branch._cells.keys()
            if self._cell(p) != branch._cell(p)
        ), key=lambda delta: delta.position))
        entities = tuple(sorted((EntityDelta(key, self._entities.get(key), branch._entities.get(key))
                                 for key in self._entities.keys() | branch._entities.keys()
                                 if self._entities.get(key) != branch._entities.get(key)), key=lambda delta: delta.key))
        change = ChangeSet(self._id, self.revision, label, changes, entities, resize)
        self._check_change(change)
        return change

    @contextmanager
    def transaction(self, label="Edit"):
        revision = self.revision
        branch = self.fork()
        yield branch
        if revision != self.revision:
            raise StaleChangeError("The document changed during the transaction")
        self.apply(self.diff(branch, label))

    def _render_source(self, change=None, *, include_nbt=True, include_entities=True):
        from .render_source import RenderSource, preview_session

        return RenderSource(preview_session(self, change)).region(include_entities=include_entities, include_nbt=include_nbt)

    def snapshot(self, change=None):
        branch = self
        if change is not None:
            branch = self.fork()
            branch.apply(change)
        return branch._document.snapshot(branch._cells, branch._entities)

    def save(self, path=None, force=False):
        if path is None and self.requires_save_as:
            raise ValueError("Source changed or is missing; choose an explicit Save as path")
        path = path or self.path
        if path is None:
            raise ValueError("Choose a destination filename")
        result = self._document.save(self.snapshot(), path, self._cells, self._entities)
        self._document = copy(self._document)
        self._document.path = result
        from structura_core.world_backup import digest

        self._document.source_hash = digest(result)
        self.save_target = result
        self.requires_save_as = False
        self._saved_state_id = self._state_id
        self._saved_changes = SavedChanges(self.origin, self.size)
        return result
