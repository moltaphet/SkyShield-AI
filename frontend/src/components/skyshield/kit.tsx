"use client";

import type { ReactNode } from "react";

/** Glassmorphism card with a glowing blue (or amber) border. */
export function Card({
  children,
  className = "",
  amber = false,
}: {
  children: ReactNode;
  className?: string;
  amber?: boolean;
}) {
  return (
    <div className={`glass ${amber ? "glass-amber" : ""} ${className}`}>{children}</div>
  );
}

/** Section heading with an eyebrow label and an animated scan line. */
export function SectionHeading({
  eyebrow,
  title,
  subtitle,
}: {
  eyebrow: string;
  title: string;
  subtitle?: string;
}) {
  return (
    <div style={{ marginBottom: "2rem", maxWidth: 720 }}>
      <div
        className="font-head cyan-text"
        style={{ fontSize: "0.72rem", letterSpacing: "0.22em", textTransform: "uppercase" }}
      >
        {eyebrow}
      </div>
      <h2 className="neon-text" style={{ fontSize: "clamp(1.6rem, 3.5vw, 2.4rem)", margin: "0.4rem 0 0.7rem" }}>
        {title}
      </h2>
      <div className="scanline" style={{ width: 120 }} />
      {subtitle && (
        <p className="dim" style={{ marginTop: "1rem", lineHeight: 1.6, fontSize: "0.98rem" }}>
          {subtitle}
        </p>
      )}
    </div>
  );
}

/** Compact stat read-out (altitude-indicator style). */
export function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: ReactNode;
  accent?: "blue" | "amber" | "lime";
}) {
  const color =
    accent === "amber" ? "var(--sky-amber)" : accent === "lime" ? "var(--sky-lime)" : "var(--sky-cyan)";
  return (
    <div>
      <div className="label" style={{ marginBottom: "0.2rem" }}>
        {label}
      </div>
      <div className="font-head" style={{ fontSize: "1.25rem", color }}>
        {value}
      </div>
    </div>
  );
}

/** Inline transaction feedback (hash / error). */
export function TxFeedback({ txHash, error }: { txHash?: string | null; error?: string | null }) {
  if (error) {
    return (
      <p style={{ color: "var(--sky-red)", fontSize: "0.82rem", marginTop: "0.7rem" }}>⚠ {error}</p>
    );
  }
  if (txHash) {
    return (
      <p className="lime-text" style={{ fontSize: "0.82rem", marginTop: "0.7rem" }}>
        ✓ Confirmed · {txHash.slice(0, 10)}…{txHash.slice(-6)}
      </p>
    );
  }
  return null;
}
