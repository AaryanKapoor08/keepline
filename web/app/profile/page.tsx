"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { motion } from "motion/react";
import { ShieldCheck, Eye, HelpCircle, Hash, Mail, Ticket, FileText, CheckCircle2, Clock } from "lucide-react";
import { useData, KIND_COLOR, KIND_LABEL, fmtDate, pname } from "@/lib/data";
import { Badge, Card, LiveDot, PageHeader, Ring, Ticker, cn } from "@/components/ui";

const SRC_ICON: Record<string, any> = { slack: Hash, email: Mail, ticket: Ticket, doc: FileText };

export default function ProfilePage() {
  const { data: p, live } = useData("/profile/sarah", "profile_sarah");
  if (!p) return <div className="text-muted">Loading…</div>;
  const kinds = Object.entries(p.kinds as Record<string, number>).filter(([k]) => k !== "fact").sort((a, b) => b[1] - a[1]);
  const srcTotal = Object.values(p.sources as Record<string, number>).reduce((a, b) => a + b, 0) || 1;
  const approved = (p.review?.approved ?? 0) + (p.review?.corrected ?? 0);
  const pending = p.review?.pending ?? 0;
  return (
    <div>
      <PageHeader
        eyebrow="03 · Knowledge profile"
        title={<>What Keepline captured from Sarah</>}
        sub="Receipts, not a clone. Every item links back to something Sarah actually wrote. She reviews all of it before anyone else can rely on it, and none of it is ever used in performance reviews."
        right={<LiveDot live={live} />}
      />

      <div className="grid grid-cols-4 gap-4">
        <Card className="col-span-1 p-5">
          <div className="flex items-center gap-2 text-[12px] uppercase tracking-[0.16em] text-accent"><ShieldCheck className="h-4 w-4" /> Consent</div>
          <div className="mt-3 text-[17px] font-semibold leading-snug">Sarah reviews everything here.</div>
          <div className="mt-3 space-y-1.5 text-[13px] text-muted">
            <div className="flex items-center gap-2"><Eye className="h-3.5 w-3.5 text-accent" /> DMs excluded by default</div>
            <div className="flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-accent" /> Approve, correct or remove any item</div>
            <div className="flex items-center gap-2"><ShieldCheck className="h-3.5 w-3.5 text-accent" /> Never tied to performance</div>
          </div>
        </Card>
        {[
          { v: p.n_facts, l: "facts captured", s: `${p.n_current} still current` },
          { v: pending, l: "awaiting her review", s: `${approved} approved so far`, warn: true },
          { v: p.n_questions_answered, l: "questions answered from her receipts", s: `helped ${p.helped_people} ${p.helped_people === 1 ? "person" : "people"} so far` },
        ].map((s, i) => (
          <Card key={i} delay={0.05 * (i + 1)} className="p-5">
            <div className={cn("text-[42px] font-semibold leading-none tracking-tight", s.warn && "text-warn")}><Ticker value={s.v ?? 0} /></div>
            <div className="mt-2 text-[14px]">{s.l}</div>
            <div className="mt-1 text-[12px] text-dim">{s.s}</div>
          </Card>
        ))}
      </div>

      <div className="mt-4 grid grid-cols-[1.5fr_1fr] gap-4">
        <Card delay={0.15} className="p-5">
          <div className="mb-4 flex items-center justify-between">
            <div className="text-[12px] uppercase tracking-[0.16em] text-dim">Coverage by area</div>
            <div className="text-[12px] text-dim">ring = strength of evidence she knows it</div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            {p.areas.slice(0, 9).map((a: any, i: number) => (
              <motion.div key={a.area_id} initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.2 + i * 0.04 }} className="flex items-center gap-3 rounded-xl border border-line bg-black/20 p-3">
                <Ring value={a.score} size={52} stroke={5} color={a.score >= 0.7 ? "var(--alarm)" : "var(--accent)"} label={<span className="text-[12px]">{Math.round(a.score * 100)}</span>} />
                <div className="min-w-0">
                  <div className="truncate text-[13px] font-medium">{a.area_name}</div>
                  <div className="text-[11.5px] text-dim">{a.n_facts} facts · {a.n_tickets_closed} tickets closed</div>
                </div>
              </motion.div>
            ))}
          </div>
        </Card>

        <div className="flex flex-col gap-4">
          <Card delay={0.2} className="p-5">
            <div className="mb-3 text-[12px] uppercase tracking-[0.16em] text-dim">Facts by kind</div>
            <div className="space-y-2">
              {kinds.map(([k, v]) => {
                const max = kinds[0][1];
                return (
                  <div key={k} className="flex items-center gap-3 text-[13px]">
                    <span className="w-[110px] text-muted">{KIND_LABEL[k] ?? k}</span>
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/5">
                      <motion.div initial={{ width: 0 }} animate={{ width: `${(v / max) * 100}%` }} transition={{ duration: 1, delay: 0.3 }} className="h-full rounded-full" style={{ background: KIND_COLOR[k] }} />
                    </div>
                    <span className="w-7 text-right font-mono tabular-nums">{v}</span>
                  </div>
                );
              })}
            </div>
          </Card>
          <Card delay={0.25} className="p-5">
            <div className="mb-3 text-[12px] uppercase tracking-[0.16em] text-dim">Receipts by source</div>
            <div className="flex h-3 overflow-hidden rounded-full">
              {Object.entries(p.sources as Record<string, number>).map(([k, v], i) => (
                <motion.div key={k} initial={{ width: 0 }} animate={{ width: `${(v / srcTotal) * 100}%` }} transition={{ duration: 1, delay: 0.3 + i * 0.1 }} style={{ background: ["#2ee6d0", "#4fb3a8", "#6f9a95", "#8a9aa6"][i % 4] }} />
              ))}
            </div>
            <div className="mt-3 grid grid-cols-4 gap-2 text-[12px]">
              {Object.entries(p.sources as Record<string, number>).map(([k, v], i) => {
                const I = SRC_ICON[k] ?? FileText;
                return (
                  <div key={k} className="flex items-center gap-1.5 text-muted">
                    <I className="h-3.5 w-3.5" style={{ color: ["#2ee6d0", "#4fb3a8", "#6f9a95", "#8a9aa6"][i % 4] }} /> {k} <span className="font-mono text-fg">{v}</span>
                  </div>
                );
              })}
            </div>
          </Card>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4">
        <Card delay={0.3} className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-[12px] uppercase tracking-[0.16em] text-dim">Review queue · sample</div>
            <Badge tone="warn"><Clock className="h-3 w-3" /> {pending} pending</Badge>
          </div>
          <div className="space-y-2">
            {p.sample_facts.slice(0, 5).map((f: any) => (
              <div key={f.id} className="flex items-start gap-3 rounded-xl border border-line bg-black/20 p-3">
                <span className={cn("mt-1.5 h-2 w-2 shrink-0", f.kind === "landmine" ? "rotate-45" : "rounded-full")} style={{ background: KIND_COLOR[f.kind] }} />
                <div className="min-w-0 flex-1">
                  <div className="text-[13.5px] leading-snug">{f.text}</div>
                  <div className="mt-1 text-[11.5px] text-dim">{KIND_LABEL[f.kind]} · since {fmtDate(f.valid_from)}</div>
                </div>
                <div className="flex shrink-0 gap-1">
                  <span className="rounded-md border border-ok/30 px-2 py-0.5 text-[11px] text-ok">Approve</span>
                  <span className="rounded-md border border-line px-2 py-0.5 text-[11px] text-muted">Correct</span>
                </div>
              </div>
            ))}
          </div>
        </Card>
        <Card delay={0.35} className="p-5">
          <div className="mb-3 flex items-center gap-2 text-[12px] uppercase tracking-[0.16em] text-dim"><HelpCircle className="h-3.5 w-3.5" /> Gaps still to capture before Sep 11</div>
          <div className="space-y-2">
            {p.gaps.slice(0, 5).map((g: any, i: number) => (
              <div key={i} className="rounded-xl border border-line bg-black/20 p-3">
                <div className="text-[13.5px] leading-snug">{g.question}</div>
                <div className="mt-1.5 flex items-center gap-2 text-[11.5px] text-dim">
                  <Badge tone={g.priority > 0.6 ? "alarm" : "warn"}>priority {g.priority.toFixed(2)}</Badge>
                  <span>{g.reason}</span>
                </div>
              </div>
            ))}
            {!p.gaps.length && <div className="text-[13px] text-muted">No open gaps for {pname("sarah")}.</div>}
          </div>
        </Card>
      </div>
    </div>
  );
}
