"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useRouter } from "next/navigation";
import { useData } from "@/lib/data";
import { PageTop, Card, Details, Big, Bars, Row, Avatar } from "@/components/kit";

const SHORT: Record<string, string> = { reconciliation: "Reconciliation", corelink_api: "CoreLink API", ssl_dns: "SSL & DNS" };

export default function Home() {
  const router = useRouter();
  const meta = useData("/meta", "meta").data;
  const wi = useData("/whatif/sarah", "whatif_sarah").data;
  const prof = useData("/profile/sarah", "profile_sarah").data;
  const c = wi?.break_counts ?? {};
  const orphaned: string[] = wi?.orphaned_areas ?? [];
  return (
    <>
      <PageTop title="Sarah Chen leaves Friday." action="See what leaves with her" onAction={() => router.push("/graph")} />
      <div className="grid grid-cols-[1fr_1.15fr_1fr] gap-4">
        <Card title="Sarah Chen" right={<Details href="/graph">Her knowledge</Details>}>
          <div className="flex flex-1 flex-col items-center justify-center py-4 text-center">
            <Avatar id="sarah" size={96} />
            <div className="mt-4 text-[22px] font-medium">Sarah Chen</div>
            <div className="text-[15px] text-muted">Senior Backend Engineer</div>
            <div className="mt-5 flex gap-2">
              <span className="rounded-full bg-[#f4f5f7] px-4 py-2 text-[14px]">Last day Sep 11</span>
              <span className="rounded-full bg-[#f4f5f7] px-4 py-2 text-[14px]">{prof?.n_facts ?? "—"} facts</span>
            </div>
          </div>
        </Card>

        <Card title="Only Sarah knows" right={<Details href="/risk">View details</Details>} delay={0.05}>
          <div className="rounded-[18px] bg-[#f4f5f7] p-5">
            <Big value={wi?.breaks?.length ?? "—"} caption={<>things that leave<br />with her</>} />
          </div>
          <div className="mt-3">
            <Bars
              height={110}
              items={[
                { label: "Recurring tasks", value: c.unowned_recurring_task ?? 0, strong: true },
                { label: "Landmines", value: c.orphaned_landmine ?? 0, red: true },
                { label: "Sole access", value: c.sole_access ?? 0 },
                { label: "Vendor contacts", value: c.vendor_contact_lost ?? 0 },
              ]}
            />
          </div>
        </Card>

        <Card title="Bus factor 1" dark right={<Details href="/risk" dark>Simulate</Details>} delay={0.1}>
          <div className="flex flex-1 flex-col justify-between">
            <Big value={orphaned.length || "—"} caption={<>systems no one<br />else knows</>} dark />
            <div className="mt-6 space-y-2">
              {orphaned.map((a) => (
                <div key={a} className="flex items-center justify-between rounded-[14px] bg-white/[0.07] px-4 py-3 text-[16px]">
                  {SHORT[a] ?? a}
                  <span className="text-[13px] text-white/50">only Sarah</span>
                </div>
              ))}
            </div>
          </div>
        </Card>
      </div>

      <div className="mt-4 grid grid-cols-[1.15fr_1fr] gap-4">
        <Card title="Company memory" delay={0.15}>
          <Row label="Receipts ingested" value={meta?.n_docs?.toLocaleString() ?? "—"} strong>
            <div className="space-y-1.5 text-[14px] text-muted">
              {Object.entries(meta?.docs_by_source ?? {}).map(([k, v]: any) => (
                <div key={k} className="flex justify-between"><span className="capitalize">{k}</span><span className="tabular-nums">{v.toLocaleString()}</span></div>
              ))}
              <div className="flex justify-between"><span>Excluded as private</span><span className="tabular-nums">{meta ? (meta.n_corpus - meta.n_docs).toLocaleString() : "—"}</span></div>
            </div>
          </Row>
          <Row label="Facts in versioned memory" value={meta?.n_facts ?? "—"} strong>
            <div className="text-[14px] text-muted">{meta?.n_superseded} were replaced by newer facts. Both versions are kept, with who said them and when.</div>
          </Row>
          <Row label="People" value={meta?.n_people ?? "—"} strong>
            <div className="text-[14px] text-muted">Also leaving: Mike O&apos;Brien (Oct 30), Tom Bouchard (Dec 18).</div>
          </Row>
        </Card>
        <Card title="Alex Rivera starts Monday" right={<Details href="/ask">Ask as Alex</Details>} delay={0.2}>
          <div className="flex flex-1 items-center gap-5 rounded-[18px] bg-[#f4f5f7] p-5">
            <Avatar id="alex" size={56} />
            <div className="text-[16px] leading-snug text-muted">
              He gets answers from Sarah&apos;s receipts, or an honest &ldquo;I don&apos;t know, ask Mike.&rdquo;
            </div>
          </div>
        </Card>
      </div>
    </>
  );
}
