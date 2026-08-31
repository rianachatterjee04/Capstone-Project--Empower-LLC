-- ==========================================================================
-- 20260829  TRUCKING / 3PL DOMAIN
-- ==========================================================================
-- The spine only. This is deliberately NOT a TMS: there is no rating engine,
-- no optimiser, no EDI, no load board. What it models is the path from an
-- operating event to an economic consequence, and the controls in between --
-- which is the part a TMS does not do and the part Fintra is for.
--
--   customer -> load -> qualification -> dispatch -> events -> POD
--            -> accessorials -> invoice -> carrier/driver settlement
--            -> margin
--
-- WHY IT LIVES IN hr-api
-- Because the demo's whole point is that the driver on the load is the person
-- HR interviewed, and driver eligibility is a compliance fact about an
-- employee. Putting loads in a separate service would mean the assignment
-- check had to call across a boundary to ask whether a licence had expired,
-- and that call is the control. It stays local until there is a reason for it
-- not to be.
--
-- THREE DISTINCTIONS THE SCHEMA REFUSES TO COLLAPSE
--
--   1. DELIVERED is not POD. A driver pressing "delivered" is an assertion by
--      an interested party. `proof_of_delivery` is a separate table with its
--      own evidence, and `loads.pod_id` is what billing reads.
--   2. An accessorial EVENT is not an accessorial CHARGE. Detention happened;
--      whether it is billable depends on the contract and, usually, on
--      somebody approving it.
--   3. Revenue is not margin, and neither is cash. The margin view subtracts
--      real cost rows and says which authority each came from.
-- ==========================================================================


-- ==========================================================================
-- PARTIES
-- ==========================================================================

CREATE TABLE IF NOT EXISTS public.trucking_customers (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  name                text NOT NULL,
  kind                text NOT NULL DEFAULT 'SHIPPER',  -- SHIPPER | CONSIGNEE | BOTH
  payment_terms_days  integer NOT NULL DEFAULT 30,
  credit_limit_cents  bigint,
  is_demo             boolean NOT NULL DEFAULT false,
  created_at          timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT trucking_customers_unique UNIQUE (org_id, name)
);
CREATE INDEX IF NOT EXISTS ix_trucking_customers_org
  ON public.trucking_customers(org_id);

