"use client";

import type { ReactNode } from "react";
import { WalletProvider } from "@/context/WalletContext";
import { SkyShieldDataProvider } from "@/context/SkyShieldDataContext";

/** App-wide client providers for the SkyShield AI dashboard. */
export function Providers({ children }: { children: ReactNode }) {
  return (
    <WalletProvider>
      <SkyShieldDataProvider>{children}</SkyShieldDataProvider>
    </WalletProvider>
  );
}
