"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { useData, pname, fmtDate, KIND_LABEL } from "@/lib/data";
import { PageTop, Card, Quote, Fade } from "@/components/kit";
import type { FlowNode, FlowEdge } from "@/components/flow";

const Flow = dynamic(() => import("@/components/flow"), { ssr: false });

const SHORT: Record<string, string> = {
  reconciliation: "Reconciliation", corelink_api: "CoreLink API", ssl_dns: "SSL & DNS", ach_payments: "ACH payments", member_portal: "Member portal",
  identity_access: "Identity & access", backups_dr: "Backups & DR", fintrac_reporting: "FINTRAC", payroll: "Payroll", card_processing: "Card processing",
};
const cut = (s: string, n = 34) => (s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s);

export default function KnowledgePage() {
  const prof = useData("/profile/sarah", "profile_sarah").data;
  const risk = useData("/risk", "risk").data;
  const g = useData("/graph/person/sarah", "graph_person_sarah").data;
  const pack = useData("/handoff/sarah", "handoff_sarah").data;
  const wi = useData("/whatif/sarah", "whatif_sarah").data;
  const [sel, setSel] = useState<string | null>(null);
  const [step, setStep] = useState<number | null>(null);

  const model = useMemo(() => {
    if (!prof || !risk || !g || !wi) return null;
    const riskBy: Record<string, any> = Object.fromEntries(risk.map((r: any) => [r.area_id, r]));
    const facts: any[] = g.nodes.filter((n: any) => n.type === "fact");
    const areas = [...prof.areas].sort((a: any, b: any) => b.score - a.score).slice(0, 4);
    const orph: string[] = wi?.orphaned_areas ?? [];
    const bf1 = areas.filter((a: any) => orph.includes(a.area_id));
    const byId = new Map<string, any>(facts.map((f) => [f.id.replace("fact:", ""), f]));
    const chain = facts
      .filter((f) => f.supersedes && byId.has(f.supersedes) && /skip/i.test(f.label))
      .map((f) => ({ old: byId.get(f.supersedes), neu: f }))[0];
    const owners: Record<string, number> = {};
    for (const it of pack?.items ?? []) if (it.suggested_owner_id && bf1.some((a: any) => a.area_id === it.area_id)) owners[it.suggested_owner_id] = (owners[it.suggested_owner_id] ?? 0) + 1;
    const owner = Object.entries(owners).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "aisha";

    const nodes: FlowNode[] = [{ id: "sarah", label: "Sarah Chen", sub: "last day Sep 11", icon: "user", trigger: true }];
    const edges: FlowEdge[] = [];
    for (const a of areas) {
      const r = riskBy[a.area_id];
      const isBf1 = bf1.includes(a);
      nodes.push({ id: `a:${a.area_id}`, label: SHORT[a.area_id] ?? a.area_name, sub: isBf1 ? "only Sarah" : `${r?.bus_factor ?? "?"} people know it`, icon: "db", state: isBf1 ? "risk" : "idle" });
      edges.push({ s: "sarah", t: `a:${a.area_id}`, label: `${a.n_facts} facts` });
    }
    for (const a of bf1) {
      const af = facts.filter((f) => f.area_id === a.area_id);
      const nl = af.filter((f) => f.kind === "landmine").length;
      const na = af.filter((f) => f.kind === "access").length;
      nodes.push({ id: `i:${a.area_id}`, label: `${nl} landmines`, sub: na ? `${na} access items` : "never-do-this rules", icon: "mine", state: "risk" });
      edges.push({ s: `a:${a.area_id}`, t: `i:${a.area_id}` });
      edges.push({ s: `i:${a.area_id}`, t: "owner", label: "hand over" });
    }
    if (chain && chain.old.area_id) {
      nodes.push({ id: "v:old", label: cut(chain.old.label, 30), sub: `${fmtDate(chain.old.valid_from)} · replaced`, icon: "history", state: "dim" });
      nodes.push({ id: "v:new", label: cut(chain.neu.label, 30), sub: `${fmtDate(chain.neu.valid_from)} · current`, icon: "history" });
      edges.push({ s: `a:${chain.old.area_id}`, t: "v:old" });
      edges.push({ s: "v:old", t: "v:new", label: "replaced by", dashed: true });
    }
    nodes.push({ id: "owner", label: pname(owner), sub: "suggested new owner", icon: "owner" });
    return { nodes, edges, facts, chain, riskBy, owner };
  }, [prof, risk, g, pack, wi]);

  const order = model?.nodes.map((n) => n.id) ?? [];
  useEffect(() => {
    if (step === null) return;
    if (step >= order.length) return;
    const t = setTimeout(() => setStep((s) => (s ?? 0) + 1), 420);
    return () => clearTimeout(t);
  }, [step, order.length]);

  const nodes: FlowNode[] = (model?.nodes ?? []).map((n) => {
    if (step === null) return n;
    const i = order.indexOf(n.id);
    if (i >= step) return { ...n, state: "dim" };
    if (n.id === "v:old") return { ...n, state: step > order.indexOf("v:new") ? "dim" : "done" };
    return { ...n, state: n.state === "risk" ? "risk" : "done" };
  });

  const panel = (() => {
    if (!sel || !model) return null;
    if (sel === "sarah") return { title: "Sarah Chen", body: <div className="text-[15px] text-muted">{prof?.n_facts} facts captured from her own Slack messages, tickets and email. She reviews every one before others rely on it.</div> };
    if (sel === "owner") return { title: pname(model.owner), body: <div className="text-[15px] text-muted">Suggested because they have the next-strongest hands-on evidence in these areas. A manager confirms; nothing feeds performance reviews.</div> };
    if (sel.startsWith("v:") && model.chain) {
      const f = sel === "v:old" ? model.chain.old : model.chain.neu;
      return { title: sel === "v:old" ? "Earlier version" : "Current version", body: <Quote c={{ quote: f.quote || f.label, stated_by: "sarah", date: f.valid_from }} /> };
    }
    const area = sel.split(":")[1];
    const onlyMines = sel.startsWith("i:");
    const list = model.facts.filter((f: any) => f.area_id === area && (!onlyMines || f.kind === "landmine" || f.kind === "access")).slice(0, 5);
    return {
      title: onlyMines ? `${SHORT[area]}: what only she knows` : SHORT[area] ?? area,
      body: (
        <div className="divide-y divide-[#ececec]">
          {list.map((f: any) => (
            <div key={f.id} className="py-3">
              <div className={f.kind === "landmine" ? "text-[12px] font-medium text-alarm" : "text-[12px] text-muted"}>{KIND_LABEL[f.kind] ?? f.kind}</div>
              <Quote c={{ quote: f.quote || f.label, stated_by: "sarah", date: f.valid_from }} small />
            </div>
          ))}
        </div>
      ),
    };
  })();

  return (
    <>
      <PageTop title="Sarah's knowledge, mapped." action="Replay history" onAction={() => { setSel(null); setStep(0); }} />
      <div className="grid grid-cols-[1fr_360px] gap-4">
        <Card className="p-3">
          {model && <Flow nodes={nodes} edges={model.edges} height={580} onNodeClick={setSel} selected={sel} />}
        </Card>
        <Card title={panel?.title ?? "Details"}>
          {panel ? (
            <div className="max-h-[520px] overflow-y-auto pr-1">{panel.body}</div>
          ) : (
            <div className="text-[15px] leading-relaxed text-muted">
              Click any node to see the receipts behind it.
              <Fade show={step !== null && step >= order.length} className="mt-6 rounded-[18px] bg-[#f4f5f7] p-4 text-[15px] text-fg">
                Every fact keeps its history: &ldquo;{model?.chain ? cut(model.chain.old.label, 60) : ""}&rdquo; was replaced on {fmtDate(model?.chain?.neu.valid_from)}.
              </Fade>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
