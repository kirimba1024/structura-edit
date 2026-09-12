from structura_core.nbt import parse_state, state_key

from .changes import StaleChangeError, _position
from .document_resize import check_resize
from .entity_data import check_entities


def check_position(position):
    if not isinstance(position, tuple) or len(position) != 3:
        raise ValueError("Coordinates must be three integers")
    x, y, z = position
    if type(x) is not int or type(y) is not int or type(z) is not int:
        _position(position)


def inside(position, lower, upper):
    return (lower[0] <= position[0] < upper[0] and lower[1] <= position[1] < upper[1]
            and lower[2] <= position[2] < upper[2])


def check_change(session, change):
    if change.document_id != session._id or change.base_revision != session.revision:
        raise StaleChangeError("The document changed; create a fresh preview")
    if len(change) > session.operation_limit:
        raise ValueError("Change exceeds the changed-cell budget")
    lower, upper = check_resize(session, change.resize)
    check_entities(session, change.entities, (lower, upper))
    seen, states = set(), set()
    size = session.size
    for delta in change.changes:
        position, cell = delta.position, delta.after
        check_position(position)
        if position in seen or not inside(position, lower, upper):
            raise ValueError("Invalid or duplicate change position")
        session._check_destination(position)
        seen.add(position)
        if not session._cell_matches(position, delta.before):
            raise StaleChangeError("The change no longer matches this document")
        if cell.state not in states:
            if state_key(parse_state(cell.state)) != cell.state:
                raise ValueError("Change states must be canonical")
            states.add(cell.state)
        original = None
        if cell.origin is not None:
            check_position(cell.origin)
            if inside(cell.origin, (0, 0, 0), size):
                original = session._original(cell.origin)
            if original is None:
                raise ValueError("Change contains an invalid source cell")
        if cell.variant is not None and (original is None or cell.variant != original.variant or cell.state != original.state):
            raise ValueError("Change contains an invalid palette variant")
        if cell.keep_nbt and cell.data is not None:
            if not cell.data.nbt:
                raise ValueError("Change contains invalid block entity data")
        elif cell.keep_nbt and not (original and original.keep_nbt and original.state.split("[", 1)[0] == cell.state.split("[", 1)[0]):
            raise ValueError("Change contains invalid block entity data")
