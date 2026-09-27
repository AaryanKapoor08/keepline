"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState } from "react";
import { AnimatePresence, LayoutGroup, motion } from "motion/react";
import { KeyRound, TriangleAlert, Repeat, UserX, Timer, Users } from "lucide-react";
import { useData, first, riskColor, riskLevel, fmtDate } from "@/lib/data";
import { Badge, LiveDot, PageHeader, Ticker, cn } from "@/components/ui";

const BREAK_META: Record<string, { label: string; icon: any; tone: string }> = {
  sole_access: { label: "Sole access lost", icon: KeyRound, tone: "text-alarm" },
  orphaned_landmine: { label: "Landmines nobody else knows", icon: TriangleAlert, tone: "text-alarm" },
  vendor_contact_lost: { label: "Vendor contacts lost", icon: UserX, tone: "text-muted" },
  unowned_recurring_task: { label: "Recurring tasks with no owner", icon: Repeat, tone: "text-muted" },
};

export default function RiskPage() {
  const risk = useData("/risk", "risk");
  const wi = useData("/whatif/sarah", "whatif_sarah");
  const [sim, setSim] = useState(false);
  const base: any[] = risk.data ?? [];
  const afterMap: Record<string, any> = Object.fromEntries((wi.data?.after ?? []).map((r: any) => [r.area_id, r]));
  const rows = base
    .map((r) => {
      const a = sim ? afterMap[r.area_id] ?? r : r;
      return { ...r, cur: a };
    })
    .sort((x, y) => y.cur.risk - x.cur.risk);
  const orphaned = new Set<string>(wi.data?.orphaned_areas ?? []);
  const breaks: any[] = wi.data?.breaks ?? [];
  const groups: Record<string, any[]> = {};
  for (const b of breaks) (groups[b.type] ??= []).push(b);

  return (
    <div>
      <PageHeader
        eyebrow="04 · Risk map"
        title="Where knowledge is one person deep"
        sub={<>risk = importance × (1 − redundancy) × departure likelihood. Redundancy comes from evidence (closed tickets weigh more than chatter), not job titles.</>}
        right={
          <div className="flex items-center gap-4">
            <LiveDot live={risk.live} />
            <button onClick={() => setSim(!sim)} className={cn("relative flex items-center gap-3 rounded-full border px-4 py-2 text-[14px] font-medium transition", sim ? "border-alarm/50 bg-alarm/15 text-alarm shadow-[0_0_30px_-6px_rgba(255,77,94,0.6)]" : "border-line bg-white/[0.03] text-fg hover:border-alarm/40")}>
              <span className={cn("relative h-5 w-9 rounded-full transition", sim ? "bg-alarm/60" : "bg-white/10")}>
                <motion.span layout className={cn("absolute top-0.5 h-4 w-4 rounded-full bg-white", sim ? "left-[18px]" : "left-0.5")} />
              </span>
              Simulate Sarah&apos;s departure
            </button>
          </div>
        }
      />

      <div className={cn("grid gap-5 transition-all", sim ? "grid-cols-[1fr_400px]" : "grid-cols-1")}>
        <LayoutGroup>
          <div className={cn("grid gap-3", sim ? "grid-cols-2" : "grid-cols-5")}>
            {rows.map((r, i) => {
              const c = r.cur;
              const col = riskColor(c.risk);
              const orph = sim && orphaned.has(r.area_id);
              return (
                <motion.div
                  layout
                  key={r.area_id}
                  transition={{ type: "spring", stiffness: 260, damping: 30 }}
                  className={cn("glass relative overflow-hidden rounded-2xl p-4", i < 2 && !sim && "row-span-1")}
                  style={{ borderColor: c.risk >= 0.35 ? `${col}55` : undefined, boxShadow: c.risk >= 0.6 ? `0 0 40px -12px ${col}` : undefined }}
                >
                  <motion.div className="absolute inset-x-0 top-0 h-[3px]" animate={{ background: col, width: `${Math.max(6, c.risk * 100)}%` }} transition={{ duration: 0.8 }} />
                  <div className="flex items-start justify-between gap-2">
                    <div className="text-[14px] font-medium leading-snug">{r.area_name}</div>
                    <motion.div key={c.risk} initial={{ scale: 1.3 }} animate={{ scale: 1 }} className="font-mono text-[22px] font-semibold tabular-nums" style={{ color: col }}>
                      {Math.round(c.risk * 100)}
                    </motion.div>
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5">
                    <Badge tone={c.risk >= 0.35 ? "alarm" : c.risk >= 0.15 ? "warn" : "accent"}>{riskLevel(c.risk)}</Badge>
                    <span className={cn("inline-flex items-center gap-1 text-[12px]", c.bus_factor <= 1 ? "text-alarm" : "text-muted")}>
                      <Users className="h-3 w-3" /> bus factor <motion.b key={c.bus_factor} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>{c.bus_factor}</motion.b>
                    </span>
                  </div>
                  <AnimatePresence>
                    {orph && (
                      <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="mt-2 rounded-md border border-alarm/40 bg-alarm/10 px-2 py-1 font-mono text-[11px] font-semibold tracking-wider text-alarm">
                        ORPHANED · NOBODY LEFT WHO KNOWS THIS
                      </motion.div>
                    )}
                  </AnimatePresence>
                  <div className="mt-3 space-y-1 text-[12px] text-dim">
                    {r.countdown_days != null && r.at_risk_person_id && (
                      <div className="flex items-center gap-1.5"><Timer className="h-3 w-3" /> {first(r.at_risk_person_id)} leaves in <span className="text-fg">{r.countdown_days}d</span></div>
                    )}
                    <div>{r.n_landmines} landmines · {r.n_facts} facts</div>
                    <div className="truncate">experts: {(c.experts ?? []).slice(0, 3).map((e: any) => first(e[0])).join(", ") || "none"}</div>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </LayoutGroup>

        <AnimatePresence>
          {sim && (
            <motion.div initial={{ opacity: 0, x: 30 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 30 }} className="glass flex max-h-[640px] flex-col rounded-2xl border-alarm/30 p-5">
              <div className="text-[12px] uppercase tracking-[0.16em] text-alarm">What breaks on Monday, Sep 14</div>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-[48px] font-semibold leading-none text-alarm"><Ticker value={breaks.length} duration={1} /></span>
                <span className="text-[14px] text-muted">things only Sarah knows</span>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2">
                {Object.entries(BREAK_META).map(([k, m]) => {
                  const I = m.icon;
                  return (
                    <div key={k} className="rounded-lg border border-line bg-black/25 p-2">
                      <div className={cn("flex items-center gap-1.5 text-[18px] font-semibold", m.tone)}><I className="h-4 w-4" /> {groups[k]?.length ?? 0}</div>
                      <div className="text-[11px] text-dim">{m.label}</div>
                    </div>
                  );
                })}
              </div>
              <div className="mt-4 flex-1 space-y-2 overflow-y-auto pr-1">
                {["sole_access", "orphaned_landmine", "vendor_contact_lost", "unowned_recurring_task"].flatMap((k) => (groups[k] ?? []).slice(0, k === "unowned_recurring_task" ? 3 : 4)).map((b, i) => {
                  const m = BREAK_META[b.type];
                  const I = m.icon;
                  return (
                    <motion.div key={i} initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.25 + i * 0.05 }} className="rounded-xl border border-line bg-black/25 p-3">
                      <div className={cn("flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider", m.tone)}><I className="h-3 w-3" /> {m.label}</div>
                      <div className="mt-1 text-[13px] leading-snug">{b.text}</div>
                      <div className="mt-1 text-[11px] text-dim">{b.area_name} · {b.stated_by_name} · {fmtDate(b.date)} · <span className="font-mono">{b.doc_id}</span></div>
                    </motion.div>
                  );
                })}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
