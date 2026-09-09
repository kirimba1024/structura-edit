from numbers import Integral

from structura_core.nbt import parse_state, state_key

from .editor_document import EditPreview


def prepared_preview(kind, result, selection, args):
    if kind == "recipe":
        change, output = result
        return EditPreview(change, kind, output=output)
    if kind in ("repeat", "placement_plan"):
        return EditPreview(result.change, kind, plan=result)
    values = args["values"]
    material = state_key(parse_state(values["target"])) if values.get("target") else None
    destination = None
    if args["mode"] == "Move blocks":
        offset = values["offset"]
        if result.resize is not None:
            offset = tuple(v + d for v, d in zip(offset, result.resize.offset))
        destination = tuple(tuple(p + d for p, d in zip(bound, offset)) for bound in (selection.lower, selection.upper))
    return EditPreview(result, kind, selection_after=destination, material=material)


class EditWorkflow:
    def __init__(self, document, tasks, *, previewed, updated):
        self.document = document
        self.tasks = tasks
        self.previewed = previewed
        self.updated = updated

    def invalidate(self, kind=None):
        if self.tasks.kind == "apply":
            return
        preview = self.document.preview
        if kind is not None and self.tasks.kind != kind and (preview is None or preview.kind != kind):
            return
        if self.document.invalidate():
            self.previewed(None)

    def prepare(self, kind, **args):
        if kind not in ("operation", "recipe", "repeat", "placement_plan"):
            raise ValueError(f"Task does not prepare an edit: {kind}")
        session = self.document.session
        if session is None or session.readonly or self.tasks.busy:
            return False
        selection = self.document.selected.region
        if kind != "placement_plan":
            if selection is None:
                return False
            args = dict(args, selection=selection)
        token = self.document.input_token
        def received(result):
            if token != self.document.input_token:
                return
            preview = prepared_preview(kind, result, selection, args)
            if self.document.show_preview(preview, token=token):
                self.previewed(preview)
        return self.tasks.submit(kind, received, session=session.fork(), **args)

    def _replace(self, kind, callback, **args):
        session = self.document.session
        if session is None or self.tasks.busy:
            return False
        token = self.document.session_token
        def received(result):
            if token != self.document.session_token:
                return
            self.updated(self.document.replace(result))
            callback(result)
        return self.tasks.submit(kind, received, session=session, **args)

    def commit(self, change, callback):
        return self._replace("apply", callback, change=change)

    def seek_history(self, index, callback):
        session = self.document.session
        if session is None or self.document.pending is not None or self.tasks.busy:
            return False
        if isinstance(index, bool) or not isinstance(index, Integral) or not 0 <= index <= len(session.history.entries):
            raise ValueError("Invalid history position")
        if index == session.history.cursor:
            return False
        self.document.invalidate()
        return self._replace("history", callback, index=index)

    def save(self, path, callback):
        session = self.document.session
        if session is None or session.readonly or self.document.pending is not None:
            return False
        return self._replace("save", callback, path=str(path))
