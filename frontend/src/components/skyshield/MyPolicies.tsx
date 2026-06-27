"use client";

import { useSkyShieldData } from "@/context/SkyShieldDataContext";
import { attoToToken, formatTimestamp } from "@/lib/format";
import { SectionHeading } from "./kit";
import { statusView } from "./status";

export function MyPolicies() {
  const { policies } = useSkyShieldData();

  return (
    <section id="policies" className="section" style={{ maxWidth: 1180, margin: "0 auto", padding: "3rem 1.5rem" }}>
      <SectionHeading
        eyebrow="Boarding Board"
        title="My Policies"
        subtitle="Live status for every policy. The autonomous resolver moves passes from monitoring → checking → resolved in real time."
      />

      {policies.length === 0 ? (
        <div className="glass" style={{ padding: "2.5rem", textAlign: "center" }}>
          <p className="dim" style={{ margin: 0 }}>No policies yet — write your first one above.</p>
        </div>
      ) : (
        <div style={{ display: "grid", gap: "0.9rem" }}>
          {policies.map((p) => {
            const view = statusView(p);
            return (
              <div
                key={p.policyId}
                className="glass"
                style={{
                  padding: "1.1rem 1.4rem",
                  display: "grid",
                  gridTemplateColumns: "auto 1fr auto auto",
                  gap: "1.4rem",
                  alignItems: "center",
                }}
              >
                {/* Flight code */}
                <div>
                  <div className="muted" style={{ fontSize: "0.62rem", letterSpacing: "0.14em" }}>FLIGHT</div>
                  <div className="font-head cyan-text" style={{ fontSize: "1.2rem" }}>{p.flightCode}</div>
                </div>

                {/* Departure */}
                <div className="dep-cell">
                  <div className="muted" style={{ fontSize: "0.62rem", letterSpacing: "0.14em" }}>DEPARTURE</div>
                  <div className="dim" style={{ fontSize: "0.85rem" }}>
                    {formatTimestamp(BigInt(p.departureTs))}
                  </div>
                </div>

                {/* Coverage / payout */}
                <div style={{ textAlign: "right" }} className="cov-cell">
                  <div className="muted" style={{ fontSize: "0.62rem", letterSpacing: "0.14em" }}>
                    {p.status === "RESOLVED" ? "PAYOUT" : "COVERAGE"}
                  </div>
                  <div
                    className={`font-head ${p.status === "RESOLVED" ? "lime-text" : "cyan-text"}`}
                    style={{ fontSize: "1rem" }}
                  >
                    {p.status === "RESOLVED"
                      ? `${attoToToken(p.payoutAmount, 0)} GEN`
                      : `${attoToToken(p.maxPayout, 0)} GEN`}
                  </div>
                </div>

                {/* Status badge */}
                <div
                  className={`badge ${view.blink ? "blink" : ""}`}
                  style={{ color: view.color, justifySelf: "end" }}
                >
                  {view.label}
                </div>
              </div>
            );
          })}
        </div>
      )}
      <style>{`@media (max-width: 720px){
        #policies .glass[style*="grid-template-columns"]{ grid-template-columns: 1fr 1fr !important; }
        #policies .dep-cell{ display:none; }
      }`}</style>
    </section>
  );
}
