"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ArrowUp, Quote, Lightbulb, UserRoundSearch, Send, CircleCheck, CircleSlash, Route } from "lucide-react";
import { postJSON, snapshot, nearest, normQ, pname, first } from "@/lib/data";
import { Badge, PageHeader, Receipt, cn, LiveDot } from "@/components/ui";

const QS = [
  "Which days does the nightly reconciliation job skip?",
  "Is it safe to rotate the CoreLink API key on a Friday?",
  "How does the portal SSL cert get renewed?",
  "What is our recovery time objective if the NAS dies?",
  "Who is our account manager at CoreLink?",
];

function Memo({ text }: { text: string }) {
  return <p className="font-serif text-[20px] leading-[1.55] text-fg">{text}</p>;
}

const ACTION: Record<string, { label: string; tone: any; icon: any }> = {
  answer: { label: "Answer", tone: "accent", icon: CircleCheck },
  abstain: { label: "Abstain", tone: "warn", icon: CircleSlash },
  route: { label: "Route to a person", tone: "blue", icon: Route },
};

export default function AskPage() {
  const [q, setQ] = useState("");
  const [ph, setPh] = useState(0);
  const [vanish, setVanish] = useState(false);
  const [ans, setAns] = useState<any>(null);
  const [asked, setAsked] = useState("");
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState(false);
  const [pinged, setPinged] = useState(false);

  useEffect(() => {
    const i = setInterval(() => setPh((p) => (p + 1) % QS.length), 3000);
    return () => clearInterval(i);
  }, []);

  const ask = async (text: string) => {
    if (!text.trim()) return;
    setVanish(true);
    setBusy(true);
    setPinged(false);
    setAsked(text);
    setTimeout(() => {
      setQ("");
      setVanish(false);
    }, 450);
    let a = await postJSON("/ask", { question: text, asker_id: "alex" });
    setLive(!!a);
    if (!a) {
      const table = (await snapshot("answers")) ?? {};
      a = table[normQ(text)] ?? nearest(text, table);
    }
        setAns(a ?? { action: "abstain", text: "I don't know. That question isn't in the offline snapshot; start the API for live answers.", said: [], inferred: [], confidence: 0 });
    setBusy(false);
  };

  const act = ans ? ACTION[ans.action] ?? ACTION.answer : null;
  const conf = ans?.confidence ?? 0;

  return (
    <div>
      <PageHeader
        eyebrow="06 · Ask · Alex's first week"
        title="Answers with receipts, or “I don't know, ask Mike.”"
        sub="Alex Rivera starts Monday. Every answer shows what was said (quoted, dated, linked), what was inferred (labelled), and when there's no evidence, who to ask instead."
        right={<LiveDot live={live} />}
      />

      <form onSubmit={(e) => { e.preventDefault(); ask(q); }} className="relative mx-auto max-w-[860px]">
        <div className="glass relative flex items-center overflow-hidden rounded-full py-1.5 pl-6 pr-1.5 focus-within:border-accent/40 focus-within:shadow-[0_0_0_4px_rgba(46,230,208,0.08)]">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className={cn("relative z-10 h-12 flex-1 bg-transparent text-[18px] outline-none transition-all duration-400", vanish && "translate-x-6 opacity-0 blur-sm")}
            aria-label="Ask Keepline"
          />
          {!q && !vanish && (
            <AnimatePresence mode="wait">
              <motion.span key={ph} initial={{ y: 10, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: -10, opacity: 0 }} className="pointer-events-none absolute left-6 text-[18px] text-dim">
                {QS[ph]}
              </motion.span>
            </AnimatePresence>
          )}
          <button type="submit" disabled={busy} className="z-10 flex h-11 w-11 items-center justify-center rounded-full bg-accent text-bg transition hover:brightness-110 disabled:opacity-50">
            <ArrowUp className="h-5 w-5" />
          </button>
        </div>
        <div className="mt-3 flex flex-wrap justify-center gap-2">
          {QS.map((s) => (
            <button key={s} type="button" onClick={() => ask(s)} className="rounded-full border border-line bg-white/[0.02] px-3 py-1 text-[12.5px] text-muted transition hover:border-accent/40 hover:text-fg">
              {s}
            </button>
          ))}
        </div>
      </form>

      <div className="mx-auto mt-8 max-w-[1100px]">
        {busy && (
          <div className="flex items-center justify-center gap-2 text-[14px] text-muted">
            Searching versioned memory as of Fri Sep 4
          </div>
        )}
        <AnimatePresence mode="wait">
          {ans && !busy && (
            <motion.div key={asked} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="grid grid-cols-[1fr_280px] gap-5">
              <div className="space-y-4">
                <div className="glass rounded-2xl p-6">
                  <div className="mb-3 text-[13px] text-dim">Alex asked: <span className="text-muted">{asked}</span></div>
                  <Memo text={ans.text} />
                </div>

                {ans.said?.length > 0 && (
                  <div>
                    <div className="mb-2 flex items-center gap-2 text-[12px] uppercase tracking-[0.16em] text-accent"><Quote className="h-3.5 w-3.5" /> Said · verbatim receipts</div>
                    <div className="space-y-2">
                      {ans.said.map((c: any, i: number) => (
                        <motion.div key={i} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.3 + i * 0.1 }}>
                          <Receipt c={c} />
                        </motion.div>
                      ))}
                    </div>
                  </div>
                )}

                {ans.inferred?.length > 0 && (
                  <div>
                    <div className="mb-2 flex items-center gap-2 text-[12px] uppercase tracking-[0.16em] text-warn"><Lightbulb className="h-3.5 w-3.5" /> Inferred · labelled reasoning</div>
                    <div className="space-y-1.5">
                      {ans.inferred.map((t: string, i: number) => (
                        <div key={i} className="rounded-xl border border-warn/20 bg-warn/[0.04] px-3.5 py-2.5 text-[13.5px] text-fg/85">{t.replace(/^Inferred:\s*/i, "")}</div>
                      ))}
                    </div>
                  </div>
                )}

                {(ans.action !== "answer" || ans.no_evidence_note) && (
                  <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.3 }} className="glass rounded-2xl border-accent2/30 p-5">
                    <div className="mb-2 flex items-center gap-2 text-[12px] uppercase tracking-[0.16em] text-accent2"><UserRoundSearch className="h-3.5 w-3.5" /> No evidence · route to a person</div>
                    <div className="text-[15px] leading-relaxed">{ans.no_evidence_note ?? "I don't know. I found no reliable evidence answering this."}</div>
                    {(ans.route_to ?? []).length > 0 && (
                      <div className="mt-4 flex items-center gap-3">
                        {ans.route_to.map((pid: string) => (
                          <div key={pid} className="flex items-center gap-2 rounded-full border border-line bg-black/25 py-1 pl-1 pr-3">
                            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent2/20 text-[11px] font-semibold text-accent2">{pname(pid).split(" ").map((s) => s[0]).join("")}</span>
                            <span className="text-[13px]">{pname(pid)}</span>
                          </div>
                        ))}
                        <button onClick={() => setPinged(true)} className={cn("ml-auto flex items-center gap-2 rounded-full px-4 py-2 text-[13px] font-semibold transition", pinged ? "border border-ok/40 bg-ok/10 text-ok" : "bg-accent2 text-bg hover:brightness-110")}>
                          <Send className="h-3.5 w-3.5" /> {pinged ? `Sent to ${first(ans.route_to[0])} in Slack` : "Ask the real person"}
                        </button>
                      </div>
                    )}
                  </motion.div>
                )}
              </div>

              <div className="space-y-4">
                <div className="glass rounded-2xl p-5">
                  <div className="text-[12px] uppercase tracking-[0.16em] text-dim">Decision</div>
                  {act && (
                    <div className="mt-2">
                      <Badge tone={act.tone} className="px-3 py-1 text-[14px]"><act.icon className="h-4 w-4" /> {act.label}</Badge>
                    </div>
                  )}
                  <div className="mt-5 text-[12px] uppercase tracking-[0.16em] text-dim">Calibrated confidence</div>
                  <div className="mt-2 flex items-baseline gap-1">
                    <span className="text-[36px] font-semibold tabular-nums">{Math.round(conf * 100)}</span>
                    <span className="text-muted">%</span>
                  </div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-white/5">
                    <motion.div initial={{ width: 0 }} animate={{ width: `${conf * 100}%` }} transition={{ duration: 1, ease: [0.16, 1, 0.3, 1] }} className="h-full rounded-full" style={{ background: conf > 0.6 ? "var(--accent)" : conf > 0.3 ? "var(--warn)" : "var(--alarm)" }} />
                  </div>
                  {ans.policy?.key && <div className="mt-4 font-mono text-[11px] text-dim">policy arm · {ans.policy.key}</div>}
                  {ans.area_id && <div className="mt-1 font-mono text-[11px] text-dim">area · {ans.area_id}</div>}
                </div>
                <div className="rounded-2xl border border-line p-4 text-[12.5px] leading-relaxed text-dim">
                  The answer / abstain / route choice is made by a contextual bandit trained against a truth-first benchmark. A confident wrong answer costs −2; saying “ask Mike” when that&apos;s right earns +0.5.
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
