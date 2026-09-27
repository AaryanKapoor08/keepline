"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Hash, Mail, Ticket, FileText, Lock, ArrowRight, Check } from "lucide-react";
import { useData, fmtDate, pname, cleanFact, isComplete } from "@/lib/data";
import { PageTop, Avatar, EASE } from "@/components/kit";
import { cn } from "@/components/ui";

type St = { s: "approved" | "corrected" | "removed" | "private"; sha: string; text?: string };
const KIND: Record<string, string> = { landmine: "Landmine", access: "Access", vendor_contact: "Vendor contact", recurring_task: "Recurring task" };
const FIRST = { slack: 2, email: 1, ticket: 1 } as Record<string, number>;
const GROUP_LABEL: Record<string, string> = { slack: "Slack", email: "Email", ticket: "Tickets" };
const sha = (t: string) => {
  let h = 2166136261;
  for (let i = 0; i < t.length; i++) h = Math.imul(h ^ t.charCodeAt(i), 16777619);
  return (h >>> 0).toString(16).padStart(8, "0").slice(0, 7);
};
const time = (iso: string) => new Date(iso).toLocaleTimeString("en-CA", { hour: "numeric", minute: "2-digit" });

function Source({ src, quote }: { src: any; quote: string }) {
  if (src.type === "slack")
    return (
      <div>
        <div className="mb-2 flex items-center gap-1.5 text-[13px] text-muted"><Hash className="h-3.5 w-3.5" strokeWidth={1.6} />{src.container.replace(/^#/, "")}</div>
        <div className="flex gap-3">
          <Avatar id={src.author} size={34} />
          <div>
            <div className="text-[14px]"><span className="font-medium">{src.author_name}</span> <span className="text-[12.5px] text-muted">{fmtDate(src.timestamp)} {time(src.timestamp)}</span></div>
            <div className="mt-0.5 text-[14.5px] leading-snug">{src.text}</div>
          </div>
        </div>
      </div>
    );
  if (src.type === "email")
    return (
      <div className="text-[14px]">
        <div className="mb-2 flex items-center gap-1.5 text-[13px] text-muted"><Mail className="h-3.5 w-3.5" strokeWidth={1.6} />Email</div>
        <div className="font-medium">{src.title}</div>
        <div className="mt-0.5 text-[12.5px] text-muted">From {src.author_name} · to {src.to.join(", ")} · {fmtDate(src.timestamp)}</div>
        <div className="mt-2 line-clamp-4 whitespace-pre-line leading-snug">{src.text.replace(/\n{2,}/g, "\n")}</div>
      </div>
    );
  return (
    <div className="text-[14px]">
      <div className="mb-2 flex items-center gap-1.5 text-[13px] text-muted"><Ticket className="h-3.5 w-3.5" strokeWidth={1.6} />{src.container} · {src.status}</div>
      <div className="font-medium">{src.title?.replace(/^\[[^\]]+\]\s*/, "")}</div>
      <div className="mt-2 rounded-[12px] bg-surface2 p-3 leading-snug">
        <span className="text-[12.5px] text-muted">{src.author_name} commented · {fmtDate(src.timestamp)}</span>
        <div>{quote || src.text}</div>
      </div>
    </div>
  );
}

function Item({ it, st, set, checked, toggle }: { it: any; st?: St; set: (s: St | null) => void; checked: boolean; toggle: () => void }) {
  const [edit, setEdit] = useState(false);
  const [text, setText] = useState(it.fact);
  const critical = it.kind === "landmine" || it.kind === "access";
  if (st)
    return (
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6, ease: EASE }} className="flex items-center gap-3 rounded-[18px] bg-white px-5 py-4 text-[14px]">
        {st.s === "approved" || st.s === "corrected" ? (
          <>
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-sig text-white"><Check className="h-3.5 w-3.5" strokeWidth={3} /></span>
            <span>{st.s === "corrected" ? "Corrected by Sarah and merged into company memory" : "Merged into company memory"} · <span className="font-mono text-muted">commit {st.sha}</span></span>
            {st.text && <span className="truncate text-muted">“{st.text}”</span>}
          </>
        ) : st.s === "removed" ? (
          <span>
            Removed. Not shared.
            {critical && <span className="text-muted"> Her manager will see that 1 critical item wasn&apos;t shared — no content.</span>}
          </span>
        ) : (
          <span className="text-muted">Kept private. Only Sarah can see it.</span>
        )}
        <button onClick={() => set(null)} className="ml-auto text-[13px] text-muted hover:text-fg">Undo</button>
      </motion.div>
    );
  return (
    <motion.div layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: EASE }} className="grid grid-cols-[1fr_32px_1fr] items-start gap-3 rounded-[22px] bg-white p-5">
      <div className="rounded-[16px] border border-[var(--line)] p-4">
        <Source src={it.source} quote={it.quote} />
      </div>
      <div className="flex h-full items-center justify-center text-faint"><ArrowRight className="h-5 w-5" strokeWidth={1.5} /></div>
      <div className="flex h-full flex-col rounded-[16px] bg-surface2 p-4">
        <div className="flex items-center justify-between">
          <span className={cn("rounded-full bg-white px-2.5 py-1 text-[12px]", it.kind === "landmine" && "text-alarm")}>{KIND[it.kind] ?? it.kind}</span>
          <label className="flex items-center gap-2 text-[12.5px] text-muted">
            <input type="checkbox" checked={checked} onChange={toggle} className="h-4 w-4 accent-[var(--sig)]" /> select
          </label>
        </div>
        <div className="mt-3 text-[12.5px] text-muted">Keepline wants to commit</div>
        {edit ? (
          <textarea autoFocus value={text} onChange={(e) => setText(e.target.value)} rows={3} className="mt-1 w-full resize-none rounded-[12px] bg-white p-3 text-[15px] leading-snug outline-none ring-2 ring-black/10" />
        ) : (
          <div className="mt-1 text-[16px] font-medium leading-snug">{it.fact}</div>
        )}
        <div className="mt-auto flex items-center gap-2 pt-4">
          {edit ? (
            <>
              <button onClick={() => set({ s: "corrected", sha: sha(it.fact_id + text), text })} className="rounded-full bg-[var(--fg)] px-4 py-2 text-[13px] text-white">Save correction</button>
              <button onClick={() => setEdit(false)} className="rounded-full bg-white px-4 py-2 text-[13px]">Cancel</button>
            </>
          ) : (
            <>
              <button onClick={() => set({ s: "approved", sha: it.sha })} className="rounded-full bg-[var(--fg)] px-4 py-2 text-[13px] text-white">Approve</button>
              <button onClick={() => setEdit(true)} className="rounded-full bg-white px-4 py-2 text-[13px]">Correct</button>
              <button onClick={() => set({ s: "removed", sha: "" })} className="rounded-full bg-white px-4 py-2 text-[13px]">Remove</button>
              <button onClick={() => set({ s: "private", sha: "" })} className="ml-auto text-[13px] text-muted hover:text-fg">Keep private</button>
            </>
          )}
        </div>
      </div>
    </motion.div>
  );
}

