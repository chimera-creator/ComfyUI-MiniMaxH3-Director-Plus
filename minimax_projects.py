"""Shared project persistence for the MiniMax H3 Director Plus nodes.

The Project node selects a *Projects root*. Every named project lives below that root
in its own folder, with canonical ``Cast``, ``Wardrobe`` and ``Sets`` subfolders. The
reader still understands the original lowercase ``wardrobe``/``sets`` layout so old
workflows can be opened and then migrated by the next save.
"""

from __future__ import annotations

import datetime as _datetime
import hashlib
import json
import os
import re
import shutil
import tempfile

import folder_paths


PROJECTS_DIR = os.path.join(os.path.dirname(__file__), "Projects")
PROJECT_SCHEMA_VERSION = 2
_PROJECT_NAME_RE = re.compile(r"[^A-Za-z0-9._ -]+")
_PROJECT_FOLDER_NAMES = {
    "cast": "Cast",
    "casting": "Cast",
    "wardrobe": "Wardrobe",
    "sets": "Sets",
    "director": "Director",
    "enhanced_prompt": "Director",
}
WARDROBE_CATEGORIES = ("Full Outfits", "Tops", "Bottoms", "Accessories", "Anatomy")
_RESOURCE_KEYS = {
    "name", "filename", "file", "file_name", "fileName",
    "imageFile", "videoFile", "audioFile", "image_file", "video_file", "audio_file",
}


def _timestamp():
    return _datetime.datetime.now(_datetime.timezone.utc).isoformat()


