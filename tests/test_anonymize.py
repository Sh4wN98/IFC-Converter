"""Anonymising the log: invented names only, in the line formats of a real log of the app."""

import logging
import re

import pytest

from ifc_converter import app
from ifc_converter.anonymize import Anonymizer, anonymize

USER = "mmuster"
COMPUTER = "BUERO-PC17"
SERVER = "fileserver01"
SOURCE = r"\\fileserver01\Users$\mmuster\Desktop\Projekt X\Haus A.ifc"
TARGET = r"\\fileserver01\Users$\mmuster\Desktop\Projekt X\Haus A.3dm"

LOG = rf"""2026-09-30 08:12:01,100 INFO    [4711] ifc_converter: IFC Converter 0.2.5 gestartet (GUI)
2026-09-30 08:12:01,101 INFO    [4711] ifc_converter: System: Windows-11-10.0.26100-SP0, 32 logische Kerne, 101.3 GB RAM frei
2026-09-30 08:12:01,102 INFO    [4711] ifc_converter: Komponenten: IFC Converter 0.2.5, Python 3.13.15, IfcOpenShell 0.9.0, rhino3dm 8.35.0, Qt 6.11.2, PySide6 6.11.2, NumPy 2.5.3, System Windows 11 (AMD64)
2026-09-30 08:12:30,000 INFO    [4711] ifc_converter.process: Umwandlung: {SOURCE} (611.5 MB) -> {TARGET}, Format 3dm, 16 Threads, geometry=brep, kernel=accurate
2026-09-30 08:13:30,000 INFO    [4711] ifc_converter.process: IFC-Datei wird gelesen (611 MB) … (nach 60 s)
2026-09-30 08:14:30,000 INFO    [4711] ifc_converter.process: Läuft seit 120 s, 35 %: Geometrie wird berechnet (16 Threads) …
2026-09-30 08:15:00,000 INFO    [4711] ifc_converter.process: Tief verschachteltes Bauteil (5004 Ebenen) 1 von 2 wird einzeln berechnet: IfcCovering 2ZLyRk6BAL6bNsO1TmDoEc „Belag Bad Familie Muster“ … (nach 150 s)
2026-09-30 08:16:00,000 WARNING [4711] ifc_converter.process: Umwandlung abgestürzt (Code 0xC00000FD) (Exit-Code 3221225725) – Neuer Versuch (2. von höchstens 7), dieses Bauteil wird übersprungen …
2026-09-30 08:16:00,001 WARNING [4711] ifc_converter.process: Ausgabe des Umwandlungsprozesses:
Windows fatal exception: stack overflow

Thread 0x00001ddc (most recent call first):
  File "ifc_converter\converter.py", line 398 in _iterate
  File "multiprocessing\connection.py", line 1054 in _exhaustive_wait
  File "C:\Users\mmuster\AppData\Local\Programs\Python\Python313\Lib\site-packages\ifcopenshell\geom\main.py", line 120 in create_shape
  File "pyi_rth_multiprocessing.py", line 81 in _freeze_support
2026-09-30 08:17:00,000 INFO    [4711] ifc_converter.process: Wird ins Zielverzeichnis kopiert (812 MB) … (nach 270 s)
2026-09-30 08:17:01,000 INFO    [4711] ifc_converter.process: Zwischendatei: C:\Users\mmuster\AppData\Local\Temp\ifc-converter-x1y2z3\Haus A.3dm
2026-09-30 08:18:00,000 INFO    [4711] ifc_converter.process: Fertig nach 330.1 s: {SOURCE} -> {TARGET}, 60541 Bauteile, 3 ohne Geometrie, 1 übersprungen
2026-09-30 08:18:00,001 WARNING [4711] ifc_converter.process: Übersprungen, weil der Geometriekern daran abstürzte oder hängen blieb (1):
  IfcCovering 2ZLyRk6BAL6bNsO1TmDoEc „Belag Bad Familie Muster“
2026-09-30 08:18:00,002 INFO    [4711] ifc_converter.process: Ohne Geometrie (2):
  IfcWall 1hqIFTRjfV6AWq_bMtnZwI „Wand Kinderzimmer Max“
  IfcSlab 0xScRe4drECQ4DMSqUjd6d
2026-09-30 08:19:00,000 ERROR   [4711] ifc_converter.process: Fehler nach 52.3 s bei P:\Kunden\Meier & Söhne\2026 Neubau\Haus 1.2 final.ifc: AssertionError: daemonic processes are not allowed to have children
2026-09-30 08:19:30,000 INFO    [4711] ifc_converter.process: Fertig nach 9.0 s: C:\Users\mmuster\Documents\Haus_B.ifc -> C:\Users\mmuster\Desktop\Haus_B (2).glb, 10 Bauteile, 0 ohne Geometrie, 0 übersprungen
2026-09-30 08:20:00,000 INFO    [4711] ifc_converter.gui: Zweiter Start auf BUERO-PC17: 1 Pfad(e) übernommen
2026-09-30 08:21:00,000 INFO    [4711] ifc_converter.process: Abgebrochen nach 29.0 s: /home/mmuster/Projekte/Haus C.ifc
"""

