"use client";
import { motion } from "motion/react";
import { Database, Search, BarChart3, Bot, ShieldCheck, History, Lock, EyeOff, UserCheck, Ban } from "lucide-react";
import { Logo } from "@/components/shell";
import { PageHeader } from "@/components/ui";

const SNOW = [
  { icon: Database, t: "AI_EXTRACT", d: "facts, kinds and quotes pulled from every message, in-warehouse" },
  { icon: Search, t: "Cortex Search", d: "hybrid retrieval over receipts, filtered by visibility" },
  { icon: BarChart3, t: "Cortex Analyst", d: "risk and bus-factor questions over a semantic model" },
  { icon: Bot, t: "Cortex Agent", d: "answer, abstain or route, with citations" },
  { icon: ShieldCheck, t: "Row access policies", d: "private channels stay private, per viewer" },
  { icon: History, t: "Time Travel", d: "the versioned memory, queryable as of any date" },
];

const STATS = [
  { v: "~20%", l: "of New Brunswick's workforce set to retire within a decade" },
  { v: "92%", l: "of organizations fail to capture knowledge from retirees (Deloitte)" },
  { v: "0.5–2×", l: "salary to replace an employee (Gallup)" },
  { v: "9%", l: "of Canadian SMB owners have a succession plan (CFIB)" },
];

export default function ClosePage() {
  return (
    <div>
      <PageHeader eyebrow="09 · Built on Snowflake" title="The data never leaves your Snowflake account" sub="Everything you just saw runs as Snowflake-native SQL and Cortex services, with a Streamlit-in-Snowflake app. The same schema runs locally for this demo." />
      <div className="grid grid-cols-6 gap-3">
        {SNOW.map((s, i) => (
          <motion.div key={s.t} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }} className="glass rounded-xl p-4">
            <s.icon className="h-5 w-5 text-accent" />
            <div className="mt-3 font-mono text-[13px] font-semibold">{s.t}</div>
            <div className="mt-1 text-[12px] leading-snug text-dim">{s.d}</div>
          </motion.div>
        ))}
      </div>

      <div className="mt-5 grid grid-cols-[1.2fr_1fr] gap-5">
        <div className="glass rounded-2xl p-6">
          <div className="text-[12px] uppercase tracking-[0.16em] text-dim">Market · owners and COOs of 20–250-person firms</div>
          <div className="mt-4 grid grid-cols-4 gap-3">
            {STATS.map((s) => (
              <div key={s.v}>
                <div className="text-[30px] font-semibold tabular-nums">{s.v}</div>
                <div className="mt-1 text-[12px] leading-snug text-muted">{s.l}</div>
              </div>
            ))}
          </div>
          <table className="mt-6 w-full text-[13px]">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wider text-dim">
                <th className="pb-2 font-normal" />
                <th className="pb-2 font-normal">Glean / Copilot</th>
                <th className="pb-2 font-normal text-accent">Keepline</th>
              </tr>
            </thead>
            <tbody className="[&_td]:border-t [&_td]:border-line [&_td]:py-2">
              <tr><td className="text-muted">Job</td><td>find what the company knows</td><td>show what it&apos;s about to forget, and save it</td></tr>
              <tr><td className="text-muted">Floor</td><td>~100 seats, $50K+/yr</td><td>$8–20/user/mo + paid handoff pack per departure</td></tr>
              <tr><td className="text-muted">Unknowns</td><td>answers anyway</td><td>&ldquo;I don&apos;t know, ask Mike&rdquo;</td></tr>
              <tr><td className="text-muted">Time</td><td>latest document wins</td><td>every fact versioned: who said it, when, what replaced it</td></tr>
              <tr><td className="text-muted">Way in</td><td>enterprise sales</td><td>free knowledge-risk scan, starting in Atlantic Canada</td></tr>
            </tbody>
          </table>
        </div>
        <div className="glass rounded-2xl p-6">
          <div className="text-[12px] uppercase tracking-[0.16em] text-dim">Privacy promises</div>
          <div className="mt-4 space-y-3.5 text-[14px]">
            <div className="flex gap-3"><EyeOff className="mt-0.5 h-4 w-4 shrink-0 text-accent" /> DMs and private email are off by default.</div>
            <div className="flex gap-3"><UserCheck className="mt-0.5 h-4 w-4 shrink-0 text-accent" /> Every employee reviews what was captured from them, and can correct or remove it.</div>
            <div className="flex gap-3"><Ban className="mt-0.5 h-4 w-4 shrink-0 text-accent" /> Never used for performance reviews.</div>
            <div className="flex gap-3"><Lock className="mt-0.5 h-4 w-4 shrink-0 text-accent" /> Receipts, not clones: Keepline quotes people, it never imitates them.</div>
          </div>
        </div>
      </div>

      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4 }} className="mt-10 flex flex-col items-center text-center">
        <Logo size={44} />
        <div className="mt-5 max-w-[900px] text-[34px] font-semibold leading-tight tracking-tight">
          Glean finds what your company knows.<br />
          <span className="text-accent">Keepline shows what it&apos;s about to forget, and saves it.</span>
        </div>
      </motion.div>
    </div>
  );
}