export default function ReviewPage() {
  const { data: q } = useData("/review_queue/sarah", "review_queue_sarah");
  const [src, setSrc] = useState<Record<string, boolean>>({ slack: true, email: true, ticket: true, doc: true });
  const [state, setState] = useState<Record<string, St>>({});
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [all, setAll] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === "TEXTAREA") return;
      if (e.key === "r" || e.key === "R") { setState({}); setChecked({}); setAll(false); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const groups: Record<string, any[]> = Object.fromEntries(
    Object.entries((q?.groups ?? {}) as Record<string, any[]>).map(([k, v]) => [
      k,
      v.map((it) => ({ ...it, fact: cleanFact(it.fact) })).sort((a, b) => Number(isComplete(b.fact)) - Number(isComplete(a.fact))),
    ]),
  );
  const visible = Object.entries(groups).filter(([k]) => src[k]);
  const shownIds = visible.flatMap(([k, items]) => (all ? items : items.slice(0, FIRST[k] ?? 1)).map((i) => i.fact_id));
  const nChecked = shownIds.filter((id) => checked[id] && !state[id]).length;
  const approveChecked = () => {
    const next = { ...state };
    for (const [, items] of visible) for (const it of items) if (checked[it.fact_id] && !next[it.fact_id]) next[it.fact_id] = { s: "approved", sha: it.sha };
    setState(next);
  };
  const total = visible.reduce((n, [, v]) => n + v.length, 0);
  const chip = (id: string, label: string, Icon: any, on: boolean, locked?: string) => (
    <button key={id} disabled={!!locked} onClick={() => setSrc({ ...src, [id]: !on })} title={locked} className={cn("flex h-11 items-center gap-2 rounded-full px-4 text-[14px] transition-colors", on ? "bg-white" : "bg-transparent text-muted ring-1 ring-line2", locked && "cursor-not-allowed")}>
      <Icon className="h-4 w-4" strokeWidth={1.6} /> {label} <span className={cn("text-[12.5px]", on ? "text-fg" : "text-muted")}>{locked ?? (on ? "on" : "off")}</span>
    </button>
  );
  return (
    <>
      <PageTop
        title="Sarah's review queue."
        sub="Captured from her work. Nothing is shared until she approves."
        action={nChecked ? `Approve ${nChecked} checked` : "Approve all checked"}
        onAction={approveChecked}
        chips={
          <>
            {chip("slack", "Slack", Hash, src.slack)}
            {chip("email", "Email", Mail, src.email)}
            {chip("ticket", "Tickets", Ticket, src.ticket)}
            {chip("doc", "Docs", FileText, src.doc)}
            {chip("dm", "Direct messages are never included.", Lock, false, " ")}
            {chip("random", "#random", Hash, false, "off")}
          </>
        }
        right={
          <div className="flex items-center gap-2 rounded-full bg-white py-1 pl-1 pr-4 text-[14px]">
            <Avatar id="sarah" size={34} /> Signed in as Sarah Chen
          </div>
        }
      />
      <div className="space-y-6">
        {visible.map(([k, items]) => (
          <div key={k}>
            <div className="mb-3 flex items-baseline gap-2 px-1">
              <span className="text-[19px] font-medium">{GROUP_LABEL[k]}</span>
              <span className="text-[14px] text-muted">{items.length} items</span>
            </div>
            <div className="space-y-3">
              <AnimatePresence initial={false}>
                {(all ? items : items.slice(0, FIRST[k] ?? 1)).map((it) => (
                  <Item key={it.fact_id} it={it} st={state[it.fact_id]} checked={!!checked[it.fact_id]}
                    toggle={() => setChecked({ ...checked, [it.fact_id]: !checked[it.fact_id] })}
                    set={(s) => setState((cur) => { const n = { ...cur }; if (s) n[it.fact_id] = s; else delete n[it.fact_id]; return n; })} />
                ))}
              </AnimatePresence>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-6 flex items-center justify-between px-1">
        <button onClick={() => setAll(!all)} className="inline-flex h-10 items-center rounded-full border border-[var(--line)] bg-white px-4 text-[14px]">
          {all ? "Show fewer" : `Show all ${total}`} <span className="ml-1">›</span>
        </button>
        <div className="text-[13px] text-muted">{q ? `${q.n_pending} captured items in total · ` : ""}Weekly Slack digest: &ldquo;You have 7 items to review&rdquo; (roadmap) · {pname("sarah")}&apos;s decisions stay local in this demo</div>
      </div>
    </>
  );
}
