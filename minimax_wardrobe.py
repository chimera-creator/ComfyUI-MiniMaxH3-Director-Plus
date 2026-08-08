"""Wardrobe item editor and per-character collage builder for MiniMax H3 Director Plus."""

import base64
import io as _io
import json
import math
import os
import uuid

from comfy_api.latest import io
import folder_paths
from PIL import Image, ImageDraw, ImageOps

from .minimax_casting import MAX_CHARACTERS, _normalise_cast
from . import minimax_media as media

MAX_WARDROBE_ITEMS = 18
COLLAGE_TILE = 256
COLLAGE_COLUMNS = 4
WARDROBE_CATEGORIES = (
    "Full Outfits", "Tops", "Bottoms", "Accessories", "Anatomy",
)


def _empty_item():
    return {
        "images": [], "description": "", "category": WARDROBE_CATEGORIES[0],
        "character_slots": [],
    }


def _empty_wardrobe():
    return {
        "version": 1,
        "items": [_empty_item() for _ in range(MAX_WARDROBE_ITEMS)],
    }


def _parse_int_list(value):
    if not isinstance(value, list):
        return []
    result = []
    for raw in value:
        try:
            number = int(raw)
        except (TypeError, ValueError):
            continue
        if 1 <= number <= MAX_CHARACTERS and number not in result:
            result.append(number)
    return result


def _normalise_items(value):
    try:
        value = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        value = None
    if not isinstance(value, dict):
        value = {}
    raw_items = value.get("items")
    if not isinstance(raw_items, list):
        raw_items = value.get("wardrobe_items")
    if not isinstance(raw_items, list):
        raw_items = []

    items = []
    for raw in raw_items[:MAX_WARDROBE_ITEMS]:
        raw = raw if isinstance(raw, dict) else {}
        images = raw.get("images") if isinstance(raw.get("images"), list) else []
        if not images and isinstance(raw.get("image"), dict):
            images = [raw["image"]]
        clean_images = [image for image in images
                        if isinstance(image, dict) and (image.get("name") or image.get("b64"))]
        assignments = raw.get("character_slots", raw.get("characters", []))
        category = str(raw.get("category") or WARDROBE_CATEGORIES[0]).strip()
        if category not in WARDROBE_CATEGORIES:
            category = WARDROBE_CATEGORIES[0]
        items.append({
            "images": clean_images[:1],
            "description": str(raw.get("description") or "").strip(),
            "category": category,
            "character_slots": _parse_int_list(assignments),
        })
    while len(items) < MAX_WARDROBE_ITEMS:
        items.append(_empty_item())
    return items


def _load_item_image(image):
    """Read one uploaded item image without failing the entire wardrobe payload."""
    try:
        if image.get("name"):
            path = media.resolve_input_path(image["name"])
            if path:
                return Image.open(path).convert("RGB")
        encoded = image.get("b64") or ""
        if encoded:
            encoded = encoded.split(",", 1)[1] if "," in encoded else encoded
            return Image.open(_io.BytesIO(base64.b64decode(encoded))).convert("RGB")
    except Exception:
        return None
    return None


def _write_wardrobe_collage(images):
    """Create one compact reference image containing all items for one character."""
    if not images:
        return None
    rows = int(math.ceil(len(images) / float(COLLAGE_COLUMNS)))
    width = COLLAGE_COLUMNS * COLLAGE_TILE
    height = rows * COLLAGE_TILE
    collage = Image.new("RGB", (width, height), (24, 24, 24))
    draw = ImageDraw.Draw(collage)
    for index, image in enumerate(images):
        row, column = divmod(index, COLLAGE_COLUMNS)
        x, y = column * COLLAGE_TILE, row * COLLAGE_TILE
        fitted = ImageOps.contain(image, (COLLAGE_TILE - 16, COLLAGE_TILE - 28))
        paste_x = x + (COLLAGE_TILE - fitted.width) // 2
        paste_y = y + 20 + (COLLAGE_TILE - 20 - fitted.height) // 2
        collage.paste(fitted, (paste_x, paste_y))
        draw.rectangle((x + 5, y + 5, x + 24, y + 20), fill=(0, 0, 0))
        draw.text((x + 10, y + 7), str(index + 1), fill=(255, 255, 255))

    output_dir = os.path.join(folder_paths.get_input_directory(), "whatdreamscost")
    os.makedirs(output_dir, exist_ok=True)
    filename = "wardrobe_collage_%s.jpg" % uuid.uuid4().hex
    path = os.path.join(output_dir, filename)
    collage.save(path, format="JPEG", quality=92, optimize=True)
    return {"name": "whatdreamscost/%s" % filename}


