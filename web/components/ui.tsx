"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { animate, motion, useInView } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { Hash, Mail, Ticket, FileText, Mic, ExternalLink, ChevronDown } from "lucide-react";
import { fmtDate, pname } from "@/lib/data";

export function cn(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

export function Ticker({ value, decimals = 0, suffix = "", prefix = "", duration = 1.4, className }: {
  value: number; decimals?: number; suffix?: string; prefix?: string; duration?: number; className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });
  const [v, setV] = useState(0);
  useEffect(() => {
    if (!inView) return;
    const c = animate(0, value, { duration, ease: [0.16, 1, 0.3, 1], onUpdate: setV });
    return () => c.stop();
  }, [inView, value, duration]);
  return (
    <span ref={ref} className={cn("tabular-nums", className)}>
      {prefix}
      {v.toLocaleString("en-CA", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}
      {suffix}
    </span>
  );
}

export function Card({ children, className, delay = 0, glow }: { children: React.ReactNode; className?: string; delay?: number; glow?: "alarm" | "accent" }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay, ease: [0.16, 1, 0.3, 1] }}
      className={cn(
        "glass glass-hover rounded-2xl relative",
        glow === "alarm" && "shadow-[0_0_0_1px_rgba(255,77,94,0.35),0_0_40px_-8px_rgba(255,77,94,0.35)]",
        glow === "accent" && "shadow-[0_0_0_1px_rgba(46,230,208,0.3),0_0_40px_-8px_rgba(46,230,208,0.3)]",
        className,
      )}
    >
      {children}
    </motion.div>
  );
}

export function Badge({ children, tone = "muted", className }: { children: React.ReactNode; tone?: "muted" | "accent" | "alarm" | "warn" | "ok" | "blue"; className?: string }) {
  const tones: Record<string, string> = {
    muted: "text-muted border-line bg-white/[0.03]",
    accent: "text-accent border-accent/30 bg-accent/10",
    alarm: "text-alarm border-alarm/40 bg-alarm/10",
    warn: "text-warn border-warn/30 bg-warn/10",
    ok: "text-ok border-ok/30 bg-ok/10",
    blue: "text-accent2 border-accent2/30 bg-accent2/10",
  };
  return <span className={cn("inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[12px] font-medium", tones[tone], className)}>{children}</span>;
}

export function Eyebrow({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("font-mono text-[12px] uppercase tracking-[0.18em] text-accent/90", className)}>{children}</div>;
}

export function PageHeader({ eyebrow, title, sub, right }: { eyebrow: string; title: React.ReactNode; sub?: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="mb-7 flex items-end justify-between gap-6">
      <div>
        <Eyebrow>{eyebrow}</Eyebrow>
        <motion.h1 initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-2 text-[34px] font-semibold leading-tight tracking-tight text-gradient">
          {title}
        </motion.h1>
        {sub && <p className="mt-2 max-w-3xl text-[15px] text-muted">{sub}</p>}
      </div>
      {right}
    </div>
  );
}

export function SourceIcon({ type, className = "h-3.5 w-3.5" }: { type?: string; className?: string }) {
  const t = (type || "").toLowerCase();
  if (t.includes("slack")) return <Hash className={className} />;
  if (t.includes("email")) return <Mail className={className} />;
  if (t.includes("ticket")) return <Ticket className={className} />;
  if (t.includes("interview")) return <Mic className={className} />;
  return <FileText className={className} />;
}

export const srcFromId = (id?: string) => (id || "").split("-")[0];

export function Receipt({ c, compact }: { c: any; compact?: boolean }) {
  const src = c.source_type || srcFromId(c.doc_id);
  return (
    <div className={cn("rounded-xl border border-line bg-black/25 p-3", c.is_current === false && "opacity-70")}>
      <div className="flex items-start gap-2">
        <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-white/5 text-muted">
          <SourceIcon type={src} />
        </div>
        <div className="min-w-0 flex-1">
          <p className={cn("text-[14px] leading-snug text-fg/90", compact && "line-clamp-2", c.is_current === false && "line-through decoration-alarm/60")}>
            &ldquo;{c.quote}&rdquo;
          </p>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-dim">
            <span className="text-muted">{c.author || c.stated_by_name || pname(c.author_id || c.stated_by)}</span>
            <span>·</span>
            <span>{fmtDate(c.timestamp || c.date)}</span>
            <span>·</span>
            <span className="font-mono">{c.doc_id}</span>
            {c.url && (
              <a href={c.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-accent/80 hover:text-accent">
                open <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>
          {c.is_current === false && c.replaced_by && (
            <div className="mt-2">
              <Badge tone="warn">Replaced by: {c.replaced_by}</Badge>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function Expandable({ head, children, defaultOpen = false }: { head: React.ReactNode; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button onClick={() => setOpen(!open)} className="flex w-full items-start gap-2 text-left">
        <div className="min-w-0 flex-1">{head}</div>
        <ChevronDown className={cn("mt-1 h-4 w-4 shrink-0 text-dim transition-transform", open && "rotate-180")} />
      </button>
      <motion.div initial={false} animate={{ height: open ? "auto" : 0, opacity: open ? 1 : 0 }} className="overflow-hidden">
        <div className="pt-2">{children}</div>
      </motion.div>
    </div>
  );
}

export function Ring({ value, size = 64, stroke = 6, color = "var(--accent)", label }: { value: number; size?: number; stroke?: number; color?: string; label?: React.ReactNode }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} stroke="rgba(148,180,200,0.12)" strokeWidth={stroke} fill="none" />
        <motion.circle
          cx={size / 2} cy={size / 2} r={r} stroke={color} strokeWidth={stroke} fill="none" strokeLinecap="round"
          strokeDasharray={c} initial={{ strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - Math.max(0, Math.min(1, value))) }}
          transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1] }}
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center text-[13px] font-semibold">{label}</div>
    </div>
  );
}

export function LiveDot({ live }: { live: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] font-mono text-dim" title={live ? "Live from the Keepline API" : "Static snapshot (API offline)"}>
      <span className={cn("h-1.5 w-1.5 rounded-full", live ? "bg-ok shadow-[0_0_8px_var(--ok)]" : "bg-warn")} />
      {live ? "LIVE" : "SNAPSHOT"}
    </span>
  );
}

export function Empty({ title, cmd }: { title: string; cmd: string }) {
  return (
    <div className="flex h-full min-h-40 flex-col items-center justify-center rounded-xl border border-dashed border-line p-6 text-center">
      <div className="text-[14px] text-muted">{title}</div>
      <code className="mt-2 rounded-md bg-black/40 px-2 py-1 font-mono text-[12px] text-accent">{cmd}</code>
    </div>
  );
}
