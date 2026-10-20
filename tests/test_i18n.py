"""The user-interface language (i18n) and the completeness of the translation tables."""

import ast
import os
import re
from pathlib import Path

import pytest

from ifc_converter import i18n

SOURCES = Path(__file__).resolve().parent.parent / "src" / "ifc_converter"
PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)")


def tr_keys() -> dict[str, str]:
    """Every literal passed to tr() in the sources -> the file it is in."""
    keys = {}
    for path in SOURCES.rglob("*.py"):
        if path.parent.name == "languages":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr"
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                keys[node.args[0].value] = path.name
    return keys


@pytest.fixture
def english():
    before = i18n.language()
    i18n.set_language("en")
    yield
    i18n.set_language(before)


def test_english_is_the_default_and_the_fallback(english):
    assert i18n.language() == "en" and i18n.DEFAULT_LANGUAGE == "en"
    assert i18n.tr("IFC file") == "IFC file"
    assert i18n.tr("{count} files", count=3) == "3 files"
    assert i18n.normalize(None) == "en" and i18n.normalize("xx") == "en"
    assert i18n.normalize("de-DE") == "de" and i18n.normalize("pt_BR.UTF-8") == "pt" and i18n.normalize("FR") == "fr"


def test_switching_sets_the_environment_for_child_processes(english):
    assert i18n.set_language("de") == "de"
    assert os.environ[i18n.ENV] == "de" and i18n.language_from_environment() == "de"
    assert i18n.set_language("klingon") == "en" and os.environ[i18n.ENV] == "en"


def test_every_language_has_a_module_and_english_has_none():
    for code in i18n.LANGUAGES:
        if code == "en":
            assert not (SOURCES / "languages" / "en.py").exists()
        else:
            assert (SOURCES / "languages" / f"{code}.py").is_file()


@pytest.mark.parametrize("code", [code for code in i18n.LANGUAGES if code != "en"])
def test_translations_are_complete_and_keep_the_placeholders(code):
    keys = tr_keys()
    texts = __import__(f"ifc_converter.languages.{code}", fromlist=["TEXTS"]).TEXTS
    missing = sorted(key for key in keys if key not in texts)
    assert not missing, f"{code}: {len(missing)} texts without translation, e.g. {missing[:5]}"
    unused = sorted(key for key in texts if key not in keys)
    assert not unused, f"{code}: {len(unused)} translations of texts not in the code, e.g. {unused[:5]}"
    for key, translation in texts.items():
        assert translation and translation.strip(), f"{code}: empty translation of {key!r}"
        assert set(PLACEHOLDER.findall(key)) == set(PLACEHOLDER.findall(translation)), \
            f"{code}: placeholders differ for {key!r}: {translation!r}"


def test_the_german_table_is_used_by_tr(english):
    texts = __import__("ifc_converter.languages.de", fromlist=["TEXTS"]).TEXTS
    if not texts:
        pytest.skip("no German texts yet")
    key, translation = next(iter(texts.items()))
    i18n.set_language("de")
    assert i18n.tr(key) == translation
