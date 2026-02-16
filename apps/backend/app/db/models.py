from __future__ import annotations
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, Boolean, Integer, Date, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid

class Base(DeclarativeBase):
    pass

class Org(Base):
    __tablename__ = "orgs"
    __table_args__ = {"schema": "public"}
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (UniqueConstraint("org_id","email", name="employees_org_email_unique"), {"schema":"public"})
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("public.orgs.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    employee_number: Mapped[str | None] = mapped_column(String, nullable=True)
    legal_name: Mapped[str] = mapped_column(String, nullable=False)
    preferred_name: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="invited")
    job_title: Mapped[str | None] = mapped_column(String, nullable=True)
    department: Mapped[str | None] = mapped_column(String, nullable=True)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    manager_employee_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("public.employees.id", ondelete="SET NULL"), nullable=True)
    start_date: Mapped = mapped_column(Date, nullable=True)
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class OnboardingPacket(Base):
    __tablename__ = "onboarding_packets"
    __table_args__ = {"schema":"public"}
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("public.orgs.id", ondelete="CASCADE"), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("public.employees.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    requested_items: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    submitted_items: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class Case(Base):
    __tablename__ = "cases"
    __table_args__ = {"schema":"public"}
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("public.orgs.id", ondelete="CASCADE"), nullable=False)
    reporter_employee_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("public.employees.id", ondelete="SET NULL"), nullable=True)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    category: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False, default="medium")
    details: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    escalation_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class JobPosting(Base):
    __tablename__ = "job_postings"
    __table_args__ = {"schema":"public"}
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("public.orgs.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class Candidate(Base):
    __tablename__ = "candidates"
    __table_args__ = (UniqueConstraint("org_id","job_posting_id","email", name="candidates_unique"), {"schema":"public"})
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("public.orgs.id", ondelete="CASCADE"), nullable=False)
    job_posting_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("public.job_postings.id", ondelete="CASCADE"), nullable=False)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    resume_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="new")
    ai_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = {"schema":"public"}
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("public.orgs.id", ondelete="CASCADE"), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String, nullable=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String, nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class OrgUnit(Base):
    __tablename__ = "org_units"
    __table_args__ = ({"schema":"public"})
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("public.orgs.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    parent_unit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("public.org_units.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class EmployeeOrgUnit(Base):
    __tablename__ = "employee_org_units"
    __table_args__ = (UniqueConstraint("org_id","employee_id","org_unit_id", name="employee_org_units_unique"), {"schema":"public"})
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("public.orgs.id", ondelete="CASCADE"), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("public.employees.id", ondelete="CASCADE"), nullable=False)
    org_unit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("public.org_units.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, default="member")
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class SalaryBand(Base):
    __tablename__ = "salary_bands"
    __table_args__ = (UniqueConstraint("org_id","job_family","level","currency", name="salary_bands_unique"), {"schema":"public"})
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("public.orgs.id", ondelete="CASCADE"), nullable=False)
    job_family: Mapped[str] = mapped_column(String, nullable=False)
    level: Mapped[str] = mapped_column(String, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False, default="USD")
    min_base: Mapped[float] = mapped_column(nullable=False)
    mid_base: Mapped[float] = mapped_column(nullable=False)
    max_base: Mapped[float] = mapped_column(nullable=False)
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class CompensationEvent(Base):
    __tablename__ = "compensation_events"
    __table_args__ = {"schema":"public"}
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("public.orgs.id", ondelete="CASCADE"), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("public.employees.id", ondelete="CASCADE"), nullable=False)
    effective_date: Mapped = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False, default="USD")
    base_salary: Mapped[float] = mapped_column(nullable=False)
    target_bonus_pct: Mapped[float | None] = mapped_column(nullable=True)
    equity_grant_value: Mapped[float | None] = mapped_column(nullable=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class Policy(Base):
    __tablename__ = "policies"
    __table_args__ = {"schema":"public"}
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("public.orgs.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    dsl: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class EscalationRule(Base):
    __tablename__ = "escalation_rules"
    __table_args__ = {"schema":"public"}
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("public.orgs.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    condition_dsl: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    sla_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    route: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    severity_floor: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class Escalation(Base):
    __tablename__ = "escalations"
    __table_args__ = (UniqueConstraint("org_id","entity_type","entity_id","rule_id", name="escalations_unique"), {"schema":"public"})
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("public.orgs.id", ondelete="CASCADE"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("public.escalation_rules.id", ondelete="CASCADE"), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    due_at: Mapped = mapped_column(DateTime(timezone=True), nullable=False)
    last_notified_at: Mapped = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
