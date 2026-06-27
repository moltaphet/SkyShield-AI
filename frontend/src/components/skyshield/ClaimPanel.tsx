"use client";

import { useState } from "react";
import { useSkyShieldData } from "@/context/SkyShieldDataContext";
import { useWallet } from "@/context/WalletContext";
import { attoToToken } from "@/lib/format";
import { Card, SectionHeading, TxFeedback } from "./kit";
import { statusView } from "./status";

export function ClaimPanel() {
  const { claimable, claim, policies } = useSkyShieldData();
  const { isConnected, connect } = useWallet();

  const [pending, setPending] = useState(false);
  const [txHash, setTxHash] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const inFlight = policies.filter((p) => p.liveStatus === "ACTIVE" || p.liveStatus === "CHECKING_API");

  async function onClaim() {
    setError(null);
    setTxHash(null);
    setPending(true);
    try {
      const amount = await claim();
      setTxHash(`claimed-${attoToToken(amount, 4)}-GEN`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Claim failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <section id="claim" className="section" style={{ maxWidth: 1180, margin: "0 auto", padding: "3rem 1.5rem 5rem" }}>
      <SectionHeading
        eyebrow="Settlement"
        title="Claim"
        subtitle="Anyone can trigger a flight check; validators settle the payout tier by consensus. Approved payouts land in your claim ledger to withdraw."
      />

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(0,1.2fr)", gap: "1.4rem" }} className="claim-grid">
        {/* Claimable balance */}
        <Card>
          <div style={{ padding: "1.8rem", display: "flex", flexDirection: "column", height: "100%" }}>
            <div className="label">Claimable Balance</div>
            <div className="font-head lime-text neon-text" style={{ fontSize: "2.6rem", margin: "0.4rem 0 0.2rem" }}>
              {attoToToken(claimable, 4)}
            </div>
            <div className="muted" style={{ fontSize: "0.78rem", letterSpacing: "0.1em" }}>GEN</div>

            <div style={{ marginTop: "auto", paddingTop: "1.6rem" }}>
              {isConnected ? (
                <button
                  className="btn btn-amber"
                  onClick={onClaim}
                  disabled={pending || claimable <= 0n}
                  style={{ width: "100%" }}
                >
                  {pending ? "Withdrawing…" : "Claim Payout"}
                </button>
              ) : (
                <button className="btn btn-primary" onClick={connect} style={{ width: "100%" }}>
                  Connect Wallet
                </button>
              )}
              <TxFeedback txHash={txHash} error={error} />
            </div>
          </div>
        </Card>

        {/* Flight status monitor */}
        <Card>
          <div style={{ padding: "1.8rem" }}>
            <div className="label" style={{ marginBottom: "1rem" }}>Flight Status Monitor</div>
            {inFlight.length === 0 ? (
              <p className="dim" style={{ margin: 0, fontSize: "0.9rem" }}>
                No flights currently being monitored. Resolved payouts appear in your balance.
              </p>
            ) : (
              <div style={{ display: "grid", gap: "0.7rem" }}>
                {inFlight.map((p) => {
                  const view = statusView(p);
                  return (
                    <div
                      key={p.policyId}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        padding: "0.7rem 1rem",
                        borderRadius: 12,
                        border: "1px solid var(--border)",
                        background: "rgba(3,8,20,0.5)",
                      }}
                    >
                      <span className="font-head cyan-text" style={{ fontSize: "1rem" }}>{p.flightCode}</span>
                      <span className={`badge ${view.blink ? "blink" : ""}`} style={{ color: view.color }}>
                        {view.label}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </Card>
      </div>
      <style>{`@media (max-width: 820px){ .claim-grid{ grid-template-columns: 1fr !important; } }`}</style>
    </section>
  );
}
