-- Columns expected by /api/verification/* (doc_verification router)
alter table public.documents add column if not exists rejection_reason text null;
alter table public.documents add column if not exists verified_at timestamptz null;
alter table public.documents add column if not exists reviewer_employee_id uuid null
  references public.employees(id) on delete set null;
