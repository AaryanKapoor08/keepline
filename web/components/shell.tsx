"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { motion } from "motion/react";
import {
  LayoutGrid, Network, UserRound, Flame, PackageCheck, MessageSquareQuote, FlaskConical, LineChart, Snowflake, Presentation,
} from "lucide-react";
import { cn } from "./ui";

export const BEATS = [
  { href: "/", label: "Overview", t: "0:00", icon: LayoutGrid },
  { href: "/graph", label: "Constellation", t: "0:15", icon: Network },
  { href: "/profile", label: "Knowledge profile", t: "0:35", icon: UserRound },
  { href: "/risk", label: "Risk map", t: "0:45", icon: Flame },
  { href: "/handoff", label: "Handoff pack", t: "0:55", icon: PackageCheck },
  { href: "/ask", label: "Ask", t: "1:10", icon: MessageSquareQuote },
  { href: "/simulate", label: "Simulator", t: "1:25", icon: FlaskConical },
  { href: "/lab", label: "RL lab & proof", t: "1:40", icon: LineChart },
  { href: "/close", label: "Snowflake & market", t: "1:55", icon: Snowflake },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const idx = Math.max(0, BEATS.findIndex((b) => b.href === path));
  const [presenter, setPresenter] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      if (e.key === "ArrowRight" || e.key === " " || e.key === "PageDown") {
        e.preventDefault();
        if (idx < BEATS.length - 1) router.push(BEATS[idx + 1].href);
      } else if (e.key === "ArrowLeft" || e.key === "PageUp") {
        e.preventDefault();
        if (idx > 0) router.push(BEATS[idx - 1].href);
      } else if (e.key.toLowerCase() === "p") {
        setPresenter((p) => !p);
      } else if (/^[1-9]$/.test(e.key)) {
        router.push(BEATS[Number(e.key) - 1].href);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [idx, router]);

  useEffect(() => {
    BEATS.forEach((b) => router.prefetch(b.href));
  }, [router]);

  return (
    <div className="flex min-h-screen">
      {/* progress line: "the line" */}
      <div className="fixed left-0 right-0 top-0 z-50 h-[2px] bg-white/5">
        <motion.div className="h-full bg-accent" animate={{ width: `${((idx + 1) / BEATS.length) * 100}%` }} transition={{ duration: 0.6 }} />
      </div>
      <aside className={cn("sticky top-0 z-40 flex h-screen shrink-0 flex-col border-r border-line bg-bg/70 backdrop-blur-xl transition-all", presenter ? "w-[64px]" : "w-[232px]")}>
        <Link href="/" className="flex items-center gap-2.5 px-4 pb-5 pt-6">
          <Logo />
          {!presenter && (
            <div>
              <div className="text-[15px] font-semibold tracking-tight">Keepline</div>
              <div className="text-[11px] text-dim">Harbourline Credit Union</div>
            </div>
          )}
        </Link>
        <nav className="flex flex-1 flex-col gap-0.5 px-2">
          {BEATS.map((b, i) => {
            const active = i === idx;
            const Icon = b.icon;
            return (
              <Link key={b.href} href={b.href} className={cn("group relative flex items-center gap-3 rounded-lg px-3 py-2 text-[13.5px] transition-colors", active ? "text-fg" : "text-muted hover:bg-white/[0.03] hover:text-fg")}>
                {active && <motion.div layoutId="nav-active" className="absolute inset-0 rounded-lg border border-accent/20 bg-accent/[0.07]" transition={{ type: "spring", stiffness: 400, damping: 34 }} />}
                <Icon className={cn("relative h-4 w-4 shrink-0", active ? "text-accent" : "text-dim group-hover:text-muted")} />
                {!presenter && (
                  <>
                    <span className="relative flex-1">{b.label}</span>
                    <span className="relative font-mono text-[10.5px] text-dim">{b.t}</span>
                  </>
                )}
              </Link>
            );
          })}
        </nav>
        {!presenter && (
          <div className="m-3 rounded-xl border border-line bg-white/[0.02] p-3 text-[11.5px] leading-relaxed text-dim">
            <div className="mb-1 flex items-center gap-1.5 text-muted">
              <Presentation className="h-3.5 w-3.5" /> Presenter
            </div>
            <span className="kbd">→</span> <span className="kbd">Space</span> next · <span className="kbd">←</span> back · <span className="kbd">P</span> focus
            <div className="mt-2 font-mono text-[10.5px]">Today · Fri 2026-09-04</div>
          </div>
        )}
      </aside>
      <main className="relative min-w-0 flex-1">
        <motion.div key={path} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }} className="mx-auto max-w-[1320px] px-8 pb-16 pt-9">
          {children}
        </motion.div>
        <div className="pointer-events-none fixed bottom-4 right-5 z-40 flex items-center gap-2 font-mono text-[11px] text-dim">
          <span>{String(idx + 1).padStart(2, "0")} / {String(BEATS.length).padStart(2, "0")}</span>
          <span className="text-accent/80">{BEATS[idx].t}</span>
        </div>
      </main>
    </div>
  );
}

export function Logo({ size = 30 }: { size?: number }) {
  return (
    <div className="relative flex items-center justify-center rounded-lg border border-accent/30 bg-accent/10" style={{ width: size, height: size }}>
      <svg viewBox="0 0 24 24" width={size * 0.62} height={size * 0.62} fill="none">
        <path d="M3 17 L9 11 L13 15 L21 7" stroke="var(--accent)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="21" cy="7" r="2" fill="var(--accent)" />
      </svg>
      
    </div>
  );
}
