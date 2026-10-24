"""Prompt builders backed by the versioned, hot-updatable AI catalog."""
from __future__ import annotations

import json
import re

from .catalog import HTML_RULE, catalog


def _lang(code: str) -> str:
    return catalog.language(code)


def _value(value: str, fallback: str = "-") -> str:
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def product_description(name: str, lang: str, details: str = "", existing: str = "",
                        keywords: str = "", tone: str = "persuasive but honest", context: str = "") -> list[dict]:
    return catalog.render("product_description", {
        "name": name, "language": _lang(lang), "details": _value(details), "existing": _value(existing),
        "keywords": _value(keywords), "tone": tone or "persuasive but honest", "context": _value(context),
        "html_rule": HTML_RULE,
    })


def product_short(name: str, lang: str, description: str = "", context: str = "") -> list[dict]:
    return catalog.render("product_short", {
        "name": name, "language": _lang(lang), "description": _value(description), "context": _value(context),
    })


def seo_meta(title: str, lang: str, content: str = "", keyword: str = "", context: str = "") -> list[dict]:
    return catalog.render("seo_meta", {
        "title": title, "language": _lang(lang), "keyword": _value(keyword),
        "context": _value(context), "content": content[:3000] or "-",
    })


def rewrite(text: str, lang: str, instruction: str = "Improve clarity and flow, keep the meaning") -> list[dict]:
    return catalog.render("rewrite", {
        "text": text, "language": _lang(lang),
        "instruction": instruction or "Improve clarity and flow, keep the meaning",
    })


def translate(text: str, target_lang: str) -> list[dict]:
    return catalog.render("translate", {"text": text, "language": _lang(target_lang)})


def post_outline(topic: str, lang: str, keywords: str = "", context: str = "") -> list[dict]:
    return catalog.render("post_outline", {
        "topic": topic, "language": _lang(lang), "keywords": _value(keywords), "context": _value(context),
        "html_rule": HTML_RULE,
    })


def post_draft(topic: str, lang: str, keywords: str = "", outline: str = "", words: int = 900,
               context: str = "") -> list[dict]:
    return catalog.render("post_draft", {
        "topic": topic, "language": _lang(lang), "keywords": _value(keywords), "outline": _value(outline),
        "words": words, "context": _value(context), "html_rule": HTML_RULE,
    })


def excerpt(content: str, lang: str, context: str = "") -> list[dict]:
    return catalog.render("excerpt", {
        "content": content[:4000] or "-", "language": _lang(lang), "context": _value(context),
    })


def suggest_tags(content: str, lang: str, context: str = "") -> list[dict]:
    return catalog.render("suggest_tags", {
        "content": content[:3000] or "-", "language": _lang(lang), "context": _value(context),
    })


def alt_text(name: str, lang: str) -> list[dict]:
    return catalog.render("alt_text", {"name": name, "language": _lang(lang)})


def seo_audit(payload: dict, lang: str) -> list[dict]:
    return catalog.render("seo_audit", {
        "language": _lang(lang), "data": json.dumps(payload, ensure_ascii=False),
    })


def perf_analysis(payload: dict, lang: str) -> list[dict]:
    return catalog.render("perf_analysis", {
        "language": _lang(lang), "data": json.dumps(payload, ensure_ascii=False),
    })


def parse_json_loose(text: str) -> dict:
    """Extract a JSON object from a model reply, tolerating fences and chatter."""
    text = text.strip()
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except Exception:
        pass

    text = re.sub(r"```[a-zA-Z0-9_-]*", "", text).strip()
    decoder = json.JSONDecoder()
    pos = 0
    while True:
        start = text.find("{", pos)
        if start == -1:
            break
        try:
            value, _end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            pos = start + 1
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("No JSON object in AI reply")


def strip_fences(text: str) -> str:
    text = text.strip()
    match = re.fullmatch(r"```(?:html|markdown|md)?\s*(.*?)\s*```", text, re.S)
    return match.group(1) if match else text
