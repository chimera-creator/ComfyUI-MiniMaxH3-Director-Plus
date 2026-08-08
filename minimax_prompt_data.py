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
        description = str(character.get("description") or "").strip()
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
    timeline_segments = []
    for index, shot in enumerate(shots, start=1):
        start = max(0.0, float(shot.get("start", 0.0)))
        length = max(1, int(round(max(0.0, float(shot.get("length", 0.0))) * fps)))
        timeline_segments.append({
            "id": "enhance-shot-%d" % index,
            "type": "image",
            "start": int(round(start * fps)),
            "length": length,
            "prompt": str(shot.get("prompt") or "").strip(),
            "fileName": "",
            "imageFile": "",
        })

    duration = max(0.1, float(duration_seconds or 0.1))
    duration_frames = max(1, int(round(duration * fps)))
    timeline = {
        "segments": timeline_segments,
        "motionSegments": [], "audioSegments": [],
        "characters": cast.get("characters", []) if isinstance(cast, dict) else [],
        "subject_definitions": subject_definitions,
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
