"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useState } from "react";

const API_ENV = process.env.NEXT_PUBLIC_KEEPLINE_API ?? "http://localhost:8000";
/** "off" = static snapshot only (hosted deploy: never probe localhost). */
export const API = API_ENV === "off" ? "" : API_ENV;
export const TODAY = "2026-09-04";

let apiDown: boolean | null = API ? null : true;

async function withTimeout(p: Promise<Response>, ms: number): Promise<Response> {
  return Promise.race([p, new Promise<Response>((_, rej) => setTimeout(() => rej(new Error("timeout")), ms))]);
}

export async function snapshot(name: string): Promise<any> {
  const r = await fetch(`/data/${name}.json`);
  if (!r.ok) return null;
  return r.json();
}

/** GET from the live API, falling back to the static snapshot in /public/data. */
export async function getJSON(path: string, snap: string): Promise<{ data: any; live: boolean }> {
  if (apiDown !== true) {
    try {
      const r = await withTimeout(fetch(API + path), apiDown === null ? 2500 : 6000);
      if (r.ok) {
        apiDown = false;
        return { data: await r.json(), live: true };
      }
    } catch {
      apiDown = true;
    }
  }
  return { data: await snapshot(snap), live: false };
}

export async function postJSON(path: string, body: any): Promise<any | null> {
  if (apiDown === true) return null;
  try {
    const r = await withTimeout(
      fetch(API + path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }),
      8000,
    );
    if (!r.ok) return null;
    apiDown = false;
    return r.json();
  } catch {
    apiDown = true;
    return null;
  }
}

export const normQ = (q: string) => q.toLowerCase().replace(/[^a-z0-9 ]+/g, "").trim();

/** Closest cached key by word overlap (for the offline snapshot). */
export function nearest(q: string, table: Record<string, any>): any | null {
  const words = new Set(normQ(q).split(/\s+/).filter((w) => w.length > 2));
  let best: string | null = null;
  let bestScore = 0;
  for (const k of Object.keys(table)) {
    const kw = k.split(/\s+/).filter((w) => w.length > 2);
    const s = kw.filter((w) => words.has(w)).length / Math.max(3, kw.length);
    if (s > bestScore) {
      bestScore = s;
      best = k;
    }
  }
  return best && bestScore >= 0.3 ? table[best] : null;
}

export function useData(path: string, snap: string) {
  const [state, setState] = useState<{ data: any; live: boolean; loading: boolean }>({ data: null, live: false, loading: true });
  useEffect(() => {
    let alive = true;
    getJSON(path, snap).then((r) => alive && setState({ ...r, loading: false }));
    return () => {
      alive = false;
    };
  }, [path, snap]);
  return state;
}

export const PEOPLE: Record<string, { name: string; role: string; color: string }> = {
  marc: { name: "Marc Leblanc", role: "CEO", color: "#8aa4b8" },
  dave: { name: "Dave MacLeod", role: "COO", color: "#8aa4b8" },
  sarah: { name: "Sarah Chen", role: "Senior Backend Engineer", color: "#ff4d5e" },
  aisha: { name: "Aisha Rahman", role: "Junior Backend Engineer", color: "#0071e3" },
  alex: { name: "Alex Rivera", role: "Backend Engineer (new)", color: "#22b8e6" },
  mike: { name: "Mike O'Brien", role: "IT Infrastructure (contract)", color: "#d6b46a" },
  nadia: { name: "Nadia Kaur", role: "IT Support Analyst", color: "#0071e3" },
  tom: { name: "Tom Bouchard", role: "Compliance Officer", color: "#d6b46a" },
  priya: { name: "Priya Nair", role: "Finance & Payroll", color: "#0071e3" },
  jen: { name: "Jen Theriault", role: "Member Services Lead", color: "#0071e3" },
  colin: { name: "Colin Doucette", role: "Member Services", color: "#0071e3" },
};
export const pname = (id?: string | null) => (id ? PEOPLE[id]?.name ?? id : "—");
export const first = (id?: string | null) => pname(id).split(" ")[0];
export const initials = (id?: string | null) =>
  pname(id)
    .split(" ")
    .map((s) => s[0])
    .join("")
    .slice(0, 2);

