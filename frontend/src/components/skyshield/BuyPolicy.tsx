"use client";

import { useMemo, useState } from "react";
import { useSkyShieldData } from "@/context/SkyShieldDataContext";
import { useWallet } from "@/context/WalletContext";
import { attoToToken } from "@/lib/format";
import {
  COVERAGE_PACKAGES,
  quotePremiumAtto,
  riskBand,
  simulateRiskBps,
} from "@/lib/skyshield/pricing";
import { Card, SectionHeading, TxFeedback } from "./kit";

const RISK_COLORS: Record<string, string> = {
  LOW: "var(--sky-lime)",
  MODERATE: "var(--sky-cyan)",
  HIGH: "var(--sky-amber)",
  EXTREME: "var(--sky-red)",
};

function defaultDeparture(): string {
  const d = new Date(Date.now() + 36 * 3600 * 1000);
  d.setMinutes(0, 0, 0);
  // datetime-local wants YYYY-MM-DDTHH:mm in local time.
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function BuyPolicy() {
  const { purchasePolicy } = useSkyShieldData();
  const { isConnected, connect } = useWallet();

  const [flightCode, setFlightCode] = useState("BA245");
  const [departure, setDeparture] = useState(defaultDeparture);
  const [coverageId, setCoverageId] = useState(COVERAGE_PACKAGES[0].id);
  const [pending, setPending] = useState(false);
  const [txHash, setTxHash] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const coverage = COVERAGE_PACKAGES.find((c) => c.id === coverageId) ?? COVERAGE_PACKAGES[0];
  const departureTs = useMemo(() => Math.floor(new Date(departure).getTime() / 1000), [departure]);

  const { riskBps, band, premiumAtto } = useMemo(() => {
    if (!flightCode.trim() || !Number.isFinite(departureTs)) {
      return { riskBps: 0, band: riskBand(0), premiumAtto: 0n };
    }
    const r = simulateRiskBps(flightCode, departureTs);
    return { riskBps: r, band: riskBand(r), premiumAtto: quotePremiumAtto(coverage.coverageAtto, BigInt(r)) };
  }, [flightCode, departureTs, coverage.coverageAtto]);

  async function onBuy() {
    setError(null);
    setTxHash(null);
    if (!flightCode.trim()) return setError("Enter a flight code.");
    if (!Number.isFinite(departureTs)) return setError("Pick a valid departure time.");
    setPending(true);
    try {
      await purchasePolicy({ flightCode, departureTs, coverageAtto: coverage.coverageAtto });
      setTxHash(`policy-${flightCode.trim().toUpperCase()}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Purchase failed.");
    } finally {
      setPending(false);
    }
  }

  const riskPct = Math.min(100, riskBps / 100);

  return (
    <section id="buy" className="section" style={{ maxWidth: 1180, margin: "0 auto", padding: "3rem 1.5rem" }}>
      <SectionHeading
        eyebrow="Underwriting Desk"
        title="Buy Policy"
        subtitle="The AI risk engine quotes your premium live as you type. The same deterministic math runs on-chain at purchase."
      />

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)", gap: "1.4rem" }} className="buy-grid">
        {/* Form */}
        <Card className="p-card">
          <div style={{ padding: "1.6rem", display: "grid", gap: "1.1rem" }}>
            <div>
              <label className="label">Flight Code</label>
              <input
                className="field"
                value={flightCode}
                onChange={(e) => setFlightCode(e.target.value.toUpperCase())}
                placeholder="e.g. BA245"
                maxLength={8}
              />
            </div>
            <div>
              <label className="label">Departure (local time)</label>
              <input
                className="field"
                type="datetime-local"
                value={departure}
                onChange={(e) => setDeparture(e.target.value)}
              />
            </div>
            <div>
              <label className="label">Coverage</label>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: "0.6rem" }}>
                {COVERAGE_PACKAGES.map((c) => {
                  const active = c.id === coverageId;
                  return (
                    <button
                      key={c.id}
                      onClick={() => setCoverageId(c.id)}
                      className="font-head"
                      style={{
                        cursor: "pointer",
                        padding: "0.7rem 0.4rem",
                        borderRadius: 12,
                        border: `1px solid ${active ? "var(--sky-blue)" : "var(--border)"}`,
                        background: active ? "rgba(0,180,255,0.14)" : "rgba(3,8,20,0.6)",
                        boxShadow: active ? "var(--glow-blue)" : "none",
                        color: active ? "#fff" : "var(--text-dim)",
                        transition: "all 0.2s ease",
                      }}
                    >
                      <div style={{ fontSize: "0.8rem" }}>{c.label}</div>
                      <div className="cyan-text" style={{ fontSize: "0.72rem", marginTop: "0.3rem" }}>
                        {attoToToken(c.coverageAtto, 0)} GEN
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            {isConnected ? (
              <button className="btn btn-primary" onClick={onBuy} disabled={pending} style={{ marginTop: "0.4rem" }}>
                {pending ? "Underwriting…" : `Buy · ${attoToToken(premiumAtto, 2)} GEN`}
              </button>
            ) : (
              <button className="btn btn-primary" onClick={connect} style={{ marginTop: "0.4rem" }}>
                Connect Wallet to Buy
              </button>
            )}
            <TxFeedback txHash={txHash} error={error} />
          </div>
        </Card>

        {/* Premium preview / risk gauge */}
        <Card amber>
          <div style={{ padding: "1.6rem" }}>
            <div className="label">AI Risk Assessment</div>
            <div className="font-head" style={{ fontSize: "2rem", color: RISK_COLORS[band.label], marginTop: "0.4rem" }}>
              {band.label}
            </div>

            {/* Risk gauge */}
            <div
              style={{
                height: 10,
                borderRadius: 999,
                marginTop: "1rem",
                background: "rgba(3,8,20,0.8)",
                border: "1px solid var(--border)",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  width: `${riskPct}%`,
                  height: "100%",
                  background: `linear-gradient(90deg, var(--sky-lime), var(--sky-amber), var(--sky-red))`,
                  transition: "width 0.4s ease",
                }}
              />
            </div>
            <div className="muted" style={{ fontSize: "0.74rem", marginTop: "0.4rem" }}>
              Estimated delay probability · {(riskBps / 100).toFixed(1)}%
            </div>

            <div style={{ borderTop: "1px solid var(--border)", margin: "1.4rem 0", paddingTop: "1.2rem", display: "grid", gap: "0.9rem" }}>
              <Row label="Coverage" value={`${attoToToken(coverage.coverageAtto, 0)} GEN`} />
              <Row label="Premium" value={`${attoToToken(premiumAtto, 4)} GEN`} accent />
              <Row label="Max Payout" value={`${attoToToken(coverage.coverageAtto, 0)} GEN`} />
            </div>

            <p className="muted" style={{ fontSize: "0.74rem", lineHeight: 1.5, margin: 0 }}>
              Payout tiers: 60–120 min → 20% · 120–240 min → 50% · &gt;240 min or cancelled → 100%.
            </p>
          </div>
        </Card>
      </div>
      <style>{`@media (max-width: 820px){ .buy-grid{ grid-template-columns: 1fr !important; } }`}</style>
    </section>
  );
}

function Row({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
      <span className="dim" style={{ fontSize: "0.85rem" }}>{label}</span>
      <span className={`font-head ${accent ? "amber-text" : "cyan-text"}`} style={{ fontSize: "1rem" }}>
        {value}
      </span>
    </div>
  );
}
