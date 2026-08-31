"""POD documents: the attacks, and the one property that matters months later.

`DELIVERED != POD` is already load-bearing in the schema and in billing. This
adds the document a customer disputing an invoice can actually be shown, and
tests the five ways that goes wrong: wrong load, duplicate, altered document,
cross-tenant, and a stale POD replaced without a trace.

The altered-document test is the one worth reading. An invoice may cite a POD
months after it was accepted, and "the file on disk today" is not the same
claim as "the file we approved" unless something re-reads and compares.
"""
from __future__ import annotations

import hashlib
import pathlib
import uuid

import pytest

from app.trucking import pod as P

PDF = b"%PDF-1.4\n" + b"signed bill of lading " * 64
OTHER = b"%PDF-1.4\n" + b"a different document " * 64


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("FINTRA_POD_ROOT", str(tmp_path / "pod"))


# ===========================================================================
# Storing
# ===========================================================================

def test_a_pod_is_stored_hashed_and_bound_to_the_load():
    org, load = uuid.uuid4(), uuid.uuid4()
    doc = P.store_document(org_id=org, load_id=load, data=PDF,
                           mime_type="application/pdf")
    assert doc.sha256 == hashlib.sha256(PDF).hexdigest()
    assert doc.byte_size == len(PDF)
    assert str(org) in doc.storage_ref and str(load) in doc.storage_ref
    assert P.read_document(doc.storage_ref, org_id=org) == PDF


def test_the_same_document_uploaded_twice_is_idempotent():
    """DUPLICATE POD. A retry from a driver's phone must not be a conflict."""
    org, load = uuid.uuid4(), uuid.uuid4()
    a = P.store_document(org_id=org, load_id=load, data=PDF,
                         mime_type="application/pdf")
    b = P.store_document(org_id=org, load_id=load, data=PDF,
                         mime_type="application/pdf")
    assert a.storage_ref == b.storage_ref
    assert a.sha256 == b.sha256


def test_an_empty_document_is_refused():
    with pytest.raises(P.PodRefused) as exc:
        P.store_document(org_id=uuid.uuid4(), load_id=uuid.uuid4(),
                         data=b"", mime_type="application/pdf")
    assert exc.value.code == "EMPTY_DOCUMENT"


def test_a_non_document_type_is_refused():
    """A POD is a scan or a photo. Accepting anything invites a .exe."""
    with pytest.raises(P.PodRefused) as exc:
        P.store_document(org_id=uuid.uuid4(), load_id=uuid.uuid4(),
                         data=PDF, mime_type="application/zip")
    assert exc.value.code == "UNSUPPORTED_DOCUMENT_TYPE"


# ===========================================================================
# Integrity over time
# ===========================================================================

def test_an_unaltered_document_verifies():
    org, load = uuid.uuid4(), uuid.uuid4()
    doc = P.store_document(org_id=org, load_id=load, data=PDF,
                           mime_type="application/pdf")
    r = P.verify_document(storage_ref=doc.storage_ref,
                          recorded_sha256=doc.sha256, org_id=org)
    assert r.intact is True and r.code == "INTACT"


def test_an_altered_document_is_detected():
    """ALTERED DOCUMENT.

    The bytes are changed on disk after binding. An invoice citing this POD is
    now citing a different file than the one that was approved, and the system
    has to be able to say so.
    """
    import pathlib
    org, load = uuid.uuid4(), uuid.uuid4()
    doc = P.store_document(org_id=org, load_id=load, data=PDF,
                           mime_type="application/pdf")

    pathlib.Path(doc.storage_ref).write_bytes(OTHER)

    r = P.verify_document(storage_ref=doc.storage_ref,
                          recorded_sha256=doc.sha256, org_id=org)
    assert r.intact is False
    assert r.code == "DOCUMENT_ALTERED"
    assert r.actual_sha256 != r.recorded_sha256
    assert "citing a different file" in r.detail


def test_a_missing_document_is_detected():
    """Retention deleted it, or a disk failed. Either way an invoice citing it
    can no longer be defended."""
    import pathlib
    org, load = uuid.uuid4(), uuid.uuid4()
    doc = P.store_document(org_id=org, load_id=load, data=PDF,
                           mime_type="application/pdf")
    pathlib.Path(doc.storage_ref).unlink()

    r = P.verify_document(storage_ref=doc.storage_ref,
                          recorded_sha256=doc.sha256, org_id=org)
    assert r.intact is False and r.code == "DOCUMENT_MISSING"


