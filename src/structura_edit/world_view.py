from .document import Document
from .session import EditSession


class WorldView(EditSession):
    def __init__(self, world, region):
        super().__init__(Document(region.structure, path=world.path, readonly=True))
        self.dimension = region.dimension
        self.center = region.center
        self.radius = region.radius
        self.vertical_radius = region.vertical_radius
        self.loaded_chunks = region.loaded
        self.missing_chunks = region.missing
        self.notices = region.notices
        self.dimensions = tuple(world.dimensions)
        self.world_name = world.name

    def _check_readable(self, selection):
        super()._check_readable(selection)
        lower = tuple(p + o for p, o in zip(selection.lower, self.origin))
        upper = tuple(p + o - 1 for p, o in zip(selection.upper, self.origin))
        requested = {(x, z) for x in range(lower[0] // 16, upper[0] // 16 + 1)
                     for z in range(lower[2] // 16, upper[2] // 16 + 1)}
        if not requested <= self.loaded_chunks:
            raise ValueError("Selection contains chunks absent from the save; load a complete region before exporting")
