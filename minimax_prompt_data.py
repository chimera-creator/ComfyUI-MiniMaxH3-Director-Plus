"""Build the JSON contract shared by Enhance Prompt and Director Plus.

Enhance Prompt writes prose for the VLM, but the Director needs the same result split
back into its timeline fields.  This module keeps that translation independent from
either node's UI code and gives every reference an explicit H3 picture ordinal.
"""

from __future__ import annotations

import json
import re


_SHOT_MARKER = re.compile(
    r"\[Shot\s+(\d+)\]\s*(?:At\s+(\d+):(\d+(?:\.\d+)?),\s*)?",
    re.IGNORECASE,
)
_AUDIO_LINE = re.compile(
    r"^\s*(?:audio|sound|sfx|overall_soundscape)\s*:\s*(.*)$", re.IGNORECASE)
_MUSIC_LINE = re.compile(
    r"^\s*(?:music|score|non_diegetic_music)\s*:\s*(.*)$", re.IGNORECASE)


def parse_json(value):
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value) if value else None
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _first_lower(value):
    value = str(value or "").strip()
    return value[:1].lower() + value[1:] if value else ""


def _with_period(value):
    value = str(value or "").strip()
    if value and value[-1] not in ".!?":
        value += "."
    return value


def extract_audio_music(prompt):
    """Remove the final sound lines from prompt prose and return them separately."""
    body = []
    audio = ""
    music = ""
    for line in str(prompt or "").splitlines():
        audio_match = _AUDIO_LINE.match(line)
        music_match = _MUSIC_LINE.match(line)
        if audio_match and not audio:
            audio = audio_match.group(1).strip()
        elif music_match and not music:
            music = music_match.group(1).strip()
        else:
            body.append(line)
    return "\n".join(body).strip(), audio, music


def parse_shots(prompt, duration_seconds):
    """Parse H3 [Shot N] markers into seconds and return the opening prose separately."""
    text = str(prompt or "").strip()
    duration = max(0.1, float(duration_seconds or 0.1))
    matches = list(_SHOT_MARKER.finditer(text))
    if not matches:
        return "", [{
            "number": 1, "start": 0.0, "end": duration, "length": duration,
            "prompt": text,
        }] if text else []

    opening = text[:matches[0].start()].strip()
    shots = []
    for index, match in enumerate(matches):
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        raw_start = 0.0
        if match.group(2) is not None:
            raw_start = float(match.group(2)) * 60.0 + float(match.group(3))
        start = max(0.0, min(duration, raw_start))
        if shots and start < shots[-1]["start"]:
            start = shots[-1]["start"]
        end = duration
        if index + 1 < len(matches):
            next_match = matches[index + 1]
            if next_match.group(2) is not None:
                end = max(start, min(duration,
                                     float(next_match.group(2)) * 60.0
                                     + float(next_match.group(3))))
        shot_text = text[match.end():next_start].strip()
        shots.append({
            "number": int(match.group(1)), "start": start, "end": end,
            "length": max(0.0, end - start), "prompt": shot_text,
        })
    if shots:
        shots[-1]["end"] = duration
        shots[-1]["length"] = max(0.0, duration - shots[-1]["start"])
    return opening, shots


def _seconds(value, default=None):
    """Parse a model-produced second value, including ``MM:SS.s`` strings."""
    if value is None or isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    text = str(value or "").strip().lower().removesuffix("s").strip()
    if not text:
        return default
    try:
        parts = text.split(":")
        if len(parts) == 2:
            return float(parts[0]) * 60.0 + float(parts[1])
        if len(parts) == 3:
            return float(parts[0]) * 3600.0 + float(parts[1]) * 60.0 + float(parts[2])
    except (TypeError, ValueError):
        return default
    return default


