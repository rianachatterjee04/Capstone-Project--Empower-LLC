"use client";
import { useMemo, useState } from "react";
import { useLiveData } from "@/lib/useLiveData";

/**
 * People / HR Reports — native report center for the Foundry People module.
 * Catalog + inline viewer, self-contained sample data (no backend needed). The
 * same reports also appear in the unified Fintra Reports Center.
 */
const CAT: { group: string; items: [string, string][] }[] = [
  { group: "Workforce", items: [
    ["Headcount by Department", "kv2"],
    ["Headcount Plan vs Actual", "variance"],
    ["Attrition & Turnover", "kv2"],
    ["Attrition Risk (predictive)", "risk"],
    ["AI Workforce Registry", "risk"],
    ["AI Productivity Analytics", "kv2"],
  ]},
  { group: "Hiring", items: [
    ["Recruiting Funnel", "funnel"],
    ["Time to Hire", "kv"],
    ["Offer Acceptance Rate", "kv"],
    ["Onboarding / Offboarding Status", "kv"],
  ]},
  { group: "Performance & Talent", items: [
    ["Performance Review Status", "kv2"],
    ["9-Box Calibration", "risk"],
    ["Skills Matrix", "risk"],
  ]},
  { group: "Compensation", items: [
    ["Compensation Benchmarking", "kv2"],
    ["Pay Equity Analysis", "risk"],
    ["Diversity & Inclusion", "kv2"],
    ["PTO & Leave Balances", "kv2"],
  ]},
];
const ALL = CAT.flatMap((c) => c.items);
const C = { text: "#0f172a", sub: "#64748b", border: "#e2e8f0", card: "#fff", bg: "#f8fafc", accent: "#7c3aed" };

function pill(s: string) {
  const ok = /low|high perf|complete|active|on track|fair|owned/i.test(s);
  const warn = /medium|review|partial|pending|watch/i.test(s);
  const bg = ok ? "#dcfce7" : warn ? "#fef9c3" : "#fee2e2";
  const fg = ok ? "#166534" : warn ? "#854d0e" : "#991b1b";
  return <span style={{ background: bg, color: fg, padding: "2px 9px", borderRadius: 999, fontSize: 11.5, fontWeight: 600 }}>{s}</span>;
}

function Body({ shape, liveRows, liveStages }: { shape: string; liveRows?: [string, number][]; liveStages?: [string, number][] }) {
  if (shape === "funnel") {
    const stages: [string, number][] = liveStages && liveStages.length ? liveStages
      : [["Applicants", 420], ["Screened", 198], ["Interview", 92], ["Onsite", 41], ["Offer", 18], ["Hired", 13]];
    const max = Math.max(1, ...stages.map((s) => s[1]));
    return <div>{stages.map(([l, n]) => (
      <div key={l} style={{ display: "flex", alignItems: "center", gap: 12, padding: "7px 0", borderBottom: "1px solid #f1f5f9" }}>
        <div style={{ width: 110, fontWeight: 600, fontSize: 13.5 }}>{l}</div>
        <div style={{ flex: 1, background: "#f1f5f9", borderRadius: 6, height: 20, overflow: "hidden" }}>
          <div style={{ width: `${Math.max(6, (n / max) * 100)}%`, height: "100%", background: C.accent, opacity: 0.85 }} />
        </div>
        <div style={{ width: 60, textAlign: "right", fontWeight: 600 }}>{n}</div>
      </div>))}</div>;
  }
  if (shape === "variance") {
    const rows: [string, number, number][] = [["Engineering", 45, 42], ["Sales", 30, 28], ["Operations", 18, 19], ["G&A", 12, 11]];
    return <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13.5 }}>
      <thead><tr style={{ color: C.sub, fontSize: 11, textTransform: "uppercase" }}>
        {["Department", "Plan", "Actual", "Var"].map((h, i) => <th key={h} style={{ textAlign: i ? "right" : "left", padding: "6px 8px", borderBottom: `1px solid ${C.border}` }}>{h}</th>)}
      </tr></thead>
      <tbody>{rows.map(([d, p, a]) => <tr key={d} style={{ borderBottom: "1px solid #f1f5f9" }}>
        <td style={{ padding: 8 }}>{d}</td><td style={{ padding: 8, textAlign: "right" }}>{p}</td>
        <td style={{ padding: 8, textAlign: "right" }}>{a}</td>
        <td style={{ padding: 8, textAlign: "right", color: a - p >= 0 ? "#16a34a" : "#dc2626" }}>{a - p > 0 ? "+" : ""}{a - p}</td></tr>)}</tbody>
    </table>;
  }
  if (shape === "risk") {
    const rows: [string, string, string][] = [["Engineering", "Low", "94"], ["Sales", "Medium", "78"], ["Operations", "Low", "88"], ["AI Agents (9)", "Owned", "—"]];
    return <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13.5 }}>
      <thead><tr style={{ color: C.sub, fontSize: 11, textTransform: "uppercase" }}>
        {["Group", "Status", "Score"].map((h) => <th key={h} style={{ textAlign: "left", padding: "6px 8px", borderBottom: `1px solid ${C.border}` }}>{h}</th>)}
      </tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i} style={{ borderBottom: "1px solid #f1f5f9" }}>
        <td style={{ padding: 8 }}>{r[0]}</td><td style={{ padding: 8 }}>{pill(r[1])}</td><td style={{ padding: 8, fontWeight: 600 }}>{r[2]}</td></tr>)}</tbody>
    </table>;
  }
  if (shape === "kv2") {
    const rows: [string, string][] = liveRows && liveRows.length
      ? [...liveRows.map(([k, v]) => [k, String(v)] as [string, string]),
         ["Total", String(liveRows.reduce((s, r) => s + Number(r[1]), 0))]]
      : [["Engineering", "42"], ["Sales", "28"], ["Operations", "19"], ["G&A", "11"], ["Total", "100"]];
    return <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13.5 }}>
      <tbody>{rows.map(([k, v], i) => <tr key={k} style={{ borderBottom: "1px solid #f1f5f9", fontWeight: i === rows.length - 1 ? 700 : 400 }}>
        <td style={{ padding: 8 }}>{k}</td><td style={{ padding: 8, textAlign: "right" }}>{v}</td></tr>)}</tbody>
    </table>;
  }
  const kv = [["Status", "On track"], ["This period", "Q4 2026"], ["Owner", "HR Agent"], ["Last updated", "Dec 20, 2026"]];
  return <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13.5 }}>
    <tbody>{kv.map(([k, v]) => <tr key={k} style={{ borderBottom: "1px solid #f1f5f9" }}>
      <td style={{ padding: 8, color: C.sub }}>{k}</td><td style={{ padding: 8, textAlign: "right", fontWeight: 600 }}>{v}</td></tr>)}</tbody>
  </table>;
}

