from collections import OrderedDict
from datetime import datetime
import json
import logging
from logging.handlers import RotatingFileHandler
from queue import Full, Queue
from threading import Thread
from time import monotonic
from uuid import uuid4


class ActionLog:
    def __init__(self, directory, *, limit=2000):
        self.directory = directory
        self.limit = limit
        self.records = OrderedDict()
        self.version = 0
        self.error = ''
        self.queue = Queue(maxsize=4096)
        self.thread = Thread(target=self._write, name='action-log', daemon=True)
        self.thread.start()

    def start(self, kind, args=None):
        args = args or {}
        session = args.get('session')
        details = {key: str(args[key])[:1024] for key in ('path', 'dimension', 'center', 'radius', 'vertical_radius', 'mode', 'operation', 'index', 'values', 'transform', 'position', 'include_entities', 'height') if key in args}
        if session is not None:
            details.update(source=str(session.path or 'Untitled'), revision=session.revision)
        selection = args.get('selection')
        if selection is not None:
            details['selection'] = dict(lower=selection.lower, upper=selection.upper, cells=selection.volume)
        placement = args.get('placement')
        if placement is not None:
            details.update(position=placement.position, move=placement.take, size=placement.clipboard.size)
        change = args.get('change')
        label = change.label if change is not None else kind.replace('_', ' ').capitalize()
        if kind == 'history' and session is not None:
            label = 'Undo' if args.get('index', 0) < session.history.cursor else 'Redo'
        if change is not None:
            details.update(blocks=len(change.changes), entities=len(change.entities))
        identifier = uuid4().hex
        record = dict(id=identifier, time=datetime.now().astimezone().isoformat(timespec='milliseconds'),
                      kind=kind, label=label, status='Running', details=details, started=monotonic())
        self.records[identifier] = record
        while len(self.records) > self.limit:
            self.records.popitem(last=False)
        self._publish(record)
        return identifier

    def finish(self, identifier, status='Done', *, error='', result=None):
        if identifier not in self.records:
            return
        record = self.records[identifier]
        record.update(status=status, seconds=round(monotonic() - record['started'], 3))
        if error:
            record['error'] = str(error)[:16000]
        if record['kind'] == 'apply' and status == 'Done' and hasattr(result, 'history') and result.history.cursor:
            entry = result.history.entries[result.history.cursor - 1]
            record.update(document=result._id, undo_key=entry.key)
        self._publish(record)

    def note(self, kind, details=None):
        identifier = self.start(kind, details)
        self.finish(identifier)

    def _publish(self, record):
        self.version += 1
        value = {key: value for key, value in record.items() if key != 'started'}
        try:
            self.queue.put_nowait(value)
        except Full:
            self.error = 'Action log queue is full; some records were not written.'

    def _write(self):
        handler = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(self.directory / 'actions.jsonl', maxBytes=4 * 1024 ** 2, backupCount=4, encoding='utf-8')
            handler.setFormatter(logging.Formatter('%(message)s'))
            while True:
                value = self.queue.get()
                try:
                    if value is None:
                        return
                    line = json.dumps(value, ensure_ascii=False)
                    handler.emit(logging.LogRecord('actions', logging.INFO, '', 0, line, (), None))
                finally:
                    self.queue.task_done()
        except OSError as error:
            self.error = f'Action log could not be written: {error}'
        finally:
            if handler is not None:
                handler.close()

    def close(self):
        try:
            self.queue.put_nowait(None)
        except Full:
            self.error = 'Action log did not finish flushing.'
        self.thread.join(timeout=1)
