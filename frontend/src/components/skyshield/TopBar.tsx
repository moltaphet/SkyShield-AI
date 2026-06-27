"use client";

import { useWallet } from "@/context/WalletContext";
import { shortenAddress } from "@/lib/format";

const NAV = [
  { id: "how", label: "How It Works" },
  { id: "buy", label: "Buy Policy" },
  { id: "policies", label: "My Policies" },
  { id: "claim", label: "Claim" },
];

export function TopBar() {
  const { address, isConnected, isConnecting, connect, disconnect, hasProvider } = useWallet();

  return (
    <header
      style={{
        position: "sticky",
        top: 0,
        zIndex: 50,
        backdropFilter: "blur(10px)",
        background: "rgba(5, 10, 26, 0.7)",
        borderBottom: "1px solid var(--border)",
      }}
    >
      <div
        style={{
          maxWidth: 1180,
          margin: "0 auto",
          padding: "0.9rem 1.5rem",
          display: "flex",
          alignItems: "center",
          gap: "1.5rem",
        }}
      >
        <a href="#top" className="font-head neon-text" style={{ fontSize: "1.15rem", fontWeight: 800 }}>
          ✈ SKYSHIELD<span className="cyan-text"> AI</span>
        </a>

        <nav style={{ display: "flex", gap: "1.3rem", marginLeft: "auto" }} className="topnav">
          {NAV.map((n) => (
            <a
              key={n.id}
              href={`#${n.id}`}
              className="font-head dim"
              style={{ fontSize: "0.72rem", letterSpacing: "0.1em", textTransform: "uppercase" }}
            >
              {n.label}
            </a>
          ))}
        </nav>

        {isConnected ? (
          <button className="btn" onClick={disconnect} title={address ?? ""}>
            {shortenAddress(address ?? "")}
          </button>
        ) : (
          <button className="btn btn-primary" onClick={connect} disabled={isConnecting}>
            {isConnecting ? "Connecting…" : hasProvider ? "Connect Wallet" : "Install Wallet"}
          </button>
        )}
      </div>
      <style>{`@media (max-width: 760px){ .topnav{ display:none !important; } }`}</style>
    </header>
  );
}
