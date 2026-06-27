# GenVault — Submission Summary

**Intelligent Staking & Yield Optimizer on GenLayer**

> Stake once. Yield accrues from the consensus block clock and compounds geometrically — fully on-chain, with zero external keepers, bots, or oracles.

- **Live contract:** `SmartStakingOptimizer` @ `0x91dCD64Fa828b5003688de07C6DCf052cF75E931`
- **Network:** GenLayer (studionet)
- **Live demo:** `<VERCEL_URL_PLACEHOLDER>`
- **Repository:** `https://github.com/moltaphet/GenVault`

---

## 1. Project Overview

GenVault is an **Intelligent Staking & Yield Optimizer** — a non-custodial vault
that turns a single deposit into a continuously optimized, self-compounding
position.

Users stake tokens into the `SmartStakingOptimizer` Intelligent Contract. From
that moment, yield accrues every second against a configurable APR/APY, and can
be folded back into principal on demand. Because each compound raises the base
that the next interval is measured against, returns grow **geometrically rather
than linearly** — the core efficiency advantage of the protocol.

Every position is tracked with full precision and transparency on-chain:

- **Principal** — current staked balance, including previously compounded yield.
- **Pending yield** — accrued-but-not-yet-compounded rewards, readable live.
- **Total balance** — principal + pending yield, i.e. the amount withdrawable now.
- **Lifetime stats** — total deposited, total compounded, total withdrawn.

All monetary values use **atto-scale `u256`** (`value × 10^18`) with exact integer
arithmetic — no floating point, no rounding drift across validators. APY is
expressed in **basis points** (`1000 bps = 10%`).

---

## 2. How It Uses Intelligent Contracts

GenVault is built specifically around capabilities that a traditional EVM smart
contract cannot offer cleanly. The compounding engine lives **entirely inside
GenLayer consensus**.

### Deterministic on-chain time → keeperless geometric compounding

Yield is a function of elapsed time:

```
pending = principal × apy_bps × elapsed_seconds
          ----------------------------------------
              BPS_DENOMINATOR × SECONDS_PER_YEAR
```

The contract reads `elapsed_seconds` from the **deterministic consensus block
timestamp** that the GenLayer leader proposes and every validator agrees on
(`datetime.datetime.now()` inside the GenVM is the sanctioned, reproducible time
source — wall-clock reads like `time.time()` are forbidden). This is the key
unlock: **the moment any user touches the vault, accrued yield is recomputed and
settled on-chain, exactly and identically across all validators.**

That design **completely removes the need for external keepers**:

- **No off-chain bot** polling and submitting `harvest()` transactions.
- **No cron scheduler** or serverless function to keep balances current.
- **No price/time oracle** feeding timestamps in from outside.

Balances are always correct because the math runs *within* the consensus that
finalizes the transaction. Compounding can be triggered by the staker
(`compound_rewards`) or **permissionlessly by anyone** (`compound_for`) — enabling
optional community/automation actors without ever granting them custody, since
the deterministic math can only ever benefit the position owner.

### Consensus-validated state transitions

Every write — stake, compound, withdraw — is re-executed and agreed upon under
GenLayer's Optimistic Democracy before it becomes state. The contract is fully
deterministic (no LLM or web calls), so all business errors are classified as
`[EXPECTED]` and must match exactly across validators, guaranteeing consensus on
both success and failure paths.

### Safety and invariants

- Every state-changing entry point **settles pending yield first**, so withdrawals
  always act on the freshest balance and the accounting invariant stays simple.
- **Withdrawals remain enabled even when the vault is paused** — funds can never
  be trapped.
- Storage uses GenLayer-native types only (`TreeMap`, `u256`, `Address`), with an
  append-only `StakeAccount` layout for safe upgradability.

### Contract surface

`16` methods — `8` write (`stake`, `compound_rewards`, `compound_for`, `withdraw`,
`withdraw_max`, `set_apy`, `set_paused`, `transfer_ownership`) and `8` view
(`get_account`, `get_stats`, `preview_pending`, `balance_of`, `total_balance_of`,
`get_apy`, `is_paused`, `get_owner`).

**Quality gates:** `genvm-lint` AST safety + SDK semantic validation pass with
zero warnings; **13/13 direct-mode tests** green (covering geometric yield,
exponential compounding, permissionless compounding, partial/max withdrawals, and
owner/pause access controls).

---

## 3. Tech Stack & Features

### Stack

| Layer | Technology |
|---|---|
| **Intelligent Contract** | Python · GenLayer GenVM · `genvm-linter` · `genlayer-test` |
| **Frontend** | **Next.js 16** (App Router, React Server Components) · React 19 · TypeScript 5 |
| **Styling** | **Tailwind CSS v4** (CSS-first config, semantic theme tokens) |
| **Web3 client** | **`genlayer-js`** · EIP-1193 injected wallet (MetaMask) |
| **Icons** | `lucide-react` + brand-accurate inline SVGs |

### Frontend integration

- **Reads** via `client.readContract({ address, functionName, args })` — gas-free
  views feed the protocol dashboard and live position card.
- **Writes** via `client.writeContract(...)` followed by
  `waitForTransactionReceipt({ status: TransactionStatus.ACCEPTED })`.
- The UI is bound to the contract through its **generated ABI** (`genvm-lint
  schema`), and the frontend's ABI copy is verified byte-identical to the
  source-of-truth — every read/write hook targets a real deployed method.
- All units are handled as `bigint` in atto scale, with centralized
  `atto ↔ token` and `bps ↔ %` conversion helpers.

### Premium UI / UX features

- **3D cyberpunk aesthetic** — glassmorphism surfaces (`backdrop-blur` + saturate),
  progressive accent gradients, layered shadows, and ambient radial glows for
  depth.
- **Dark / light theme toggle** — animated Sun/Moon switch, persisted to
  `localStorage`, with a pre-hydration script that applies the saved theme before
  first paint (no flash, no hydration mismatch).
- **Micro-interactions** — hover/active scale transitions on every button and
  input, focus rings, a pulsing live-connection indicator, and smooth color
  transitions across the whole palette.
- **Real-time shared state** — protocol stats and account position live in one
  data context, so any stake/compound/withdraw refreshes every view at once;
  pending yield ticks live via polling.
- **Fully responsive** — fluid grid from mobile to desktop.
- **Robust states** — skeleton loaders, in-flight transaction spinners, explicit
  error banners, wallet-not-connected and contract-not-configured guards.
- **Protocol explainer** — an in-app "About the Protocol" section detailing the
  keeperless, real-time geometric yield model.

---

## 4. Links

- **Live Demo (Vercel):** `<VERCEL_URL_PLACEHOLDER>`
- **GitHub Repository:** [github.com/moltaphet/GenVault](https://github.com/moltaphet/GenVault)
- **Deployed Contract:** `0x91dCD64Fa828b5003688de07C6DCf052cF75E931`

---

<div align="center">
<sub><strong>GenVault</strong> · powered by the SmartStakingOptimizer Intelligent Contract on GenLayer</sub>
</div>
