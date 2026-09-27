"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState } from "react";
import { motion } from "motion/react";
import { useData, first } from "@/lib/data";
import { PageTop, Card, Big, Row, Fade, Details } from "@/components/kit";
import { cn } from "@/components/ui";

const SHORT: Record<string, string> = { reconciliation: "Reconciliation", corelink_api: "CoreLink API", ssl_dns: "SSL & DNS" };
const LABEL: Record<string, string> = {
  sole_access: "systems only she can access",
  orphaned_landmine: "never-do-this rules",
  unowned_recurring_task: "recurring tasks with no owner",
};

export default function RiskPage() {
  const wi = useData("/whatif/sarah", "whatif_sarah").data;
  const risk = useData("/risk", "risk").data;
  const [sim, setSim] = useState(false);
  const [all, setAll] = useState(false);
  const orphaned: string[] = wi?.orphaned_areas ?? [];
  const riskBy: Record<string, any> = Object.fromEntries((risk ?? []).map((r: any) => [r.area_id, r]));
  const c = wi?.break_counts ?? {};
  const breaks: any[] = wi?.breaks ?? [];
  return (
    <>
      <PageTop title={`${orphaned.length || 3} systems. No one else knows them.`} action={sim ? "Reset" : "Simulate her leaving"} onAction={() => setSim(!sim)} />
      <div className="grid grid-cols-3 gap-4">
        {orphaned.map((a, i) => {
          const r = riskBy[a];
          return (
            <Card key={a} title={SHORT[a] ?? a} delay={i * 0.05} right={<span className={cn("text-[13px]", sim ? "text-alarm" : "text-muted")}>{sim ? "bus factor 0" : "bus factor 1"}</span>}>
              <motion.div animate={{ backgroundColor: sim ? "#fbeceb" : "#f4f5f7" }} transition={{ duration: 0.7 }} className="rounded-[18px] p-5">
                <Big value={r ? Math.round(r.risk * 100) : "—"} unit="/100" caption="risk" red={sim} />
                <div className="mt-4 text-[15px] text-muted">
                  {sim ? "No one left with hands-on evidence." : <>Hands-on: {first(r?.experts?.[0]?.[0])} only. Leaves in {r?.countdown_days ?? "—"} days.</>}
                </div>
              </motion.div>
            </Card>
          );
        })}
      </div>
      <Fade show={sim} className="mt-4">
        <Card title="What breaks on Monday" right={<Details onClick={() => setAll(!all)} open={all}>{all ? "Hide list" : "View all"}</Details>}>
          <div className="grid grid-cols-3 gap-4">
            {Object.keys(LABEL).map((k, i) => (
              <motion.div key={k} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 + i * 0.2 }} className={cn("rounded-[18px] p-5", k === "orphaned_landmine" ? "bg-[#111] text-white" : "bg-[#f4f5f7]")}>
                <Big value={c[k] ?? 0} caption={LABEL[k]} red={false} dark={k === "orphaned_landmine"} />
              </motion.div>
            ))}
          </div>
          {all && (
            <div className="mt-4">
              {Object.keys(LABEL).map((k) => (
                <Row key={k} label={LABEL[k].replace(/^./, (x) => x.toUpperCase())} value={c[k] ?? 0} strong>
                  <div className="space-y-2 text-[14px]">
                    {breaks.filter((b) => b.type === k).slice(0, 6).map((b, i) => (
                      <div key={i}>{b.text} <span className="text-muted">· {b.area_name}</span></div>
                    ))}
                  </div>
                </Row>
              ))}
            </div>
          )}
        </Card>
      </Fade>
    </>
  );
}
