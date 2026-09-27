"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { Settings, Bell } from "lucide-react";
import { cn } from "./ui";
import AskPanel from "./askpanel";

export const ROUTES = [
  { href: "/", label: "Home" },
  { href: "/graph", label: "Knowledge" },
  { href: "/review", label: "Review" },
  { href: "/history", label: "History" },
  { href: "/lab", label: "Proof" },
  { href: "/close", label: "Snowflake" },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const idx = ROUTES.findIndex((r) => r.href === path);

  useEffect(() => {
    ROUTES.forEach((r) => router.prefetch(r.href));
  }, [router]);

  useEffect(() => {
    let t = new URLSearchParams(window.location.search).get("theme");
    try {
      if (t) localStorage.setItem("keepline-theme", t);
      else t = localStorage.getItem("keepline-theme");
    } catch {}
    document.documentElement.dataset.theme = t && ["harbour", "evergreen", "violet"].includes(t) ? t : "harbour";
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
    <div className="min-h-screen bg-outer px-6 py-6">
      <div className="mx-auto min-h-[calc(100vh-48px)] max-w-[1400px] rounded-[32px] bg-canvas p-5">
        <header className="flex h-[68px] items-center justify-between rounded-[22px] bg-white px-3">
          <Link href="/" className="flex h-12 w-12 items-center justify-center rounded-[14px] bg-surface2" aria-label="Keepline home">
            <Mark size={22} />
          </Link>
          <nav className="flex items-center gap-1.5">
            {ROUTES.map((r) => (
              <Link
                key={r.href}
                href={r.href}
                className={cn("rounded-full px-4 py-2.5 text-[14px] transition-colors", path === r.href ? "bg-sig text-white" : "bg-surface2 text-fg hover:bg-surface3")}
              >
                {r.label}
              </Link>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            <AskPanel />
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-surface2"><Settings className="h-[18px] w-[18px]" strokeWidth={1.6} /></span>
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-surface2"><Bell className="h-[18px] w-[18px]" strokeWidth={1.6} /></span>
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-sig text-[13px] font-medium text-white" title="Dave MacLeod, COO">DM</span>
          </div>
        </header>
        <main className="px-2 pb-6 pt-8">{children}</main>
      </div>
    </div>
  );
}

export function Mark({ size = 16, light }: { size?: number; light?: boolean }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" aria-hidden>
      <path d="M3 17 L9 11 L13 15 L21 7" stroke={light ? "#ffffff" : "#111111"} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Logo({ size = 30 }: { size?: number }) {
  return <Mark size={size} />;
}
