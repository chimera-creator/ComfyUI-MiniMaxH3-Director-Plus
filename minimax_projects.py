"""Shared project persistence for the MiniMax H3 Director Plus nodes.

Projects intentionally live beside the nodes in ``Projects/<project>/wardrobe`` so a
workflow can be moved with the custom node directory.  The JSON document is
source-oriented: each node contributes a named source and later saves merge
into the same project instead of replacing the other node data.
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


def _project_dir(project_name: str) -> str:
    safe_name = normalise_project_name(project_name)
    path = os.path.abspath(os.path.join(PROJECTS_DIR, safe_name))
    root = os.path.abspath(PROJECTS_DIR)
    if os.path.commonpath([root, path]) != root:
        raise ValueError("Invalid project path.")
    return path


def _project_file(project_name: str) -> str:
    return os.path.join(_project_dir(project_name), "wardrobe", "project.json")


def _empty_document(project_name: str) -> dict:
    return {
        "schema_version": PROJECT_SCHEMA_VERSION,
        "project_name": normalise_project_name(project_name),
        "created_at": _timestamp(),
        "updated_at": _timestamp(),
        "sources": {},
        "resources": [],
    }


def load_project(project_name: str) -> dict | None:
    try:
        path = _project_file(project_name)
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
    document.setdefault("sources", {})
    document.setdefault("resources", [])
    return document


def list_projects() -> list[dict]:
    if not os.path.isdir(PROJECTS_DIR):
        return []
    projects = []
    for entry in os.scandir(PROJECTS_DIR):
        if not entry.is_dir() or not os.path.isfile(os.path.join(entry.path, "wardrobe", "project.json")):
            continue
        try:
            document = load_project(entry.name) or {}
            projects.append({
                "name": document.get("project_name", entry.name),
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


def _copy_resources(project_dir: str, references: list[str]) -> list[dict]:
    resource_dir = os.path.join(project_dir, "wardrobe", "resources")
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
            "stored": "resources/%s" % destination_name,
            "size": os.path.getsize(destination),
        })
    return copied


def save_project(project_name: str, source: str, data, resource_refs=None) -> dict:
    safe_name = normalise_project_name(project_name)
    source = str(source or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,39}", source):
        raise ValueError("Invalid project source.")
    if not isinstance(data, dict):
        raise ValueError("Project source data must be an object.")

    project_dir = _project_dir(safe_name)
    os.makedirs(os.path.join(project_dir, "wardrobe"), exist_ok=True)
    document = load_project(safe_name) or _empty_document(safe_name)
    document["schema_version"] = PROJECT_SCHEMA_VERSION
    document["project_name"] = safe_name
    document.setdefault("sources", {})[source] = data

    references = list(resource_refs or []) + collect_resource_refs(data)
    copied = _copy_resources(project_dir, references)
    existing = {item.get("original"): item for item in (document.get("resources") or [])
                if isinstance(item, dict) and item.get("original")}
    for item in copied:
        existing[item["original"]] = item
    document["resources"] = sorted(existing.values(), key=lambda item: item["original"])
    document["updated_at"] = _timestamp()

    project_path = _project_file(safe_name)
    wardrobe_dir = os.path.join(project_dir, "wardrobe")
    fd, temporary = tempfile.mkstemp(prefix=".project-", suffix=".json", dir=wardrobe_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary, project_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return document