PERSONAL = [USER, COMPUTER, SERVER, "Projekt X", "Haus A", "Haus_B", "Haus C", "Haus 1.2", "Meier", "Kunden",
            "Neubau", "Belag Bad", "Familie Muster", "Kinderzimmer", "Projekte"]


@pytest.fixture
def anonymizer():
    return Anonymizer(users=[USER], computers=[COMPUTER])


def test_nothing_personal_survives(anonymizer):
    text = anonymizer.text(LOG)
    for word in PERSONAL:
        assert word.lower() not in text.lower(), word
    assert len(text.splitlines()) == len(LOG.splitlines())


def test_network_and_local_paths_keep_their_kind_and_pair_input_with_output(anonymizer):
    lines = anonymizer.text(LOG).splitlines()
    start = next(line for line in lines if "Umwandlung: " in line)
    assert start.endswith(
        r"Umwandlung: \\<Server>\<Freigabe>\<Benutzer>\Desktop\<Ordner>\Datei-1.ifc (611.5 MB) -> "
        r"\\<Server>\<Freigabe>\<Benutzer>\Desktop\<Ordner>\Datei-1.3dm, Format 3dm, 16 Threads, geometry=brep, "
        "kernel=accurate"
    )
    done = next(line for line in lines if "Fertig nach 330.1 s" in line)
    assert "Datei-1.ifc -> " in done and "Datei-1.3dm, 60541 Bauteile, 3 ohne Geometrie" in done
    assert any(r"bei P:\<Ordner>\<Ordner>\<Ordner>\Datei-2.ifc: AssertionError: daemonic" in line for line in lines)
    assert any(r"C:\Users\<Benutzer>\Documents\Datei-3.ifc -> C:\Users\<Benutzer>\Desktop\Datei-3 (2).glb, 10 Bauteile"
               in line for line in lines)
    assert any(r"C:\Users\<Benutzer>\AppData\Local\Temp\ifc-converter-x1y2z3\Datei-1.3dm" in line for line in lines)
    assert any(line.endswith("Abgebrochen nach 29.0 s: /home/<Benutzer>/<Ordner>/Datei-4.ifc") for line in lines)
    assert any("Zweiter Start auf <Rechner>: 1 Pfad(e)" in line for line in lines)


def test_element_names_go_class_and_globalid_stay(anonymizer):
    text = anonymizer.text(LOG)
    assert "  IfcCovering 2ZLyRk6BAL6bNsO1TmDoEc\n" in text
    assert "einzeln berechnet: IfcCovering 2ZLyRk6BAL6bNsO1TmDoEc … (nach 150 s)" in text
    assert "  IfcWall 1hqIFTRjfV6AWq_bMtnZwI\n  IfcSlab 0xScRe4drECQ4DMSqUjd6d\n" in text
    assert "„" not in text


