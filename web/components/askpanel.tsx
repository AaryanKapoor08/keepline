"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { X, Hash, Mail, Ticket, FileText, ArrowUp } from "lucide-react";
import { API, snapshot, normQ, nearest, pname, fmtDate } from "@/lib/data";
import { cn } from "./ui";

const EASE = [0.25, 0.1, 0.25, 1] as const;
const SUGGEST = ["What should I know before touching reconciliation?", "Who can cover CoreLink when Sarah leaves?", "What's the office wifi password?"];
const ASKERS = ["alex", "dave", "aisha"];

type Turn = { q: string; a: any | null; offline?: boolean };

async function askChat(messages: { role: string; content: string }[], asker: string): Promise<{ a: any; offline: boolean }> {
  try {
    const r = await Promise.race([
      fetch(API + "/chat", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ messages, asker_id: asker }) }),
      new Promise<Response>((_, rej) => setTimeout(() => rej(new Error("timeout")), 20000)),
    ]);
    if (r.ok) return { a: await r.json(), offline: false };
  } catch {}
  const table = (await snapshot("chat_canned")) ?? {};
  const q = messages[messages.length - 1].content;
  return { a: table[normQ(q)] ?? nearest(q, table), offline: true };
}

const Src = ({ id }: { id?: string }) => {
  const t = (id ?? "").split("-")[0];
  const I = t === "slack" ? Hash : t === "email" ? Mail : t === "ticket" ? Ticket : FileText;
  return <I className="h-3.5 w-3.5 shrink-0 text-muted" strokeWidth={1.6} />;
};

function Receipt({ c }: { c: any }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-[var(--line)] last:border-0">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 py-2 text-left text-[13px]">
        <Src id={c.doc_id} />
        <span>{c.author_name ?? pname(c.author_id)}</span>
        <span className="text-muted">· {fmtDate(c.timestamp)} · {c.doc_id}</span>
        {c.is_current === false && <span className="rounded-full bg-surface2 px-2 py-0.5 text-[11.5px] text-muted">replaced</span>}
        <span className="ml-auto text-[12.5px] text-[var(--sig)]">{open ? "Hide quote" : "Show quote"} ›</span>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <div className="mb-2 rounded-[12px] bg-surface2 p-3 text-[14px] leading-snug">&ldquo;{c.quote}&rdquo;</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Memo({ text }: { text: string }) {
  const [more, setMore] = useState(false);
  const long = text.length > 420;
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <div>
      <p className={cn("whitespace-pre-line text-[18px] leading-[1.55]", long && !more && "line-clamp-5")}>
        {parts.map((p, i) => (p.startsWith("**") ? <strong key={i} className="font-medium">{p.slice(2, -2)}</strong> : <span key={i}>{p}</span>))}
      </p>
      {long && <button onClick={() => setMore(!more)} className="mt-1 text-[14px] text-[var(--sig)]">{more ? "Less" : "More"} ›</button>}
    </div>
  );
}

