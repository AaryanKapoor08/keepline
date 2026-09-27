"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Hash, Mail, Ticket, FileText } from "lucide-react";
import { getJSON, useData, fmtDate, first, isRestatement, isUnrelated, cleanFact, isComplete } from "@/lib/data";
import { PageTop, Card, Avatar, Details, Fade } from "@/components/kit";
import { cn } from "@/components/ui";

const AREAS = [
  ["reconciliation", "Reconciliation"], ["corelink_api", "CoreLink API"], ["ssl_dns", "SSL & DNS"], ["backups_dr", "Backups & DR"], ["fintrac_reporting", "FINTRAC"],
];
const WHEN = [["2026-03-31", "Mar 31"], ["2026-05-31", "May 31"], ["2026-07-31", "Jul 31"], ["2026-09-04", "Today"]];
const SrcIcon = ({ t }: { t?: string }) => {
  const I = t === "slack" ? Hash : t === "email" ? Mail : t === "ticket" ? Ticket : FileText;
  return <I className="h-3.5 w-3.5 text-muted" strokeWidth={1.6} />;
};

function Diff({ d, asOf }: { d: any; asOf: string }) {
  const happened = d.new.valid_from <= asOf;
  return (
    <div className="overflow-hidden rounded-[16px] border border-[var(--line)] font-mono text-[13px]">
      <div className="flex items-center justify-between bg-surface2 px-4 py-2 font-sans text-[12.5px] text-muted">
        <span>{d.new.area_id}.md · {d.old.sha} → {d.new.sha}</span>
        <span>{happened ? `replaced on ${fmtDate(d.replaced_on)}` : `not yet replaced as of ${fmtDate(asOf)}`}</span>
      </div>
      <div className={cn("flex gap-3 px-4 py-2", happened ? "bg-alarmtint" : "bg-white")}>
        <span className="text-muted">{happened ? "−" : " "}</span>
        <span className={happened ? "text-alarmdeep" : ""}>{cleanFact(d.old.message)}</span>
      </div>
      {happened && (
        <div className="flex gap-3 bg-sigtint px-4 py-2">
          <span className="text-muted">+</span>
          <span>{cleanFact(d.new.message)}</span>
        </div>
      )}
      <div className="bg-white px-4 py-2 font-sans text-[12.5px] text-muted">
        {happened ? <>{d.new.author_name} · {fmtDate(d.new.valid_from)} · {d.new.doc_id}</> : <>{d.old.author_name} · {fmtDate(d.old.valid_from)} · {d.old.doc_id}</>}
      </div>
    </div>
  );
}

