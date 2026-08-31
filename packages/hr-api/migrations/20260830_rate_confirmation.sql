-- The rate confirmation: what the broker and the carrier actually agreed.
--
-- WHY THIS TABLE EXISTS
-- `trucking_loads.carrier_rate_cents` is a number in a field. A carrier
-- disputing a settlement is not shown a field; they are shown the rate
-- confirmation they accepted, with its accessorial terms and the time they
-- accepted it. Without that document the brokered flow has a hole in exactly
-- the place money changes hands, and every carrier payable in the system is
-- an assertion by the party who owes it.
--
-- WHAT IT ESTABLISHES
--   the agreed linehaul and fuel surcharge, as separate figures
--   which accessorials were PRE-APPROVED, and at what rate
--   who accepted it, and when
--   the sha256 of the document that was sent, so a later edit is detectable
--
-- WHAT IT DOES NOT ESTABLISH
-- That the carrier is who they say they are, or that their authority is
-- current. Those are `trucking_carriers` and `fmcsa_authority`, and
-- `eligibility.check_carrier` remains the gate. A signed rate confirmation
-- from a revoked carrier is a signed document from a carrier who may not haul.

BEGIN;

CREATE TABLE IF NOT EXISTS public.trucking_rate_confirmations (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
    load_id             uuid NOT NULL REFERENCES public.trucking_loads(id) ON DELETE CASCADE,
    carrier_id          uuid NOT NULL REFERENCES public.trucking_carriers(id),

    confirmation_number text NOT NULL,

    -- The agreed money, kept apart. A fuel surcharge folded into linehaul
    -- cannot be re-derived when fuel moves, and a carrier arguing about FSC is
    -- arguing about a figure that no longer exists.
    linehaul_cents      bigint NOT NULL DEFAULT 0,
    fuel_surcharge_cents bigint NOT NULL DEFAULT 0,
    agreed_total_cents  bigint NOT NULL DEFAULT 0,

    -- Which accessorials the broker committed to in advance, and at what rate.
    -- An accessorial NOT listed here is not pre-approved, and billing already
    -- refuses to pay an unapproved charge.
    -- Shape: [{"kind":"DETENTION","rate_cents":5000,"unit":"HOUR",
    --          "free_time_minutes":120,"cap_cents":30000}, ...]
    approved_accessorials jsonb NOT NULL DEFAULT '[]'::jsonb,

    state               text NOT NULL DEFAULT 'DRAFT',
    issued_at           timestamptz,
    accepted_at         timestamptz,
    accepted_by         text,
    accepted_channel    text,

    -- The document as sent. Re-reading and comparing is what makes a later
    -- edit detectable, exactly as with a POD.
    document_ref        text,
    document_sha256     text,

    -- An amendment never overwrites: it points back at what it replaces, so
    -- the settlement that cited the original can still be defended.
    supersedes_id       uuid REFERENCES public.trucking_rate_confirmations(id),
    superseded_at       timestamptz,
    amendment_reason    text,

    is_demo             boolean NOT NULL DEFAULT false,
    created_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT trucking_ratecon_state_ck CHECK (
        state IN ('DRAFT','ISSUED','ACCEPTED','DECLINED','SUPERSEDED','VOID')),

    -- The total is the sum of its parts. A rate confirmation whose total does
    -- not equal linehaul + FSC is a document that says two different things.
    CONSTRAINT trucking_ratecon_total_ck CHECK (
        agreed_total_cents = linehaul_cents + fuel_surcharge_cents),

    -- ACCEPTED is the state that authorises a payable, so it must carry the
    -- evidence that it was accepted. A row that claims acceptance with no time
    -- and no counterparty is the field it was meant to replace.
    CONSTRAINT trucking_ratecon_accepted_ck CHECK (
        state <> 'ACCEPTED'
        OR (accepted_at IS NOT NULL AND accepted_by IS NOT NULL)),

    -- ISSUED means it left the building, so it has a time and a document.
    CONSTRAINT trucking_ratecon_issued_ck CHECK (
        state NOT IN ('ISSUED','ACCEPTED')
        OR (issued_at IS NOT NULL AND document_sha256 IS NOT NULL)),

    -- An amendment names what it replaces and why. Silently replacing terms
    -- changes what an existing settlement cites.
    CONSTRAINT trucking_ratecon_amendment_ck CHECK (
        supersedes_id IS NULL OR amendment_reason IS NOT NULL),

    -- Nothing negative. A rate confirmation is not a credit memo.
    CONSTRAINT trucking_ratecon_nonneg_ck CHECK (
        linehaul_cents >= 0 AND fuel_surcharge_cents >= 0
        AND agreed_total_cents >= 0)
);

-- One LIVE confirmation per load. Superseded and declined rows stay, which is
-- the point of superseding rather than updating.
CREATE UNIQUE INDEX IF NOT EXISTS uq_ratecon_live_per_load
    ON public.trucking_rate_confirmations (org_id, load_id)
    WHERE state IN ('DRAFT','ISSUED','ACCEPTED');

CREATE UNIQUE INDEX IF NOT EXISTS uq_ratecon_number
    ON public.trucking_rate_confirmations (org_id, confirmation_number);

CREATE INDEX IF NOT EXISTS ix_ratecon_carrier
    ON public.trucking_rate_confirmations (org_id, carrier_id, state);

-- The load points at the confirmation currently governing it, so a settlement
-- can be traced without searching.
ALTER TABLE public.trucking_loads
    ADD COLUMN IF NOT EXISTS rate_confirmation_id uuid
        REFERENCES public.trucking_rate_confirmations(id);

-- The settlement records WHICH confirmation authorised it. A carrier payable
-- with no rate confirmation behind it is traceable as such rather than
-- indistinguishable from one that has one.
ALTER TABLE public.trucking_settlements
    ADD COLUMN IF NOT EXISTS rate_confirmation_id uuid
        REFERENCES public.trucking_rate_confirmations(id);

COMMIT;
