"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Check, X } from "lucide-react";
import { useData, pname } from "@/lib/data";
import { PageTop, Card, Quote, EASE } from "@/components/kit";
import { cn } from "@/components/ui";

const CARDS = [
  { s: "access", t: "Access" },
  { s: "vendor_contacts", t: "Vendor contacts" },
  { s: "recurring_tasks", t: "Recurring tasks" },
  { s: "landmines", t: "Landmines" },
  { s: "unresolved_work", t: "Open work" },
  { s: "suggested_owners", t: "Suggested owners" },
];

export default function HandoffPage() {
  const { data: pack } = useData("/handoff/sarah", "handoff_sarah");
  const [stage, setStage] = useState<0 | 1 | 2>(0);
  const [open, setOpen] = useState<string | null>(null);
  const [signed, setSigned] = useState(false);
  const items: any[] = pack?.items ?? [];
  const of = (s: string) => items.filter((i) => i.section === s);
  const card = CARDS.find((c) => c.s === open);
  const act = () => {
    if (stage === 0) {
      setStage(1);
      setTimeout(() => setStage(2), 900);
    } else if (stage === 2) setSigned(true);
  };
  return (
    <>
      <PageTop
        title="Her handoff pack, written for her."
        action={stage < 2 ? (stage === 1 ? "Generating…" : "Generate handoff pack") : signed ? <><Check className="h-4 w-4" /> Signed by Sarah</> : "Sarah signs off"}
        onAction={act}
      />
      {stage < 2 ? (
        <Card className="min-h-[360px] items-center justify-center text-center">
          <div className="text-[19px] text-muted">
            {stage === 1 ? `Reading ${pack?.n_receipts_scanned?.toLocaleString() ?? ""} messages Sarah wrote or was part of…` : "Built from Sarah's own receipts. She checks every line before anyone relies on it."}
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-3 gap-4">
          {CARDS.map((c, i) => (
            <motion.button
              key={c.s}
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.07, duration: 0.6, ease: EASE }}
              onClick={() => setOpen(c.s)}
              className={cn("flex h-[200px] flex-col justify-between rounded-[24px] p-6 text-left transition-transform hover:-translate-y-0.5", c.s === "landmines" ? "bg-[#111] text-white" : "bg-white")}
            >
              <div className="flex items-center justify-between">
                <span className="text-[19px] font-medium">{c.t}</span>
                <span className={cn("rounded-full border px-3 py-1 text-[13px]", c.s === "landmines" ? "border-white/20" : "border-[#e5e5ea]")}>Open ›</span>
              </div>
              <div className="flex items-end gap-3">
                <span className={cn("text-[56px] font-medium leading-none tracking-[-0.03em]", c.s === "landmines" && "text-alarm")}>{of(c.s).length}</span>
                <span className={cn("pb-1 text-[14px]", c.s === "landmines" ? "text-white/60" : "text-muted")}>{signed ? "confirmed" : "to review"}</span>
              </div>
            </motion.button>
          ))}
        </div>
      )}

      <AnimatePresence>
        {card && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[60] flex justify-end bg-black/20" onClick={() => setOpen(null)}>
            <motion.div initial={{ x: 40, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 40, opacity: 0 }} transition={{ duration: 0.45, ease: EASE }} onClick={(e) => e.stopPropagation()} className="m-4 w-[560px] overflow-y-auto rounded-[28px] bg-white p-8">
              <div className="flex items-center justify-between">
                <div className="text-[28px] font-medium">{card.t}</div>
                <button onClick={() => setOpen(null)} className="flex h-10 w-10 items-center justify-center rounded-full bg-[#f4f5f7]"><X className="h-4 w-4" /></button>
              </div>
              <div className="mt-4 divide-y divide-[#ececec]">
                {of(card.s).slice(0, 10).map((it, i) => (
                  <div key={i} className="py-4">
                    <div className="text-[16px] font-medium leading-snug">{it.title}</div>
                    {it.suggested_owner_id && <div className="mt-1 text-[14px] text-muted">Suggested owner: {pname(it.suggested_owner_id)}</div>}
                    {it.citations?.[0] && (
                      <div className="mt-3 rounded-[16px] bg-[#f4f5f7] p-4">
                        <Quote c={it.citations[0]} small />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
