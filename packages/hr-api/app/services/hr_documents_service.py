"""HR document upload: validate a file, read the text out of it, store it.

WHAT THIS DOES
An admin uploads a policy or benefits guide (PDF, Word, plain text or Markdown).
This module checks the file, extracts its text, and hands that text to the
helpdesk knowledge index in rag_service, which is what the AI helpdesk reads.

WHAT IT REFUSES TO DO
It never trusts the file name alone. A file called policy.pdf that does not
start like a PDF is refused. A Word file is only opened if it is a real zip with
a document part, and one that declares XML entities is refused, because those
can be used to blow up memory. A PDF with no text (usually a scan) is refused
with a clear message instead of being stored as an empty document the helpdesk
would silently never match.

WHAT IT DOES NOT DO YET
The original file is not kept. Only the extracted text and a few details about
the upload (name, size, hash, who, when) are stored, in the same in memory index
the helpdesk already uses, so uploaded documents are lost when the API restarts.
Durable storage and chunking belong to the vector store work in the same sprint.

This module keeps no state of its own, on purpose: there is one store, in
rag_service, and one place that says which documents exist.
"""
from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from xml.etree import ElementTree as ET

from app.services import rag_service

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARS = 200_000
MAX_PDF_PAGES = 200
MAX_DOCX_XML_BYTES = 20 * 1024 * 1024
MAX_TITLE_CHARS = 120

ALLOWED_EXTENSIONS = (".txt", ".md", ".pdf", ".docx")

