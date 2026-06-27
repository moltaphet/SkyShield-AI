# SkyShield AI — Frontend

Next.js (App Router) + TypeScript + Tailwind CSS v4 frontend for **SkyShield AI**,
the autonomous parametric flight-insurance protocol. It connects to the
`SkyShieldAI` Intelligent Contract on GenLayer through
[`genlayer-js`](https://www.npmjs.com/package/genlayer-js), using the ABI in
`src/abi/skyshield-abi.json`.

The UI ships a custom **"Dark Aviation / Cyberpunk Sky"** theme: deep-navy backdrop
with an animated starfield + drifting clouds, glassmorphism cards with neon
blue/amber borders, a sweeping radar indicator, and Orbitron/Inter typography.

## Getting started

```bash
cd frontend
npm install

# Configure the contract + network
cp .env.local.example .env.local
# then edit .env.local:
#   NEXT_PUBLIC_SKYSHIELD_CONTRACT_ADDRESS=0x91dCD64Fa828b5003688de07C6DCf052cF75E931
#   NEXT_PUBLIC_GENLAYER_CHAIN=studionet   (studionet | localnet | testnetAsimov | testnetBradbury)

npm run dev      # http://localhost:3000
```

The contract address defaults to the live studionet deployment when the env var is
unset. studionet RPC: `https://studio.genlayer.com/api`.

Other scripts: `npm run build`, `npm run start`, `npm run typecheck`.

## Folder layout

```
frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx          # Root layout, fonts (Orbitron/Inter), backdrop
│   │   ├── page.tsx            # Single-page dashboard composition
│   │   └── globals.css         # Tailwind v4 + aviation/cyberpunk theme
│   ├── components/
│   │   ├── Providers.tsx       # Wallet + SkyShield data providers
│   │   └── skyshield/
│   │       ├── Starfield.tsx   # Animated stars + drifting clouds
│   │       ├── TopBar.tsx      # Nav + wallet connect
│   │       ├── Hero.tsx        # Title, tagline, live pool stats, radar
│   │       ├── HowItWorks.tsx  # Buy → AI Prices → Monitored → Payout
│   │       ├── BuyPolicy.tsx   # Flight form + live AI risk gauge & premium preview
│   │       ├── MyPolicies.tsx  # Boarding board with live status badges
│   │       ├── ClaimPanel.tsx  # Claimable balance + flight status monitor
│   │       ├── kit.tsx         # Card, SectionHeading, Stat, TxFeedback
│   │       └── status.ts       # Live policy → status badge mapping
│   ├── context/
│   │   ├── WalletContext.tsx       # Injected-wallet (EIP-1193) connection
│   │   └── SkyShieldDataContext.tsx # Pool/policy state + actions + live resolver
│   ├── hooks/
│   │   └── useTxAction.ts      # Write-tx lifecycle (pending/hash/error)
│   ├── lib/
│   │   ├── config.ts           # Env-driven chain config
│   │   ├── format.ts           # atto <-> token, bps <-> %, address/time helpers
│   │   ├── genlayer/
│   │   │   └── client.ts       # createClient factories (read / wallet / dev)
│   │   └── skyshield/
│   │       ├── config.ts       # Contract address + economic constants
│   │       ├── contract.ts     # Typed read/write wrappers + ABI re-export
│   │       ├── types.ts        # Policy, PoolStats, LpPosition
│   │       └── pricing.ts      # Client-side premium preview (mirrors on-chain math)
│   └── abi/
│       └── skyshield-abi.json  # Generated from the contract (genvm-lint schema)
├── .env.local.example
├── next.config.mjs
├── postcss.config.mjs
└── tsconfig.json
```

## Contract integration

- **Reads** (no wallet): `getPoolStats`, `getPolicy`, `getLpPosition`, `getClaimable`,
  `previewPremium`, `quotePayout` in `src/lib/skyshield/contract.ts` — all via
  `client.readContract({ address, functionName, args })`.
- **Writes** (wallet-connected): `provideLiquidity`, `withdrawLiquidity`,
  `purchasePolicy`, `checkFlightAndExecute`, `claim` — via `client.writeContract(...)`
  followed by `client.waitForTransactionReceipt({ hash, status })`.
- **Units:** all money is atto-scale `bigint` (`value * 10 ** 18`). Convert with
  `tokenToAtto` / `attoToToken`. Basis points render with `bpsToPercent`.
- **Instant preview:** `src/lib/skyshield/pricing.ts` reproduces the contract's
  deterministic premium math so the Buy Policy form quotes live; the authoritative
  `risk_bps` is always produced on-chain at purchase.

## Notes

- The wallet layer (`WalletContext.tsx` + `genlayer/client.ts`) targets an injected
  EIP-1193 provider (MetaMask-style). Swap in your preferred connector there; the
  rest of the app is decoupled from it.
- Keep `src/abi/skyshield-abi.json` in sync with the contract:
  `genvm-lint schema ../contracts/sky_shield_ai.py --output src/abi/skyshield-abi.json`.
