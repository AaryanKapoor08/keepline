"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ShieldAlert, ShieldCheck, TriangleAlert, ArrowRight, Users } from "lucide-react";
import { postJSON, snapshot, nearest, normQ, first, fmtDate, pname, riskColor } from "@/lib/data";
import { Badge, PageHeader, Receipt, cn } from "@/components/ui";

const DECISIONS = [
  "Rotate the CoreLink API key this Friday",
  "Run the reconciliation job manually on the 15th",
  "Restart the ACH server at 4pm today",
  "Restore last night's backup onto the replication primary",
];
const BRIEF =
  "Migrate the member portal to a new SSL provider and add CoreLink webhooks so nightly reconciliation runs faster. Touches ACH settlement files too.";

const VERDICT: Record<string, { label: string; cls: string; icon: any }> = {
  conflict: { label: "Conflict", cls: "border-alarm/50 bg-alarm/10 text-alarm", icon: ShieldAlert },
  caution: { label: "Caution", cls: "border-warn/40 bg-warn/10 text-warn", icon: TriangleAlert },
  clear: { label: "Clear", cls: "border-accent/40 bg-accent/10 text-accent", icon: ShieldCheck },
};

function DecisionCheck() {
  const [text, setText] = useState(DECISIONS[0]);
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const run = async (t: string) => {
    setText(t);
    setBusy(true);
    let r = await postJSON("/decision", { text: t });
    if (!r) {
      const table = (await snapshot("decisions")) ?? {};
      r = table[normQ(t)] ?? nearest(t, table);
    }
    setRes(r);
    setBusy(false);
  };
  const v = res ? VERDICT[res.verdict] ?? VERDICT.clear : null;
  const top = (res?.conflicts ?? []).filter((c: any) => c.severity === "conflict" || res.verdict !== "conflict").slice(0, 2);
  return (
    <div>
      <form onSubmit={(e) => { e.preventDefault(); run(text); }} className="flex gap-2">
        <input value={text} onChange={(e) => setText(e.target.value)} className="glass h-12 flex-1 rounded-xl px-4 text-[16px] outline-none focus:border-accent/40" />
        <button className="rounded-xl bg-accent px-5 text-[14px] font-semibold text-bg disabled:opacity-50" disabled={busy}>Check</button>
      </form>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {DECISIONS.map((d) => (
          <button key={d} onClick={() => run(d)} className="rounded-full border border-line px-2.5 py-0.5 text-[12px] text-muted hover:border-accent/40 hover:text-fg">{d}</button>
        ))}
      </div>
      <AnimatePresence mode="wait">
        {res && v && (
          <motion.div key={res.proposal} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="mt-4 space-y-3">
            <div className={cn("flex items-center gap-3 rounded-xl border px-4 py-3", v.cls)}>
              <v.icon className="h-6 w-6" />
              <div className="flex-1">
                <div className="text-[18px] font-semibold uppercase tracking-wide">{v.label}</div>
                <div className="text-[13px] opacity-85">
                  {res.target_dates?.length ? `Target date ${fmtDate(res.target_dates[0])}. ` : ""}
                  {(res.areas ?? []).map((a: any) => a.area_name).join(" · ")}
                </div>
              </div>
              {res.suggested_reviewer && (
                <div className="text-right text-[12px]">
                  <div className="opacity-70">Suggested reviewer</div>
                  <div className="text-[14px] font-semibold">{res.suggested_reviewer_name ?? pname(res.suggested_reviewer)}</div>
                </div>
              )}
            </div>
            {top.map((c: any, i: number) => (
              <div key={i}>
                {c.why && <div className="mb-1 font-mono text-[11.5px] text-alarm">{c.why}</div>}
                <Receipt c={c} />
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function WhatIf() {
  const [people, setPeople] = useState<string[]>(["sarah", "mike", "tom"]);
  const [date, setDate] = useState("2026-12-31");
  const [res, setRes] = useState<any>(null);
  const run = async () => {
    let r = await postJSON("/whatif", { people, date });
    if (!r) r = await snapshot("whatif_multi");
    setRes(r);
  };
  const before = Object.fromEntries((res?.before ?? []).map((r: any) => [r.area_id, r]));
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        {["sarah", "mike", "tom", "aisha", "priya"].map((p) => (
          <button key={p} onClick={() => setPeople((ps) => (ps.includes(p) ? ps.filter((x) => x !== p) : [...ps, p]))} className={cn("rounded-full border px-3 py-1 text-[13px]", people.includes(p) ? "border-alarm/50 bg-alarm/10 text-alarm" : "border-line text-muted")}>
            {pname(p)}
          </button>
        ))}
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="glass rounded-lg px-2 py-1 font-mono text-[12px] [color-scheme:dark]" />
        <button onClick={run} className="ml-auto flex items-center gap-1.5 rounded-lg bg-accent px-4 py-1.5 text-[13px] font-semibold text-bg">Run what-if <ArrowRight className="h-3.5 w-3.5" /></button>
      </div>
      {res && (
        <div className="mt-4 space-y-1.5">
          <div className="mb-2 text-[13px] text-muted">
            If {res.people.map(first).join(", ")} are gone by {fmtDate(res.date)}: <span className="font-semibold text-alarm">{res.orphaned_areas.length} areas orphaned</span>
          </div>
          {(res.after as any[]).sort((a, b) => b.risk - a.risk).slice(0, 7).map((r: any, i: number) => {
            const b = before[r.area_id];
            return (
              <div key={r.area_id} className="flex items-center gap-3 text-[13px]">
                <span className="w-[210px] truncate">{r.area_name}</span>
                <div className="relative h-2.5 flex-1 overflow-hidden rounded-full bg-white/5">
                  <div className="absolute h-full rounded-full bg-white/15" style={{ width: `${(b?.risk ?? 0) * 100}%` }} />
                  <motion.div initial={{ width: `${(b?.risk ?? 0) * 100}%` }} animate={{ width: `${r.risk * 100}%` }} transition={{ duration: 0.9, delay: i * 0.05 }} className="absolute h-full rounded-full" style={{ background: riskColor(r.risk) }} />
                </div>
                <span className="w-[92px] text-right font-mono text-[12px] tabular-nums text-dim">{Math.round((b?.risk ?? 0) * 100)} → <span style={{ color: riskColor(r.risk) }}>{Math.round(r.risk * 100)}</span></span>
                <span className={cn("w-[52px] text-right font-mono text-[12px]", r.bus_factor === 0 ? "text-alarm" : "text-muted")}>bf {r.bus_factor}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Staffing() {
  const [brief, setBrief] = useState(BRIEF);
  const [res, setRes] = useState<any>(null);
  const run = async () => {
    let r = await postJSON("/staffing", { text: brief });
    if (!r) r = await snapshot("staffing");
    setRes(r);
  };
  return (
    <div>
      <textarea value={brief} onChange={(e) => setBrief(e.target.value)} rows={3} className="glass w-full resize-none rounded-xl p-3 text-[14px] leading-relaxed outline-none focus:border-accent/40" />
      <button onClick={run} className="mt-2 flex items-center gap-1.5 rounded-lg bg-accent px-4 py-1.5 text-[13px] font-semibold text-bg">Plan staffing <ArrowRight className="h-3.5 w-3.5" /></button>
      {res && (
        <div className="mt-4 space-y-2">
          {(res.areas ?? []).map((a: any, i: number) => (
            <motion.div key={a.area_id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }} className="rounded-xl border border-line bg-black/20 p-3">
              <div className="flex items-center gap-3">
                <span className="flex-1 text-[14px] font-medium">{a.area_name}</span>
                <span className="font-mono text-[13px] tabular-nums">
                  bus factor <span className={a.bus_factor_before <= 1 ? "text-alarm" : ""}>{a.bus_factor_before}</span> → <span className="text-accent">{a.bus_factor_after}</span>
                </span>
              </div>
              <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[12px] text-muted">
                <Users className="h-3.5 w-3.5" />
                {a.learner_name && <Badge tone="accent">learner · {a.learner_name}</Badge>}
                {a.reviewer_name && <Badge>reviewer · {a.reviewer_name}</Badge>}
                {(a.holders ?? []).map((h: any) => (
                  <span key={h.person_id}>{h.name}{h.leaving_in_days != null ? <span className="text-alarm"> (leaves in {h.leaving_in_days}d)</span> : ""}</span>
                ))}
              </div>
              {a.rationale && <div className="mt-1 text-[12px] text-dim">{a.rationale}</div>}
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function SimulatePage() {
  return (
    <div>
      <PageHeader eyebrow="07 · Simulator" title="Check a decision before you make it" sub="The same versioned memory, pointed forward: test a change against every rule on record, model departures, and staff a project so it doesn't create the next bus-factor-1." />
      <div className="grid grid-cols-[1.25fr_1fr] gap-5">
        <div className="glass rounded-2xl p-5">
          <div className="mb-3 text-[12px] uppercase tracking-[0.16em] text-dim">Decision check</div>
          <DecisionCheck />
        </div>
        <div className="flex flex-col gap-5">
          <div className="glass rounded-2xl p-5">
            <div className="mb-3 text-[12px] uppercase tracking-[0.16em] text-dim">Departure what-if</div>
            <WhatIf />
          </div>
          <div className="glass rounded-2xl p-5">
            <div className="mb-3 text-[12px] uppercase tracking-[0.16em] text-dim">Project staffing</div>
            <Staffing />
          </div>
        </div>
      </div>
    </div>
  );
}
