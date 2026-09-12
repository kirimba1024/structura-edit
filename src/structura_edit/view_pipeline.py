from dataclasses import dataclass, replace
from functools import cached_property
from time import perf_counter
import traceback

from .render_source import RenderSource, preview_session
from .sections import prepare_sections
from .height_slice import HeightSlice
from .loading import MAX_GEOMETRY_BYTES, replacement_sizes
from .task_protocol import SubmitResult


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
        atlas = map_spec(self.state, assets, cache_path, preview=bool(self.change)) if self.height.mode == "all" else None
        return dict(source=RenderSource(self.state, self.height).region(include_nbt=False), assets=assets, atlas=atlas)


class ViewPipeline:
    def __init__(self, scene, camera, minimap, submit, on_rendered, *, cache_path=None, retained_geometry=lambda: 0,
                 map_updates=None, schedule=None, failed=None, prepare_scene=None, present_scene=None):
        self.scene = scene
        self.camera = camera
        self.minimap = minimap
        self.submit = submit
        self.on_rendered = on_rendered
        self.cache_path = cache_path
        self.retained_geometry = retained_geometry
        self.map_updates = map_updates
        self.schedule = schedule
        self.failed = failed
        self.prepare_scene = prepare_scene
        self.present_scene = present_scene
        self._installation = None
        self.reset()

    def reset(self):
        self._cancel_installation()
        self.current = None
        self.ready = False
        self.preparing = False
        self.render_queued = False
        self.map_queued = False
        self.maps_current = None
        self.displayed = None

    def request(self, session, change, assets, entities, *, fit=False, data=None, height=HeightSlice()):
        self._cancel_installation()
        fit = fit or bool(self.current and self.current.fit and not self.ready)
        self.current = ViewRequest(session.fork(), change, assets, entities, fit, height)
        self.ready = False
        self.preparing = True
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
        if request is None or self._installation is not None:
            return
        if self.render_queued:
            self.render_queued = False
            previous = self.displayed
            if previous is not None and previous.assets != request.assets:
                previous = None
            if request.change is not None:
                accepted = self.submit("render_preview", lambda result: self._preview_rendered(request, result),
                                       request=request, previous=previous, assets=request.assets)
            else:
                accepted = self.submit(
                    "render", lambda data: self._rendered(request, data),
                    prepare_args=lambda: request.geometry_args(previous))
            self.render_queued = not accepted and accepted is not SubmitResult.FAILED_TO_START
            if accepted is SubmitResult.FAILED_TO_START:
                self.preparing = False
        elif self.map_queued and (not self.minimap.collapsed or hasattr(request.session, "map_identity")):
            self.map_queued = False
            if self.map_updates is not None:
                self.map_updates.request(request)
                self.maps_current = request
                return
            accepted = self.submit(
                "map", lambda images: self._mapped(request, images), prepare_args=lambda: request.map_args(self.cache_path))
            self.map_queued = not accepted and accepted is not SubmitResult.FAILED_TO_START

    def _preview_rendered(self, request, result):
        if request is not self.current:
            return
        state, data = result
        object.__setattr__(request, "state", state)
        self._rendered(request, data)

    def _rendered(self, request, data):
        if request is not self.current:
            return
        if self.prepare_scene is not None:
            self.prepare_scene(request, lambda: self._stage_rendered(request, data))
        else:
            self._stage_rendered(request, data)

    def _stage_rendered(self, request, data):
        if request is not self.current or not self.preparing:
            return
        retained = self.retained_geometry()
        if retained and sum(replacement_sizes(data, self.scene.section_bytes).values()) + retained > MAX_GEOMETRY_BYTES:
            self.fail()
            raise ValueError("Scene and clipboard exceed 192 MiB; use a smaller selection")
        if self.schedule is None:
            self.scene.replace(data, request.session.revision)
            self._presented(request, data)
        else:
            steps = self.scene.replace_steps(data, request.session.revision)
            self._installation = steps
            self.render_queued = True
            self.schedule(lambda: self._install_next(request, data, steps))

    def _cancel_installation(self):
        if self._installation is not None:
            self._installation.close()
            self._installation = None

    def fail(self):
        self._cancel_installation()
        self.preparing = False
        self.render_queued = False

    def _install_next(self, request, data, steps):
        if steps is not self._installation:
            return
        retirement = getattr(self.scene.plotter, 'retirement', None)
        if getattr(self.camera, 'moving', False) or (retirement is not None and retirement.busy):
            self.schedule(lambda: self._install_next(request, data, steps))
            return
        try:
            deadline = perf_counter() + 0.002
            while True:
                if not next(steps, False):
                    self._installation = None
                    self.render_queued = False
                    self._presented(request, data)
                    return
                if perf_counter() >= deadline:
                    self.schedule(lambda: self._install_next(request, data, steps))
                    return
        except Exception as error:
            self.fail()
            self.failed(f"{type(error).__name__}: {error}\n{traceback.format_exc()}")

    def _presented(self, request, data):
        self.scene.height = request.height
        if self.present_scene is not None:
            self.present_scene(request)
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
        self.preparing = False
        self.map_queued = True
        self.on_rendered(data)

    def _mapped(self, request, images):
        if request is self.current:
            self.minimap.set_images(images)
            self.maps_current = request