export default function HistoryPage() {
  const [area, setArea] = useState("reconciliation");
  const [h, setH] = useState<any>(null);
  const [asOf, setAsOf] = useState("2026-09-04");
  const [prOpen, setPrOpen] = useState(false);
  const [tab, setTab] = useState<"commits" | "decisions" | "owners">("commits");
  const decisions = useData("/ledger/decisions", "ledger_decisions").data;
  const owners = useData("/ledger/owners", "ledger_owners").data;
  const [merged, setMerged] = useState<Record<string, string>>({});
  const review = useData("/review/sarah", "review_sarah").data;
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (q.get("review")) setPrOpen(true);
    const t = q.get("tab");
    if (t === "decisions" || t === "owners") setTab(t);
  }, []);
  useEffect(() => {
    getJSON(`/history/${area}`, `history_${area}`).then((r) => setH(r.data));
  }, [area]);
  const commits = useMemo(() => {
    const cs: any[] = (h?.commits ?? []).filter((c: any) => c.valid_from <= asOf);
    const replacedBy = new Set(cs.filter((c) => c.supersedes).map((c) => c.supersedes));
    return cs.filter((c) => !replacedBy.has(c.fact_id) && isComplete(cleanFact(c.message))).map((c) => ({ ...c, message: cleanFact(c.message) })).slice(0, 7).map((c) => ({ ...c, versions: 1 + (h?.diffs ?? []).filter((d: any) => d.new.fact_id === c.fact_id && !isRestatement(d.new.message, d.old.message)).length }));
  }, [h, asOf]);
  const real = (h?.diffs ?? []).filter((d: any) => !isRestatement(d.new.message, d.old.message));
  const diff = real.find((d: any) => /skip/i.test(d.old.message)) ?? real[0];

  return (
    <>
      <PageTop title="Every fact has a history." action="Open review queue" actionHref="/review" />
      <div className="mb-4 flex gap-1 self-start rounded-full bg-white p-1" style={{ width: "fit-content" }}>
        {(["commits", "decisions", "owners"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)} className={cn("h-9 rounded-full px-4 text-[14px] capitalize", tab === t ? "bg-sig text-white" : "hover:bg-surface2")}>{t}</button>
        ))}
      </div>
      {tab === "decisions" && (
        <Card title="Decisions ledger" right={<span className="text-[13px] text-muted">{decisions?.length ?? 0} decisions and changes, each credited to who made it</span>}>
          {[...(decisions ?? [])]
            .map((d: any) => (d.replaced && isUnrelated(d.message, d.replaced) ? { ...d, replaced: undefined } : d))
            .map((d: any) => ({ ...d, restated: d.replaced ? isRestatement(d.message, d.replaced) : false }))
            .sort((a: any, b: any) => Number(!!b.replaced && !b.restated) - Number(!!a.replaced && !a.restated) || (a.valid_from < b.valid_from ? 1 : -1))
            .slice(0, 12)
            .map((d: any) => (
            <div key={d.sha} className="flex items-start gap-3 border-b border-[var(--line)] py-3 last:border-0">
              <Avatar id={d.author ?? "sarah"} size={30} />
              <div className="min-w-0 flex-1">
                <div className="text-[15px] leading-snug">{cleanFact(d.message)}</div>
                {d.replaced && !d.restated && <div className="mt-0.5 text-[13px] text-muted">replaced &ldquo;{d.replaced}&rdquo;</div>}
                {d.restated && <div className="mt-0.5 text-[13px] text-muted" title={d.replaced}>also stated {fmtDate(d.replaced_date)} ›</div>}
                <div className="mt-1 flex items-center gap-2 text-[12.5px] text-muted">
                  <span>decided by {d.author_name}</span>·<span>{fmtDate(d.valid_from)}</span>·<SrcIcon t={d.source_type} /><span>{d.doc_id}</span>
                </div>
              </div>
            </div>
          ))}
        </Card>
      )}
      {tab === "owners" && (
        <Card title="Owners" right={<span className="text-[13px] text-muted">from hands-on evidence, like CODEOWNERS</span>}>
          {(owners ?? []).map((o: any) => (
            <div key={o.area_id} className="grid grid-cols-[240px_1fr_1.4fr] items-center gap-4 border-b border-[var(--line)] py-3 text-[14.5px] last:border-0">
              <span className="font-medium">{o.area_name}</span>
              <span>{o.owners.map((x: any) => x.name).join(", ")}{o.bus_factor <= 1 && <span className="ml-2 text-[12.5px] text-alarm">only owner</span>}</span>
              <span className="text-muted">
                {o.handoff?.continue ? <>{o.handoff.from_name?.split(" ")[0]} leaves {fmtDate(o.handoff.on)} · <span className="text-fg">{o.handoff.continue.map((n: string) => n.split(" ")[0]).join(" and ")} continue</span></> : o.handoff ? <>Pending handoff: <span className="text-fg">{o.handoff.from_name?.split(" ")[0]} → {o.handoff.to_name ?? "unassigned"}</span> on {fmtDate(o.handoff.on)}{o.handoff.reviewer_name ? `, reviewer ${o.handoff.reviewer_name.split(" ")[0]}` : ""}</> : "No change planned"}
              </span>
            </div>
          ))}
        </Card>
      )}
      {tab === "commits" && (<>
      <div className="mb-4 flex items-center justify-between">
        <div className="flex gap-2">
          {AREAS.map(([id, l]) => (
            <button key={id} onClick={() => setArea(id)} className={cn("h-10 rounded-full px-4 text-[14px]", area === id ? "bg-sig text-white" : "bg-white hover:bg-white/70")}>{l}</button>
          ))}
        </div>
        <div className="flex items-center gap-1 rounded-full bg-white p-1">
          <span className="px-3 text-[13px] text-muted">View memory as of</span>
          {WHEN.map(([d, l]) => (
            <button key={d} onClick={() => setAsOf(d)} className={cn("h-8 rounded-full px-3.5 text-[13px]", asOf === d ? "bg-sig text-white" : "hover:bg-surface2")}>{l}</button>
          ))}
        </div>
      </div>

      <AnimatePresence>
        {prOpen && review && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="mb-4 overflow-hidden">
            <Card title={<>Review: knowledge captured from Sarah <span className="ml-2 rounded-full bg-surface2 px-3 py-1 text-[13px] text-muted">{review.n_pending} facts · awaiting her review</span></>} right={<span className="text-[13px] text-muted">Nothing is shared until she merges it</span>}>
              <div className="grid grid-cols-[1.4fr_1fr] gap-6">
                <div>
                  {review.commits.slice(0, 5).map((c: any) => (
                    <div key={c.sha} className="flex items-center gap-3 border-b border-[var(--line)] py-3 last:border-0">
                      <span className="font-mono text-[12.5px] text-muted">{c.sha}</span>
                      <span className="flex-1 text-[14.5px] leading-snug">{c.message}</span>
                      {merged[c.sha] ? (
                        <span className="text-[13px] text-muted">{merged[c.sha]}</span>
                      ) : (
                        <span className="flex gap-1.5">
                          <button onClick={() => setMerged({ ...merged, [c.sha]: "Approved" })} className="rounded-full bg-sig px-3 py-1.5 text-[12.5px] text-white">Approve</button>
                          <button onClick={() => setMerged({ ...merged, [c.sha]: "Correction requested" })} className="rounded-full bg-surface2 px-3 py-1.5 text-[12.5px]">Correct</button>
                        </span>
                      )}
                    </div>
                  ))}
                </div>
                <div>
                  <div className="mb-2 text-[14px] font-medium">Open issues · questions to ask before Sep 11</div>
                  {review.issues.slice(0, 4).map((g: any, i: number) => (
                    <div key={i} className="border-b border-[var(--line)] py-2.5 text-[14px] leading-snug last:border-0">
                      {g.question}
                      <div className="mt-0.5 text-[12.5px] text-muted">assigned to {first(g.person_id)} · due Sep 11</div>
                    </div>
                  ))}
                </div>
              </div>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="grid grid-cols-[1.25fr_1fr] gap-4">
        <Card title={`${h?.area_name ?? ""} · log`} right={<span className="text-[13px] text-muted">Owner: {h?.codeowners?.map((o: any) => o.name).join(", ") || "—"} · {h?.n_commits ?? 0} commits</span>}>
          <AnimatePresence mode="wait">
            <motion.div key={area + asOf} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              {commits.map((c: any) => (
                <div key={c.sha} className="flex items-start gap-3 border-b border-[var(--line)] py-3 last:border-0">
                  <Avatar id={c.author ?? "sarah"} size={30} />
                  <div className="min-w-0 flex-1">
                    <div className="text-[14.5px] leading-snug">{c.message}</div>
                    <div className="mt-1 flex items-center gap-2 text-[12.5px] text-muted">
                      <span className="font-mono">{c.sha}</span>·<span>{c.author_name}</span>·<span>{fmtDate(c.valid_from)}</span>·<SrcIcon t={c.source_type} /><span>{c.doc_id}</span>
                      {c.versions > 1 && <span className="rounded-full bg-surface2 px-2 py-0.5 text-fg">{c.versions} versions</span>}
                    </div>
                  </div>
                </div>
              ))}
              {!commits.length && <div className="py-6 text-[14px] text-muted">Nothing known about this area yet on {fmtDate(asOf)}.</div>}
            </motion.div>
          </AnimatePresence>
        </Card>
        <div className="space-y-4">
          <Card title="Diff">
            {diff ? <Diff d={diff} asOf={asOf} /> : <div className="text-[14px] text-muted">No replaced facts in this area.</div>}
            <div className="mt-3 text-[13px] text-muted">Old versions are never deleted. Answers use the current line and cite it.</div>
          </Card>
          <Card title="Blame" right={<Details href="/graph?person=sarah">Owner&apos;s knowledge</Details>}>
            <Fade show={!!commits[0]}>
              {commits[0] && (
                <div className="text-[14px] leading-relaxed">
                  <span className="font-mono text-muted">{commits[0].sha}</span> &ldquo;{commits[0].message}&rdquo;
                  <div className="mt-1 text-muted">said by {commits[0].author_name} on {fmtDate(commits[0].valid_from)} in {commits[0].source_type} {commits[0].doc_id}</div>
                </div>
              )}
            </Fade>
          </Card>
        </div>
      </div>
      </>)}
    </>
  );
}
