"use client";

/**
 * Legacy route. The public profile / culture card is now the "Overview" (and
 * "Total comp") tab of the single unified person page at /app/people/[id].
 * Redirect there, preserving the employee id.
 */
import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

export default function ProfileRedirect() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params?.id ?? "";

  useEffect(() => {
    router.replace(id ? `/app/people/${id}` : "/app/people");
  }, [id, router]);

  return <div className="p-8 text-sm text-muted">Opening the unified profile…</div>;
}
