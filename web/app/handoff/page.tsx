"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Check, Loader2, KeyRound, TriangleAlert, Repeat, UserX, Ticket, Scale, Users, UserCheck, PenLine, FileSignature } from "lucide-react";
import { useData, first, postJSON, fmtDate } from "@/lib/data";
import { Badge, Expandable, LiveDot, PageHeader, Receipt, cn } from "@/components/ui";

const SECTIONS: Record<string, { label: string; icon: any; tone: string; span?: string }> = {
  landmines: { label: "Landmines", icon: TriangleAlert, tone: "text-alarm", span: "col-span-2 row-span-2" },
  access: { label: "Access & credentials", icon: KeyRound, tone: "text-accent", span: "row-span-2" },
  recurring_tasks: { label: "Recurring tasks", icon: Repeat, tone: "text-accent", span: "row-span-2" },
  vendor_contacts: { label: "Vendor contacts", icon: UserX, tone: "text-muted" },
  unresolved_work: { label: "Open tickets", icon: Ticket, tone: "text-accent" },
  decisions: { label: "Decisions & why", icon: Scale, tone: "text-muted" },
  suggested_owners: { label: "Suggested owners", icon: UserCheck, tone: "text-muted" },
  key_links_people: { label: "Key people", icon: Users, tone: "text-muted" },
};

