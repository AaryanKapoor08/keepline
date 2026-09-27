"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Settings, Bell } from "lucide-react";
import { cn } from "./ui";
import AskPanel from "./askpanel";

export const ROUTES = [
  { href: "/", label: "Home" },
  { href: "/graph", label: "Knowledge" },
  { href: "/review", label: "Review" },
  { href: "/history", label: "History" },
  { href: "/lab", label: "Proof" },
  { href: "/snowflake", label: "Snowflake" },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const idx = ROUTES.findIndex((r) => r.href === path);
  const [asSarah, setAsSarah] = useState(false);
  useEffect(() => {
    const on = (e: Event) => setAsSarah(!!(e as CustomEvent).detail);
    window.addEventListener("keepline-viewer", on);
    return () => window.removeEventListener("keepline-viewer", on);
  }, []);
  useEffect(() => setAsSarah(false), [path]);
  const viewerSarah = path === "/review" || asSarah;

  useEffect(() => {
    ROUTES.forEach((r) => router.prefetch(r.href));
  }, [router]);

  useEffect(() => {
    let t = new URLSearchParams(window.location.search).get("theme");
    try {
      if (t) localStorage.setItem("keepline-theme", t);
      else t = localStorage.getItem("keepline-theme");
    } catch {}
    document.documentElement.dataset.theme = t && ["graphite", "starlight"].includes(t) ? t : "graphite";
  }, [path]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      const fwd = e.key === "ArrowRight" || e.key === " " || e.key === "PageDown";
      const back = e.key === "ArrowLeft" || e.key === "PageUp";
      if (!fwd && !back) return;
      e.preventDefault();
      const i = idx < 0 ? 0 : idx;
      if (fwd && i < ROUTES.length - 1) router.push(ROUTES[i + 1].href);
      if (back && i > 0) router.push(ROUTES[i - 1].href);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [idx, router]);

  return (
    <div className="min-h-screen bg-canvas">
      <header className="sticky top-0 z-50 border-b border-black/[0.07] bg-[var(--nav)] backdrop-blur-xl backdrop-saturate-150">
        <div className="mx-auto flex h-[60px] max-w-[1400px] items-center justify-between px-8">
          <Link href="/" className="flex h-10 w-10 items-center justify-center rounded-full transition-colors hover:bg-black/[0.05]" aria-label="Keepline home">
            <Mark size={20} />
          </Link>
          <nav className="flex items-center gap-1">
            {ROUTES.map((r) => (
              <Link
                key={r.href}
                href={r.href}
                className={cn("rounded-full px-4 py-2 text-[14px] transition-colors", path === r.href ? "bg-sig text-white" : "text-fg/80 hover:bg-black/[0.05] hover:text-fg")}
              >
                {r.label}
              </Link>
            ))}
          </nav>
          <div className="flex items-center gap-1.5">
            <AskPanel />
            <span className="flex h-10 w-10 items-center justify-center rounded-full text-fg/80 transition-colors hover:bg-black/[0.05]"><Settings className="h-[18px] w-[18px]" strokeWidth={1.6} /></span>
            <span className="flex h-10 w-10 items-center justify-center rounded-full text-fg/80 transition-colors hover:bg-black/[0.05]"><Bell className="h-[18px] w-[18px]" strokeWidth={1.6} /></span>
            <span className="ml-1 flex h-9 w-9 items-center justify-center rounded-full bg-sig text-[12.5px] font-medium text-white" title={viewerSarah ? "Signed in as Sarah Chen" : "Signed in as Dave MacLeod, COO"}>{viewerSarah ? "SC" : "DM"}</span>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-[1400px] px-8 pb-20 pt-12">{children}</main>
    </div>
  );
}

export function Mark({ size = 16, light }: { size?: number; light?: boolean }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" aria-hidden>
      <path d="M3 17 L9 11 L13 15 L21 7" style={{ stroke: light ? "#ffffff" : "var(--fg)" }} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Logo({ size = 30 }: { size?: number }) {
  return <Mark size={size} />;
}
