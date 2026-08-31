"use client";
/**
 * Employer landing — role-aware home.
 *
 * The home is an ACTION FEED, not a dashboard of charts:
 *   - a manager lands on "Who needs my attention today" (ManagerHome)
 *   - an owner / admin / hr lands on the "People Ops Cockpit" (AdminHome)
 *
 * Role comes from the signed-in context. A `?as=manager|admin` override is
 * honored for demo/preview so either landing can be shown without re-auth.
 */
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { getUserContext, type AppRole } from "@/lib/auth";

import { ManagerHome } from "@/components/homes/ManagerHome";
import { AdminHome } from "@/components/homes/AdminHome";

export default function Home() {
  const params = useSearchParams();
  const override = params.get("as");
  const [role, setRole] = useState<AppRole | null>(null);

  useEffect(() => { getUserContext().then((c) => setRole(c.role)); }, []);

  if (!role) return null;

  const effective: "manager" | "admin" =
    override === "manager" ? "manager"
    : override === "admin" ? "admin"
    : role === "manager" ? "manager"
    : "admin";

  return effective === "manager" ? <ManagerHome /> : <AdminHome />;
}
