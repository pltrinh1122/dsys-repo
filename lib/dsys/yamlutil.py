"""Tiny YAML-subset parser/writer for dsys configuration.

Supported subset:
  - flat ``key: value`` mappings, plus ONE nested mapping level
    (2-space indent);
  - full-line ``#`` comments and trailing ``#`` comments (a ``#``
    preceded by whitespace, outside quotes);
  - integers detected with ``^[+-]?\\d+$``;
  - matching single/double quotes stripped (with minimal unescaping).

Anything outside the subset raises ValueError on load.
"""

import re

_INT_RE = re.compile(r"^[+-]?\d+$")
_KEY_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
_QUOTE_SPECIALS = set("#:\"'{}[],&*!|>@`")


def _strip_comment(line: str) -> str:
    """Remove a trailing comment: a '#' outside quotes preceded by whitespace."""
    out = []
    in_single = False
    in_double = False
    prev = ""
    i = 0
    while i < len(line):
        ch = line[i]
        if (in_single or in_double) and ch == "\\" and i + 1 < len(line):
            out.append(ch)
            out.append(line[i + 1])
            prev = line[i + 1]
            i += 2
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double and prev in ("", " ", "\t"):
            break
        out.append(ch)
        prev = ch
        i += 1
    return "".join(out)


def _parse_scalar(text: str):
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        inner = text[1:-1]
        if text[0] == '"':
            inner = inner.replace('\\"', '"').replace("\\\\", "\\")
        else:
            inner = inner.replace("''", "'")
        return inner
    if _INT_RE.match(text):
        try:
            return int(text)
        except ValueError:
            pass
    return text


def _check_key(key: str, lineno: int) -> None:
    if not _KEY_RE.match(key):
        raise ValueError(f"line {lineno}: bad key {key!r}")


def loads(text: str) -> dict:
    """Parse the YAML subset into a dict. Raises ValueError on malformed input."""
    result: dict = {}
    current_parent = None
    for lineno, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        stripped = raw.lstrip()
        if stripped.startswith("#"):
            continue
        indent = len(raw) - len(stripped)
        if indent % 2 != 0:
            raise ValueError(f"line {lineno}: odd indentation (only 2-space indents)")
        if "\t" in raw[:indent]:
            raise ValueError(f"line {lineno}: tab indentation is not allowed")
        level = indent // 2
        if level > 1:
            raise ValueError(f"line {lineno}: only one nested mapping level allowed")
        line = _strip_comment(raw).rstrip()
        if not line.strip():
            continue
        if ":" not in line:
            raise ValueError(f"line {lineno}: expected 'key: value'")
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        _check_key(key, lineno)
        if level == 0:
            current_parent = None
            if key in result:
                raise ValueError(f"line {lineno}: duplicate key {key!r}")
            if value == "":
                result[key] = {}
                current_parent = key
            else:
                result[key] = _parse_scalar(value)
        else:
            if current_parent is None:
                raise ValueError(f"line {lineno}: indented entry without a parent mapping")
            if value == "":
                raise ValueError(f"line {lineno}: only one nested mapping level allowed")
            parent = result[current_parent]
            if key in parent:
                raise ValueError(f"line {lineno}: duplicate key {key!r}")
            parent[key] = _parse_scalar(value)
    return result


def _needs_quotes(s: str) -> bool:
    if s == "" or s != s.strip():
        return True
    if _INT_RE.match(s) or s in ("true", "false", "null", "~"):
        return True
    return any(ch in _QUOTE_SPECIALS for ch in s)


def _dump_scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        if _needs_quotes(value):
            return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
        return value
    raise ValueError(f"unsupported value type: {type(value).__name__}")


def dumps(mapping: dict) -> str:
    """Serialize a flat dict (plus one nested-mapping level) to the subset."""
    if not isinstance(mapping, dict):
        raise ValueError("dumps() expects a dict")
    lines = []
    for key, value in mapping.items():
        if not isinstance(key, str) or not _KEY_RE.match(key):
            raise ValueError(f"bad key: {key!r}")
        if isinstance(value, dict):
            if not value:
                raise ValueError(f"key {key!r}: empty nested mappings are not supported")
            lines.append(f"{key}:")
            for sub_key, sub_value in value.items():
                if not isinstance(sub_key, str) or not _KEY_RE.match(sub_key):
                    raise ValueError(f"bad key: {sub_key!r}")
                if isinstance(sub_value, dict):
                    raise ValueError("only one nested mapping level is supported")
                lines.append(f"  {sub_key}: {_dump_scalar(sub_value)}")
        else:
            lines.append(f"{key}: {_dump_scalar(value)}")
    return ("\n".join(lines) + "\n") if lines else ""
