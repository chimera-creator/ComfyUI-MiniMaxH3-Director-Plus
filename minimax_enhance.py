"""MiniMax H3 Enhance Prompt — a local vision model writes the prompt from your references.

The node hands up to nine reference images plus a one-line wish to Ollama / LM Studio /
any OpenAI-compatible endpoint, and returns text meant for the Director's `global_prompt`
input. The same images come back out of `ref_images`, and `director_json` carries the
parsed duration, shots, guide fields, and ordered reference manifest for the Director.

The default Full H3 preset gives the model the Director's exact ordered reference manifest
and asks for a terminal JSON object. The response is normalized against the real context,
so model-generated numbering can never reorder the images sent through `ref_images`.
Legacy global/storyboard presets retain their original section/reference cleanup.
"""
import logging
import re
import base64
import io as _io
import json

import numpy as np
import torch
from aiohttp import web
from PIL import Image

from comfy_api.latest import io
from server import PromptServer

from . import minimax_media as media
from .minimax_context import normalise_context, reference_tensors, MiniMaxH3Context
from .minimax_core import extra
from .minimax_prompt_data import build_director_payload, extract_audio_music, parse_json

log = logging.getLogger(__name__)

MAX_IMAGES = 9          # matches plan.MAX_REF_IMAGES (ref2va path, from the model card)

PRESET_FULL = "Full H3 Prompt to Director"
PRESET_GLOBAL = "global (scene + style)"
PRESET_STORYBOARD = "storyboard (shots + timings)"

# Length guidance below is the model card's own: "For generation tasks, detailed_description
# is normally 350-500 English words." When the timeline carries no shot text, the global
# prompt IS the whole detailed_description, so it needs that length rather than a lead-in.
_CAMERA = """CAMERA VOCABULARY - use only these motion types:
Zoom In, Zoom Out, Push In, Pull Out, Pan Left, Pan Right, Truck Left, Truck Right,
Tilt Up, Tilt Down, Pedestal Up, Pedestal Down, Arc Shot, Tracking Shot, Static Shot,
Shake Slightly, Shake Strongly, POV, Roll Clockwise, Roll Counterclockwise.
Add amplitude ("with small amplitude" / "with large amplitude") and speed ("at slow speed" /
"at fast speed") only when they carry meaning. Camera motion is written as a natural English
action within the shot, never stacked as separate labels at the end of a sentence.
Example: "The camera pushes in with small amplitude at slow speed toward the folded letter
in her hands."
"""

_AUDIO = """AUDIO
End with exactly two lines, in this order, as the last two lines, with no blank line
between them and nothing after them.

The first line starts with "Audio: " and then one to four sentences of ambience, physical
action sounds and non-verbal human sounds - wind, rain, traffic, footsteps, fabric,
impacts, breathing, laughter. No dialogue, no singing, no diegetic music. Write "Audio: N/A"
only if total silence was asked for.

The second line starts with "Music: " and then one to three sentences describing score the
characters cannot hear: instrumentation, tempo, rhythm, dynamic change. No mood words, no
explanation of what the music conveys. Write "Music: N/A" if there should be no score.

Write the sentences directly after the colon. Do not wrap them in angle brackets, braces,
parentheses or quotation marks.
"""

_FORBIDDEN = """NEVER WRITE
- Any section label: subject_definitions, summary, retention_analysis,
  detailed_description, integrated_multimodal_description, overall_soundscape,
  non_diegetic_music. A separate tool adds them; a second set would nest structure inside
  structure.
- <Picture 1>, <Subject 1>, <Video 1>, <Audio 1> or any numbered reference tag. That tool
  assigns the numbers and yours would collide with them.
- Talk about the input: no "Image 1 shows", no "in the second photo", no "the reference
  images". Describe what is in them.
- Markdown of any kind: no headings, bullets, bold, code fences, no wrapping quotes.
- Any preamble, commentary, question, apology or explanation of your choices.

OUTPUT
Only the prompt text. Nothing before it, nothing after it.
"""

SYSTEM_FULL = """You write a complete full-reference MiniMax-H3 prompt package for a Director node.

Use every supplied character, final wardrobe, location, concept, and ordered picture
reference. A <Picture N> tag always identifies the Nth image in the supplied batch. Never
renumber, omit, swap, or invent picture tags. Refer to recurring people as <Subject N>
after binding each subject to its cast picture.

Write these six sections in this exact order: subject_definitions, summary,
retention_analysis, detailed_description, overall_soundscape, non_diegetic_music. The
detailed_description must describe visual style, framing, subjects, final clothing,
environment, lighting, actions, state changes, camera behavior, physical sound, and
dialogue in playback order. Use the MiniMax shot notation requested by the supplied guide.
Keep every shot inside the target duration and make later shot start times strictly increase.
Keep the detailed description to about {budget} English words.

Write the six-section H3 prompt first. Then write the literal marker DIRECTOR_JSON: and one
valid JSON object matching the supplied schema. Put all six complete section values in that
object. The JSON must use double-quoted keys and strings, no comments, no trailing commas,
no markdown fence, and no text after its closing brace. Do not summarize or contradict the
prose. The application validates the object, derives timeline segments from
detailed_description, and attaches the actual image data before sending it to the Director.
"""

SYSTEM_GLOBAL = """You write the opening block of a MiniMax-H3 video prompt.

You receive reference images and a short, informal wish from the user. Your output is
inserted verbatim into a larger, already-structured MiniMax prompt that a separate tool
compiles. That tool adds every section label, the shot markers, all timestamps and all
reference numbering. You write only the opening block.

LENGTH
About {budget} English words for the description, then the two audio lines. Stop there.

FORM
One or two paragraphs of flowing English prose. Never a list. Never a heading. The words
below name what the prose has to cover - they are not labels to print. Writing "Style and
format:" or "Lighting:" into your answer is wrong; write the sentence instead.

Open by naming the visual style and format, chosen from: Cinematic, live-action,
2D-animated, 3D CG, claymation, watercolor, vintage film - derived from the reference
images when they show one. Then the opening framing and composition, e.g. "a medium-wide
shot frames ...". Then the subjects: for every person, animal or object that matters,
the visible identity - age, build, hair, face, clothing with colours, distinctive props.
Describe them in words; never number them. Then the environment: location, key props, time
of day, weather. Then the lighting: direction, hardness, colour temperature, visible
practical sources. Then the actions and state changes, and finally how the camera behaves,
written as a natural English action inside the sentence.

Every detail must correspond to something visible or audible. Do not write intentions,
feelings, symbolism or backstory, and do not reduce the text to a plot summary.

ON-SCREEN TEXT
Any sign, banner, label or subtitle actually visible goes in English double quotation
marks, verbatim and untranslated: A red neon sign reading "OPEN" glows above the doorway.

%s
%s
%s""" % (_CAMERA, _AUDIO, _FORBIDDEN)

