import sqlite3
from typing import NamedTuple

from .map_images import MAX_MAP_PIXELS, MapRenderer
from .map_projection import VIEWS, cave_view
from .resources import refresh_resources, resolve_assets


class CameraMapState(NamedTuple):
    key: tuple
    renderer: MapRenderer
    atlas_spec: object = None
    atlas_source: object = None
    atlas_result: object = None


def context_key(request):
    state = request.state
    return (getattr(state, "_document", None), state._id, state._state_id, state.origin, state.size,
            request.assets, request.height)


def render_camera_maps(request, cut, large, previous, cache_path, areas=(), automatic=False, cave_y=None):
    from .map_cache import map_spec, store_maps

    key = context_key(request)
    if previous is None or previous.key != key:
        refresh_resources(request.assets)
        previous = CameraMapState(key, MapRenderer(request.map_args()["source"], request.assets))
    renderer = previous.renderer
    if automatic:
        cut = renderer.environment.cut(cut)
    views = VIEWS if large else ("top",)
    images = renderer.images(cut=cut, max_pixels=MAX_MAP_PIXELS, cave_y=cave_y, views=views)
    atlas, notice = None, ""
    state = CameraMapState(key, renderer)
    if large and request.height.mode == "all":
        reusable = {view: pixels for view, pixels in images.items() if not cave_view(view, cut, cave_y)}
        atlas = map_spec(request.state, resolve_assets(request.assets), cache_path, cut=cut,
                         preview=bool(request.change), views=reusable)
        if atlas is not None:
            if (previous.atlas_result is not None and previous.atlas_spec == atlas
                    and reusable.keys() == previous.atlas_source.keys()
                    and all(reusable[view] is previous.atlas_source[view] for view in reusable)):
                state = previous
                converted, atlas = previous.atlas_result
                images = converted if converted.keys() == images.keys() else dict(images, **converted)
            else:
                try:
                    converted, published = store_maps(atlas, reusable)
                    if published is not None:
                        state = CameraMapState(key, renderer, atlas, reusable, (converted, published))
                    images = converted if converted.keys() == images.keys() else dict(images, **converted)
                    atlas = published
                except (OSError, ValueError, sqlite3.Error) as error:
                    atlas, notice = None, f"Map cache unavailable: {error}"
    return state, images, atlas, notice, renderer.details(areas, cut=cut, cave_y=cave_y), cut, cave_y
