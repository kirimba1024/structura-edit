from PySide6.QtCore import QObject

from .world_placement import placement_area


class PlacementReview(QObject):
    def __init__(self, placement, document, edits, tasks, views):
        super().__init__(placement)
        self.placement, self.document, self.edits = placement, document, edits
        self.tasks, self.views = tasks, views
        placement.bar.adjust_requested.connect(self.adjust)
        placement.bar.preview_requested.connect(self.preview)
        placement.cancelled.connect(self.discard)

    @property
    def plan(self):
        preview = self.document.preview
        return preview.plan if preview is not None and preview.kind == "placement_plan" else None

    def apply(self):
        self.prepare(commit=True)

    def preview(self):
        self.prepare(commit=False)

    def prepare(self, *, commit):
        placement = self.placement
        if placement.model is None or self.tasks.busy or not self.views.ready:
            return
        reason = placement.model.reason(self.document.session)
        if reason:
            placement.message.emit(reason)
            return
        plan = self.plan
        if plan is None:
            placement.model.following = False
            placement.refresh()
            if placement_area(self.document.session, placement.model.position, placement.model.clipboard.size) is not None:
                self.load_area(commit=commit)
            else:
                self.prepare_plan(commit=commit)
        elif commit and plan.change:
            placement.commit(plan.change)

    def prepare_plan(self, *, commit):
        def ready(preview):
            if preview.change:
                self.placement.commit(preview.change)
            else:
                self.edits.previewed(preview)
        self.edits.prepare("placement_plan", placement=self.placement.model, ready=ready if commit else None)

    def load_area(self, *, commit):
        token = self.document.input_token, self.placement.token
        session_token = self.document.session_token
        def received(result):
            if token != (self.document.input_token, self.placement.token):
                return
            session, model = result
            update = self.document.replace(session, token=session_token)
            if update is None:
                return
            self.placement.model = model
            self.placement.clipboard = model.clipboard
            self.placement.session = session
            self.edits.updated(update)
            self.prepare_plan(commit=commit)
        self.tasks.submit("placement_area", received, session=self.document.session, placement=self.placement.model)

    def discard(self):
        if self.plan is not None or self.tasks.kind == "placement_plan":
            self.edits.invalidate()

    def adjust(self):
        if self.tasks.busy:
            return
        self.discard()
        self.placement.scene.plotter.setFocus()
