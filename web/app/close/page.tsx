"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { useData } from "@/lib/data";
import { PageTop, Card, Fade, Details } from "@/components/kit";
import type { FlowNode, FlowEdge } from "@/components/flow";

const Flow = dynamic(() => import("@/components/flow"), { ssr: false });
const ORDER = ["slack", "email", "ticket", "doc", "privacy", "extract", "memory", "agent", "out"];

export default function ClosePage() {
  const meta = useData("/meta", "meta").data;
  const [t, setT] = useState<number | null>(null);
  const [price, setPrice] = useState(false);
  useEffect(() => {
    if (t === null || t > ORDER.length) return;
    const i = setTimeout(() => setT((x) => (x ?? 0) + 1), 380);
    return () => clearTimeout(i);
  }, [t]);
  const src = meta?.docs_by_source ?? {};
  const ran = (id: string) => t !== null && ORDER.indexOf(id) < t;
  const st = (id: string): FlowNode["state"] => (t === null ? "idle" : ran(id) ? "done" : ORDER.indexOf(id) === t ? "running" : "dim");
  const nodes: FlowNode[] = [
    { id: "slack", label: "Slack", icon: "slack", trigger: true, state: st("slack") },
    { id: "email", label: "Email", icon: "email", trigger: true, state: st("email") },
    { id: "ticket", label: "Tickets", icon: "ticket", trigger: true, state: st("ticket") },
    { id: "doc", label: "Docs", icon: "doc", trigger: true, state: st("doc") },
    { id: "privacy", label: "Privacy filter", sub: "DMs excluded · row access policies", icon: "shield", state: st("privacy") },
    { id: "extract", label: "Extract facts", sub: "AI_EXTRACT", icon: "extract", state: st("extract") },
    { id: "memory", label: "Versioned memory", sub: "Time Travel = checkout any date", icon: "history", state: st("memory") },
    { id: "agent", label: "Answer agent", sub: "Cortex Search + Agent", icon: "bot", state: st("agent") },
    { id: "out", label: "Answer · Abstain · Route", icon: "split", state: st("out"), wide: true },
  ];
  const lab = (id: string, s: string) => (ran(id) ? s : undefined);
  const edges: FlowEdge[] = [
    { s: "slack", t: "privacy", label: lab("slack", `${(src.slack ?? 0).toLocaleString()} items`) },
    { s: "email", t: "privacy", label: lab("email", `${src.email ?? 0} items`) },
    { s: "ticket", t: "privacy", label: lab("ticket", `${src.ticket ?? 0} items`) },
    { s: "doc", t: "privacy", label: lab("doc", `${src.doc ?? 0} items`) },
    { s: "privacy", t: "extract", label: lab("privacy", `${meta?.n_docs?.toLocaleString() ?? ""} kept`) },
    { s: "extract", t: "memory", label: lab("extract", `${meta?.n_facts ?? ""} facts`) },
    { s: "memory", t: "agent", label: lab("memory", `${meta?.n_superseded ?? ""} versions replaced`) },
    { s: "agent", t: "out", label: lab("agent", "1 answer, with receipt") },
  ];
  const done = t !== null && t > ORDER.length - 1;
  return (
    <>
      <PageTop title="Built on Snowflake. Private by design." action={t === null ? "Execute workflow" : "Run again"} onAction={() => setT(0)} />
      <Card title="How Keepline works" right={<span className="text-[13px] text-muted">runs inside your Snowflake account</span>}>
        <Flow nodes={nodes} edges={edges} height={420} />
        <Fade show={done} className="mt-4 flex items-center justify-between rounded-[18px] bg-surface2 px-5 py-4">
          <div className="text-[15px] text-muted">Which days does the recon job skip?</div>
          <div className="text-[17px] font-medium">The 1st and the 15th. Sarah Chen, Aug 31.</div>
        </Fade>
      </Card>
      <div className="mt-4 grid grid-cols-[1.4fr_1fr] gap-4">
        <Card dark>
          <div className="text-[30px] font-medium leading-[1.2] tracking-[-0.015em]">
            Glean finds what your company knows.
            <br />
            <span className="text-white/50">Keepline shows what it&apos;s about to forget.</span>
          </div>
          <div className="mt-6 text-[14px] text-white/60">DMs off by default · every employee reviews what was captured · never used for performance reviews</div>
        </Card>
        <Card title="Pricing" right={<Details onClick={() => setPrice(!price)} open={price}>{price ? "Less" : "Market"}</Details>}>
          <div className="flex items-end gap-3">
            <span className="text-[48px] font-medium leading-none tracking-[-0.03em]"><span className="text-[#b0b0b8]">$</span>8–20</span>
            <span className="pb-1 text-[14px] text-muted">per user / month<br />+ handoff pack per departure</span>
          </div>
          <div className="mt-3 text-[14px] text-muted">Starts with a free knowledge risk scan.</div>
          <Fade show={price} className="mt-4 space-y-1.5 text-[14px] text-muted">
            <div>For 20–250 person firms, below Glean&apos;s ~100-seat, $50K+ floor.</div>
            <div>92% of organizations fail to capture retiree knowledge (Deloitte).</div>
            <div>Only 9% of Canadian SMB owners have a succession plan (CFIB).</div>
          </Fade>
        </Card>
      </div>
    </>
  );
}
