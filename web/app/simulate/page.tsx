"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { postJSON, snapshot, normQ, nearest, first, fmtDate } from "@/lib/data";
import { PageTop, Card, Quote, Details, Fade, PersonPill } from "@/components/kit";
import { cn } from "@/components/ui";

const DECISIONS = [
  "Rotate the CoreLink API key this Friday",
  "Run the reconciliation job manually on the 15th",
  "Restore last night's backup onto the replication primary",
];

async function check(t: string) {
  let r = await postJSON("/decision", { text: t });
  if (!r) {
    const table = (await snapshot("decisions")) ?? {};
    r = table[normQ(t)] ?? nearest(t, table);
  }
  return r;
}

export default function SimulatePage() {
  const [text, setText] = useState(DECISIONS[0]);
  const [r, setR] = useState<any>(null);
  const [why, setWhy] = useState(false);
  const run = async (t: string) => {
    setText(t);
    setWhy(false);
    setR(await check(t));
  };
  useEffect(() => {
    run(DECISIONS[0]);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const top = r?.conflicts?.[0];
  const verdict = r?.verdict === "conflict" ? `Conflicts with a rule ${first(top?.stated_by)} set.` : r?.verdict === "caution" ? `Check first. ${first(top?.stated_by)} left a related rule.` : "No conflicts on record.";
  return (
    <>
      <PageTop title="Check a decision before you make it." action="Check decision" onAction={() => run(text)} />
      <div className="grid grid-cols-[360px_1fr] gap-4">
        <Card title="Proposed change">
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} className="w-full resize-none rounded-[16px] bg-[#f4f5f7] p-4 text-[16px] leading-snug outline-none focus:ring-2 focus:ring-black/10" />
          <div className="mt-4 text-[13px] text-muted">Try another</div>
          <div className="mt-2 space-y-2">
            {DECISIONS.map((d) => (
              <button key={d} onClick={() => run(d)} className={cn("w-full rounded-[14px] px-4 py-3 text-left text-[14px] transition-colors", r?.proposal === d ? "bg-[#111] text-white" : "bg-[#f4f5f7] hover:bg-[#ececef]")}>{d}</button>
            ))}
          </div>
        </Card>
        <Card title="Result" right={top ? <Details onClick={() => setWhy(!why)} open={why}>{why ? "Hide" : "Why"}</Details> : null}>
          <AnimatePresence mode="wait">
            {r && (
              <motion.div key={r.proposal} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                <div className="text-[14px] text-muted">{r.proposal}{r.target_dates?.[0] ? ` · ${fmtDate(r.target_dates[0])}` : ""}</div>
                <div className="mt-3 flex items-center gap-3 text-[34px] font-medium leading-tight tracking-[-0.015em]">
                  {r.verdict === "conflict" && <span className="h-3 w-3 shrink-0 rounded-full bg-alarm" />}
                  {verdict}
                </div>
                {r.suggested_reviewer && (
                  <div className="mt-5 flex items-center gap-3 text-[14px] text-muted">
                    Suggested reviewer <PersonPill id={r.suggested_reviewer} />
                  </div>
                )}
                <Fade show={why && !!top} className="mt-6 rounded-[18px] bg-[#f4f5f7] p-5">
                  {top && (
                    <>
                      {top.why && <div className="mb-2 text-[13px] text-muted">{top.why}</div>}
                      <Quote c={top} />
                    </>
                  )}
                </Fade>
              </motion.div>
            )}
          </AnimatePresence>
        </Card>
      </div>
    </>
  );
}
