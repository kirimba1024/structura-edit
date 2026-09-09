from dataclasses import dataclass, replace
from functools import cached_property

from .render_source import RenderSource, preview_session
from .sections import prepare_sections
from .height_slice import HeightSlice
from .loading import MAX_GEOMETRY_BYTES, replacement_sizes


@dataclass(frozen=True)
class ViewRequest:
    session: object
    change: object
    assets: object
    entities: bool
    fit: bool
    height: HeightSlice = HeightSlice()

    @cached_property
    def state(self):
        return preview_session(self.session, self.change)

    def geometry_args(self, previous):
        data = prepare_sections(self.state, ghost=self.change, original=self.session, include_entities=self.entities,
                                previous=(previous.state, None) if previous else None,
                                previous_entities=previous.entities if previous else True,
                                height=self.height, previous_height=previous.height if previous else HeightSlice())
        return dict(data, assets=self.assets)

    def map_args(self, cache_path=None):
        from .map_cache import map_spec
        from .resources import resolve_assets

        assets = resolve_assets(self.assets)
        atlas = map_spec(self.state, assets, cache_path) if self.height.mode == "all" else None
        return dict(source=RenderSource(self.state, self.height).region(include_nbt=False), assets=assets, atlas=atlas)


class ViewPipeline:
    def __init__(self, scene, camera, minimap, submit, on_rendered, *, cache_path=None, retained_geometry=lambda: 0, map_updates=None):
        self.scene = scene
        self.camera = camera
        self.minimap = minimap
        self.submit = submit
        self.on_rendered = on_rendered
        self.cache_path = cache_path
        self.retained_geometry = retained_geometry
        self.map_updates = map_updates
        self.reset()

    def reset(self):
        self.current = None
        self.ready = False
        self.render_queued = False
        self.map_queued = False
        self.maps_current = None
        self.displayed = None

    def request(self, session, change, assets, entities, *, fit=False, data=None, height=HeightSlice()):
        fit = fit or bool(self.current and self.current.fit and not self.ready)
        self.current = ViewRequest(session.fork(), change, assets, entities, fit, height)
        self.ready = False
        self.render_queued = True
        self.map_queued = False
        if data is not None:
            self.render_queued = False
            self._rendered(self.current, data)

    def request_maps(self):
        if self.current is not self.maps_current:
            self.map_queued = self.current is not None

    def accept(self, session, *, request=None):
        if not self.ready or self.displayed is None or (request is not None and request is not self.current):
            return False
        self.scene.accept_preview()
        self.scene.display_revision = session.revision
        self.displayed = replace(self.displayed, session=session.fork(), change=None)
        return True

    def rebase(self, session):
        self.current = self.displayed = replace(self.current, session=session.fork(), change=None, fit=False)
        self.map_queued = True

    def flush(self):
        request = self.current
        if request is None:
            return
        if self.render_queued:
            self.render_queued = False
            previous = self.displayed
            if previous is not None and previous.assets != request.assets:
                previous = None
            accepted = self.submit(
                "render", lambda data: self._rendered(request, data),
                prepare_args=lambda: request.geometry_args(previous))
            self.render_queued = not accepted
        elif self.map_queued and (not self.minimap.collapsed or hasattr(request.session, "map_identity")):
            self.map_queued = False
            if self.map_updates is not None:
                self.map_updates.request(request)
                self.maps_current = request
                return
            accepted = self.submit(
                "map", lambda images: self._mapped(request, images), prepare_args=lambda: request.map_args(self.cache_path))
            self.map_queued = not accepted

    def _rendered(self, request, data):
        if request is not self.current:
            return
        retained = self.retained_geometry()
        if retained and sum(replacement_sizes(data, self.scene.section_bytes).values()) + retained > MAX_GEOMETRY_BYTES:
            raise ValueError("Scene and clipboard exceed 192 MiB; use a smaller selection")
        self.scene.replace(data, request.session.revision)
        self.scene.height = request.height
        if self.displayed is not None and self.displayed.state._id == request.state._id:
            offset = tuple(old - new for old, new in zip(self.displayed.state.origin, request.state.origin))
            if any(offset):
                self.camera.translate(offset)
        self.displayed = request
        if request.fit:
            self.camera.frame(request.session.size)
        else:
            self.camera.needs_render = True
            self.camera.render()
        self.ready = True
        self.map_queued = True
        self.on_rendered(data)

    def _mapped(self, request, images):
        if request is self.current:
            self.minimap.set_images(images)
            self.maps_current = request
