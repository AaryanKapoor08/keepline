"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Search, MoreVertical, Building2, CalendarDays, Download, ChevronRight } from "lucide-react";
import { pname, fmtDate } from "@/lib/data";
import { cn } from "./ui";

export const EASE = [0.25, 0.1, 0.25, 1] as const;

export function PageTop({ title, action, onAction, actionHref, sub, chips, right, secondary }: { title: React.ReactNode; action?: React.ReactNode; onAction?: () => void; actionHref?: string; sub?: React.ReactNode; chips?: React.ReactNode; right?: React.ReactNode; secondary?: { label: React.ReactNode; onClick: () => void } }) {
  return (
    <div className="mb-6">
      <div className="flex items-end justify-between gap-6">
        <div>
          <motion.h1 initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease: EASE }} className="text-[42px] font-medium leading-[1.1] tracking-[-0.02em]">
            {title}
          </motion.h1>
          {sub && <p className="mt-2 text-[17px] text-muted">{sub}</p>}
        </div>
        <div className="flex gap-2">
        {secondary && <button onClick={secondary.onClick} className="btn-primary">{secondary.label}</button>}
        {action &&
          (actionHref ? (
            <a href={actionHref} className="btn-primary">{action}</a>
          ) : (
            <button onClick={onAction} className="btn-primary">{action}</button>
          ))}
        </div>
      </div>
      <div className="mt-6 flex items-center justify-between">
        <div className="flex gap-2">
          {chips ?? (
            <>
              <Chip icon={Building2}>Harbourline Credit Union</Chip>
              <Chip icon={CalendarDays}>As of Sep 4, 2026</Chip>
              <Chip icon={Download}>Export</Chip>
            </>
          )}
        </div>
        {right ?? <div className="flex items-center gap-2">
          <div className="flex h-11 w-[300px] items-center gap-2 rounded-full bg-white px-4 text-[14px] text-dim">
            <Search className="h-4 w-4" strokeWidth={1.6} /> Search knowledge
          </div>
          <span className="flex h-11 w-11 items-center justify-center rounded-full bg-white"><MoreVertical className="h-4 w-4" strokeWidth={1.6} /></span>
        </div>}
      </div>
    </div>
  );
}

export function Chip({ children, icon: I, onClick, active }: { children: React.ReactNode; icon?: any; onClick?: () => void; active?: boolean }) {
  return (
    <button onClick={onClick} className={cn("flex h-11 items-center gap-2 rounded-full px-4 text-[14px] transition-colors", active ? "bg-sig text-white" : "bg-white text-fg hover:bg-white/70")}>
      {I && <I className="h-4 w-4" strokeWidth={1.6} />}
      {children}
    </button>
  );
}

export function Card({ title, right, children, className, dark, delay = 0 }: { title?: React.ReactNode; right?: React.ReactNode; children: React.ReactNode; className?: string; dark?: boolean; delay?: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, delay, ease: EASE }}
      className={cn("flex flex-col rounded-[24px] p-6", dark ? "bg-sig text-white" : "bg-white shadow-card", className)}
    >
      {(title || right) && (
        <div className="mb-4 flex items-center justify-between gap-3">
          <div className="text-[19px] font-medium">{title}</div>
          {right}
        </div>
      )}
      {children}
    </motion.div>
  );
}

export function Details({ children = "View details", onClick, href, dark, open }: { children?: React.ReactNode; onClick?: () => void; href?: string; dark?: boolean; open?: boolean }) {
  const cls = cn("inline-flex h-9 items-center gap-1 rounded-full border px-3.5 text-[13px] transition-colors", dark ? "border-white/20 text-white hover:bg-white/10" : "border-[var(--line)] bg-white text-fg hover:bg-surface2");
  const inner = (
    <>
      {children} <ChevronRight className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-90")} />
    </>
  );
  return href ? <a href={href} className={cls}>{inner}</a> : <button onClick={onClick} className={cls}>{inner}</button>;
}

export function Big({ value, unit, caption, red, dark }: { value: React.ReactNode; unit?: string; caption?: React.ReactNode; red?: boolean; dark?: boolean }) {
  return (
    <div className="flex items-end gap-3">
      <div className={cn("text-[56px] font-medium leading-none tracking-[-0.03em] tabular-nums", red && "text-alarm")}>
        {value}
        {unit && <span className={cn("ml-1", dark ? "text-white/40" : "text-[#b0b0b8]")}>{unit}</span>}
      </div>
      {caption && <div className={cn("pb-1 text-[14px] leading-tight", dark ? "text-white/60" : "text-muted")}>{caption}</div>}
    </div>
  );
}

/** Black bar vs hatched gray bars, the reference's only chart language. */
export function Bars({ items, height = 150 }: { items: { label: string; value: number; strong?: boolean; red?: boolean }[]; height?: number }) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <div className="flex items-end gap-2 rounded-[18px] bg-surface2 p-3" style={{ height: height + 56 }}>
      {items.map((it, i) => (
        <div key={it.label} className="flex flex-1 flex-col justify-end">
          <div className="mb-2 text-[14px] font-medium tabular-nums">{it.value}</div>
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: Math.max(8, (it.value / max) * height) }}
            transition={{ duration: 0.8, delay: 0.1 * i, ease: EASE }}
            className={cn("rounded-[12px]", it.red ? "bg-alarm" : it.strong ? "bg-sig" : "hatch")}
          />
          <div className="mt-2 truncate text-[12px] text-muted">{it.label}</div>
        </div>
      ))}
    </div>
  );
}

export function Row({ label, value, children, strong }: { label: React.ReactNode; value?: React.ReactNode; children?: React.ReactNode; strong?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-[var(--line)] last:border-0">
      <button onClick={() => children && setOpen(!open)} className="flex w-full items-center gap-2 py-3.5 text-left text-[16px]">
        {children ? <span className={cn("text-[11px] transition-transform", open && "rotate-90")}>▶</span> : <span className="w-[11px]" />}
        <span className={cn("flex-1", strong && "font-medium")}>{label}</span>
        <span className="tabular-nums">{value}</span>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <div className="pb-3 pl-5">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function Avatar({ id, size = 40, dark }: { id: string; size?: number; dark?: boolean }) {
  return (
    <span className={cn("inline-flex shrink-0 items-center justify-center rounded-full font-medium", dark ? "bg-white text-[#111]" : "bg-sig text-white")} style={{ width: size, height: size, fontSize: size * 0.36 }}>
      {pname(id).split(" ").map((x) => x[0]).join("").slice(0, 2)}
    </span>
  );
}

export function PersonPill({ id, note }: { id: string; note?: string }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full bg-surface2 py-1 pl-1 pr-4 text-[14px]">
      <Avatar id={id} size={28} />
      {pname(id)}
      {note && <span className="text-muted">· {note}</span>}
    </span>
  );
}

export function Quote({ c, small }: { c: any; small?: boolean }) {
  return (
    <div className={cn("text-left", small ? "text-[14px]" : "text-[16px]")}>
      <div className="leading-[1.5] text-fg">&ldquo;{c.quote}&rdquo;</div>
      <div className="mt-1 text-[13px] text-muted">
        {c.author || c.stated_by_name || pname(c.author_id || c.stated_by)}, {fmtDate(c.timestamp || c.date)}
        {c.doc_id && <span> · {c.doc_id}</span>}
      </div>
    </div>
  );
}

export function Fade({ show, children, className }: { show: boolean; children: React.ReactNode; className?: string }) {
  return (
    <AnimatePresence>
      {show && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.6, ease: EASE }} className={className}>
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
