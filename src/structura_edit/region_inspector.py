from concurrent.futures import ThreadPoolExecutor
from math import floor

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, QTimer, Signal
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QHeaderView, QLineEdit, QTabWidget, QTreeView, QVBoxLayout, QWidget

from .controls import MessageLabel
from .inspection import material_name, quantity
from .object_labels import entity_label
from .picking import EMPTY


def region_details(session, selection):
    counts = session.palette_counts(selection)
    blocks = [(state, material_name(state), f'{count:,}') for state, count in sorted(counts.items(), key=lambda row: (-row[1], row[0]))
              if state.split('[', 1)[0] not in EMPTY]
    total = sum(count for state, count in counts.items() if state.split('[', 1)[0] not in EMPTY)
    positions = session._document.source.block_nbt.keys() | session._cells.keys()
    data = []
    for position in sorted(positions):
        if position not in selection:
            continue
        cell = session._cell(position)
        if cell and cell.keep_nbt:
            world = tuple(p + o for p, o in zip(position, session.origin))
            data.append((position, material_name(cell.state), 'X {} · Y {} · Z {}'.format(*world)))
    entities = []
    for key, value in session._entities.items():
        record = value.unpack()
        if tuple(floor(float(v)) for v in record['pos']) in selection:
            world = tuple(float(p) + o for p, o in zip(record['pos'], session.origin))
            entities.append((key, entity_label(record['nbt']), 'X {:.1f} · Y {:.1f} · Z {:.1f}'.format(*world)))
    return blocks, data, entities, total


class RegionRows(QAbstractTableModel):
    def __init__(self, headings, parent=None):
        super().__init__(parent)
        self.headings, self.rows = headings, []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 2

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        key, name, detail = self.rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return (name, detail)[index.column()]
        if role == Qt.ItemDataRole.UserRole:
            return key
        if role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.UserRole + 1):
            return f'{name}\n{key}\n{detail}'

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.headings[section]

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()


class RegionInspector(QDialog):
    object_requested = Signal(str, object)

    def __init__(self, parent, session, selection):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle('Inspect selection')
        self.resize(720, 520)
        self.models = []
        self.info = MessageLabel('Counting blocks and finding objects…')
        layout = QVBoxLayout(self)
        layout.addWidget(self.info)
        lower = tuple(p + o for p, o in zip(selection.lower, session.origin))
        upper = tuple(p - 1 + o for p, o in zip(selection.upper, session.origin))
        size = tuple(hi - lo for lo, hi in zip(selection.lower, selection.upper))
        self.summary = '{} × {} × {} · {:,} cells\nFrom {} to {}'.format(*size, selection.volume, lower, upper)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        for kind, label, headings in (('block', 'Blocks', ('Material', 'Count')),
                                      ('data', 'Block data', ('Block', 'Position')),
                                      ('entity', 'Entities', ('Entity', 'Position'))):
            page = QWidget()
            contents = QVBoxLayout(page)
            search = QLineEdit(placeholderText='Find by name, ID or position…', clearButtonEnabled=True)
            contents.addWidget(search)
            model = RegionRows(headings, self)
            filtered = QSortFilterProxyModel(self)
            filtered.setSourceModel(model)
            filtered.setFilterRole(Qt.ItemDataRole.UserRole + 1)
            filtered.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            search.textChanged.connect(filtered.setFilterFixedString)
            table = QTreeView()
            table.setRootIsDecorated(False)
            table.setUniformRowHeights(True)
            table.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
            table.setModel(filtered)
            table.header().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            contents.addWidget(table, 1)
            if kind != 'block':
                table.setToolTip('Double-click to inspect this object, its inventory and NBT data.')
                table.activated.connect(lambda index, k=kind: self.object_requested.emit(k, index.data(Qt.ItemDataRole.UserRole)))
            else:
                table.setToolTip('All blocks in the selection, including blocks hidden inside solid terrain. Hover for the complete block state.')
            self.tabs.addTab(page, label)
            self.models.append(model)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='region-inspector')
        self.future = self.executor.submit(region_details, session.fork(), selection)
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.poll)
        self.timer.start()
        self.finished.connect(self.shutdown)

    def poll(self):
        if not self.future.done():
            return
        self.timer.stop()
        try:
            blocks, data, entities, total = self.future.result()
            for index, (model, rows, title) in enumerate(zip(self.models, (blocks, data, entities), ('Blocks', 'Block data', 'Entities'))):
                model.set_rows(rows)
                self.tabs.setTabText(index, f'{title} ({len(rows):,})')
            self.info.setText(self.summary + f"\n{quantity(total, 'block')} · {quantity(len(entities), 'entity', 'entities')}. Empty space is not counted as a block.")
        except Exception as error:
            self.info.setText(f'Inspection unavailable: {error}')

    def shutdown(self, *args):
        self.timer.stop()
        self.executor.shutdown(wait=False, cancel_futures=True)
