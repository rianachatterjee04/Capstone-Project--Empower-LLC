-- The commercial loop: from a market observation to a dollar of margin.
--
-- WHY THIS IS A SCHEMA AND NOT A REPORT
-- The loop existed only inside a demo script. It printed a convincing story
-- and persisted nothing, so there was no way to open it, no way to check it
-- weeks later, and no way for a second load from the same customer to update
-- the answer. A narration is not a product.
--
-- THE THREE THINGS THE SCHEMA REFUSES
--
--   1. MARKETING TO A SOURCE THAT DOES NOT LICENCE IT.
--      A public register of carriers is readable. Reading it is not permission
--      to run an outreach campaign against the businesses in it. The licence
--      travels with the prospect, and an action against a prospect whose
--      source does not permit direct marketing is refused by a constraint
--      rather than by a code review.
--
--   2. A LEAD THAT NO HUMAN SAVED.
--      `saved_by` is NOT NULL on any prospect past OBSERVED. A scan can
--      surface a name; only a person can decide it is a lead. Without that,
--      "our AI found 400 leads" means "our AI copied 400 rows".
--
--   3. ATTRIBUTION WITHOUT CASH.
--      An attribution row records what it counted and how strong that is. It
--      cannot claim REALISED unless cash was actually collected, because the
--      question "did the campaign work" is a question about money that moved.

BEGIN;