SYSTEM_STORYBOARD = """You write the shot-by-shot body of a MiniMax-H3 video prompt.

You receive reference images, a short informal wish from the user, and the target duration
of the video in seconds. Your output is inserted verbatim into a larger, already-structured
MiniMax prompt. The surrounding tool adds every section label and all reference numbering.
You write the shot sequence and nothing else.

OPENING
Begin with one or two sentences establishing style and initial composition, before the
first shot marker. Style is one of: Cinematic, live-action, 2D-animated, 3D CG, claymation,
watercolor, vintage film - derived from the reference images when they show one.

SHOT NOTATION
- First shot: "[Shot 1] " with NO timestamp.
- Every later shot: "[Shot N] At MM:SS.mmm, " - two-digit minutes, two-digit seconds,
  three-digit milliseconds. Example: "[Shot 2] At 00:03.500, the camera cuts to a close-up
  of steam rising from the sliced bread."
- Cut times strictly increase and all fall inside the given duration.
- Shots follow each other as continuous prose separated by a single space. No line breaks
  between shots, no list, no numbering other than the [Shot N] marker.

WHEN TO CUT
A cut should introduce new information about the subject, space, state, viewpoint, or time.
If only the distance or a slight angle needs to change, prefer camera motion. A five-second
video is usually one or two shots.
Cut wording: "the camera cuts to", "the shot cuts to", "the shot transitions to", "the shot
changes to", "the shot switches to". Use cross-dissolve, fade or wipe only when asked for.

WHAT EACH SHOT MUST ESTABLISH, in this order:
composition -> subject appearance and position -> environment and lighting -> actions and
state changes -> camera movement -> current sound.
These name what the prose has to cover; they are not labels to print. Never write
"composition:" or "lighting:" into your answer - write the sentence instead.

LENGTH
About {budget} English words in total. Dialogue-dense content prioritises fitting the
complete spoken timeline over reaching a word count.

ON-SCREEN TEXT
Any sign, banner, label or subtitle actually visible goes in English double quotation
marks, verbatim and untranslated.

%s
%s
%s""" % (_CAMERA, _AUDIO, _FORBIDDEN)

_SYSTEM = {
    PRESET_FULL: SYSTEM_FULL,
    PRESET_GLOBAL: SYSTEM_GLOBAL,
    PRESET_STORYBOARD: SYSTEM_STORYBOARD,
}

# The guide's own figure, used when the budget is switched off.
_GUIDE_WORDS = "350 to 500"


SYSTEM_AUDIO_ONLY = """You add the two sound lines to a video prompt.

You are given the finished visual description of a video. Reply with exactly two lines and
nothing else.

The first line starts with "Audio: " and then one to four sentences of ambience, physical
action sounds and non-verbal human sounds that fit that description - wind, rain, traffic,
footsteps, fabric, impacts, breathing, laughter. No dialogue, no singing, no diegetic music.

The second line starts with "Music: " and then one to three sentences describing score the
characters cannot hear: instrumentation, tempo, rhythm, dynamic change. No mood words, no
explanation of what the music conveys.

No preamble, no commentary, no markdown, no quotation marks, no angle brackets. Two lines,
then stop."""


SYSTEM_SPICY = """You are the second-pass editor for a MiniMax-H3 video prompt.

Rewrite the supplied first-pass prompt to add vivid, sensual, flirtatious and mature detail
where it fits the visible subjects and requested scenario. Keep the result tasteful,
consensual and adult. Preserve the original identities, setting, shot order, actions,
camera language, timing, reference tags and overall intent. Do not invent minors, coercion,
or unrelated events. Do not add section labels, markdown, commentary or explanations.

Return only the revised prompt text. Preserve the final Audio: and Music: lines, keeping
them as the last two lines in that order.
"""


def system_for(preset, max_words):
    """The preset's instructions with the user's actual word budget filled in.

    Hardcoding "350 to 500" made the widget a lie: the model aimed at 500 whatever the
    setting, and the surplus was silently trimmed afterwards.
    """
    template = _SYSTEM.get(preset, SYSTEM_GLOBAL)
    return template.replace("{budget}", str(int(max_words)) if max_words else _GUIDE_WORDS)


def _full_context_data(context, duration_seconds):
    """Return the Director's canonical cast/reference view for the full preset."""
    return build_director_payload("", duration_seconds, context, PRESET_FULL)


def _reference_without_image(reference):
    if not isinstance(reference, dict):
        return {}
    keep = ("index", "picture", "h3_reference", "source", "character_slot",
            "location_index", "description")
    return {key: reference.get(key) for key in keep if reference.get(key) is not None}


def _full_character_details(context_data):
    subject_definitions = str(context_data.get("subject_definitions") or "").strip()
    cast = context_data.get("cast") if isinstance(context_data.get("cast"), dict) else {}
    references = context_data.get("references") if isinstance(context_data.get("references"), list) else []
    subject_of_slot = {}
    next_subject = 1
    for slot, _character in enumerate(cast.get("characters", []) or [], start=1):
        if any(item.get("source") in ("char", "cast") and
               int(item.get("character_slot", 0) or 0) == slot for item in references):
            subject_of_slot[slot] = next_subject
            next_subject += 1
    lines = [subject_definitions] if subject_definitions else []
    for slot, subject in subject_of_slot.items():
        wardrobe_refs = [item for item in references
                         if item.get("source") == "wardrobe" and
                         int(item.get("character_slot", 0) or 0) == slot]
        if not wardrobe_refs:
            continue
        pictures = " and ".join(item.get("picture") or item.get("h3_reference")
                                for item in wardrobe_refs)
        descriptions = " ".join(str(item.get("description") or "").strip()
                                for item in wardrobe_refs).strip()
        line = "The final wardrobe for <Subject %d> is shown in %s" % (subject, pictures)
        if descriptions:
            line += ": " + descriptions
        if line[-1] not in ".!?":
            line += "."
        lines.append(line)
    return " ".join(lines).strip()