function Answer({ t, onRoute }: { t: Turn; onRoute: (id: string) => void }) {
  const [trace, setTrace] = useState(false);
  const a = t.a;
  if (!a) return <div className="text-[15px] text-muted">Looking through the company&apos;s memory…</div>;
  const text = String(a.text ?? "").replace(/--/g, "—").replace(/\s*\[[^\]]*(?:slack|email|ticket|doc)-[^\]]*\]/g, "").replace(/\n{3,}/g, "\n\n").replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1$2").trim();
  return (
    <div>
      <Memo text={text} />
      {a.citations?.length > 0 && (
        <div className="mt-4 rounded-[16px] bg-white px-4 py-1">
          {a.citations.slice(0, 4).map((c: any, i: number) => <Receipt key={i} c={c} />)}
        </div>
      )}
      {(a.action === "route" || a.action === "abstain") && a.route_to?.[0] && (
        <button onClick={() => onRoute(a.route_to[0])} className="mt-4 inline-flex h-10 items-center rounded-full bg-sig px-4 text-[14px] text-white">
          I don&apos;t know. Ask {pname(a.route_to[0])} ›
        </button>
      )}
      <div className="mt-3 flex items-center gap-4 text-[13px] text-muted">
        {a.trace?.length > 0 && (
          <button onClick={() => setTrace(!trace)} className="hover:text-fg">How I found this <span className={cn("inline-block transition-transform", trace && "rotate-90")}>›</span></button>
        )}
        <span>{a.action === "answer" ? "Answered from receipts" : a.action === "route" ? "Routed to a person" : "No evidence, so no answer"} · confidence {Math.round((a.confidence ?? 0) * 100)}%</span>
        {t.offline && <span className="rounded-full bg-white px-2.5 py-0.5 text-[12px] text-fg">Offline — showing saved answer</span>}
      </div>
      <AnimatePresence>
        {trace && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {a.trace.map((s: any, i: number) => (
                <div key={i} className="flex items-center gap-2">
                  {i > 0 && <span className="h-px w-5 bg-[var(--line-2)]" />}
                  <div className="rounded-[12px] border-2 border-[var(--line)] bg-white px-3 py-2">
                    <div className="font-mono text-[12px]">{s.tool}</div>
                    <div className="max-w-[240px] truncate text-[11.5px] text-muted">{s.summary}</div>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default function AskPanel() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [asker, setAsker] = useState("alex");
  const [q, setQ] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === "Escape") setOpen(false);
    };
    const onAsk = (e: Event) => {
      setQ((e as CustomEvent).detail?.prefill ?? "");
      setOpen(true);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("keepline-ask", onAsk);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("keepline-ask", onAsk);
    };
  }, []);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);
  const send = async (text: string) => {
    if (!text.trim()) return;
    setQ("");
    const history = turns.flatMap((t) => [{ role: "user", content: t.q }, { role: "assistant", content: t.a?.text ?? "" }]);
    const idx = turns.length;
    setTurns((ts) => [...ts, { q: text, a: null }]);
    const { a, offline } = await askChat([...history, { role: "user", content: text }], asker);
    setTurns((ts) => ts.map((t, i) => (i === idx ? { ...t, a: a ?? { action: "abstain", text: "I don't know. That question isn't in the saved answers; start the API to ask anything.", citations: [], trace: [] }, offline } : t)));
  };
  return (
    <>
      <button onClick={() => setOpen(true)} className="flex h-11 items-center gap-2 rounded-full bg-surface2 pl-4 pr-2 text-[14px] hover:bg-surface3">
        Ask Keepline <span className="rounded-md bg-white px-1.5 py-0.5 font-mono text-[11px] text-muted">⌘K</span>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[70] flex justify-end bg-black/15" onClick={() => setOpen(false)}>
            <motion.div initial={{ x: 60, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 60, opacity: 0 }} transition={{ duration: 0.45, ease: EASE }} onClick={(e) => e.stopPropagation()} className="m-4 flex w-[660px] flex-col rounded-[28px] bg-canvas">
              <div className="flex items-center justify-between rounded-t-[28px] px-6 pb-3 pt-5">
                <div className="flex items-center gap-3">
                  <div className="text-[22px] font-medium">Ask Keepline</div>
                  <span className="rounded-full bg-white px-3 py-1 text-[12.5px] text-muted">{pname(asker).split(" ")[0]} · Tue Sep 15</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[13px] text-muted">Asking as</span>
                  {ASKERS.map((p) => (
                    <button key={p} onClick={() => setAsker(p)} className={cn("h-9 rounded-full px-3 text-[13px]", asker === p ? "bg-sig text-white" : "bg-white")}>{pname(p).split(" ")[0]}</button>
                  ))}
                  <button onClick={() => setOpen(false)} className="ml-2 flex h-9 w-9 items-center justify-center rounded-full bg-white"><X className="h-4 w-4" /></button>
                </div>
              </div>
              <div className="flex-1 space-y-6 overflow-y-auto px-6 py-2">
                {!turns.length && (
                  <div className="pt-6">
                    <div className="text-[15px] text-muted">Answers come from Harbourline&apos;s messages, email and tickets, with the receipt. If there&apos;s no evidence, Keepline says so and tells you who to ask.</div>
                    <div className="mt-5 flex flex-wrap gap-2">
                      {SUGGEST.map((s) => (
                        <button key={s} onClick={() => send(s)} className="rounded-full bg-white px-4 py-2.5 text-[14px] hover:bg-surface3">{s}</button>
                      ))}
                    </div>
                  </div>
                )}
                {turns.map((t, i) => (
                  <motion.div key={i} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: EASE }} className="border-b border-[var(--line)] pb-6 last:border-0">
                    <div className="mb-2 text-[14px] text-muted">{t.q}</div>
                    <Answer t={t} onRoute={(id) => { setOpen(false); router.push(`/graph?person=${id}`); }} />
                  </motion.div>
                ))}
                <div ref={end} />
              </div>
              <form onSubmit={(e) => { e.preventDefault(); send(q); }} className="m-4 flex items-center gap-2 rounded-full bg-white p-1.5 pl-5">
                <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask anything about the company's knowledge" className="h-11 flex-1 bg-transparent text-[16px] outline-none placeholder:text-dim" />
                <button className="flex h-11 w-11 items-center justify-center rounded-full bg-sig text-white"><ArrowUp className="h-5 w-5" /></button>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
