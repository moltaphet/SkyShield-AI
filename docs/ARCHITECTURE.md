# SkyShield AI — Contract Architecture

This document describes the `SkyShieldAI` Intelligent Contract and the ABI the
frontend binds to. Pair it with the machine-readable [`abi.json`](abi.json).

## 1. Overview

`SkyShieldAI` is a single-file GenLayer Intelligent Contract
(`contracts/sky_shield_ai.py`) that underwrites parametric flight-delay insurance.
Unlike a deterministic-only contract, it performs **non-deterministic work inside
consensus** and reconciles it with custom equivalence functions.

### Why it is "intelligent"

- It reads **live flight status** from an aviation API via `gl.nondet.web` — every
  validator independently re-fetches, so there is no trusted oracle or keeper.
- It uses `gl.nondet.exec_prompt` (an **LLM**) to price premiums from delay/weather
  risk and to parse noisy flight-status text into a structured payout decision.
- Consensus is reached on the **derived decision** (risk band / payout tier), not
  the raw bytes, via custom **equivalence-principle** validator functions.
- Time comes only from the **consensus block clock** (`datetime.datetime.now()`,
  which the GenVM replaces with the leader-proposed, validator-agreed block time).

## 2. State model

### Contract storage (`gl.Contract` fields)

| Field | Type | Meaning |
|-------|------|---------|
| `owner` | `Address` | Admin (pause, fallback resolution, transfer ownership) |
| `paused` | `bool` | Blocks new policies + LP deposits (never exits) |
| `reentrancy_locked` | `bool` | Re-entrancy guard for value-out paths |
| `total_assets` | `u256` | GEN backing the pool (LP deposits + premiums − payouts), atto |
| `total_shares` | `u256` | Total LP shares minted |
| `locked_coverage` | `u256` | Sum of `max_payout` reserved by ACTIVE policies, atto |
| `lp_shares` | `TreeMap[Address, u256]` | Per-LP share balance |
| `claimable` | `TreeMap[Address, u256]` | Pull-payment ledger (passengers + exiting LPs) |
| `next_policy_id` | `u256` | Monotonic policy id counter |
| `policies` | `TreeMap[u256, Policy]` | All policies by id |
| `active_key_to_policy` | `TreeMap[str, u256]` | Dedup index: passenger+flight+departure → policy id |
| `policy_count` / `lp_count` | `u256` | Lifetime counters |
| `total_premiums_collected` / `total_payouts` / `total_yield_to_lps` | `u256` | Lifetime totals (atto) |

### Per-policy record (`Policy`)

| Field | Type | Meaning |
|-------|------|---------|
| `policy_id` | `u256` | Unique id |
| `passenger` | `Address` | Policy holder |
| `flight_code` | `str` | e.g. `BA245` |
| `departure_timestamp` | `u256` | Scheduled departure, unix seconds |
| `premium_paid` | `u256` | Premium escrowed into the pool (atto) |
| `max_payout` | `u256` | Coverage reserved while ACTIVE (atto) |
| `payout_amount` | `u256` | Actual payout on resolution (atto) |
| `status` | `str` | `ACTIVE` / `RESOLVED` / `EXPIRED` |
| `risk_bps` | `u256` | AI risk score the premium was priced from |
| `delay_minutes` | `u256` | Observed delay at resolution |
| `created_at` / `resolved_at` | `u256` | Consensus timestamps |

## 3. Economic model

All money is **atto-scale** (`value × 10**18`); shares and risk are basis points.

```
ATTO              = 10**18
BPS_DENOMINATOR   = 10_000           # 100.00%
BASE_COVERAGE     = 1_000 * ATTO     # max payout underwritten per policy
LOADING_BPS       = 3_000            # +30% protocol margin over fair odds
MIN_PREMIUM       = 1 * ATTO         # premium floor
MAX_RISK_BPS      = 10_000           # risk probability clamped to [0, 100%]
```

### Premium pricing

```
expected_loss = coverage * risk_bps / BPS_DENOMINATOR
premium       = expected_loss * (BPS_DENOMINATOR + LOADING_BPS) / BPS_DENOMINATOR
premium       = max(premium, MIN_PREMIUM)
```

