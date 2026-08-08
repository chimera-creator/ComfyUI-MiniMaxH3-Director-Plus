"""Shared project persistence for the MiniMax H3 Director Plus nodes.

Projects default to ``Projects/<project>/wardrobe`` beside the nodes, but the Project
node can select any local project folder. The JSON document is source-oriented: each
node contributes a named source and later saves merge into the same project instead of
replacing the other node data.
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
PROJECT_SCHEMA_VERSION = 1
_PROJECT_NAME_RE = re.compile(r"[^A-Za-z0-9._ -]+")
_PROJECT_FOLDERS = {"wardrobe", "sets"}
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
    """Return an absolute project-folder path, defaulting to the bundled Projects folder."""
    raw = str(value or "").strip()
    path = os.path.abspath(os.path.expanduser(raw or PROJECTS_DIR))
    if not os.path.isabs(path):
        raise ValueError("Project path must be absolute.")
    return path


def _project_dir(project_name: str, project_path: str | None = None) -> str:
    if project_path:
        return normalise_project_path(project_path)
    safe_name = normalise_project_name(project_name)
    return os.path.abspath(os.path.join(PROJECTS_DIR, safe_name))


def _project_file(project_name: str, project_path: str | None = None) -> str:
    return os.path.join(_project_dir(project_name, project_path), "wardrobe", "project.json")


def _normalise_folder(value: str) -> str:
    folder = str(value or "wardrobe").strip().lower()
    if folder not in _PROJECT_FOLDERS:
        raise ValueError("Invalid project folder.")
    return folder


def _empty_document(project_name: str) -> dict:
    return {
        "schema_version": PROJECT_SCHEMA_VERSION,
        "project_name": normalise_project_name(project_name),
        "created_at": _timestamp(),
        "updated_at": _timestamp(),
        "sources": {},
        "resources": [],
    }


def load_project(project_name: str, project_path: str | None = None) -> dict | None:
    try:
        path = _project_file(project_name, project_path)
    except ValueError:
        raise
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        document = json.load(handle)
    if not isinstance(document, dict):
        raise ValueError("Project file is not a JSON object.")
    document.setdefault("schema_version", PROJECT_SCHEMA_VERSION)
    document.setdefault("project_name", normalise_project_name(project_name))
    document.setdefault("project_path", os.path.abspath(os.path.dirname(os.path.dirname(path))))
    document.setdefault("sources", {})
    document.setdefault("resources", [])
    return document


def load_project_at_path(project_path: str) -> dict | None:
    """Load a project selected by its folder path, without requiring its name first."""
    path = normalise_project_path(project_path)
    project_file = os.path.join(path, "wardrobe", "project.json")
    if not os.path.isfile(project_file):
        return None
    with open(project_file, "r", encoding="utf-8") as handle:
        document = json.load(handle)
    if not isinstance(document, dict) or not document.get("project_name"):
        raise ValueError("Project file is not a valid project document.")
    document.setdefault("schema_version", PROJECT_SCHEMA_VERSION)
    document.setdefault("sources", {})
    document.setdefault("resources", [])
    document["project_path"] = path
    return document


def ensure_project(project_name: str, project_path: str | None = None) -> dict:
    """Create a project index if needed and return its document."""
    safe_name = normalise_project_name(project_name)
    selected_path = normalise_project_path(project_path) if project_path else None
    document = load_project_at_path(selected_path) if selected_path else load_project(safe_name)
    if document is not None:
        return document
    project_dir = _project_dir(safe_name, selected_path)
    os.makedirs(os.path.join(project_dir, "wardrobe"), exist_ok=True)
    os.makedirs(os.path.join(project_dir, "sets"), exist_ok=True)
    document = _empty_document(safe_name)
    document["project_path"] = project_dir
    project_file = _project_file(safe_name, selected_path)
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


def list_projects(project_path: str | None = None) -> list[dict]:
    root = normalise_project_path(project_path)
    if not os.path.isdir(root):
        return []
    projects = []
    for entry in os.scandir(root):
        if not entry.is_dir() or not os.path.isfile(os.path.join(entry.path, "wardrobe", "project.json")):
            continue
        try:
            document = load_project(entry.name, root) or {}
            projects.append({
                "name": document.get("project_name", entry.name),
                "path": document.get("project_path", entry.path),
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


def _copy_resources(project_dir: str, folder: str, references: list[str]) -> list[dict]:
    resource_dir = os.path.join(project_dir, folder, "resources")
    os.makedirs(resource_dir, exist_ok=True)
    copied = []
    for reference in references:
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
        copied.append({
            "original": reference,
            "stored": "%s/resources/%s" % (folder, destination_name),
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


def save_project(project_name: str, source: str, data, resource_refs=None,
                 folder="wardrobe", project_path: str | None = None) -> dict:
    safe_name = normalise_project_name(project_name)
    folder = _normalise_folder(folder)
    source = str(source or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,39}", source):
        raise ValueError("Invalid project source.")
    if not isinstance(data, dict):
        raise ValueError("Project source data must be an object.")

    project_dir = _project_dir(safe_name, project_path)
    folder_dir = os.path.join(project_dir, folder)
    os.makedirs(folder_dir, exist_ok=True)
    document = load_project(safe_name, project_dir) or _empty_document(safe_name)
    document["schema_version"] = PROJECT_SCHEMA_VERSION
    document["project_name"] = safe_name
    document["project_path"] = project_dir
    document.setdefault("sources", {})[source] = data

    references = list(resource_refs or []) + collect_resource_refs(data)
    copied = _copy_resources(project_dir, folder, references)
    existing = {item.get("original"): item for item in (document.get("resources") or [])
                if isinstance(item, dict) and item.get("original")}
    for item in copied:
        existing[item["original"]] = item
    document["resources"] = sorted(existing.values(), key=lambda item: item["original"])
    document["updated_at"] = _timestamp()

    project_file = _project_file(safe_name, project_dir)
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
