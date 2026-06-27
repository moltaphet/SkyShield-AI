"use client";

import { SectionHeading } from "./kit";

const STEPS = [
  {
    n: "01",
    icon: "🎫",
    title: "Buy Policy",
    body: "Enter your flight code and departure. Coverage is reserved from the underwriting vault the moment your policy is written.",
  },
  {
    n: "02",
    icon: "🧠",
    title: "AI Prices Risk",
    body: "An on-chain LLM scores delay & weather risk for that exact flight and prices the premium from fair odds plus a protocol margin.",
  },
  {
    n: "03",
    icon: "📡",
    title: "Flight Monitored",
    body: "After departure, every validator independently re-fetches live flight status over the native internet and agrees on the outcome.",
  },
  {
    n: "04",
    icon: "💸",
    title: "Auto Payout",
    body: "Delays trigger a tiered payout (20% / 50% / 100%) credited to your claim ledger automatically — on-time flights become LP yield.",
  },
];

export function HowItWorks() {
  return (
    <section id="how" className="section" style={{ maxWidth: 1180, margin: "0 auto", padding: "3rem 1.5rem" }}>
      <SectionHeading
        eyebrow="Protocol Flow"
        title="How It Works"
        subtitle="Four autonomous steps — from boarding pass to payout — all settled inside GenLayer consensus."
      />

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))",
          gap: "1.2rem",
        }}
      >
        {STEPS.map((s, i) => (
          <div key={s.n} className="glass" style={{ padding: "1.6rem", position: "relative" }}>
            <div
              className="font-head"
              style={{
                position: "absolute",
                top: "1rem",
                right: "1.2rem",
                fontSize: "1.6rem",
                color: "rgba(0,180,255,0.18)",
                fontWeight: 800,
              }}
            >
              {s.n}
            </div>
            <div style={{ fontSize: "2rem", marginBottom: "0.8rem" }}>{s.icon}</div>
            <h3 className="cyan-text" style={{ fontSize: "1.1rem", margin: "0 0 0.6rem" }}>
              {s.title}
            </h3>
            <p className="dim" style={{ fontSize: "0.9rem", lineHeight: 1.6, margin: 0 }}>
              {s.body}
            </p>
            {i < STEPS.length - 1 && (
              <div
                className="cyan-text arrow-flow"
                style={{
                  position: "absolute",
                  right: "-0.85rem",
                  top: "50%",
                  fontSize: "1.2rem",
                  opacity: 0.6,
                }}
              >
                →
              </div>
            )}
          </div>
        ))}
      </div>
      <style>{`@media (max-width: 980px){ .arrow-flow{ display:none; } }`}</style>
    </section>
  );
}
