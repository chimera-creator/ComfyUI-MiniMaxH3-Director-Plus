"""Standalone character/cast editor for MiniMax H3 Director Plus."""

import json

from comfy_api.latest import io

MAX_CHARACTERS = 9


def _empty_character():
    return {"images": [], "description": "", "hired": False}


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
                "description": str(item.get("description") or ""),
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
            ],
            outputs=[
                io.String.Output(
                    display_name="CAST",
                    tooltip="Character references and descriptions for MiniMax H3 Director Plus.",
                ),
            ],
        )

    @classmethod
    def execute(cls, cast_data="") -> io.NodeOutput:
        value = _normalise_cast(cast_data)
        # Analyzer settings stay local to this node; the graph only needs the reusable
        # character payload and should not carry an API key into the Director socket.
        payload = {"version": value["version"], "characters": [
            {
                **character,
                "images": character["images"] if character.get("hired", True) else [],
                "description": character["description"] if character.get("hired", True) else "",
            }
            for character in value["characters"]
        ]}
        return io.NodeOutput(json.dumps(payload, separators=(",", ":")))


NODE_CLASS_MAPPINGS = {"MiniMaxH3CastingDirectorPlusCS": MiniMaxH3CastingDirector}
NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxH3CastingDirectorPlusCS": "MiniMax H3 Casting Director Plus",
}
