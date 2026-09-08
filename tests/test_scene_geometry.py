import numpy as np
import pytest
from structura_render.geometry import TexturedMesh

pv = pytest.importorskip("pyvista")


@pytest.mark.parametrize("mode,alpha", [(1, 255), (2, 128)])
def test_mask_holes_preserve_depth_and_blend_stays_translucent(mode, alpha):
    from structura_edit.scene_geometry import add_geometry

    view = pv.Plotter(off_screen=True, window_size=(200, 200))
    view.set_background("blue")
    view.enable_depth_peeling(number_of_peels=8)
    view.render_window.SetMultiSamples(0)
    image = np.zeros((2, 2, 4), dtype=np.uint8)
    image[:, :, 1] = 255
    image[:, 1, 3] = alpha
    geometry = TexturedMesh(np.array([[-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, 1, 0]], dtype=np.float32),
                            np.array([[0, 1, 2, 3]]), np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32),
                            np.array([mode], dtype=np.uint8), image)
    try:
        actor, = add_geometry(view, {"meshes": [geometry], "flat": []})
        actor.GetProperty().LightingOff()
        view.add_mesh(pv.Plane(center=(0, 0, -0.5), direction=(0, 0, 1), i_size=2, j_size=2),
                      color="red", lighting=False)
        view.camera_position = [(0, 0, 4), (0, 0, 0), (0, 1, 0)]
        view.camera.parallel_projection = True
        view.camera.parallel_scale = 1.1
        view.show(auto_close=False)
        pixels = view.screenshot()
        assert np.array_equal(pixels[100, 50], [255, 0, 0])
        right = pixels[100, 150].astype(int)
        if mode == 1:
            assert actor.GetForceOpaque()
            assert np.array_equal(right, [0, 255, 0])
        else:
            assert not actor.GetForceOpaque()
            assert 80 < right[0] < 180 and 80 < right[1] < 180 and right[2] == 0
    finally:
        view.close()