def _merge_model_subjects(authoritative, model_value, references):
    """Keep cast bindings authoritative while retaining safe model-defined extra subjects."""
    authoritative = str(authoritative or "").strip()
    model_value = str(model_value or "").strip()
    if not model_value:
        return authoritative
    valid_pictures = {int(item.get("index") or 0) for item in references
                      if isinstance(item, dict) and int(item.get("index") or 0) > 0}
    cast_subjects = [int(value) for value in re.findall(
        r"<Subject\s+(\d+)>", authoritative, re.I)]
    last_cast_subject = max(cast_subjects) if cast_subjects else 0
    chunks = [chunk.strip() for chunk in re.split(
        r"(?=(?:<Subject|<Picture|<Video|<Audio)\s+\d+>)", model_value, flags=re.I)
              if chunk.strip()]
    extras = []
    for chunk in chunks:
        subject_match = re.match(r"<Subject\s+(\d+)>", chunk, re.I)
        if subject_match and int(subject_match.group(1)) <= last_cast_subject:
            continue
        pictures = {int(value) for value in re.findall(r"<Picture\s+(\d+)>", chunk, re.I)}
        if pictures and not pictures.issubset(valid_pictures):
            continue
        if chunk not in authoritative and chunk not in extras:
            extras.append(chunk)
    return " ".join(part for part in (authoritative, " ".join(extras)) if part).strip()


def _full_location_details(context_data):
    references = context_data.get("references") if isinstance(context_data.get("references"), list) else []
    lines = []
    for reference in references:
        if reference.get("source") not in ("location", "set", "sets"):
            continue
        picture = reference.get("picture") or reference.get("h3_reference")
        if not picture:
            continue
        description = str(reference.get("description") or "").strip()
        line = "%s is a location for the sequence" % picture
        if description:
            line += ": " + description
        if line[-1] not in ".!?":
            line += "."
        lines.append(line)
    return "\n".join(lines)


def build_full_h3_request(idea, context, guide, duration_seconds):
    """Build the exact first-pass request used by Full H3 Prompt to Director."""
    context_data = _full_context_data(context, duration_seconds)
    references = [_reference_without_image(item)
                  for item in context_data.get("references", [])]
    duration = max(0.1, float(duration_seconds or 0.1))
    character_details = _full_character_details(context_data) or "No cast characters were supplied."
    location_details = _full_location_details(context_data) or "No location references were supplied."
    concept = str(idea or "").strip() or "Describe what these images show as a video."
    schema = {
        "version": 1,
        "duration_seconds": duration,
        "subject_definitions": context_data.get("subject_definitions", ""),
        "summary": "[reference generation] One short paragraph describing the target video and reference roles.",
        "retention_analysis": context_data.get("retention_analysis", ""),
        "detailed_description": (
            "Opening style and composition. [Shot 1] Shot action, camera behavior, "
            "state changes, sound, and dialogue in playback order."
        ),
        "overall_soundscape": "Ambience and physical sounds across the full video.",
        "non_diegetic_music": "Audience-only instrumentation, tempo, and dynamics, or N/A.",
        # These derived fields make the model's timing intent explicit. Enhance validates
        # them against detailed_description and rebuilds the final timeline JSON.
        "global_prompt": "Opening style, composition, subjects, and location.",
        "shots": [{
            "number": 1, "start": 0.0, "end": duration, "length": duration,
            "prompt": "Shot action, camera behavior, state changes, and audible events.",
        }],
        "references": references,
    }
    return (
        "This is the character details:\n%s\n\n"
        "Location details:\n%s\n\n"
        "Concept:\n%s\n\n"
        "Follow this guide completely for how to write the prompt in the correct format:\n%s\n\n"
        "End the response with DIRECTOR_JSON: followed by one valid JSON object with this "
        "exact field structure. Replace the example prompt values with the finished result. "
        "Keep the supplied reference entries in this exact order; do not add, remove, or "
        "renumber them. The closing brace must be the final character of the response.\n%s"
        % (character_details, location_details, concept, guide,
           json.dumps(schema, indent=2, ensure_ascii=False))
    )


def _extract_response_json(value):
    """Extract a terminal DIRECTOR_JSON object and return it with the preceding prose."""
    text = media.strip_thinking(str(value or "")).strip()
    marker = re.search(r"DIRECTOR_JSON\s*:\s*", text, re.I)
    search_start = marker.end() if marker else 0
    prose = text[:marker.start()].strip() if marker else text
    decoder = json.JSONDecoder()
    starts = [index for index in range(search_start, len(text)) if text[index] == "{"]
    for start in starts:
        try:
            parsed, _end = decoder.raw_decode(text[start:])
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict):
            return parsed, prose
    direct = parse_json(text)
    return (direct, "") if direct else ({}, prose)


def _valid_model_director_json(value):
    if not isinstance(value, dict):
        return False
    required_strings = ("subject_definitions", "summary", "retention_analysis",
                        "detailed_description", "overall_soundscape",
                        "non_diegetic_music")
    if any(not isinstance(value.get(key), str) for key in required_strings):
        return False
    if not isinstance(value.get("shots"), list) or not isinstance(value.get("references"), list):
        return False
    try:
        return float(value.get("duration_seconds")) > 0
    except (TypeError, ValueError):
        return False


_FULL_SECTION = re.compile(
    r"^\s*(subject_definitions|summary|wardrobe_definitions|location_definitions|"
    r"retention_analysis|detailed_description|integrated_multimodal_description|"
    r"overall_soundscape|non_diegetic_music)\s*:\s*",
    re.I | re.M,
)


def _full_text_body(value):
    """Remove outer H3 section wrappers while retaining the generated description."""
    text = str(value or "").strip()
    matches = list(_FULL_SECTION.finditer(text))
    if not matches:
        return text
    sections = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[match.group(1).lower()] = text[match.end():end].strip()
    body = (sections.get("detailed_description") or
            sections.get("integrated_multimodal_description") or "")
    audio = sections.get("overall_soundscape", "")
    music = sections.get("non_diegetic_music", "")
    if audio:
        body = (body + "\nAudio: " + audio).strip()
    if music:
        body = (body + "\nMusic: " + music).strip()
    return body


