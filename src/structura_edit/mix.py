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
    anchor: str = "local"
    gradient: tuple = ()
    algorithm: int = 1

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
        if self.algorithm != 1 or self.anchor not in ("local", "world"):
            raise ValueError("Unsupported mix algorithm or coordinate anchor")
        if self.gradient and (len(self.gradient) != 2 or len(self.items) != 2
                              or any(type(value) is not int for value in self.gradient)
                              or self.gradient[0] >= self.gradient[1]):
            raise ValueError("A height gradient needs two materials and increasing integer Y limits")
        object.__setattr__(self, "gradient", tuple(self.gradient))

    @property
    def total(self):
        return sum(weight for _, weight in self.items)

    @property
    def label(self):
        return f"{len(self.items)} materials · seed {self.seed} · {self.anchor}" + (" · Y gradient" if self.gradient else "")

    def at(self, position, origin=(0, 0, 0)):
        if self.anchor == "world":
            position = tuple(p + o for p, o in zip(position, origin))
        if self.gradient:
            lo, hi = self.gradient
            chance = max(0, min(hi - lo, position[1] - lo))
            index = int(hashed(self.seed, *position) * (hi - lo) < chance * (1 << 64))
            return self.items[index][0]
        draw = hashed(self.seed, position[0], position[1], position[2]) % self.total
        for state, weight in self.items:
            if draw < weight:
                return state
            draw -= weight
        return self.items[-1][0]

    def __call__(self, position, before):
        return self.at(position)

    def preset(self):
        return {"schema": 1, "algorithm": self.algorithm, "items": self.items, "seed": self.seed,
                "anchor": self.anchor, "gradient": self.gradient}

    @classmethod
    def from_preset(cls, value):
        if not isinstance(value, dict) or value.get("schema") != 1:
            raise ValueError("Unsupported mix preset")
        return cls(**{key: value[key] for key in ("items", "seed", "anchor", "gradient", "algorithm")})
