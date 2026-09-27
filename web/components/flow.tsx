"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useMemo } from "react";
import { ReactFlow, Background, BackgroundVariant, Controls, Handle, Position, MarkerType, type Node, type Edge, type NodeProps } from "@xyflow/react";
import dagre from "@dagrejs/dagre";
import {
  User, Database, KeyRound, TriangleAlert, Repeat, Contact, UserCheck, History, Hash, Mail, Ticket, FileText, ShieldCheck, ScanText,
  Bot, Split, HelpCircle, SlidersHorizontal, Dices, Scale, Trophy, Check, Server, Lock, Globe,
} from "lucide-react";
import { cn } from "./ui";

export const ICONS: Record<string, any> = {
  user: User, db: Database, key: KeyRound, mine: TriangleAlert, repeat: Repeat, contact: Contact, owner: UserCheck, history: History,
  slack: Hash, email: Mail, ticket: Ticket, doc: FileText, shield: ShieldCheck, extract: ScanText, bot: Bot, split: Split, q: HelpCircle,
  features: SlidersHorizontal, dice: Dices, scale: Scale, trophy: Trophy, server: Server, lock: Lock, globe: Globe,
};

export type FlowNode = {
  id: string;
  label: string;
  sub?: string;
  icon: string;
  trigger?: boolean;
  state?: "idle" | "running" | "done" | "risk" | "dim";
  wide?: boolean;
};
export type FlowEdge = { s: string; t: string; label?: string; dashed?: boolean; back?: boolean };

function N8nNode({ data }: NodeProps) {
  const d = data as unknown as FlowNode & { selected?: boolean };
  const I = ICONS[d.icon] ?? Database;
  const border =
    d.state === "risk" ? "border-alarm" : d.state === "done" ? "border-[#1f9d55]" : d.state === "running" ? "border-sig" : "border-[#d9d9de]";
  return (
    <div className={cn("flex w-[150px] flex-col items-center transition-opacity duration-500", d.state === "dim" && "opacity-35")}>
      <div
        className={cn(
          "relative flex h-[84px] items-center justify-center border-2 bg-white transition-colors duration-300",
          d.wide ? "w-[120px]" : "w-[84px]",
          d.trigger ? "rounded-l-[42px] rounded-r-[14px]" : "rounded-[14px]",
          border,
          d.state === "running" && "shadow-[0_0_0_4px_rgba(17,17,17,0.08)]",
          d.selected && "ring-2 ring-[#111]/15",
        )}
      >
        <Handle type="target" position={Position.Left} className="!h-2.5 !w-2.5 !border-2 !border-[#b0b0b8] !bg-white" />
        <I className={cn("h-8 w-8", d.state === "risk" ? "text-alarm" : "text-[#1d1d1f]")} strokeWidth={1.4} />
        {d.state === "done" && (
          <span className="absolute -right-2 -top-2 flex h-5 w-5 items-center justify-center rounded-full bg-[#1f9d55] text-white">
            <Check className="h-3 w-3" strokeWidth={3} />
          </span>
        )}
        <Handle type="source" position={Position.Right} className="!h-2.5 !w-2.5 !border-2 !border-[#b0b0b8] !bg-white" />
      </div>
      <div className="mt-2 text-center text-[15px] font-medium leading-tight text-fg">{d.label}</div>
      {d.sub && <div className={cn("mt-0.5 line-clamp-2 text-center text-[13px] leading-tight", d.state === "risk" ? "text-alarm" : "text-muted")}>{d.sub}</div>}
    </div>
  );
}

const nodeTypes = { n8n: N8nNode };

function layout(nodes: FlowNode[], edges: FlowEdge[]) {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: 22, ranksep: 58, marginx: 10, marginy: 10 });
  g.setDefaultEdgeLabel(() => ({}));
  nodes.forEach((n) => g.setNode(n.id, { width: 150, height: 128 }));
  edges.filter((e) => !e.back).forEach((e) => g.setEdge(e.s, e.t));
  dagre.layout(g);
  return nodes.map((n) => {
    const p = g.node(n.id);
    return { id: n.id, x: p.x - 75, y: p.y - 64 };
  });
}

export default function Flow({ nodes, edges, height = 520, onNodeClick, selected }: { nodes: FlowNode[]; edges: FlowEdge[]; height?: number; onNodeClick?: (id: string) => void; selected?: string | null }) {
  const structure = nodes.map((n) => n.id).join("|") + "#" + edges.map((e) => e.s + ">" + e.t).join("|");
  const pos = useMemo(() => layout(nodes, edges), [structure]); // eslint-disable-line react-hooks/exhaustive-deps
  const rfNodes: Node[] = nodes.map((n) => {
    const p = pos.find((x) => x.id === n.id)!;
    return { id: n.id, type: "n8n", position: { x: p.x, y: p.y }, data: { ...n, selected: selected === n.id } as any, draggable: true };
  });
  const rfEdges: Edge[] = edges.map((e, i) => ({
    id: `e${i}`,
    source: e.s,
    target: e.t,
    type: e.back ? "smoothstep" : "default",
    label: e.label,
    animated: false,
    style: { stroke: e.back ? "#c7c7cc" : "#b0b0b8", strokeWidth: 1.5, strokeDasharray: e.dashed || e.back ? "5 4" : undefined },
    markerEnd: { type: MarkerType.ArrowClosed, color: "#b0b0b8", width: 16, height: 16 },
    labelStyle: { fontSize: 13, fill: "#6e6e73", fontFamily: "var(--font-hanken)" },
    labelBgStyle: { fill: "#f4f5f7" },
    labelBgPadding: [6, 3] as [number, number],
    labelBgBorderRadius: 6,
  }));
  return (
    <div style={{ height }} className="overflow-hidden rounded-[18px] bg-[var(--flow)]">
      <ReactFlow
        key={structure}
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.08, maxZoom: 1.15 }}
        minZoom={0.3}
        maxZoom={1.6}
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_, n) => onNodeClick?.(n.id)}
        nodesConnectable={false}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1.2} color="#d4d4d8" />
        <Controls position="bottom-left" showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