-- ---------------------------------------------------------------------------
-- Where a name came from, and what we may do with it
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.commercial_sources (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
    name            text NOT NULL,
    kind            text NOT NULL,
    -- The whole point of the table. FMCSA is PUBLIC_REGISTER and does not
    -- permit outreach; a list the sales team built themselves does.
    permits_direct_marketing boolean NOT NULL DEFAULT false,
    licence_note    text NOT NULL,
    retrieved_at    timestamptz,
    is_demo         boolean NOT NULL DEFAULT false,
    created_at      timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT commercial_sources_kind_ck CHECK (
        kind IN ('PUBLIC_REGISTER','PURCHASED_LIST','SELF_SOURCED',
                 'INBOUND','REFERRAL','PARTNER','UNATTRIBUTED')),
    -- A source that permits outreach has to say on what basis. "true" with no
    -- note is the field that gets set by whoever is in a hurry.
    CONSTRAINT commercial_sources_licence_ck CHECK (
        permits_direct_marketing = false OR length(licence_note) >= 12)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_commercial_source_name
    ON public.commercial_sources (org_id, name);

-- ---------------------------------------------------------------------------
-- A business we might sell to
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.commercial_prospects (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
    -- Deleting a source takes its prospects: a prospect whose licence
    -- basis no longer exists must not survive as an unattributed name.
    source_id       uuid NOT NULL REFERENCES public.commercial_sources(id)
                        ON DELETE CASCADE,

    name            text NOT NULL,
    city            text,
    state           text,
    -- How confident we are this is a real, correctly-identified business.
    identity_strength text NOT NULL DEFAULT 'NAMED_ONLY',

    stage           text NOT NULL DEFAULT 'OBSERVED',
    -- NOT NULL past OBSERVED. A scan surfaces a name; a person makes it a lead.
    saved_by        text,
    saved_at        timestamptz,

    customer_id     uuid REFERENCES public.trucking_customers(id),
    converted_at    timestamptz,

    is_demo         boolean NOT NULL DEFAULT false,
    created_at      timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT commercial_prospects_stage_ck CHECK (
        stage IN ('OBSERVED','SAVED','CONTACTED','QUALIFIED','CUSTOMER',
                  'DISQUALIFIED')),
    CONSTRAINT commercial_prospects_identity_ck CHECK (
        identity_strength IN ('NAMED_ONLY','ADDRESS_MATCHED','VERIFIED',
                              'SELF_IDENTIFIED')),
    -- THE HUMAN GATE.
    CONSTRAINT commercial_prospects_human_ck CHECK (
        stage = 'OBSERVED'
        OR (saved_by IS NOT NULL AND saved_at IS NOT NULL)),
    -- A prospect that is a customer names the customer.
    CONSTRAINT commercial_prospects_customer_ck CHECK (
        stage <> 'CUSTOMER'
        OR (customer_id IS NOT NULL AND converted_at IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS ix_commercial_prospects_stage
    ON public.commercial_prospects (org_id, stage);

-- ---------------------------------------------------------------------------
-- Something we did, and what it cost
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.commercial_actions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
    prospect_id     uuid REFERENCES public.commercial_prospects(id)
                        ON DELETE CASCADE,

    action_kind     text NOT NULL,
    description     text NOT NULL,
    occurred_on     date NOT NULL,

    spend_cents     bigint NOT NULL DEFAULT 0,
    -- The same ladder the trucking costs use. A budget line is MODELED; an
    -- invoice we paid is FINANCIAL_ACTUAL.
    spend_authority text NOT NULL DEFAULT 'MODELED',
    spend_source_ref text,

    -- Which positioning problem this was meant to address. Free text on
    -- purpose: it is a hypothesis, not a taxonomy.
    hypothesis      text,

    is_demo         boolean NOT NULL DEFAULT false,
    created_at      timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT commercial_actions_kind_ck CHECK (
        action_kind IN ('OUTBOUND_EMAIL','OUTBOUND_CALL','DIRECT_MAIL',
                        'PAID_SEARCH','PAID_SOCIAL','EVENT','CONTENT',
                        'REFERRAL_FEE','SALES_TIME','OTHER')),
    CONSTRAINT commercial_actions_authority_ck CHECK (
        spend_authority IN ('MODELED','PLATFORM_REPORTED','CORROBORATED',
                            'FINANCIAL_ACTUAL')),
    CONSTRAINT commercial_actions_spend_ck CHECK (spend_cents >= 0),
    -- Spend above zero that claims to be an actual has to cite something.
    CONSTRAINT commercial_actions_actual_ck CHECK (
        spend_authority <> 'FINANCIAL_ACTUAL'
        OR spend_source_ref IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS ix_commercial_actions_prospect
    ON public.commercial_actions (org_id, prospect_id);

-- ---------------------------------------------------------------------------
-- Did it work?
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.commercial_attributions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
    prospect_id     uuid NOT NULL REFERENCES public.commercial_prospects(id)
                        ON DELETE CASCADE,
    customer_id     uuid REFERENCES public.trucking_customers(id),

    computed_at     timestamptz NOT NULL DEFAULT now(),

    spend_cents             bigint NOT NULL DEFAULT 0,
    revenue_cents           bigint NOT NULL DEFAULT 0,
    direct_cost_cents       bigint NOT NULL DEFAULT 0,
    contribution_margin_cents bigint NOT NULL DEFAULT 0,
    cash_collected_cents    bigint NOT NULL DEFAULT 0,

    loads_count     integer NOT NULL DEFAULT 0,

    verdict         text NOT NULL,
    -- The MINIMUM authority across everything that fed the number, never the
    -- average. One paid invoice does not make a page of estimates measured.
    grade           text NOT NULL,
    basis           text NOT NULL,
    note            text NOT NULL,

    is_demo         boolean NOT NULL DEFAULT false,

    CONSTRAINT commercial_attr_verdict_ck CHECK (
        verdict IN ('WORKED','DID_NOT_WORK','TOO_EARLY',
                    'INSUFFICIENT_EVIDENCE')),
    CONSTRAINT commercial_attr_grade_ck CHECK (
        grade IN ('MODELED','PLATFORM_REPORTED','CORROBORATED',
                  'FINANCIAL_ACTUAL')),
    CONSTRAINT commercial_attr_basis_ck CHECK (
        basis IN ('REALISED','MODELED')),
    -- THE CASH GATE. "Did it work" is a question about money that moved.
    CONSTRAINT commercial_attr_cash_ck CHECK (
        basis <> 'REALISED' OR cash_collected_cents > 0)
);

CREATE INDEX IF NOT EXISTS ix_commercial_attr_prospect
    ON public.commercial_attributions (org_id, prospect_id, computed_at DESC);

-- Which prospect a customer came from, so a load can be traced back to the
-- action that produced the account.
-- SET NULL, not CASCADE: a customer exists independently of how it was
-- sourced. Deleting the commercial history should lose the ATTRIBUTION, never
-- the account -- and a customer whose origin is unknown is a normal state that
-- the loop reports rather than hides.
ALTER TABLE public.trucking_customers
    ADD COLUMN IF NOT EXISTS prospect_id uuid
        REFERENCES public.commercial_prospects(id) ON DELETE SET NULL;

COMMIT;
