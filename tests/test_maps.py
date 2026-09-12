import numpy as np
import pytest
from itertools import product
from types import SimpleNamespace

from PIL import Image, ImageColor
from structura_core import parse_state

from structura_edit.map_projection import VIEWS, project, unproject


@pytest.mark.parametrize("view", VIEWS)
def test_map_coordinates_roundtrip(view):
    point, size = (1.25, 2.5, 3.75), (12, 8, 16)
    assert np.allclose(unproject(project(point, size, view), point, size, view), point)


def test_all_six_maps_are_built_and_bounded(edit):
    pytest.importorskip("structura_render")
    from structura_edit.map_images import build_maps
    images = build_maps(edit)
    assert set(images) == set(VIEWS)
    assert all(image.dtype == np.uint8 and image.ndim == 3 for image in images.values())
    assert sum(image.shape[0] * image.shape[1] for image in images.values()) <= 1_000_000
    with pytest.raises(ValueError, match="budget"):
        build_maps(edit, max_pixels=1)


@pytest.mark.parametrize("view", VIEWS)
@pytest.mark.parametrize("scale", [1, 4, 16])
def test_cutout_and_translucent_layers_show_terrain_through_air_gaps(tmp_path, view, scale):
    from structura_render.projection_grid import VIEWS as AXES
    from structura_edit.map_images import build_source_maps
    from structura_edit.map_projection import plane_size

    ground = Image.new("RGBA", (4, 4), (20, 100, 60, 255))
    glass = Image.new("RGBA", (4, 4), (30, 60, 220, 128))
    flower = Image.new("RGBA", (4, 4), (255, 255, 255, 0))
    flower.putpixel((1, 1), (240, 20, 20, 255))
    flower.putpixel((2, 1), (220, 210, 30, 128))
    directory = tmp_path / "textures/block"
    directory.mkdir(parents=True)
    names = ["stone", "glass", "poppy"]
    for name, texture in zip(names, (ground, glass, flower)):
        texture.save(directory / f"{name}.png")
    axis, reverse = AXES[view]
    size = tuple(4 if i == axis else 3 for i in range(3))
    def position(a, b, depth):
        point = [a, b]
        point.insert(axis, size[axis] - depth - 1 if reverse else depth)
        return tuple(point)
    present = {position(a, b, 3): 0 for a, b in product(range(3), repeat=2)}
    present.update({position(1, 1, 2): 1, position(1, 1, 0): 2})
    palette = [f"minecraft:{name}" for name in names]
    source = SimpleNamespace(size=size, present=present, palette=palette, palette_raw=list(map(parse_state, palette)))
    budget = sum(np.prod(plane_size(size, direction)) for direction in VIEWS) * scale**2
    pixels = build_source_maps(source, tmp_path, max_pixels=budget)[view]
    layers = [texture.resize((scale, scale), Image.Resampling.BOX) for texture in (ground, glass, flower)]
    expected = np.asarray(Image.alpha_composite(Image.alpha_composite(*layers[:2]), layers[2]).convert("RGB"))
    assert np.allclose(pixels[scale:2 * scale, scale:2 * scale], expected, atol=1)
    assert np.all(pixels[:scale, :scale] == (20, 100, 60))


def test_fully_transparent_texture_never_tints_the_empty_map(tmp_path):
    from structura_edit.appearance import MAP_BACKGROUND
    from structura_edit.map_images import build_source_maps

    directory = tmp_path / "textures/block"
    directory.mkdir(parents=True)
    Image.new("RGBA", (4, 4), (255, 255, 255, 0)).save(directory / "poppy.png")
    source = SimpleNamespace(size=(3, 3, 3), present={(1, 2, 1): 0}, palette=["minecraft:poppy"],
                             palette_raw=[parse_state("minecraft:poppy")])
    assert all(np.all(image == ImageColor.getrgb(MAP_BACKGROUND)) for image in build_source_maps(source, tmp_path).values())


def test_default_map_preserves_original_sixteen_pixel_texture(tmp_path):
    from structura_edit.map_images import build_source_maps

    directory = tmp_path / "textures/block"
    directory.mkdir(parents=True)
    texture = np.arange(16 * 16 * 3, dtype=np.uint8).reshape(16, 16, 3)
    Image.fromarray(texture).save(directory / "stone.png")
    source = SimpleNamespace(size=(1, 1, 1), present={(0, 0, 0): 0}, palette=["minecraft:stone"],
                             palette_raw=[parse_state("minecraft:stone")])
    images = build_source_maps(source, tmp_path)
    assert all(image.shape == (16, 16, 3) for image in images.values())
    assert np.array_equal(images["top"], texture)


@pytest.mark.parametrize('view', VIEWS)
def test_zoom_fetches_original_pixels_even_when_overview_is_reduced(tmp_path, view):
    from structura_edit.map_images import MapRenderer

    directory = tmp_path / 'textures/block'
    directory.mkdir(parents=True)
    texture = np.arange(16 * 16 * 3, dtype=np.uint8).reshape(16, 16, 3)
    Image.fromarray(texture).save(directory / 'stone.png')
    source = SimpleNamespace(size=(4, 4, 4), present={p: 0 for p in product(range(4), repeat=3)},
                             palette=['minecraft:stone'], palette_raw=[parse_state('minecraft:stone')])
    renderer = MapRenderer(source, tmp_path)
    assert renderer.images(max_pixels=6 * 16)[view].shape == (4, 4, 3)
    area = (1, 1, 3, 3)
    actual_area, pixels = renderer.details(((view, area),))[view]
    assert actual_area == area and pixels.shape == (32, 32, 3)
    assert np.array_equal(pixels, np.tile(texture, (2, 2, 1)))


def test_plant_uses_model_particle_texture_instead_of_solid_color(tmp_path):
    import json
    from structura_edit.map_images import MapRenderer

    for directory in ('textures/block', 'blockstates', 'models/block'):
        (tmp_path / directory).mkdir(parents=True)
    Image.new('RGBA', (16, 16), (123, 45, 67, 255)).save(tmp_path / 'textures/block/peony_top.png')
    (tmp_path / 'blockstates/peony.json').write_text(json.dumps({'variants': {'': {'model': 'block/flower'}}}))
    (tmp_path / 'models/block/flower.json').write_text(json.dumps({'textures': {'particle': 'block/peony_top'}}))
    source = SimpleNamespace(size=(1, 1, 1), present={(0, 0, 0): 0}, palette=['minecraft:peony'],
                             palette_raw=[parse_state('minecraft:peony')])
    assert np.all(MapRenderer(source, tmp_path).images()['top'] == (123, 45, 67))
