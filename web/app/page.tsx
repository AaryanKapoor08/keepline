"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useData, fmtDate } from "@/lib/data";
import { PageTop, Card, Details, Big, Avatar } from "@/components/kit";
import { cn } from "@/components/ui";

const TEAM_LABEL: Record<string, string> = { engineering: "Engineering", it: "IT", finance: "Finance", operations: "Compliance", member_services: "Member services", leadership: "Leadership" };
const days = (d: string) => Math.round((new Date(d + "T12:00:00").getTime() - new Date("2026-09-04T12:00:00").getTime()) / 864e5);

export default function Home() {
  const router = useRouter();
  const meta = useData("/meta", "meta").data;
  const risk = useData("/risk", "risk").data;
  const latest = useData("/history/latest", "history_latest").data;
  const people: any[] = meta?.people ?? [];
  const leaving = people.filter((p) => p.departure_date).sort((a, b) => (a.departure_date < b.departure_date ? -1 : 1));
  const joining = people.filter((p) => p.start_date > "2026-09-04");
  const bf1 = (risk ?? []).filter((r: any) => r.bus_factor <= 1).length;
  const top: any[] = (risk ?? []).slice(0, 3);
  const teams: Record<string, number> = {};
  for (const p of people) teams[p.team] = (teams[p.team] ?? 0) + 1;

  return (
    <>
      <PageTop title="Good morning, Dave." action="Open Sarah's knowledge" onAction={() => router.push("/graph?person=sarah")} />
      <div className="grid grid-cols-[1.2fr_1fr_1fr] gap-4">
        <Card title="Upcoming departures" right={<Details href="/graph">Knowledge map</Details>}>
          {leaving.map((p, i) => (
            <Link key={p.id} href={`/graph?person=${p.id}`} className={cn("flex items-center gap-3 border-b border-[var(--line)] py-3 last:border-0", i === 0 && "")}>
              <Avatar id={p.id} size={40} />
              <div className="flex-1">
                <div className="text-[16px] font-medium">{p.name}</div>
                <div className="text-[13px] text-muted">{p.role}</div>
              </div>
              <div className="text-right">
                <div className={cn("text-[15px]", i === 0 && "font-medium text-alarm")}>{fmtDate(p.departure_date)}</div>
                <div className="text-[12.5px] text-muted">in {days(p.departure_date)} days</div>
              </div>
              <span className="text-muted">›</span>
            </Link>
          ))}
        </Card>

        <Card title="Knowledge health" dark right={<Details href="/graph" dark>View details</Details>}>
          <Big value={bf1 || "—"} unit={`/${risk?.length ?? 10}`} caption={<>areas only one<br />person knows</>} dark />
          <div className="mt-6 grid grid-cols-2 gap-3">
            <div className="rounded-[16px] bg-white/[0.07] p-4">
              <div className="text-[26px] font-medium">{meta?.n_facts ?? "—"}</div>
              <div className="text-[12.5px] text-white/60">facts captured</div>
            </div>
            <div className="rounded-[16px] bg-white/[0.07] p-4">
              <div className="text-[26px] font-medium">{meta?.n_docs?.toLocaleString() ?? "—"}</div>
              <div className="text-[12.5px] text-white/60">receipts, DMs excluded</div>
            </div>
          </div>
        </Card>

        <Card title="Most at risk" right={<Details href="/graph?simulate=corelink_v3">Simulate</Details>}>
          {top.map((r) => (
            <div key={r.area_id} className="flex items-center justify-between border-b border-[var(--line)] py-3 last:border-0">
              <div>
                <div className="text-[15px]">{r.area_name}</div>
                <div className="text-[12.5px] text-muted">{r.bus_factor <= 1 ? `only ${r.at_risk_person_id ? r.at_risk_person_id[0].toUpperCase() + r.at_risk_person_id.slice(1) : "one person"}` : `${r.bus_factor} people`} · leaves in {r.countdown_days ?? "—"} days</div>
              </div>
              <div className={cn("text-[24px] font-medium tabular-nums", r.risk >= 0.5 && "text-alarm")}>{Math.round(r.risk * 100)}</div>
            </div>
          ))}
        </Card>
      </div>

      <div className="mt-4 grid grid-cols-[1.4fr_1fr_1fr] gap-4">
        <Card title="Latest changes" right={<Details href="/history">History</Details>}>
          {(latest ?? []).map((c: any) => (
            <div key={c.sha} className="flex items-start gap-3 border-b border-[var(--line)] py-3 last:border-0">
              <span className="mt-0.5 font-mono text-[12.5px] text-muted">{c.sha}</span>
              <div className="flex-1">
                <div className="text-[14.5px] leading-snug">{c.message}</div>
                <div className="text-[12.5px] text-muted">{c.author_name} · {fmtDate(c.valid_from)}</div>
              </div>
              {c.supersedes && <span className="rounded-full bg-surface2 px-2.5 py-1 text-[12px]">replaces a fact</span>}
            </div>
          ))}
        </Card>
        <Card title="Joining" right={<Details href="/graph?as=alex">Onboard</Details>}>
          {joining.map((p) => (
            <div key={p.id} className="flex items-center gap-3 rounded-[16px] bg-surface2 p-4">
              <Avatar id={p.id} size={44} />
              <div>
                <div className="text-[16px] font-medium">{p.name}</div>
                <div className="text-[13px] text-muted">{TEAM_LABEL[p.team]} · starts {fmtDate(p.start_date)}</div>
              </div>
            </div>
          ))}
          <div className="mt-3 text-[13.5px] text-muted">Joins Sarah&apos;s team the Monday after she leaves.</div>
        </Card>
        <Card title="People & teams">
          <Big value={people.length || "—"} caption={`people · ${Object.keys(teams).length} teams`} />
          <div className="mt-4 flex flex-wrap gap-2">
            {Object.entries(teams).map(([t, n]) => (
              <span key={t} className="rounded-full bg-surface2 px-3 py-1.5 text-[13px]">{TEAM_LABEL[t] ?? t} <span className="text-muted">{n}</span></span>
            ))}
          </div>
        </Card>
      </div>
    </>
  );
}
