"""Tiny i18n: English source strings are the keys; Persian translations live in fa.py."""
from .config import cfg


def t(text: str) -> str:
    if cfg.language == "fa":
        from .fa import FA

        return FA.get(text, text)
    return text
