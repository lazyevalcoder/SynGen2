"""Shared helpers."""
import json
import re


def extract_json(text):
    """Pull a JSON object out of LLM output. Tries, in order:
    1. direct parse of the whole text
    2. fenced code blocks (```json ... ```) anywhere in the text
    3. first '{' to last '}' substring
    Raises ValueError if nothing parses.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        raise ValueError("empty LLM output")

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    candidates = []
    for block in re.findall(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL):
        candidates.append(block.strip())

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        candidates.append(cleaned[start:end + 1])

    for candidate in candidates:
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue

    raise ValueError("no parsable JSON object found in LLM output")


def get_at_path(obj, dotted_path):
    node = obj
    for token in _tokens(dotted_path):
        node = node[token]
    return node


def set_at_path(obj, dotted_path, value):
    tokens = _tokens(dotted_path)
    node = obj
    for i, token in enumerate(tokens):
        last = i == len(tokens) - 1
        if last:
            node[token] = value
            return
        nxt_is_int = isinstance(tokens[i + 1], int)
        if isinstance(token, int):
            node = node[token]
        else:
            if nxt_is_int and token not in node:
                node[token] = []
            node = node.setdefault(token, {})


def _tokens(dotted_path):
    tokens = []
    for part in dotted_path.split("."):
        head = part.strip()
        while head:
            bracket = head.find("[")
            if bracket == -1:
                tokens.append(head)
                break
            if bracket > 0:
                tokens.append(head[:bracket])
            close = head.find("]")
            tokens.append(int(head[bracket + 1:close]))
            head = head[close + 1:]
    return tokens
