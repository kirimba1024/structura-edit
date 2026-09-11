import argparse
import json
import pickle
import os
import subprocess
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter, sleep

from structura_edit.jobs import Worker
from structura_edit.task_protocol import ApplyCommand, HistoryCommand, OperationCommand, TaskSuccess
from benchmark_world_patch import world_view


class Meter:
    def __init__(self, connection):
        self.connection = connection
        self.bytes = 0
        self.received_bytes = 0

    def send(self, request):
        self.bytes = len(pickle.dumps(request, protocol=5))
        self.connection.send(request)

    def recv(self):
        reply = self.connection.recv()
        if isinstance(reply, TaskSuccess):
            self.received_bytes = len(pickle.dumps(reply, protocol=5))
        return reply

    def close(self):
        self.connection.close()


def wait(worker):
    deadline = perf_counter() + 30
    while perf_counter() < deadline:
        result = worker.poll()
        if result is not None:
            assert isinstance(result, TaskSuccess), result
            return result
        sleep(0.001)
    raise AssertionError('Worker timed out')


def run(path, pending, resident, repeats):
    session = world_view(path, pending)
    session.history.prepare()
    worker = Worker()
    samples = {name: [] for name in ('preview', 'apply', 'undo', 'redo')}
    def submit(command):
        if resident:
            worker.submit_document(command, session)
        else:
            branch = session.fork() if command.kind == 'operation' else session
            worker.submit(command.kind, session=branch, **vars(command))
        return wait(worker)
    def preview():
        return OperationCommand('Fill', session.select(((0, 0, 0), (1, 1, 1))), {'target': 'minecraft:glass'})
    try:
        started = perf_counter()
        submit(preview())
        cold_ms = (perf_counter() - started) * 1000
        for _ in range(repeats):
            started = perf_counter()
            change = submit(preview()).payload
            samples['preview'].append((perf_counter() - started) * 1000)
            for name, command in (('apply', ApplyCommand(change)), ('undo', HistoryCommand(session.history.cursor)),
                                  ('redo', HistoryCommand(session.history.cursor + 1))):
                started = perf_counter()
                session = submit(command).payload
                samples[name].append((perf_counter() - started) * 1000)
            session = submit(HistoryCommand(session.history.cursor - 1)).payload
        worker._connection = meter = Meter(worker._connection)
        reply = submit(preview())
        preview_bytes = dict(sent=meter.bytes, received=meter.received_bytes)
        reply = submit(ApplyCommand(reply.payload))
        apply_bytes = dict(sent=meter.bytes, received=meter.received_bytes)
        rss = {name: int(subprocess.check_output(['ps', '-o', 'rss=', '-p', str(pid)]).strip()) / 1024
               for name, pid in (('parent_mib', os.getpid()), ('worker_mib', worker._process.pid))}
        return dict(rss=rss, mode='resident' if resident else 'full_session', pending=pending, cold_ms=cold_ms,
                    stages={name: dict(median_ms=median(values), samples_ms=values) for name, values in samples.items()},
                    preview_bytes=preview_bytes, apply_bytes=apply_bytes)
    finally:
        worker.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('/private/tmp/structura-worker-document.json'))
    parser.add_argument('--repeats', type=int, default=5)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error('--repeats must be positive')
    rows = []
    with TemporaryDirectory(prefix='structura-worker-benchmark-') as temporary:
        for pending in (0, 100_000, 300_000, 500_000):
            for resident in (False, True):
                row = run(Path(temporary), pending, resident, args.repeats)
                rows.append(row)
                print(json.dumps(row), flush=True)
    args.output.write_text(json.dumps(dict(rows=rows, repeats=args.repeats,
        scenario='Real spawn/Pipe and SQLite history; synthetic world patch; no GUI or world writes; bytes measured separately from timings'), indent=2) + '\n')


if __name__ == '__main__':
    main()