def _shot_time(value):
    seconds = max(0.0, float(value or 0.0))
    minutes = int(seconds // 60)
    remainder = seconds - minutes * 60
    return "%02d:%06.3f" % (minutes, remainder)


def _body_from_response(model_data, prose, duration_seconds):
    detailed_description = str(model_data.get("detailed_description") or "").strip()
    global_prompt = str(model_data.get("global_prompt") or "").strip()
    shots = model_data.get("shots") if isinstance(model_data.get("shots"), list) else []
    shot_parts = []
    duration = max(0.1, float(duration_seconds or 0.1))
    previous_start = 0.0
    for index, shot in enumerate(shots, start=1):
        if not isinstance(shot, dict):
            continue
        prompt = str(shot.get("prompt") or shot.get("segment_prompt") or "").strip()
        if not prompt:
            continue
        try:
            start = max(0.0, min(duration, float(shot.get("start", 0.0) or 0.0)))
        except (TypeError, ValueError):
            start = previous_start
        start = max(previous_start, start)
        previous_start = start
        number = int(shot.get("number") or index)
        marker = "[Shot %d] " % number if not shot_parts else \
            "[Shot %d] At %s, " % (number, _shot_time(start))
        shot_parts.append(marker + prompt)
    body = detailed_description or \
        "\n\n".join(part for part in (global_prompt, " ".join(shot_parts)) if part)
    if not body:
        body = str(model_data.get("prompt") or prose or "").strip()
    body = _full_text_body(body)
    audio = str(model_data.get("overall_soundscape") or "").strip()
    music = str(model_data.get("non_diegetic_music") or "").strip()
    if audio and not re.search(r"^\s*(?:audio|sound|sfx)\s*:", body, re.I | re.M):
        body += "\nAudio: " + audio
    if music and not re.search(r"^\s*(?:music|score)\s*:", body, re.I | re.M):
        body += "\nMusic: " + music
    return body.strip()


def _clean_full_body(value, max_words=0):
    """Use the storyboard cleaner without deleting valid Director picture/subject tags."""
    text = _full_text_body(value)
    saved = []

    def stash(match):
        saved.append(match.group(0))
        return "MMXREFTAG%dTOKEN" % (len(saved) - 1)

    text = _RE_REFTAG.sub(stash, text)
    text = clean_prompt(text, PRESET_STORYBOARD, max_words=max_words)
    for index, original in enumerate(saved):
        text = text.replace("MMXREFTAG%dTOKEN" % index, original)
    return text


def build_full_director_payload(prompt, model_data, duration_seconds, context):
    """Normalize model JSON to the actual Director contract and real reference order."""
    payload = build_director_payload(prompt, duration_seconds, context, PRESET_FULL)
    payload["summary"] = "[reference generation] The target video uses the supplied ordered references."
    if isinstance(model_data, dict):
        summary = str(model_data.get("summary") or "").strip()
        if summary:
            payload["summary"] = summary
            payload["timeline"]["summary"] = summary
        for key in ("retention_analysis",):
            value = str(model_data.get(key) or "").strip()
            if value:
                payload[key] = value
                payload["timeline"][key] = value
        # With no cast context, retain a model-supplied binding. When context exists, the
        # deterministic binding wins because it is the only source that knows the exact
        # image batch and final Wardrobe Director assignment.
        if not payload.get("subject_definitions"):
            value = str(model_data.get("subject_definitions") or "").strip()
            if value:
                payload["subject_definitions"] = value
                payload["timeline"]["subject_definitions"] = value
    payload["timeline"]["summary"] = payload["summary"]
    character_details = _full_character_details(payload)
    if isinstance(model_data, dict):
        character_details = _merge_model_subjects(
            character_details, model_data.get("subject_definitions"),
            payload.get("references", []),
        )
    if character_details:
        payload["subject_definitions"] = character_details
        payload["timeline"]["subject_definitions"] = character_details
    detailed, _audio, _music = extract_audio_music(prompt)
    payload["detailed_description"] = detailed
    parts = [
        "subject_definitions: " + str(payload.get("subject_definitions") or ""),
        "summary: " + str(payload.get("summary") or ""),
        "retention_analysis: " + str(payload.get("retention_analysis") or ""),
        "detailed_description: " + detailed,
        "overall_soundscape: " + str(payload.get("overall_soundscape") or ""),
        "non_diegetic_music: " + str(payload.get("non_diegetic_music") or ""),
    ]
    payload["full_prompt"] = "\n\n".join(parts)
    payload["model_json_valid"] = _valid_model_director_json(model_data)
    return payload

# --------------------------------------------------------------------------------------
# post-processing: what the model was told not to write, removed when it wrote it anyway
# --------------------------------------------------------------------------------------

_SECTION_LABELS = ("subject_definitions", "summary", "retention_analysis",
                   "detailed_description", "integrated_multimodal_description",
                   "overall_soundscape", "non_diegetic_music")
_RE_FENCE = re.compile(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$")
_RE_LABEL = re.compile(r"^\s*(?:%s)\s*:\s*" % "|".join(_SECTION_LABELS), re.I | re.M)
_RE_REFTAG = re.compile(r"<\s*(?:picture|subject|video|audio|image)\s*\d+\s*>", re.I)
_RE_SHOT = re.compile(r"\[\s*shot\s*\d+\s*\]\s*", re.I)
# "[Shot 1] At 00:00.000," — the guide is explicit that the first shot carries no
# timestamp, and the system prompt says so, but the model writes one anyway often enough
# that it belongs in the filter rather than in more instruction text.
_RE_SHOT1_TIME = re.compile(
    r"(\[\s*shot\s*1\s*\]\s*)At\s+\d{1,2}:\d{2}(?:\.\d{1,3})?\s*,\s*", re.I)
_RE_TIMESTAMP = re.compile(r"\bAt\s+\d{1,2}:\d{2}(?:\.\d{1,3})?\s*,\s*", re.I)
_RE_MD_HEAD = re.compile(r"^\s{0,3}#{1,6}\s*", re.M)
_RE_MD_BULLET = re.compile(r"^\s{0,3}[-*+]\s+", re.M)
_RE_BLANKS = re.compile(r"\n{3,}")
# Instruction words echoed back as labels. Small models answer a numbered brief point by
# point; the system prompt forbids it, this catches the ones that do it anyway.
_RE_ECHO = re.compile(
    r"^\s*(?:style(?: and format)?|form|length|opening framing(?: and composition)?|"
    r"composition|subjects?|environment|lighting|actions?(?: and state changes)?|"
    r"camera(?: movement| behaviour| behavior)?|on-screen text|output)\s*:\s*", re.I | re.M)


def _first_sentences(value, count):
    """Keep at most `count` sentences. The guide allows 1-4 for the soundscape and 1-3 for
    the score; a small model asked for "one to four sentences" wrote 210 words in testing."""
    parts = [p for p in _RE_SENTENCE.split(value.strip()) if p]
    return " ".join(parts[:count]).strip() if len(parts) > count else value.strip()


def _unwrap(value):
    """Strip a bracket or quote pair the model wrapped a value in.

    The system prompt used to show placeholders as <one to four sentences ...>; small
    models copied the angle brackets into the answer. The wording no longer does that,
    but the guard is one line and the failure is silent.
    """
    value = value.strip()
    for opener, closer in (("<", ">"), ("{", "}"), ("[", "]"), ("(", ")"),
                           ('"', '"'), ("'", "'")):
        if len(value) > 1 and value.startswith(opener) and value.endswith(closer):
            value = value[1:-1].strip()
    return value


_RE_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _trim_to_words(text, budget):
    """Cut the body back to `budget` words, ending on a sentence.

    A 9B model told "350 to 500 words" happily wrote 6446 in testing. The token cap on the
    request stops the runaway; this puts the tail on a sentence boundary instead of
    mid-word. The Audio:/Music: lines are extracted before this runs, so trimming can
    never lose them.
    """
    words = text.split()
    if budget <= 0 or len(words) <= budget:
        return text
    kept, used = [], 0
    for sentence in _RE_SENTENCE.split(text):
        n = len(sentence.split())
        if used + n > budget:
            break
        kept.append(sentence)
        used += n
    if not kept:                      # one sentence longer than the whole budget
        return " ".join(words[:budget]).rstrip(",;:") + "."
    return " ".join(kept).strip()


def clean_prompt(text, preset, max_words=0):
    """Strip everything the compiler owns, so the two cannot fight over structure."""
    text = media.strip_thinking(text)
    text = _RE_FENCE.sub("", text).strip()
    text = _RE_LABEL.sub("", text)
    text = _RE_REFTAG.sub("", text)
    text = _RE_MD_HEAD.sub("", text)
    text = _RE_MD_BULLET.sub("", text)
    text = text.replace("**", "")

    if preset != PRESET_STORYBOARD:
        # shot markers and their timestamps belong to the timeline, not to the global block
        text = _RE_SHOT.sub("", text)
        text = _RE_TIMESTAMP.sub("", text)
    else:
        text = _RE_SHOT1_TIME.sub(r"\1", text)
        if text.strip() and not _RE_SHOT.search(text):
            # Storyboard prose with no markers at all is just a global prompt with extra
            # steps — measured in 1 of 4 runs. What it describes *is* one shot, so label
            # it as one and the notation is valid again.
            text = "[Shot 1] " + text.lstrip()

    # a wrapping pair of quotes the model added around the whole answer
    stripped = text.strip()
    if len(stripped) > 2 and stripped[0] in "\"'" and stripped[-1] == stripped[0]:
        text = stripped[1:-1]

    lines = [ln.rstrip() for ln in text.strip().splitlines()]
    # split_audio_music() reads line by line and stops at a blank line, so the Audio: and
    # Music: lines have to sit together at the end with nothing blank between them
    body, audio, music = [], None, None
    for ln in lines:
        low = ln.strip().lower()
        if low.startswith(("audio:", "sound:", "sfx:")) and audio is None:
            head, _, rest = ln.strip().partition(":")
            audio = "%s: %s" % (head.strip(), _first_sentences(_unwrap(rest), 4))
        elif low.startswith(("music:", "score:")) and music is None:
            head, _, rest = ln.strip().partition(":")
            music = "%s: %s" % (head.strip(), _first_sentences(_unwrap(rest), 3))
        else:
            body.append(_RE_ECHO.sub("", ln))
    out = _RE_BLANKS.sub("\n\n", "\n".join(body).strip())
    if max_words:
        out = _trim_to_words(out, max_words)
    tail = [x for x in (audio, music) if x]
    if tail:
        out = (out + "\n" + "\n".join(tail)).strip()
    return out


def _tensor_to_b64(images, max_edge, quality):
    """ComfyUI IMAGE batch -> JPEG base64, downscaled.

    Nine reference frames at full resolution are megabytes of JSON and minutes of VLM
    time; for "describe what you see" a 768 px long edge is plenty.
    """
    from PIL import Image
    import base64
    import io as _io

    out = []
    for frame in images:
        arr = (frame.clamp(0, 1) * 255.0).to(torch.uint8).cpu().numpy()
        img = Image.fromarray(arr)
        if img.mode != "RGB":
            img = img.convert("RGB")
        longest = max(img.width, img.height)
        if max_edge > 0 and longest > max_edge:
            scale = max_edge / float(longest)
            img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))),
                             Image.LANCZOS)
        buf = _io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        out.append(base64.b64encode(buf.getvalue()).decode("ascii"))
    return out