def test_everything_else_stays(anonymizer):
    text = anonymizer.text(LOG)
    for kept in [
        "2026-09-30 08:12:01,101 INFO    [4711] ifc_converter: System: Windows-11-10.0.26100-SP0, 32 logische Kerne, "
        "101.3 GB RAM frei",
        "IfcOpenShell 0.9.0, rhino3dm 8.35.0, Qt 6.11.2",
        "Läuft seit 120 s, 35 %: Geometrie wird berechnet (16 Threads) …",
        "(Code 0xC00000FD) (Exit-Code 3221225725)",
        "Windows fatal exception: stack overflow",
        'File "ifc_converter\\converter.py", line 398 in _iterate',  # relative program paths unchanged
        'File "multiprocessing\\connection.py", line 1054 in _exhaustive_wait',
        'File "pyi_rth_multiprocessing.py", line 81 in _freeze_support',
        # Absolute program paths: the user goes, the package path stays.
        'File "C:\\Users\\<Benutzer>\\AppData\\Local\\Programs\\<Ordner>\\<Ordner>\\Lib\\site-packages\\ifcopenshell'
        '\\geom\\main.py", line 120 in create_shape',
    ]:
        assert kept in text, kept


def test_the_same_name_keeps_its_pseudonym_and_copies_are_marked(anonymizer):
    assert anonymizer.file_name("Haus A.ifc") == "Datei-1.ifc"
    assert anonymizer.file_name("haus a.3dm") == "Datei-1.3dm"
    assert anonymizer.file_name("Haus A (2).3dm") == "Datei-1 (2).3dm"
    assert anonymizer.file_name("Haus A.glb.indices.tmp") == "Datei-1.glb.indices.tmp"
    assert anonymizer.file_name("Haus 1.2 final.ifc") == "Datei-2.ifc"
    assert anonymizer.file_name("Datei-1.ifc") == "Datei-1.ifc"  # already anonymous


def test_paths_end_where_the_text_goes_on(anonymizer):
    line = anonymizer.line(r"Fehler bei D:\IFC Test\Haus A.ifc: Datei kaputt, 3/4 fertig, siehe C:\Temp\x y (Ordner)")
    assert line == r"Fehler bei D:\<Ordner>\Datei-1.ifc: Datei kaputt, 3/4 fertig, siehe C:\Temp\<Ordner> (Ordner)"
    assert anonymizer.line("Ausgabeordner: P:\\Projekte\\2026 Neubau") == "Ausgabeordner: P:\\<Ordner>\\<Ordner>"
    assert anonymizer.line("Quellcode: https://github.com/Sh4wN98/IFC-Converter") == \
        "Quellcode: https://github.com/Sh4wN98/IFC-Converter"
    assert anonymizer.line("Haus_B.ifc wird umgewandelt (1/2)") == "Datei-2.ifc wird umgewandelt (1/2)"


def test_short_user_names_are_only_replaced_in_paths():
    anonymizer = Anonymizer(users=["jo"], computers=[])
    assert anonymizer.line(r"C:\Users\jo\Desktop\a.ifc, jo joggt") == r"C:\Users\<Benutzer>\Desktop\Datei-1.ifc, jo joggt"


def test_own_names_by_default(monkeypatch):
    monkeypatch.setenv("USERNAME", "erika.musterfrau")
    monkeypatch.setenv("COMPUTERNAME", "WS-4711")
    assert anonymize("Benutzer erika.musterfrau auf WS-4711") == "Benutzer <Benutzer> auf <Rechner>"


@pytest.fixture
def user_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "config_dir", lambda: tmp_path / "config")
    monkeypatch.setattr(app, "log_dir", lambda: tmp_path / "logs")
    yield tmp_path
    app.stop_logging()


