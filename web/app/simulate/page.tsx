"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import dynamic from "next/dynamic";
import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { postJSON, snapshot, normQ, nearest, first, pname, fmtDate } from "@/lib/data";
import { PageTop, Card, Quote, Details, Fade, Big, EASE } from "@/components/kit";
import { cn } from "@/components/ui";
import type { FlowNode, FlowEdge } from "@/components/flow";

const Flow = dynamic(() => import("@/components/flow"), { ssr: false });

const TEMPLATES = [
  { id: "corelink_v3", name: "Upgrade CoreLink API to v3" },
  { id: "mobile_app", name: "Launch new mobile banking app" },
  { id: "fintrac", name: "FINTRAC reporting overhaul" },
];
const SHORT: Record<string, string> = {
  reconciliation: "Reconciliation", corelink_api: "CoreLink API", ssl_dns: "SSL & DNS", ach_payments: "ACH payments", member_portal: "Member portal",
  identity_access: "Identity & access", backups_dr: "Backups & DR", fintrac_reporting: "FINTRAC & AML", payroll: "Payroll", card_processing: "Card processing",
};
const pct = (v?: number) => (v == null ? "—" : `${Math.round(v * 100)}%`);

async function runSim(tid: string, leave: string | null, weeks: number) {
  let r = await postJSON("/project_sim", { template_id: tid, leaves: leave ? { [leave]: Math.floor(weeks / 2) } : null });
  if (!r) {
    const all = (await snapshot("project_sims")) ?? {};
    r = all[leave ? `${tid}|${leave}` : tid] ?? all[tid];
  }
  return r;
}

function DecisionCard() {
  const [r, setR] = useState<any>(null);
  const [why, setWhy] = useState(false);
  const run = async () => {
    const t = "Rotate the CoreLink API key this Friday";
    let res = await postJSON("/decision", { text: t });
    if (!res) {
      const table = (await snapshot("decisions")) ?? {};
      res = table[normQ(t)] ?? nearest(t, table);
    }
    setR(res);
  };
  const top = r?.conflicts?.[0];
  return (
    <Card title="Check a decision" right={r ? <Details onClick={() => setWhy(!why)} open={why}>{why ? "Hide" : "Why"}</Details> : <Details onClick={run}>Check</Details>}>
      <div className="rounded-[16px] bg-[#f4f5f7] px-4 py-3 text-[15px]">Rotate the CoreLink API key this Friday</div>
      {r && (
        <div className="mt-3 flex items-center gap-2 text-[18px] font-medium">
          {r.verdict === "conflict" && <span className="h-2.5 w-2.5 rounded-full bg-alarm" />}
          {r.verdict === "conflict" ? `Conflicts with a rule ${first(top?.stated_by)} set.` : "No conflicts on record."}
        </div>
      )}
      <Fade show={why && !!top} className="mt-3 rounded-[16px] bg-[#f4f5f7] p-4">{top && <Quote c={top} small />}</Fade>
    </Card>
  );
}

