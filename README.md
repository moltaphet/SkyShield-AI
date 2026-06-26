<div align="center">

# 🏦 GenVault

### Intelligent Staking & Yield Optimizer on GenLayer

**Stake → Auto-Compound → Optimize.** A trust-minimized vault where yield accrues
from the consensus block clock and compounds geometrically — with no external
keeper, oracle, or cron job in the loop.

[![GitHub](https://img.shields.io/badge/GitHub-moltaphet%2FGenVault-181717?logo=github)](https://github.com/moltaphet/GenVault)
[![X](https://img.shields.io/badge/X-@0xehs4hn-000000?logo=x)](https://x.com/0xehs4hn)
[![GenLayer](https://img.shields.io/badge/Built%20on-GenLayer-34d399)](https://genlayer.com)

</div>

---

## Overview

GenVault is an **Intelligent Staking & Yield Optimizer** built on the
[GenLayer](https://genlayer.com) protocol. Its core is the
**`SmartStakingOptimizer`** Intelligent Contract — a deterministic, consensus-safe
vault that lets accounts stake tokens, accrues yield over time from a configurable
APY/APR, and automatically re-stakes (compounds) that yield back into each
account's principal.

Because every balance update is re-executed and agreed upon by GenLayer's
validators, and because time comes from the **deterministic consensus block
timestamp**, the vault needs no off-chain automation to stay correct. Compounding
lifts the principal that the next interval is measured against, so positions grow
**geometrically** rather than linearly.

- **Live contract address:** `0x43050A476485547450Aa80A4Bf059D17CE17CC28`

## Key capabilities

| Capability | Description | Entry points |
|---|---|---|
| **Staking** | Per-account principal and yield tracking in atto precision | `stake(amount)` |
| **Intelligent compounding** | Timestamp-driven yield re-staked into principal; keeperless | `compound_rewards()`, `compound_for(staker)` |
| **Withdrawals** | Partial and maximum (principal + compounded rewards) | `withdraw(amount)`, `withdraw_max()` |
| **Live reads** | Gas-free position & protocol views for the UI | `get_account`, `get_stats`, `preview_pending`, … |

## Technical stack

| Layer | Technology |
|---|---|
| **Intelligent Contract** | Python · [GenLayer](https://genlayer.com) GenVM · `genvm-linter` · `genlayer-test` |
| **Frontend** | [Next.js 16](https://nextjs.org) (App Router) · React 19 · TypeScript 5 |
| **Styling** | [Tailwind CSS v4](https://tailwindcss.com) · glassmorphism · dark/light theming |
| **Web3 client** | [`genlayer-js`](https://www.npmjs.com/package/genlayer-js) · EIP-1193 wallet (MetaMask) |
| **Icons** | `lucide-react` + inline brand SVGs |

## Architecture

```
genvault/
├── contracts/
│   └── smart_staking_optimizer.py     # SmartStakingOptimizer Intelligent Contract
├── tests/
│   └── direct/
│       └── test_smart_staking_optimizer.py   # Fast in-memory (direct-mode) tests
├── docs/
│   ├── ARCHITECTURE.md                # Contract design + full ABI reference
│   └── abi.json                       # Machine-readable ABI (genvm-lint schema)
├── frontend/                          # Next.js 16 dashboard
│   ├── src/
│   │   ├── app/                       # layout · page · globals.css (theme system)
│   │   ├── components/                # ProtocolStats · AccountOverview · Stake/Compound/Withdraw
│   │   │                              # AboutProtocol · WalletConnect · ThemeToggle · SocialLinks · ui
│   │   ├── context/                   # ThemeContext · WalletContext · VaultDataContext
│   │   ├── hooks/                     # useTxAction
│   │   ├── lib/                       # config · format · genlayer/{client,contract,types}
│   │   └── abi/abi.json               # ABI consumed by the UI
│   └── .env.local.example
├── requirements.txt                   # Contract tooling (Python 3.10–3.12)
└── README.md
```

## How it works

1. **Stake** — deposit tokens; the contract records principal and starts the accrual clock.
2. **Accrue** — yield grows every second using `principal × apy_bps × elapsed ÷ (10000 × seconds_per_year)`, evaluated against the consensus block timestamp.
3. **Compound** — fold pending yield into principal (by the owner, or permissionlessly by anyone via `compound_for`); future yield is then earned on the larger base.
4. **Withdraw** — take out principal + compounded rewards, partially or in full. Withdrawals stay enabled even if the vault is paused, so funds are never trapped.

All money is **atto-scale `u256`** (`value × 10¹⁸`) with exact integer math — no
floats, no cross-validator drift. APY is expressed in **basis points**
(`1000` = `10%`).

## Getting started

### Prerequisites

- **Python 3.10–3.12** for the contract toolchain (the GenLayer test harness does not yet support 3.13+).
- **Node.js 18+** and npm for the frontend.

### 1. Smart contract

```bash
# From the repository root
pip install -r requirements.txt

# Lint + validate the contract (run after every change)
genvm-lint check contracts/smart_staking_optimizer.py

# Run the fast direct-mode tests
pytest tests/direct/ -v

# Refresh the ABI consumed by the frontend
genvm-lint schema contracts/smart_staking_optimizer.py --output docs/abi.json
```

### 2. Frontend

```bash
cd frontend
npm install

# Configure the deployed contract + network
cp .env.local.example .env.local
#   NEXT_PUBLIC_CONTRACT_ADDRESS=0x43050A476485547450Aa80A4Bf059D17CE17CC28
#   NEXT_PUBLIC_GENLAYER_CHAIN=studionet   # studionet | localnet | testnetAsimov | testnetBradbury

npm run dev      # http://localhost:3000
```

Other frontend scripts: `npm run build`, `npm run start`, `npm run typecheck`.

## Frontend features

- 🌗 **Dark / light theme** with a Sun/Moon toggle, persisted and flash-free on load.
- 🧊 **Premium 3D / cyberpunk aesthetic** — glassmorphism cards, progressive
  gradients, layered shadows, and micro-interactions (hover/scale) on every control.
- 🔌 **Wallet connection** via injected EIP-1193 provider with live account/network sync.
- ⚡ **Real-time state** — protocol stats and account position share one data
  context, so a stake/compound/withdraw refreshes every view at once; pending
  yield ticks live.
- 📖 **Protocol explainer** describing keeperless, real-time geometric yield.

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — contract design, storage model, yield math, and the full public ABI.
- [`frontend/README.md`](frontend/README.md) — frontend structure and integration details.

## Links

- **GitHub:** https://github.com/moltaphet/GenVault
- **X (Twitter):** https://x.com/0xehs4hn

---

<div align="center">
<sub>GenVault · powered by the SmartStakingOptimizer Intelligent Contract on GenLayer</sub>
</div>