def test_anonymised_copy_of_all_log_files(user_dirs, monkeypatch):
    monkeypatch.setenv("USERNAME", USER)
    logs = user_dirs / "logs"
    logs.mkdir()
    (logs / "ifc-converter.log.2").write_text(f"alt: {SOURCE}\n", encoding="utf-8")
    (logs / "ifc-converter.log.1").write_text(f"mittel: {TARGET}\n", encoding="utf-8")
    (logs / "ifc-converter.log").write_text("neu: IfcWall 1hqIFTRjfV6AWq_bMtnZwI „Wand“\n", encoding="utf-8")
    target = app.write_anonymized_log(user_dirs / "anonym.txt")
    assert target.read_text(encoding="utf-8").splitlines() == [
        r"alt: \\<Server>\<Freigabe>\<Benutzer>\Desktop\<Ordner>\Datei-1.ifc",
        r"mittel: \\<Server>\<Freigabe>\<Benutzer>\Desktop\<Ordner>\Datei-1.3dm",
        "neu: IfcWall 1hqIFTRjfV6AWq_bMtnZwI",
    ]


def test_the_copy_includes_the_crash_log_of_the_window(user_dirs, monkeypatch):
    monkeypatch.setenv("USERNAME", USER)
    logs = user_dirs / "logs"
    logs.mkdir()
    (logs / "ifc-converter.log").write_text("neu\n", encoding="utf-8")
    (logs / "crash.log").write_text(f"Windows fatal exception: access violation\n  File \"{SOURCE}\"\n", encoding="utf-8")
    target = app.write_anonymized_log(user_dirs / "anonym.txt")
    lines = target.read_text(encoding="utf-8").splitlines()
    assert lines[:3] == ["neu", "", "===== crash.log ====="]
    assert lines[3] == "Windows fatal exception: access violation"
    assert "<Benutzer>" in lines[4] and USER not in lines[4]


def test_no_log_no_copy(user_dirs):
    with pytest.raises(FileNotFoundError):
        app.write_anonymized_log(user_dirs / "anonym.txt")


def test_log_file_is_always_written_anonymised(user_dirs, monkeypatch):
    # There is no setting for it: the log never holds user, server, folder, file or element names.
    monkeypatch.setenv("USERNAME", USER)
    (user_dirs / "config").mkdir()
    app.settings_path().write_text("[General]\nformat=3dm\nanonymize_log=false\n", encoding="utf-8")  # ignored
    for kind in ("GUI", "CLI"):
        path = app.setup_logging(kind)
        logging.getLogger("ifc_converter.process").info("Umwandlung: %s -> %s", SOURCE, TARGET)
        logging.getLogger("ifc_converter").info("Fertig: IfcWall 1hqIFTRjfV6AWq_bMtnZwI „Wand“")
        app.stop_logging()
        text = path.read_text(encoding="utf-8")
        assert r"Umwandlung: \\<Server>\<Freigabe>\<Benutzer>\Desktop\<Ordner>\Datei-1.ifc -> " in text
        assert "Fertig: IfcWall 1hqIFTRjfV6AWq_bMtnZwI\n" in text
        assert SOURCE not in text and "fileserver01" not in text and "Wand" not in text


def test_placeholders_follow_the_language():
    from ifc_converter import i18n

    i18n.set_language("en")
    try:
        anonymizer = Anonymizer(users=[USER], computers=[COMPUTER])
        assert anonymizer.line(f"Umwandlung: {SOURCE} -> {TARGET}") == (
            r"Umwandlung: \\<server>\<share>\<user>\Desktop\<folder>\File-1.ifc -> "
            r"\\<server>\<share>\<user>\Desktop\<folder>\File-1.3dm")
        assert anonymizer.file_name("File-1.ifc") == "File-1.ifc"  # already anonymous
        assert anonymizer.file_name("Datei-1.ifc") == "File-2.ifc"  # in English, a name like any other
        assert anonymize("Benutzer mmuster auf BUERO-PC17", anonymizer) == "Benutzer <user> auf <computer>"
    finally:
        i18n.set_language("de")
    # An Anonymizer keeps the placeholders of the language it was created in.
    assert anonymizer.line(r"C:\Users\mmuster\x.ifc") == r"C:\Users\<user>\File-3.ifc"
    assert Anonymizer(users=[USER], computers=[]).line(r"C:\Users\mmuster\x.ifc") == r"C:\Users\<Benutzer>\Datei-1.ifc"
