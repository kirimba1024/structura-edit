from dataclasses import dataclass

from structura_core.nbt import parse_state, state_key

from .picking import EMPTY


@dataclass(frozen=True)
class DestinationRule:
    mode: str = "all"
    material: str = ""

    def __post_init__(self):
        if self.mode not in ("all", "air", "material"):
            raise ValueError("Choose Replace all, Keep existing or Only material")
        material = state_key(parse_state(self.material)) if self.mode == "material" else ""
        object.__setattr__(self, "material", material)

    @property
    def label(self):
        return {"all": "Replace all", "air": "Keep existing", "material": "Only material"}[self.mode]

    def allows(self, state):
        state = state or "minecraft:air"
        if self.mode == "all":
            return True
        if self.mode == "air":
            return state.split("[", 1)[0] in EMPTY
        return (state if "[" in self.material else state.split("[", 1)[0]) == self.material
