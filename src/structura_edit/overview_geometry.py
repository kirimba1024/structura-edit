import numpy as np

from structura_render.block_geometry import shape_is_occluder
from structura_render.lod_geometry import LodMesh, colored_geometry
from structura_render.lod_rectangles import compact_geometry


def overview_geometry(geometry, source):
    mesh = colored_geometry(geometry['meshes'], geometry['flat'])
    solid = np.asarray([shape_is_occluder(name) or name.endswith('_leaves') for name in source.palette] + [False])
    solid = solid[source.present.array]
    corners = mesh.points[mesh.triangles]
    normals = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    axis_aligned = np.count_nonzero(normals, axis=1) == 1
    centers = corners.mean(axis=1) + 1
    before = np.floor(centers - np.sign(normals) * .001).astype(int)
    after = np.floor(centers + np.sign(normals) * .001).astype(int)
    inside = ((before >= 0) & (after >= 0) & (before < solid.shape) & (after < solid.shape)).all(axis=1)
    indices = np.flatnonzero(axis_aligned & inside & (mesh.colors[mesh.triangles, 3] == 255).all(axis=1))
    keep = np.ones(len(corners), bool)
    keep[indices] = ~(solid[tuple(before[indices].T)] & solid[tuple(after[indices].T)])
    return LodMesh(*compact_geometry(mesh.points, mesh.triangles[keep], mesh.colors))