export default function SimulatePage() {
  const [tid, setTid] = useState("corelink_v3");
  const [r, setR] = useState<any>(null);
  const [opt, setOpt] = useState<string | null>(null);
  const [leave, setLeave] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const go = async (t = tid, l = leave) => {
    setBusy(true);
    const res = await runSim(t, l, t === "corelink_v3" ? 12 : 16);
    setR(res);
    if (!opt || !l) setOpt(res?.recommended ?? "balanced");
    setBusy(false);
  };
  const o = r?.options?.find((x: any) => x.id === opt) ?? r?.options?.[0];

  const nodes: FlowNode[] = [];
  const edges: FlowEdge[] = [];
  if (o) {
    nodes.push({ id: "p", label: TEMPLATES.find((t) => t.id === tid)?.name ?? "Project", sub: `${r.weeks} weeks`, icon: "db", trigger: true, wide: true });
    const people = new Set<string>();
    for (const a of o.areas) {
      nodes.push({ id: `a:${a.area_id}`, label: SHORT[a.area_id] ?? a.area_name, sub: a.status === "lack" ? "no one available" : `${pct(a.p_uncovered_at_end)} gap at end`, icon: "db", state: a.status === "lack" || a.p_uncovered_at_end > 0.3 ? "risk" : "done" });
      edges.push({ s: "p", t: `a:${a.area_id}` });
      for (const [k, role] of [["lead", "leads"], ["reviewer", "reviews"], ["learner", "learns"]] as const) {
        const pid = a[k];
        if (!pid) continue;
        if (!people.has(pid)) {
          people.add(pid);
          const dep = r.timeline.find((x: any) => x.person_id === pid);
          nodes.push({ id: `u:${pid}`, label: pname(pid), sub: dep ? `leaves week ${dep.week + 1}` : undefined, icon: "user", state: dep ? "risk" : "idle" });
        }
        edges.push({ s: `a:${a.area_id}`, t: `u:${pid}`, label: role, dashed: k === "learner" });
      }
    }
  }

  return (
    <>
      <PageTop title="Simulate a project before you staff it." action={busy ? "Running…" : r ? "Run again" : "Run simulation"} onAction={() => go()} />
      <div className="mb-4 flex gap-2">
        {TEMPLATES.map((t) => (
          <button key={t.id} onClick={() => { setTid(t.id); setLeave(null); setOpt(null); if (r) go(t.id, null); }} className={cn("h-11 rounded-full px-5 text-[14px]", tid === t.id ? "bg-[#111] text-white" : "bg-white hover:bg-white/70")}>{t.name}</button>
        ))}
      </div>

      {!r ? (
        <div className="grid grid-cols-[1.6fr_1fr] gap-4">
          <Card className="min-h-[300px] justify-center">
            <div className="max-w-[560px] text-[19px] leading-relaxed text-muted">
              Keepline maps the project to the areas it needs, staffs it three ways from who actually knows what, then plays out {"2,000"} possible futures with the known departures and ordinary absences.
            </div>
          </Card>
          <DecisionCard />
        </div>
      ) : (
        <>
          <div className="grid grid-cols-[1fr_1fr_1fr_1fr] gap-4">
            <Card title="Staffing option">
              <div className="space-y-2">
                {r.options.map((x: any) => (
                  <button key={x.id} onClick={() => setOpt(x.id)} className={cn("flex w-full items-center justify-between rounded-[14px] px-4 py-2.5 text-left text-[15px]", opt === x.id ? "bg-[#111] text-white" : "bg-[#f4f5f7] hover:bg-[#ececef]")}>
                    {x.label}
                    {r.recommended === x.id && <span className={cn("text-[12px]", opt === x.id ? "text-white/60" : "text-muted")}>recommended</span>}
                  </button>
                ))}
              </div>
            </Card>
            <Card title="Area still uncovered at the end" dark>
              <Big value={pct(o.p_uncovered_at_end)} caption={<>chance, over<br />{r.runs.toLocaleString()} futures</>} dark />
            </Card>
            <Card title="Weeks with a gap">
              <Big value={o.expected_gap_weeks} caption={<>expected area-weeks<br />with no one who knows it</>} />
            </Card>
            <Card title="Busiest person">
              <Big value={o.busiest.areas} caption={<>areas for<br />{o.busiest.name}</>} />
            </Card>
          </div>

          <div className="mt-4 grid grid-cols-[1.6fr_1fr] gap-4">
            <Card title="Plan" right={<span className="text-[13px] text-muted">{o.description.split(":")[1]}</span>}>
              <AnimatePresence mode="wait">
                <motion.div key={opt + String(leave) + tid} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.5, ease: EASE }}>
                  <Flow nodes={nodes} edges={edges} height={400} />
                </motion.div>
              </AnimatePresence>
            </Card>
            <div className="space-y-4">
              <Card title="Timeline" right={<span className="text-[13px] text-muted">{fmtDate(r.start)} → {fmtDate(r.end)}</span>}>
                <div className="relative mt-2 h-10">
                  <div className="absolute inset-x-0 top-4 h-2 rounded-full bg-[#f4f5f7]" />
                  {r.timeline.map((x: any) => (
                    <div key={x.person_id} className="absolute top-0 flex -translate-x-1/2 flex-col items-center" style={{ left: `${Math.min(97, Math.max(3, ((x.week + 0.5) / r.weeks) * 100))}%` }}>
                      <span className="h-10 w-0.5 bg-alarm" />
                    </div>
                  ))}
                </div>
                <div className="mt-2 space-y-1 text-[13px]">
                  {r.timeline.map((x: any) => (
                    <div key={x.person_id} className="flex justify-between"><span>{x.name} leaves{x.forced ? " (what-if)" : ""}</span><span className="text-muted">week {x.week + 1} · {fmtDate(x.date)}</span></div>
                  ))}
                </div>
              </Card>
              <Card title="What if someone leaves mid-project?">
                <div className="flex flex-wrap gap-2">
                  {o.people.filter((p: string) => !r.timeline.some((x: any) => x.person_id === p && !x.forced)).map((p: string) => (
                    <button key={p} onClick={() => { const l = leave === p ? null : p; setLeave(l); go(tid, l); }} className={cn("rounded-full px-3.5 py-2 text-[13px]", leave === p ? "bg-[#111] text-white" : "bg-[#f4f5f7] hover:bg-[#ececef]")}>{first(p)}</button>
                  ))}
                </div>
                <div className="mt-2 text-[12.5px] text-muted">Removes them at week {Math.floor(r.weeks / 2) + 1} and re-runs every future.</div>
              </Card>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-3 gap-4">
            <Card title="Where we lack">
              {o.areas.filter((a: any) => a.status !== "strong").map((a: any) => (
                <div key={a.area_id} className="border-b border-[#ececec] py-2.5 text-[14px] last:border-0">
                  <span className={a.status === "lack" ? "text-alarm" : ""}>{a.area_name}</span>
                  <div className="text-[12.5px] text-muted">{a.status === "lack" ? "no holder available for the project" : a.learner_name ? `one person on the project knows it · ${a.learner_name} learns it` : "one person on the project knows it"}</div>
                </div>
              ))}
              {!o.areas.some((a: any) => a.status !== "strong") && <div className="text-[14px] text-muted">Every area has two people.</div>}
            </Card>
            <Card title="Where we're strong">
              {o.strong.length ? o.strong.map((s: string) => <div key={s} className="border-b border-[#ececec] py-2.5 text-[14px] last:border-0">{s}</div>) : <div className="text-[14px] text-muted">No area has two available holders yet.</div>}
            </Card>
            <Card title="Where we lose">
              {o.lose.length ? o.lose.map((l: any, i: number) => (
                <div key={i} className="border-b border-[#ececec] py-2.5 text-[14px] last:border-0">
                  {l.name} leaves week {l.week + 1}
                  <div className="text-[12.5px] text-muted">{l.area}: {l.landmines} don&apos;ts, {l.recurring_tasks} recurring tasks stall</div>
                </div>
              )) : <div className="text-[14px] text-muted">No assigned holder leaves during the project.</div>}
            </Card>
          </div>
          <div className="mt-3 text-[12.5px] text-muted">
            Model: {Math.round(r.assumptions.unplanned_absence_per_month * 100)}% chance per person per month of a 1–3 week absence (same for everyone); a learner can cover an area after {r.assumptions.transfer_weeks} weeks next to a holder, or {r.assumptions.self_study_weeks} weeks from Keepline&apos;s receipts. A recommendation for a manager to approve; never used to judge individuals.
          </div>
          <div className="mt-4 w-[420px]"><DecisionCard /></div>
        </>
      )}
    </>
  );
}