export const KIND_COLOR: Record<string, string> = {
  landmine: "#ff3b30",
  access: "#0071e3",
  vendor_contact: "#1d1d1f",
  recurring_task: "#6e6e73",
  procedure: "#86868b",
  decision: "#a1a1a6",
  owner: "#aeaeb2",
  fact: "#c7c7cc",
};
export const KIND_LABEL: Record<string, string> = {
  landmine: "Landmines",
  access: "Access",
  vendor_contact: "Vendor contacts",
  recurring_task: "Recurring tasks",
  procedure: "Procedures",
  decision: "Decisions",
  owner: "Ownership",
  fact: "Facts",
};

export const fmtDate = (s?: string | null) =>
  s ? new Date(s.length <= 10 ? s + "T12:00:00" : s).toLocaleDateString("en-CA", { month: "short", day: "numeric", year: "numeric" }) : "";

export const riskColor = (r: number) => (r >= 0.35 ? "#ff3b30" : r >= 0.15 ? "#1d1d1f" : "#86868b");
export const riskLevel = (r: number) => (r >= 0.6 ? "Critical" : r >= 0.35 ? "High" : r >= 0.15 ? "Elevated" : "Low");

/** Current value of a theme token (for SVG attributes and chart libs that can't read CSS variables). */
export function cssVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

// ---------------------------------------------------------------------------------------------- restatement vs change
const STOP = new Set("the a an of to and or is it in on for our we us as at by be are was now today from with this that".split(" "));
const WEEKDAYS = /\b(mon|tues|wednes|thurs|fri|satur|sun)day\b/gi;
function values(t: string): Set<string> {
  const out = new Set<string>();
  for (const m of t.matchAll(/\d+(?::\d+)?(?:st|nd|rd|th)?/gi)) out.add(m[0].toLowerCase());
  for (const m of t.matchAll(WEEKDAYS)) out.add(m[0].toLowerCase());
  // proper nouns: capitalised words that don't start a sentence
  for (const m of t.matchAll(/(?<![.!?]\s|^)\b([A-Z][A-Za-z0-9]+)\b/g)) out.add(m[1].toLowerCase());
  return out;
}
function tokens(t: string): Set<string> {
  return new Set(t.toLowerCase().match(/[a-z0-9]+/g)?.filter((w) => !STOP.has(w) && w.length > 1) ?? []);
}
const UNITS = new Set(["day", "days", "week", "weeks", "month", "months", "hour", "hours", "minute", "minutes", "min", "year", "years"]);
/** True when two linked facts share no topic words beyond numbers and units: a spurious link, shown as a plain decision. */
export function isUnrelated(newText: string, oldText: string): boolean {
  const topical = (t: string) => new Set([...tokens(t)].filter((w) => !UNITS.has(w) && !/^\d/.test(w)));
  const a = topical(newText);
  for (const w of topical(oldText)) if (a.has(w)) return false;
  return true;
}
/** True when the "new" fact only restates the old one (no new value, similar wording): not a real change. */
export function isRestatement(newText: string, oldText: string): boolean {
  const nv = values(newText);
  const ov = new Set([...values(oldText), ...tokens(oldText)]);
  for (const v of nv) if (!ov.has(v)) return false;
  const a = tokens(newText);
  const b = tokens(oldText);
  const inter = [...a].filter((x) => b.has(x)).length;
  return inter / (a.size + b.size - inter || 1) >= 0.4;
}

// ---------------------------------------------------------------------------------------------- display cleanup
const FILLER = /^(?:(?:yep|yeah|yes|ok(?:ay)?(?: so)?|so|btw|fyi(?: for anyone touching this)?|heads up(?: all)?|reminder(?: for [^:]+)?|update(?: after [^:]+)?)\s*[,:\u2014\u2013-]*\s+|@[\w.]+[\s,:]*)+/i;
/** Strip conversational filler and leading @mentions from an extracted fact for display. */
export function cleanFact(t: string): string {
  const s = String(t ?? "").replace(FILLER, "").trim();
  return s ? s[0].toUpperCase() + s.slice(1) : t;
}
/** A fact that reads on its own: long enough, not a continuation fragment. */
export function isComplete(t: string): boolean {
  const s = String(t ?? "").trim();
  return s.split(/\s+/).length >= 7 && !/^(otherwise|also|and|but|or|then|@)/i.test(s) && !/^[a-z]/.test(s);
}