def normalise_shots(value, duration_seconds):
    """Normalise an LLM ``shots``/``segments`` list to the Director shot contract.

    Full-reference responses are usually well formed, but OpenAI-compatible models use
    several harmless variants in practice (``segment_prompt``, ``start_time``, timestamp
    strings, or plain strings). Keeping that tolerance here prevents a valid multi-shot
    answer from silently collapsing into one timeline segment.
    """
    duration = max(0.1, float(duration_seconds or 0.1))
    if isinstance(value, dict):
        value = list(value.values())
    if not isinstance(value, list):
        return []

    prepared = []
    for index, raw in enumerate(value, start=1):
        if isinstance(raw, str):
            raw = {"prompt": raw}
        if not isinstance(raw, dict):
            continue
        prompt = str(
            raw.get("prompt") or raw.get("segment_prompt") or
            raw.get("description") or raw.get("detailed_description") or
            raw.get("action") or ""
        ).strip()
        if not prompt:
            continue
        start = _seconds(raw.get("start", raw.get("start_seconds", raw.get("start_time"))))
        end = _seconds(raw.get("end", raw.get("end_seconds", raw.get("end_time"))))
        length = _seconds(raw.get("length", raw.get("duration", raw.get("duration_seconds"))))
        try:
            number = int(raw.get("number", raw.get("shot", raw.get("index", index))) or index)
        except (TypeError, ValueError):
            number = index
        prepared.append({"number": number, "prompt": prompt,
                         "start": start, "end": end, "length": length})
    if not prepared:
        return []

    count = len(prepared)
    has_timing = any(item[key] is not None for item in prepared
                     for key in ("start", "end", "length"))
    if not has_timing:
        step = duration / count
        for index, item in enumerate(prepared):
            item["start"] = index * step
            item["end"] = duration if index + 1 == count else (index + 1) * step
    else:
        cursor = 0.0
        for index, item in enumerate(prepared):
            start = item["start"] if item["start"] is not None else cursor
            start = max(cursor, min(duration, start))
            end = item["end"]
            if end is None and item["length"] is not None:
                end = start + max(0.0, item["length"])
            if end is None and index + 1 < count:
                end = prepared[index + 1]["start"]
            if end is None:
                remaining = count - index
                end = start + max(0.0, duration - start) / remaining
            end = max(start, min(duration, end))
            item["start"], item["end"] = start, end
            cursor = end

    shots = []
    for index, item in enumerate(prepared):
        start = max(0.0, min(duration, float(item["start"] or 0.0)))
        end = max(start, min(duration, float(item["end"] or start)))
        if index + 1 < count:
            next_start = prepared[index + 1].get("start")
            if next_start is not None:
                end = max(start, min(duration, float(next_start)))
        else:
            end = duration
        shots.append({
            "number": int(item["number"] or index + 1),
            "start": start,
            "end": end,
            "length": max(0.0, end - start),
            "prompt": item["prompt"],
        })
    return shots


def shots_to_timeline_segments(shots, fps=24.0):
    """Convert normalized second-based shots to Director pixel-frame segments."""
    timeline_segments = []
    for index, shot in enumerate(shots or [], start=1):
        start = max(0.0, float(shot.get("start", 0.0)))
        length = max(1, int(round(max(0.0, float(shot.get("length", 0.0))) * fps)))
        timeline_segments.append({
            "id": "enhance-shot-%d" % index,
            # Enhance shots carry timing and prose, not a timeline keyframe image.
            # Mark them as text so the Director canvas renders the segment prompt.
            "type": "text",
            "start": int(round(start * fps)),
            "length": length,
            "prompt": str(shot.get("prompt") or "").strip(),
            "fileName": "",
            "imageFile": "",
        })
    return timeline_segments


def _source_payload(context):
    sources = context.get("sources") if isinstance(context, dict) else {}
    if not isinstance(sources, dict):
        sources = {}
    for key in ("cast_wardrobe_sets", "cast_wardrobe", "cast", "casting"):
        payload = sources.get(key)
        if isinstance(payload, dict) and isinstance(payload.get("characters"), list):
            return payload
    for payload in sources.values():
        if isinstance(payload, dict) and isinstance(payload.get("characters"), list):
            return payload
    return {}


def _reference_manifest(context):
    raw = context.get("references") if isinstance(context, dict) else None
    if not isinstance(raw, list):
        raw = []
    result = []
    for index, reference in enumerate(raw, start=1):
        if not isinstance(reference, dict):
            continue
        image = reference.get("image") or reference.get("reference")
        if not isinstance(image, dict):
            continue
        item = dict(reference)
        item["index"] = index
        item["picture"] = "<Picture %d>" % index
        item["h3_reference"] = item["picture"]
        item["image"] = image
        result.append(item)
    if result:
        return result

    images = context.get("images") if isinstance(context, dict) else []
    if not isinstance(images, list):
        images = []
    return [{
        "index": index, "picture": "<Picture %d>" % index,
        "h3_reference": "<Picture %d>" % index, "source": "input",
        "image": image, "description": "",
    } for index, image in enumerate(images[:9], start=1) if isinstance(image, dict)]


def _anatomy_sentence(description, character):
    description = str(description or "").strip()
    if not description:
        return ""
    pronouns = str(character.get("pronouns", character.get("pronoun", "auto")) or "auto").lower()
    if pronouns in ("she", "she/her", "her"):
        possessive = "her"
    elif pronouns in ("they", "they/them", "them", "their"):
        possessive = "their"
    else:
        possessive = "his"
    description = _first_lower(description)
    if not re.match(r"^(?:a|an)\s+", description, re.IGNORECASE):
        description = "a " + description
    return _with_period("%s body has %s" % (possessive, description))


