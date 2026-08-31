"""Proof of delivery as a document, not a checkbox.

WHY THIS EXISTS SEPARATELY FROM THE DELIVERED EVENT
A driver tapping "delivered" is an assertion by an interested party. The
schema already keeps proof_of_delivery in its own table with an
evidence_strength, and billing already reads that rather than the status
field. What was missing is the document itself: a signed bill of lading that a
customer disputing an invoice can actually be shown.

WHAT A STORED POD ESTABLISHES
That a file with THIS sha256 was bound to THIS load at THIS time by THIS
organisation. That is a chain of custody over the artifact. It is not a
verification that the signature is genuine -- nothing here reads handwriting
-- and `evidence_strength` stays the caller's honest claim about what the
document is.

THE ATTACKS THIS REFUSES
  wrong load        a POD binds to one load; the row is unique per load
  duplicate         re-uploading the SAME bytes is idempotent; DIFFERENT bytes
                    under an existing POD is a conflict, not an overwrite
  altered document  the hash is recorded at bind time; verify() re-reads the
                    file and compares, so a later edit is detectable
  cross-tenant      the path carries the org, and a ref from another tenant
                    does not resolve
  superseded        a replacement is an explicit supersede that keeps the
                    original, because an invoice may already cite it
"""
from __future__ import annotations

import hashlib
import pathlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

POD_VERSION = "pod-2026.08.29"

ALLOWED_DOC_MIME = {
    "application/pdf", "image/jpeg", "image/png", "image/heic", "image/webp",
    "image/tiff",
}
MAX_DOC_BYTES = 32 * 1024 * 1024

#: What kind of thing the document is. Ordered weakest to strongest; billing
#: accepts only the top three (see billing.BILLABLE_POD_STRENGTH).
STRENGTHS = ("ASSERTED_BY_DRIVER", "RECEIVER_ACKNOWLEDGED",
             "SIGNED_DOCUMENT", "EDI_CONFIRMED")


class PodRefused(RuntimeError):
    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def storage_root() -> pathlib.Path:
    import os
    root = os.environ.get("FINTRA_POD_ROOT")
    if root:
        return pathlib.Path(root).expanduser()
    return pathlib.Path.home() / ".fintra" / "pod-documents"


@dataclass
class StoredDocument:
    org_id: object
    load_id: object
    storage_ref: str
    sha256: str
    byte_size: int
    mime_type: str
    #: Other loads in this tenant already holding a file with the same hash.
    #: Empty is the normal case. Non-empty means one signed document is about
    #: to release a second invoice, which a human has to agree to.
    also_on_load_ids: tuple = ()
    stored_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc))

    @property
    def reused_from_another_load(self) -> bool:
        return bool(self.also_on_load_ids)


def _doc_path(org_id, load_id, sha: str, ext: str) -> pathlib.Path:
    """org/load/<hash>.ext.

    Content-addressed on purpose: the same document uploaded twice lands on
    the same path, which is what makes a retry idempotent instead of a
    conflict.
    """
    return storage_root() / str(org_id) / str(load_id) / f"{sha[:32]}{ext}"


def _ext_for(mime: str) -> str:
    return {"application/pdf": ".pdf", "image/jpeg": ".jpg",
            "image/png": ".png", "image/heic": ".heic",
            "image/webp": ".webp", "image/tiff": ".tif"}.get(
        mime.split(";")[0].strip().lower(), ".bin")


def store_document(*, org_id, load_id, data: bytes,
                   mime_type: str) -> StoredDocument:
    if not data:
        raise PodRefused(
            "EMPTY_DOCUMENT",
            "the upload contained no bytes. A POD row pointing at an empty "
            "file claims evidence that does not exist.")
    if len(data) > MAX_DOC_BYTES:
        raise PodRefused("DOCUMENT_TOO_LARGE",
                         f"{len(data)} bytes exceeds {MAX_DOC_BYTES}")

    base = mime_type.split(";")[0].strip().lower()
    if base not in ALLOWED_DOC_MIME:
        raise PodRefused(
            "UNSUPPORTED_DOCUMENT_TYPE",
            f"{mime_type!r} is not accepted. A POD is a scan or a photo: "
            f"{sorted(ALLOWED_DOC_MIME)}")

    sha = hashlib.sha256(data).hexdigest()

    # ONE SIGNATURE, TWO LOADS.
    #
    # Storage is per-load, so the identical signed document could be attached
    # to a second load with nothing said. A POD is what releases an invoice, so
    # that is one signature releasing two of them -- billing a customer twice
    # on evidence that proves one delivery, and the document would look
    # perfectly good in a dispute over either.
    #
    # NOT REFUSED. A consolidated bill of lading covering more than one
    # shipment is a real thing in freight, and a rule that made it impossible
    # would be wrong more often than the fraud it prevents. What is not
    # acceptable is it happening SILENTLY, so the reuse is detected, named on
    # the row, and left for a human -- the same answer this codebase gives
    # everywhere else it has evidence pointing two ways at once.
    also_on = _same_document_on_other_loads(org_id, sha, exclude_load_id=load_id)

    path = _doc_path(org_id, load_id, sha, _ext_for(base))
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)

    return StoredDocument(org_id=org_id, load_id=load_id,
                          storage_ref=str(path), sha256=sha,
                          byte_size=len(data), mime_type=base,
                          also_on_load_ids=also_on)


