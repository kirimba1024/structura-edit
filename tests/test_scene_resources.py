import gc

import numpy as np
import pyvista as pv

from vtkmodules.util.numpy_support import vtk_to_numpy
from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter

from structura_render.packets import polygon_packets
from structura_edit.scene_geometry import packet_actor, warm_actor
from structura_edit.scene_textures import TexturePool


def pixels(window):
    capture = vtkWindowToImageFilter()
    capture.SetInput(window)
    capture.ReadFrontBufferOff()
    capture.ShouldRerenderOff()
    capture.Update()
    return vtk_to_numpy(capture.GetOutput().GetPointData().GetScalars()).copy()


def test_gpu_preparation_preserves_frame_and_shares_texture_buffers():
    view = pv.Plotter(off_screen=True, window_size=(100, 100))
    view.set_background('blue')
    view.add_mesh(pv.Plane(), color='red')
    view.show(auto_close=False)
    mesh = pv.Plane(i_resolution=1, j_resolution=1)
    pool = TexturePool()
    packet, = polygon_packets(mesh.points, mesh.faces.reshape(-1, 5)[:, 1:], 'OPAQUE',
                               uv=mesh.active_texture_coordinates, image=np.full((16, 16, 4), 255, np.uint8),
                               texture_key=b'texture')
    first, second = packet_actor(packet, pool), packet_actor(packet, pool)
    try:
        assert first.GetTexture() is second.GetTexture() and len(pool.textures) == 1
        assert first.GetMapper().GetStatic()
        assert first.GetMapper().GetInput().GetPolys().GetConnectivityArray().GetDataTypeSize() == 4
        del packet
        gc.collect()
        before = pixels(view.render_window)
        warm_actor(view, first)
        assert np.array_equal(before, pixels(view.render_window))
        view.renderer.AddActor(first)
        view.render()
        assert first.GetMapper().GetInput().GetNumberOfCells() == 1
        view.renderer.RemoveActor(first)
        del first, second
        gc.collect()
        assert not pool.textures
    finally:
        view.close()
