from vtkmodules.util.numpy_support import numpy_to_vtk
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper

from .scene_textures import texture_pool


def remove_geometry(plotter, actors):
    retirement = getattr(plotter, 'retirement', None)
    if retirement is not None:
        retirement.add(actors)
        return
    for actor in actors:
        plotter.renderer.RemoveActor(actor)


def add_geometry(plotter, data):
    actors = []
    try:
        actors.extend(add_geometry_steps(plotter, data))
    except Exception:
        remove_geometry(plotter, actors)
        raise
    return actors


def packet_actor(packet, pool):
    points = vtkPoints()
    points.SetData(numpy_to_vtk(packet.points, deep=False))
    cells = vtkCellArray()
    cells.SetData(packet.indices.shape[1], numpy_to_vtk(packet.indices.ravel(), deep=False))
    mesh = vtkPolyData()
    mesh.SetPoints(points)
    mesh.SetPolys(cells)
    mapper = vtkPolyDataMapper()
    mapper.SetInputData(mesh)
    mapper.StaticOn()
    actor = vtkActor()
    actor.SetMapper(mapper)
    actor._structura_packet = packet
    prop = actor.GetProperty()
    prop.SetAmbient(.35)
    prop.SetDiffuse(1)
    prop.SetInterpolationToFlat()
    prop.SetBackfaceCulling(packet.cull)
    prop.SetColor(*(value / 255 for value in packet.color[:3]))
    prop.SetOpacity(packet.color[3] / 255)
    if packet.colors is not None:
        mesh.GetPointData().SetScalars(numpy_to_vtk(packet.colors, deep=False))
        mapper.SetColorModeToDirectScalars()
        mapper.SetScalarModeToUsePointData()
    else:
        mapper.ScalarVisibilityOff()
    if packet.uv is not None:
        mesh.GetPointData().SetTCoords(numpy_to_vtk(packet.uv, deep=False))
        actor._structura_texture = pool.get(packet)
        actor.SetTexture(actor._structura_texture)
    actor.SetForceOpaque(packet.mode != 'BLEND')
    return actor


def add_geometry_steps(plotter, data):
    pool = texture_pool(plotter)
    for packet in data['packets']:
        actor = packet_actor(packet, pool)
        actor.SetPosition(*data.get('position', (0, 0, 0)))
        actor.SetPickable(False)
        warm_actor(plotter, actor)
        plotter.renderer.AddActor(actor)
        yield actor


def warm_actor(plotter, actor):
    window = plotter.render_window
    if window.GetNeverRendered():
        return
    window.MakeCurrent()
    state = window.GetState()
    state.Push()
    try:
        state.vtkglViewport(0, 0, 0, 0)
        actor.RenderOpaqueGeometry(plotter.renderer)
        actor.RenderTranslucentPolygonalGeometry(plotter.renderer)
    finally:
        state.Pop()
