"""The dialogs in English (the tests in test_gui.py assert the German texts, see conftest)."""

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from ifc_converter import i18n
from ifc_converter.dialogs import KERNEL_INFO, AboutDialog, ErrorDialog, Preferences, SettingsDialog, SkippedDialog


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def english():
    i18n.set_language("en")
    yield
    i18n.set_language("de")


def test_settings_dialog_in_english(app, english):
    dialog = SettingsDialog(Preferences())
    assert [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())] == [
        "Performance", "Geometry kernel", "Output", "Log file",
    ]
    assert dialog.windowTitle() == "Settings"
    assert dialog.priority_check.text() == "Convert at low priority (recommended)"
    assert dialog.threads_spin.specialValueText().startswith("Automatic (")
    assert dialog.kernel_buttons["accurate"].text() == "Accurate (recommended)"
    assert dialog.threads_usage.text().startswith("With this, a conversion uses up to ")
    assert "<folder>" in dialog.anonymize_check.toolTip() and "File-1.ifc" in dialog.anonymize_check.toolTip()
    dialog.deleteLater()


def test_kernel_info_follows_the_language(english):
    assert KERNEL_INFO["hybrid"][0] == "Fast" and list(KERNEL_INFO) == ["accurate", "hybrid", "opencascade"]
    assert dict(KERNEL_INFO.items())["opencascade"][0] == "OpenCASCADE only"
    i18n.set_language("de")
    assert KERNEL_INFO["hybrid"] == (
        "Schnell", "3- bis 13-mal schneller, kann aber bei einzelnen Bauteilen Flächen weglassen oder doppelt erzeugen.")


def test_skipped_dialog_in_english(app, english):
    dialog = SkippedDialog("haus.ifc", ["IfcWall 2O2Fr$t4X7Zf8NOew3FLOH „Wand“"], ["IfcSlab 0xScRe4drECQ4DMSqUjd6d"],
                           skipped=3, inside=2)
    assert dialog.windowTitle() == "Skipped elements – haus.ifc"
    assert [dialog.table.horizontalHeaderItem(i).text() for i in range(4)] == ["Reason", "Class", "GlobalId", "Name"]
    assert dialog.rows[0] == ("Skipped (geometry kernel crashed)", "IfcWall", "2O2Fr$t4X7Zf8NOew3FLOH", "Wand")
    assert dialog.rows[1][0] == "Without geometry"
    texts = "\n".join(label.text() for label in dialog.findChildren(QLabel))
    assert "1 skipped because the geometry kernel crashed or hung on them; 3 without geometry (not convertible); " \
           "2 interior elements left out (building hull only)." in texts
    assert "2 more elements without geometry could not be named individually." in texts
    assert "How to find an element in the CAD program" in texts
    assert dialog._text(dialog.rows).startswith("Reason\tClass\tGlobalId\tName\nSkipped (geometry kernel crashed)\t")
    dialog.deleteLater()


def test_about_and_error_dialogs_in_english(app, english):
    about = AboutDialog()
    texts = [label.text() for label in about.findChildren(QLabel)]
    assert about.windowTitle() == "About IFC Converter"
    for expected in ("Component", "Version", "Licence", "Qt", "PySide6", "System"):
        assert expected in texts
    assert any(text.startswith("Converts IFC building models") for text in texts)
    about.deleteLater()
    error = ErrorDialog("ValueError: broken", "Traceback …")
    assert error.windowTitle() == "IFC Converter – Unexpected error"
    error.copy_details()
    assert error.copy_button.text() == "Copied ✓"
    error.deleteLater()
