"""The language of the user interface.

Texts the user sees are written in English in the code and passed through ``tr``, which looks
them up in the table of the current language (see the ``languages`` package: one module per
language, holding the English text as key). A text without a translation is shown in English.
Placeholders use str.format syntax: ``tr("{count} files", count=3)``; a translation must keep the
same placeholders (tests/test_i18n.py checks that for every language).

The language is chosen once at start (settings, or the IFC_CONVERTER_LANG environment variable,
else English) and handed to the conversion child processes through that variable, so that their
status messages and notes arrive in the same language.
"""

from __future__ import annotations

import importlib
import os

# The package imports every language module by name, so that PyInstaller packs them: set_language
# loads them by their code, which the build cannot see.
import ifc_converter.languages  # noqa: F401

# Code -> the language's own name, in the order shown in the menu.
LANGUAGES = {
    "en": "English",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
    "it": "Italiano",
    "pt": "Português",
    "nl": "Nederlands",
    "pl": "Polski",
    "tr": "Türkçe",
}
DEFAULT_LANGUAGE = "en"
ENV = "IFC_CONVERTER_LANG"

_language = DEFAULT_LANGUAGE
_texts: dict[str, str] = {}


def normalize(code: str | None) -> str:
    """"de-DE", "de_AT.UTF-8" or "DE" -> "de"; unknown or empty -> the default (English)."""
    code = (code or "").strip().replace("_", "-").split(".")[0].split("-")[0].lower()
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


def language() -> str:
    """The code of the current language."""
    return _language


def set_language(code: str | None) -> str:
    """Switch the texts to ``code`` (see LANGUAGES; unknown -> English) and return the code used.
    Child processes started from now on inherit it through IFC_CONVERTER_LANG."""
    global _language, _texts
    _language = normalize(code)
    _texts = {} if _language == DEFAULT_LANGUAGE else dict(importlib.import_module(
        f"ifc_converter.languages.{_language}").TEXTS)
    os.environ[ENV] = _language
    return _language


def tr(text: str, **values) -> str:
    """``text`` (English) in the current language, with ``values`` filled in."""
    translated = _texts.get(text, text)
    return translated.format(**values) if values else translated


def language_from_environment() -> str:
    """The language a child process or the command line should use: IFC_CONVERTER_LANG, else English."""
    return normalize(os.environ.get(ENV))
