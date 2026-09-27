"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import { Play, RotateCcw, Lock } from "lucide-react";
import { Line, LineChart, ResponsiveContainer, XAxis, YAxis, Tooltip, ReferenceLine, CartesianGrid, Scatter, ScatterChart, ZAxis } from "recharts";
import { useData } from "@/lib/data";
import { Badge, Empty, LiveDot, PageHeader, cn } from "@/components/ui";

const REWARDS = [
  { o: "Correct answer with valid citation", r: "+1.0" },
  { o: "Correct abstain or correct route", r: "+0.5" },
  { o: "Unnecessary abstain", r: "−0.3" },
  { o: "Confident wrong answer", r: "−2.0" },
];
const OUTCOME_R: Record<string, string> = {
  correct_cited: "+1.0", correct_uncited: "+0", correct_abstain: "+0.5", correct_route: "+0.5", unnecessary_abstain: "−0.3", wrong_route: "−", hallucination: "−2.0", stale_answer: "−2.0",
};
const SYS: Record<string, { label: string; color: string }> = {
  plain: { label: "Plain search", color: "#8a9aa6" },
  keepline: { label: "Keepline", color: "#2ee6d0" },
  keepline_rl: { label: "Keepline + bandit", color: "#4fb3a8" },
};
const metricVal = (m: any) => (m == null ? null : typeof m === "number" ? m : m.value ?? null);
const metricN = (m: any) => (m == null || typeof m === "number" ? null : m.n ?? null);

function Loop({ row }: { row: any }) {
  const stages = [
    { k: "Question", v: row?.question ?? "—" },
    { k: "Context features", v: row ? `${row.area_id ?? "?"} · ${row.qtype}` : "—" },
    { k: "Bandit picks arm", v: row?.arm ?? "—", mono: true },
    { k: "Action", v: row?.action ?? "—" },
    { k: "Grader vs truth", v: row?.outcome?.replace(/_/g, " ") ?? "—" },
    { k: "Reward", v: row ? (row.reward >= 0 ? "+" : "") + row.reward.toFixed(2) : "—", mono: true, tone: row ? (row.reward >= 0.5 ? "text-accent" : row.reward < 0 ? "text-alarm" : "text-muted") : "" },
  ];
  return (
    <div className="grid grid-cols-6 gap-2">
      {stages.map((s, i) => (
        <motion.div key={s.k + (row?.step ?? 0)} initial={{ borderColor: "rgba(46,230,208,0.6)" }} animate={{ borderColor: "rgba(148,180,200,0.12)" }} transition={{ delay: i * 0.05, duration: 0.6 }} className="relative rounded-xl border bg-black/25 p-2.5">
          <div className="font-mono text-[10px] uppercase tracking-wider text-dim">{i + 1} · {s.k}</div>
          <div className={cn("mt-1 line-clamp-2 text-[12.5px] leading-snug", s.mono && "font-mono", s.tone)}>{s.v}</div>
          {i < 5 && <div className="absolute -right-2 top-1/2 z-10 h-px w-2 bg-line" />}
        </motion.div>
      ))}
    </div>
  );
}

