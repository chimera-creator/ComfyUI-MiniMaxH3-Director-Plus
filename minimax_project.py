"""Shared project selector for MiniMax H3 Director Plus workflows."""

import json
import os

from comfy_api.latest import io

from .minimax_projects import (
    PROJECTS_DIR,
    ensure_project,
    load_project_at_path,
    normalise_project_name,
    normalise_projects_path,
)


class MiniMaxH3DirectorProject(io.ComfyNode):
    """Select or create one project for the connected Director nodes."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3DirectorProjectPlusCS",
            display_name="MiniMax H3 Director Project Plus",
            category="MiniMax H3",
            description=(
                "Select a Projects root and create one named project folder. Connect PROJECT DATA to the optional "
                "project inputs on Casting Director, Wardrobe Director, Location Scout, "
                "or the main Director."
            ),
            inputs=[
                io.String.Input(
                    "project_name", default="", optional=True,
                    tooltip="Project name selected by the project editor.",
                ),
                io.String.Input(
                    "projects_path", default=PROJECTS_DIR, optional=True,
                    tooltip="Absolute Projects root. Each project is stored in its own named folder below this path.",
                ),
                io.String.Input(
                    "project_path", default="", optional=True,
                    tooltip="Legacy exact project-folder path. New workflows should use projects_path.",
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
    def execute(cls, project_name="", projects_path=PROJECTS_DIR, project_path="") -> io.NodeOutput:
        name = str(project_name or "").strip()
        root = str(projects_path or "").strip()
        legacy_path = str(project_path or "").strip()
        if not root and legacy_path:
            root = legacy_path
        if legacy_path:
            existing = load_project_at_path(legacy_path)
            if existing and (not projects_path or
                             os.path.abspath(os.path.expanduser(str(projects_path))) == os.path.abspath(PROJECTS_DIR)):
                root = str(existing.get("projects_path") or os.path.dirname(legacy_path))
                name = name or str(existing.get("project_name") or "").strip()
        root = normalise_projects_path(root or PROJECTS_DIR)
        if not name:
            return io.NodeOutput(json.dumps({
                "version": 2,
                "project_name": "",
                "projects_path": root,
                "project_root": root,
                "project_path": "",
                "sources": {},
                "resources": [],
            }, separators=(",", ":")))
        document = ensure_project(normalise_project_name(name), projects_path=root)
        return io.NodeOutput(json.dumps(document, separators=(",", ":")))


NODE_CLASS_MAPPINGS = {"MiniMaxH3DirectorProjectPlusCS": MiniMaxH3DirectorProject}
NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxH3DirectorProjectPlusCS": "MiniMax H3 Director Project Plus",
}
