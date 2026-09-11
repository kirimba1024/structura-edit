from collections import Counter
from math import ceil, floor
from types import SimpleNamespace

from structura_core import parse_state
from structura_core.entity_positions import shift_entity

from .cell_data import cell_payload
from .object_labels import entity_label
from .picking import EMPTY
from .render_source import RenderSource


PREVIEW_SPAN = 32
PREVIEW_ENTITIES = 32


def quantity(count, noun, plural=None):
    word = noun if count == 1 else plural or noun + "s"
    return f"{count:,} {word}"


def material_name(state):
    return (state or "minecraft:air").split("[", 1)[0].split(":", 1)[-1].replace("_", " ").capitalize()


def payload_facts(payload):
    facts = []
    if "Health" in payload:
        facts.append(f"Health {float(payload['Health']):g}")
    if "Age" in payload:
        age = int(payload["Age"])
        facts.append("Baby" if age < 0 else "Adult")
    if "CustomName" in payload:
        facts.append(str(payload.get("id", "")).removeprefix("minecraft:"))
    items = payload.get("Items", payload.get("Inventory", []))
    stacks = [item for item in items if str(item.get("id", "minecraft:air")) != "minecraft:air"]
    if stacks:
        count = sum(int(item.get("count", item.get("Count", 1))) for item in stacks)
        facts.append(f"Inventory · {quantity(count, 'item')} · {quantity(len(stacks), 'slot')}")
    if "Item" in payload and "id" in payload["Item"]:
        item = payload["Item"]
        count = int(item.get("count", item.get("Count", 1)))
        facts.append(f"{count} × {material_name(str(item['id']))}")
    return facts


def block_details(session, position):
    state = session.state_at(position) or "minecraft:air"
    cell = session._cell(position)
    payload = cell_payload(session._document.source, cell, position) if cell else None
    world = tuple(p + o for p, o in zip(position, session.origin))
    facts = ["X {} · Y {} · Z {}".format(*world)]
    if "[" in state:
        facts.append(state.split("[", 1)[1].rstrip("]").replace(",", " · "))
    if payload:
        facts.extend(payload_facts(payload))
    return material_name(state), facts, state


def entity_details(session, keys):
    records = [session._entities[key].unpack() for key in sorted(keys) if key in session._entities]
    if not records:
        return "No entity", [], "", records
    if len(records) == 1:
        record = records[0]
        coords = tuple(float(p) + o for p, o in zip(record["pos"], session.origin))
        facts = ["X {:.1f} · Y {:.1f} · Z {:.1f}".format(*coords), *payload_facts(record["nbt"])]
        return entity_label(record["nbt"]), facts, str(record["nbt"].get("id", "Entity")), records
    counts = Counter(str(record["nbt"].get("id", "Entity")) for record in records)
    return f"{len(records):,} entities", [f"{material_name(name)} · {count:,}" for name, count in counts.most_common(3)], "Selected entities", records


def inspect_selection(session, selection, keys=()):
    if keys:
        title, facts, detail, records = entity_details(session, keys)
        origin = tuple(floor(min(float(record["pos"][axis]) for record in records)) for axis in range(3)) if records else (0, 0, 0)
        entities = [shift_entity(record, tuple(-v for v in origin)) for record in records[:PREVIEW_ENTITIES]]
        source = SimpleNamespace(size=(1, 1, 1), palette_raw=[], palette=[], present={}, block_nbt={}, entities=entities)
        note = f"First {PREVIEW_ENTITIES} entities shown" if len(records) > PREVIEW_ENTITIES else ""
        return dict(title=title, facts=facts, detail=detail, source=source, note=note)
    counts = Counter({name: count for name, count in session.palette_counts(selection, by_state=False).items() if name not in EMPTY})
    total = sum(counts.values())
    size = tuple(hi - lo for lo, hi in zip(selection.lower, selection.upper))
    if selection.volume == 1:
        title, facts, detail = block_details(session, selection.lower)
    else:
        title = "{} × {} × {} blocks".format(*size)
        facts = [f"{total:,} total · {quantity(len(counts), 'material')}"]
        top = counts.most_common(3)
        facts.extend(f"{material_name(name)} · {count:,} ({count / total:.0%})" for name, count in top)
        other = total - sum(count for _, count in top)
        if other:
            facts.append(f"Other · {other:,} ({other / total:.0%})")
        detail = "\n".join(f"{name} · {count:,}" for name, count in counts.most_common(12))
    step = max(1, ceil(max(size) / PREVIEW_SPAN))
    if step == 1:
        source = RenderSource(session).region(selection.lower, selection.upper)
        source.present = {p: i for p, i in source.present.items() if tuple(v + lo for v, lo in zip(p, selection.lower)) in selection}
        source.block_nbt = {p: value for p, value in source.block_nbt.items() if p in source.present}
        entities = [value.unpack() for value in session._entities.values()]
        entities = [record for record in entities if tuple(floor(float(p)) for p in record['pos']) in selection]
        source.entities = [shift_entity(record, tuple(-v for v in selection.lower)) for record in entities[:PREVIEW_ENTITIES]]
        note = f"First {PREVIEW_ENTITIES} entities shown" if len(entities) > PREVIEW_ENTITIES else ""
    else:
        groups = {}
        base = session._document.source.present
        for position in session.stored_positions(selection):
            cell = session._cells.get(position)
            state = cell.state if cell else session._states[base[position]] if position in base else None
            if state is None or state.split("[", 1)[0] in EMPTY:
                continue
            local = tuple((v - lo) // step for v, lo in zip(position, selection.lower))
            groups.setdefault(local, Counter())[state] += 1
        states, palette, present = {}, [], {}
        for position, choices in groups.items():
            state = choices.most_common(1)[0][0]
            if state not in states:
                states[state] = len(palette)
                palette.append(parse_state(state))
            present[position] = states[state]
        source = SimpleNamespace(size=tuple(ceil(v / step) for v in size), palette_raw=palette,
                                 palette=[str(state["Name"]) for state in palette], present=present, block_nbt={}, entities=[])
        note = f"Overview · blocks grouped {step} × {step} × {step}"
    return dict(title=title, facts=facts, detail=detail, source=source, note=note)


class InspectionBuilder:
    def __init__(self):
        self.assets = object()
        self.bank = None

    def __call__(self, session, selection, keys, assets):
        from structura_render.assets import AssetContext
        from structura_render.textures import TextureBank
        from .preview import build_geometry

        result = inspect_selection(session, selection, keys)
        if self.bank is None or self.assets != assets:
            self.bank = TextureBank(AssetContext(assets))
            self.assets = assets
        result["geometry"] = build_geometry(result.pop("source"), assets, bank=self.bank)
        return result
