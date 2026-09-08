from PySide6.QtCore import QObject


class PlacementReview(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.plan = None
        window.placement.bar.adjust_requested.connect(self.adjust)
        window.placement.cancelled.connect(self.discard)

    def apply(self):
        window, placement = self.window, self.window.placement
        if window.worker.busy or not window.views.ready:
            return
        if self.plan is None:
            placement.model.following = False
            placement.refresh()
            window._run("placement_plan", self.prepared, session=window.session.fork(), placement=placement.model)
        elif window.pending is self.plan.change and self.plan.change:
            placement.committing = True
            window._run("apply", self.committed, session=window.session, change=self.plan.change)

    def prepared(self, plan):
        self.plan = plan
        self.window.pending = plan.change
        self.window.render_scene()

    def committed(self, session):
        placement = self.window.placement
        change = self.plan.change
        offset = change.resize.offset if change.resize is not None else (0, 0, 0)
        bounds = tuple(tuple(p + d for p, d in zip(bound, offset)) for bound in placement.model.bounds)
        self.plan = None
        self.window.pending = None
        placement._applied(session, None, bounds, len(change))

    def discard(self):
        if self.plan is None:
            return
        plan, self.plan = self.plan, None
        if self.window.pending is plan.change:
            self.window.pending = None
            self.window.render_scene()

    def adjust(self):
        if self.window.worker.busy:
            return
        self.discard()
        self.window.plotter.setFocus()
