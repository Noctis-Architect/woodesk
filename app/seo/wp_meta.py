from __future__ import annotations

SEO_KEYS = {
    "yoast": ("_yoast_wpseo_title", "_yoast_wpseo_metadesc", "_yoast_wpseo_focuskw"),
    "rankmath": ("rank_math_title", "rank_math_description", "rank_math_focus_keyword"),
}


def meta_value(item: dict, key: str) -> str:
    for meta in item.get("meta_data", []) or []:
        if meta.get("key") == key:
            return str(meta.get("value") or "")
    return ""
