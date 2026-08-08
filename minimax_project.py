"""Shared project selector for MiniMax H3 Director Plus workflows."""

import json

from comfy_api.latest import io

from .minimax_projects import ensure_project, normalise_project_name


class MiniMaxH3DirectorProject(io.ComfyNode):
    """Select or create one project for the connected Director nodes."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3DirectorProjectPlusCS",
            display_name="MiniMax H3 Director Project Plus",
            category="MiniMax H3",
            description=(
                "Select or create a shared project. Connect PROJECT DATA to the optional "
                "project inputs on Casting Director, Wardrobe Director, Location Scout, "
                "or the main Director."
            ),
            inputs=[
                io.String.Input(
                    "project_name", default="", optional=True,
                    tooltip="Project name selected by the project editor.",
                ),
            ],
            outputs=[
                io.String.Output(
                    display_name="PROJECT DATA",
                    tooltip="Project name, saved sources, resource metadata, and timestamps.",
                ),
            ],
        )

    @classmethod
    def execute(cls, project_name="") -> io.NodeOutput:
        name = str(project_name or "").strip()
        if not name:
            return io.NodeOutput(json.dumps({
                "version": 1,
                "project_name": "",
                "sources": {},
                "resources": [],
            }, separators=(",", ":")))
        document = ensure_project(normalise_project_name(name))
        return io.NodeOutput(json.dumps(document, separators=(",", ":")))


NODE_CLASS_MAPPINGS = {"MiniMaxH3DirectorProjectPlusCS": MiniMaxH3DirectorProject}
NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxH3DirectorProjectPlusCS": "MiniMax H3 Director Project Plus",
}
