"use client";

import { useMemo, useState } from "react";

type OnboardingField =
  | "first_name"
  | "last_name"
  | "preferred_name"
  | "email"
  | "phone"
  | "job_title"
  | "department"
  | "manager"
  | "start_date"
  | "salary"
  | "pay_frequency"
  | "bank_name"
  | "account_last4"
  | "routing_last4"
  | "ssn_last4"
  | "citizenship_status"
  | "documents"
  | "benefits";

type OnboardingStep = {
  key: string;
  title: string;
  fields: OnboardingField[];
};

type OnboardingForm = {
  first_name?: string;
  last_name?: string;
  preferred_name?: string;
  email?: string;
  phone?: string;
  job_title?: string;
  department?: string;
  manager?: string;
  start_date?: string;
  salary?: string;
  pay_frequency?: string;
  bank_name?: string;
  account_last4?: string;
  routing_last4?: string;
  ssn_last4?: string;
  citizenship_status?: string;
  documents?: string;
  benefits?: string;
};

function Input({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
  maxLength,
}: {
  label: string;
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  type?: string;
  placeholder?: string;
  maxLength?: number;
}) {
  return (
    <label className="block">
      <div className="mb-1 text-sm font-medium text-black/80">{label}</div>
      <input
        type={type}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        maxLength={maxLength}
        className="w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none ring-0 transition focus:border-black/30"
      />
    </label>
  );
}

function Textarea({
  label,
  value,
  onChange,
  placeholder,
  rows = 4,
}: {
  label: string;
  value: string;
  onChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  placeholder?: string;
  rows?: number;
}) {
  return (
    <label className="block">
      <div className="mb-1 text-sm font-medium text-black/80">{label}</div>
      <textarea
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        rows={rows}
        className="w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none ring-0 transition focus:border-black/30"
      />
    </label>
  );
}

const steps: OnboardingStep[] = [
  {
    key: "personal",
    title: "Personal info",
    fields: ["first_name", "last_name", "preferred_name", "email", "phone"],
  },
  {
    key: "job",
    title: "Job details",
    fields: ["job_title", "department", "manager", "start_date"],
  },
  {
    key: "payroll",
    title: "Payroll",
    fields: ["salary", "pay_frequency", "bank_name", "account_last4", "routing_last4", "ssn_last4"],
  },
  {
    key: "i9",
    title: "I-9 verification",
    fields: ["citizenship_status", "documents"],
  },
  {
    key: "benefits",
    title: "Benefits",
    fields: ["benefits"],
  },
];