-- A carrier we broker to. FMCSA data may be attached, and the columns are
-- named so that nobody mistakes a public register for a verified fact:
-- authority_source and authority_checked_at travel with the value.
CREATE TABLE IF NOT EXISTS public.trucking_carriers (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  name                text NOT NULL,
  dot_number          text,
  mc_number           text,

  authority_status    text NOT NULL DEFAULT 'UNKNOWN',
  -- ACTIVE | INACTIVE | REVOKED | UNKNOWN
  authority_source    text NOT NULL DEFAULT 'NOT_CONNECTED',
  -- FMCSA_LIVE | FMCSA_CACHED | MANUAL_ENTRY | NOT_CONNECTED
  authority_checked_at timestamptz,

  insurance_expires_on date,
  insurance_source    text NOT NULL DEFAULT 'NOT_CONNECTED',

  is_approved         boolean NOT NULL DEFAULT false,
  approved_by         text,
  approved_at         timestamptz,
  payment_terms_days  integer NOT NULL DEFAULT 30,

  is_demo             boolean NOT NULL DEFAULT false,
  created_at          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT trucking_carriers_unique UNIQUE (org_id, name),
  CONSTRAINT trucking_carriers_authority_ck CHECK (authority_status IN (
    'ACTIVE','INACTIVE','REVOKED','UNKNOWN')),
  CONSTRAINT trucking_carriers_source_ck CHECK (authority_source IN (
    'FMCSA_LIVE','FMCSA_CACHED','MANUAL_ENTRY','NOT_CONNECTED')),
  -- A status that claims to come from a source must say when it was checked.
  -- A stale "ACTIVE" is how a revoked carrier keeps getting loads.
  CONSTRAINT trucking_carriers_checked_ck
    CHECK (authority_source = 'NOT_CONNECTED' OR authority_checked_at IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS ix_trucking_carriers_org
  ON public.trucking_carriers(org_id);


-- ==========================================================================
-- DRIVERS AND EQUIPMENT
-- ==========================================================================
-- A driver IS an employee. employee_id is the link back to HR, and therefore
-- back to the interview that hired them.
CREATE TABLE IF NOT EXISTS public.trucking_drivers (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  employee_id         uuid REFERENCES public.employees(id) ON DELETE SET NULL,

  driver_code         text NOT NULL,
  status              text NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE | INACTIVE | ON_LEAVE | TERMINATED

  -- Worker classification is explicit and is NOT a UI convenience. Getting it
  -- wrong is a legal exposure, so it is stored, not inferred, and the
  -- settlement path reads it to decide payroll vs contractor settlement.
  worker_classification text NOT NULL DEFAULT 'W2_EMPLOYEE',
  -- W2_EMPLOYEE | CONTRACTOR_1099 | OWNER_OPERATOR
  classification_source text NOT NULL DEFAULT 'MANUAL_ENTRY',
  classification_note   text,

  pay_model           text NOT NULL DEFAULT 'HOURLY',
  -- HOURLY | SALARY | PER_MILE | PER_LOAD | PERCENTAGE
  pay_rate_cents      bigint,

  home_base           text,
  is_demo             boolean NOT NULL DEFAULT false,
  created_at          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT trucking_drivers_unique UNIQUE (org_id, driver_code),
  CONSTRAINT trucking_drivers_class_ck CHECK (worker_classification IN (
    'W2_EMPLOYEE','CONTRACTOR_1099','OWNER_OPERATOR')),
  CONSTRAINT trucking_drivers_pay_ck CHECK (pay_model IN (
    'HOURLY','SALARY','PER_MILE','PER_LOAD','PERCENTAGE'))
);
CREATE INDEX IF NOT EXISTS ix_trucking_drivers_org
  ON public.trucking_drivers(org_id);

-- Credentials with expiry. This table is the reason assignment can fail
-- closed: a licence, medical card or endorsement is a dated fact, and an
-- expired one is not a warning.
CREATE TABLE IF NOT EXISTS public.driver_credentials (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  driver_id           uuid NOT NULL REFERENCES public.trucking_drivers(id) ON DELETE CASCADE,

  credential_type     text NOT NULL,
  -- CDL_A | CDL_B | CDL_C | MEDICAL_CARD | HAZMAT | TANKER | DOUBLES_TRIPLES
  -- | TWIC | DRUG_TEST | MVR_CHECK
  identifier          text,
  issuing_authority   text,
  issued_on           date,
  expires_on          date,

  -- How we know. A self-reported credential is not a verified one, and the
  -- eligibility check treats them differently.
  verification_state  text NOT NULL DEFAULT 'SELF_REPORTED',
  -- SELF_REPORTED | DOCUMENT_ON_FILE | VERIFIED_EXTERNAL | EXTERNAL_VERIFICATION_REQUIRED
  verification_source text,
  verified_at         timestamptz,

  created_at          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT driver_credentials_unique UNIQUE (driver_id, credential_type),
  CONSTRAINT driver_credentials_verify_ck CHECK (verification_state IN (
    'SELF_REPORTED','DOCUMENT_ON_FILE','VERIFIED_EXTERNAL',
    'EXTERNAL_VERIFICATION_REQUIRED'))
);
CREATE INDEX IF NOT EXISTS ix_driver_credentials_org
  ON public.driver_credentials(org_id, driver_id);

CREATE TABLE IF NOT EXISTS public.trucking_equipment (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  unit_code           text NOT NULL,
  equipment_kind      text NOT NULL,   -- TRACTOR | DRY_VAN | REEFER | FLATBED | TANKER
  status              text NOT NULL DEFAULT 'AVAILABLE',
  -- AVAILABLE | ASSIGNED | MAINTENANCE | OUT_OF_SERVICE
  is_demo             boolean NOT NULL DEFAULT false,
  created_at          timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT trucking_equipment_unique UNIQUE (org_id, unit_code)
);
CREATE INDEX IF NOT EXISTS ix_trucking_equipment_org
  ON public.trucking_equipment(org_id);


-- ==========================================================================
-- LOADS
-- ==========================================================================

CREATE TABLE IF NOT EXISTS public.trucking_loads (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  customer_id         uuid NOT NULL REFERENCES public.trucking_customers(id) ON DELETE CASCADE,

  load_number         text NOT NULL,
  status              text NOT NULL DEFAULT 'DRAFT',
  -- DRAFT | QUOTED | BOOKED | PLANNED | DISPATCHED | AT_PICKUP | PICKED_UP
  -- | IN_TRANSIT | AT_DELIVERY | DELIVERED | POD_RECEIVED | EXCEPTION
  -- | CANCELLED | READY_TO_INVOICE | INVOICED | SETTLED

  -- How it is being covered. The same engine serves an asset carrier and a
  -- broker; the difference is which of these two is set.
  fulfilment_mode     text NOT NULL DEFAULT 'UNDECIDED',
  -- UNDECIDED | OWN_FLEET | BROKERED
  driver_id           uuid REFERENCES public.trucking_drivers(id) ON DELETE SET NULL,
  tractor_id          uuid REFERENCES public.trucking_equipment(id) ON DELETE SET NULL,
  trailer_id          uuid REFERENCES public.trucking_equipment(id) ON DELETE SET NULL,
  carrier_id          uuid REFERENCES public.trucking_carriers(id) ON DELETE SET NULL,

  origin_city         text NOT NULL,
  origin_state        text NOT NULL,
  destination_city    text NOT NULL,
  destination_state   text NOT NULL,
  pickup_window_start timestamptz,
  pickup_window_end   timestamptz,
  delivery_window_start timestamptz,
  delivery_window_end timestamptz,

  equipment_required  text NOT NULL DEFAULT 'DRY_VAN',
  temperature_min_f   integer,
  temperature_max_f   integer,
  hazmat              boolean NOT NULL DEFAULT false,
  commodity           text,
  weight_lbs          integer,
  miles               integer,

  -- Money in cents. The customer rate is a contract term, not a note.
  customer_rate_cents bigint NOT NULL DEFAULT 0,
  carrier_rate_cents  bigint,

  pod_id              uuid,          -- FK added after proof_of_delivery exists
  invoice_id          uuid,

  is_demo             boolean NOT NULL DEFAULT false,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT trucking_loads_unique UNIQUE (org_id, load_number),
  CONSTRAINT trucking_loads_mode_ck CHECK (fulfilment_mode IN (
    'UNDECIDED','OWN_FLEET','BROKERED')),
  -- A brokered load needs a carrier; an own-fleet load needs a driver. This is
  -- the schema refusing to hold a load that nobody is covering.
  CONSTRAINT trucking_loads_coverage_ck CHECK (
    fulfilment_mode <> 'BROKERED' OR carrier_id IS NOT NULL
      OR status IN ('DRAFT','QUOTED','BOOKED','PLANNED','CANCELLED')),
  CONSTRAINT trucking_loads_own_ck CHECK (
    fulfilment_mode <> 'OWN_FLEET' OR driver_id IS NOT NULL
      OR status IN ('DRAFT','QUOTED','BOOKED','PLANNED','CANCELLED'))
);
CREATE INDEX IF NOT EXISTS ix_trucking_loads_org
  ON public.trucking_loads(org_id, status);
CREATE INDEX IF NOT EXISTS ix_trucking_loads_driver
  ON public.trucking_loads(org_id, driver_id);

CREATE TABLE IF NOT EXISTS public.trucking_load_events (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  load_id             uuid NOT NULL REFERENCES public.trucking_loads(id) ON DELETE CASCADE,

  event_type          text NOT NULL,
  -- ARRIVED_PICKUP | LOADED | DEPARTED_PICKUP | IN_TRANSIT | DELAY
  -- | ARRIVED_DELIVERY | UNLOADED | DELIVERED | EXCEPTION | TEMPERATURE_ALARM

  occurred_at         timestamptz NOT NULL,
  -- WHO SAYS SO. A GPS ping and a driver tapping a button are different kinds
  -- of claim, and the accessorial engine weighs them differently.
  source              text NOT NULL,
  -- DRIVER_APP | TELEMATICS | CARRIER_REPORTED | CUSTOMER_REPORTED
  -- | DISPATCHER_ENTRY | DEMO_SIMULATED
  actor_ref           text,
  latitude            numeric(9,6),
  longitude           numeric(9,6),
  note                text,
  payload             jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT trucking_load_events_source_ck CHECK (source IN (
    'DRIVER_APP','TELEMATICS','CARRIER_REPORTED','CUSTOMER_REPORTED',
    'DISPATCHER_ENTRY','DEMO_SIMULATED'))
);
CREATE INDEX IF NOT EXISTS ix_trucking_load_events_org
  ON public.trucking_load_events(org_id, load_id, occurred_at);


-- ==========================================================================
-- PROOF OF DELIVERY
-- ==========================================================================
-- Separate from the DELIVERED event on purpose. A driver marking a load
-- delivered is an assertion by an interested party; a signed receipt from the
-- consignee is evidence. Billing reads THIS table.
CREATE TABLE IF NOT EXISTS public.proof_of_delivery (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  load_id             uuid NOT NULL REFERENCES public.trucking_loads(id) ON DELETE CASCADE,

  received_at         timestamptz NOT NULL,
  receiver_name       text,
  signature_kind      text NOT NULL DEFAULT 'NONE',
  -- NONE | TYPED_NAME | DRAWN_SIGNATURE | SCANNED_DOCUMENT | EDI_214
  document_ref        text,
  document_sha256     text,

  evidence_strength   text NOT NULL,
  -- ASSERTED_BY_DRIVER | RECEIVER_ACKNOWLEDGED | SIGNED_DOCUMENT | EDI_CONFIRMED
  exceptions_noted    text,
  is_demo             boolean NOT NULL DEFAULT false,
  created_at          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT proof_of_delivery_unique UNIQUE (load_id),
  CONSTRAINT proof_of_delivery_strength_ck CHECK (evidence_strength IN (
    'ASSERTED_BY_DRIVER','RECEIVER_ACKNOWLEDGED','SIGNED_DOCUMENT',
    'EDI_CONFIRMED'))
);

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                 WHERE conname = 'trucking_loads_pod_fk') THEN
    ALTER TABLE public.trucking_loads
      ADD CONSTRAINT trucking_loads_pod_fk FOREIGN KEY (pod_id)
      REFERENCES public.proof_of_delivery(id) ON DELETE SET NULL;
  END IF;
END $$;


-- ==========================================================================
-- ACCESSORIALS
-- ==========================================================================
-- The event and the charge are different rows. Detention happened; whether it
-- is billable depends on the contract and on somebody approving it. An
-- accessorial that becomes revenue without that chain is a manual total
-- wearing a category.
CREATE TABLE IF NOT EXISTS public.trucking_accessorials (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  load_id             uuid NOT NULL REFERENCES public.trucking_loads(id) ON DELETE CASCADE,

  accessorial_type    text NOT NULL,
  -- DETENTION | LAYOVER | TONU | LUMPER | STOP_OFF | REDELIVERY | STORAGE
  -- | FUEL_SURCHARGE | OTHER

  -- The operating fact.
  triggering_event_id uuid REFERENCES public.trucking_load_events(id) ON DELETE SET NULL,
  measured_quantity   numeric(12,3),
  measured_unit       text,            -- HOURS | DAYS | OCCURRENCES

  -- The contractual rule that turns the fact into money.
  rate_cents          bigint,
  free_allowance      numeric(12,3),
  billable_quantity   numeric(12,3),
  amount_cents        bigint NOT NULL DEFAULT 0,
  rate_rule_ref       text,

  state               text NOT NULL DEFAULT 'PROPOSED',
  -- PROPOSED | APPROVED | DISPUTED | REJECTED | BILLED
  approved_by         text,
  approved_at         timestamptz,
  dispute_note        text,

  -- Which side of the ledger. Detention is usually billed to the customer AND
  -- owed to the carrier, at different rates.
  direction           text NOT NULL DEFAULT 'CUSTOMER_BILLABLE',
  -- CUSTOMER_BILLABLE | CARRIER_PAYABLE

  created_at          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT trucking_accessorials_state_ck CHECK (state IN (
    'PROPOSED','APPROVED','DISPUTED','REJECTED','BILLED')),
  CONSTRAINT trucking_accessorials_direction_ck CHECK (direction IN (
    'CUSTOMER_BILLABLE','CARRIER_PAYABLE')),
  -- Nothing with money on it may be APPROVED without a named approver.
  CONSTRAINT trucking_accessorials_approval_ck CHECK (
    state <> 'APPROVED' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS ix_trucking_accessorials_org
  ON public.trucking_accessorials(org_id, load_id);


-- ==========================================================================
-- BILLING AND SETTLEMENT
-- ==========================================================================

CREATE TABLE IF NOT EXISTS public.trucking_invoices (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  customer_id         uuid NOT NULL REFERENCES public.trucking_customers(id) ON DELETE CASCADE,
  load_id             uuid NOT NULL REFERENCES public.trucking_loads(id) ON DELETE CASCADE,

  invoice_number      text NOT NULL,
  -- Derived, never typed. line_total is the contract rate plus APPROVED
  -- accessorials, and the derivation note records how it was reached.
  linehaul_cents      bigint NOT NULL DEFAULT 0,
  accessorial_cents   bigint NOT NULL DEFAULT 0,
  total_cents         bigint NOT NULL DEFAULT 0,
  derivation_note     text NOT NULL,

  issued_on           date NOT NULL DEFAULT current_date,
  due_on              date,
  state               text NOT NULL DEFAULT 'ISSUED',
  -- ISSUED | SENT | PARTIALLY_PAID | PAID | DISPUTED | VOID

  paid_cents          bigint NOT NULL DEFAULT 0,
  paid_at             timestamptz,

  is_demo             boolean NOT NULL DEFAULT false,
  created_at          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT trucking_invoices_unique UNIQUE (org_id, invoice_number),
  CONSTRAINT trucking_invoices_one_per_load UNIQUE (load_id),
  CONSTRAINT trucking_invoices_total_ck
    CHECK (total_cents = linehaul_cents + accessorial_cents)
);
CREATE INDEX IF NOT EXISTS ix_trucking_invoices_org
  ON public.trucking_invoices(org_id, state);

-- What we owe the carrier or the driver for this load. Separate from the
-- customer invoice, and separate BY WORKER CLASSIFICATION: a W-2 driver's pay
-- becomes a payroll input, a contractor's becomes a settlement. Mixing them
-- for UI convenience is a misclassification waiting to be found.
CREATE TABLE IF NOT EXISTS public.trucking_settlements (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  load_id             uuid NOT NULL REFERENCES public.trucking_loads(id) ON DELETE CASCADE,

  payee_kind          text NOT NULL,   -- CARRIER | DRIVER_CONTRACTOR | DRIVER_W2
  carrier_id          uuid REFERENCES public.trucking_carriers(id) ON DELETE SET NULL,
  driver_id           uuid REFERENCES public.trucking_drivers(id) ON DELETE SET NULL,

  linehaul_cents      bigint NOT NULL DEFAULT 0,
  accessorial_cents   bigint NOT NULL DEFAULT 0,
  deduction_cents     bigint NOT NULL DEFAULT 0,
  total_cents         bigint NOT NULL DEFAULT 0,
  derivation_note     text NOT NULL,

  state               text NOT NULL DEFAULT 'PROPOSED',
  -- PROPOSED | APPROVED | PAYROLL_INPUT | PAID | HELD | REJECTED
  approved_by         text,
  approved_at         timestamptz,
  hold_reason         text,

  -- Set when this becomes a payroll input rather than a direct payment.
  payroll_reference   text,

  created_at          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT trucking_settlements_unique UNIQUE (load_id, payee_kind),
  CONSTRAINT trucking_settlements_payee_ck CHECK (payee_kind IN (
    'CARRIER','DRIVER_CONTRACTOR','DRIVER_W2')),
  CONSTRAINT trucking_settlements_state_ck CHECK (state IN (
    'PROPOSED','APPROVED','PAYROLL_INPUT','PAID','HELD','REJECTED')),
  CONSTRAINT trucking_settlements_approval_ck CHECK (
    state NOT IN ('APPROVED','PAID')
    OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)),
  -- A W-2 driver's pay may never be PAID from here. It goes to payroll.
  CONSTRAINT trucking_settlements_w2_ck CHECK (
    payee_kind <> 'DRIVER_W2' OR state <> 'PAID')
);
CREATE INDEX IF NOT EXISTS ix_trucking_settlements_org
  ON public.trucking_settlements(org_id, state);

-- Direct operating costs, with the authority each figure carries. A modelled
-- fuel allocation and a fuel receipt are both useful and are not the same
-- fact, so margin reports both and never silently averages them.
CREATE TABLE IF NOT EXISTS public.trucking_load_costs (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  load_id             uuid NOT NULL REFERENCES public.trucking_loads(id) ON DELETE CASCADE,

  cost_type           text NOT NULL,
  -- FUEL | TOLLS | MAINTENANCE | DRIVER_LABOR | CARRIER_PAY | LUMPER
  -- | INSURANCE_ALLOCATION | OTHER
  amount_cents        bigint NOT NULL DEFAULT 0,

  authority           text NOT NULL DEFAULT 'MODELED',
  -- MODELED | PLATFORM_REPORTED | CORROBORATED | FINANCIAL_ACTUAL
  source_ref          text,
  note                text,
  created_at          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT trucking_load_costs_authority_ck CHECK (authority IN (
    'MODELED','PLATFORM_REPORTED','CORROBORATED','FINANCIAL_ACTUAL'))
);
CREATE INDEX IF NOT EXISTS ix_trucking_load_costs_org
  ON public.trucking_load_costs(org_id, load_id);
