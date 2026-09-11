import json
from pathlib import Path
from zipfile import ZipFile

from .resources import resolve_assets


def material_catalog(assets):
    source = resolve_assets(assets)
    names, identifiers, version = {}, [], None
    if source.is_file():
        with ZipFile(source) as archive:
            paths = archive.namelist()
            if "version.json" in paths:
                version = json.loads(archive.read("version.json")).get("world_version")
            for path in paths:
                parts = path.split("/")
                if len(parts) >= 4 and parts[0] == "assets" and parts[2] == "blockstates" and path.endswith(".json"):
                    identifiers.append(parts[1] + ":" + "/".join(parts[3:])[:-5])
                elif len(parts) == 4 and parts[0] == "assets" and parts[2:] == ["lang", "en_us.json"]:
                    names.update(json.loads(archive.read(path)))
    elif source.is_dir():
        for root in [source, *(p for p in source.parent.iterdir() if p.is_dir() and p != source)]:
            identifiers.extend(root.name + ":" + str(path.relative_to(root / "blockstates"))[:-5]
                               for path in (root / "blockstates").rglob("*.json"))
            language = root / "lang" / "en_us.json"
            if language.is_file():
                names.update(json.loads(language.read_text()))
    rows = {identifier: names.get("block." + identifier.replace(":", ".").replace("/", "."),
                                 identifier.split(":", 1)[1].replace("_", " ").title())
            for identifier in sorted(set(identifiers))}
    return {"rows": rows, "version": version, "source": str(Path(source))}
