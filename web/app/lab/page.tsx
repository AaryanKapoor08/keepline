"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { Line, LineChart, ResponsiveContainer, XAxis, YAxis, ReferenceLine, CartesianGrid } from "recharts";
import { useData, cssVar } from "@/lib/data";
import { PageTop, Card, Details, Fade, EASE } from "@/components/kit";
import type { FlowNode, FlowEdge } from "@/components/flow";

const Flow = dynamic(() => import("@/components/flow"), { ssr: false });
const val = (m: any) => (m && typeof m === "object" ? m.value : m) as number | undefined;
const pct = (v?: number) => (v == null ? "—" : `${Math.round(v * 100)}%`);
const cut = (s = "", n = 42) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

function wrongAll(sys: any) {
  const o = sys?.outcomes ?? {};
  const k = (o.hallucination ?? 0) + (o.stale_answer ?? 0);
  const n = sys?.n_questions ?? 0;
  return { v: n ? k / n : undefined, k, n };
}

export default function LabPage() {
  const bt = useData("/results/benchmark_test", "benchmark_test").data;
  const rob = useData("/results/robustness", "robustness").data;
  const log = useData("/results/training_log", "training_log").data;
  const curve = useData("/results/reward_curve", "reward_curve").data;
  const [noise, setNoise] = useState(false);
  const [learn, setLearn] = useState(false);
  const [lvl, setLvl] = useState(0);
  const [t, setT] = useState<number | null>(null);
  const S = bt?.systems;
  const rows: any[] = log?.rows ?? [];
  const SIG = cssVar("--sig", "#1D4ED8");

  useEffect(() => {
    if (t === null) return;
    const i = setTimeout(() => setT((x) => (x === null ? null : x + 1)), 170);
    return () => clearTimeout(i);
  }, [t]);

  const acc = { k: S?.keepline?.accuracy_cited, p: S?.plain?.accuracy_cited };
  const wk = wrongAll(S?.keepline);
  const wp = wrongAll(S?.plain);
  const rk = S?.keepline?.routing_accuracy;
  const rp = S?.plain?.routing_accuracy;
  const ROWS = [
    { l: "Right answers, with a source", k: val(acc.k), p: val(acc.p), kl: pct(val(acc.k)), pl: pct(val(acc.p)), n: `n=${acc.k?.n ?? "—"} answerable` },
    { l: "Confidently wrong", k: wk.v, p: wp.v, kl: pct(wk.v), pl: pct(wp.v), n: `n=${wk.n} questions, both` },
    { l: "Routed to the right person", k: val(rk), p: val(rp), kl: `${rk?.k ?? "—"}/${rk?.n ?? "—"}`, pl: `${rp?.k ?? "—"}/${rp?.n ?? "—"}`, n: `n=${rk?.n ?? "—"} routing questions` },
  ];

  const bins = (sys: any) => (sys?.reliability_bins ?? []).filter((b: any) => b.n > 0).map((b: any) => ({ x: b.confidence, y: b.accuracy }));
  const kb = bins(S?.keepline);
  const pb = bins(S?.plain);

  const rowIdx = t === null ? 0 : Math.min(rows.length - 1, Math.floor(t / 7) * 25);
  const phase = t === null ? -1 : t % 7;
  const r = rows[rowIdx];
  const st = (i: number): FlowNode["state"] => (t === null ? "idle" : i < phase ? "done" : i === phase ? "running" : "dim");
  const nodes: FlowNode[] = [
    { id: "q", label: "Question", sub: t === null ? "from the training split" : cut(r?.question, 40), icon: "q", trigger: true, state: st(0) },
    { id: "f", label: "Context features", sub: t === null ? "area, type, evidence" : `${r?.area_id ?? "?"} · ${r?.qtype}`, icon: "features", state: st(1) },
    { id: "b", label: "Bandit picks policy", sub: t === null ? "28 arms" : r?.arm, icon: "dice", state: st(2) },
    { id: "a", label: "Answer / Abstain / Route", sub: t === null ? "" : r?.action, icon: "split", state: st(3), wide: true },
    { id: "g", label: "Grader vs truth file", sub: t === null ? "never seen by product" : r?.outcome?.replace(/_/g, " "), icon: "scale", state: st(4) },
    { id: "w", label: "Reward", sub: t === null ? "+1 · +0.5 · −0.3 · −2" : `${r?.reward >= 0 ? "+" : ""}${r?.reward?.toFixed(2)}`, icon: "trophy", state: st(5) },
  ];
  const edges: FlowEdge[] = [
    { s: "q", t: "f" }, { s: "f", t: "b" }, { s: "b", t: "a" }, { s: "a", t: "g" }, { s: "g", t: "w" }, { s: "w", t: "b", label: "update", back: true },
  ];
  const frac = rows.length ? rowIdx / (rows.length - 1) : 0;
  const series = curve ? curve.rolling.bandit.map((v: number, i: number) => ({ i, bandit: v, def: curve.rolling.default[i] })) : [];
  const shown = series.slice(0, Math.max(2, Math.round(frac * series.length)));
  const levels: any[] = rob?.levels ?? [];
  const L = levels[lvl];

  return (
    <>
      <PageTop title={`Tested on ${bt?.n_questions ?? 216} questions it had never seen.`} action={learn ? "Hide how it learns" : "How it learns"} onAction={() => { setLearn(!learn); if (!learn) { setT(0); setTimeout(() => document.getElementById("learn")?.scrollIntoView({ behavior: "smooth", block: "center" }), 150); } }} />
      <div className="grid grid-cols-[1.1fr_1fr] gap-4">
        <Card title="Keepline vs plain search" right={<Details onClick={() => setNoise(!noise)} open={noise}>{noise ? "Hide noise" : "Add noise"}</Details>}>
          {ROWS.map((row, i) => (
            <div key={row.l} className="border-b border-[var(--line)] py-4 last:border-0">
              <div className="flex items-baseline justify-between">
                <span className="text-[16px]">{row.l}</span>
                <span className="text-[12px] text-muted">{row.n}</span>
              </div>
              <div className="mt-2 flex items-center gap-3">
                <span className="w-[78px] text-[30px] font-medium tracking-[-0.02em]">{row.kl}</span>
                <div className="h-3 flex-1 rounded-full bg-surface2">
                  <motion.div initial={{ width: 0 }} animate={{ width: `${(row.k ?? 0) * 100}%` }} transition={{ duration: 0.9, delay: i * 0.1, ease: EASE }} className="h-3 rounded-full bg-sig" />
                </div>
              </div>
              <div className="mt-1.5 flex items-center gap-3">
                <span className="w-[78px] text-[15px] text-muted">{row.pl}</span>
                <div className="h-3 flex-1 rounded-full bg-surface2">
                  <motion.div initial={{ width: 0 }} animate={{ width: `${(row.p ?? 0) * 100}%` }} transition={{ duration: 0.9, delay: i * 0.1 + 0.1, ease: EASE }} className="hatch h-3 rounded-full" />
                </div>
              </div>
            </div>
          ))}
          <div className="mt-3 flex gap-4 text-[12px] text-muted">
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-sig" /> Keepline</span>
            <span className="flex items-center gap-1.5"><span className="hatch h-2.5 w-2.5 rounded-full" /> Plain search</span>
            <span>Held-out test split, run once.</span>
          </div>
          <Fade show={noise} className="mt-4 rounded-[18px] bg-surface2 p-4">
            <div className="flex items-center gap-3 text-[13px] text-muted">
              Clean
              <input type="range" min={0} max={Math.max(0, levels.length - 1)} value={lvl} onChange={(e) => setLvl(Number(e.target.value))} className="flex-1 accent-[var(--sig)]" />
              Brutal
            </div>
            <div className="mt-3 flex items-baseline gap-6">
              <div><span className="text-[28px] font-medium">{pct(val(L?.systems?.keepline?.hallucination_rate))}</span> <span className="text-[13px] text-muted">Keepline wrong (of answered)</span></div>
              <div className="text-muted"><span className="text-[22px]">{pct(val(L?.systems?.plain?.hallucination_rate))}</span> <span className="text-[13px]">plain search wrong</span></div>
            </div>
            {L?.examples?.[0] && <div className="mt-2 text-[13px] text-muted">&ldquo;{cut(L.examples[0].after, 110)}&rdquo;</div>}
          </Fade>
        </Card>

        <Card title="Its confidence means something" right={<span className="text-[13px] text-muted">test split · calibration</span>}>
          <div className="flex items-end gap-8">
            <div>
              <div className="text-[56px] font-medium leading-none tracking-[-0.03em] text-[var(--sig)]">{val(S?.keepline?.ece)?.toFixed(2) ?? "—"}</div>
              <div className="mt-1 text-[13px] text-muted">Keepline calibration error</div>
            </div>
            <div>
              <div className="text-[32px] leading-none text-muted">{val(S?.plain?.ece)?.toFixed(2) ?? "—"}</div>
              <div className="mt-1 text-[13px] text-muted">plain search</div>
            </div>
          </div>
          <div className="mt-5 h-[250px] rounded-[18px] bg-surface2 p-3">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart margin={{ top: 8, right: 12, left: -18, bottom: 4 }}>
                <CartesianGrid stroke="rgba(0,0,0,0.05)" />
                <XAxis dataKey="x" type="number" domain={[0.3, 0.9]} tickFormatter={(v) => `${Math.round(v * 100)}%`} tick={{ fontSize: 11, fill: "#8C8F95" }} axisLine={false} tickLine={false} />
                <YAxis type="number" domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} tick={{ fontSize: 11, fill: "#8C8F95" }} axisLine={false} tickLine={false} />
                <ReferenceLine segment={[{ x: 0.3, y: 0.3 }, { x: 0.9, y: 0.9 }]} stroke="#B8B4AB" strokeDasharray="4 4" />
                <Line data={pb} dataKey="y" stroke="#9A9EA5" strokeWidth={1.5} dot={{ r: 3 }} isAnimationActive={false} />
                <Line data={kb} dataKey="y" stroke={SIG} strokeWidth={2} dot={{ r: 3.5 }} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-3 flex flex-wrap gap-4 text-[12.5px] text-muted">
            <span className="flex items-center gap-1.5"><span className="h-0.5 w-4 bg-sig" /> Keepline</span>
            <span className="flex items-center gap-1.5"><span className="h-0.5 w-4 bg-[#9A9EA5]" /> Plain search</span>
            <span>dashed = perfectly calibrated. When Keepline says 60%, it&apos;s right about 60% of the time.</span>
          </div>
        </Card>
      </div>

      {learn && (
        <div className="mt-4 grid grid-cols-[1.6fr_1fr] gap-4" id="learn">
          <Card title="How it learns" right={<span className="text-[13px] text-muted">{t === null ? "" : `training replay · step ${r?.step ?? 0} of ${log?.n ?? ""}`}</span>}>
            <Flow nodes={nodes} edges={edges} height={260} />
          </Card>
          <Card title="Training reward" right={<span className="text-[13px] text-muted">blue = bandit · gray = fixed default</span>}>
            <div className="h-[150px] rounded-[18px] bg-surface2 p-3">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={t === null ? series : shown} margin={{ top: 4, right: 4, left: -30, bottom: -8 }}>
                  <XAxis dataKey="i" hide type="number" domain={[0, Math.max(1, series.length - 1)]} />
                  <YAxis domain={[-1, 1.2]} tick={{ fontSize: 10, fill: "#8C8F95" }} axisLine={false} tickLine={false} />
                  <Line dataKey="def" stroke="#C7C3BA" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                  <Line dataKey="bandit" stroke={SIG} strokeWidth={1.5} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-3 text-[13.5px] leading-relaxed text-muted">
              +1 for a cited answer, +0.5 for a correct &ldquo;ask someone&rdquo;, −2 for a confident wrong answer. Honest result: with 388 training questions, the bandit&apos;s thresholds did not beat the calibrated default on the test split. The calibration above is what generalized.
            </div>
          </Card>
        </div>
      )}
    </>
  );
}
