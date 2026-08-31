"use client";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

type Employee = {
  id: string;
  legal_name: string;
  job_title: string;
  department: string;
  status: string;
  email: string;
};

const SALARY_BY_TITLE: Record<string, number> = {
  "Software Engineer": 115000,
  "Senior Software Engineer": 145000,
  "Product Manager": 125000,
  "HR Specialist": 78000,
  "UX Designer": 95000,
  "Sales Lead": 105000,
  "Sales Representative": 72000,
  "Finance Analyst": 88000,
  "Marketing Manager": 98000,
  "Operations Manager": 92000,
};

const DEFAULT_SALARY = 80000;

function getSalary(title: string) {
  return SALARY_BY_TITLE[title] ?? DEFAULT_SALARY;
}

function fmt(n: number) {
  return n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
}

function PayStubRow({ label, amount, muted = false, bold = false }: { label: string; amount: number; muted?: boolean; bold?: boolean }) {
  return (
    <div className={`flex justify-between py-2 border-b border-black/5 last:border-0 ${muted ? "text-black/40" : ""} ${bold ? "font-semibold" : "text-sm"}`}>
      <span>{label}</span>
      <span className={amount < 0 ? "text-red-600" : ""}>{amount < 0 ? `-${fmt(Math.abs(amount))}` : fmt(amount)}</span>
    </div>
  );
}

export default function PayrollPage() {
  const { data: employees = [], isLoading, isError } = useQuery({
    queryKey: ["employees"],
    queryFn: () => apiFetch<Employee[]>("/employees"),
  });

  const me = employees[0]; // In real auth, filter by current user_id
  const salary = me ? getSalary(me.job_title) : DEFAULT_SALARY;
  const biweeklyGross = salary / 26;

  // Deductions
  const federalTax = biweeklyGross * 0.22;
  const stateTax = biweeklyGross * 0.093;
  const socialSecurity = biweeklyGross * 0.062;
  const medicare = biweeklyGross * 0.0145;
  const healthInsurance = 250 / 2; // $250/mo employee share
  const retirement401k = biweeklyGross * 0.05;
  const totalDeductions = federalTax + stateTax + socialSecurity + medicare + healthInsurance + retirement401k;
  const netPay = biweeklyGross - totalDeductions;

  const ytdGross = biweeklyGross * 8; // 8 pay periods so far this year
  const ytdNet = netPay * 8;

  const payPeriods = [
    { label: "Apr 1 – Apr 14, 2026", net: netPay, status: "paid" },
    { label: "Mar 16 – Mar 31, 2026", net: netPay, status: "paid" },
    { label: "Mar 1 – Mar 15, 2026", net: netPay, status: "paid" },
    { label: "Feb 16 – Feb 28, 2026", net: netPay, status: "paid" },
  ];

  if (isLoading) return <div className="p-8 text-sm text-black/40">Loading payroll…</div>;
  if (isError || !me) return <div className="p-8 text-sm text-red-500">Failed to load payroll data.</div>;

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Payroll</div>
        <div className="mt-1 text-sm text-black/60">Pay stubs and earnings summary</div>
      </div>

      {/* YTD Summary */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "YTD Gross", value: fmt(ytdGross) },
          { label: "YTD Deductions", value: fmt(ytdGross - ytdNet) },
          { label: "YTD Net Pay", value: fmt(ytdNet) },
        ].map((s) => (
          <div key={s.label} className="rounded-2xl border border-black/10 bg-white p-5 shadow-sm">
            <div className="text-xs text-black/50 mb-1">{s.label}</div>
            <div className="text-xl font-semibold">{s.value}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Current Pay Stub */}
        <div className="rounded-2xl border border-black/10 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="text-sm font-semibold">Current Pay Period</div>
              <div className="text-xs text-black/50">Apr 15 – Apr 28, 2026 · Biweekly</div>
            </div>
            <span className="rounded-full bg-amber-50 border border-amber-200 text-amber-700 text-xs px-2.5 py-0.5 font-medium">Upcoming</span>
          </div>

          <div className="mb-3">
            <div className="text-xs font-medium text-black/40 uppercase tracking-wide mb-2">Earnings</div>
            <PayStubRow label="Regular pay" amount={biweeklyGross} />
          </div>

          <div className="mb-3">
            <div className="text-xs font-medium text-black/40 uppercase tracking-wide mb-2">Deductions</div>
            <PayStubRow label="Federal income tax" amount={-federalTax} />
            <PayStubRow label="CA state income tax" amount={-stateTax} />
            <PayStubRow label="Social Security" amount={-socialSecurity} />
            <PayStubRow label="Medicare" amount={-medicare} />
            <PayStubRow label="Health insurance" amount={-healthInsurance} />
            <PayStubRow label="401(k) contribution (5%)" amount={-retirement401k} />
          </div>

          <div className="border-t border-black/10 pt-3 mt-2">
            <div className="flex justify-between font-semibold">
              <span>Net pay</span>
              <span className="text-emerald-700">{fmt(netPay)}</span>
            </div>
          </div>

          <div className="mt-4 rounded-xl bg-black/5 px-4 py-3 text-xs text-black/50">
            <div className="font-medium text-black/70 mb-1">{me.legal_name}</div>
            <div>{me.job_title} · {me.department}</div>
            <div>Annual salary: {fmt(salary)}</div>
          </div>
        </div>

        {/* Pay History */}
        <div className="rounded-2xl border border-black/10 bg-white shadow-sm">
          <div className="border-b border-black/10 px-5 py-4">
            <div className="text-sm font-semibold">Pay history</div>
            <div className="text-xs text-black/50 mt-0.5">Last 4 pay periods</div>
          </div>
          <div className="divide-y divide-black/5">
            {payPeriods.map((p) => (
              <div key={p.label} className="flex items-center justify-between px-5 py-3">
                <div>
                  <div className="text-sm font-medium">{p.label}</div>
                  <div className="text-xs text-black/50">Net: {fmt(p.net)}</div>
                </div>
                <span className="rounded-full bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs px-2.5 py-0.5 font-medium capitalize">
                  {p.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
