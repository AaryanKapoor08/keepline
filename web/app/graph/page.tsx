"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Play, Pause, GitCommitHorizontal, ArrowLeft, History } from "lucide-react";
import Constellation from "@/components/constellation";
import { useData, KIND_COLOR, KIND_LABEL, fmtDate, getJSON } from "@/lib/data";
import { Badge, LiveDot, PageHeader, cn } from "@/components/ui";

const D0 = new Date("2026-03-01T12:00:00").getTime();
const D1 = new Date("2026-09-04T12:00:00").getTime();
const DAYS = Math.round((D1 - D0) / 864e5);
const dayToIso = (d: number) => new Date(D0 + d * 864e5).toISOString().slice(0, 10);

function useSize(ref: React.RefObject<HTMLDivElement | null>) {
  const [s, setS] = useState({ w: 900, h: 600 });
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setS({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, [ref]);
  return s;
}

export default function GraphPage() {
  const org = useData("/graph/org", "graph_org");
  const [person, setPerson] = useState<string | null>(null);
  const [pg, setPg] = useState<any>(null);
  const [day, setDay] = useState(DAYS);
  const [playing, setPlaying] = useState(false);
  const [hover, setHover] = useState<any>(null);
  const box = useRef<HTMLDivElement>(null);
  const { w, h } = useSize(box);

  useEffect(() => {
    if (!person) return;
    getJSON(`/graph/person/${person}`, `graph_person_${person}`).then((r) => setPg(r.data));
  }, [person]);

  useEffect(() => {
    if (!playing) return;
    const i = setInterval(() => {
      setDay((d) => {
        if (d >= DAYS) {
          setPlaying(false);
          return DAYS;
        }
        return Math.min(DAYS, d + 2);
      });
    }, 45);
    return () => clearInterval(i);
  }, [playing]);

  const asOf = dayToIso(day);
  const graph = person ? pg : org.data;

  const facts = useMemo(() => (pg?.nodes ?? []).filter((n: any) => n.type === "fact" && n.valid_from <= asOf), [pg, asOf]);
  const versions = useMemo(() => {
    if (!pg) return [];
    const byId = new Map<string, any>(pg.nodes.map((n: any) => [n.id.replace("fact:", ""), n]));
    return pg.nodes
      .filter((n: any) => n.type === "fact" && n.supersedes && byId.has(n.supersedes))
      .map((n: any) => ({ old: byId.get(n.supersedes), neu: n }))
      .sort((a: any, b: any) => (a.neu.valid_from < b.neu.valid_from ? -1 : 1));
  }, [pg]);
  const kindCounts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const f of facts) c[f.kind] = (c[f.kind] ?? 0) + 1;
    return c;
  }, [facts]);

  const startReplay = () => {
    setDay(0);
    setPlaying(true);
  };

  return (
    <div>
      <PageHeader
        eyebrow="02 · Knowledge constellation"
        title={person ? "Sarah's knowledge, replayed" : "Where Harbourline's knowledge lives"}
        sub={
          person
            ? "Every node is a fact captured from her own messages and tickets, with its receipts. Drag time: facts appear as they are learned; superseded facts dim and link to what replaced them."
            : "People → areas → the facts that matter → receipts. Red means one departure away from lost. Click Sarah."
        }
        right={
          <div className="flex items-center gap-3">
            <LiveDot live={org.live} />
            {person && (
              <button onClick={() => { setPerson(null); setPg(null); setDay(DAYS); }} className="flex items-center gap-1.5 rounded-full border border-line px-3 py-1.5 text-[13px] text-muted hover:text-fg">
                <ArrowLeft className="h-3.5 w-3.5" /> Whole org
              </button>
            )}
          </div>
        }
      />
      <div className="grid grid-cols-[1fr_320px] gap-5">
        <div className="glass relative h-[610px] overflow-hidden rounded-2xl" ref={box}>
          <div className="grid-bg pointer-events-none absolute inset-0 opacity-60" />
          {graph && (
            <Constellation
              key={person ?? "org"}
              graph={graph}
              mode={person ? "person" : "org"}
              asOf={person ? asOf : undefined}
              width={w}
              height={h}
              onHover={setHover}
              onNodeClick={(n) => {
                if (!person && n.type === "person") {
                  setPerson(n.pid ?? n.id.replace("person:", ""));
                  setDay(DAYS);
                }
              }}
            />
          )}
          {!person && (
            <button onClick={() => { setPerson("sarah"); setDay(DAYS); }} className="absolute left-4 top-4 flex items-center gap-2 rounded-full border border-alarm/40 bg-alarm/10 px-3.5 py-1.5 text-[13px] font-medium text-alarm backdrop-blur hover:bg-alarm/20">
              <span className="h-2 w-2 rounded-full bg-alarm shadow-[0_0_8px_var(--alarm)]" /> Open Sarah Chen
            </button>
          )}
          {person && (
            <div className="absolute inset-x-4 bottom-4 rounded-xl border border-line bg-bg/80 p-3.5 backdrop-blur-xl">
              <div className="flex items-center gap-3">
                <button onClick={() => (playing ? setPlaying(false) : day >= DAYS ? startReplay() : setPlaying(true))} className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent text-bg shadow-[0_0_16px_rgba(46,230,208,0.5)]">
                  {playing ? <Pause className="h-4 w-4" /> : <Play className="ml-0.5 h-4 w-4" />}
                </button>
                <div className="flex-1">
                  <input type="range" min={0} max={DAYS} value={day} onChange={(e) => { setPlaying(false); setDay(Number(e.target.value)); }} className="w-full" />
                  <div className="mt-0.5 flex justify-between font-mono text-[10.5px] text-dim">
                    {["Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep"].map((m) => <span key={m}>{m}</span>)}
                  </div>
                </div>
                <div className="w-[138px] text-right">
                  <div className="font-mono text-[11px] uppercase tracking-wider text-dim">memory as of</div>
                  <div className="font-mono text-[15px] text-accent">{fmtDate(asOf)}</div>
                </div>
              </div>
            </div>
          )}
          <AnimatePresence>
            {hover && hover.type !== "doc" && (
              <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="pointer-events-none absolute right-4 top-4 max-w-[340px] rounded-xl border border-line bg-bg/90 p-3.5 backdrop-blur-xl">
                <div className="text-[11px] uppercase tracking-wider text-dim">{hover.type === "fact" ? KIND_LABEL[hover.kind] ?? hover.kind : hover.type}</div>
                <div className="mt-1 text-[14px] leading-snug">{hover.label}</div>
                {hover.type === "area" && hover.risk != null && (
                  <div className="mt-2 flex gap-2"><Badge tone={hover.risk >= 0.35 ? "alarm" : "accent"}>risk {(hover.risk * 100).toFixed(0)}</Badge><Badge>bus factor {hover.bus_factor}</Badge></div>
                )}
                {hover.type === "fact" && hover.valid_from && <div className="mt-1.5 font-mono text-[11px] text-dim">valid from {hover.valid_from}{hover.valid_to ? ` → replaced ${hover.valid_to}` : " · current"}</div>}
                {hover.role && <div className="mt-1 text-[12px] text-muted">{hover.role}{hover.departure_date ? ` · leaves ${fmtDate(hover.departure_date)}` : ""}</div>}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <div className="flex flex-col gap-4">
          {!person ? (
            <>
              <div className="glass rounded-2xl p-4">
                <div className="mb-3 text-[12px] uppercase tracking-[0.16em] text-dim">Legend</div>
                <div className="space-y-2.5 text-[13px]">
                  <div className="flex items-center gap-2.5"><span className="h-3 w-3 rounded-full border-2 border-alarm" /> Person leaving (pulses)</div>
                  <div className="flex items-center gap-2.5"><span className="h-3 w-3 rounded-full bg-alarm/40 ring-2 ring-alarm/60" /> Area at risk · bus factor 1 glows</div>
                  <div className="flex items-center gap-2.5"><span className="h-3 w-3 rounded-full bg-accent/30 ring-1 ring-accent" /> Area with redundancy</div>
                  <div className="flex items-center gap-2.5"><span className="h-2.5 w-2.5 rotate-45 bg-alarm" /> Landmine ("never do X")</div>
                  <div className="flex items-center gap-2.5"><span className="h-2 w-2 rounded-full" style={{ background: KIND_COLOR.access }} /> Access · <span className="h-2 w-2 rounded-full" style={{ background: KIND_COLOR.vendor_contact }} /> Vendor · <span className="h-2 w-2 rounded-full" style={{ background: KIND_COLOR.recurring_task }} /> Recurring</div>
                  <div className="flex items-center gap-2.5"><span className="h-1.5 w-1.5 bg-muted" /> Receipt (Slack, email, ticket, doc)</div>
                </div>
              </div>
              <div className="glass rounded-2xl p-4">
                <div className="mb-3 text-[12px] uppercase tracking-[0.16em] text-dim">People</div>
                <div className="space-y-1">
                  {(org.data?.nodes ?? []).filter((n: any) => n.type === "person").map((n: any) => (
                    <button key={n.id} onClick={() => { setPerson(n.pid); setDay(DAYS); }} className="flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left text-[13px] hover:bg-white/[0.04]">
                      <span className={cn(n.pid === "sarah" && "text-alarm")}>{n.label}</span>
                      {n.departure_date && <span className="font-mono text-[11px] text-warn">leaves {n.departure_date.slice(5)}</span>}
                    </button>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <>
              <div className="glass rounded-2xl p-4">
                <div className="flex items-baseline justify-between">
                  <div className="text-[12px] uppercase tracking-[0.16em] text-dim">Captured by {fmtDate(asOf)}</div>
                  <div className="font-mono text-[22px] font-semibold text-accent tabular-nums">{facts.length}</div>
                </div>
                <div className="mt-3 space-y-1.5">
                  {Object.entries(kindCounts).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                    <div key={k} className="flex items-center gap-2 text-[12.5px]">
                      <span className={cn("h-2 w-2", k === "landmine" ? "rotate-45" : "rounded-full")} style={{ background: KIND_COLOR[k] }} />
                      <span className="flex-1 text-muted">{KIND_LABEL[k] ?? k}</span>
                      <span className="font-mono tabular-nums">{v}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="glass flex-1 rounded-2xl p-4">
                <div className="mb-3 flex items-center gap-2 text-[12px] uppercase tracking-[0.16em] text-dim"><History className="h-3.5 w-3.5" /> Version history</div>
                <div className="space-y-3">
                  {versions.filter((v: any) => /recon|skip/i.test(v.neu.label + v.old.label)).concat(versions.filter((v: any) => !/recon|skip/i.test(v.neu.label + v.old.label))).slice(0, 3).map((v: any, i: number) => {
                    const happened = v.neu.valid_from <= asOf;
                    const seenOld = v.old.valid_from <= asOf;
                    return (
                      <div key={i} className={cn("rounded-xl border p-3 transition-all", happened ? "border-warn/40 bg-warn/[0.05]" : "border-line opacity-60")}>
                        <div className={cn("text-[12.5px] leading-snug", happened ? "text-dim line-through decoration-warn/70" : seenOld ? "text-fg" : "text-dim")}>{v.old.label}</div>
                        <div className="my-1.5 flex items-center gap-1.5 font-mono text-[10.5px] text-warn"><GitCommitHorizontal className="h-3.5 w-3.5" /> superseded {fmtDate(v.neu.valid_from)}</div>
                        <div className={cn("text-[13px] font-medium leading-snug", happened ? "text-fg" : "text-dim")}>{v.neu.label}</div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
