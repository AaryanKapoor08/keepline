"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { postJSON, snapshot, normQ, nearest, pname, first } from "@/lib/data";
import { PageTop, Card, Quote, Details, Avatar, PersonPill, Fade } from "@/components/kit";
import { cn } from "@/components/ui";

const ASKS = [
  { label: "Which days does the recon job skip?", q: "Which days does the nightly reconciliation job skip?" },
  { label: "Can I rotate the CoreLink key on a Friday?", q: "Is it safe to rotate the CoreLink API key on a Friday?" },
  { label: "What's our recovery time if the NAS dies?", q: "What is our recovery time objective if the NAS dies?" },
];

function shortAnswer(a: any): string {
  if (!a) return "";
  if (a.action !== "answer") return `I don't know. Ask ${pname(a.route_to?.[0])}.`;
  let t: string = a.text ?? "";
  const i = t.indexOf(" Per ");
  if (i > 0) t = t.slice(0, i);
  else t = t.replace(/^Per [^:]+:\s*/, "");
  return t.replace(/\s*\((Current|This)[^)]*\)\.?/g, "").replace(/--/g, "—").trim();
}

async function askQ(q: string) {
  let a = await postJSON("/ask", { question: q, asker_id: "alex" });
  if (!a) {
    const table = (await snapshot("answers")) ?? {};
    a = table[normQ(q)] ?? nearest(q, table);
  }
  return a;
}

export default function AskPage() {
  const [a, setA] = useState<any>(null);
  const [asked, setAsked] = useState(ASKS[0].label);
  const [src, setSrc] = useState(false);
  const [own, setOwn] = useState(false);
  const [q, setQ] = useState("");
  const [pinged, setPinged] = useState(false);
  const run = async (question: string, label?: string) => {
    setAsked(label ?? question);
    setSrc(false);
    setPinged(false);
    setA(await askQ(question));
  };
  useEffect(() => {
    run(ASKS[0].q, ASKS[0].label);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const cur = a?.said?.find((c: any) => c.is_current !== false) ?? a?.said?.[0];
  const routed = a && a.action !== "answer";

  return (
    <>
      <PageTop title="Good morning, Alex." action={own ? "Close" : "Ask your own question"} onAction={() => setOwn(!own)} />
      <div className="grid grid-cols-[360px_1fr] gap-4">
        <Card title="Questions">
          <div className="flex items-center gap-3 pb-4">
            <Avatar id="alex" size={40} />
            <div className="text-[14px] leading-snug text-muted">Alex Rivera, first week.<br />Sarah left on Friday.</div>
          </div>
          <div className="space-y-2">
            {ASKS.map((x) => (
              <button key={x.q} onClick={() => run(x.q, x.label)} className={cn("w-full rounded-[16px] px-4 py-3.5 text-left text-[15px] transition-colors", asked === x.label ? "bg-[#111] text-white" : "bg-[#f4f5f7] hover:bg-[#ececef]")}>
                {x.label}
              </button>
            ))}
          </div>
          <Fade show={own} className="mt-4">
            <form onSubmit={(e) => { e.preventDefault(); if (q.trim()) run(q); }}>
              <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Type a question, press Enter" className="h-12 w-full rounded-full bg-[#f4f5f7] px-5 text-[15px] outline-none placeholder:text-dim focus:ring-2 focus:ring-black/10" />
            </form>
          </Fade>
        </Card>

        <Card title="Answer" right={a?.action === "answer" ? <Details onClick={() => setSrc(!src)} open={src}>{src ? "Hide source" : "Show source"}</Details> : null}>
          <AnimatePresence mode="wait">
            {a && (
              <motion.div key={asked} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.45 }}>
                <div className="text-[14px] text-muted">{asked}</div>
                <div className="mt-3 text-[32px] font-medium leading-[1.2] tracking-[-0.015em]">{shortAnswer(a)}</div>
                {!routed && cur && (
                  <div className="mt-5 text-[15px] text-muted">
                    &ldquo;{cur.quote}&rdquo; — {cur.author ?? pname(cur.author_id)}
                  </div>
                )}
                {routed && (
                  <div className="mt-6 flex items-center gap-3">
                    {a.route_to?.[0] && <PersonPill id={a.route_to[0]} note="worked on this" />}
                    {!pinged ? (
                      <button onClick={() => setPinged(true)} className="btn-primary !h-11">Ask {first(a.route_to?.[0])}</button>
                    ) : (
                      <span className="text-[15px] text-muted">Sent to {first(a.route_to?.[0])} in Slack.</span>
                    )}
                  </div>
                )}
                <Fade show={src && !routed} className="mt-6 space-y-3">
                  {(a.said ?? []).slice(0, 2).map((c: any, i: number) => (
                    <div key={i} className={cn("rounded-[16px] bg-[#f4f5f7] p-4", c.is_current === false && "opacity-60")}>
                      <Quote c={c} small />
                      {c.is_current === false && <div className="mt-2 text-[13px] text-muted">Replaced by a newer message. Kept on record.</div>}
                    </div>
                  ))}
                </Fade>
              </motion.div>
            )}
          </AnimatePresence>
        </Card>
      </div>
    </>
  );
}
