from __future__ import annotations

from dataclasses import fields
from typing import Any, Optional, Tuple, TYPE_CHECKING
from uuid import uuid4

from .changes import StaleChangeError
from .task_protocol import DocumentRequest, DocumentToken, ApplyCommand, HistoryCommand, SaveCommand, ProgressCallback

if TYPE_CHECKING:
    from .session import EditSession
    from .object_search import ObjectSearch


def document_token(session: EditSession) -> DocumentToken:
    return DocumentToken(uuid4().hex, session._id, session.revision, session._state_id)


def matches_document(token: DocumentToken, session: EditSession) -> bool:
    return (token.document_id, token.revision, token.state_id) == (session._id, session.revision, session._state_id)


class WorkerDocument:
    session: Optional[EditSession]
    token: Optional[DocumentToken]

    def __init__(self) -> None:
        self.clear()

    def clear(self) -> None:
        self.session = None
        self.token = None

    def execute(self, request: DocumentRequest, progress: Optional[ProgressCallback] = None,
                *, object_search: Optional[ObjectSearch] = None) -> Tuple[Any, DocumentToken]:
        from .tasks import execute
        from .worker_delta import compact_change, DocumentDelta

        if request.snapshot is not None:
            if not matches_document(request.token, request.snapshot):
                raise StaleChangeError('The document snapshot does not match its version')
            self.session, self.token = request.snapshot, request.token
            if object_search is not None:
                object_search.reset()
        if self.session is None or request.token != self.token or not matches_document(request.token, self.session):
            raise StaleChangeError('The worker document is unavailable or stale; prepare the operation again')
        command = request.command
        args = {field.name: getattr(command, field.name) for field in fields(command)}
        try:
            self.session.history.prune()
            change = compact_change(self.session, command)
            with self.session.history.defer_pruning():
                result = execute(command.kind, dict(args, session=self.session), progress, object_search=object_search)
            token = document_token(self.session) if isinstance(command, (ApplyCommand, HistoryCommand, SaveCommand)) else request.token
            if change is not None:
                result = DocumentDelta.capture(self.session, request.token, change, local=isinstance(command, ApplyCommand))
            self.token = token
            return result, token
        except BaseException:
            self.clear()
            raise