export default function HandoffPage() {
  const { data: pack, live } = useData("/handoff/sarah", "handoff_sarah");
  const [step, setStep] = useState(0);
  const [signed, setSigned] = useState(false);
  const items: any[] = pack?.items ?? [];
  const cnt = (s: string) => items.filter((i) => i.section === s).length;
  const steps = pack
    ? [
        `Scanning ${pack.n_receipts_scanned?.toLocaleString() ?? "all"} receipts`,
        `${cnt("access")} access items`,
        `${cnt("landmines")} landmines`,
        `${cnt("unresolved_work")} open tickets`,
        `${cnt("recurring_tasks")} recurring tasks · ${cnt("vendor_contacts")} vendor contacts`,
        `Suggested owners for every area`,
      ]
    : [];
  const done = step >= steps.length && steps.length > 0;

  useEffect(() => {
    if (!pack || step >= steps.length) return;
    const t = setTimeout(() => setStep((s) => s + 1), step === 0 ? 700 : 420);
    return () => clearTimeout(t);
  }, [pack, step, steps.length]);

  const sign = async () => {
    setSigned(true);
    await postJSON("/handoff/sarah/signoff", {});
  };

  const order = ["landmines", "access", "recurring_tasks", "vendor_contacts", "unresolved_work", "decisions", "suggested_owners", "key_links_people"];

  return (
    <div>
      <PageHeader
        eyebrow="05 · Handoff pack"
        title="Sarah's handoff pack, written from her own receipts"
        sub={<>Generated {fmtDate("2026-09-04")}, one week before her last day. She confirms, corrects or removes each item, then signs off.</>}
        right={
          <div className="flex items-center gap-3">
            <LiveDot live={live} />
            <button onClick={() => setStep(0)} className="rounded-full border border-line px-3 py-1.5 text-[13px] text-muted hover:text-fg">Regenerate</button>
          </div>
        }
      />

      <AnimatePresence mode="wait">
        {!done ? (
          <motion.div key="loader" exit={{ opacity: 0, scale: 0.98 }} className="glass mx-auto mt-10 max-w-[560px] rounded-2xl p-8">
            <div className="mb-5 flex items-center gap-2 text-[13px] text-muted"><Loader2 className="h-4 w-4 animate-spin text-accent" /> Building handoff pack for Sarah Chen</div>
            <div className="space-y-3.5">
              {steps.map((s, i) => (
                <motion.div key={i} initial={{ opacity: 0.25 }} animate={{ opacity: i <= step ? 1 : 0.25 }} className="flex items-center gap-3 text-[16px]">
                  <span className={cn("flex h-6 w-6 items-center justify-center rounded-full border", i < step ? "border-accent bg-accent/20 text-accent" : i === step ? "border-accent/60 text-accent" : "border-line text-dim")}>
                    {i < step ? <Check className="h-3.5 w-3.5" /> : i === step ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                  </span>
                  <span className={i < step ? "text-fg" : "text-muted"}>{s}</span>
                </motion.div>
              ))}
            </div>
          </motion.div>
        ) : (
          <motion.div key="pack" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            <div className="grid auto-rows-[minmax(150px,auto)] grid-cols-4 gap-4">
              {order.filter((s) => cnt(s) > 0).map((s, si) => {
                const m = SECTIONS[s] ?? { label: s, icon: PenLine, tone: "text-muted" };
                const I = m.icon;
                const its = items.filter((i) => i.section === s);
                const lim = s === "landmines" ? 6 : m.span?.includes("row-span-2") ? 5 : 3;
                return (
                  <motion.div key={s} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: si * 0.06 }} className={cn("glass glass-hover overflow-hidden rounded-2xl p-4", m.span, s === "landmines" && "border-alarm/30")}>
                    <div className="mb-3 flex items-center justify-between">
                      <div className={cn("flex items-center gap-2 text-[13px] font-semibold", m.tone)}><I className="h-4 w-4" /> {m.label}</div>
                      <span className="font-mono text-[12px] text-dim">{its.length}</span>
                    </div>
                    <div className="space-y-2">
                      {its.slice(0, lim).map((it, i) => (
                        <div key={i} className="rounded-xl border border-line bg-black/20 p-2.5">
                          <Expandable
                            head={
                              <div>
                                <div className="text-[13px] leading-snug">{it.title}</div>
                                <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-dim">
                                  {it.suggested_owner_id && <Badge tone="ok">→ {first(it.suggested_owner_id)}</Badge>}
                                  {it.citations?.length > 0 && <span>{it.citations.length} receipt{it.citations.length > 1 ? "s" : ""}</span>}
                                  <span className={signed ? "text-ok" : ""}>{signed ? "confirmed" : "pending review"}</span>
                                </div>
                              </div>
                            }
                          >
                            <div className="space-y-2">
                              {it.detail && <div className="text-[12px] text-muted">{it.detail}</div>}
                              {(it.citations ?? []).slice(0, 2).map((c: any, j: number) => <Receipt key={j} c={c} compact />)}
                            </div>
                          </Expandable>
                        </div>
                      ))}
                    </div>
                  </motion.div>
                );
              })}
            </div>

            <div className="mt-5 flex items-center justify-between rounded-2xl border border-line bg-white/[0.02] p-5">
              <div>
                <div className="text-[15px] font-medium">{items.length} items · {pack.gaps?.length ?? 0} gap-interview questions before Sep 11</div>
                <div className="text-[13px] text-dim">Nothing is shared until Sarah signs. She can correct any line.</div>
              </div>
              <div className="relative">
                <AnimatePresence mode="wait">
                  {!signed ? (
                    <motion.button key="b" exit={{ opacity: 0, scale: 0.9 }} onClick={sign} className="flex items-center gap-2 rounded-full bg-accent px-6 py-3 text-[15px] font-semibold text-bg transition hover:brightness-110">
                      <FileSignature className="h-4 w-4" /> Sarah signs off
                    </motion.button>
                  ) : (
                    <motion.div key="s" initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: 1, scale: 1 }} transition={{ type: "spring", stiffness: 300, damping: 16 }} className="flex items-center gap-3 rounded-full border border-ok/40 bg-ok/10 px-5 py-2.5 text-ok">
                      <motion.span initial={{ rotate: -90 }} animate={{ rotate: 0 }} className="flex h-7 w-7 items-center justify-center rounded-full bg-ok text-bg"><Check className="h-4 w-4" strokeWidth={3} /></motion.span>
                      <div>
                        <div className="text-[14px] font-semibold">Signed by Sarah Chen</div>
                        <div className="font-mono text-[11px] opacity-80">handed to Aisha & Alex · receipts attached</div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
