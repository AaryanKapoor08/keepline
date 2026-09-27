"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { X, Lock } from "lucide-react";
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
    <div className="border-b border-[var(--line)] last:border-0">
      <button onClick={() => c && setOpen(!open)} className="flex w-full items-start gap-2.5 py-2.5 text-left">
        <span className={cn("mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full", red ? "bg-alarm" : "bg-sig")} />
        <span className="flex-1 text-[14.5px] leading-snug">
          {title}
          {sub && <span className="text-muted"> · {sub}</span>}
        </span>
        {c && <span className={cn("mt-0.5 text-[12px] text-muted transition-transform", open && "rotate-90")}>›</span>}
      </button>
      <AnimatePresence>
        {open && c && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <div className="mb-3 ml-4 rounded-[14px] bg-surface2 p-3"><Quote c={c} small /></div>
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
          <button key={x.q} onClick={() => run(x.q, x.label)} className={cn("rounded-full px-3.5 py-2 text-[13px]", asked === x.label ? "bg-sig text-white" : "bg-surface2 hover:bg-surface3")}>{x.label}</button>
        ))}
      </div>
      {a && (
        <motion.div key={asked} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="mt-4">
          <div className="text-[19px] font-medium leading-snug">{shortAnswer(a)}</div>
          {a.action === "answer" && cur && <div className="mt-3 rounded-[14px] bg-surface2 p-3"><Quote c={cur} small /></div>}
          {a.action !== "answer" && <div className="mt-2 text-[13px] text-muted">No reliable receipt, so Keepline routes you to the person with hands-on evidence.</div>}
        </motion.div>
      )}
    </Section>
  );
}


