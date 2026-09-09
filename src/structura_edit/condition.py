from dataclasses import dataclass

from structura_core.nbt import parse_state, state_key

from .picking import EMPTY


KINDS = ("air", "non-air", "materials", "properties")


@dataclass(frozen=True)
class Condition:
    kind: str = "non-air"
    values: tuple = ()
    negate: bool = False

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError("Choose Air, Non-air, Materials or Properties")
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

    @property
    def label(self):
        if self.kind == "air":
            text = "air"
        elif self.kind == "non-air":
            text = "non-air"
        elif self.kind == "materials":
            text = ", ".join(self.values) or "materials"
        else:
            text = ", ".join(f"{key}={item}" for key, item in self.pairs) or "properties"
        return "not " + text if self.negate else text

    def matches(self, state):
        if self.kind == "air":
            result = state is None or state.split("[", 1)[0] in EMPTY
        elif state is None:
            result = False
        elif self.kind == "non-air":
            result = state.split("[", 1)[0] not in EMPTY
        elif self.kind == "materials":
            result = any(state == value if "[" in value else state.split("[", 1)[0] == value for value in self.values)
        else:
            properties = {key: str(item) for key, item in parse_state(state).get("Properties", {}).items()}
            result = all(properties.get(key, item) == item for key, item in self.pairs)
        return result != self.negate
