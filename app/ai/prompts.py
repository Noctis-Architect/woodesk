"""Prompt templates. Every task returns chat messages for the AI client."""
from __future__ import annotations

import json
import re

LANG_NAMES = {
    "fa": "Persian (Farsi)", "en": "English", "ar": "Arabic", "tr": "Turkish",
    "de": "German", "fr": "French", "es": "Spanish", "ru": "Russian",
}

SYSTEM = (
    "You are an expert e-commerce copywriter, blogger and SEO specialist working inside a "
    "WordPress/WooCommerce management app. Follow the instructions exactly. Output ONLY the "
    "requested content - no preface, no explanations, no markdown code fences. Never invent "
    "technical specifications, prices, certifications or claims that were not provided."
)

HTML_RULE = "Format as clean HTML using only <p>, <h2>, <h3>, <ul>, <li>, <strong>, <em>. No <html>/<body>/<h1> tags."


def _msg(user: str) -> list[dict]:
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def _lang(code: str) -> str:
    return LANG_NAMES.get(code, code)


def product_description(name: str, lang: str, details: str = "", existing: str = "", keywords: str = "", tone: str = "persuasive but honest") -> list[dict]:
    return _msg(
        f"Write a complete product description in {_lang(lang)} for the product below.\n"
        f"Product name: {name}\nKnown details: {details or '-'}\nFocus keywords: {keywords or '-'}\n"
        f"Existing description (improve/reuse facts if present): {existing or '-'}\nTone: {tone}.\n"
        f"Structure: short intro paragraph, a bullet list of key features, a closing paragraph. {HTML_RULE}"
    )


def product_short(name: str, lang: str, description: str = "") -> list[dict]:
    return _msg(
        f"Write a short product summary (max 2 sentences, ~40 words) in {_lang(lang)} for '{name}'.\n"
        f"Base it on this description if available: {description or '-'}\nOutput plain HTML with a single <p>."
    )


def seo_meta(title: str, lang: str, content: str = "", keyword: str = "") -> list[dict]:
    return _msg(
        f"Create SEO metadata in {_lang(lang)} for the page below.\nTitle: {title}\nFocus keyword: {keyword or '-'}\n"
        f"Content: {content[:3000] or '-'}\n"
        'Return ONLY a JSON object: {"title": "<=60 chars", "description": "<=155 chars", '
        '"slug": "latin-lowercase-hyphenated", "focus_keyword": "..."}'
    )


def rewrite(text: str, lang: str, instruction: str = "Improve clarity and flow, keep the meaning") -> list[dict]:
    return _msg(
        f"Rewrite the text below in {_lang(lang)}. Instruction: {instruction}.\n"
        f"Keep any HTML tags/structure that already exist.\n\nTEXT:\n{text}"
    )


def translate(text: str, target_lang: str) -> list[dict]:
    return _msg(f"Translate the text below into {_lang(target_lang)}. Keep HTML tags unchanged.\n\nTEXT:\n{text}")


def post_outline(topic: str, lang: str, keywords: str = "") -> list[dict]:
    return _msg(
        f"Create a detailed blog article outline in {_lang(lang)} about: {topic}\nKeywords: {keywords or '-'}\n"
        "Return a list of H2 headings, each with 2-3 bullet points. " + HTML_RULE
    )


def post_draft(topic: str, lang: str, keywords: str = "", outline: str = "", words: int = 900) -> list[dict]:
    return _msg(
        f"Write a complete, original blog article in {_lang(lang)} (about {words} words) on: {topic}\n"
        f"Keywords to include naturally: {keywords or '-'}\nOutline to follow (optional): {outline or '-'}\n"
        f"Use an engaging introduction, H2/H3 sections and a conclusion. {HTML_RULE}"
    )


def excerpt(content: str, lang: str) -> list[dict]:
    return _msg(f"Write a 2-sentence excerpt in {_lang(lang)} (plain text, <=40 words) for this article:\n{content[:4000]}")


def suggest_tags(content: str, lang: str) -> list[dict]:
    return _msg(f"Suggest 5-8 short tags in {_lang(lang)} for the content below. Return them comma-separated on one line.\n{content[:3000]}")


def alt_text(name: str, lang: str) -> list[dict]:
    return _msg(f"Write a concise image alt text (<=100 chars) in {_lang(lang)} for a product photo of: {name}")


def parse_json_loose(text: str) -> dict:
    """Extract a JSON object from a model reply, tolerating ``` fences and chatter."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("No JSON object in AI reply")
    return json.loads(m.group(0))


def strip_fences(text: str) -> str:
    text = text.strip()
    m = re.fullmatch(r"```(?:html|markdown|md)?\s*(.*?)\s*```", text, re.S)
    return m.group(1) if m else text
