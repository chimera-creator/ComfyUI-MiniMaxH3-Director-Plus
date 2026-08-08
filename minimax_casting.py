"""Standalone character/cast editor for MiniMax H3 Director Plus."""

import json

from comfy_api.latest import io

from .minimax_context import MiniMaxH3Context, make_context, project_details
from .minimax_projects import project_source_data

MAX_CHARACTERS = 9
PRONOUN_OPTIONS = ("auto", "he", "she", "they")


def _normalise_pronouns(value):
    value = str(value or "auto").strip().lower()
    aliases = {
        "he/him": "he", "him": "he", "his": "he",
        "she/her": "she", "her": "she", "hers": "she",
        "they/them": "they", "them": "they", "their": "they",
    }
    value = aliases.get(value, value)
    return value if value in PRONOUN_OPTIONS else "auto"


def _empty_character():
    return {
        "images": [], "appearance": "", "wardrobe": "", "description": "",
        "pronouns": "auto", "hired": False,
    }


def _merge_character_description(item):
    appearance = str(item.get("appearance") or "").strip()
    wardrobe = str(item.get("wardrobe") or "").strip()
    if appearance or wardrobe:
        return " ".join(part for part in (appearance, wardrobe) if part)
    return str(item.get("description") or "").strip()


def _is_hired(value, default=True):
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "off", "no"}
    return bool(value)


def _empty_cast():
    return {
        "version": 1,
        "characters": [_empty_character() for _ in range(MAX_CHARACTERS)],
        "analyzeProvider": "ollama",
        "analyzeBaseUrl": "",
        "analyzeModel": "",
        "analyzeApiKey": "",
    }


def _active_cast_payload(value):
    """Return the compact cast shape used by both CAST outputs."""
    return {
        "version": value["version"],
        "characters": [
            {
                **character,
                # Keep the old Director-facing field populated for workflows and
                # integrations that only know about `description`.
                "description": _merge_character_description(character),
                "hired": True,
            }
            for character in value["characters"]
            if character.get("hired", True)
        ],
    }


def _cast_context(payload):
    lines = [
        "Use the supplied cast references and descriptions when writing the video prompt.",
        "Cast reference images are labeled <image N> in the order listed below.",
    ]
    image_number = 0
    for character_number, character in enumerate(payload.get("characters", []), start=1):
        description = str(character.get("description") or "").strip()
        images = character.get("images") if isinstance(character.get("images"), list) else []
        if images:
            for _image in images:
                image_number += 1
                suffix = (": " + description) if description else ": cast reference image"
                lines.append("<image %d> cast character %d%s" %
                             (image_number, character_number, suffix))
        elif description:
            lines.append("Cast character %d: %s" % (character_number, description))
    return "\n".join(lines)


def _normalise_cast(cast_data):
    try:
        value = json.loads(cast_data) if isinstance(cast_data, str) else cast_data
    except (TypeError, ValueError):
        value = None
    if not isinstance(value, dict):
        return _empty_cast()

    result = _empty_cast()
    characters = value.get("characters")
    if isinstance(characters, list):
        result["characters"] = []
        for item in characters[:MAX_CHARACTERS]:
            item = item if isinstance(item, dict) else {}
            images = item.get("images") if isinstance(item.get("images"), list) else []
            result["characters"].append({
                "images": images,
                "appearance": str(item.get("appearance") or ""),
                "wardrobe": str(item.get("wardrobe") or ""),
                "description": _merge_character_description(item),
                "pronouns": _normalise_pronouns(item.get("pronouns", item.get("pronoun"))),
                # Casts saved before the hire toggle existed remain active.
                "hired": _is_hired(item.get("hired")),
            })
        while len(result["characters"]) < MAX_CHARACTERS:
            result["characters"].append(_empty_character())

    for key in ("analyzeProvider", "analyzeBaseUrl", "analyzeModel", "analyzeApiKey"):
        if value.get(key) is not None:
            result[key] = str(value.get(key) or "")
    return result


