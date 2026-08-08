"""Location Scout set-reference editor for MiniMax H3 Director Plus."""

import base64
import io as _io
import json

import numpy as np
import torch

from comfy_api.latest import io
from PIL import Image, ImageOps

from . import minimax_media as media
from .minimax_casting import MAX_CHARACTERS, _normalise_cast


MAX_LOCATION_ITEMS = 18
MAX_REFERENCE_IMAGES = 9
CANVAS_SIZE = 768


def _empty_item():
    return {"images": [], "description": ""}


def _empty_sets():
    return {"version": 1, "items": [_empty_item() for _ in range(MAX_LOCATION_ITEMS)]}


def _normalise_sets(value):
    try:
        value = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        value = None
    if not isinstance(value, dict):
        value = {}
    raw_items = value.get("items")
    if not isinstance(raw_items, list):
        raw_items = value.get("location_items", value.get("set_references", []))
    if not isinstance(raw_items, list):
        raw_items = []

    items = []
    for raw in raw_items[:MAX_LOCATION_ITEMS]:
        raw = raw if isinstance(raw, dict) else {}
        images = raw.get("images") if isinstance(raw.get("images"), list) else []
        if not images and isinstance(raw.get("image"), dict):
            images = [raw["image"]]
        clean_images = [image for image in images
                        if isinstance(image, dict) and (image.get("name") or image.get("b64"))]
        items.append({
            "images": clean_images[:1],
            "description": str(raw.get("description") or "").strip(),
        })
    while len(items) < MAX_LOCATION_ITEMS:
        items.append(_empty_item())
    return items


def _load_image(reference):
    try:
        if reference.get("name"):
            path = media.resolve_input_path(reference["name"])
            if path:
                return Image.open(path).convert("RGB")
        encoded = reference.get("b64") or ""
        if encoded:
            encoded = encoded.split(",", 1)[1] if "," in encoded else encoded
            return Image.open(_io.BytesIO(base64.b64decode(encoded))).convert("RGB")
    except Exception:
        return None
    return None


def _reference_data(cast_wardrobe, items):
    """Return ordered image entries and the JSON cast/wardrobe passthrough."""
    try:
        raw = json.loads(cast_wardrobe) if isinstance(cast_wardrobe, str) else cast_wardrobe
    except (TypeError, ValueError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    cast = _normalise_cast(raw)
    active_characters = [character for character in cast["characters"]
                         if character.get("hired", True)]
    entries = []

    def add_reference(reference, source, description=""):
        if len(entries) >= MAX_REFERENCE_IMAGES:
            return False
        image = _load_image(reference)
        if image is None:
            return False
        entries.append({
            "image": image, "reference": reference, "source": source,
            "picture_index": len(entries) + 1, "description": description,
        })
        return True

    for character_slot, character in enumerate(active_characters, start=1):
        for reference in character.get("images", []) or []:
            add_reference(reference, "cast", character.get("description", ""))

    wardrobe_collages = raw.get("wardrobe_collages")
    if not isinstance(wardrobe_collages, list):
        wardrobe_collages = []
    if wardrobe_collages:
        for collage in wardrobe_collages:
            if not isinstance(collage, dict):
                continue
            images = collage.get("images") if isinstance(collage.get("images"), list) else []
            if images:
                add_reference(images[0], "wardrobe", str(collage.get("description") or ""))
    else:
        for item in raw.get("wardrobe_items", []) or []:
            if not isinstance(item, dict):
                continue
            images = item.get("images") if isinstance(item.get("images"), list) else []
            if images:
                add_reference(images[0], "wardrobe", str(item.get("description") or ""))

    location_references = []
    for item in items:
        if not item.get("images"):
            continue
        reference = item["images"][0]
        before = len(entries)
        if add_reference(reference, "location", item.get("description", "")):
            entry = entries[-1]
            location_references.append({
                "images": [reference],
                "description": item.get("description", ""),
                "picture_index": entry["picture_index"],
            })
        elif len(entries) == before and len(entries) >= MAX_REFERENCE_IMAGES:
            break

    payload = {
        "version": 3,
        "characters": active_characters,
        "wardrobe_items": raw.get("wardrobe_items", []) or [],
        "wardrobe_collages": wardrobe_collages,
        "location_references": location_references,
    }
    return payload, entries


def _pack_images(entries):
    if not entries:
        return None
    tensors = []
    for entry in entries:
        fitted = ImageOps.contain(entry["image"], (CANVAS_SIZE, CANVAS_SIZE))
        canvas = Image.new("RGB", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0))
        canvas.paste(fitted, ((CANVAS_SIZE - fitted.width) // 2,
                              (CANVAS_SIZE - fitted.height) // 2))
        array = np.asarray(canvas, dtype=np.float32) / 255.0
        tensors.append(torch.from_numpy(array))
    return torch.stack(tensors, dim=0)


def _context_for(payload, entries):
    lines = [
        "Use the supplied cast, wardrobe, and location references when writing the prompt.",
        "The ordered visual references are labeled <image #>; location references come after cast and wardrobe references.",
    ]
    for index, entry in enumerate(entries, start=1):
        source = entry.get("source")
        label = "location/set" if source == "location" else source or "reference"
        description = str(entry.get("description") or "").strip()
        suffix = (": " + description) if description else ": reference image"
        lines.append("<image %d> %s%s" % (index, label, suffix))
    return "\n".join(lines)


class MiniMaxH3LocationScout(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3LocationScoutPlusCS",
            display_name="MiniMax H3 Location Scout Plus",
            category="MiniMax H3",
            description=(
                "Collect location and set reference images, descriptions, and picture tags. "
                "Connect CAST + WARDROBE from Wardrobe Director and LOCATION CONTEXT plus "
                "IMAGE REFS to Enhance Prompt."
            ),
            inputs=[
                io.String.Input(
                    "cast_wardrobe", force_input=True, optional=True,
                    tooltip="CAST + WARDROBE output from Wardrobe Director.",
                ),
                io.String.Input(
                    "analyze_settings", force_input=True, optional=True,
                    tooltip="ANALYZE SETTINGS output from Casting Director.",
                ),
                io.String.Input(
                    "sets_data", multiline=True, default=json.dumps(_empty_sets()),
                    tooltip="JSON state of the Location Scout UI (auto-managed).",
                ),
            ],
            outputs=[
                io.String.Output(
                    display_name="CAST + WARDROBE + SETS",
                    tooltip="Cast, wardrobe, and location references for the Director.",
                ),
                io.String.Output(
                    display_name="LOCATION CONTEXT",
                    tooltip="Context for the Enhance Prompt node.",
                ),
                io.Image.Output(
                    display_name="IMAGE REFS",
                    tooltip="Ordered cast, wardrobe, and location images for Enhance Prompt.",
                ),
            ],
        )

    @classmethod
    def execute(cls, cast_wardrobe="", analyze_settings="", sets_data="") -> io.NodeOutput:
        items = _normalise_sets(sets_data)
        payload, entries = _reference_data(cast_wardrobe, items)
        return io.NodeOutput(
            json.dumps(payload, separators=(",", ":")),
            _context_for(payload, entries),
            _pack_images(entries),
        )


NODE_CLASS_MAPPINGS = {"MiniMaxH3LocationScoutPlusCS": MiniMaxH3LocationScout}
NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxH3LocationScoutPlusCS": "MiniMax H3 Location Scout Plus",
}
