"""Shared typed context hand-off for the MiniMax H3 Plus authoring nodes.

The context value deliberately stays a Python object rather than being flattened to
JSON.  That lets Location Scout pass its already-packed IMAGE tensor while the earlier
nodes can pass lightweight file references for Enhance Prompt to resolve from the
selected project folder.
"""

from __future__ import annotations

import base64
import io as _io
import os

import numpy as np
import torch
from PIL import Image

from comfy_api.latest import io

from . import minimax_media as media
from .minimax_projects import parse_project_document


MiniMaxH3Context = io.Custom("MINIMAX_H3_CONTEXT")


def project_details(value) -> dict:
    """Return project identity and safe-to-use asset roots from PROJECT DATA."""
    document = parse_project_document(value) or {}
    if not document and isinstance(value, dict) and (value.get("path") or value.get("project_path")):
        document = value
    project_path = str(document.get("project_path") or "").strip()
    project_path = project_path or str(document.get("path") or "").strip()
    project_name = str(document.get("project_name") or "").strip()
    project_name = project_name or str(document.get("name") or "").strip()
    asset_roots = []
    if project_path:
        project_path = os.path.abspath(project_path)
        asset_roots = [
            project_path,
            os.path.join(project_path, "wardrobe", "resources"),
            os.path.join(project_path, "sets", "resources"),
        ]
    return {
        "name": project_name,
        "path": project_path,
        "asset_roots": asset_roots,
        "resources": document.get("resources", []) if isinstance(document, dict) else [],
    }


def make_context(prompt_context="", images=None, project=None, sources=None,
                 image_tensor=None) -> dict:
    """Build the stable payload emitted by Casting, Wardrobe, and Location nodes."""
    project = project if isinstance(project, dict) else {}
    return {
        "version": 1,
        "prompt_context": str(prompt_context or "").strip(),
        "images": list(images or []),
        "image_tensor": image_tensor,
        "project": project,
        "project_name": project.get("name", ""),
        "project_path": project.get("path", ""),
        "asset_roots": list(project.get("asset_roots") or []),
        "resources": list(project.get("resources") or []),
        "sources": sources if isinstance(sources, dict) else {},
    }


def normalise_context(value) -> dict:
    """Accept a typed context value and tolerate malformed/legacy values."""
    if not isinstance(value, dict):
        return {}
    result = dict(value)
    result["images"] = [image for image in (result.get("images") or [])
                        if isinstance(image, dict)]
    result["prompt_context"] = str(result.get("prompt_context") or result.get("context") or "").strip()
    project = result.get("project")
    if not isinstance(project, dict):
        project = {}
    result["project"] = project
    result["project_path"] = str(result.get("project_path") or project.get("path") or "").strip()
    result["asset_roots"] = list(result.get("asset_roots") or project.get("asset_roots") or [])
    result["resources"] = list(result.get("resources") or project.get("resources") or [])
    return result


def _project_candidates(name, project):
    name = str(name or "").replace("\\", "/").lstrip("/")
    if not name:
        return []
    project = project if isinstance(project, dict) else {}
    project_path = str(project.get("path") or "").strip()
    candidates = []
    for resource in project.get("resources", []) or []:
        if not isinstance(resource, dict):
            continue
        if str(resource.get("original") or "").replace("\\", "/").lstrip("/") == name:
            stored = str(resource.get("stored") or "").replace("\\", "/").lstrip("/")
            if project_path and stored:
                candidates.append(os.path.join(project_path, *stored.split("/")))
    if project_path:
        candidates.extend([
            os.path.join(project_path, *name.split("/")),
            os.path.join(project_path, "wardrobe", "resources", os.path.basename(name)),
            os.path.join(project_path, "sets", "resources", os.path.basename(name)),
        ])
    return candidates


def resolve_reference_path(reference, context=None):
    """Resolve an image reference from Comfy input or the selected project assets."""
    if not isinstance(reference, dict):
        return None
    name = reference.get("name") or reference.get("filename") or reference.get("file")
    if name:
        path = media.resolve_input_path(str(name))
        if path:
            return path
        context = normalise_context(context or {})
        for candidate in _project_candidates(name, context.get("project") or context):
            candidate = os.path.abspath(candidate)
            if os.path.isfile(candidate):
                return candidate
    return None


def load_reference_image(reference, context=None):
    """Load a referenced image, including an inline browser data URL."""
    try:
        path = resolve_reference_path(reference, context)
        if path:
            return Image.open(path).convert("RGB")
        encoded = reference.get("b64") or ""
        if encoded:
            encoded = encoded.split(",", 1)[1] if "," in encoded else encoded
            return Image.open(_io.BytesIO(base64.b64decode(encoded))).convert("RGB")
    except Exception:
        return None
    return None


def reference_tensors(references, context=None, limit=9):
    """Decode ordered context references into Comfy IMAGE batches."""
    tensors = []
    for reference in list(references or [])[:limit]:
        image = load_reference_image(reference, context)
        if image is None:
            continue
        array = np.asarray(image, dtype=np.float32) / 255.0
        tensors.append(torch.from_numpy(array).unsqueeze(0))
    return tensors
