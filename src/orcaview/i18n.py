"""UTF-8 interface language packs. The scientific core does not depend on Qt."""

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import re
from string import Formatter


BASE_LOCALE = "en"
_LOCALE = re.compile(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*")
_active_messages = {}
_diagnostic_templates = []


@dataclass(frozen=True)
class LanguagePack:
    locale: str
    name: str
    messages: dict


def _fields(text):
    # Permit word reordering and numbered replacements for implicit positional
    # fields. A pack must never introduce an attribute access or a format spec.
    fields = []
    implicit = 0
    numbered = False
    for _, field, spec, conversion in Formatter().parse(text):
        if field is not None:
            if not field:
                if numbered:
                    raise ValueError("Mixed implicit and explicit indexes")
                field = str(implicit)
                implicit += 1
            elif re.match(r"\d+(?:[.\[]|$)", field):
                if implicit:
                    raise ValueError("Mixed implicit and explicit indexes")
                numbered = True
            fields.append((field, spec, conversion))
    return Counter(fields)


def _read_pack(path):
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("Invalid language pack")
    locale, name, messages = (data.get(key) for key in ("locale", "name", "messages"))
    if not isinstance(locale, str) or not _LOCALE.fullmatch(locale) or locale == BASE_LOCALE:
        raise ValueError("Invalid language tag")
    if not isinstance(name, str) or not name.strip() or not isinstance(messages, dict):
        raise ValueError("Missing language name or messages")
    for key, value in messages.items():
        if not isinstance(value, str) or not key or not value.strip() or _fields(key) != _fields(value):
            raise ValueError(f"Invalid translation for {key!r}")
    return LanguagePack(locale, name.strip(), messages)


def discover_languages(directory=None, *, bundled=None):
    """Offer native English plus translations installed in a pack directory."""
    packs = {BASE_LOCALE: LanguagePack(BASE_LOCALE, "English", {})}
    failures = []
    for folder in (bundled, directory):
        if folder is None:
            continue
        try:
            paths = sorted(Path(folder).glob("*.json"))
        except OSError:
            failures.append(str(folder))
            continue
        seen = set()
        for path in paths:
            try:
                pack = _read_pack(path)
                if pack.locale in seen:
                    raise ValueError("Duplicate language in the same directory")
            except (OSError, UnicodeError, ValueError, RecursionError):
                failures.append(str(path))
                continue
            seen.add(pack.locale)
            base = packs.get(pack.locale)
            if base:
                pack = LanguagePack(pack.locale, pack.name, {**base.messages, **pack.messages})
            packs[pack.locale] = pack
    return packs, failures


def activate_language(pack):
    global _active_messages, _diagnostic_templates
    _active_messages = pack.messages
    templates = []
    for source, translated in pack.messages.items():
        # Core readers intentionally return the original diagnostic even when
        # running in a background worker or persisting a scientific record.
        if "{" not in source:
            continue
        parts = list(Formatter().parse(source))
        if not any(field is not None for _, field, _, _ in parts) or not any(
                any(ch.isalpha() for ch in literal) for literal, *_ in parts):
            continue
        templates.append((parts, list(Formatter().parse(translated))))
    _diagnostic_templates = sorted(templates, key=lambda pair: sum(len(literal) for literal, *_ in pair[0]),
                                   reverse=True)


def tr(source, /, *args, **kwargs):
    """Translate authored interface text before interpolating application data."""
    message = _active_messages.get(source, source)
    return message.format(*args, **kwargs) if args or kwargs else message


def _captured_fields(parts, message):
    """Match an already-rendered template using only literal boundaries."""
    fields = {}
    start = 0
    implicit = 0
    for index, (literal, field, spec, conversion) in enumerate(parts):
        if not message.startswith(literal, start):
            return None
        start += len(literal)
        if field is None:
            continue
        if index + 1 == len(parts):
            end = len(message)
        else:
            delimiter, next_field, _, _ = parts[index + 1]
            if not delimiter:
                return None  # Adjacent fields have no uniquely recoverable boundary.
            if next_field is None:
                end = len(message) - len(delimiter)
            else:
                end = message.find(delimiter, start)
            if end < start:
                return None
        if field == "":
            field = str(implicit)
            implicit += 1
        key = (field, spec, conversion)
        value = message[start:end]
        if key in fields and fields[key] != value:
            return None
        fields[key] = value
        start = end
    return fields if start == len(message) else None


def diagnostic_text(error):
    """Translate a displayed diagnostic, preserving the rendered parameter values."""
    message = str(error)
    if message in _active_messages:
        return _active_messages[message]
    for source, translated in _diagnostic_templates:
        fields = _captured_fields(source, message)
        if fields is None:
            continue
        output = []
        implicit = 0
        for literal, field, spec, conversion in translated:
            output.append(literal)
            if field is not None:
                if field == "":
                    field = str(implicit)
                    implicit += 1
                output.append(fields[(field, spec, conversion)])
        return "".join(output)
    return message
