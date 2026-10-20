"""The translation tables of the user interface, one module per language (see i18n).

Each module holds ``TEXTS``: the English text as written in the code -> the translation, with the
same placeholders. English itself has no module. The modules are imported here by name so that
PyInstaller packs them (i18n loads them by their code).
"""

from ifc_converter.languages import de, es, fr, it, nl, pl, pt, tr  # noqa: F401
