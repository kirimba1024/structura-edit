from dataclasses import dataclass


@dataclass(frozen=True)
class Parameter:
    name: str
    label: str
    default: object
    description: str


PARAMETERS = {
    p.name: p for p in (
        Parameter("source", "From", "minecraft:stone", "Block ID, or complete state for an exact match"),
        Parameter("target", "To", "minecraft:stone", "Material to place"),
        Parameter("offset", "Offset X / Y / Z", (0, 0, 0), "Integer displacement of the selected blocks"),
        Parameter("mask", "Only", "", "Restrict changes to a block ID or complete state"),
        Parameter("surface", "Only exposed blocks", False, "A non-air block with an exposed face"),
        Parameter("preserve_properties", "Keep compatible properties", True, "Retain matching properties such as stair direction when changing material"),
    )
}


@dataclass(frozen=True)
class Command:
    name: str
    description: str
    parameters: tuple
    group: str = "Region"

    def defaults(self):
        return {name: PARAMETERS[name].default for name in self.parameters}

    def execute(self, edit, selection, **values):
        unknown = values.keys() - self.defaults().keys()
        if unknown:
            raise ValueError(f"Unknown parameters: {', '.join(sorted(unknown))}")
        args = {**self.defaults(), **values}
        if self.name == "Replace":
            return edit.replace(selection, **args)
        if self.name in ("Move blocks", "Duplicate"):
            return edit.move(selection, args["offset"], copy=self.name == "Duplicate")
        return edit.shape(selection, "minecraft:air" if self.name == "Erase" else args["target"],
                          form="Box" if self.name in ("Fill", "Erase") else self.name,
                          mask=args.get("mask"), surface=args.get("surface", False))


COMMANDS = {
    c.name: c for c in (
        Command("Replace", "Replace matching blocks within the selection", ("source", "target", "preserve_properties")),
        Command("Fill", "Fill the selected region", ("target", "mask", "surface")),
        Command("Erase", "Clear blocks in the selected region", ("mask", "surface")),
        Command("Move blocks", "Move blocks and their data; entities and biomes stay in place", ("offset",)),
        Command("Duplicate", "Copy selected blocks without changing the source", ("offset",)),
        Command("Walls", "Build the four vertical boundary walls", ("target", "mask", "surface"), "Shapes"),
        Command("Shell", "Build the six boundary faces", ("target", "mask", "surface"), "Shapes"),
        Command("Ellipsoid", "Fit an ellipsoid inside the selection", ("target", "mask", "surface"), "Shapes"),
        Command("Cylinder", "Fit a vertical cylinder inside the selection", ("target", "mask", "surface"), "Shapes"),
        Command("Top surface", "Change the highest non-air block in each selected column", ("target", "mask", "surface"), "Shapes"),
    )
}

REGION_COMMANDS = tuple(name for name, command in COMMANDS.items() if command.group == "Region" and name != "Duplicate")
