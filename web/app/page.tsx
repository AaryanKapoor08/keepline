"use client";
import { motion } from "motion/react";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, CalendarClock, KeyRound, TriangleAlert, Building2 } from "lucide-react";
import { useData } from "@/lib/data";
import { Badge, LiveDot, Ticker } from "@/components/ui";

// Demo clock: Friday 2026-09-04 16:00 Halifax; Sarah's last day ends 2026-09-11 17:00.
const START = new Date("2026-09-04T16:00:00-03:00").getTime();
const END = new Date("2026-09-11T17:00:00-03:00").getTime();

function Countdown() {
  const [t0] = useState(() => Date.now());
  const [now, setNow] = useState(0);
  useEffect(() => {
    const i = setInterval(() => setNow(Date.now() - t0), 1000);
    return () => clearInterval(i);
  }, [t0]);
  const left = Math.max(0, END - (START + now));
  const d = Math.floor(left / 864e5);
  const h = Math.floor((left % 864e5) / 36e5);
  const m = Math.floor((left % 36e5) / 6e4);
  const s = Math.floor((left % 6e4) / 1e3);
  const cell = (v: number, l: string) => (
    <div className="flex flex-col items-center">
      <div className="w-[76px] rounded-xl border border-alarm/25 bg-alarm/[0.06] py-2 text-center font-mono text-[38px] font-semibold tabular-nums text-fg">
        {String(v).padStart(2, "0")}
      </div>
      <div className="mt-1.5 text-[11px] uppercase tracking-[0.2em] text-dim">{l}</div>
    </div>
  );
  return (
    <div className="flex gap-3">
      {cell(d, "days")}
      {cell(h, "hours")}
      {cell(m, "min")}
      {cell(s, "sec")}
    </div>
  );
}

export default function Home() {
  const { data: meta, live } = useData("/meta", "meta");
  const { data: whatif } = useData("/whatif/sarah", "whatif_sarah");
  const counts = whatif?.break_counts ?? {};
  return (
    <div className="relative -mx-8 -mt-9 min-h-[calc(100vh-10px)] overflow-hidden px-10 pt-16">
      {/* spotlight + grid */}
      <div className="grid-bg pointer-events-none absolute inset-0" />

      <div className="relative mx-auto max-w-[1180px]">
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-3">
          <Badge tone="accent"><Building2 className="h-3 w-3" /> Harbourline Credit Union · Halifax</Badge>
          <Badge>Friday, Sep 4 2026</Badge>
          <LiveDot live={live} />
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
          className="mt-7 max-w-[980px] text-[68px] font-semibold leading-[1.02] tracking-[-0.035em] text-gradient"
        >
          When Sarah leaves Friday,<br />
          <span className="text-fg/60">what breaks </span>
          <span className="text-alarm">Monday?</span>
        </motion.h1>

        <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }} className="mt-5 max-w-[680px] text-[18px] leading-relaxed text-muted">
          Keepline turns Slack, email and tickets into a versioned, receipt-backed company memory, then shows what your
          company is about to forget and saves it before the last day.
        </motion.p>

        <div className="mt-11 grid grid-cols-[1.15fr_1fr] gap-6">
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }} className="glass relative overflow-hidden rounded-2xl border-alarm/25 p-6">
            <div className="flex items-center gap-4">
              <div className="pulse-alarm flex h-14 w-14 items-center justify-center rounded-full border border-alarm/40 bg-alarm/15 text-[18px] font-semibold">SC</div>
              <div className="flex-1">
                <div className="text-[20px] font-semibold">Sarah Chen</div>
                <div className="text-[14px] text-muted">Senior Backend Engineer · 6 months of receipts</div>
              </div>
              <Badge tone="alarm"><CalendarClock className="h-3 w-3" /> Last day Fri Sep 11</Badge>
            </div>
            <div className="mt-6">
              <div className="mb-3 text-[12px] uppercase tracking-[0.18em] text-dim">Time until her knowledge walks out</div>
              <Countdown />
            </div>
            <div className="mt-6 flex flex-wrap gap-2">
              {(meta?.sarah_orphaned_areas ?? ["reconciliation", "corelink_api", "ssl_dns"]).map((a: string) => (
                <Badge key={a} tone="alarm">Bus factor 1 · {meta?.areas?.find((x: { id: string; name: string }) => x.id === a)?.name ?? a}</Badge>
              ))}
            </div>
          </motion.div>

          <div className="grid grid-cols-2 gap-4">
            {[
              { v: meta?.n_docs, l: "receipts ingested", sub: meta?.n_corpus ? `of ${meta.n_corpus.toLocaleString()} messages · private DMs excluded` : "Slack · email · tickets · docs", tone: "text-fg" },
              { v: meta?.n_facts, l: "facts in versioned memory", sub: `${meta?.n_superseded ?? 0} superseded, kept with history`, tone: "text-fg" },
              { v: whatif?.breaks?.length, l: "things only Sarah knows", sub: "orphaned the day she leaves", tone: "text-alarm" },
              { v: counts.orphaned_landmine, l: "landmines she carries", sub: "\"never do X\" rules, with receipts", tone: "text-alarm", icon: true },
            ].map((s, i) => (
              <motion.div key={i} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.45 + i * 0.08 }} className="glass rounded-2xl p-5">
                <div className={`text-[44px] font-semibold leading-none tracking-tight ${s.tone}`}>
                  {s.v != null ? <Ticker value={s.v} /> : "—"}
                </div>
                <div className="mt-2 flex items-center gap-1.5 text-[14px] text-fg/85">
                  {s.icon && <TriangleAlert className="h-3.5 w-3.5 text-alarm" />}
                  {s.l}
                </div>
                <div className="mt-1 text-[12px] text-dim">{s.sub}</div>
              </motion.div>
            ))}
          </div>
        </div>

        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1 }} className="mt-10 flex items-center justify-between border-t border-line pt-6">
          <div className="flex items-center gap-6 text-[13px] text-muted">
            <span className="flex items-center gap-2"><KeyRound className="h-4 w-4 text-alarm" /> {counts.sole_access ?? 0} sole-access systems</span>
            <span>{counts.vendor_contact_lost ?? 0} vendor contacts only she holds</span>
            <span>{counts.unowned_recurring_task ?? 0} recurring tasks with no other owner</span>
          </div>
          <Link href="/graph" className="group flex items-center gap-2 rounded-full border border-accent/30 bg-accent/10 px-5 py-2.5 text-[14px] font-medium text-accent transition hover:bg-accent/20">
            See what Keepline captured <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
          </Link>
        </motion.div>
      </div>
    </div>
  );
}
