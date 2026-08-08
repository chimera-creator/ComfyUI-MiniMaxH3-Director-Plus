from comfy_api.latest import ComfyExtension, io
from typing_extensions import override

from .minimax_director import MiniMaxH3Director
from .minimax_casting import MiniMaxH3CastingDirector
from .minimax_wardrobe import MiniMaxH3WardrobeDirector
from .minimax_enhance import MiniMaxH3EnhancePrompt
from .minimax_preview import MiniMaxH3PreviewOverride
from .minimax_retake import MiniMaxH3RetakeStitch

# MiniMaxH3DirectorChain is deliberately NOT registered — see minimax_chain.py.
# The backend works; there is no usable way to give it a timeline, so it is withdrawn
# rather than shipped as a feature nobody can operate.


class MiniMaxH3DirectorExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [MiniMaxH3Director, MiniMaxH3CastingDirector, MiniMaxH3WardrobeDirector,
                MiniMaxH3PreviewOverride,
                MiniMaxH3RetakeStitch, MiniMaxH3EnhancePrompt]


async def comfy_entrypoint() -> MiniMaxH3DirectorExtension:
    return MiniMaxH3DirectorExtension()


NODE_CLASS_MAPPINGS = {
    "MiniMaxH3DirectorPlusCS": MiniMaxH3Director,
    "MiniMaxH3CastingDirectorPlusCS": MiniMaxH3CastingDirector,
    "MiniMaxH3WardrobeDirectorPlusCS": MiniMaxH3WardrobeDirector,
    "MiniMaxH3PreviewOverridePlusCS": MiniMaxH3PreviewOverride,
    "MiniMaxH3RetakeStitchPlusCS": MiniMaxH3RetakeStitch,
    "MiniMaxH3EnhancePromptPlusCS": MiniMaxH3EnhancePrompt,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxH3DirectorPlusCS": "MiniMax H3 Director Plus",
    "MiniMaxH3CastingDirectorPlusCS": "MiniMax H3 Casting Director Plus",
    "MiniMaxH3WardrobeDirectorPlusCS": "MiniMax H3 Wardrobe Director Plus",
    "MiniMaxH3PreviewOverridePlusCS": "MiniMax H3 Preview Override Plus",
    "MiniMaxH3RetakeStitchPlusCS": "MiniMax H3 Retake Stitch Plus",
    "MiniMaxH3EnhancePromptPlusCS": "MiniMax H3 Enhance Prompt Plus",
}

WEB_DIRECTORY = "./js"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