def _collect(images_dict):
    """Autogrow hands over {"image0": tensor, ...}; unconnected slots are simply absent,
    and a connected-but-unresolved one can still be None."""
    if not images_dict:
        return []
    def order(name):
        digits = "".join(ch for ch in name if ch.isdigit())
        return int(digits) if digits else 0
    return [images_dict[k] for k in sorted(images_dict, key=order)
            if images_dict[k] is not None]


class MiniMaxH3EnhancePrompt(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3EnhancePromptPlusCS",
            display_name="MiniMax H3 Enhance Prompt Plus",
            category="MiniMax H3",
            description=(
                "Turns a one-line idea plus typed cast/wardrobe/location context into a MiniMax-H3 prompt, "
                "using a local vision model (Ollama / LM Studio / OpenAI-compatible). "
                "Connect CONTEXT DATA when available; legacy direct image sockets remain "
                "available. Wire `prompt` into the Director's global_prompt and `ref_images` "
                "into its ref_images, so the model describes exactly the images H3 conditions on."
            ),
            inputs=[
                io.Autogrow.Input(
                    "images",
                    io.Autogrow.TemplatePrefix(
                        io.Image.Input("image", optional=True,
                                       tooltip="A reference image. A new socket appears as you "
                                               "connect; disconnecting closes the gap."),
                        prefix="image", min=0, max=MAX_IMAGES),
                    optional=True,
                    tooltip="Up to %d reference images. They are described by the vision model "
                            "and passed straight through to ref_images." % MAX_IMAGES),
                io.String.Input("idea", multiline=True, default="",
                                tooltip="What you want, in plain words. The vision model turns "
                                        "this plus the images into a MiniMax-shaped prompt."),
                io.String.Input("context", multiline=True, default="", optional=True,
                                tooltip="Structured cast, wardrobe, and location context from "
                                        "a Scout or Director node."),
                MiniMaxH3Context.Input(
                    "context_data", optional=True,
                    tooltip="Preferred typed context from Casting, Wardrobe, or Location Scout. "
                            "Carries ordered images, prompt data, and project asset paths.",
                ),
                io.Combo.Input("preset", options=[PRESET_FULL, PRESET_GLOBAL, PRESET_STORYBOARD],
                               default=PRESET_FULL,
                               tooltip="'Full H3 Prompt to Director' combines final cast and "
                                       "wardrobe details, numbered locations, the concept, and "
                                       "the selected system guide, then returns validated "
                                       "Director JSON. Legacy global and storyboard modes remain "
                                       "available for existing workflows."),
                io.String.Input("system_prompt", multiline=True, default="", optional=True,
                                tooltip="Overrides the built-in instructions. Leave empty to use "
                                        "the preset's own, which is derived from MiniMax's "
                                        "prompt-writing guide."),
                io.Float.Input("duration_seconds", default=5.0, min=1.0, max=60.0, step=0.5,
                               optional=True,
                               tooltip="Told to the model so its timestamps fit. Match the "
                                       "Director's duration."),
                io.Combo.Input("provider", options=["ollama", "lmstudio", "custom"],
                               default="ollama", optional=True,
                               tooltip="Where the vision model runs."),
                io.String.Input("base_url", default="", optional=True,
                                tooltip="Empty = the provider's default (Ollama "
                                        "http://127.0.0.1:11434, LM Studio "
                                        "http://127.0.0.1:1234). http:// is added if you "
                                        "leave it off. No path — just host and port."),
                io.String.Input("model", default="", optional=True,
                                tooltip="Model name. Must be a VISION model — a text-only model "
                                        "will ignore your images without saying so. Empty falls "
                                        "back to the provider default."),
                io.String.Input("api_key", default="", optional=True,
                                tooltip="Optional API key for LM Studio or Custom OpenAI-compatible "
                                        "endpoints. Sent as a Bearer token only when present."),
                io.Boolean.Input("use_spicy_model", default=False, optional=True,
                                 tooltip="Run a second pass over the first prompt with a separate "
                                         "model and the spicy system prompt."),
                io.String.Input("spicy_model", default="", optional=True,
                                tooltip="Second-pass model name. Empty reuses the primary model."),
                io.String.Input("spicy_system_prompt", multiline=True, default="", optional=True,
                                tooltip="Optional replacement for the built-in spicy system prompt."),
                io.Int.Input("seed", default=0, min=0, max=0xFFFFFFFFFFFFFFFF,
                             control_after_generate=True, optional=True,
                             tooltip="ComfyUI caches node outputs, so an unchanged input means "
                                     "the model is never asked again. Change this to force a "
                                     "fresh answer."),
                io.Int.Input("max_image_size", default=768, min=128, max=2048, step=64,
                             optional=True,
                             tooltip="Long edge the images are downscaled to before they are "
                                     "sent. Larger costs time and buys little."),
                io.Int.Input("max_words", default=500, min=0, max=2000, step=50,
                             optional=True,
                             tooltip="Hard limit on the description. MiniMax's guide puts a "
                                     "detailed_description at 350-500 words; small models "
                                     "ignore that when asked politely, so the request is "
                                     "capped and the result trimmed to a sentence end. "
                                     "0 disables both."),
                io.Boolean.Input("unload_after", default=True, optional=True,
                                 tooltip="Drop the vision model from VRAM when done, so it is "
                                         "not still resident while H3 samples. Turn off only "
                                         "while iterating on prompts — reloading costs seconds, "
                                         "an OOM costs the render. Ollama only."),
                io.Combo.Input("on_error", options=["passthrough", "fail"],
                               default="passthrough", optional=True,
                               tooltip="'passthrough' hands your raw idea on and warns, so a "
                                       "stopped Ollama does not kill the whole run."),
                io.String.Input("processed_prompt", multiline=True, default="", optional=True,
                                tooltip="Prompt materialized by the Process button. When present, "
                                        "the generation queue reuses it and does not call the LLM "
                                        "again. Clear it and press Process after changing inputs."),
                io.String.Input("processed_director_json", multiline=True, default="", optional=True,
                                tooltip="Director JSON materialized by the Process button. Hidden in the UI "
                                        "and reused with the cached prompt."),
            ],
            outputs=[
                io.String.Output(display_name="prompt",
                                 tooltip="Wire into the Director's global_prompt."),
                io.Image.Output(display_name="ref_images",
                                tooltip="The same images, batched. Wire into the Director's "
                                        "ref_images."),
                io.Float.Output(display_name="duration_seconds",
                                tooltip="The duration you set above, passed on so you only "
                                        "type it once. Wire into the Director's `duration` "
                                        "input (the connection-only one, in seconds)."),
                io.String.Output(display_name="director_json",
                                 tooltip="Director-ready JSON containing duration, shots, guide fields, "
                                         "and ordered H3 <Picture N> reference metadata."),
            ],
        )

    @classmethod
    async def execute(cls, images=None, idea="", preset=PRESET_FULL, system_prompt="",
                      duration_seconds=5.0, provider="ollama", base_url="", model="", api_key="",
                      use_spicy_model=False, spicy_model="", spicy_system_prompt="",
                      seed=0, max_image_size=768, max_words=500, unload_after=True,
                      on_error="passthrough", context="", processed_prompt="",
                      context_data=None, processed_director_json="") -> io.NodeOutput:
        typed_context = normalise_context(context_data)
        context_has_images = isinstance(context_data, dict) and (
            "image_tensor" in context_data or "images" in context_data
        )
        if typed_context.get("image_tensor") is not None:
            tensors = [typed_context["image_tensor"]]
        elif context_has_images:
            tensors = reference_tensors(typed_context.get("images"), typed_context,
                                        limit=MAX_IMAGES)
        else:
            tensors = _collect(images)
        if not typed_context and tensors:
            typed_context = {
                "images": [{} for _ in range(min(MAX_IMAGES, len(tensors)))],
                "references": [{"image": {}} for _ in range(min(MAX_IMAGES, len(tensors)))],
            }
        if len(tensors) > MAX_IMAGES:
            log.warning("[MiniMaxEnhance] %d images connected, MiniMax H3 takes at most %d — "
                        "dropping the rest.", len(tensors), MAX_IMAGES)
            tensors = tensors[:MAX_IMAGES]

        batched = None
        if tensors:
            flat = []
            for t in tensors:
                flat.extend([t[i:i + 1] for i in range(t.shape[0])])
            flat = flat[:MAX_IMAGES]
            sizes = {tuple(t.shape[1:3]) for t in flat}
            if len(sizes) > 1:
                log.warning("[MiniMaxEnhance] reference images have different sizes %s — "
                            "scaling them to the first one.", sorted(sizes))
            batched = extra("nodes_post_processing", "batch_images").batch_images(flat)

        # The authoring UI can materialize this node before a generation is queued.
        # Keep returning the image batch so the Director still receives the exact same
        # references, but do not repeat any of the VLM, spicy-pass, or sound-line calls.
        cached_prompt = str(processed_prompt or "").strip()
        if cached_prompt:
            log.info("[MiniMaxEnhance] using processed prompt; skipping LLM calls")
            cached_json = parse_json(processed_director_json)
            if not cached_json:
                if preset == PRESET_FULL:
                    cached_json = build_full_director_payload(
                        cached_prompt, {}, float(duration_seconds), typed_context)
                else:
                    cached_json = build_director_payload(
                        cached_prompt, float(duration_seconds), typed_context, preset)
            return io.NodeOutput(cached_prompt, batched, float(duration_seconds),
                                 json.dumps(cached_json, separators=(",", ":")))

        provider = (provider or "ollama").lower()
        defaults = media._PROVIDER_DEFAULTS.get(provider, media._PROVIDER_DEFAULTS["ollama"])
        url = media.normalize_base_url(base_url, defaults["url"])
        model_name = model or defaults["model"]
        api_key = str(api_key or "").strip()
        use_spicy_model = bool(use_spicy_model)
        spicy_model_name = str(spicy_model or "").strip() or model_name
        spicy_system = (spicy_system_prompt or "").strip() or SYSTEM_SPICY
        system = (system_prompt or "").strip() or system_for(preset, max_words)

        if preset == PRESET_FULL:
            user = build_full_h3_request(
                idea, typed_context, system, float(duration_seconds))
        else:
            user = (idea or "").strip() or "Describe what these images show as a video."
            context_parts = []
            typed_context_text = typed_context.get("prompt_context", "")
            if typed_context_text:
                context_parts.append(typed_context_text)
            legacy_context = (context or "").strip()
            if legacy_context and legacy_context not in context_parts:
                context_parts.append(legacy_context)
            if context_parts:
                user = "\n\n".join(context_parts) + "\n\n" + user
            if preset == PRESET_STORYBOARD:
                user = "%s\n\nTarget duration: %.1f seconds." % (user, float(duration_seconds))
            # Recency matters more than instruction count for small models: without this
            # reminder qwen3.5:9b dropped the two closing lines in roughly half the runs.
            user += ("\n\nRemember: finish with the Audio: line and then the Music: line, "
                     "and write nothing after them.")

        b64 = _tensor_to_b64(batched, int(max_image_size), 88) if batched is not None else []
        log.info("[MiniMaxEnhance] %s via %s (%s, model '%s'), %d image(s)...",
                 ("full" if preset == PRESET_FULL else
                  ("storyboard" if preset == PRESET_STORYBOARD else "global")),
                 provider, url, model_name, len(b64))

        # The token cap is only a runaway backstop; the shaping is done afterwards by
        # _trim_to_words and _first_sentences. It has to stay generous, because the model
        # writes the description first and the Audio:/Music: lines last — cut it too close
        # and those never get written, which leaves the Director's overall_soundscape and
        # non_diegetic_music empty. Measured: 300 words at 600 tokens lost them entirely.
        cap = int(max_words * 2.2) + 400 if max_words else None
        # Ollama drops the model right after answering when keep_alive is 0. That matters
        # here: the VLM and H3 are usually on the same card, and a 7B vision model still
        # resident when sampling starts is the difference between a render and an OOM.
        keep_alive = 0 if unload_after else 300
        model_director_data = {}
        try:
            raw = await media.vlm_generate(b64, user, provider, url, model_name,
                                           system_prompt=system, timeout=300,
                                           max_tokens=cap, keep_alive=keep_alive,
                                           api_key=api_key)
            if preset == PRESET_FULL:
                model_director_data, prose = _extract_response_json(raw)
                prompt = _clean_full_body(
                    _body_from_response(model_director_data, prose, duration_seconds),
                    max_words=int(max_words),
                )
                if not _valid_model_director_json(model_director_data):
                    log.warning("[MiniMaxEnhance] full preset returned missing or incomplete "
                                "DIRECTOR_JSON; normalizing it against the prompt and real context.")
            else:
                prompt = clean_prompt(raw, preset, max_words=int(max_words))
            if not prompt:
                raise media.VLMError("The model returned nothing usable.")

            if use_spicy_model:
                log.info("[MiniMaxEnhance] spicy second pass via %s (model '%s')...",
                         provider, spicy_model_name)
                spicy_user = (
                    "Revise this first-pass MiniMax-H3 prompt according to your instructions. "
                    "Return the complete revised prompt, not a summary:\n\n%s" % prompt)
                try:
                    spicy_raw = await media.vlm_generate(
                        b64, spicy_user, provider, url, spicy_model_name,
                        system_prompt=spicy_system, timeout=300,
                        max_tokens=cap, keep_alive=keep_alive, api_key=api_key)
                    spicy_prompt = (_clean_full_body(spicy_raw, max_words=int(max_words))
                                    if preset == PRESET_FULL else
                                    clean_prompt(spicy_raw, preset, max_words=int(max_words)))
                    if not spicy_prompt:
                        raise media.VLMError("The spicy model returned nothing usable.")
                    prompt = spicy_prompt
                except media.VLMError as e:
                    if on_error == "fail":
                        raise
                    log.warning("[MiniMaxEnhance] spicy second pass unavailable: %s; "
                                "keeping the first-pass prompt.", e)

            # Small models reliably drop the two closing lines after a long description --
            # qwen3.5:9b managed both in 0 of 4 measured runs. Asking again, on its own,
            # is far more dependable than asking harder in the first prompt, and it only
            # costs a few seconds when it is actually needed.
            has_audio = re.search(r"^\s*(?:audio|sound|sfx)\s*:", prompt, re.I | re.M)
            has_music = re.search(r"^\s*(?:music|score)\s*:", prompt, re.I | re.M)
            if not (has_audio and has_music):
                log.info("[MiniMaxEnhance] no %s line — asking for the sound lines separately.",
                         "Audio/Music" if not (has_audio or has_music)
                         else ("Music" if has_audio else "Audio"))
                try:
                    tail = await media.vlm_generate(
                        [], prompt, provider, url,
                        spicy_model_name if use_spicy_model else model_name,
                        system_prompt=SYSTEM_AUDIO_ONLY, timeout=120, max_tokens=300,
                        keep_alive=keep_alive, api_key=api_key)
                    merged = (_clean_full_body("%s\n%s" % (prompt, tail))
                              if preset == PRESET_FULL else
                              clean_prompt("%s\n%s" % (prompt, tail), preset))
                    if re.search(r"^\s*(?:audio|sound|sfx)\s*:", merged, re.I | re.M):
                        prompt = merged
                except media.VLMError as e:
                    log.warning("[MiniMaxEnhance] sound lines unavailable: %s", e)
        except Exception as e:
            # Deliberately broad: 'passthrough' promises the run survives, and the thing
            # that took a run down in practice was aiohttp rejecting a URL without a
            # scheme -- not a VLMError at all. The traceback still reaches the console.
            if on_error == "fail":
                if isinstance(e, media.VLMError):
                    raise ValueError("MiniMax H3 Enhance Prompt: %s" % e)
                raise
            log.warning("[MiniMaxEnhance] %s — passing your text through unchanged.", e,
                        exc_info=not isinstance(e, media.VLMError))
            prompt = (idea or "").strip()
        finally:
            # Backstop for keep_alive, and it also runs when the call blew up half way —
            # that is exactly when a model is left sitting in VRAM.
            if unload_after:
                await media.unload_model(provider, url, model_name)
                if use_spicy_model and spicy_model_name != model_name:
                    await media.unload_model(provider, url, spicy_model_name)

        log.info("[MiniMaxEnhance] %d chars:\n%s", len(prompt), prompt)
        if preset == PRESET_FULL:
            director_data = build_full_director_payload(
                prompt, model_director_data, float(duration_seconds), typed_context)
        else:
            director_data = build_director_payload(prompt, float(duration_seconds),
                                                   typed_context, preset)
        return io.NodeOutput(prompt, batched, float(duration_seconds),
                             json.dumps(director_data, separators=(",", ":")))