function CreditSection({ pid }: { pid: string }) {
  const [c, setC] = useState<any>(null);
  const [shared, setShared] = useState(false);
  useEffect(() => {
    getJSON(`/credit/${pid}`, `credit_${pid}`).then((r) => setC(r.data));
  }, [pid]);
  if (!c || (!c.n_questions && !c.onboarding_facts)) return null;
  const fn = first(pid);
  return (
    <div className="rounded-[20px] bg-white p-5">
      <div className="flex items-baseline justify-between">
        <div className="text-[16px] font-medium">Credit</div>
        <div className="flex items-center gap-1.5 text-[12.5px] text-muted"><Lock className="h-3 w-3" strokeWidth={1.8} /> Private to {fn} · {pid === "sarah" ? "she" : "they"} choose{pid === "sarah" ? "s" : ""} to share</div>
      </div>
      <div className="mt-3 space-y-1.5 text-[15px] leading-snug">
        {c.n_questions > 0 && <div>{pname(pid).split(" ")[0]}&apos;s knowledge answered <b className="font-medium">{c.n_questions} questions</b> for <b className="font-medium">{c.n_colleagues} colleagues</b> in the last two weeks.</div>}
        {c.onboarding_facts > 0 && <div><b className="font-medium">{c.onboarding_facts} messages {fn} wrote</b> are in Alex&apos;s onboarding.</div>}
        {c.prevented && <div>{fn}&apos;s rule &ldquo;{c.prevented.rule}&rdquo; came out of {c.prevented.incident}.</div>}
      </div>
      <div className="mt-3">
        {c.examples.map((e: any, i: number) => (
          <Item key={i} title={`${e.asker_name?.split(" ")[0]} asked “${e.question}”`} sub={`answered from ${pid === "sarah" ? "her" : "their"} ${e.source_type === "slack" ? "message" : e.source_type ?? "note"} of ${fmtDate(e.date)}`} c={{ quote: e.fact, stated_by: pid, date: e.date, doc_id: e.doc_id }} />
        ))}
      </div>
      <div className="mt-3 flex items-center justify-between">
        <button onClick={() => setShared(!shared)} className={cn("h-9 rounded-full px-4 text-[13px]", shared ? "bg-sigtint text-[var(--sig)]" : "bg-surface2 hover:bg-surface3")}>
          {shared ? "Shared with Dave MacLeod" : "Share with manager"}
        </button>
        <span className="text-[12px] text-muted">{c.note}</span>
      </div>
    </div>
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
  const rc = (it: any) => (it.n_receipts > 1 ? `${it.n_receipts} receipts` : undefined);
  const years = p ? Math.max(0, Math.floor((new Date("2026-09-04").getTime() - new Date(p.start_date).getTime()) / 3.156e10)) : 0;
  const strength = (s: number) => (s >= 0.7 ? "deep" : s >= 0.4 ? "working" : "some");
  const owners = sec("suggested_owners");
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[60] flex justify-end bg-black/15" onClick={onClose}>
      <motion.div initial={{ x: 60, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 60, opacity: 0 }} transition={{ duration: 0.45, ease: EASE }} onClick={(e) => e.stopPropagation()} className="m-4 w-[640px] overflow-y-auto rounded-[28px] bg-surface2 p-5">
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
                <button onClick={onClose} className="flex h-9 w-9 items-center justify-center rounded-full bg-surface2"><X className="h-4 w-4" /></button>
              </div>
              <Link href={`/history?review=${pid}`} className="mt-4 block rounded-[14px] bg-surface2 px-4 py-2.5 text-[13.5px] text-fg hover:bg-surface3">
                Owner of {d.owner_of.length} areas · {d.open_reviews} open review ({d.pending_facts} facts) · {d.open_issues} open issues <span className="text-muted">›</span>
              </Link>
            </div>
            <Section title="What they know" n={d.profile.areas.length}>
              {d.profile.areas.slice(0, 5).map((a: any) => <Item key={a.area_id} title={a.area_name} sub={`${strength(a.score)} · ${a.n_facts} facts`} />)}
            </Section>
            <Section title="Don'ts" n={sec("landmines").length}>
              {sec("landmines").slice(0, 5).map((it, i) => <Item key={i} title={it.title} sub={rc(it)} c={it.citations?.[0]} red />)}
              {!sec("landmines").length && <div className="py-2 text-[14px] text-muted">None captured.</div>}
            </Section>
            <Section title="What they're handling" n={sec("unresolved_work", "recurring_tasks", "procedures").length}>
              {sec("unresolved_work", "recurring_tasks", "procedures").slice(0, 5).map((it, i) => <Item key={i} title={it.title} sub={it.section === "unresolved_work" ? "open" : it.section === "procedures" ? "how-to" : "recurring"} c={it.citations?.[0]} />)}
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
            <CreditSection pid={pid} />
            {p.departure_date && <AskBox pid={pid} />}
            <button onClick={() => window.dispatchEvent(new CustomEvent("keepline-ask", { detail: { prefill: `What should I know about ${p.name}'s areas?` } }))} className="w-full rounded-[20px] bg-white p-4 text-left text-[14px] text-[var(--sig)]">
              Ask Keepline about {p.name.split(" ")[0]}&apos;s areas ›
            </button>
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
      <motion.div initial={{ x: 60, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 60, opacity: 0 }} transition={{ duration: 0.45, ease: EASE }} onClick={(e) => e.stopPropagation()} className="m-4 w-[640px] space-y-3 overflow-y-auto rounded-[28px] bg-surface2 p-5">
        <div className="flex items-start gap-4 rounded-[20px] bg-white p-5">
          <Avatar id="alex" size={56} />
          <div className="flex-1">
            <div className="text-[24px] font-medium leading-tight">Alex Rivera</div>
            <div className="text-[14px] text-muted">Backend Engineer · joins Engineering (Sarah&apos;s team) Sep 14</div>
          </div>
          <button onClick={onClose} className="flex h-9 w-9 items-center justify-center rounded-full bg-surface2"><X className="h-4 w-4" /></button>
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

const SIM_T = [
  { id: "corelink_v3", label: "Upgrade the CoreLink API to v3 next month", short: "CoreLink v3" },
  { id: "mobile_app", label: "Launch a new mobile banking app", short: "Mobile banking app" },
  { id: "fintrac", label: "Overhaul FINTRAC reporting", short: "FINTRAC overhaul" },
];
const pct = (v?: number) => (v == null ? "—" : `${Math.round(v * 100)}%`);
const md = (d: string) => new Date(d + "T12:00:00").toLocaleDateString("en-CA", { month: "short", day: "numeric" });

async function runSim(tid: string | null, text: string) {
  const t = SIM_T.find((x) => x.id === tid && x.label === text);
  let r = await postJSON("/project_sim", t ? { template_id: t.id } : { brief: text, weeks: 12 });
  if (!r) {
    const all = (await snapshot("project_sims")) ?? {};
    r = all[t?.id ?? "corelink_v3"];
  }
  return r;
}

function overlay(r: any, o: any) {
  const areas = r.areas.map((a: any) => a.area_id);
  const people = new Set<string>(r.dependents ?? []);
  for (const a of o.areas) for (const k of ["lead", "reviewer", "learner"]) if (a[k]) people.add(a[k]);
  const tags: Record<string, string> = {};
  for (const x of r.timeline) if (people.has(x.person_id)) tags[x.person_id] = `${x.person_id === "mike" ? "contract ends" : "leaves"} ${md(x.date)} · week ${x.week + 1} of project`;
  const rules: Record<string, number> = {};
  for (const a of r.areas) if (a.rules?.length) rules[a.area_id] = a.rules.length;
  const pairs: { p: string; a: string; label: string }[] = [];
  for (const a of o.areas) {
    if (a.learner) pairs.push({ p: a.learner, a: a.area_id, label: "learns" });
    if (a.reviewer) pairs.push({ p: a.reviewer, a: a.area_id, label: "reviews" });
  }
  return { areas, people: [...people], tags, rules, pairs };
}

function SimResult({ r, opt, setOpt }: { r: any; opt: string; setOpt: (o: string) => void }) {
  const focus = r.areas.find((a: any) => a.area_id === "corelink_api") ?? [...r.areas].sort((a: any, b: any) => a.holders.length - b.holders.length)[0];
  const at = (o: any) => o.areas.find((a: any) => a.area_id === focus?.area_id)?.p_uncovered_at_end;
  const label = (o: any) =>
    o.id === "fastest" ? "Without pairing" : o.id === "balanced" ? `Pair ${o.areas.find((a: any) => a.learner)?.learner_name?.split(" ")[0] ?? "a learner"} this week` : "Resilient";
  return (
    <div className="rounded-[24px] bg-sig p-6 text-white">
      <div className="text-[15px] text-white/60">{focus?.area_name} uncovered at project end</div>
      <div className="mt-1 text-[13px] text-white/40">across {r.runs.toLocaleString()} simulated futures</div>
      <div className="mt-5 space-y-2">
        {r.options.map((o: any) => (
          <button key={o.id} onClick={() => setOpt(o.id)} className={cn("flex w-full items-center justify-between rounded-[14px] px-4 py-3 text-left transition-colors", opt === o.id ? "bg-white text-[#111]" : "bg-white/[0.07] hover:bg-white/[0.12]")}>
            <span className="text-[15px]">{label(o)}</span>
            <span className="text-[26px] font-medium tabular-nums">{pct(at(o))}</span>
          </button>
        ))}
      </div>
      <div className="mt-6 text-[12.5px] text-white/50">{md(r.start)} → {md(r.end)}</div>
      <div className="relative mt-2 h-6">
        <div className="absolute inset-x-0 top-[11px] h-0.5 bg-white/20" />
        {r.timeline.map((x: any) => (
          <div key={x.person_id} className="absolute top-0 -translate-x-1/2" style={{ left: `${Math.min(96, Math.max(4, ((x.week + 0.5) / r.weeks) * 100))}%` }}>
            <span className="block h-6 w-0.5 bg-alarm" />
          </div>
        ))}
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 text-[12px] text-white/60">
        {r.timeline.map((x: any) => <span key={x.person_id}>{first(x.person_id)} wk {x.week + 1}</span>)}
      </div>
    </div>
  );
}

function SimDetails({ o }: { o: any }) {
  const lack = o.areas.filter((a: any) => a.p_uncovered_at_end >= 0.15);
  const strong = o.areas.filter((a: any) => a.p_uncovered_at_end < 0.15).sort((a: any, b: any) => a.p_uncovered_at_end - b.p_uncovered_at_end);
  const lose: Record<string, any[]> = {};
  for (const l of o.lose) (lose[l.name] ??= []).push(l);
  const row = "border-b border-[var(--line)] py-2.5 text-[14px] last:border-0";
  const cards: { t: string; body: React.ReactNode }[] = [];
  if (lack.length)
    cards.push({ t: "Where we lack", body: lack.map((a: any) => (
      <div key={a.area_id} className={row}><span className="text-alarm">{a.area_name}</span><div className="text-[12.5px] text-muted">{pct(a.p_uncovered_at_end)} chance nobody covers it at the end{a.learner_name ? ` · ${a.learner_name} learns it` : ""}</div></div>
    )) });
  if (strong.length)
    cards.push({ t: "Where we're strong", body: strong.map((a: any) => (
      <div key={a.area_id} className={row}>{a.area_name}<div className="text-[12.5px] text-muted">{a.lead_name} leads{a.reviewer_name ? `, ${a.reviewer_name} reviews` : ""} · {pct(a.p_uncovered_at_end)} gap</div></div>
    )) });
  if (Object.keys(lose).length)
    cards.push({ t: "Where we lose", body: Object.entries(lose).map(([n, ls]) => (
      <div key={n} className={row}>{n} leaves week {ls[0].week + 1}<div className="text-[12.5px] text-muted">{ls.map((l: any) => `${l.area} (${l.landmines} don'ts, ${l.recurring_tasks} recurring tasks)`).join(" and ")} stall</div></div>
    )) });
  return (
    <div className={cn("mt-4 grid gap-4", cards.length === 3 ? "grid-cols-3" : cards.length === 2 ? "grid-cols-2" : "grid-cols-1")}>
      {cards.map((c) => <Card key={c.t} title={c.t}>{c.body}</Card>)}
    </div>
  );
}

function RulesSheet({ area, rules, onClose }: { area: string; rules: any[]; onClose: () => void }) {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[60] flex justify-end bg-black/15" onClick={onClose}>
      <motion.div initial={{ x: 60, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 60, opacity: 0 }} transition={{ duration: 0.45, ease: EASE }} onClick={(e) => e.stopPropagation()} className="m-4 w-[560px] space-y-3 overflow-y-auto rounded-[28px] bg-surface2 p-5">
        <div className="flex items-center justify-between rounded-[20px] bg-white p-5">
          <div>
            <div className="text-[13px] text-alarm">What this change could break</div>
            <div className="text-[22px] font-medium">{area}: {rules.length} rules</div>
          </div>
          <button onClick={onClose} className="flex h-9 w-9 items-center justify-center rounded-full bg-surface2"><X className="h-4 w-4" /></button>
        </div>
        {rules.map((r, i) => (
          <div key={i} className="rounded-[20px] bg-white p-5">
            <div className="text-[15px] font-medium">{r.text}</div>
            <div className="mt-2 rounded-[14px] bg-surface2 p-3"><Quote c={r} small /></div>
          </div>
        ))}
      </motion.div>
    </motion.div>
  );
}

export default function KnowledgePage() {
  const meta = useData("/meta", "meta").data;
  const risk = useData("/risk", "risk").data;
  const [sel, setSel] = useState<string | null>(null);
  const [alex, setAlex] = useState(false);
  const [simOpen, setSimOpen] = useState(false);
  const [tid, setTid] = useState<string | null>("corelink_v3");
  const [text, setText] = useState(SIM_T[0].label);
  const [r, setR] = useState<any>(null);
  const [opt, setOpt] = useState("fastest");
  const [details, setDetails] = useState(false);
  const [ruleArea, setRuleArea] = useState<string | null>(null);
  const run = async (t = tid, x = text) => {
    const res = await runSim(t, x);
    setR(res);
    setOpt("fastest");
  };
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (q.get("person")) setSel(q.get("person"));
    if (q.get("as") === "alex") setAlex(true);
    const sim = q.get("simulate");
    if (sim) {
      const t = SIM_T.find((x) => x.id === sim.replace("-", "_")) ?? SIM_T[0];
      setSimOpen(true);
      setTid(t.id);
      setText(t.label);
      run(t.id, t.label);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const o = r?.options?.find((x: any) => x.id === opt);
  const ov = r && o ? overlay(r, o) : null;
  const clear = () => { setR(null); setSimOpen(false); setDetails(false); };
  const ruleData = ruleArea ? r?.areas?.find((a: any) => a.area_id === ruleArea) : null;
  return (
    <>
      <PageTop
        title="Who knows what at Harbourline."
        secondary={{ label: simOpen ? "Clear simulation" : "Simulate a change", onClick: () => (simOpen ? clear() : (setAlex(false), setSel(null), setSimOpen(true))) }}
        action={alex ? "Show everyone" : "View as Alex"}
        onAction={() => { clear(); setSel(null); setAlex(!alex); }}
      />
      <AnimatePresence>
        {simOpen && (
          <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="mb-4 flex items-center gap-3 rounded-[22px] bg-white p-3">
            <input value={text} onChange={(e) => { setText(e.target.value); setTid(SIM_T.find((t) => t.label === e.target.value)?.id ?? null); }} className="h-12 flex-1 rounded-full bg-surface2 px-5 text-[16px] outline-none focus:ring-2 focus:ring-[var(--sig-tint)]" />
            {SIM_T.slice(1).map((t) => (
              <button key={t.id} onClick={() => { setTid(t.id); setText(t.label); run(t.id, t.label); }} className="h-10 rounded-full bg-surface2 px-4 text-[13.5px] hover:bg-surface3">{t.short}</button>
            ))}
            <button onClick={() => run()} className="btn-primary !h-12">Run</button>
          </motion.div>
        )}
      </AnimatePresence>
      <div className={cn("grid gap-4", ov ? "grid-cols-[1fr_360px]" : "grid-cols-1")}>
        <Card className="p-3">
          {meta && risk && (
            <OrgFlow people={meta.people} risk={risk} selected={sel} focusTeam={alex ? "engineering" : null} sim={ov} height={ov ? 600 : 560}
              onPerson={(id) => (id === "alex" && !ov ? setAlex(true) : setSel(id))} onArea={(a) => { if (ov?.rules[a]) setRuleArea(a); }} />
          )}
          <div className="flex items-center gap-5 px-3 pb-1 pt-3 text-[12.5px] text-muted">
            {ov ? (
              <span>Lit: what &ldquo;{text}&rdquo; touches and who it depends on. Dashed: the suggested pairing. Click a red badge for the rules it could break.</span>
            ) : (
              <>
                <span>Lines show hands-on knowledge only (closed tickets, stated facts), not job titles.</span>
                <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-[4px] border-2 border-alarm" /> only one person knows it</span>
                <span className="ml-auto">Click a person to open their knowledge.</span>
              </>
            )}
          </div>
        </Card>
        {ov && (
          <div className="space-y-3">
            <SimResult r={r} opt={opt} setOpt={setOpt} />
            <button onClick={() => setDetails(!details)} className="inline-flex h-10 items-center rounded-full border border-[var(--line)] bg-white px-4 text-[14px]">{details ? "Hide details" : "Details"} <span className="ml-1">›</span></button>
            <div className="text-[12.5px] leading-relaxed text-muted">A recommendation for a manager to approve. Uses who knows what and HR dates only; never performance.</div>
          </div>
        )}
      </div>
      {ov && details && <SimDetails o={o} />}
      <AnimatePresence>
        {sel && <PersonSheet pid={sel} onClose={() => setSel(null)} />}
        {alex && !sel && <AlexSheet onClose={() => setAlex(false)} />}
        {ruleData && <RulesSheet area={ruleData.area_name} rules={ruleData.rules} onClose={() => setRuleArea(null)} />}
      </AnimatePresence>
    </>
  );
}
