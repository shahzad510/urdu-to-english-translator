"""Read and write the text and Word files used by the window."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from docx.table import Table
from docx.text.paragraph import Paragraph

from urdu_translator.errors import DocumentError
from urdu_translator.translation.segments import contains_urdu

_TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "utf-16", "cp1256")


def read_document(path: Path) -> str:
    """Load a ``.txt`` or ``.docx`` file as plain text, one paragraph per line."""
    source = Path(path)
    if not source.is_file():
        raise DocumentError(f"Could not open {source.name}. The file is missing.")
    suffix = source.suffix.lower()
    try:
        if suffix == ".txt":
            return _read_txt(source)
        if suffix == ".docx":
            return _read_docx(source)
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError(f"Could not read {source.name}. {exc}") from exc
    raise DocumentError("Open a .txt or .docx file.")


def write_txt(path: Path, text: str) -> None:
    """Save ``text`` as UTF-8."""
    destination = Path(path)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise DocumentError(f"Could not save {destination.name}. {exc}") from exc


def write_translation_docx(
    path: Path,
    *,
    urdu: str,
    english: str,
    gist: str,
    gist_level: str = "",
) -> None:
    """Save the Urdu source, the English translation, and the contextual summary.

    Each section has a heading. Blank lines stay blank paragraphs. Urdu lines
    are right to left; English and the summary stay left to right.
    """
    destination = Path(path)
    try:
        document = Document()
        _prepare_document(document)
        _add_section(document, "Urdu Text", urdu, first=True)
        _add_section(document, "English Translation", english, first=False)
        _add_section(
            document,
            "Gist / Contextual Summary",
            gist,
            first=False,
            level=gist_level,
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        document.save(str(destination))
    except DocumentError:
        raise
    except OSError as exc:
        raise DocumentError(f"Could not save {destination.name}. {exc}") from exc
    except Exception as exc:
        raise DocumentError(f"Could not create the Word document. {exc}") from exc


def write_docx(path: Path, text: str) -> None:
    """Save ``text`` as a Word document, one source line per paragraph.

    Paragraphs are left-to-right so an Urdu speaker label stays at the start
    of the line and the English translation follows it.
    """
    destination = Path(path)
    try:
        document = Document()
        _prepare_document(document)
        for line in text.split("\n"):
            paragraph = document.add_paragraph(line)
            paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(2)
            _force_ltr(paragraph)
            _apply_run_fonts(paragraph)
        destination.parent.mkdir(parents=True, exist_ok=True)
        document.save(str(destination))
    except DocumentError:
        raise
    except OSError as exc:
        raise DocumentError(f"Could not save {destination.name}. {exc}") from exc
    except Exception as exc:
        raise DocumentError(f"Could not create the Word document. {exc}") from exc


def _read_txt(path: Path) -> str:
    data = path.read_bytes()
    for encoding in _TEXT_ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeError:
            continue
    raise DocumentError(f"{path.name} is not valid UTF-8, UTF-16, or Windows Urdu text.")


def _read_docx(path: Path) -> str:
    """Read paragraphs and tables in document order.

    Report files store headings in single-column tables and field pairs in
    wider tables. Merged cells are repeated by the reader, so consecutive
    copies of the same cell are kept once. A label/value pair becomes one
    line, and a dialogue cell keeps its internal line breaks.
    """
    document = Document(str(path))
    lines: list[str] = []
    previous_was_table = False
    for block in _iter_blocks(document):
        if isinstance(block, Paragraph):
            if previous_was_table and lines and lines[-1] != "":
                lines.append("")
            lines.append(block.text)
            previous_was_table = False
            continue
        if lines and lines[-1] != "":
            lines.append("")
        lines.extend(_table_lines(block))
        previous_was_table = True
    return "\n".join(lines)


def _iter_blocks(document: Document):
    parent = document
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, parent)
        elif child.tag == qn("w:tbl"):
            yield Table(child, parent)


def _table_lines(table: Table) -> list[str]:
    lines: list[str] = []
    for row in table.rows:
        nonempty = [text.strip() for text in _unique_cell_texts(row) if text.strip()]
        if not nonempty:
            lines.append("")
            continue
        if len(nonempty) == 1:
            lines.extend(nonempty[0].split("\n"))
            continue
        if len(nonempty) % 2 == 0:
            for index in range(0, len(nonempty), 2):
                lines.append(_join_field(nonempty[index], nonempty[index + 1]))
            continue
        lines.append("\t".join(nonempty))
    return lines


def _unique_cell_texts(row) -> list[str]:
    values: list[str] = []
    for cell in row.cells:
        if values and values[-1] == cell.text:
            continue
        values.append(cell.text)
    return values


def _join_field(label: str, value: str) -> str:
    if not value:
        return label
    if label.endswith((":", "：")):
        return f"{label} {value}"
    return f"{label}\t{value}"


def _add_section(
    document: Document,
    title: str,
    body: str,
    *,
    first: bool,
    level: str = "",
) -> None:
    heading = document.add_paragraph()
    heading.alignment = WD_ALIGN_PARAGRAPH.LEFT
    heading.paragraph_format.space_before = Pt(0 if first else 16)
    heading.paragraph_format.space_after = Pt(6)
    run = heading.add_run(title)
    run.bold = True
    run.font.name = "Calibri"
    run.font.size = Pt(16)
    run.font.color.rgb = RGBColor(0x00, 0x00, 0x00)
    _force_ltr(heading)
    _apply_run_fonts(heading)
    for heading_run in heading.runs:
        heading_run.bold = True
        heading_run.font.size = Pt(16)
        heading_run.font.color.rgb = RGBColor(0x00, 0x00, 0x00)
    if level.strip():
        note = document.add_paragraph(f"Summary level: {level.strip()}")
        note.alignment = WD_ALIGN_PARAGRAPH.LEFT
        note.paragraph_format.space_before = Pt(0)
        note.paragraph_format.space_after = Pt(6)
        _force_ltr(note)
        _apply_run_fonts(note)
    text = body if body.strip() else ""
    lines = text.split("\n") if text else [""]
    for line in lines:
        paragraph = document.add_paragraph(line)
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(2)
        right_to_left = bool(line) and contains_urdu(line)
        if right_to_left:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            _force_rtl(paragraph)
        else:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
            _force_ltr(paragraph)
        _apply_run_fonts(paragraph)


def _prepare_document(document: Document) -> None:
    section = document.sections[0]
    for margin in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
        setattr(section, margin, Inches(0.85))
    normal = document.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(12)
    normal.font.color.rgb = RGBColor(0x1C, 0x19, 0x15)


def _set_bidi(paragraph, value: str) -> None:
    properties = paragraph._p.get_or_add_pPr()
    bidi = properties.find(qn("w:bidi"))
    if bidi is None:
        bidi = OxmlElement("w:bidi")
        properties.append(bidi)
    bidi.set(qn("w:val"), value)


def _force_ltr(paragraph) -> None:
    _set_bidi(paragraph, "0")


def _force_rtl(paragraph) -> None:
    _set_bidi(paragraph, "1")


def _apply_run_fonts(paragraph) -> None:
    """Use Calibri for English and Arial for any Urdu still in the line.

    Arial ships with Windows and contains Arabic-script glyphs, so speaker
    names remain visible in Word without installing another font.
    """
    for run in paragraph.runs:
        run.font.name = "Calibri"
        run.font.size = Pt(12)
        fonts = run._element.get_or_add_rPr().get_or_add_rFonts()
        fonts.set(qn("w:ascii"), "Calibri")
        fonts.set(qn("w:hAnsi"), "Calibri")
        fonts.set(qn("w:cs"), "Arial")