def _subject_definitions(cast, references):
    characters = cast.get("characters") if isinstance(cast, dict) else []
    if not isinstance(characters, list):
        return [], {}
    lines = []
    subject_of_slot = {}
    next_subject = 1
    for slot, character in enumerate(characters, start=1):
        if not isinstance(character, dict) or character.get("hired", True) is False:
            continue
        refs = []
        for item in references:
            if item.get("source") not in ("char", "cast"):
                continue
            try:
                reference_slot = int(item.get("character_slot", item.get("slot", 0)) or 0)
            except (TypeError, ValueError):
                continue
            if reference_slot == slot:
                refs.append(item)
        if not refs:
            continue
        subject = next_subject
        next_subject += 1
        subject_of_slot[slot] = subject
        pictures = " and ".join(item["picture"] for item in refs)
        appearance = str(character.get("appearance") or "").strip()
        original_wardrobe = str(character.get("wardrobe") or "").strip()
        wardrobe_parts = []
        anatomy_parts = []
        for collage in cast.get("wardrobe_collages", []) or []:
            if not isinstance(collage, dict):
                continue
            try:
                collage_slot = int(collage.get("character_slot", collage.get("slot", 0)) or 0)
            except (TypeError, ValueError):
                continue
            if collage_slot != slot:
                continue
            wardrobe = str(collage.get("description") or "").strip()
            anatomy = str(collage.get("anatomy_description") or "").strip()
            if wardrobe:
                wardrobe_parts.append(wardrobe)
            if anatomy:
                anatomy_parts.append(anatomy)
        # Wardrobe Director is authoritative when it has an assignment for this cast
        # member. This prevents the original casting-test outfit from leaking into the
        # final subject definition after a wardrobe change.
        if wardrobe_parts or anatomy_parts:
            description = " ".join(part for part in
                                   (appearance, " ".join(wardrobe_parts),
                                    _anatomy_sentence(" ".join(anatomy_parts), character))
                                   if part).strip()
        else:
            description = " ".join(part for part in (appearance, original_wardrobe)
                                   if part).strip()
            description = description or str(character.get("description") or "").strip()
        line = "<Subject %d> is the character shown in %s" % (subject, pictures)
        if description:
            line += " " + _first_lower(description)
        lines.append(_with_period(line))
    return lines, subject_of_slot


def build_director_payload(prompt, duration_seconds, context=None, preset=""):
    """Return Director-ready JSON data for an Enhance Prompt result."""
    context = context if isinstance(context, dict) else {}
    body, audio, music = extract_audio_music(prompt)
    opening, shots = parse_shots(body, duration_seconds)
    references = _reference_manifest(context)
    cast = _source_payload(context)
    subject_lines, subject_of_slot = _subject_definitions(cast, references)
    subject_definitions = " ".join(subject_lines)
    subjects = ["<Subject %d>" % number for number in sorted(subject_of_slot.values())]
    retention = "Keep the identity, face and clothing of %s consistent across every shot." \
        % ", ".join(subjects) if subjects else ""

    fps = 24.0
    timeline_segments = shots_to_timeline_segments(shots, fps)

    duration = max(0.1, float(duration_seconds or 0.1))
    duration_frames = max(1, int(round(duration * fps)))
    timeline = {
        "segments": timeline_segments,
        "motionSegments": [], "audioSegments": [],
        "characters": cast.get("characters", []) if isinstance(cast, dict) else [],
        "subject_definitions": subject_definitions,
        "summary": "",
        "retention_analysis": retention,
        "overall_soundscape": audio,
        "non_diegetic_music": music,
        "reference_mode": "REF2VA" if references else "OFF",
        "normalStartFrame": 0,
        "normalDurationFrames": duration_frames,
    }
    payload = {
        "version": 1,
        "duration": duration,
        "duration_seconds": duration,
        "duration_frames": duration_frames,
        "preset": str(preset or ""),
        "prompt": str(prompt or "").strip(),
        "global_prompt": opening,
        "shots": shots,
        "segments": timeline_segments,
        "subject_definitions": subject_definitions,
        "retention_analysis": retention,
        "overall_soundscape": audio,
        "non_diegetic_music": music,
        "references": references,
        "reference_images": references,
        "reference_mode": "REF2VA" if references else "OFF",
        "timeline": timeline,
        "cast": cast or None,
        "project": context.get("project") or {},
    }
    return payload
