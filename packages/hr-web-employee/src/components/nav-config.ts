/**
 * Employee portal nav map. Calm, employee-first language. No HR jargon.
 *
 * Self-service is the whole point, so every "my" surface is one click away and
 * grouped the way an employee actually thinks: Me · Pay · Growth ·
 * Workflows · Benefits · Confidential.
 */
import type { AppRole } from "@/lib/auth";
import {
  IconHome,
  IconPeople,
  IconBenefits,
  IconCompliance,
  IconPerformance,
} from "./icons";

export type NavSection = {
  id: string;
  label: string;
  href: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  roles: AppRole[];
  children?: { label: string; href: string }[];
};

const ALL: AppRole[] = ["owner", "admin", "hr", "manager", "employee"];

export const NAV: NavSection[] = [
  {
    id: "home",
    label: "Today",
    href: "/app",
    icon: IconHome,
    roles: ALL,
    children: [
      { label: "Briefing", href: "/app" },
      { label: "My tasks", href: "/app/work" },
      { label: "My profile", href: "/app/twin" },
      { label: "Company directory", href: "/app/org" },
    ],
  },
  {
    id: "pay",
    label: "Pay & Equity",
    href: "/app/compensation",
    icon: IconBenefits,
    roles: ALL,
    children: [
      { label: "My total compensation", href: "/app/compensation" },
      { label: "My pay & payslips", href: "/app/payroll" },
      { label: "My benefits", href: "/app/benefits" },
    ],
  },
  {
    id: "growth",
    label: "Growth",
    href: "/app/performance",
    icon: IconPerformance,
    roles: ALL,
    children: [
      { label: "My reviews & goals", href: "/app/performance" },
      { label: "My 1:1s", href: "/app/one-on-ones" },
      { label: "Recognition", href: "/app/recognition" },
      { label: "Pulse", href: "/app/pulse" },
      { label: "Learning paths", href: "/app/learning" },
      { label: "Internal mobility", href: "/app/marketplace" },
    ],
  },
  {
    id: "workflows",
    label: "Workflows",
    href: "/app/onboarding",
    icon: IconPeople,
    roles: ALL,
    children: [
      { label: "Onboarding", href: "/app/onboarding" },
      { label: "Time off (PTO)", href: "/app/pto" },
      { label: "Documents", href: "/app/documents" },
      { label: "Assistant", href: "/app/assistant" },
    ],
  },
  {
    id: "confidential",
    label: "Confidential",
    href: "/app/ombudsman",
    icon: IconCompliance,
    roles: ALL,
    children: [
      { label: "Report a concern", href: "/app/ombudsman" },
      { label: "My reports", href: "/app/cases" },
    ],
  },
];
