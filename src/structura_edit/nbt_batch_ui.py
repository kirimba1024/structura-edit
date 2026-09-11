from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QPlainTextEdit, QVBoxLayout

from .appearance import GRID
from .nbt_batch import MAX_VALUE_LENGTH, parse_field_path


class BatchNbtDialog(QDialog):
    preview_requested = Signal()
    apply_requested = Signal()
    changed = Signal()

    def __init__(self, parent, count, query, *, protected):
        super().__init__(parent)
        self.protected = protected
        self.setWindowTitle('Edit field in search results')
        self.resize(720, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*([GRID * 2] * 4))
        layout.setSpacing(GRID)
        scope = 'selection' if query.get('selection') is not None else 'loaded area'
        title = QLabel(f"{count:,} objects from all pages · {scope}\nSearch: {query.get('text') or 'All names'}")
        title.setWordWrap(True)
        layout.addWidget(title)
        hint = QLabel('Replace one existing scalar field. Each object keeps its stored type.\nMissing fields and invalid values are skipped and reported.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        form = QFormLayout()
        self.path = QLineEdit(placeholderText='/Items/0/count', maxLength=2048)
        self.path.setAccessibleName('Field path')
        self.path.setToolTip('Start with /. Separate fields and list indices with /. Use ~1 for a slash in a field name and ~0 for a tilde.')
        self.value = QPlainTextEdit()
        self.value.setMaximumHeight(100)
        self.value.setAccessibleName('New value')
        form.addRow('Field path', self.path)
        form.addRow('New value', self.value)
        layout.addLayout(form)
        self.summary = QLabel('Preview to see which objects will change.')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setAccessibleName('Change details')
        layout.addWidget(self.details, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.preview = buttons.addButton('Preview', QDialogButtonBox.ButtonRole.ActionRole)
        self.apply = buttons.addButton('Apply', QDialogButtonBox.ButtonRole.ActionRole)
        self.apply.setEnabled(False)
        self.preview.clicked.connect(self.preview_requested)
        self.apply.clicked.connect(self.apply_requested)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.path.textChanged.connect(self.changed)
        self.value.textChanged.connect(self.changed)
        self.path.setFocus()

    def reject(self):
        if not self.protected():
            super().reject()

    def closeEvent(self, event):
        if self.protected():
            event.ignore()
        else:
            super().closeEvent(event)

    def show_plan(self, plan, origin):
        self.summary.setText(plan.summary)
        lines = [f'{count:,} skipped: {reason}' for reason, count in plan.skipped]
        lines.append(f'Examples: first {len(plan.samples):,} of {plan.total:,} objects')
        for row, before, after, reason in plan.samples:
            position = ', '.join(f'{value + offset:g}' for value, offset in zip(row.position, origin))
            lines.append(f'{row.identity} @ {position}\n{reason or f"{before} → {after}"}')
        self.details.setPlainText('\n\n'.join(lines))


class BatchNbtController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.dialog = self.targets = self.token = None
        window.objects.finder.batch_requested.connect(self.open)

    def open(self, query):
        window = self.window
        if not window._objects_available() or window.document.session.readonly:
            return
        if self.dialog is not None:
            self.dialog.close()
        token = window.document.session_token
        window.navigation.stop()
        def received(targets):
            if token != window.document.session_token:
                return
            self.targets, self.token = targets, token
            dialog = BatchNbtDialog(window, len(targets.rows), query, protected=lambda: window.tasks.protected)
            self.dialog = dialog
            dialog.preview_requested.connect(self.preview)
            dialog.apply_requested.connect(window.apply_pending)
            dialog.changed.connect(self.changed)
            dialog.finished.connect(lambda result: self.closed(dialog))
            dialog.show()
            self.sync()
        window.tasks.submit('nbt_targets', received, session=window.document.session.fork(), query=query)

    def changed(self):
        self.window.edits.invalidate('nbt_batch')
        if self.dialog is not None:
            self.dialog.summary.setText('Preview to see which objects will change.')
            self.dialog.details.clear()
        self.sync()

    def closed(self, dialog):
        if self.dialog is not dialog:
            return
        self.dialog = self.targets = self.token = None
        if self.window.tasks.kind == 'nbt_batch':
            self.window.cancel_task()
        self.window.edits.invalidate('nbt_batch')
        self.window.plotter.setFocus()

    def preview(self):
        if self.dialog is None or self.token != self.window.document.session_token:
            return
        try:
            path = parse_field_path(self.dialog.path.text())
            text = self.dialog.value.toPlainText()
            if len(text) > MAX_VALUE_LENGTH:
                raise ValueError(f'Use at most {MAX_VALUE_LENGTH:,} characters')
            self.window.edits.prepare('nbt_batch', targets=self.targets, path=path, text=text)
        except ValueError as error:
            self.dialog.summary.setText(str(error))

    def previewed(self, preview):
        if self.dialog is not None and preview is not None and preview.kind == 'nbt_batch':
            self.dialog.show_plan(preview.plan, self.window.document.session.origin)

    def failed(self, message):
        if self.dialog is not None:
            self.dialog.summary.setText(message.splitlines()[0] if message else 'Operation failed')
            self.dialog.details.setPlainText(message)

    def sync(self):
        if self.dialog is None:
            return
        window = self.window
        if self.token != window.document.session_token:
            self.dialog.close()
            return
        preview = window.document.preview
        own = preview is not None and preview.kind == 'nbt_batch'
        available = not window.tasks.busy
        self.dialog.preview.setEnabled(available and (preview is None or own))
        self.dialog.apply.setEnabled(available and own and bool(preview.change) and window.views.ready)
        self.dialog.path.setEnabled(not window.tasks.protected)
        self.dialog.value.setEnabled(not window.tasks.protected)
