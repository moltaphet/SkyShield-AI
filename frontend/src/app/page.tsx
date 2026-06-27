"use client";

import { TopBar } from "@/components/skyshield/TopBar";
import { Hero } from "@/components/skyshield/Hero";
import { HowItWorks } from "@/components/skyshield/HowItWorks";
import { BuyPolicy } from "@/components/skyshield/BuyPolicy";
import { MyPolicies } from "@/components/skyshield/MyPolicies";
import { ClaimPanel } from "@/components/skyshield/ClaimPanel";

export default function Page() {
  return (
    <main>
      <TopBar />
      <Hero />
      <HowItWorks />
      <BuyPolicy />
      <MyPolicies />
      <ClaimPanel />

      <footer
        style={{
          borderTop: "1px solid var(--border)",
          padding: "2rem 1.5rem",
          textAlign: "center",
        }}
      >
        <p className="font-head neon-text" style={{ fontSize: "0.95rem", margin: 0 }}>
          ✈ SKYSHIELD <span className="cyan-text">AI</span>
        </p>
        <p className="muted" style={{ fontSize: "0.78rem", marginTop: "0.6rem" }}>
          Autonomous parametric flight insurance · Built on{" "}
          <a href="https://genlayer.com" className="cyan-text" target="_blank" rel="noreferrer">
            GenLayer
          </a>{" "}
          ·{" "}
          <a href="https://x.com/0xehs4hn" className="cyan-text" target="_blank" rel="noreferrer">
            @0xehs4hn
          </a>
        </p>
      </footer>
    </main>
  );
}
