"""Standalone character/cast editor for MiniMax H3 Director Plus."""

import json

from comfy_api.latest import io


def _empty_cast():
    return {
        "version": 1,
        "characters": [
            {"images": [], "description": ""},
            {"images": [], "description": ""},
            {"images": [], "description": ""},
        ],
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
        for item in characters[:3]:
            item = item if isinstance(item, dict) else {}
            images = item.get("images") if isinstance(item.get("images"), list) else []
            result["characters"].append({
                "images": images,
                "description": str(item.get("description") or ""),
            })
        while len(result["characters"]) < 3:
            result["characters"].append({"images": [], "description": ""})

    for key in ("analyzeProvider", "analyzeBaseUrl", "analyzeModel", "analyzeApiKey"):
        if value.get(key) is not None:
            result[key] = str(value.get(key) or "")
    return result


class MiniMaxH3CastingDirector(io.ComfyNode):
    """Three reusable character slots that can feed a MiniMax H3 Director."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3CastingDirectorPlusCS",
            display_name="MiniMax H3 Casting Director Plus",
            category="MiniMax H3",
            description=(
                "Create up to three reusable character references. Connect CAST to the "
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
        payload = {"version": value["version"], "characters": value["characters"]}
        return io.NodeOutput(json.dumps(payload, separators=(",", ":")))


NODE_CLASS_MAPPINGS = {"MiniMaxH3CastingDirectorPlusCS": MiniMaxH3CastingDirector}
NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxH3CastingDirectorPlusCS": "MiniMax H3 Casting Director Plus",
}
