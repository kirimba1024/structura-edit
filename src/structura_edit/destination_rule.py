from dataclasses import dataclass

from structura_core.nbt import parse_state, state_key

from .condition import Condition
from .picking import EMPTY


@dataclass(frozen=True)
class DestinationRule:
    mode: str = "all"
    material: str = ""
    condition: object = None

    def __post_init__(self):
        if self.mode not in ("all", "air", "material", "where"):
            raise ValueError("Choose Replace all, Keep existing, Only material or Only where")
        material = state_key(parse_state(self.material)) if self.mode == "material" else ""
        object.__setattr__(self, "material", material)
        if self.mode == "where" and not isinstance(self.condition, Condition):
            raise ValueError("Only where needs a condition")

    @property
    def label(self):
        if self.mode == "where":
            return "Only where " + self.condition.label
        return {"all": "Replace all", "air": "Keep existing", "material": "Only material"}[self.mode]

    def allows(self, state):
        state = state or "minecraft:air"
        if self.mode == "all":
            return True
        if self.mode == "air":
            return state.split("[", 1)[0] in EMPTY
        if self.mode == "material":
            return (state if "[" in self.material else state.split("[", 1)[0]) == self.material
        return self.condition.matches(state)
