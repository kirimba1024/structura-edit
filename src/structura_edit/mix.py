from dataclasses import dataclass

from structura_core.nbt import parse_state, state_key


MASK = (1 << 64) - 1


def hashed(seed, x, y, z):
    value = (seed * 0x9E3779B97F4A7C15 ^ x * 0xC2B2AE3D27D4EB4F ^ y * 0x165667B19E3779F9 ^ z * 0x27D4EB2F165667C5) & MASK
    value = (value ^ value >> 30) * 0xBF58476D1CE4E5B9 & MASK
    value = (value ^ value >> 27) * 0x94D049BB133111EB & MASK
    return value ^ value >> 31


@dataclass(frozen=True)
class Mix:
    items: tuple
    seed: int = 0

    def __post_init__(self):
        if not self.items:
            raise ValueError("Add at least one material")
        canonical = []
        for state, weight in self.items:
            if isinstance(weight, bool) or not isinstance(weight, int) or weight <= 0:
                raise ValueError("Weights must be positive integers")
            canonical.append((state_key(parse_state(state)), weight))
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("Seed must be a non-negative integer")
        object.__setattr__(self, "items", tuple(canonical))

    @property
    def total(self):
        return sum(weight for _, weight in self.items)

    @property
    def label(self):
        return f"{len(self.items)} materials · seed {self.seed}"

    def at(self, position):
        draw = hashed(self.seed, position[0], position[1], position[2]) % self.total
        for state, weight in self.items:
            if draw < weight:
                return state
            draw -= weight
        return self.items[-1][0]

    def __call__(self, position, before):
        return self.at(position)
