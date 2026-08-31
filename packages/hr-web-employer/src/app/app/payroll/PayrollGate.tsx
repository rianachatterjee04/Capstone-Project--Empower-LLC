"use client";
/**
 * Shared fail-soft empty states for the payroll workspace: service down,
 * license locked (402 surfaced as "Payroll module not activated"), or a
 * plain error. Renders nothing when the result is healthy.
 */
import { EmptyState, Surface } from "@/components/ds";
import type { PayrollResult } from "@/lib/payroll";

export function PayrollGate({ result }: { result: PayrollResult<unknown> | null }) {
  if (!result || result.data) return null;
  if (result.unreachable) {
    return (
      <Surface>
        <EmptyState
          title="Payroll service unreachable"
          description="The payroll service (port 8050) is not responding. Start it with npm run dev:payroll, or try again in a moment — nothing here is lost."
        />
      </Surface>
    );
  }
  if (result.licenseLocked) {
    return (
      <Surface>
        <EmptyState
          title="Payroll module not activated"
          description="Payroll is a licensed add-on and is not activated for this organization yet. An owner can activate it with the payroll license password (POST /api/payroll/license/activate), or contact Fintra to purchase the module."
        />
      </Surface>
    );
  }
  return (
    <Surface>
      <EmptyState title="Payroll data unavailable" description={result.error} />
    </Surface>
  );
}
