"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { ReactFlow, Background, BackgroundVariant, Controls, Handle, Position, MarkerType, type Node, type Edge, type NodeProps } from "@xyflow/react";
import { Database } from "lucide-react";
import { cn } from "./ui";

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
    <div className={cn("h-full w-full rounded-[20px] bg-[#f4f5f7] transition-opacity", d.dim && "opacity-40")}>
      <div className="px-4 pt-2.5 text-[13px] font-medium text-muted">{d.label}</div>
    </div>
  );
}

function PersonNode({ data }: NodeProps) {
  const d = data as any;
  const ini = String(d.name).split(" ").map((x: string) => x[0]).join("").slice(0, 2);
  return (
    <div className={cn("flex h-[62px] w-[230px] cursor-pointer items-center gap-3 rounded-[16px] border bg-white px-3 transition-all", d.selected ? "border-[#111] shadow-[0_0_0_3px_rgba(17,17,17,0.08)]" : "border-[#e5e5ea] hover:border-[#b0b0b8]", d.dim && "opacity-35")}>
      <Handle type="source" position={d.side === "L" ? Position.Right : Position.Left} className="!h-2 !w-2 !border-2 !border-[#b0b0b8] !bg-white" />
      <span className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[13px] font-medium", d.leaving ? "bg-[#111] text-white" : "bg-[#f4f5f7] text-fg")}>{ini}</span>
      <div className="min-w-0">
        <div className="truncate text-[14px] font-medium leading-tight">{d.name}</div>
        <div className="truncate text-[12px] leading-tight text-muted">{d.role}</div>
        {d.leaving && <div className="text-[11.5px] font-medium leading-tight text-alarm">leaves {fmt(d.leaving)}</div>}
        {d.joining && <div className="text-[11.5px] font-medium leading-tight text-fg">joins {fmt(d.joining)}</div>}
      </div>
    </div>
  );
}

function AreaNode({ data }: NodeProps) {
  const d = data as any;
  return (
    <div className={cn("flex h-[48px] w-[210px] items-center gap-2.5 rounded-[14px] border-2 bg-white px-3 transition-opacity", d.bf1 ? "border-alarm" : "border-[#d9d9de]", d.dim && "opacity-35")}>
      <Handle id="l" type="target" position={Position.Left} className="!h-2 !w-2 !border-2 !border-[#b0b0b8] !bg-white" />
      <Database className={cn("h-4 w-4 shrink-0", d.bf1 ? "text-alarm" : "text-fg")} strokeWidth={1.6} />
      <div className="min-w-0">
        <div className="truncate text-[13px] font-medium leading-tight">{d.label}</div>
        <div className={cn("text-[11.5px] leading-tight", d.bf1 ? "text-alarm" : "text-muted")}>{d.bf1 ? "only 1 person knows it" : `${d.bf} people know it`}</div>
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

export default function OrgFlow({ people, risk, selected, focusTeam, onPerson }: { people: any[]; risk: any[]; selected?: string | null; focusTeam?: string | null; onPerson: (id: string) => void }) {
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
        data: { name: p.name, role: p.role, side: t.side, leaving: p.departure_date, joining: p.start_date > "2026-09-04" ? p.start_date : null, selected: selected === p.id, dim: focusTeam && focusTeam !== t.id },
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
    nodes.push({ id: `a:${r.area_id}`, type: "area", position: { x: PW + 2 * PAD + 180, y: i * step + (step - 48) / 2 }, draggable: false, data: { label: SHORT[r.area_id] ?? r.area_name, bf1: r.bus_factor <= 1, bf: r.bus_factor, dim: focusTeam && !focusAreas.has(r.area_id) } });
  });
  const edges: Edge[] = strong.map((s, i) => {
    const on = selected === s.p;
    const dim = focusTeam && people.find((p) => p.id === s.p)?.team !== focusTeam;
    return {
      id: `e${i}`, source: s.p, target: `a:${s.a}`, targetHandle: pos[s.p].side === "L" ? "l" : "r", type: "default",
      style: { stroke: on ? "#111" : "#c7c7cc", strokeWidth: on ? 2 : 1.4, opacity: dim ? 0.25 : 1 },
      markerEnd: { type: MarkerType.ArrowClosed, color: on ? "#111" : "#c7c7cc", width: 14, height: 14 },
    };
  });
  return (
    <div className="h-[560px] overflow-hidden rounded-[18px] bg-[#fafafa]">
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
        onNodeClick={(_, n) => n.type === "person" && onPerson(n.id)}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1.2} color="#d4d4d8" />
        <Controls position="bottom-left" showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