def _build_wardrobe_collages(active_characters, items):
    collages = []
    for character_slot in range(1, len(active_characters) + 1):
        assigned_items = [
            item for item in items
            if character_slot in item.get("character_slots", []) and item.get("images")
        ]
        source_images = []
        descriptions = []
        anatomy_descriptions = []
        for item in assigned_items:
            image = _load_item_image(item["images"][0])
            if image is not None:
                source_images.append(image)
            if item.get("description"):
                if item.get("category") == "Anatomy":
                    anatomy_descriptions.append(item["description"])
                else:
                    descriptions.append(item["description"])
        collage = _write_wardrobe_collage(source_images)
        if collage is None:
            continue
        collages.append({
            "character_slot": character_slot,
            "images": [collage],
            "description": "; ".join(descriptions),
            "anatomy_description": "; ".join(anatomy_descriptions),
            "item_count": len(source_images),
        })
    return collages


class MiniMaxH3WardrobeDirector(io.ComfyNode):
    """Assign wardrobe reference images and item descriptions to cast members."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3WardrobeDirectorPlusCS",
            display_name="MiniMax H3 Wardrobe Director Plus",
            category="MiniMax H3",
            description=(
                "Assign clothing and accessory reference images to characters from a "
                "Casting Director. Connect CAST + WARDROBE to the Director's cast input."
            ),
            inputs=[
                io.String.Input(
                    "cast_wardrobe", force_input=True, optional=True,
                    tooltip="CAST + WARDROBE output from MiniMax H3 Casting Director Plus.",
                ),
                io.String.Input(
                    "analyze_settings", force_input=True, optional=True,
                    tooltip="ANALYZE SETTINGS output from Casting Director Plus. Enables item analysis.",
                ),
                io.String.Input(
                    "wardrobe_data", multiline=True, default=json.dumps(_empty_wardrobe()),
                    tooltip="JSON state of the Wardrobe Director UI (auto-managed; do not edit by hand).",
                ),
            ],
            outputs=[
                io.String.Output(
                    display_name="CAST + WARDROBE",
                    tooltip="The connected cast plus assigned wardrobe items for the Director.",
                ),
            ],
        )

    @classmethod
    def execute(cls, cast_wardrobe="", analyze_settings="", wardrobe_data="") -> io.NodeOutput:
        cast = _normalise_cast(cast_wardrobe)
        active_characters = [
            {**character, "hired": True}
            for character in cast["characters"]
            if character.get("hired", True)
        ]
        items = _normalise_items(wardrobe_data)
        items = [
            {
                **item,
                "character_slots": [slot for slot in item["character_slots"]
                                    if slot <= len(active_characters)],
            }
            for item in items
        ]
        wardrobe_collages = _build_wardrobe_collages(active_characters, items)
        payload = {
            "version": 2,
            "characters": active_characters,
            "wardrobe_items": items,
            "wardrobe_collages": wardrobe_collages,
        }
        return io.NodeOutput(json.dumps(payload, separators=(",", ":")))


NODE_CLASS_MAPPINGS = {"MiniMaxH3WardrobeDirectorPlusCS": MiniMaxH3WardrobeDirector}
NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxH3WardrobeDirectorPlusCS": "MiniMax H3 Wardrobe Director Plus",
}
