from collections import Counter
from dataclasses import dataclass

from amulet_nbt import CompoundTag

from .changes import ChangeSet, StaleChangeError
from .nbt_values import ARRAY_VALUES, CONTAINERS, SCALARS, at_path, parse_scalar, replace_value, scalar_text
from .object_edits import block_data, edit_block_data, edit_entity_data
from .object_search import ObjectSearch, search_revision


MAX_BATCH_OBJECTS = 10_000
MAX_VALUE_LENGTH = 65_536
PROTECTED_FIELDS = frozenset(('id', 'UUID', 'UUIDMost', 'UUIDLeast', 'Dimension', 'Pos', 'x', 'y', 'z'))


@dataclass(frozen=True)
class NbtTargets:
    revision: tuple
    rows: tuple


@dataclass(frozen=True)
class NbtBatchPlan:
    change: ChangeSet
    total: int
    unchanged: int
    skipped: tuple
    samples: tuple

    @property
    def summary(self):
        skipped = sum(count for reason, count in self.skipped)
        return f"{len(self.change):,} changed · {self.unchanged:,} unchanged · {skipped:,} skipped / {self.total:,} objects"


def collect_nbt_targets(session, text="", *, kind="data", selection=None, search=None):
    rows = (search or ObjectSearch()).collect(session, text, kind=kind, selection=selection,
                                             limit=min(MAX_BATCH_OBJECTS, session.operation_limit))
    return NbtTargets(search_revision(session), rows)


def parse_field_path(text):
    if not isinstance(text, str) or not text.startswith('/') or len(text) > 2048:
        raise ValueError("Start the field path with /, for example /Items/0/count")
    parts = text[1:].split('/')
    if len(parts) > 128:
        raise ValueError("The field path is too deep")
    for part in parts:
        escaped = part.replace('~0', '').replace('~1', '')
        if '~' in escaped:
            raise ValueError("Use ~0 for a tilde and ~1 for a slash in a field name")
    return tuple(part.replace('~1', '/').replace('~0', '~') for part in parts)


def resolve_path(root, path):
    resolved = []
    value = root
    for key in path:
        if isinstance(value, CompoundTag):
            if not isinstance(key, str) or key not in value:
                raise ValueError("Field is missing")
        elif isinstance(value, CONTAINERS):
            if isinstance(key, str) and key.isascii() and key.isdecimal():
                key = int(key)
            if type(key) is not int or not 0 <= key < len(value):
                raise ValueError("List or array index is missing")
        else:
            raise ValueError("Field path crosses a scalar")
        resolved.append(key)
        value = at_path(value, (key,))
    return tuple(resolved), value


def replace_nbt_values(session, targets, path, text, *, progress=None):
    if session.readonly:
        raise ValueError("This source is view-only in this release")
    if not isinstance(targets, NbtTargets) or targets.revision != search_revision(session):
        raise StaleChangeError("The document changed; collect fresh search results")
    if len(targets.rows) > min(MAX_BATCH_OBJECTS, session.operation_limit):
        raise ValueError("Too many objects; narrow the search or selection")
    path = parse_field_path(path) if isinstance(path, str) else tuple(path)
    if not path or len(path) > 128 or any(type(key) not in (str, int) for key in path):
        raise ValueError("Choose an existing scalar field")
    if path[0] in PROTECTED_FIELDS:
        raise ValueError("Identity and position fields cannot be changed in a batch")
    if not isinstance(text, str) or len(text) > MAX_VALUE_LENGTH:
        raise ValueError(f"The value must contain at most {MAX_VALUE_LENGTH:,} characters")
    blocks, entities, samples = [], [], []
    skipped = Counter()
    unchanged = 0
    seen = set()
    for index, row in enumerate(targets.rows):
        key = row.kind, row.key if row.kind == 'entity' else row.position
        if key in seen:
            raise ValueError("The object set contains duplicates")
        seen.add(key)
        before_text = after_text = ''
        reason = ''
        try:
            if row.kind == 'entity':
                payload = session._entities[row.key].unpack()['nbt']
            elif row.kind == 'block':
                _, payload = block_data(session, row.position)
                if not payload:
                    raise ValueError("Block has no data")
            else:
                raise ValueError("Unsupported object type")
            resolved, before = resolve_path(payload, path)
            if not isinstance(before, SCALARS) or type(before) in ARRAY_VALUES:
                raise ValueError("Field is not a scalar")
            before_text = scalar_text(before)
            after = parse_scalar(before, text)
            after_text = scalar_text(after)
            if before == after:
                unchanged += 1
                reason = 'Unchanged'
            else:
                updated = replace_value(payload, resolved, after)
                change = (edit_entity_data(session, row.key, updated) if row.kind == 'entity'
                          else edit_block_data(session, row.position, updated))
                blocks.extend(change.changes)
                entities.extend(change.entities)
        except (KeyError, IndexError, TypeError, ValueError) as error:
            reason = str(error)
            skipped[reason] += 1
        if len(samples) < 24:
            samples.append((row, before_text[:160], after_text[:160], reason))
        if progress:
            progress('Object data', index + 1, len(targets.rows))
    change = ChangeSet(session._id, session.revision, 'Edit NBT in search results', tuple(blocks), tuple(entities))
    session._check_change(change)
    return NbtBatchPlan(change, len(targets.rows), unchanged, tuple(sorted(skipped.items())), tuple(samples))
