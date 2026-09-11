from dataclasses import dataclass

from structura_core.nbt import parse_state, state_key

from .picking import EMPTY


KINDS = ("air", "non-air", "materials", "properties", "all", "any", "height", "block-entities")


@dataclass(frozen=True)
class Condition:
    kind: str = "non-air"
    values: tuple = ()
    negate: bool = False
    strict: bool = False

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError("Unknown condition kind")
        if self.kind in ("all", "any"):
            if not self.values or any(not isinstance(value, Condition) for value in self.values):
                raise ValueError("Add at least one child condition")
            object.__setattr__(self, "values", tuple(self.values))
            return
        values = []
        for value in self.values:
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Condition values must be non-empty strings")
            value = value.strip()
            values.append(state_key(parse_state(value)) if "[" in value and self.kind == "materials" else value)
        pairs = []
        if self.kind == "properties":
            for value in values:
                for part in value.split(","):
                    key, split, item = part.partition("=")
                    if not split or not key.strip() or not item.strip():
                        raise ValueError("Properties look like facing=north, waterlogged=true")
                    pairs.append((key.strip(), item.strip()))
        object.__setattr__(self, "values", tuple(values))
        object.__setattr__(self, "pairs", tuple(pairs))
        if self.kind == "height":
            if len(values) != 2 or int(values[0]) > int(values[1]):
                raise ValueError("Height needs a lower and upper Y, inclusive")

    @property
    def label(self):
        if self.kind in ("all", "any"):
            text = (" AND " if self.kind == "all" else " OR ").join(f"({value.label})" for value in self.values)
        elif self.kind == "height":
            text = f"Y {self.values[0]}…{self.values[1]}"
        elif self.kind == "block-entities":
            text = "has block entity"
        elif self.kind == "air":
            text = "air"
        elif self.kind == "non-air":
            text = "non-air"
        elif self.kind == "materials":
            text = ", ".join(self.values) or "materials"
        else:
            text = ", ".join(f"{key}={item}" for key, item in self.pairs) or "properties"
        return "not " + text if self.negate else text

    def at(self, session, position):
        try:
            session._check_destination(position)
        except ValueError:
            return False
        cell = session._cell(position)
        return self.matches(cell.state if cell else None,
                            position=tuple(p + o for p, o in zip(position, session.origin)),
                            has_nbt=bool(cell and cell.keep_nbt))

    def matches(self, state, *, position=None, has_nbt=False, known=True):
        if not known:
            return False
        if self.kind in ("all", "any"):
            choose = all if self.kind == "all" else any
            result = choose(value.matches(state, position=position, has_nbt=has_nbt) for value in self.values)
        elif self.kind == "height":
            if position is None:
                raise ValueError("A height condition needs cell coordinates")
            result = int(self.values[0]) <= position[1] <= int(self.values[1])
        elif self.kind == "block-entities":
            result = has_nbt
        elif self.kind == "air":
            result = state is None or state.split("[", 1)[0] in EMPTY
        elif state is None:
            result = False
        elif self.kind == "non-air":
            result = state.split("[", 1)[0] not in EMPTY
        elif self.kind == "materials":
            result = any(state == value if "[" in value else state.split("[", 1)[0] == value for value in self.values)
        else:
            properties = {key: str(item) for key, item in parse_state(state).get("Properties", {}).items()}
            result = all(properties.get(key, None if self.strict else item) == item for key, item in self.pairs)
        return result != self.negate