export default function ReportsPage() {
  const [sel, setSel] = useState<[string, string]>(ALL[0]);
  const [q, setQ] = useState("");
  const cats = useMemo(() => CAT.map((c) => ({ ...c, items: c.items.filter(([n]) => n.toLowerCase().includes(q.toLowerCase())) })).filter((c) => c.items.length), [q]);

  // Live data from hr-api (falls back to sample until non-empty data arrives).
  const headcount = useLiveData<[string, number][]>("/reports/headcount", [], (j) => (j.rows || []).map((r: any) => [r[0], Number(r[1])]));
  const attrition = useLiveData<[string, number][]>("/reports/attrition", [], (j) => (j.rows || []).map((r: any) => [r[0], Number(r[1])]));
  const funnel = useLiveData<[string, number][]>("/reports/recruiting-funnel", [], (j) => (j.stages || []).map((s: any) => [s.stage, Number(s.count)]));
  const pto = useLiveData<[string, number][]>("/reports/pto", [], (j) => (j.rows || []).map((r: any) => [r[0], Number(r[1])]));
  const comp = useLiveData<[string, number][]>("/reports/compensation", [], (j) => (j.rows || []).map((r: any) => [r[0], Number(r[1])]));
  const perf = useLiveData<[string, number][]>("/reports/performance", [], (j) => (j.rows || []).map((r: any) => [r[0], Number(r[1])]));
  const liveByName: Record<string, { rows?: [string, number][]; stages?: [string, number][]; live: boolean }> = {
    "Headcount by Department": { rows: headcount.data, live: headcount.live },
    "Attrition & Turnover": { rows: attrition.data, live: attrition.live },
    "Recruiting Funnel": { stages: funnel.data, live: funnel.live },
    "PTO & Leave Balances": { rows: pto.data, live: pto.live },
    "Compensation Benchmarking": { rows: comp.data, live: comp.live },
    "Performance Review Status": { rows: perf.data, live: perf.live },
  };
  const liveSel = liveByName[sel[0]];
  return (
    <div style={{ background: C.bg, minHeight: "100vh", color: C.text, padding: 24 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>People / HR Reports</h1>
      <p style={{ color: C.sub, marginTop: 4 }}>{ALL.length} reports — workforce, hiring, performance, compensation and the AI workforce.</p>
      <div style={{ display: "grid", gridTemplateColumns: "300px 1fr", gap: 18, marginTop: 18 }}>
        <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, padding: 12 }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search reports" style={{ width: "100%", padding: "8px 10px", border: `1px solid ${C.border}`, borderRadius: 8, marginBottom: 10 }} />
          {cats.map((c) => (
            <div key={c.group} style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: C.sub, textTransform: "uppercase", letterSpacing: 0.4, margin: "4px 0" }}>{c.group}</div>
              {c.items.map(([n, s]) => (
                <button key={n} onClick={() => setSel([n, s])} style={{ display: "block", width: "100%", textAlign: "left", padding: "7px 9px", borderRadius: 7, border: "none", cursor: "pointer", fontSize: 13, background: sel[0] === n ? "#f3e8ff" : "transparent", color: sel[0] === n ? C.accent : C.text }}>{n}</button>
              ))}
            </div>
          ))}
        </div>
        <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 14, padding: 24 }}>
          <div style={{ textAlign: "center", marginBottom: 16 }}>
            <div style={{ fontWeight: 700 }}>Fintra Demo, Inc. · People</div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>{sel[0]}</div>
            <div style={{ fontSize: 12.5, color: C.sub }}>As of December 31, 2026</div>
            {liveSel && (
              <span style={{ display: "inline-block", marginTop: 8, fontSize: 11, padding: "2px 8px", borderRadius: 999,
                background: liveSel.live ? "#dcfce7" : "#f1f5f9", color: liveSel.live ? "#166534" : C.sub }}>
                {liveSel.live ? "Live data" : "Live-ready · sample shown"}
              </span>
            )}
          </div>
          <Body shape={sel[1]} liveRows={liveSel?.rows} liveStages={liveSel?.stages} />
        </div>
      </div>
    </div>
  );
}
