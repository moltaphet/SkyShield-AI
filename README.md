<div align="center">

# ✈️ SkyShield AI

### Autonomous Parametric Flight Insurance on GenLayer

**Buy a policy → fly → get paid automatically.** A trust-minimized travel-insurance
protocol that prices premiums and settles delay claims entirely inside consensus —
with **no external oracle, keeper, or claims adjuster** in the loop.

[![GitHub](https://img.shields.io/badge/GitHub-moltaphet%2FSkyShield--AI-181717?logo=github)](https://github.com/moltaphet/SkyShield-AI)
[![X](https://img.shields.io/badge/X-@0xehs4hn-000000?logo=x)](https://x.com/0xehs4hn)
[![GenLayer](https://img.shields.io/badge/Built%20on-GenLayer-34d399)](https://genlayer.com)

</div>

---

## Overview

SkyShield AI is a **parametric flight-delay insurance protocol** built as a GenLayer
Intelligent Contract. Passengers buy a policy for a specific flight; if that flight is
delayed or cancelled, the contract pays out automatically based on the severity of the
delay — no claim forms, no manual review, no centralized oracle feed.

It does this by using GenLayer's two native superpowers **directly inside consensus**:

- **Native internet connectivity** (`gl.nondet.web`) — every validator independently
  re-fetches live flight status from an aviation API.
- **LLM-driven reasoning** (`gl.nondet.exec_prompt`) — the model (a) prices premiums
  from delay/weather risk and (b) parses noisy, free-form flight-status text into a
  structured payout decision.

Because each validator re-runs both steps, the **derived payout tier** — not the raw,
noisy API payload — is the consensus-critical value. All economic state is settled with
exact integer math in *atto* scale (`value × 10¹⁸`), so there is no floating-point drift
between validators.

- **Contract:** `SkyShieldAI` ([`contracts/sky_shield_ai.py`](contracts/sky_shield_ai.py))
- **Address:** `0x91dCD64Fa828b5003688de07C6DCf052cF75E931`
- **Network:** GenLayer `studionet`

---

## Key Features

| Feature | What it does |
|---------|--------------|
| 🧠 **AI risk pricing** | An LLM scores delay/weather risk for the specific flight and prices the premium from fair odds plus a protocol margin — no hardcoded rate table. |
| 🌐 **Live flight data** | Validators read real flight status from an aviation API via `gl.nondet.web`, with consensus reached on the *derived decision*, not the raw bytes. |
| 🎚️ **Multi-tier payouts** | Delay severity maps to graduated payouts (20% / 50% / 100%) instead of a single all-or-nothing trigger. |
| 🏦 **LP underwriting vault** | A share-based liquidity pool lets anyone underwrite policies; LPs earn the premiums of flights that land on time. |

---

## How It Works

```
   LPs                Passenger              Anyone / settlement
    │                     │                          │
    │ provide_liquidity   │                          │
    ▼                     │                          │
 ┌──────────────┐         │ purchase_policy          │
 │ Underwriting │◄────────┤ (LLM prices premium,     │
 │    Vault     │ premium │  coverage reserved)      │
 └──────────────┘ escrow  │                          │
    ▲                     │   after departure  ──────┤ check_flight_and_execute
    │ on-time premium     │                          │ (re-fetch status → payout tier)
    │ becomes LP yield    ▼                          ▼
    └──────────  delayed → payout credited to passenger.claimable → claim()
```

1. **Underwrite.** Liquidity providers deposit GEN with `provide_liquidity` and receive
   pro-rata vault shares.
2. **Buy a policy.** A passenger calls `purchase_policy(flight_code, departure_timestamp)`.
   An LLM assesses risk and prices the premium; the premium is escrowed into the vault and
   the full `max_payout` is **reserved** so the protocol can never sell coverage it cannot pay.
3. **Settle (permissionless).** After departure, anyone calls `check_flight_and_execute`.
   Validators re-fetch live flight status and independently map it to a payout tier; the
   equivalence principle requires agreement on the *tier*, not the raw payload.
4. **Outcome.**
   - **On time** → payout `0`, policy `EXPIRED`, the whole premium becomes LP yield.
   - **Delayed / cancelled** → tiered payout credited to the passenger's `claimable` ledger.
5. **Withdraw.** Passengers (and LPs) pull funds with `claim()`.

### Payout tiers

| Delay | Payout |
|-------|--------|
| 60–120 min | **20%** of coverage |
| 120–240 min | **50%** of coverage |
| > 240 min **or cancelled** | **100%** of coverage |

Base coverage is **1,000 GEN per policy**; premiums are priced from fair odds plus a 30%
protocol loading, with a 1 GEN floor. A **solvency invariant** (`total_assets ≥ locked_coverage`)
is preserved on every state transition, so reserved coverage can never be drained by LP withdrawals.

---

## Contract Methods

`SkyShieldAI` — 16 public methods (9 write, 7 view).

### Write

| Method | Description |
|--------|-------------|
| `provide_liquidity(amount)` | Deposit GEN into the underwriting vault; mints pro-rata LP shares. |
| `withdraw_liquidity(shares)` | Burn LP shares and credit redeemed GEN to your claimable balance (cannot touch reserved coverage). |
| `purchase_policy(flight_code, departure_timestamp)` | Buy a policy; an LLM prices the premium from live risk, escrows it, and reserves the max payout. |
| `check_flight_and_execute(policy_id)` | Permissionless settlement: re-fetch live flight status and resolve the policy to a payout tier via consensus. |
| `claim()` | Withdraw your accumulated claimable balance (payouts + LP redemptions). |
| `admin_open_policy(passenger, flight_code, departure_timestamp, risk_bps)` | Owner fallback: open a policy with an explicit risk score (no LLM call). |
| `admin_resolve_policy(policy_id, delay_minutes, cancelled)` | Owner fallback: resolve a policy deterministically without the web/LLM path. |
| `set_paused(value)` | Owner switch; blocks new deposits/policies but always allows exits. |
| `transfer_ownership(new_owner)` | Transfer contract ownership. |

### View

| Method | Description |
|--------|-------------|
| `preview_premium(risk_bps)` | Quote the premium for a given risk score. |
| `quote_payout(delay_minutes, cancelled)` | Quote the payout for a delay/cancellation outcome. |
| `get_policy(policy_id)` | Full policy record (passenger, flight, status, premium, payout). |
| `claimable_of(account)` | Withdrawable balance for an account. |
| `lp_position(account)` | LP shares and their current GEN value for an account. |
| `share_price_atto()` | Current LP share price in atto scale. |
| `get_pool_stats()` | Vault totals: assets, shares, locked coverage, available liquidity. |

---

## Tech Stack

- **Smart contract:** GenLayer Intelligent Contract (GenVM), Python SDK [`py-genlayer`](https://docs.genlayer.com)
- **Non-determinism in consensus:** `gl.nondet.web` (live aviation API) + `gl.nondet.exec_prompt` (LLM), reconciled with custom validator **equivalence-principle** functions that compare derived decisions, not raw bytes
- **Math:** exact integer / *atto* (`10¹⁸`) accounting — no floating point
- **Frontend:** Next.js + TypeScript with the [`genlayer-js`](https://docs.genlayer.com) client
- **Testing:** [`genlayer-test`](https://docs.genlayer.com) (direct mode, in-memory) + `pytest`; lint/validate via `genvm-lint`

---

## Quickstart

### 1. Contract

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Lint + validate the contract
genvm-lint check contracts/sky_shield_ai.py

# Run fast in-memory tests
pytest tests/direct/ -v
```

### 2. Frontend

```bash
cd frontend
npm install

# Configure the deployed contract + network
cp .env.local.example .env.local
#   NEXT_PUBLIC_CONTRACT_ADDRESS=0x91dCD64Fa828b5003688de07C6DCf052cF75E931
#   NEXT_PUBLIC_GENLAYER_CHAIN=studionet

npm run dev
```

---

## Safety & Determinism

- **Re-entrancy guard** plus strict checks-effects-interactions ordering on every value-out
  path (`withdraw_liquidity`, `claim`).
- **Solvency invariant** `total_assets ≥ locked_coverage` enforced on every transition.
- **Duplicate-policy protection** — a passenger cannot hold two ACTIVE policies for the same
  flight + departure.
- **Consensus time** comes only from the agreed block time, never a wall-clock read.

---

<div align="center">

Built on [GenLayer](https://genlayer.com) · [@0xehs4hn](https://x.com/0xehs4hn)

</div>