function Chaos({ rob }: { rob: any }) {
  const levels: any[] = useMemo(() => {
    if (!rob) return [];
    const L = rob.levels ?? rob.ladder ?? rob.results ?? [];
    return Array.isArray(L) ? L : Object.entries(L).map(([k, v]: any) => ({ level: k, ...v }));
  }, [rob]);
  const [lvl, setLvl] = useState(0);
  if (!levels.length) return <Empty title="Chaos ladder not generated yet (noise L0 → L4)" cmd="data/results/robustness.json" />;
  const cur = levels[Math.min(lvl, levels.length - 1)];
  const sysOf = (l: any) => l.systems ?? l.metrics ?? l;
  const metrics = ["accuracy_cited", "hallucination_rate", "abstain_precision", "current_fact_accuracy"];
  const ex = (cur.examples ?? [])[0];
  return (
    <div className="grid grid-cols-[1fr_1fr] gap-5">
      <div>
        <div className="flex items-center gap-3">
          <span className="font-mono text-[12px] text-dim">noise</span>
          <input type="range" min={0} max={levels.length - 1} value={lvl} onChange={(e) => setLvl(Number(e.target.value))} className="flex-1" />
          <span className="w-[150px] font-mono text-[13px] text-accent">L{cur.level ?? lvl} · {cur.name ?? ["clean", "light", "messy", "heavy", "brutal"][lvl] ?? ""}</span>
        </div>
        <div className="mt-2 font-mono text-[11.5px] text-dim">{cur.n_docs?.toLocaleString()} docs in corpus · {cur.facts_extracted ?? "—"} facts extracted · N={rob.n_questions} questions</div>
        {!ex && <div className="mt-3 rounded-lg border border-line bg-black/25 p-2.5 text-[12.5px] text-muted">Clean corpus. Drag right to add typos, slang, fragments, bot spam, forwarded duplicates, wrong claims and 3× chatter.</div>}
        {ex && (
          <div className="mt-3 space-y-2 text-[12.5px]">
            <div className="rounded-lg border border-line bg-black/25 p-2.5"><span className="font-mono text-[10px] text-dim">BEFORE</span><div className="mt-0.5">{ex.before ?? ex.original}</div></div>
            <div className="rounded-lg border border-alarm/25 bg-alarm/[0.04] p-2.5"><span className="font-mono text-[10px] text-alarm">AFTER L{cur.level ?? lvl}</span><div className="mt-0.5">{ex.after ?? ex.corrupted}</div></div>
          </div>
        )}
      </div>
      <div className="space-y-2.5">
        {metrics.map((m) => (
          <div key={m}>
            <div className="mb-1 text-[11.5px] text-dim">{m.replace(/_/g, " ")}</div>
            {Object.keys(SYS).map((s) => {
              const v = metricVal(sysOf(cur)?.[s]?.[m]);
              const n = metricN(sysOf(cur)?.[s]?.[m]);
              return (
                <div key={s} className="flex items-center gap-2 text-[11.5px]">
                  <span className="w-[92px] text-muted">{SYS[s].label}</span>
                  <div className="h-2 flex-1 rounded-full bg-white/5">
                    <motion.div animate={{ width: `${(v ?? 0) * 100}%` }} className="h-full rounded-full" style={{ background: m === "hallucination_rate" && s === "plain" ? "#ff4d5e" : SYS[s].color }} />
                  </div>
                  <span className="w-[80px] text-right font-mono tabular-nums">{v == null ? "—" : `${(v * 100).toFixed(0)}%`}{n ? <span className="text-dim"> n={n}</span> : null}</span>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function LabPage() {
  const curve = useData("/results/reward_curve", "reward_curve");
  const log = useData("/results/training_log", "training_log");
  const bench = useData("/results/benchmark_dev", "benchmark_dev");
  const benchTest = useData("/results/benchmark_test", "benchmark_test");
  const rob = useData("/results/robustness", "robustness");
  const bandit = useData("/results/bandit", "bandit");
  const [p, setP] = useState(0);
  const [playing, setPlaying] = useState(false);

  const series = useMemo(() => {
    const c = curve.data;
    if (!c) return [];
    const R = c.rolling;
    const n = R.bandit.length;
    return Array.from({ length: n }, (_, i) => ({ step: i * (c.stride ?? 1), bandit: R.bandit[i], default: R.default[i], random: R.random[i], oracle: R.oracle[i] }));
  }, [curve.data]);
  const rows: any[] = log.data?.rows ?? [];

  useEffect(() => {
    if (!playing || !series.length) return;
    const i = setInterval(() => setP((x) => (x >= 1 ? (setPlaying(false), 1) : Math.min(1, x + 0.006))), 30);
    return () => clearInterval(i);
  }, [playing, series.length]);
  useEffect(() => {
    if (series.length && p === 0) {
      const t = setTimeout(() => setPlaying(true), 500);
      return () => clearTimeout(t);
    }
  }, [series.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const shown = series.slice(0, Math.max(2, Math.round(p * series.length)));
  const row = rows.length ? rows[Math.min(rows.length - 1, Math.floor(p * (rows.length - 1)))] : null;
  const arms: any[] = bandit.data?.arms ?? [];
  const armHits = useMemo(() => {
    const m: Record<string, number> = {};
    for (const r of rows.slice(0, Math.floor(p * rows.length))) m[r.arm] = (m[r.arm] ?? 0) + 1;
    return m;
  }, [rows, p]);
  const maxHit = Math.max(1, ...Object.values(armHits));

  const B = (benchTest.data ?? bench.data)?.systems;
  const split = benchTest.data ? "test" : "dev";
  const rel = B?.keepline?.reliability_bins ?? [];
  const MET = [
    { k: "accuracy_cited", l: "Accuracy with valid citation", up: true },
    { k: "hallucination_rate", l: "Confident-wrong rate (of answered)", up: false },
    { k: "correct_action_rate", l: "Right action (answer / abstain / route)", up: true },
    { k: "routing_accuracy", l: "Routed to the right person", up: true },
    { k: "current_fact_accuracy", l: "Current-fact accuracy", up: true },
    { k: "ece", l: "Calibration error (ECE, lower is better)", up: false, raw: true, dp: 3 },
    { k: "mean_reward", l: "Mean reward", up: true, raw: true, dp: 2 },
  ];

  return (
    <div>
      <PageHeader
        eyebrow="08 · RL lab & proof"
        title="Rewarded for saying “I don't know” instead of guessing"
        sub="A contextual bandit (LinUCB) learns when to answer, abstain or route: per-question features in, one of 28 policy arms out, rewarded by a grader that checks against a truth file the product never sees. Not an LLM fine-tune."
        right={<LiveDot live={curve.live} />}
      />

      <div className="glass rounded-2xl p-5">
        <div className="mb-3 flex items-center justify-between">
          <div className="text-[12px] uppercase tracking-[0.16em] text-dim">Training replay · step {row?.step ?? 0} / {log.data?.n ?? "—"}</div>
          <button onClick={() => { setP(0); setPlaying(true); }} className="flex items-center gap-1.5 rounded-full border border-line px-3 py-1 text-[12px] text-muted hover:text-fg">
            {p >= 1 ? <RotateCcw className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />} Replay
          </button>
        </div>
        <Loop row={row} />
        <div className="mt-4 grid grid-cols-[1fr_300px] gap-5">
          <div className="h-[260px]">
            {series.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={shown} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
                  <CartesianGrid stroke="rgba(148,180,200,0.07)" vertical={false} />
                  <XAxis dataKey="step" type="number" domain={[0, series[series.length - 1].step]} tick={{ fill: "#5a6a75", fontSize: 11 }} tickLine={false} axisLine={false} />
                  <YAxis tick={{ fill: "#5a6a75", fontSize: 11 }} tickLine={false} axisLine={false} domain={[-1.2, 1.2]} />
                  <ReferenceLine y={0} stroke="rgba(148,180,200,0.2)" />
                  <Tooltip contentStyle={{ background: "#0c1116", border: "1px solid rgba(148,180,200,0.2)", borderRadius: 8, fontSize: 12 }} />
                  <Line dataKey="oracle" stroke="#5a6a75" strokeDasharray="4 4" dot={false} isAnimationActive={false} strokeWidth={1.2} />
                  <Line dataKey="random" stroke="#3a4650" dot={false} isAnimationActive={false} strokeWidth={1.2} />
                  <Line dataKey="default" stroke="#8a9aa6" dot={false} isAnimationActive={false} strokeWidth={1.4} />
                  <Line dataKey="bandit" stroke="#2ee6d0" dot={false} isAnimationActive={false} strokeWidth={2.4} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <Empty title="No reward curve yet" cmd="python -m keepline.rl.train" />
            )}
          </div>
          <div>
            <div className="mb-2 flex gap-3 text-[11.5px]">
              <span className="text-accent">— bandit</span><span className="text-muted">— fixed default</span><span className="text-[#5a6a75]">- - oracle</span><span className="text-[#3a4650]">— random</span>
            </div>
            <div className="mb-2 text-[11px] uppercase tracking-wider text-dim">Arm pulls ({arms.length} arms)</div>
            <div className="grid grid-cols-7 gap-1">
              {arms.map((a: any) => {
                const h = armHits[a.key] ?? 0;
                const on = row?.arm === a.key;
                return (
                  <div key={a.key} title={a.key} className={cn("h-6 rounded-[4px] border transition-colors", on ? "border-accent" : "border-transparent")} style={{ background: `rgba(46,230,208,${0.05 + 0.75 * (h / maxHit)})` }} />
                );
              })}
            </div>
            {curve.data?.final && (
              <div className="mt-3 space-y-1 font-mono text-[12px]">
                {Object.entries(curve.data.final as Record<string, number>).map(([k, v]) => (
                  <div key={k} className="flex justify-between"><span className="text-dim">{k.replace("_", " ")}</span><span className={k === "bandit" ? "text-accent" : "text-muted"}>{v >= 0 ? "+" : ""}{v.toFixed(3)}</span></div>
                ))}
                <div className="pt-1 text-[10.5px] text-dim">train-split replay: mean reward per question, N={curve.data.n_train} train questions × {curve.data.epochs} epochs</div>
              </div>
            )}
          </div>
        </div>
        {row && <div className="mt-2 font-mono text-[11px] text-dim">grader outcome {row.outcome} → reward table {OUTCOME_R[row.outcome] ?? "?"} + calibration bonus</div>}
      </div>

      <div className="mt-5 grid grid-cols-[1.35fr_1fr] gap-5">
        <div className="glass rounded-2xl p-5">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-[12px] uppercase tracking-[0.16em] text-dim">Keepline vs plain search · {split} split</div>
            <Badge>N = {(benchTest.data ?? bench.data)?.n_questions ?? "—"} questions</Badge>
          </div>
          {B ? (
            <table className="w-full text-[13px]">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-dim">
                  <th className="pb-2 font-normal">Metric</th>
                  {Object.keys(SYS).map((s) => <th key={s} className="pb-2 text-right font-normal">{SYS[s].label}</th>)}
                </tr>
              </thead>
              <tbody>
                {MET.map((m) => (
                  <tr key={m.k} className="border-t border-line">
                    <td className="py-2 text-muted">{m.l}</td>
                    {Object.keys(SYS).map((s) => {
                      const v = metricVal(B[s]?.[m.k]);
                      const n = metricN(B[s]?.[m.k]);
                      return (
                        <td key={s} className={cn("py-2 text-right font-mono tabular-nums", s === "keepline" && "text-accent", m.k === "hallucination_rate" && s === "plain" && "text-alarm")}>
                          {v == null ? "—" : m.raw ? (m.k === "mean_reward" && v >= 0 ? "+" : "") + v.toFixed(m.dp ?? 2) : `${(v * 100).toFixed(1)}%`}
                          {n != null && <span className="ml-1 text-[10.5px] text-dim">n={n}</span>}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Empty title="Benchmark not run yet" cmd="python -m keepline.eval.benchmark --split dev" />
          )}
          <div className="mt-3 text-[11.5px] leading-relaxed text-dim">
            {split === "test" ? "Held-out test split, run once, never seen during development. " : "Dev split. "}
            Headline system is Keepline with its calibrated default policy. The learned calibrator generalizes (ECE {metricVal(B?.plain?.ece)?.toFixed(2) ?? "—"} → {metricVal(B?.keepline?.ece)?.toFixed(2) ?? "—"}).
            Honest result: the bandit's thresholds, tuned on dev with 388 training questions, over-abstain on test and do not beat the calibrated default (reward {metricVal(B?.keepline_rl?.mean_reward)?.toFixed(3) ?? "—"} vs {metricVal(B?.keepline?.mean_reward)?.toFixed(3) ?? "—"}). More real usage data means better thresholds; that is the roadmap.
          </div>
        </div>
        <div className="glass rounded-2xl p-5">
          <div className="mb-3 text-[12px] uppercase tracking-[0.16em] text-dim">Calibration · Keepline confidence vs accuracy</div>
          <div className="h-[200px]">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
                <CartesianGrid stroke="rgba(148,180,200,0.07)" />
                <XAxis dataKey="confidence" type="number" domain={[0, 1]} tick={{ fill: "#5a6a75", fontSize: 11 }} tickLine={false} axisLine={false} />
                <YAxis dataKey="accuracy" type="number" domain={[0, 1]} tick={{ fill: "#5a6a75", fontSize: 11 }} tickLine={false} axisLine={false} />
                <ZAxis dataKey="n" range={[30, 400]} />
                <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke="rgba(148,180,200,0.3)" strokeDasharray="4 4" />
                <Tooltip contentStyle={{ background: "#0c1116", border: "1px solid rgba(148,180,200,0.2)", borderRadius: 8, fontSize: 12 }} />
                <Scatter data={rel.filter((b: any) => b.n > 0)} fill="#2ee6d0" />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 text-[11px] text-dim">Bubble size = N questions per bin. Keepline ECE {metricVal(B?.keepline?.ece)?.toFixed(3) ?? "—"} vs plain search {metricVal(B?.plain?.ece)?.toFixed(3) ?? "—"} · {split} split.</div>
        </div>
      </div>

      <div className="mt-5 glass rounded-2xl p-5">
        <div className="mb-3 flex items-center justify-between">
          <div className="text-[12px] uppercase tracking-[0.16em] text-dim">Truth-first benchmark</div>
          <Badge tone="accent"><Lock className="h-3 w-3" /> test split frozen · sha256 ea2160d2…</Badge>
        </div>
        <div className="grid grid-cols-5 items-center gap-2 text-center text-[13px]">
          {[
            ["Truth file", "168 facts, who knows them, when they changed"],
            ["Rendered data", "Slack, email, tickets written from the truth"],
            ["Keepline", "never sees the truth (enforced by a test)"],
            ["Grader", "checks keywords, citations, currency, routing"],
            ["Reward", REWARDS.map((r) => r.r).join(" / ")],
          ].map(([a, b], i) => (
            <div key={a} className="relative rounded-xl border border-line bg-black/25 p-3">
              <div className="font-medium">{a}</div>
              <div className="mt-1 text-[11.5px] leading-snug text-dim">{b}</div>
              {i < 4 && <div className="beam absolute -right-2 top-1/2 h-px w-2 overflow-hidden bg-accent/40" />}
            </div>
          ))}
        </div>
      </div>

      <div className="mt-5 glass rounded-2xl p-5">
        <div className="mb-3 text-[12px] uppercase tracking-[0.16em] text-dim">Chaos ladder · does it hold up on messy data?</div>
        <Chaos rob={rob.data} />
      </div>
    </div>
  );
}
