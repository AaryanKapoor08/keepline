"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { ReactFlow, Background, BackgroundVariant, Controls, Handle, Position, MarkerType, type Node, type Edge, type NodeProps } from "@xyflow/react";
import { Database } from "lucide-react";
import { cn } from "./ui";
import { cssVar } from "@/lib/data";

export const TEAMS: { id: string; label: string; side: "L" | "R" }[] = [
  { id: "engineering", label: "Engineering", side: "L" },
  { id: "operations", label: "Compliance", side: "L" },
  { id: "finance", label: "Finance", side: "L" },
  { id: "it", label: "IT", side: "R" },
  { id: "member_services", label: "Member services", side: "R" },
  { id: "leadership", label: "Leadership", side: "R" },
];

const PW = 230, PH = 62, PAD = 14, HEAD = 36, GAP = 22;
const fmt = (d?: string | null) => (d ? new Date(d + "T12:00:00").toLocaleDateString("en-CA", { month: "short", day: "numeric" }) : "");

function TeamNode({ data }: NodeProps) {
  const d = data as any;
  return (
    <div className={cn("h-full w-full rounded-[20px] bg-surface2 transition-opacity duration-500", d.dim && "opacity-40")}>
      <div className="px-4 pt-2.5 text-[13px] font-medium text-muted">{d.label}</div>
    </div>
  );
}

function PersonNode({ data }: NodeProps) {
  const d = data as any;
  const ini = String(d.name).split(" ").map((x: string) => x[0]).join("").slice(0, 2);
  return (
    <div className={cn("flex h-[62px] w-[230px] cursor-pointer items-center gap-3 rounded-[16px] border bg-white px-3 transition-all", d.selected ? "border-sig shadow-[0_0_0_3px_rgba(17,17,17,0.08)]" : d.tag ? "border-alarm" : "border-[var(--line)] hover:border-[#b0b0b8]", d.dim && "opacity-20")}>
      <Handle type="source" position={d.side === "L" ? Position.Right : Position.Left} className="!h-2 !w-2 !border-2 !border-[#b0b0b8] !bg-white" />
      <span className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[13px] font-medium", d.leaving ? "bg-sig text-white" : "bg-surface2 text-fg")}>{ini}</span>
      <div className="min-w-0">
        <div className="truncate text-[14px] font-medium leading-tight">{d.name}</div>
        <div className="truncate text-[12px] leading-tight text-muted">{d.role}</div>
        {d.tag ? <div className="truncate text-[12px] font-medium leading-tight text-alarm">{d.tag}</div> : d.leaving && <div className="text-[12px] font-medium leading-tight text-alarm">leaves {fmt(d.leaving)}</div>}
        {d.joining && <div className="text-[12px] font-medium leading-tight text-fg">joins {fmt(d.joining)}</div>}
      </div>
    </div>
  );
}

function AreaNode({ data }: NodeProps) {
  const d = data as any;
  return (
    <div className={cn("relative flex h-[48px] w-[210px] cursor-pointer items-center gap-2.5 rounded-[14px] border-2 bg-white px-3 transition-opacity duration-500", d.bf1 ? "border-alarm" : "border-[#d9d9de]", d.lit && "shadow-[0_0_0_4px_rgba(17,17,17,0.07)]", d.dim && "opacity-20")}>
      {d.rules ? <span className="absolute -right-3 -top-3 rounded-full bg-alarm px-2 py-0.5 text-[11px] font-medium text-white">{d.rules} rules</span> : null}
      <Handle id="l" type="target" position={Position.Left} className="!h-2 !w-2 !border-2 !border-[#b0b0b8] !bg-white" />
      <Database className={cn("h-4 w-4 shrink-0", d.bf1 ? "text-alarm" : "text-fg")} strokeWidth={1.6} />
      <div className="min-w-0">
        <div className="truncate text-[13px] font-medium leading-tight">{d.label}</div>
        <div className={cn("text-[12px] leading-tight", d.bf1 ? "text-alarm" : "text-muted")}>{d.bf1 ? "only 1 person knows it" : `${d.bf} people know it`}</div>
      </div>
      <Handle id="r" type="target" position={Position.Right} className="!h-2 !w-2 !border-2 !border-[#b0b0b8] !bg-white" />
    </div>
  );
}

const nodeTypes = { team: TeamNode, person: PersonNode, area: AreaNode };
const SHORT: Record<string, string> = {
  reconciliation: "Reconciliation", corelink_api: "CoreLink API", ssl_dns: "SSL & DNS", ach_payments: "ACH payments", member_portal: "Member portal",
  identity_access: "Identity & access", backups_dr: "Backups & DR", fintrac_reporting: "FINTRAC & AML", payroll: "Payroll", card_processing: "Card processing",
};

export type SimOverlay = { areas: string[]; people: string[]; tags: Record<string, string>; rules: Record<string, number>; pairs: { p: string; a: string; label: string }[] };

