"""Reading text out of uploaded HR files, and refusing the ones we should.

No network and no live model. Real bytes for every format.

Run:  python -m pytest tests/test_hr_documents_parsing.py -v
"""
from __future__ import annotations

import pytest

from app.services import hr_documents_service as S
from tests._hr_doc_fixtures import make_blank_pdf, make_docx, make_pdf

POLICY = "Employees may work remotely up to three days a week with manager approval."


def _refused(filename: str, data: bytes) -> S.DocumentError:
    with pytest.raises(S.DocumentError) as info:
        S.parse_document(filename, data)
    return info.value


# --- the formats we accept -------------------------------------------------

def test_plain_text_is_read():
    out = S.parse_document("remote.txt", POLICY.encode())
    assert out.text == POLICY and out.kind == "txt" and out.pages is None


def test_markdown_is_read():
    out = S.parse_document("remote.md", f"# Remote work\n\n{POLICY}".encode())
    assert POLICY in out.text and out.kind == "md"


def test_word_document_paragraphs_are_read_in_order():
    data = make_docx(["Remote work policy", POLICY, "Ask HR with questions."])
    out = S.parse_document("remote.docx", data)
    assert out.text.splitlines() == ["Remote work policy", POLICY, "Ask HR with questions."]
    assert out.kind == "docx"


def test_pdf_text_is_read_and_pages_are_counted():
    out = S.parse_document("remote.pdf", make_pdf([POLICY]))
    assert "remotely up to three days" in out.text
    assert out.kind == "pdf" and out.pages == 1


def test_windows_1252_text_is_read_not_refused():
    out = S.parse_document("quote.txt", "The “policy” applies.".encode("cp1252"))
    assert "policy" in out.text


# --- the files we refuse ---------------------------------------------------

def test_unsupported_type_is_refused_with_415():
    err = _refused("macro.exe", b"MZ....")
    assert err.status == 415


def test_a_name_that_lies_about_its_type_is_refused():
    assert _refused("policy.pdf", b"this is just text").status == 415
    assert _refused("policy.docx", b"this is just text").status == 415


def test_binary_data_named_txt_is_refused():
    assert _refused("data.txt", b"\x00\x01\x02\x03binary").status == 415


def test_empty_file_is_refused():
    assert _refused("empty.txt", b"").status == 422


def test_whitespace_only_text_is_refused():
    assert _refused("blank.txt", b"   \n\n \t ").status == 422


def test_a_scanned_pdf_with_no_text_says_why():
    err = _refused("scan.pdf", make_blank_pdf())
    assert err.status == 422 and "scan" in err.message.lower()


def test_file_over_the_size_limit_is_refused_with_413():
    err = _refused("big.txt", b"a" * (S.MAX_FILE_BYTES + 1))
    assert err.status == 413


def test_text_over_the_character_limit_is_refused_with_413():
    err = _refused("long.txt", ("word " * 50_000).encode())
    assert err.status == 413


def test_word_file_declaring_entities_is_refused():
    bomb = '<!DOCTYPE d [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
    err = _refused("bomb.docx", make_docx(["hello"], extra_xml=bomb))
    assert err.status == 422


def test_a_zip_that_is_not_a_word_document_is_refused():
    import io, zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("hello.txt", "hi")
    assert _refused("fake.docx", buf.getvalue()).status == 415


def test_a_broken_pdf_is_refused_not_crashed():
    assert _refused("broken.pdf", b"%PDF-1.4\nthis is not a pdf body").status == 422


# --- cleaning --------------------------------------------------------------

def test_control_characters_and_blank_runs_are_cleaned():
    out = S.parse_document("a.txt", b"one\r\n\r\n\r\n\r\ntwo\x07  \nthree")
    assert out.text == "one\n\ntwo\nthree"


def test_default_title_comes_from_the_file_name():
    assert S.default_title("C:\\docs\\Remote_Work-policy.pdf") == "Remote Work policy"
    assert S.default_title("") == "Untitled document"


def test_title_and_category_are_checked():
    with pytest.raises(S.DocumentError):
        S.clean_title("   ")
    with pytest.raises(S.DocumentError):
        S.clean_title("x" * (S.MAX_TITLE_CHARS + 1))
    assert S.clean_category(None) == "policy"
    assert S.clean_category(" Time Off ") == "time off"
    with pytest.raises(S.DocumentError):
        S.clean_category("../etc")
