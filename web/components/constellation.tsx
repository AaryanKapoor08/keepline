"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";
import { KIND_COLOR, riskColor } from "@/lib/data";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

type Props = {
  graph: { nodes: any[]; links: any[] };
  mode: "org" | "person";
  asOf?: string; // YYYY-MM-DD: replay the versioned memory (person mode)
  width: number;
  height: number;
  onNodeClick?: (n: any) => void;
  onHover?: (n: any | null) => void;
  focusId?: string | null;
};

const ALARM = "#ff4d5e";
const ACCENT = "#2ee6d0";

function diamond(ctx: CanvasRenderingContext2D, x: number, y: number, r: number) {
  ctx.beginPath();
  ctx.moveTo(x, y - r);
  ctx.lineTo(x + r, y);
  ctx.lineTo(x, y + r);
  ctx.lineTo(x - r, y);
  ctx.closePath();
}

export default function Constellation({ graph, mode, asOf, width, height, onNodeClick, onHover, focusId }: Props) {
  const fgRef = useRef<any>(null);
  const [hover, setHover] = useState<any>(null);
  const t0 = useRef(0);
  useEffect(() => {
    t0.current = performance.now();
  }, []);

  // keep stable object identity so positions persist while the time slider filters
  const all = useMemo(() => {
    const nodes = graph.nodes.map((n) => ({ ...n }));
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const links = graph.links.filter((l) => byId.has(l.source?.id ?? l.source) && byId.has(l.target?.id ?? l.target)).map((l) => ({ ...l }));
    return { nodes, links, byId };
  }, [graph]);

  const data = useMemo(() => {
    if (mode !== "person" || !asOf) return { nodes: all.nodes, links: all.links };
    const vis = new Set<string>();
    for (const n of all.nodes) {
      if (n.type === "fact") {
        if ((n.valid_from ?? "") <= asOf) vis.add(n.id);
      } else if (n.type !== "doc") vis.add(n.id);
    }
    const links = all.links.filter((l) => {
      const s = l.source?.id ?? l.source;
      const t = l.target?.id ?? l.target;
      if (l.rel === "supported_by") return vis.has(s);
      return vis.has(s) && vis.has(t);
    });
    for (const l of links) if (l.rel === "supported_by") vis.add(l.target?.id ?? l.target);
    return { nodes: all.nodes.filter((n) => vis.has(n.id)), links };
  }, [all, asOf, mode]);

  const isCurrent = (n: any) => {
    if (n.type !== "fact") return true;
    if (mode === "person" && asOf) return !n.valid_to || n.valid_to > asOf;
    return n.is_current !== false;
  };

  useEffect(() => {
    const fg = fgRef.current;
    if (!fg) return;
    fg.d3Force("charge")?.strength(mode === "org" ? -320 : -70);
    fg.d3Force("link")?.distance((l: any) => (l.rel === "knows" ? 130 : l.rel === "supported_by" ? 18 : l.rel === "supersedes" ? 30 : 45));
  }, [mode, data]);

  useEffect(() => {
    const id = setTimeout(() => fgRef.current?.zoomToFit(700, 60), 1400);
    return () => clearTimeout(id);
  }, [graph, mode]);

  const neighbors = useMemo(() => {
    const m = new Map<string, Set<string>>();
    for (const l of data.links) {
      const s = l.source?.id ?? l.source;
      const t = l.target?.id ?? l.target;
      if (!m.has(s)) m.set(s, new Set());
      if (!m.has(t)) m.set(t, new Set());
      m.get(s)!.add(t);
      m.get(t)!.add(s);
    }
    return m;
  }, [data]);

  const hot = hover?.id ?? focusId ?? null;
  const lit = (id: string) => !hot || id === hot || neighbors.get(hot)?.has(id);

  return (
    <ForceGraph2D
      ref={fgRef}
      graphData={data}
      width={width}
      height={height}
      backgroundColor="rgba(0,0,0,0)"
      cooldownTicks={180}
      d3VelocityDecay={0.28}
      nodeRelSize={4}
      enableNodeDrag
      onNodeHover={(n: any) => {
        setHover(n);
        onHover?.(n);
      }}
      onNodeClick={(n: any) => onNodeClick?.(n)}
      linkColor={(l: any) => {
        const s = l.source?.id ?? l.source;
        const t = l.target?.id ?? l.target;
        const on = !hot || s === hot || t === hot;
        if (l.rel === "supersedes") return `rgba(214,180,106,${on ? 0.9 : 0.25})`;
        if (l.rel === "knows" || l.rel === "owns") {
          const tn = all.byId.get(t);
          const risky = (tn?.risk ?? 0) >= 0.35 || (tn?.bus_factor === 1 && mode === "org");
          return risky ? `rgba(255,77,94,${on ? 0.45 : 0.08})` : `rgba(46,230,208,${on ? 0.35 : 0.06})`;
        }
        return `rgba(148,180,200,${on ? 0.22 : 0.05})`;
      }}
      linkWidth={(l: any) => (l.rel === "supersedes" ? 2.2 : l.rel === "knows" ? 0.6 + 2.4 * (l.weight ?? 0.5) : 0.6)}
      linkLineDash={(l: any) => (l.rel === "supersedes" ? [4, 3] : null)}
      linkDirectionalParticles={(l: any) => (l.rel === "supersedes" ? 4 : l.rel === "knows" ? Math.ceil(3 * (l.weight ?? 0.3)) : l.rel === "stated" ? 1 : 0)}
      linkDirectionalParticleSpeed={(l: any) => (l.rel === "supersedes" ? 0.012 : 0.004)}
      linkDirectionalParticleWidth={(l: any) => (l.rel === "supersedes" ? 3.2 : 1.8)}
      linkDirectionalParticleColor={(l: any) => {
        if (l.rel === "supersedes") return "#d6b46a";
        const t = all.byId.get(l.target?.id ?? l.target);
        return (t?.risk ?? 0) >= 0.35 ? ALARM : ACCENT;
      }}
      nodeLabel={() => ""}
      nodeCanvasObjectMode={() => "replace"}
      nodeCanvasObject={(n: any, ctx: CanvasRenderingContext2D, scale: number) => {
        if (!Number.isFinite(n.x) || !Number.isFinite(n.y)) return;
        const on = lit(n.id);
        const a = on ? 1 : 0.18;
        const t = (performance.now() - t0.current) / 1000;
        ctx.globalAlpha = a;
        if (n.type === "person") {
          const leaving = !!n.departure_date;
          const r = mode === "person" ? 13 : 9;
          const col = leaving ? (n.pid === "sarah" || n.id === "person:sarah" ? ALARM : "#d6b46a") : "#9fb3bf";
          ctx.shadowColor = col;
          ctx.shadowBlur = leaving ? 18 + 6 * Math.sin(t * 3) : 6;
          ctx.fillStyle = "#0b1117";
          ctx.beginPath();
          ctx.arc(n.x, n.y, r, 0, 2 * Math.PI);
          ctx.fill();
          ctx.lineWidth = 2;
          ctx.strokeStyle = col;
          ctx.stroke();
          ctx.shadowBlur = 0;
          ctx.fillStyle = "#e8eef2";
          ctx.font = `600 ${r * 0.8}px Geist, sans-serif`;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          const ini = String(n.label).split(" ").map((s: string) => s[0]).join("").slice(0, 2);
          ctx.fillText(ini, n.x, n.y + 0.5);
          if (scale > 0.9 || mode === "person") {
            ctx.font = `500 ${Math.max(4, 11 / scale)}px Geist, sans-serif`;
            ctx.fillStyle = "rgba(232,238,242,0.85)";
            ctx.fillText(n.label, n.x, n.y + r + 8 / scale + 3);
          }
        } else if (n.type === "area") {
          const risk = n.risk ?? (n.score ?? 0.4);
          const col = mode === "org" ? riskColor(n.risk ?? 0) : ACCENT;
          const r = mode === "org" ? 6 + 3 * (n.criticality ?? 2) : 6 + 8 * (n.score ?? 0.3);
          const bf1 = mode === "org" && n.bus_factor === 1 && (n.risk ?? 0) >= 0.3;
          if (bf1) {
            const pulse = 1 + 0.25 * Math.sin(t * 2.4);
            const g = ctx.createRadialGradient(n.x, n.y, r * 0.5, n.x, n.y, r * 3 * pulse);
            g.addColorStop(0, "rgba(255,77,94,0.45)");
            g.addColorStop(1, "rgba(255,77,94,0)");
            ctx.fillStyle = g;
            ctx.beginPath();
            ctx.arc(n.x, n.y, r * 3 * pulse, 0, 2 * Math.PI);
            ctx.fill();
          }
          ctx.shadowColor = col;
          ctx.shadowBlur = 12;
          ctx.fillStyle = col + (mode === "org" ? "33" : "22");
          ctx.beginPath();
          ctx.arc(n.x, n.y, r, 0, 2 * Math.PI);
          ctx.fill();
          ctx.lineWidth = 1.6;
          ctx.strokeStyle = col;
          ctx.stroke();
          ctx.shadowBlur = 0;
          void risk;
          ctx.font = `600 ${Math.max(4, 12 / scale)}px Geist, sans-serif`;
          ctx.textAlign = "center";
          ctx.textBaseline = "top";
          ctx.fillStyle = "rgba(232,238,242,0.92)";
          ctx.fillText(n.label, n.x, n.y + r + 3);
          if (bf1) {
            ctx.font = `600 ${Math.max(3, 9.5 / scale)}px Geist Mono, monospace`;
            ctx.fillStyle = ALARM;
            ctx.fillText("BUS FACTOR 1", n.x, n.y + r + 3 + 14 / scale);
          }
        } else if (n.type === "fact") {
          const cur = isCurrent(n);
          const col = KIND_COLOR[n.kind] ?? "#6b7f8c";
          ctx.globalAlpha = a * (cur ? 1 : 0.35);
          if (n.kind === "landmine") {
            ctx.shadowColor = ALARM;
            ctx.shadowBlur = 10;
            ctx.fillStyle = ALARM;
            diamond(ctx, n.x, n.y, 5.5);
            ctx.fill();
            ctx.shadowBlur = 0;
          } else {
            ctx.fillStyle = col;
            ctx.beginPath();
            ctx.arc(n.x, n.y, 3.4, 0, 2 * Math.PI);
            ctx.fill();
          }
          if (!cur) {
            ctx.strokeStyle = "#d6b46a";
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(n.x - 6, n.y);
            ctx.lineTo(n.x + 6, n.y);
            ctx.stroke();
          }
          if (hot === n.id || (focusId && neighbors.get(focusId)?.has(n.id) && scale > 2.2)) {
            ctx.globalAlpha = 1;
            ctx.font = `500 ${Math.max(3, 10 / scale)}px Geist, sans-serif`;
            ctx.textAlign = "left";
            ctx.textBaseline = "middle";
            ctx.fillStyle = "#e8eef2";
            ctx.fillText(String(n.label).slice(0, 70), n.x + 8, n.y);
          }
        } else {
          ctx.fillStyle = "rgba(148,180,200,0.55)";
          ctx.fillRect(n.x - 1.5, n.y - 1.5, 3, 3);
        }
        ctx.globalAlpha = 1;
      }}
      nodePointerAreaPaint={(n: any, color: string, ctx: CanvasRenderingContext2D) => {
        if (!Number.isFinite(n.x)) return;
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.type === "person" ? 14 : n.type === "area" ? 14 : 6, 0, 2 * Math.PI);
        ctx.fill();
      }}
      autoPauseRedraw={false}
    />
  );
}
