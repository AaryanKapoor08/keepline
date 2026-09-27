"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { X } from "lucide-react";
import { useData, getJSON, postJSON, snapshot, normQ, nearest, pname, first, fmtDate } from "@/lib/data";
import { PageTop, Card, Quote, Avatar, EASE } from "@/components/kit";
import { cn } from "@/components/ui";

const OrgFlow = dynamic(() => import("@/components/orgflow"), { ssr: false });

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

function Item({ title, sub, c, red }: { title: string; sub?: string; c?: any; red?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-[#ececec] last:border-0">
      <button onClick={() => c && setOpen(!open)} className="flex w-full items-start gap-2.5 py-2.5 text-left">
        <span className={cn("mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full", red ? "bg-alarm" : "bg-[#111]")} />
        <span className="flex-1 text-[14.5px] leading-snug">
          {title}
          {sub && <span className="text-muted"> · {sub}</span>}
        </span>
        {c && <span className={cn("mt-0.5 text-[12px] text-muted transition-transform", open && "rotate-90")}>›</span>}
      </button>
      <AnimatePresence>
        {open && c && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <div className="mb-3 ml-4 rounded-[14px] bg-[#f4f5f7] p-3"><Quote c={c} small /></div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Section({ title, children, n }: { title: string; children: React.ReactNode; n?: number }) {
  return (
    <div className="rounded-[20px] bg-white p-5">
      <div className="mb-1 flex items-baseline justify-between">
        <div className="text-[16px] font-medium">{title}</div>
        {n != null && <div className="text-[13px] text-muted">{n}</div>}
      </div>
      {children}
    </div>
  );
}

function AskBox({ pid }: { pid: string }) {
  const [a, setA] = useState<any>(null);
  const [asked, setAsked] = useState<string | null>(null);
  const run = async (q: string, label: string) => {
    setAsked(label);
    let r = await postJSON("/ask", { question: q, asker_id: "alex" });
    if (!r) {
      const t = (await snapshot("answers")) ?? {};
      r = t[normQ(q)] ?? nearest(q, t);
    }
    setA(r);
  };
  const cur = a?.said?.find((c: any) => c.is_current !== false) ?? a?.said?.[0];
  return (
    <Section title={`Ask about ${first(pid)}'s areas`}>
      <div className="mt-2 flex flex-wrap gap-2">
        {ASKS.map((x) => (
          <button key={x.q} onClick={() => run(x.q, x.label)} className={cn("rounded-full px-3.5 py-2 text-[13px]", asked === x.label ? "bg-[#111] text-white" : "bg-[#f4f5f7] hover:bg-[#ececef]")}>{x.label}</button>
        ))}
      </div>
      {a && (
        <motion.div key={asked} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="mt-4">
          <div className="text-[19px] font-medium leading-snug">{shortAnswer(a)}</div>
          {a.action === "answer" && cur && <div className="mt-3 rounded-[14px] bg-[#f4f5f7] p-3"><Quote c={cur} small /></div>}
          {a.action !== "answer" && <div className="mt-2 text-[13px] text-muted">No reliable receipt, so Keepline routes you to the person with hands-on evidence.</div>}
        </motion.div>
      )}
    </Section>
  );
}

function PersonSheet({ pid, onClose }: { pid: string; onClose: () => void }) {
  const [d, setD] = useState<any>(null);
  useEffect(() => {
    setD(null);
    getJSON(`/person/${pid}`, `person_${pid}`).then((r) => setD(r.data));
  }, [pid]);
  const p = d?.person;
  const items: any[] = d?.pack?.items ?? [];
  const sec = (...s: string[]) => items.filter((i) => s.includes(i.section));
  const years = p ? Math.max(0, Math.floor((new Date("2026-09-04").getTime() - new Date(p.start_date).getTime()) / 3.156e10)) : 0;
  const strength = (s: number) => (s >= 0.7 ? "deep" : s >= 0.4 ? "working" : "some");
  const owners = sec("suggested_owners");
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[60] flex justify-end bg-black/15" onClick={onClose}>
      <motion.div initial={{ x: 60, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 60, opacity: 0 }} transition={{ duration: 0.45, ease: EASE }} onClick={(e) => e.stopPropagation()} className="m-4 w-[640px] overflow-y-auto rounded-[28px] bg-[#f4f5f7] p-5">
        {!d ? (
          <div className="p-6 text-muted">Loading…</div>
        ) : (
          <div className="space-y-3">
            <div className="rounded-[20px] bg-white p-5">
              <div className="flex items-start gap-4">
                <Avatar id={pid} size={56} />
                <div className="flex-1">
                  <div className="text-[24px] font-medium leading-tight">{p.name}</div>
                  <div className="text-[14px] text-muted">{p.role} · {years ? `${years} years` : "new"} at Harbourline</div>
                  {p.departure_date && <div className="mt-1 text-[14px] font-medium text-alarm">Last day {fmtDate(p.departure_date)}</div>}
                  {p.start_date > "2026-09-04" && <div className="mt-1 text-[14px] font-medium">Joins {fmtDate(p.start_date)}</div>}
                </div>
                <button onClick={onClose} className="flex h-9 w-9 items-center justify-center rounded-full bg-[#f4f5f7]"><X className="h-4 w-4" /></button>
              </div>
              <Link href={`/history?review=${pid}`} className="mt-4 block rounded-[14px] bg-[#f4f5f7] px-4 py-2.5 text-[13.5px] text-fg hover:bg-[#ececef]">
                Owner of {d.owner_of.length} areas · {d.open_reviews} open review ({d.pending_facts} facts) · {d.open_issues} open issues <span className="text-muted">›</span>
              </Link>
            </div>
            <Section title="What they know" n={d.profile.areas.length}>
              {d.profile.areas.slice(0, 5).map((a: any) => <Item key={a.area_id} title={a.area_name} sub={`${strength(a.score)} · ${a.n_facts} facts`} />)}
            </Section>
            <Section title="Don'ts" n={sec("landmines").length}>
              {sec("landmines").slice(0, 5).map((it, i) => <Item key={i} title={it.title} c={it.citations?.[0]} red />)}
              {!sec("landmines").length && <div className="py-2 text-[14px] text-muted">None captured.</div>}
            </Section>
            <Section title="What they're handling" n={sec("unresolved_work", "recurring_tasks").length}>
              {sec("unresolved_work", "recurring_tasks").slice(0, 5).map((it, i) => <Item key={i} title={it.title} sub={it.section === "unresolved_work" ? "open" : "recurring"} c={it.citations?.[0]} />)}
            </Section>
            <Section title="Access & vendor contacts" n={sec("access", "vendor_contacts").length}>
              {sec("access", "vendor_contacts").slice(0, 5).map((it, i) => <Item key={i} title={it.title} c={it.citations?.[0]} />)}
              <div className="pt-2 text-[12px] text-muted">Where access lives and who holds it. Never the secrets themselves.</div>
            </Section>
            <Section title="Who else knows">
              {d.owner_of.slice(0, 4).map((a: string) => {
                const o = d.others[a] ?? [];
                const strong = o.filter((x: any) => x.strong);
                const sug = owners.find((it) => it.area_id === a)?.suggested_owner_id;
                return (
                  <Item key={a} title={d.profile.areas.find((x: any) => x.area_id === a)?.area_name ?? a}
                    sub={strong.length ? `also held by ${strong.map((x: any) => first(x.person_id)).join(", ")}` : `no one else${sug ? ` · suggested new owner ${pname(sug)}` : ""}`} red={!strong.length} />
                );
              })}
            </Section>
            {p.departure_date && <AskBox pid={pid} />}
          </div>
        )}
      </motion.div>
    </motion.div>
  );
}

function AlexSheet({ onClose }: { onClose: () => void }) {
  const { data: o } = useData("/onboarding/alex", "onboarding_alex");
  const sec = (t: string) => o?.sections?.find((s: any) => s.title.startsWith(t))?.items ?? [];
  const SYS = /corelink|recon|ach|backup|cert|ssl|key|restart|primary|cutoff|rotat|replica/i;
  const mines = sec("Open risks").filter((x: any) => /landmine/i.test(x.type ?? "") && SYS.test(x.title ?? "")).slice(0, 5);
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[60] flex justify-end bg-black/15" onClick={onClose}>
      <motion.div initial={{ x: 60, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 60, opacity: 0 }} transition={{ duration: 0.45, ease: EASE }} onClick={(e) => e.stopPropagation()} className="m-4 w-[640px] space-y-3 overflow-y-auto rounded-[28px] bg-[#f4f5f7] p-5">
        <div className="flex items-start gap-4 rounded-[20px] bg-white p-5">
          <Avatar id="alex" size={56} />
          <div className="flex-1">
            <div className="text-[24px] font-medium leading-tight">Alex Rivera</div>
            <div className="text-[14px] text-muted">Backend Engineer · joins Engineering (Sarah&apos;s team) Sep 14</div>
          </div>
          <button onClick={onClose} className="flex h-9 w-9 items-center justify-center rounded-full bg-[#f4f5f7]"><X className="h-4 w-4" /></button>
        </div>
        <Section title="Who to ask about what" n={sec("Who to ask").length}>
          {sec("Who to ask").map((x: any, i: number) => <Item key={i} title={`${x.area} → ${x.person}`} sub={x.after ? `after ${x.after}` : x.why} c={x.citations?.[0]} />)}
        </Section>
        <Section title="Don'ts to know first" n={mines.length}>
          {mines.map((x: any, i: number) => <Item key={i} title={x.title} c={x.citations?.[0]} red />)}
        </Section>
        <Section title="Starter tasks" n={sec("Starter").length}>
          {sec("Starter").map((x: any, i: number) => <Item key={i} title={x.task} sub={x.buddy ? `buddy ${x.buddy}` : undefined} c={x.citations?.[0]} />)}
        </Section>
      </motion.div>
    </motion.div>
  );
}

export default function KnowledgePage() {
  const meta = useData("/meta", "meta").data;
  const risk = useData("/risk", "risk").data;
  const [sel, setSel] = useState<string | null>(null);
  const [alex, setAlex] = useState(false);
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (q.get("person")) setSel(q.get("person"));
    if (q.get("as") === "alex") setAlex(true);
  }, []);
  return (
    <>
      <PageTop title="Who knows what at Harbourline." action={alex ? "Show everyone" : "View as Alex"} onAction={() => { setSel(null); setAlex(!alex); }} />
      <Card className="p-3">
        {meta && risk && <OrgFlow people={meta.people} risk={risk} selected={sel} focusTeam={alex ? "engineering" : null} onPerson={(id) => (id === "alex" ? setAlex(true) : setSel(id))} />}
        <div className="flex items-center gap-5 px-3 pb-1 pt-3 text-[12.5px] text-muted">
          <span>Lines show hands-on knowledge only (closed tickets, stated facts), not job titles.</span>
          <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-[4px] border-2 border-alarm" /> only one person knows it</span>
          <span className="ml-auto">Click a person to open their knowledge.</span>
        </div>
      </Card>
      <AnimatePresence>
        {sel && <PersonSheet pid={sel} onClose={() => setSel(null)} />}
        {alex && !sel && <AlexSheet onClose={() => setAlex(false)} />}
      </AnimatePresence>
    </>
  );
}
