"""Text and Word export keep one source line per paragraph."""

from pathlib import Path

from docx import Document

from urdu_translator.documents import read_document, write_docx, write_txt


def test_txt_round_trip_keeps_urdu(tmp_path: Path):
    path = tmp_path / "notes.txt"
    write_txt(path, "جمال :۔سلام\n\nشیخ:۔ ٹھیک ہے۔\n")
    assert read_document(path) == "جمال :۔سلام\n\nشیخ:۔ ٹھیک ہے۔\n"


def test_docx_table_keeps_field_pairs_and_speaker_lines(tmp_path: Path):
    document = Document()
    document.add_paragraph("MONITORING REPORT")
    table = document.add_table(rows=3, cols=6)
    fields = table.rows[0].cells
    fields[1].text = "Freq:"
    fields[2].text = "462.225 MHz"
    fields[4].text = "Lang:"
    fields[5].text = "Urdu"
    table.rows[1].cells[0].text = "جمال :۔سلام\nشیخ:۔ ٹھیک ہے۔"
    table.rows[2].cells[0].text = "Analysis: ۔ متن"
    path = tmp_path / "report.docx"
    document.save(str(path))

    text = read_document(path)
    assert "MONITORING REPORT" in text
    assert "Freq: 462.225 MHz" in text
    assert "Lang: Urdu" in text
    assert "جمال :۔سلام" in text
    assert "شیخ:۔ ٹھیک ہے۔" in text
    assert "Analysis: ۔ متن" in text


def test_docx_round_trip_keeps_blank_paragraphs(tmp_path: Path):
    path = tmp_path / "notes.docx"
    original = "ROC/ Area:\nA-5/ Shahrag\n\nجمال :۔ Hello there"
    write_docx(path, original)
    assert read_document(path) == original

    document = Document(str(path))
    assert [paragraph.text for paragraph in document.paragraphs] == [
        "ROC/ Area:",
        "A-5/ Shahrag",
        "",
        "جمال :۔ Hello there",
    ]
