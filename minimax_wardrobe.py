"""Wardrobe item editor for MiniMax H3 Director Plus."""

import json

from comfy_api.latest import io

from .minimax_casting import MAX_CHARACTERS, _normalise_cast

MAX_WARDROBE_ITEMS = 9


def _empty_item():
    return {"images": [], "description": "", "character_slots": []}


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
        items.append({
            "images": clean_images[:1],
            "description": str(raw.get("description") or "").strip(),
            "character_slots": _parse_int_list(assignments),
        })
    while len(items) < MAX_WARDROBE_ITEMS:
        items.append(_empty_item())
    return items


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
    def execute(cls, cast_wardrobe="", wardrobe_data="") -> io.NodeOutput:
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
        payload = {
            "version": 2,
            "characters": active_characters,
            "wardrobe_items": items,
        }
        return io.NodeOutput(json.dumps(payload, separators=(",", ":")))


NODE_CLASS_MAPPINGS = {"MiniMaxH3WardrobeDirectorPlusCS": MiniMaxH3WardrobeDirector}
NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxH3WardrobeDirectorPlusCS": "MiniMax H3 Wardrobe Director Plus",
}