export default function OrgFlow({ people, risk, selected, focusTeam, onPerson, sim, onArea, height = 560 }: { people: any[]; risk: any[]; selected?: string | null; focusTeam?: string | null; onPerson: (id: string) => void; sim?: SimOverlay | null; onArea?: (id: string) => void; height?: number }) {
  const SIG = cssVar("--sig", "#1D4ED8");
  const nodes: Node[] = [];
  const pos: Record<string, { x: number; y: number; side: "L" | "R" }> = {};
  const colY = { L: 0, R: 0 };
  const colX = { L: 0, R: PW + 2 * PAD + 180 + 210 + 180 };
  for (const t of TEAMS) {
    const members = people.filter((p) => p.team === t.id);
    if (!members.length) continue;
    const h = HEAD + members.length * (PH + 10) + PAD - 10 + 4;
    const gid = `team:${t.id}`;
    nodes.push({ id: gid, type: "team", position: { x: colX[t.side], y: colY[t.side] }, data: { label: t.label, dim: focusTeam && focusTeam !== t.id }, style: { width: PW + 2 * PAD, height: h }, draggable: false, selectable: false });
    members.forEach((p, i) => {
      const y = HEAD + i * (PH + 10);
      nodes.push({
        id: p.id, type: "person", parentId: gid, extent: "parent", position: { x: PAD, y }, draggable: false,
        data: { name: p.name, role: p.role, side: t.side, leaving: p.departure_date, joining: p.start_date > "2026-09-04" ? p.start_date : null, selected: selected === p.id, dim: sim ? !sim.people.includes(p.id) : focusTeam && focusTeam !== t.id, tag: sim?.tags[p.id] },
      });
      pos[p.id] = { x: colX[t.side] + PAD, y: colY[t.side] + y + PH / 2, side: t.side };
    });
    colY[t.side] += h + GAP;
  }
  const strong: { p: string; a: string }[] = [];
  for (const r of risk) for (const e of r.experts.slice(0, Math.max(1, r.bus_factor))) if (pos[e[0]]) strong.push({ p: e[0], a: r.area_id });
  const focusAreas = new Set(strong.filter((s) => !focusTeam || people.find((p) => p.id === s.p)?.team === focusTeam).map((s) => s.a));
  const areas = [...risk].sort((a, b) => {
    const m = (id: string) => {
      const ys = strong.filter((s) => s.a === id).map((s) => pos[s.p].y);
      return ys.length ? ys.reduce((x, y) => x + y, 0) / ys.length : 9999;
    };
    return m(a.area_id) - m(b.area_id);
  });
  const total = Math.max(colY.L, colY.R) - GAP;
  const step = total / areas.length;
  areas.forEach((r, i) => {
    nodes.push({ id: `a:${r.area_id}`, type: "area", position: { x: PW + 2 * PAD + 180, y: i * step + (step - 48) / 2 }, draggable: false, data: { label: SHORT[r.area_id] ?? r.area_name, bf1: r.bus_factor <= 1, bf: r.bus_factor, dim: sim ? !sim.areas.includes(r.area_id) : focusTeam && !focusAreas.has(r.area_id), lit: sim?.areas.includes(r.area_id), rules: sim?.rules[r.area_id] } });
  });
  const edges: Edge[] = strong.map((s, i) => {
    const on = selected === s.p;
    const dim = sim ? !(sim.areas.includes(s.a) && sim.people.includes(s.p)) : focusTeam && people.find((p) => p.id === s.p)?.team !== focusTeam;
    return {
      id: `e${i}`, source: s.p, target: `a:${s.a}`, targetHandle: pos[s.p].side === "L" ? "l" : "r", type: "default",
      style: { stroke: on || (sim && !dim) ? SIG : "#c7c7cc", strokeWidth: on || (sim && !dim) ? 2 : 1.4, opacity: dim ? 0.15 : 1, transition: "opacity .6s" },
      markerEnd: { type: MarkerType.ArrowClosed, color: on ? SIG : "#c7c7cc", width: 14, height: 14 },
    };
  });
  for (const [i, pr] of (sim?.pairs ?? []).entries()) {
    if (!pos[pr.p]) continue;
    edges.push({
      id: `pair${i}`, source: pr.p, target: `a:${pr.a}`, targetHandle: pos[pr.p].side === "L" ? "l" : "r", type: "default", label: pr.label,
      style: { stroke: SIG, strokeWidth: 1.8, strokeDasharray: "6 5" }, animated: true,
      labelStyle: { fontSize: 12, fill: SIG, fontWeight: 500 }, labelBgStyle: { fill: "#ffffff" }, labelBgPadding: [6, 3] as [number, number], labelBgBorderRadius: 6,
      markerEnd: { type: MarkerType.ArrowClosed, color: SIG, width: 14, height: 14 },
    });
  }
  return (
    <div style={{ height }} className="overflow-hidden rounded-[18px] bg-[var(--flow)]">
      <ReactFlow
        key={focusTeam ?? "all"}
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.06 }}
        minZoom={0.3}
        maxZoom={1.6}
        proOptions={{ hideAttribution: true }}
        nodesConnectable={false}
        onNodeClick={(_, n) => (n.type === "person" ? onPerson(n.id) : n.type === "area" ? onArea?.(n.id.slice(2)) : null)}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1.2} color="#d4d4d8" />
        <Controls position="bottom-left" showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