def normalise_project_name(value: str) -> str:
    """Return a safe, stable folder name or raise ValueError for invalid input."""
    value = str(value or "").strip()
    value = _PROJECT_NAME_RE.sub("_", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    if not value:
        raise ValueError("Project name is required.")
    if value in {".", ".."}:
        raise ValueError("Invalid project name.")
    return value[:100]


def normalise_project_path(value: str | None) -> str:
    """Return an absolute filesystem path."""
    raw = str(value or "").strip()
    path = os.path.abspath(os.path.expanduser(raw or PROJECTS_DIR))
    if not os.path.isabs(path):
        raise ValueError("Project path must be absolute.")
    return path


def normalise_projects_path(value: str | None) -> str:
    """Return the root folder containing one directory per named project."""
    return normalise_project_path(value)


def _project_dir(project_name: str, project_path: str | None = None,
                projects_path: str | None = None) -> str:
    if project_path:
        return normalise_project_path(project_path)
    safe_name = normalise_project_name(project_name)
    root = normalise_projects_path(projects_path)
    return os.path.abspath(os.path.join(root, safe_name))


def _project_file(project_name: str, project_path: str | None = None,
                 projects_path: str | None = None) -> str:
    return os.path.join(_project_dir(project_name, project_path, projects_path), "project.json")


def _folder_name(value: str, source: str = "") -> str:
    key = str(value or source or "wardrobe").strip().replace("\\", "/").strip("/")
    lower = key.lower()
    if lower in _PROJECT_FOLDER_NAMES:
        return _PROJECT_FOLDER_NAMES[lower]
    if key in _PROJECT_FOLDER_NAMES.values():
        return key
    # Keep source-specific saves predictable while allowing a future source folder.
    if source and str(source).strip().lower() in _PROJECT_FOLDER_NAMES:
        return _PROJECT_FOLDER_NAMES[str(source).strip().lower()]
    raise ValueError("Invalid project folder.")


def _project_file_candidates(project_dir: str) -> list[str]:
    return [
        os.path.join(project_dir, "project.json"),
        os.path.join(project_dir, "Wardrobe", "project.json"),
        os.path.join(project_dir, "wardrobe", "project.json"),
    ]


def _is_project_dir(path: str) -> bool:
    path = os.path.abspath(path)
    return any(os.path.isfile(candidate) for candidate in _project_file_candidates(path))


def _empty_document(project_name: str) -> dict:
    return {
        "schema_version": PROJECT_SCHEMA_VERSION,
        "project_name": normalise_project_name(project_name),
        "created_at": _timestamp(),
        "updated_at": _timestamp(),
        "sources": {},
        "resources": [],
    }


def _load_project_file(path: str, project_name: str = "") -> dict | None:
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        document = json.load(handle)
    if not isinstance(document, dict):
        raise ValueError("Project file is not a JSON object.")
    document.setdefault("schema_version", PROJECT_SCHEMA_VERSION)
    if not document.get("project_name") and project_name:
        document["project_name"] = normalise_project_name(project_name)
    document.setdefault("project_path", os.path.abspath(os.path.dirname(path)))
    document.setdefault("projects_path", os.path.dirname(document["project_path"]))
    document.setdefault("sources", {})
    document.setdefault("resources", [])
    document.setdefault("folders", {
        name: os.path.join(document["project_path"], folder)
        for name, folder in (("cast", "Cast"), ("wardrobe", "Wardrobe"), ("sets", "Sets"))
    })
    return document


def load_project(project_name: str, project_path: str | None = None,
                 projects_path: str | None = None) -> dict | None:
    """Load a project by name from a Projects root or by its exact folder path."""
    safe_name = normalise_project_name(project_name)
    project_dir = _project_dir(safe_name, project_path, projects_path)
    for candidate in _project_file_candidates(project_dir):
        document = _load_project_file(candidate, safe_name)
        if document is not None:
            document["project_path"] = project_dir
            document["projects_path"] = os.path.dirname(project_dir)
            return document
    return None


def load_project_at_path(project_path: str) -> dict | None:
    """Load a project selected by its exact project-folder path."""
    path = normalise_project_path(project_path)
    for candidate in _project_file_candidates(path):
        document = _load_project_file(candidate)
        if document is not None:
            if not document.get("project_name"):
                raise ValueError("Project file is not a valid project document.")
            document["project_path"] = path
            document["projects_path"] = os.path.dirname(path)
            return document
    return None


def ensure_project(project_name: str, projects_path: str | None = None,
                   project_path: str | None = None) -> dict:
    """Create ``<projects root>/<project name>`` if needed and return its document."""
    safe_name = normalise_project_name(project_name)
    selected_path = normalise_project_path(project_path) if project_path else None
    document = (load_project_at_path(selected_path) if selected_path
                else load_project(safe_name, projects_path=projects_path))
    if document is not None:
        project_dir = document.get("project_path") or _project_dir(safe_name, selected_path, projects_path)
        os.makedirs(project_dir, exist_ok=True)
        for folder in ("Cast", "Wardrobe", "Sets", "Director"):
            os.makedirs(os.path.join(project_dir, folder), exist_ok=True)
        for category in WARDROBE_CATEGORIES:
            os.makedirs(os.path.join(project_dir, "Wardrobe", category), exist_ok=True)
        return document
    project_dir = _project_dir(safe_name, selected_path, projects_path)
    os.makedirs(project_dir, exist_ok=True)
    for folder in ("Cast", "Wardrobe", "Sets", "Director"):
        os.makedirs(os.path.join(project_dir, folder), exist_ok=True)
    for category in WARDROBE_CATEGORIES:
        os.makedirs(os.path.join(project_dir, "Wardrobe", category), exist_ok=True)
    document = _empty_document(safe_name)
    document["project_path"] = project_dir
    document["projects_path"] = os.path.dirname(project_dir)
    document["folders"] = {
        name: os.path.join(project_dir, folder)
        for name, folder in (("cast", "Cast"), ("wardrobe", "Wardrobe"), ("sets", "Sets"))
    }
    project_file = _project_file(safe_name, selected_path, projects_path)
    _write_json_atomic(project_file, document, os.path.dirname(project_file))
    return document


def parse_project_document(value) -> dict | None:
    """Parse a Project node payload without exposing filesystem paths."""
    try:
        value = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        return None
    if not isinstance(value, dict) or not value.get("project_name"):
        return None
    return value


def project_source_data(value, source: str):
    """Extract a node source from a Project node payload."""
    document = parse_project_document(value)
    if not document:
        return None
    saved = (document.get("sources") or {}).get(str(source or "").strip().lower())
    if not isinstance(saved, dict):
        return None
    data = saved.get("data")
    if isinstance(data, dict):
        return data
    return saved


def list_projects(projects_path: str | None = None) -> list[dict]:
    root = normalise_projects_path(projects_path)
    if not os.path.isdir(root):
        return []
    projects = []
    for entry in os.scandir(root):
        if not entry.is_dir() or not _is_project_dir(entry.path):
            continue
        try:
            document = load_project(entry.name, projects_path=root) or {}
            projects.append({
                "name": document.get("project_name", entry.name),
                "path": document.get("project_path", entry.path),
                "projects_path": document.get("projects_path", root),
                "updated_at": document.get("updated_at", ""),
                "resource_count": len(document.get("resources", []) or []),
                "sources": sorted((document.get("sources") or {}).keys()),
            })
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    projects.sort(key=lambda item: (str(item.get("updated_at", "")), item["name"]), reverse=True)
    return projects


def _looks_like_asset(value) -> bool:
    if not isinstance(value, str):
        return False
    value = value.strip()
    return bool(value and not value.startswith(("data:", "blob:", "http://", "https://")))


def collect_resource_refs(value, key: str | None = None) -> list[str]:
    """Find ComfyUI input-file references in an arbitrary node payload."""
    found = []
    if isinstance(value, dict):
        for child_key, child in value.items():
            if child_key in _RESOURCE_KEYS and _looks_like_asset(child):
                found.append(child)
            else:
                found.extend(collect_resource_refs(child, child_key))
    elif isinstance(value, list):
        for child in value:
            found.extend(collect_resource_refs(child, key))
    elif key in _RESOURCE_KEYS and _looks_like_asset(value):
        found.append(value)

    result = []
    seen = set()
    for ref in found:
        normal = str(ref).replace("\\", "/").lstrip("/")
        if normal and normal not in seen:
            seen.add(normal)
            result.append(normal)
    return result


def _resolve_input_reference(reference: str) -> str | None:
    input_dir = os.path.abspath(folder_paths.get_input_directory())
    clean = str(reference or "").replace("\\", "/").lstrip("/")
    candidates = [
        os.path.join(input_dir, clean),
        os.path.join(input_dir, "whatdreamscost", os.path.basename(clean)),
        os.path.join(input_dir, os.path.basename(clean)),
    ]
    for candidate in candidates:
        candidate = os.path.abspath(candidate)
        if os.path.commonpath([input_dir, candidate]) != input_dir:
            continue
        if os.path.isfile(candidate):
            return candidate
    return None


def _copy_resources(project_dir: str, folder: str, references: list[str],
                    subfolder: str = "resources") -> list[dict]:
    resource_dir = os.path.join(project_dir, folder, subfolder) if subfolder else os.path.join(project_dir, folder)
    os.makedirs(resource_dir, exist_ok=True)
    copied = []
    for reference in references:
        if isinstance(reference, dict):
            reference = (reference.get("name") or reference.get("filename") or
                         reference.get("file") or reference.get("fileName") or "")
        if not isinstance(reference, str) or not reference.strip():
            continue
        source = _resolve_input_reference(reference)
        if not source:
            continue
        basename = os.path.basename(source) or "resource"
        destination_name = basename
        destination = os.path.join(resource_dir, destination_name)
        if os.path.exists(destination):
            try:
                same_file = os.path.samefile(source, destination)
            except OSError:
                same_file = False
            if not same_file:
                digest = hashlib.sha1(reference.encode("utf-8")).hexdigest()[:10]
                stem, extension = os.path.splitext(basename)
                destination_name = "%s_%s%s" % (stem, digest, extension)
                destination = os.path.join(resource_dir, destination_name)
        shutil.copy2(source, destination)
        stored = "%s/%s" % (folder.replace("\\", "/"), destination_name)
        if subfolder:
            stored = "%s/%s/%s" % (folder.replace("\\", "/"), subfolder, destination_name)
        copied.append({
            "original": reference,
            "stored": stored,
            "size": os.path.getsize(destination),
        })
    return copied


def _write_json_atomic(path: str, document: dict, directory: str):
    fd, temporary = tempfile.mkstemp(prefix=".project-", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _json_value(value, fallback=None):
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value) if value else None
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed is not None else fallback


def _wardrobe_items(data) -> list[dict]:
    state = _json_value(data.get("wardrobe_data") if isinstance(data, dict) else data, {})
    if not isinstance(state, dict):
        return []
    items = state.get("items")
    if not isinstance(items, list):
        items = state.get("wardrobe_items")
    return [item for item in (items or []) if isinstance(item, dict)]


def _save_wardrobe_categories(project_dir: str, project_name: str, data: dict) -> list[dict]:
    """Write one metadata index and its images inside each Wardrobe category folder."""
    copied = []
    items = _wardrobe_items(data)
    for category in WARDROBE_CATEGORIES:
        category_items = [item for item in items
                          if str(item.get("category") or WARDROBE_CATEGORIES[0]).strip() == category]
        category_dir = os.path.join(project_dir, "Wardrobe", category)
        os.makedirs(category_dir, exist_ok=True)
        copied.extend(_copy_resources(
            project_dir, os.path.join("Wardrobe", category),
            collect_resource_refs(category_items), subfolder="",
        ))
        _write_json_atomic(
            os.path.join(category_dir, "items.json"),
            {
                "schema_version": PROJECT_SCHEMA_VERSION,
                "project_name": project_name,
                "category": category,
                "items": category_items,
            },
            category_dir,
        )
    return copied


def save_project(project_name: str, source: str, data, resource_refs=None,
                 folder=None, project_path: str | None = None,
                 projects_path: str | None = None) -> dict:
    safe_name = normalise_project_name(project_name)
    source = str(source or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,39}", source):
        raise ValueError("Invalid project source.")
    if not isinstance(data, dict):
        raise ValueError("Project source data must be an object.")

    folder = _folder_name(folder, source)
    project_dir = _project_dir(safe_name, project_path, projects_path)
    folder_dir = os.path.join(project_dir, folder)
    os.makedirs(folder_dir, exist_ok=True)
    document = load_project(safe_name, project_path=project_dir) or _empty_document(safe_name)
    document["schema_version"] = PROJECT_SCHEMA_VERSION
    document["project_name"] = safe_name
    document["project_path"] = project_dir
    document["projects_path"] = os.path.dirname(project_dir)
    document["folders"] = {
        name: os.path.join(project_dir, canonical)
        for name, canonical in (("cast", "Cast"), ("wardrobe", "Wardrobe"), ("sets", "Sets"))
    }
    document.setdefault("sources", {})[source] = data

    references = list(resource_refs or []) + collect_resource_refs(data)
    copied = _copy_resources(project_dir, folder, references, subfolder="images")
    if source == "wardrobe" or folder == "Wardrobe":
        copied.extend(_save_wardrobe_categories(project_dir, safe_name, data))
    existing = {item.get("original"): item for item in (document.get("resources") or [])
                if isinstance(item, dict) and item.get("original")}
    for item in copied:
        existing[item["original"]] = item
    document["resources"] = sorted(existing.values(), key=lambda item: item["original"])
    document["updated_at"] = _timestamp()

    project_file = _project_file(safe_name, project_path=project_dir)
    os.makedirs(os.path.dirname(project_file), exist_ok=True)
    _write_json_atomic(project_file, document, os.path.dirname(project_file))
    _write_json_atomic(
        os.path.join(folder_dir, "%s.json" % source),
        {
            "schema_version": PROJECT_SCHEMA_VERSION,
            "project_name": safe_name,
            "source": source,
            "updated_at": document["updated_at"],
            "data": data,
        },
        folder_dir,
    )
    return document
