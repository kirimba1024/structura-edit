from dataclasses import dataclass
from pathlib import Path

from .loading import DEFAULT_RADIUS, DEFAULT_VERTICAL_RADIUS, MAX_WORLD_BLOCKS, check_world_budget
from .session import EditSession
from .world_view import WorldView
from .file_state import fingerprint


@dataclass(frozen=True)
class SourceVersionRequired:
    options: dict


def open_with_version_request(**options):
    from structura_core.schematic import MissingSchematicDataVersion

    try:
        return open_source(**options)
    except MissingSchematicDataVersion:
        return SourceVersionRequired(options)


def source_stamps(directory, center, radius):
    x, _, z = center
    paths = {str(Path(directory) / f"r.{cx // 32}.{cz // 32}.mca")
             for cx in range(int(x // 16) - radius, int(x // 16) + radius + 1)
             for cz in range(int(z // 16) - radius, int(z // 16) + radius + 1)}
    paths.update(str(Path(directory) / f"c.{cx}.{cz}.mcc")
                 for cx in range(int(x // 16) - radius, int(x // 16) + radius + 1)
                 for cz in range(int(z // 16) - radius, int(z // 16) + radius + 1))
    return {path: fingerprint(path) for path in paths}


def open_source(path, *, region=None, palette_index=0, center=None, dimension=None,
                radius=DEFAULT_RADIUS, vertical_radius=DEFAULT_VERTICAL_RADIUS, include_entities=True,
                source_data_version=None, target_version=None, strict=False, world_changes=None):
    path = Path(path).expanduser().resolve()
    if path.name == "level.dat":
        path = path.parent
    if not path.is_dir():
        return EditSession.open(path, region=region, palette_index=palette_index, source_data_version=source_data_version,
                                target_version=target_version, strict=strict)
    if region is not None or palette_index != 0:
        raise ValueError("Named regions and palette variants apply to schematic files")
    if source_data_version is not None or target_version is not None:
        raise ValueError("Format conversion options apply to schematic files")
    from structura_core.world import JavaWorld

    world = JavaWorld(path)
    center = world.start if center is None else center
    dimension = dimension or world.start_dimension
    if dimension not in world.dimensions:
        raise ValueError(f"Unknown dimension: {dimension}")
    check_world_budget(center, radius, vertical_radius)
    stamps = source_stamps(world.dimensions[dimension] / "region", center, radius)
    area = world.read_region(center, dimension=dimension, radius=radius,
                             vertical_radius=vertical_radius, include_entities=include_entities,
                             max_blocks=MAX_WORLD_BLOCKS)
    if world_changes is not None:
        world_changes.revision += 1
    session = WorldView(world, area, world_changes)
    session.map_stamps = stamps
    session.map_identity = str(world.path), dimension, str(world.data.get("WorldGenSettings", {}).get("seed", world.data.get("RandomSeed", "")))
    return session
