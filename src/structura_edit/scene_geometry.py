import numpy as np
import pyvista as pv


def remove_geometry(plotter, actors):
    for actor in actors:
        plotter.remove_actor(actor, reset_camera=False, render=False)


def add_geometry(plotter, data):
    from structura_render.mesh import material_groups

    actors = []
    try:
        for geometry in data["meshes"]:
            if not len(geometry.quads):
                continue
            texture = pv.Texture(geometry.image)
            texture.SetInterpolate(False)
            texture.mipmap = False
            for mode, points, quads, uv in material_groups(geometry):
                faces = np.column_stack((np.full(len(quads), 4), quads)).ravel()
                mesh = pv.PolyData(points, faces)
                mesh.active_texture_coordinates = uv
                actor = plotter.add_mesh(mesh, texture=texture, smooth_shading=False,
                                         ambient=0.35, reset_camera=False, render=False)
                actors.append(actor)
                actor.SetForceOpaque(mode != "BLEND")
        for points, faces, rgba in data["flat"]:
            if len(points):
                actors.append(plotter.add_mesh(
                    pv.PolyData(points, faces), color=tuple(v / 255 for v in rgba[:3]),
                    opacity=rgba[3] / 255, ambient=0.35, reset_camera=False, render=False))
    except Exception:
        remove_geometry(plotter, actors)
        raise
    return actors
