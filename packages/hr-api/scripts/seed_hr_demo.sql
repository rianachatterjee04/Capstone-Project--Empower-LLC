-- ============================================================================
-- HR demo seed — idempotent. Stands up a demo tenant the app can drive:
--   * 1 org (id matches the dev-auth default org, so `Bearer dev:` works)
--   * 10 employees (1 CEO + managers + ICs across departments)
--   * 1 open job posting + 1 candidate
--   * a performance review + comp record per employee
--
-- Fixed UUIDs + ON CONFLICT / NOT EXISTS make re-runs safe.
-- ============================================================================

-- Org (dev-auth default tenant)
INSERT INTO public.orgs (id, name)
VALUES ('11111111-1111-1111-1111-111111111111', 'Northwind Robotics')
ON CONFLICT (id) DO NOTHING;

-- Employees
INSERT INTO public.employees (id, org_id, employee_number, legal_name, preferred_name, email, status, job_title, department, location, manager_employee_id, start_date) VALUES
 ('a0000000-0000-0000-0000-000000000001','11111111-1111-1111-1111-111111111111','E001','Dana Whitfield','Dana','dana.ceo@northwind.test','active','Chief Executive Officer','Executive','Remote', NULL,'2021-01-04'),
 ('a0000000-0000-0000-0000-000000000002','11111111-1111-1111-1111-111111111111','E002','Marcus Lindqvist','Marcus','marcus.eng@northwind.test','active','VP Engineering','Engineering','San Francisco','a0000000-0000-0000-0000-000000000001','2021-03-15'),
 ('a0000000-0000-0000-0000-000000000003','11111111-1111-1111-1111-111111111111','E003','Priya Nandakumar','Priya','priya.eng@northwind.test','active','Staff Engineer','Engineering','San Francisco','a0000000-0000-0000-0000-000000000002','2021-06-01'),
 ('a0000000-0000-0000-0000-000000000004','11111111-1111-1111-1111-111111111111','E004','Tomas Alvarez','Tomas','tomas.eng@northwind.test','active','Senior Engineer','Engineering','Remote','a0000000-0000-0000-0000-000000000002','2022-02-14'),
 ('a0000000-0000-0000-0000-000000000005','11111111-1111-1111-1111-111111111111','E005','Grace Oduya','Grace','grace.sales@northwind.test','active','VP Sales','Sales','New York','a0000000-0000-0000-0000-000000000001','2021-05-10'),
 ('a0000000-0000-0000-0000-000000000006','11111111-1111-1111-1111-111111111111','E006','Ben Carter','Ben','ben.sales@northwind.test','active','Account Executive','Sales','New York','a0000000-0000-0000-0000-000000000005','2022-09-01'),
 ('a0000000-0000-0000-0000-000000000007','11111111-1111-1111-1111-111111111111','E007','Sofia Marin','Sofia','sofia.mktg@northwind.test','active','Head of Marketing','Marketing','Austin','a0000000-0000-0000-0000-000000000001','2021-11-08'),
 ('a0000000-0000-0000-0000-000000000008','11111111-1111-1111-1111-111111111111','E008','Kenji Watanabe','Kenji','kenji.ops@northwind.test','active','People Operations Lead','People','Remote','a0000000-0000-0000-0000-000000000001','2022-01-20'),
 ('a0000000-0000-0000-0000-000000000009','11111111-1111-1111-1111-111111111111','E009','Amara Bello','Amara','amara.fin@northwind.test','active','Finance Manager','Finance','New York','a0000000-0000-0000-0000-000000000001','2022-04-11'),
 ('a0000000-0000-0000-0000-000000000010','11111111-1111-1111-1111-111111111111','E010','Liam Novak','Liam','liam.eng@northwind.test','active','Software Engineer','Engineering','Remote','a0000000-0000-0000-0000-000000000002','2023-07-17')
ON CONFLICT (id) DO NOTHING;

-- Open requisition + a candidate
INSERT INTO public.job_postings (id, org_id, title, location, description, status)
VALUES ('b0000000-0000-0000-0000-000000000001','11111111-1111-1111-1111-111111111111',
        'Senior Backend Engineer','Remote (US)',
        'Own core services for the robotics fleet platform. Python/Postgres, distributed systems.','open')
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.candidates (id, org_id, job_posting_id, full_name, email, resume_text, status, ai_score, ai_summary)
VALUES ('c0000000-0000-0000-0000-000000000001','11111111-1111-1111-1111-111111111111',
        'b0000000-0000-0000-0000-000000000001','Riley Sanders','riley.sanders@example.com',
        '8 years backend engineering. Led Postgres-backed services at scale. Python, asyncio, distributed systems.',
        'applied', NULL, NULL)
ON CONFLICT (id) DO NOTHING;

-- Performance review + comp record per employee (deterministic; mirrors 20260630 seed)
INSERT INTO public.performance_reviews (org_id, employee_id, cycle, status, rating)
SELECT org_id, id, 'Q4 2026',
  (ARRAY['completed','in_progress','pending','completed','calibrated'])[1 + (abs(hashtext(id::text)) % 5)],
  3 + (abs(hashtext(id::text)) % 3)
FROM public.employees
ON CONFLICT (org_id, employee_id, cycle) DO NOTHING;

INSERT INTO public.comp_records (org_id, employee_id, base_salary, bonus_target, effective_date)
SELECT org_id, id,
  80000 + (abs(hashtext(id::text)) % 120000),
  (80000 + (abs(hashtext(id::text)) % 120000)) * 0.12,
  '2026-01-01'
FROM public.employees
ON CONFLICT (org_id, employee_id, effective_date) DO NOTHING;
