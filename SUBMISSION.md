# SkyShield AI — Submission Summary

**Autonomous Parametric Flight Insurance on GenLayer**

> Buy a policy, fly, and get paid automatically. Premiums are priced by an on-chain AI from live flight risk, and delay claims settle inside consensus — with zero oracles, keepers, or claims adjusters.

- **Live contract:** `SkyShieldAI` @ `0x91dCD64Fa828b5003688de07C6DCf052cF75E931`
- **Network:** GenLayer (studionet)
- **Live demo:** `<VERCEL_URL_PLACEHOLDER>`
- **Repository:** `https://github.com/moltaphet/SkyShield-AI`

---

## 1. Project Overview

SkyShield AI is a **parametric flight-delay insurance protocol** — a non-custodial
underwriting vault that turns a single premium into automatic, severity-based
coverage for a specific flight.

A passenger buys a policy for a flight via the `SkyShieldAI` Intelligent Contract.
An on-chain AI prices the premium from the flight's delay/weather risk, the premium
is escrowed into a shared liquidity pool, and the full coverage is reserved. After
departure, anyone can trigger settlement: the contract reads the live flight status
and pays out a graduated amount based on how late the flight actually was. There are
**no claim forms, no manual review, and no centralized oracle feed**.

Every position is tracked on-chain with full precision:

- **Policy** — passenger, flight, status, premium paid, reserved coverage, and any payout.
- **Liquidity pool** — a share-based underwriting vault (`total_assets` / `total_shares`)
  that backs policies and earns the premiums of flights that land on time.
- **Claim ledger** — a pull-payment balance for passengers (payouts) and exiting LPs.
- **Lifetime stats** — premiums collected, payouts made, and yield routed to LPs.

All monetary values use **atto-scale `u256`** (`value × 10^18`) with exact integer
arithmetic — no floating point, no rounding drift across validators. Risk and payout
shares are expressed in **basis points** (`10000 bps = 100%`).

---

## 2. How It Uses Intelligent Contracts

SkyShield is built specifically around capabilities a traditional EVM smart contract
cannot offer. The pricing and claims engine lives **entirely inside GenLayer
consensus**, using both of the protocol's native superpowers.

### Native internet access → live flight data, no oracle

To settle a policy, the contract calls `gl.nondet.web` to fetch the flight's real
status directly from an aviation API. **Every validator independently re-fetches**
the data, so there is no single trusted oracle, no relayer, and no off-chain keeper
feeding results in. The settlement entry point (`check_flight_and_execute`) is
**permissionless** — anyone can trigger it after departure.

### LLM reasoning → AI premium pricing & robust parsing

The contract calls `gl.nondet.exec_prompt` to (a) score the flight's delay/weather
risk and price the premium from fair odds plus a protocol margin, and (b) parse
messy, free-form flight-status text into a structured, deterministic outcome.

### Equivalence principle → consensus on the *decision*, not the bytes

Raw web payloads and LLM text are noisy and will never be byte-identical across
validators. SkyShield wraps both non-deterministic steps in **custom validator
equivalence functions** that compare the *derived decision* — the risk band and the
payout tier — rather than the raw response. Validators agree on what matters
(the money), following GenLayer's equivalence-principle guidance. Time comes only
from the **deterministic consensus block clock** (`datetime.datetime.now()` inside
the GenVM), never a wall-clock read.

### Safety and invariants

- **Solvency invariant:** `total_assets >= locked_coverage` is preserved on every
  state transition, so reserved coverage can never be drained by LP withdrawals.
- **Re-entrancy guard** plus strict checks-effects-interactions ordering on every
  value-out path (`withdraw_liquidity`, `claim`).
- **Duplicate-policy protection:** a passenger cannot hold two ACTIVE policies for
  the same flight + departure.
- **Withdrawals/exits stay enabled even when paused** — funds can never be trapped.
- Deterministic fallbacks: owner-only `admin_open_policy` / `admin_resolve_policy`
  resolve a policy without the web/LLM path if needed.

### Contract surface

`16` methods — `9` write (`provide_liquidity`, `withdraw_liquidity`,
`purchase_policy`, `check_flight_and_execute`, `claim`, `admin_open_policy`,
`admin_resolve_policy`, `set_paused`, `transfer_ownership`) and `7` view
(`preview_premium`, `quote_payout`, `get_policy`, `claimable_of`, `lp_position`,
`share_price_atto`, `get_pool_stats`).

**Quality gates:** `genvm-lint` AST safety + SDK semantic validation pass with zero
warnings; **26/26 direct-mode tests** green; **9/9 integration tests** pass against
the live `studionet` deployment under full leader + validator consensus (LP flows,
policy lifecycle, all payout tiers, duplicate rejection, solvency, and live on-chain
reads).

---

## 3. Tech Stack & Features

### Stack

| Layer | Technology |
|---|---|
| **Intelligent Contract** | Python · GenLayer GenVM · `genvm-linter` · `genlayer-test` |
| **Non-determinism** | `gl.nondet.web` (aviation API) · `gl.nondet.exec_prompt` (LLM) · custom equivalence |
| **Frontend** | **Next.js 16** (App Router, RSC) · React 19 · TypeScript 5 |
| **Styling** | **Tailwind CSS v4** + a custom "Dark Aviation / Cyberpunk Sky" theme |
| **Web3 client** | **`genlayer-js`** · EIP-1193 injected wallet (MetaMask) |

### Frontend integration

- **Reads** via `client.readContract({ address, functionName, args })` — gas-free
  views feed the dashboard (pool stats, premium preview, policy board, claim balance).
- **Writes** via `client.writeContract(...)` followed by
  `waitForTransactionReceipt({ status: TransactionStatus.ACCEPTED })`.
- The UI is bound through the **generated ABI** (`genvm-lint schema`); the client-side
  premium preview reproduces the on-chain pricing math exactly for instant quotes.
- All units are handled as `bigint` in atto scale, with centralized `atto ↔ token`
  and `bps ↔ %` helpers.

### UI / UX features

- **Dark Aviation / Cyberpunk Sky theme** — deep-navy backdrop with an animated
  starfield and drifting clouds, glassmorphism cards with neon blue/amber borders,
  a sweeping radar indicator, Orbitron headings + Inter body, and neon glow effects.
- **Hero** with live pool stats, **How It Works** (Buy → AI Prices → Monitored → Payout),
  **Buy Policy** with a live AI risk gauge and premium preview, **My Policies** boarding
  board with live status badges, and a **Claim** settlement panel.
- **Real-time shared state** — an autonomous resolver advances boarding passes from
  monitoring → checking → resolved, and any action refreshes every view at once.
- **Fully responsive**, with wallet-not-connected and transaction-lifecycle states.

---

## 4. Links

- **Live Demo (Vercel):** `<VERCEL_URL_PLACEHOLDER>`
- **GitHub Repository:** [github.com/moltaphet/SkyShield-AI](https://github.com/moltaphet/SkyShield-AI)
- **Deployed Contract:** `0x91dCD64Fa828b5003688de07C6DCf052cF75E931`

---

<div align="center">
<sub><strong>SkyShield AI</strong> · autonomous parametric flight insurance on GenLayer</sub>
</div>
