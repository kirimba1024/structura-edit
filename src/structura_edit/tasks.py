import io
import sqlite3
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from numbers import Integral
from typing import Callable, Optional


RECIPE_OUTPUT_LIMIT = 16_000


class _Output(io.StringIO):
    def write(self, text):
        length = len(text)
        retained = self.getvalue() + text[-RECIPE_OUTPUT_LIMIT:]
        self.seek(0)
        self.truncate()
        super().write(retained[-RECIPE_OUTPUT_LIMIT:])
        return length


@dataclass(frozen=True)
class TaskContext:
    progress: Optional[Callable] = None
    object_search: object = None


@dataclass(frozen=True)
class Task:
    execute: Callable
    message: str
    protected: bool = False
    resources: bool = False


def _open(args, context):
    from .source_loading import open_with_version_request

    return open_with_version_request(**args)


def _world(args, context):
    from .height_slice import HeightSlice
    from .preview import build_sections
    from .sections import prepare_sections
    from .source_loading import open_source

    options = {key: args[key] for key in ("path", "center", "dimension", "radius", "vertical_radius", "include_entities")}
    session = open_source(**options, world_changes=args.get("world_changes"))
    height = args.get("height", HeightSlice())
    rendered = build_sections(**prepare_sections(session, height=height), assets=args["assets"], progress=context.progress)
    return session, dict(rendered, height=height)


def _save(args, context):
    args["session"].save(args["path"])
    return args["session"]


def _apply(args, context):
    args["session"].apply(args["change"])
    return args["session"]


def _history(args, context):
    session, index = args["session"], args["index"]
    if isinstance(index, bool) or not isinstance(index, Integral) or not 0 <= index <= len(session.history.entries):
        raise ValueError("Invalid history position")
    total = abs(index - session.history.cursor)
    step = session.undo if index < session.history.cursor else session.redo
    while session.history.cursor != index:
        step()
        if context.progress:
            context.progress("History", total - abs(index - session.history.cursor), total)
    return session


def _render(args, context):
    from .preview import build_sections

    return build_sections(**args, progress=context.progress)


def _export(args, context):
    return args["session"].export_selection(args["selection"], args["path"])


def _map(args, context):
    from .map_cache import store_maps
    from .map_images import build_source_maps

    images = build_source_maps(args["source"], args["assets"], progress=context.progress)
    atlas = args.get("atlas")
    if atlas is not None:
        try:
            images, atlas = store_maps(atlas, images)
        except (OSError, ValueError, sqlite3.Error) as error:
            return images, None, f"Map cache unavailable: {error}"
    return images, atlas, ""


def _objects(args, context):
    from .object_edits import prepare_object_change

    return prepare_object_change(**args)


def _object_search(args, context):
    from .object_search import ObjectSearch

    search = context.object_search if context.object_search is not None else ObjectSearch()
    return search.find(args["session"], **args["query"])


def _operation(args, context):
    from .commands import COMMANDS

    return COMMANDS[args["mode"]].execute(args["session"], args["selection"], **args["values"])


def _clipboard(args, context):
    from .placement_jobs import prepare_clipboard

    return prepare_clipboard(**args, progress=context.progress)


def _placement(args, context):
    from .placement_jobs import prepare_placement

    return prepare_placement(**args, progress=context.progress)


def _placement_plan(args, context):
    return args["placement"].plan(args["session"])


def _repeat(args, context):
    from .clipboard_placement import plan_stack

    options = {key: value for key, value in args.items() if key != "session"}
    return plan_stack(args["session"], **options)


def _recipe(args, context):
    session = args["session"]
    branch = session.fork()
    output = _Output()
    namespace = {"edit": branch, "selection": args["selection"]}
    with redirect_stdout(output), redirect_stderr(output):
        exec(compile(args["code"], "<structura recipe>", "exec"), namespace)
    return session.diff(branch), output.getvalue()


def _connected(args, context):
    from .connected import connected_selection

    return connected_selection(args["session"], args["start"], criterion=args["criterion"], progress=context.progress)


def _item_icons(args, context):
    from .item_icons import render_icons

    return render_icons(args["ids"], args["assets"])


TASKS = {
    "open": Task(_open, "Opening…"),
    "world": Task(_world, "Loading world…", resources=True),
    "save": Task(_save, "Saving…", protected=True),
    "apply": Task(_apply, "Applying…", protected=True),
    "history": Task(_history, "Restoring history…", protected=True),
    "render": Task(_render, "Building preview…", resources=True),
    "export": Task(_export, "Exporting…", protected=True),
    "map": Task(_map, "", resources=True),
    "objects": Task(_objects, "Preparing object data…"),
    "object_search": Task(_object_search, "Finding objects…"),
    "operation": Task(_operation, "Preparing change…"),
    "connected": Task(_connected, "Selecting connected blocks…"),
    "item_icons": Task(_item_icons, "", resources=True),
    "clipboard": Task(_clipboard, "Preparing clipboard…", resources=True),
    "placement": Task(_placement, "Preparing placement…", resources=True),
    "placement_plan": Task(_placement_plan, "Checking placement rule…"),
    "repeat": Task(_repeat, "Preparing copies…"),
    "recipe": Task(_recipe, "Running recipe…"),
}


def task_definition(kind):
    try:
        return TASKS[kind]
    except KeyError:
        raise ValueError(f"Unknown task: {kind}") from None


def execute(kind, args, progress=None, *, object_search=None):
    task = task_definition(kind)
    if task.resources:
        from .resources import refresh_resources

        refresh_resources(args.get("assets"))
    return task.execute(args, TaskContext(progress, object_search))