# ===========================================================================
# Tenancy
# ===========================================================================

def test_another_tenant_cannot_read_the_document():
    """CROSS-TENANT POD. A customer's signed BOL names their consignee, their
    addresses and what they shipped."""
    org_a, org_b, load = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    doc = P.store_document(org_id=org_a, load_id=load, data=PDF,
                           mime_type="application/pdf")

    assert P.read_document(doc.storage_ref, org_id=org_a) == PDF
    with pytest.raises(P.PodRefused) as exc:
        P.read_document(doc.storage_ref, org_id=org_b)
    assert exc.value.code == "DOCUMENT_OUTSIDE_TENANT"


def test_binding_to_another_tenants_load_is_refused():
    with pytest.raises(P.PodRefused) as exc:
        P.validate_binding(load_org_id=uuid.uuid4(), actor_org_id=uuid.uuid4(),
                           load_status="DELIVERED", existing_sha=None,
                           new_sha="a", evidence_strength="SIGNED_DOCUMENT")
    assert exc.value.code == "WRONG_TENANT"


# ===========================================================================
# Binding rules
# ===========================================================================

@pytest.mark.parametrize("status", ["DRAFT", "QUOTED", "BOOKED", "PLANNED",
                                    "CANCELLED"])
def test_a_pod_before_the_freight_moved_is_refused(status):
    """WRONG LOAD, in its most common form: the document is attached to a load
    that has not been delivered."""
    org = uuid.uuid4()
    with pytest.raises(P.PodRefused) as exc:
        P.validate_binding(load_org_id=org, actor_org_id=org,
                           load_status=status, existing_sha=None,
                           new_sha="a", evidence_strength="SIGNED_DOCUMENT")
    assert exc.value.code == "LOAD_NOT_DELIVERED"


@pytest.mark.parametrize("status", ["DELIVERED", "POD_RECEIVED", "IN_TRANSIT",
                                    "AT_DELIVERY", "EXCEPTION"])
def test_a_pod_on_a_moved_load_is_allowed(status):
    """Positive control. A rule that refused every status would pass the test
    above and make the feature unusable."""
    org = uuid.uuid4()
    P.validate_binding(load_org_id=org, actor_org_id=org, load_status=status,
                       existing_sha=None, new_sha="a",
                       evidence_strength="SIGNED_DOCUMENT")


def test_replacing_an_existing_pod_with_a_different_one_is_refused():
    """SUPERSEDED / STALE POD.

    Silently replacing it changes what an already-issued invoice cites. The
    refusal forces an explicit supersede, which keeps the original.
    """
    org = uuid.uuid4()
    with pytest.raises(P.PodRefused) as exc:
        P.validate_binding(load_org_id=org, actor_org_id=org,
                           load_status="DELIVERED", existing_sha="old",
                           new_sha="new", evidence_strength="SIGNED_DOCUMENT")
    assert exc.value.code == "POD_ALREADY_BOUND"


def test_rebinding_the_same_document_is_not_a_conflict():
    org = uuid.uuid4()
    P.validate_binding(load_org_id=org, actor_org_id=org,
                       load_status="DELIVERED", existing_sha="same",
                       new_sha="same", evidence_strength="SIGNED_DOCUMENT")


def test_an_unknown_evidence_strength_is_refused():
    org = uuid.uuid4()
    with pytest.raises(P.PodRefused) as exc:
        P.validate_binding(load_org_id=org, actor_org_id=org,
                           load_status="DELIVERED", existing_sha=None,
                           new_sha="a", evidence_strength="PROBABLY_FINE")
    assert exc.value.code == "UNKNOWN_EVIDENCE_STRENGTH"


