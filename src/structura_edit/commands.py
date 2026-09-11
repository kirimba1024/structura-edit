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
        Parameter("thickness", "Thickness", 1, "Shell depth to keep when hollowing out"),
        Parameter("depth", "Depth", 1, "Positive extrusion depth in blocks"),
        Parameter("normal", "Normal X / Y / Z", (0, 1, 0), "One axis: ±X, ±Y or ±Z; taken from Planar select"),
        Parameter("outside", "Outside frame", True, "Place the frame outside the selected plane"),
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
        if self.name in ("Extrude", "Frame"):
            from .planar import extrude, frame

            return (extrude(edit, selection, args["normal"], args["depth"]) if self.name == "Extrude" else
                    frame(edit, selection, args["normal"], args["target"], args["thickness"], args["outside"]))
        if self.name == "Replace":
            return edit.replace(selection, **args)
        if self.name in ("Move blocks", "Duplicate"):
            return edit.move(selection, args["offset"], copy=self.name == "Duplicate")
        return edit.shape(selection, "minecraft:air" if self.name in ("Erase", "Hollow") else args["target"],
                          form="Box" if self.name in ("Fill", "Erase") else self.name,
                          mask=args.get("mask"), surface=args.get("surface", False),
                          thickness=args.get("thickness", 1))


COMMANDS = {
    c.name: c for c in (
        Command("Replace", "Change only blocks matching From inside the selection. Choose To, then Preview and Apply; Cancel leaves the world unchanged.", ("source", "target", "preserve_properties")),
        Command("Fill", "Fill the selected space with To, including empty cells. Only limits which existing blocks change. Preview before Apply.", ("target", "mask", "surface")),
        Command("Erase", "Remove selected blocks and their stored data, such as chest contents. Entities stay. Preview before Apply; Undo restores the edit.", ("mask", "surface")),
        Command("Move blocks", "Move blocks and their data; entities and biomes stay in place", ("offset",)),
        Command("Duplicate", "Copy selected blocks without changing the source", ("offset",)),
        Command("Walls", "Build the four vertical sides of the selection. Leave its floor, roof and interior unchanged. Preview before Apply.", ("target", "mask", "surface"), "Shapes"),
        Command("Shell", "Build the four walls, floor and roof of the selection. Leave the interior unchanged. Preview before Apply.", ("target", "mask", "surface"), "Shapes"),
        Command("Hollow", "Empty the selection inside its boundary. Thickness controls how many outer layers to keep. Preview before Apply.", ("thickness", "mask", "surface"), "Shapes"),
        Command("Ellipsoid", "Fit an ellipsoid inside the selection", ("target", "mask", "surface"), "Shapes"),
        Command("Cylinder", "Fit a vertical cylinder inside the selection", ("target", "mask", "surface"), "Shapes"),
        Command("Top surface", "Change the highest non-air block in each selected column", ("target", "mask", "surface"), "Shapes"),
        Command("Overlay surface", "Place material above the highest non-air block of each column", ("target", "mask", "surface"), "Shapes"),
        Command("Extrude", "Extend a flat full-cube face into empty cells", ("normal", "depth"), "Shapes"),
        Command("Frame", "Frame a flat full-cube face with a square neighbourhood", ("normal", "target", "thickness", "outside"), "Shapes"),
    )
}

REGION_COMMANDS = tuple(name for name, command in COMMANDS.items() if command.group == "Region" and name not in ("Duplicate", "Move blocks"))
SHAPE_COMMANDS = tuple(name for name, command in COMMANDS.items() if command.group == "Shapes")
UI_COMMANDS = REGION_COMMANDS + SHAPE_COMMANDS
