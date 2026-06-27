"use client";

import { useSkyShieldData } from "@/context/SkyShieldDataContext";
import { SKYSHIELD_CONTRACT_ADDRESS, isSkyShieldConfigured } from "@/lib/skyshield/config";
import { attoToToken, shortenAddress } from "@/lib/format";
import { Stat } from "./kit";

export function Hero() {
  const { stats } = useSkyShieldData();

  return (
    <section
      id="top"
      className="section"
      style={{
        maxWidth: 1180,
        margin: "0 auto",
        padding: "5rem 1.5rem 3rem",
        display: "grid",
        gridTemplateColumns: "minmax(0,1.3fr) minmax(0,1fr)",
        gap: "3rem",
        alignItems: "center",
      }}
    >
      <div>
        <div
          className="badge cyan-text"
          style={{ marginBottom: "1.4rem" }}
        >
          LIVE ON GENLAYER · STUDIONET
        </div>

        <h1
          className="neon-text"
          style={{ fontSize: "clamp(2.6rem, 7vw, 5rem)", lineHeight: 1.02, margin: 0, fontWeight: 800 }}
        >
          SkyShield <span className="cyan-text">AI</span>
        </h1>
        <p
          className="font-head"
          style={{
            fontSize: "clamp(1rem, 2.4vw, 1.4rem)",
            color: "var(--sky-silver)",
            marginTop: "1.1rem",
            letterSpacing: "0.04em",
          }}
        >
          Autonomous Flight Insurance on GenLayer
        </p>
        <p className="dim" style={{ fontSize: "1.02rem", lineHeight: 1.65, marginTop: "1.2rem", maxWidth: 560 }}>
          Buy a policy, fly, and get paid automatically. Premiums are priced by an
          on-chain AI from live flight risk, and delay claims settle inside consensus —
          with <span className="cyan-text">no oracle, no keeper, and no claims adjuster</span>.
        </p>

        <div style={{ display: "flex", gap: "1rem", marginTop: "2rem", flexWrap: "wrap" }}>
          <a href="#buy" className="btn btn-primary">Buy a Policy</a>
          <a href="#how" className="btn">How It Works</a>
        </div>

        <div
          className="muted"
          style={{ marginTop: "1.6rem", fontSize: "0.78rem", fontFamily: "var(--font-head)", letterSpacing: "0.06em" }}
        >
          CONTRACT&nbsp;
          <span className="cyan-text" title={SKYSHIELD_CONTRACT_ADDRESS}>
            {shortenAddress(SKYSHIELD_CONTRACT_ADDRESS)}
          </span>
          {!isSkyShieldConfigured && <span className="amber-text"> · SIMULATION MODE</span>}
        </div>
      </div>

      {/* Radar + altitude-style stat panel */}
      <div className="glass" style={{ padding: "1.8rem" }}>
        <div style={{ display: "flex", justifyContent: "center", marginBottom: "1.6rem" }}>
          <div className="radar" style={{ width: 170, height: 170 }}>
            <div
              className="font-head cyan-text"
              style={{
                position: "absolute",
                inset: 0,
                display: "grid",
                placeItems: "center",
                fontSize: "0.7rem",
                letterSpacing: "0.12em",
                textShadow: "0 0 10px var(--sky-blue)",
              }}
            >
              MONITORING
            </div>
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.2rem 1rem" }}>
          <Stat label="Pool TVL" value={`${attoToToken(stats.totalAssets, 0)} GEN`} />
          <Stat label="Available" value={`${attoToToken(stats.availableLiquidity, 0)} GEN`} accent="lime" />
          <Stat label="Coverage Locked" value={`${attoToToken(stats.lockedCoverage, 0)} GEN`} accent="amber" />
          <Stat label="Policies Written" value={stats.policyCount.toLocaleString()} />
        </div>
      </div>

      <style>{`@media (max-width: 880px){ #top{ grid-template-columns: 1fr !important; } }`}</style>
    </section>
  );
}