def test_a_driver_asserted_document_is_storable_but_still_not_billable():
    """The two rules do not overlap, and both have to hold.

    A photo the driver took is a legitimate artifact to keep. It is still not
    a receiver's acknowledgement, and billing continues to refuse it.
    """
    from app.trucking import billing as B

    org = uuid.uuid4()
    P.validate_binding(load_org_id=org, actor_org_id=org,
                       load_status="DELIVERED", existing_sha=None,
                       new_sha="a", evidence_strength="ASSERTED_BY_DRIVER")

    assert "ASSERTED_BY_DRIVER" not in B.BILLABLE_POD_STRENGTH
    with pytest.raises(B.BillingRefused) as exc:
        B.build_invoice(
            load=type("L", (), {"customer_rate_cents": 100_000,
                                "status": "DELIVERED"})(),
            pod=type("P", (), {"evidence_strength": "ASSERTED_BY_DRIVER"})(),
            accessorials=[])
    assert exc.value.code == "POD_TOO_WEAK"


# ===========================================================================
# One signature, two loads
# ===========================================================================

def test_the_same_signed_document_on_a_second_load_is_flagged():
    """The attack the other five did not cover.

    Storage is per-load, so the identical signed document could be attached to
    a second load with nothing said. A POD is what RELEASES AN INVOICE, so that
    is one signature releasing two of them -- billing a customer twice on
    evidence that proves one delivery, and the document looks perfectly good in
    a dispute over either.
    """
    org, load_a, load_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    first = P.store_document(org_id=org, load_id=load_a, data=PDF,
                             mime_type="application/pdf")
    assert not first.reused_from_another_load

    second = P.store_document(org_id=org, load_id=load_b, data=PDF,
                              mime_type="application/pdf")
    assert second.reused_from_another_load, (
        "the same signed document was accepted on a second load with no "
        "signal; one signature would release two invoices")
    assert second.also_on_load_ids == (str(load_a),)


def test_it_is_flagged_and_not_refused():
    """A consolidated bill of lading covering more than one shipment is a real
    thing in freight. A rule that made it impossible would be wrong more often
    than the fraud it prevents, so the document is stored and the reuse is
    named for a human to agree to."""
    org, a, b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    P.store_document(org_id=org, load_id=a, data=PDF, mime_type="application/pdf")
    second = P.store_document(org_id=org, load_id=b, data=PDF,
                              mime_type="application/pdf")
    assert P.read_document(second.storage_ref, org_id=org) == PDF


def test_a_driver_retrying_on_the_same_load_is_not_flagged():
    """The false positive that would make the flag useless. A phone retrying
    an upload must stay idempotent and silent."""
    org, load = uuid.uuid4(), uuid.uuid4()
    P.store_document(org_id=org, load_id=load, data=PDF, mime_type="application/pdf")
    again = P.store_document(org_id=org, load_id=load, data=PDF,
                             mime_type="application/pdf")
    assert not again.reused_from_another_load


def test_a_different_document_on_another_load_is_not_flagged():
    org, a, b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    P.store_document(org_id=org, load_id=a, data=PDF, mime_type="application/pdf")
    other = P.store_document(org_id=org, load_id=b, data=OTHER,
                             mime_type="application/pdf")
    assert not other.reused_from_another_load


def test_the_check_does_not_look_into_another_tenant():
    """Two organisations legitimately hold identical bytes -- an empty scan, a
    template. Telling one that the other has the same file would leak the
    existence of the other's document."""
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    P.store_document(org_id=org_a, load_id=uuid.uuid4(), data=PDF,
                     mime_type="application/pdf")
    theirs = P.store_document(org_id=org_b, load_id=uuid.uuid4(), data=PDF,
                              mime_type="application/pdf")
    assert not theirs.reused_from_another_load


def test_control_the_detection_reads_the_name_the_writer_uses():
    """The bug this had on the first attempt: _doc_path names the file with
    sha[:32] and the scan compared the whole 64-character digest, so it matched
    nothing and never fired. A detector that silently cannot detect is worse
    than no detector, because the absence of a flag reads as a clean result.
    """
    org, load = uuid.uuid4(), uuid.uuid4()
    doc = P.store_document(org_id=org, load_id=load, data=PDF,
                           mime_type="application/pdf")
    stored = pathlib.Path(doc.storage_ref)
    assert stored.stem == doc.sha256[:32], (
        "the stored filename is no longer sha[:32]; "
        "_same_document_on_other_loads compares against that and will stop "
        "matching")
