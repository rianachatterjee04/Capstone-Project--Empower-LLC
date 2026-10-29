-- ==========================================================================
-- 20261029  EMPLOYEE SKILLS + ROLE SKILL REQUIREMENTS  (Sprint 10, #220 #228)
-- ==========================================================================
-- Two small tables.
--
--   employee_skills          what each person can do, and how well (1 to 4)
--   role_skill_requirements  what each role needs, and how well (1 to 4)
--
-- The skill gap analysis compares one against the other, so both use the same
-- 1 to 4 scale:  1 beginner, 2 working, 3 advanced, 4 expert.
--
-- The older ai_skills table only covers the eight AI skills, so it is left
-- alone. These tables hold any skill an organisation cares about.
--
-- Skill and role names are stored lower case with single spaces. The service
-- does that before every write, so "Python" and "python " are one skill.
-- ==========================================================================

CREATE TABLE IF NOT EXISTS public.employee_skills (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id       uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  employee_id  uuid NOT NULL REFERENCES public.employees(id) ON DELETE CASCADE,
  skill        text NOT NULL,
  level        integer NOT NULL,
  -- who set it: the employee ("self") or someone in HR or management ("hr")
  source       text NOT NULL DEFAULT 'self',
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT employee_skills_level_range CHECK (level BETWEEN 1 AND 4),
  CONSTRAINT employee_skills_unique UNIQUE (org_id, employee_id, skill)
);
CREATE INDEX IF NOT EXISTS ix_employee_skills_org_employee
  ON public.employee_skills(org_id, employee_id);
CREATE INDEX IF NOT EXISTS ix_employee_skills_org_skill
  ON public.employee_skills(org_id, skill);

CREATE TABLE IF NOT EXISTS public.role_skill_requirements (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  role            text NOT NULL,
  skill           text NOT NULL,
  required_level  integer NOT NULL DEFAULT 2,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT role_skill_requirements_level_range CHECK (required_level BETWEEN 1 AND 4),
  CONSTRAINT role_skill_requirements_unique UNIQUE (org_id, role, skill)
);
CREATE INDEX IF NOT EXISTS ix_role_skill_requirements_org_role
  ON public.role_skill_requirements(org_id, role);