def _same_document_on_other_loads(org_id, sha256: str, *,
                                  exclude_load_id) -> tuple:
    """Load directories in this tenant already holding a file with this hash.

    Filesystem rather than database on purpose: this module owns the bytes and
    knows nothing about rows, and the question is about the bytes.
    """
    root = (storage_root() / str(org_id))
    if not root.is_dir():
        return ()
    found = []
    for load_dir in sorted(root.iterdir()):
        if not load_dir.is_dir() or load_dir.name == str(exclude_load_id):
            continue
        # _doc_path names the file with sha[:32], not the whole digest.
        # Comparing the full hash here matched nothing and the detection
        # silently never fired -- which is worse than not having it.
        stem = sha256[:32]
        if any(f.stem == stem for f in load_dir.iterdir() if f.is_file()):
            found.append(load_dir.name)
    return tuple(found)


def read_document(storage_ref: str, *, org_id) -> bytes:
    path = pathlib.Path(storage_ref).resolve()
    tenant_root = (storage_root() / str(org_id)).resolve()
    try:
        path.relative_to(tenant_root)
    except ValueError:
        raise PodRefused(
            "DOCUMENT_OUTSIDE_TENANT",
            "the stored reference resolves outside this organisation's "
            "document directory")
    if not path.is_file():
        raise PodRefused("DOCUMENT_MISSING",
                         f"the row references {storage_ref}, not on disk")
    return path.read_bytes()


@dataclass
class IntegrityResult:
    intact: bool
    code: str
    detail: str
    recorded_sha256: Optional[str] = None
    actual_sha256: Optional[str] = None


def verify_document(*, storage_ref: str, recorded_sha256: str,
                    org_id) -> IntegrityResult:
    """Re-read the file and compare it to the hash recorded when it was bound.

    This is what makes ALTERED DOCUMENT detectable. An invoice may cite this
    POD months later, and "the file on disk today" and "the file we accepted"
    are not the same claim unless something checks.
    """
    try:
        data = read_document(storage_ref, org_id=org_id)
    except PodRefused as exc:
        return IntegrityResult(False, exc.code, exc.detail,
                               recorded_sha256=recorded_sha256)

    actual = hashlib.sha256(data).hexdigest()
    if actual != recorded_sha256:
        return IntegrityResult(
            False, "DOCUMENT_ALTERED",
            ("the document on disk does not match the hash recorded when it "
             "was accepted. An invoice citing this POD is citing a different "
             "file than the one that was approved."),
            recorded_sha256=recorded_sha256, actual_sha256=actual)

    return IntegrityResult(True, "INTACT",
                           "the document matches the hash recorded at binding",
                           recorded_sha256=recorded_sha256,
                           actual_sha256=actual)


def validate_binding(*, load_org_id, actor_org_id, load_status: str,
                     existing_sha: Optional[str], new_sha: str,
                     evidence_strength: str) -> None:
    """Every reason a POD may not be attached to this load. Raises."""
    if str(load_org_id) != str(actor_org_id):
        raise PodRefused(
            "WRONG_TENANT",
            "this load belongs to another organisation")

    if evidence_strength not in STRENGTHS:
        raise PodRefused(
            "UNKNOWN_EVIDENCE_STRENGTH",
            f"{evidence_strength!r} is not one of {list(STRENGTHS)}")

    # A POD before the freight moved is not proof of anything.
    if load_status in ("DRAFT", "QUOTED", "BOOKED", "PLANNED", "CANCELLED"):
        raise PodRefused(
            "LOAD_NOT_DELIVERED",
            f"this load is {load_status}. A proof of delivery for freight "
            f"that has not been delivered is not evidence; it is a document "
            f"attached to the wrong thing.")

    if existing_sha is not None and existing_sha != new_sha:
        raise PodRefused(
            "POD_ALREADY_BOUND",
            "this load already has a different proof of delivery. Replacing "
            "it silently would change what an existing invoice cites; "
            "supersede it explicitly instead.")
