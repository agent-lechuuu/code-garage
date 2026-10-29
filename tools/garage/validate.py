"""`garage validate`: the catalog is well-formed and consistent; CI and pre-commit run it.

Checks: every catalog/*.yaml against schema/catalog.schema.json (a small built-in validator for the JSON-Schema
subset the schema uses, so no extra dependency); slice = file name; topic ids unique across slices, prefixed by the
slice, area = the id's second part; see_also ids resolve (and aren't the topic itself); no resource twice in a topic;
catalog/synonyms.yaml shape; then garage.policy.check(catalog, pins, trust) when that module exists (licence/trust
rules). `--guard FILE...` is the repo guard (pre-commit): no media, archives, databases or files over 10 MB.

  validate(repo=None) -> (errors, warnings)
"""
import datetime
import json
import os
import re
from pathlib import Path

from . import catalog, optional, paths

GUARD_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".mp4", ".mov", ".mkv", ".avi", ".mp3", ".wav",
             ".flac", ".m4a", ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".zst", ".7z", ".rar", ".iso", ".img",
             ".apk", ".aab", ".sqlite", ".sqlite3", ".db", ".pyc", ".jar", ".whl", ".exe", ".dll", ".so", ".dylib", ".bin"}
GUARD_MAX = 10_000_000
GUARD_ALLOW = {"dist/catalog.json"}   # generated, 3-5 MB by design


# ---- a JSON-Schema subset (type, enum, required, properties, additionalProperties, items, pattern, min/max*, $ref)

_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "number": (int, float), "integer": int}