_CATEGORY = re.compile(r"^[a-z0-9][a-z0-9 _-]{0,39}$")
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class DocumentError(Exception):
    """A document that cannot be accepted. `status` is the HTTP status to use."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class ParsedDocument:
    text: str
    kind: str            # txt | md | pdf | docx
    pages: Optional[int]  # PDF page count, else None


# --------------------------------------------------------------------------
# names and categories
# --------------------------------------------------------------------------
def extension_of(filename: str) -> str:
    name = (filename or "").strip().lower()
    dot = name.rfind(".")
    return name[dot:] if dot != -1 else ""


def default_title(filename: str) -> str:
    base = (filename or "").replace("\\", "/").split("/")[-1]
    stem = base.rsplit(".", 1)[0] if "." in base else base
    stem = re.sub(r"[_\-]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem[:MAX_TITLE_CHARS] or "Untitled document"


def clean_title(value: str) -> str:
    title = re.sub(r"[\x00-\x1f\x7f]", " ", value or "")
    title = re.sub(r"\s+", " ", title).strip()
    if not title:
        raise DocumentError("A title is required.", 400)
    if len(title) > MAX_TITLE_CHARS:
        raise DocumentError(f"The title is longer than {MAX_TITLE_CHARS} characters.", 400)
    return title


def clean_category(value: Optional[str]) -> str:
    category = (value or "policy").strip().lower()
    if not _CATEGORY.match(category):
        raise DocumentError(
            "The category must be 1 to 40 letters, numbers, spaces, dashes or underscores.", 400
        )
    return category


# --------------------------------------------------------------------------
# reading the file
# --------------------------------------------------------------------------
def _normalise(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _parse_text(data: bytes) -> str:
    if b"\x00" in data[:4096]:
        raise DocumentError("That file looks like binary data, not text.", 415)
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DocumentError("The text could not be read. Save it as UTF-8 and try again.", 422)


def _parse_docx(data: bytes) -> str:
    if not data.startswith(b"PK\x03\x04"):
        raise DocumentError("That file is not a real Word (.docx) document.", 415)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            try:
                info = zf.getinfo("word/document.xml")
            except KeyError:
                raise DocumentError("That file is not a real Word (.docx) document.", 415)
            if info.file_size > MAX_DOCX_XML_BYTES:
                raise DocumentError("That Word document is too large to read.", 413)
            xml = zf.read(info)
    except zipfile.BadZipFile:
        raise DocumentError("That file is not a real Word (.docx) document.", 415)
    # Entities can be nested to expand into gigabytes. A real document has none.
    head = xml.lower()
    if b"<!doctype" in head or b"<!entity" in head:
        raise DocumentError("That Word document contains data we do not accept.", 422)
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        raise DocumentError("That Word document could not be read.", 422)

    paragraphs: list[str] = []
    for para in root.iter(f"{_W}p"):
        parts: list[str] = []
        for node in para.iter():
            if node.tag == f"{_W}t" and node.text:
                parts.append(node.text)
            elif node.tag == f"{_W}tab":
                parts.append("\t")
            elif node.tag in (f"{_W}br", f"{_W}cr"):
                parts.append("\n")
        line = "".join(parts).strip()
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs)


def _parse_pdf(data: bytes) -> tuple[str, int]:
    if not data.startswith(b"%PDF-"):
        raise DocumentError("That file is not a real PDF.", 415)
    try:
        from pypdf import PdfReader
        from pypdf.errors import PyPdfError
    except Exception:  # pragma: no cover - depends on the install
        raise DocumentError("PDF reading is not installed on this server.", 501)
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise DocumentError("That PDF is password protected. Remove the password and try again.", 422)
        count = len(reader.pages)
        if count > MAX_PDF_PAGES:
            raise DocumentError(f"That PDF has more than {MAX_PDF_PAGES} pages. Split it and upload the parts.", 413)
        pages = [(page.extract_text() or "") for page in reader.pages]
    except DocumentError:
        raise
    except (PyPdfError, ValueError, KeyError, OSError, RecursionError):
        raise DocumentError("That PDF could not be read.", 422)
    except Exception:
        raise DocumentError("That PDF could not be read.", 422)
    return "\n\n".join(pages), count


def parse_document(filename: str, data: bytes) -> ParsedDocument:
    ext = extension_of(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise DocumentError(
            "That file type is not supported. Upload a " + ", ".join(ALLOWED_EXTENSIONS) + " file.", 415
        )
    if not data:
        raise DocumentError("That file is empty.", 422)
    if len(data) > MAX_FILE_BYTES:
        raise DocumentError(f"That file is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.", 413)

    pages: Optional[int] = None
    if ext in (".txt", ".md"):
        raw = _parse_text(data)
    elif ext == ".docx":
        raw = _parse_docx(data)
    else:
        raw, pages = _parse_pdf(data)

    text = _normalise(raw)
    if not text:
        if ext == ".pdf":
            raise DocumentError(
                "No text was found in that PDF. It may be a scan or an image. "
                "Upload a version with selectable text.", 422)
        raise DocumentError("No text was found in that file.", 422)
    if len(text) > MAX_TEXT_CHARS:
        raise DocumentError(
            f"That document is longer than {MAX_TEXT_CHARS:,} characters. Split it and upload the parts.", 413)
    return ParsedDocument(text=text, kind=ext.lstrip("."), pages=pages)


# --------------------------------------------------------------------------
# storing and managing
# --------------------------------------------------------------------------
def store_upload(
    *,
    org_id: str,
    user_id: str,
    filename: str,
    data: bytes,
    title: Optional[str] = None,
    category: Optional[str] = None,
) -> dict:
    """Validate, read and store one uploaded file. Raises DocumentError."""
    parsed = parse_document(filename, data)
    final_title = clean_title(title) if (title or "").strip() else default_title(filename)
    final_category = clean_category(category)
    digest = hashlib.sha256(data).hexdigest()

    for existing in rag_service.list_documents(org_id):
        if existing["status"] == "active" and existing["meta"].get("sha256") == digest:
            raise DocumentError(
                f"This file was already uploaded as \"{existing['title']}\".", 409)

    meta = {
        "filename": (filename or "").replace("\\", "/").split("/")[-1][:200],
        "kind": parsed.kind,
        "size_bytes": len(data),
        "sha256": digest,
        "pages": parsed.pages,
        "uploaded_by": user_id,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    created = rag_service.add_document(
        org_id, final_title, parsed.text, category=final_category, source="upload", meta=meta)
    return {
        **created,
        "status": "active",
        "filename": meta["filename"],
        "kind": parsed.kind,
        "size_bytes": meta["size_bytes"],
        "chars": len(parsed.text),
        "pages": parsed.pages,
    }


def _require(org_id: str, doc_id: str):
    doc = rag_service.get_document(org_id, doc_id)
    if doc is None:
        raise DocumentError("Document not found.", 404)
    return doc


def rename_or_recategorise(
    org_id: str, doc_id: str, *, title: Optional[str], category: Optional[str]
) -> dict:
    doc = _require(org_id, doc_id)
    if doc.source != "upload":
        raise DocumentError("Built in documents cannot be edited. You can archive them instead.", 409)
    if title is None and category is None:
        raise DocumentError("Send a title or a category to change.", 400)
    new_title = clean_title(title) if title is not None else None
    new_category = clean_category(category) if category is not None else None
    out = rag_service.update_document(org_id, doc_id, title=new_title, category=new_category)
    if out is None:  # removed between the check and the update
        raise DocumentError("Document not found.", 404)
    return out


def archive(org_id: str, doc_id: str) -> dict:
    _require(org_id, doc_id)
    out = rag_service.set_document_status(org_id, doc_id, "archived")
    if out is None:
        raise DocumentError("Document not found.", 404)
    return out


def restore(org_id: str, doc_id: str) -> dict:
    doc = _require(org_id, doc_id)
    digest = doc.meta.get("sha256")
    if digest:
        for other in rag_service.list_documents(org_id):
            if other["id"] != doc_id and other["status"] == "active" and other["meta"].get("sha256") == digest:
                raise DocumentError(
                    f"The same file is already active as \"{other['title']}\".", 409)
    out = rag_service.set_document_status(org_id, doc_id, "active")
    if out is None:
        raise DocumentError("Document not found.", 404)
    return out


def delete(org_id: str, doc_id: str) -> None:
    doc = _require(org_id, doc_id)
    if doc.source != "upload":
        raise DocumentError("Built in documents cannot be deleted. You can archive them instead.", 409)
    if not rag_service.remove_document(org_id, doc_id):
        raise DocumentError("Document not found.", 404)