NODE_CLASS_MAPPINGS = {"MiniMaxH3EnhancePromptPlusCS": MiniMaxH3EnhancePrompt}
NODE_DISPLAY_NAME_MAPPINGS = {"MiniMaxH3EnhancePromptPlusCS": "MiniMax H3 Enhance Prompt Plus"}


def _tensor_from_data_url(value):
    """Decode a browser-supplied reference image for the authoring Process action."""
    raw = str(value or "")
    if "," in raw and raw.lower().startswith("data:"):
        raw = raw.split(",", 1)[1]
    image = Image.open(_io.BytesIO(base64.b64decode(raw))).convert("RGB")
    array = np.asarray(image, dtype=np.float32) / 255.0
    return torch.from_numpy(array).unsqueeze(0)


@PromptServer.instance.routes.post("/minimax_director/enhance/process")
async def process_enhance_endpoint(request):
    """Run Enhance Prompt from the node UI and return a prompt to cache in the node.

    This is deliberately separate from the Comfy execution queue: Processing is an
    authoring action, while the Director is the only node that should perform the
    actual generation job. The cached prompt is then consumed by ``execute`` above.
    """
    try:
        data = await request.json()
        image_values = data.get("images") or []
        tensors = {}
        for index, value in enumerate(image_values[:MAX_IMAGES]):
            if value:
                tensors["image%d" % index] = _tensor_from_data_url(value)
        output = await MiniMaxH3EnhancePrompt.execute(
            images=tensors,
            idea=data.get("idea", ""),
            preset=data.get("preset", PRESET_FULL),
            system_prompt=data.get("system_prompt", ""),
            duration_seconds=float(data.get("duration_seconds") or 5.0),
            provider=data.get("provider", "ollama"),
            base_url=data.get("base_url", ""),
            model=data.get("model", ""),
            api_key=data.get("api_key", ""),
            use_spicy_model=bool(data.get("use_spicy_model", False)),
            spicy_model=data.get("spicy_model", ""),
            spicy_system_prompt=data.get("spicy_system_prompt", ""),
            seed=int(data.get("seed") or 0),
            max_image_size=int(data.get("max_image_size") or 768),
            max_words=int(data.get("max_words", 500) if data.get("max_words") is not None else 500),
            unload_after=bool(data.get("unload_after", True)),
            on_error=data.get("on_error", "passthrough"),
            context=data.get("context", ""),
            processed_prompt="",
            context_data=data.get("context_data"),
            processed_director_json="",
        )
        return web.json_response({"status": "success", "prompt": output[0],
                                  "director_json": output[3]})
    except Exception as error:
        log.exception("[MiniMaxEnhance] Process action failed")
        return web.json_response({"status": "error", "message": str(error)}, status=500)