def check_schema(value, schema, root=None, where="$"):
    root = root or schema
    errs = []
    if "$ref" in schema:
        node = root
        for part in schema["$ref"].removeprefix("#/").split("/"):
            node = node[part]
        return check_schema(value, node, root, where)
    t = schema.get("type")
    if t:
        ok = isinstance(value, _TYPES[t]) and not (t in ("integer", "number") and isinstance(value, bool))
        if not ok:
            return [f"{where}: expected {t}, got {type(value).__name__} {str(value)[:60]!r}"]
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{where}: {value!r} not one of {schema['enum']}")
    if isinstance(value, str):
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errs.append(f"{where}: {value[:80]!r} does not match {schema['pattern']}")
        if len(value) < schema.get("minLength", 0):
            errs.append(f"{where}: shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errs.append(f"{where}: longer than {schema['maxLength']} ({len(value)})")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value < schema.get("minimum", value):
        errs.append(f"{where}: below {schema['minimum']}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errs.append(f"{where}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errs.append(f"{where}: more than {schema['maxItems']} items")
        if schema.get("uniqueItems") and len({json.dumps(v, sort_keys=True) for v in value}) != len(value):
            errs.append(f"{where}: duplicate items")
        if "items" in schema:
            for k, v in enumerate(value):
                errs += check_schema(v, schema["items"], root, f"{where}[{k}]")
    if isinstance(value, dict):
        for k in schema.get("required", []):
            if k not in value:
                errs.append(f"{where}: missing {k}")
        props = schema.get("properties", {})
        for k, v in value.items():
            if k in props:
                errs += check_schema(v, props[k], root, f"{where}.{k}")
            elif schema.get("additionalProperties") is False:
                errs.append(f"{where}: unknown field {k!r}")
    return errs


def _plain(v):
    """YAML dates -> 'YYYY-MM-DD' (the schema speaks JSON)."""
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_plain(x) for x in v]
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()[:10]
    return v


def _where(doc, path):
    """'$.topics[3].resources[1].url' -> 'topic <id> resource <name>: url'."""
    m = re.match(r"\$\.topics\[(\d+)\](?:\.resources\[(\d+)\])?(.*)", path)
    if not m:
        return path
    t = doc["topics"][int(m.group(1))]
    out = f"{t.get('id', '#' + m.group(1))}"
    if m.group(2) is not None:
        out += f" / {t['resources'][int(m.group(2))].get('name', '#' + m.group(2))}"
    return out + (f" {m.group(3).lstrip('.')}" if m.group(3) else "")


def _load_yaml(p):
    return catalog.load_yaml(p) if Path(p).is_file() else {}


def validate(repo=None):
    repo = Path(repo) if repo else paths.repo()
    errors, warnings = [], []
    schema = json.loads((repo / "schema" / "catalog.schema.json").read_text())
    files = catalog._yaml_files(repo)
    if not files:
        return [f"no catalog/*.yaml in {repo}"], []
    docs, seen = [], {}
    for p in files:
        try:
            doc = _plain(catalog.load_yaml(p))
        except Exception as e:   # noqa: BLE001 - a YAML error is a validation error, with its position
            errors.append(f"{p.name}: YAML: {e}")
            continue
        if not isinstance(doc, dict):
            errors.append(f"{p.name}: not a mapping")
            continue
        for e in check_schema(doc, schema):
            path, _, msg = e.partition(": ")
            errors.append(f"{p.name}: {_where(doc, path)}: {msg}")
        if doc.get("slice") != p.stem:
            errors.append(f"{p.name}: slice {doc.get('slice')!r} differs from the file name")
        for t in doc.get("topics") or []:
            tid = t.get("id", "?")
            parts = str(tid).split(".")
            if tid in seen:
                errors.append(f"{p.name}: duplicate topic id {tid} (also in {seen[tid]})")
            seen[tid] = p.name
            if parts[0] != doc.get("slice"):
                errors.append(f"{p.name}: {tid}: id must start with the slice '{doc.get('slice')}.'")
            if len(parts) > 1 and t.get("area") != parts[1]:
                errors.append(f"{p.name}: {tid}: area {t.get('area')!r} must equal the id's second part {parts[1]!r}")
            rids = {}
            for r in t.get("resources") or []:
                if not isinstance(r, dict) or "url" not in r:
                    continue
                rid = catalog.normalize_url(r["url"])
                if rid in rids:
                    errors.append(f"{p.name}: {tid}: resource listed twice ({rid})")
                rids[rid] = 1
                if r.get("archived") and r.get("tier") == 1:
                    warnings.append(f"{p.name}: {tid}: archived resource at tier 1 ({r.get('name')})")
        docs.append((p, doc))
    for p, doc in docs:
        for t in doc.get("topics") or []:
            for s in t.get("see_also") or []:
                if s == t.get("id"):
                    errors.append(f"{p.name}: {t['id']}: see_also points to itself")
                elif s not in seen:
                    errors.append(f"{p.name}: {t.get('id')}: see_also {s} does not exist")
    syn = repo / "catalog" / "synonyms.yaml"
    if syn.is_file():
        data = _load_yaml(syn)
        s = data.get("synonyms") if isinstance(data, dict) else None
        if not isinstance(s, dict):
            errors.append("synonyms.yaml: needs a 'synonyms:' mapping")
        else:
            for k, v in s.items():
                if not isinstance(k, str) or not re.fullmatch(r"[a-z0-9][a-z0-9'_+#-]*( [a-z0-9][a-z0-9'_+#-]*)*", k):
                    errors.append(f"synonyms.yaml: key {k!r} must be lowercase words separated by single spaces")
                if not isinstance(v, list) or not all(isinstance(x, str) and x for x in v):
                    errors.append(f"synonyms.yaml: {k}: value must be a list of words")
    if errors:
        return errors, warnings
    policy = optional("policy")
    if policy is None:
        warnings.append("garage.policy not installed: licence/trust policy not checked")
    else:
        cat = catalog.load(repo)
        pins_mod = optional("pins")
        try:
            pins = pins_mod.all() if pins_mod is not None else _load_yaml(repo / "lock" / "pins.yaml")
        except Exception as e:   # noqa: BLE001
            errors.append(f"pins: {e}")
            pins = {}
        trust = _load_yaml(repo / "trust" / "registry.yaml")
        errors += [f"policy: {e}" for e in policy.check(cat, pins or {}, trust or {})]
    return errors, warnings


def guard(files):
    """The repo guard: problems with the files about to be committed (empty list = fine)."""
    bad = []
    for f in files:
        if not os.path.isfile(f) or os.path.islink(f):
            continue
        size, ext = os.path.getsize(f), os.path.splitext(f)[1].lower()
        rel = os.path.relpath(f).replace(os.sep, "/")
        if ext in GUARD_EXT:
            bad.append(f"{f}: media/archive/database/binary files don't go in git (snapshots live in GARAGE_HOME)")
        elif re.match(r"(mirror|quarantine|index|state)/", rel):   # GARAGE_HOME's folders, if one is nested here
            bad.append(f"{f}: mirrored or index content doesn't go in git")
        elif ext == ".log" and size > 1_000_000:
            bad.append(f"{f}: raw log over 1 MB ({size // 1000} kB)")
        elif size > GUARD_MAX and rel not in GUARD_ALLOW:
            bad.append(f"{f}: over 10 MB ({size // 1_000_000} MB)")
    return bad


def health():
    if catalog.dist_file() == catalog.PACKAGED and not paths.repo().is_dir():
        return [("PASS", "validate: n/a off-server (the bundled catalog was validated when it was built)")]
    try:
        errors, warnings = validate()
    except Exception as e:   # noqa: BLE001
        return [("FAIL", f"validate: {e}")]
    if errors:
        return [("FAIL", f"validate: {len(errors)} errors, first: {errors[0]}")]
    return [("PASS", f"validate: catalog valid ({len(warnings)} warnings)")]