The `risk_bps` is produced **on-chain by the AI** at purchase; `preview_premium`
exposes the deterministic pricing for any given score.

### Payout tiers

| Delay | Payout (bps of coverage) |
|-------|--------------------------|
| 60–120 min | 2_000 (20%) |
| 120–240 min | 5_000 (50%) |
| > 240 min **or cancelled** | 10_000 (100%) |
| < 60 min (on time) | 0 → policy `EXPIRED`, premium becomes LP yield |

### Money flow & invariant

On purchase, `premium` is added to `total_assets` and `max_payout` is added to
`locked_coverage`. On resolution, the granular payout is credited to the
passenger's `claimable` ledger and the reservation is released. The protocol
**always preserves `total_assets >= locked_coverage`**, so it can never sell
coverage it cannot pay, and LPs can only ever withdraw un-reserved liquidity.

## 4. Public ABI

Money arguments/returns are **atto-scale**. Addresses are 0x-prefixed hex strings.

### Constructor

No parameters. The deployer becomes `owner` and the pool starts empty.

### Write methods

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| `provide_liquidity` | `amount: int` | `int` | Deposit GEN into the vault; mints pro-rata LP shares. |
| `withdraw_liquidity` | `shares: int` | `int` | Burn shares; credits redeemed GEN to `claimable`. Cannot touch reserved coverage. |
| `purchase_policy` | `flight_code: str, departure_timestamp: int` | `int` | AI prices premium, escrows it, reserves coverage; returns policy id. |
| `check_flight_and_execute` | `policy_id: int` | `dict` | Permissionless: re-fetch live status and resolve to a payout tier. |
| `claim` | — | `int` | Withdraw the caller's `claimable` balance. |
| `admin_open_policy` | `passenger: str, flight_code: str, departure_timestamp: int, risk_bps: int` | `int` | Owner fallback: open with an explicit risk score (no LLM). |
| `admin_resolve_policy` | `policy_id: int, delay_minutes: int, cancelled: bool` | `dict` | Owner fallback: resolve deterministically (no web/LLM). |
| `set_paused` | `value: bool` | — | Owner only. Exits stay enabled while paused. |
| `transfer_ownership` | `new_owner: str` | — | Owner only. |

### View methods (gas-free reads)

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| `preview_premium` | `risk_bps: int` | `int` | Premium for a given risk score. |
| `quote_payout` | `delay_minutes: int, cancelled: bool` | `int` | Payout for a delay/cancellation outcome. |
| `get_policy` | `policy_id: int` | `dict` | Full policy record. |
| `claimable_of` | `account: str` | `int` | Withdrawable balance. |
| `lp_position` | `account: str` | `dict` | LP shares + redeemable/available GEN value. |
| `share_price_atto` | — | `int` | Current LP share price (atto). |
| `get_pool_stats` | — | `dict` | `total_assets`, `total_shares`, `locked_coverage`, `available_liquidity`, counts, lifetime totals, `paused`, `owner`. |

## 5. Errors & non-determinism classification

Deterministic business errors are prefixed `[EXPECTED]` and must match exactly
across validators (e.g. `[EXPECTED] deposit amount must be positive`,
`[EXPECTED] insufficient pool liquidity`, `[EXPECTED] caller is not the owner`).

Non-deterministic failures from the web/LLM path are classified so validators can
agree on the *kind* of failure rather than exact text:

- `[EXTERNAL]` — upstream/API error
- `[TRANSIENT]` — network / 5xx (agree if both transient)
- `[LLM_ERROR]` — model output unusable

## 6. Frontend integration

The UI uses `genlayer-js`:

1. **Read** pool/policy state with the view methods (no transaction, instant):
   `get_pool_stats`, `get_policy`, `lp_position`, `claimable_of`, `preview_premium`,
   `quote_payout`, `share_price_atto`.
2. **Write** via `provide_liquidity`, `purchase_policy`, `check_flight_and_execute`,
   `claim`, `withdraw_liquidity` — submit a transaction and wait for acceptance.
3. **Display scaling:** divide atto values by `10**18` for human units; render
   basis points as `bps / 100` percent.
4. The client mirrors the deterministic pricing math for an instant premium preview;
   the authoritative `risk_bps` is always produced on-chain at purchase.