class MiniMaxH3CastingDirector(io.ComfyNode):
    """Nine reusable character slots that can feed a MiniMax H3 Director."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3CastingDirectorPlusCS",
            display_name="MiniMax H3 Casting Director Plus",
            category="MiniMax H3",
            description=(
                "Create up to nine reusable character references. Connect CAST to the "
                "MiniMax H3 Director Plus cast input; the Director keeps its own slots "
                "as a backward-compatible fallback when CAST is not connected."
            ),
            inputs=[
                io.String.Input(
                    "cast_data", multiline=True, default=json.dumps(_empty_cast()),
                    tooltip="JSON state of the Casting Director UI (auto-managed; do not edit by hand).",
                ),
                io.String.Input(
                    "project", force_input=True, optional=True,
                    tooltip="Optional PROJECT DATA output. Loads the saved casting source when present.",
                ),
            ],
            outputs=[
                io.String.Output(
                    display_name="CAST",
                    tooltip="Character references and descriptions for MiniMax H3 Director Plus.",
                ),
                io.String.Output(
                    display_name="CAST + WARDROBE",
                    tooltip="Character references plus wardrobe-item assignments for Wardrobe Director.",
                ),
                io.String.Output(
                    display_name="ANALYZE SETTINGS",
                    tooltip="Provider, model, URL, and optional API key for Casting/Wardrobe analysis.",
                ),
                io.String.Output(
                    display_name="CONTEXT",
                    tooltip="Cast descriptions and ordered cast image context for Enhance Prompt.",
                ),
                MiniMaxH3Context.Output(
                    display_name="CONTEXT DATA",
                    tooltip="Typed cast context with ordered image references and project asset paths for Enhance Prompt.",
                ),
            ],
        )

    @classmethod
    def execute(cls, cast_data="", project="") -> io.NodeOutput:
        saved = project_source_data(project, "casting")
        if isinstance(saved, dict):
            saved_cast = saved.get("cast_data")
            if not saved_cast and isinstance(saved.get("widgets"), dict):
                saved_cast = saved["widgets"].get("cast_data")
            if saved_cast:
                cast_data = saved_cast
        value = _normalise_cast(cast_data)
        project_info = project_details(project)
        # Analyzer settings stay local to this node; the graph only needs the reusable
        # character payload and should not carry an API key into the Director socket.
        payload = _active_cast_payload(value)
        if project_info.get("path"):
            # Preserve the selected project through CAST -> Wardrobe -> Location even
            # when those nodes are not separately connected to the Project node.
            payload["project"] = project_info
        cast_json = json.dumps(payload, separators=(",", ":"))
        # The second socket deliberately starts with an empty item list. The Wardrobe
        # Director owns item state; this socket is the stable cast hand-off into it.
        wardrobe_json = json.dumps({**payload, "wardrobe_items": []}, separators=(",", ":"))
        analyze_settings = json.dumps({
            "provider": value.get("analyzeProvider", "ollama"),
            "base_url": value.get("analyzeBaseUrl", ""),
            "model": value.get("analyzeModel", ""),
            "api_key": value.get("analyzeApiKey", ""),
        }, separators=(",", ":"))
        image_refs = [
            image
            for character in payload.get("characters", [])
            for image in (character.get("images") or [])
            if isinstance(image, dict)
        ]
        context_data = make_context(
            prompt_context=_cast_context(payload),
            images=image_refs,
            project=project_info,
            sources={"cast": payload},
        )
        return io.NodeOutput(cast_json, wardrobe_json, analyze_settings,
                             _cast_context(payload), context_data)


NODE_CLASS_MAPPINGS = {"MiniMaxH3CastingDirectorPlusCS": MiniMaxH3CastingDirector}
NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxH3CastingDirectorPlusCS": "MiniMax H3 Casting Director Plus",
}
