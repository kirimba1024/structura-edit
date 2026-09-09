from PySide6.QtCore import QObject


class PlacementReview(QObject):
    def __init__(self, placement, document, edits, tasks, views):
        super().__init__(placement)
        self.placement, self.document, self.edits = placement, document, edits
        self.tasks, self.views = tasks, views
        placement.bar.adjust_requested.connect(self.adjust)
        placement.cancelled.connect(self.discard)

    @property
    def plan(self):
        preview = self.document.preview
        return preview.plan if preview is not None and preview.kind == "placement_plan" else None

    def apply(self):
        placement = self.placement
        if placement.model is None or self.tasks.busy or not self.views.ready:
            return
        plan = self.plan
        if plan is None:
            placement.model.following = False
            placement.refresh()
            self.edits.prepare("placement_plan", placement=placement.model)
        elif plan.change:
            placement.commit(plan.change)

    def discard(self):
        if self.plan is not None or self.tasks.kind == "placement_plan":
            self.edits.invalidate()

    def adjust(self):
        if self.tasks.busy:
            return
        self.discard()
        self.placement.scene.plotter.setFocus()
