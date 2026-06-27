import type { Metadata } from "next";
import { Orbitron, Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/Providers";
import { Starfield } from "@/components/skyshield/Starfield";

const orbitron = Orbitron({
  subsets: ["latin"],
  weight: ["500", "600", "700", "800"],
  variable: "--font-orbitron",
  display: "swap",
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "SkyShield AI — Autonomous Flight Insurance on GenLayer",
  description:
    "Parametric flight-delay insurance that prices premiums and settles claims autonomously inside GenLayer consensus — no oracle, no keeper, no claims adjuster.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${orbitron.variable} ${inter.variable}`} suppressHydrationWarning>
      <body>
        <div className="sky-backdrop" aria-hidden />
        <Starfield />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