export default function OnboardingPage() {
  const [currentStep, setCurrentStep] = useState(0);
  const [form, setForm] = useState<OnboardingForm>({
    pay_frequency: "biweekly",
  });

  const step = steps[currentStep];

  const progress = useMemo(() => {
    return Math.round(((currentStep + 1) / steps.length) * 100);
  }, [currentStep]);

  function next() {
    setCurrentStep((s) => Math.min(s + 1, steps.length - 1));
  }

  function back() {
    setCurrentStep((s) => Math.max(s - 1, 0));
  }

  function submit() {
    console.log("Onboarding form submitted:", form);
    alert("Onboarding packet saved locally for MVP.");
  }

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-black/10 bg-white p-6 shadow-sm">
        <div className="mb-2 text-2xl font-semibold">Employee onboarding</div>
        <div className="text-sm text-black/60">
          Collect basic personal, job, payroll, verification, and benefits information.
        </div>

        <div className="mt-4">
          <div className="mb-2 flex items-center justify-between text-xs text-black/50">
            <span>
              Step {currentStep + 1} of {steps.length}
            </span>
            <span>{progress}% complete</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-black/10">
            <div
              className="h-full rounded-full bg-black transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-black/10 bg-white p-6 shadow-sm">
        <div className="mb-1 text-lg font-semibold">{step.title}</div>
        <div className="mb-6 text-sm text-black/60">
          Complete the fields below for this section.
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {step.fields.includes("first_name") ? (
            <Input
              label="First name"
              value={form.first_name ?? ""}
              onChange={(e) => setForm({ ...form, first_name: e.target.value })}
            />
          ) : null}

          {step.fields.includes("last_name") ? (
            <Input
              label="Last name"
              value={form.last_name ?? ""}
              onChange={(e) => setForm({ ...form, last_name: e.target.value })}
            />
          ) : null}

          {step.fields.includes("preferred_name") ? (
            <Input
              label="Preferred name"
              value={form.preferred_name ?? ""}
              onChange={(e) => setForm({ ...form, preferred_name: e.target.value })}
            />
          ) : null}

          {step.fields.includes("email") ? (
            <Input
              label="Email"
              type="email"
              value={form.email ?? ""}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          ) : null}

          {step.fields.includes("phone") ? (
            <Input
              label="Phone"
              value={form.phone ?? ""}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
            />
          ) : null}

          {step.fields.includes("job_title") ? (
            <Input
              label="Job title"
              value={form.job_title ?? ""}
              onChange={(e) => setForm({ ...form, job_title: e.target.value })}
            />
          ) : null}

          {step.fields.includes("department") ? (
            <Input
              label="Department"
              value={form.department ?? ""}
              onChange={(e) => setForm({ ...form, department: e.target.value })}
            />
          ) : null}

          {step.fields.includes("manager") ? (
            <Input
              label="Manager"
              value={form.manager ?? ""}
              onChange={(e) => setForm({ ...form, manager: e.target.value })}
            />
          ) : null}

          {step.fields.includes("start_date") ? (
            <Input
              label="Start date"
              type="date"
              value={form.start_date ?? ""}
              onChange={(e) => setForm({ ...form, start_date: e.target.value })}
            />
          ) : null}

          {step.fields.includes("salary") ? (
            <Input
              label="Annual salary"
              type="number"
              value={form.salary ?? ""}
              onChange={(e) => setForm({ ...form, salary: e.target.value })}
              placeholder="120000"
            />
          ) : null}

          {step.fields.includes("pay_frequency") ? (
            <label className="block">
              <div className="mb-1 text-sm font-medium text-black/80">Pay frequency</div>
              <select
                value={form.pay_frequency ?? "biweekly"}
                onChange={(e) => setForm({ ...form, pay_frequency: e.target.value })}
                className="w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none transition focus:border-black/30"
              >
                <option value="weekly">Weekly</option>
                <option value="biweekly">Biweekly</option>
                <option value="semimonthly">Semimonthly</option>
                <option value="monthly">Monthly</option>
              </select>
            </label>
          ) : null}

          {step.fields.includes("bank_name") ? (
            <Input
              label="Bank name"
              value={form.bank_name ?? ""}
              onChange={(e) => setForm({ ...form, bank_name: e.target.value })}
            />
          ) : null}

          {step.fields.includes("account_last4") ? (
            <Input
              label="Account last 4"
              maxLength={4}
              value={form.account_last4 ?? ""}
              onChange={(e) => setForm({ ...form, account_last4: e.target.value })}
            />
          ) : null}

          {step.fields.includes("routing_last4") ? (
            <Input
              label="Routing last 4"
              maxLength={4}
              value={form.routing_last4 ?? ""}
              onChange={(e) => setForm({ ...form, routing_last4: e.target.value })}
            />
          ) : null}

          {step.fields.includes("ssn_last4") ? (
            <Input
              label="SSN last 4"
              maxLength={4}
              value={form.ssn_last4 ?? ""}
              onChange={(e) => setForm({ ...form, ssn_last4: e.target.value })}
            />
          ) : null}

          {step.fields.includes("citizenship_status") ? (
            <label className="block md:col-span-2">
              <div className="mb-1 text-sm font-medium text-black/80">Citizenship status</div>
              <select
                value={form.citizenship_status ?? ""}
                onChange={(e) => setForm({ ...form, citizenship_status: e.target.value })}
                className="w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none transition focus:border-black/30"
              >
                <option value="">Select</option>
                <option value="us_citizen">U.S. Citizen</option>
                <option value="permanent_resident">Permanent Resident</option>
                <option value="authorized_noncitizen">Authorized Noncitizen</option>
              </select>
            </label>
          ) : null}

          {step.fields.includes("documents") ? (
            <div className="md:col-span-2">
              <Textarea
                label="I-9 documents (MVP)"
                value={form.documents ?? ""}
                onChange={(e) => setForm({ ...form, documents: e.target.value })}
                placeholder="List documents you will provide (e.g., Passport, Driver's license + SS card)."
              />
            </div>
          ) : null}

          {step.fields.includes("benefits") ? (
            <div className="md:col-span-2">
              <Textarea
                label="Benefits elections / notes"
                value={form.benefits ?? ""}
                onChange={(e) => setForm({ ...form, benefits: e.target.value })}
                placeholder="Medical plan, dental, vision, HSA/FSA, dependents, and any notes."
              />
            </div>
          ) : null}
        </div>

        <div className="mt-8 flex items-center justify-between">
          <button
            onClick={back}
            disabled={currentStep === 0}
            className="rounded-xl border border-black/10 px-4 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-40"
          >
            Back
          </button>

          {currentStep < steps.length - 1 ? (
            <button
              onClick={next}
              className="rounded-xl bg-black px-4 py-2 text-sm font-medium text-white"
            >
              Next
            </button>
          ) : (
            <button
              onClick={submit}
              className="rounded-xl bg-black px-4 py-2 text-sm font-medium text-white"
            >
              Finish
            </button>
          )}
        </div>
      </div>

      <div className="rounded-2xl border border-black/10 bg-white p-6 shadow-sm">
        <div className="mb-2 text-sm font-semibold">Current payload preview</div>
        <pre className="overflow-x-auto rounded-xl bg-black p-4 text-xs text-white">
{JSON.stringify(form, null, 2)}
        </pre>
      </div>
    </div>
  );
}
