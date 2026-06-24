# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
GenVault — SmartStakingOptimizer
================================

An Intelligent Staking & Yield Optimizer contract for the GenLayer protocol.

The contract lets accounts stake tokens, tracks each account's principal and
the yield it accrues over time, and re-stakes (compounds) that yield back into
the principal on demand. All time-dependent math is driven by the deterministic
consensus clock that the GenVM exposes through ``datetime.datetime.now()`` (the
block time the leader proposes and every validator agrees on) so all validators
compute identical results — there is no wall-clock read and no reliance on a
client-supplied timestamp.

Design notes
------------
* Money is stored in *atto* scale (value * 10**18) using ``u256``. This is the
  cross-chain convention and keeps every arithmetic operation exact integer
  math — no floats, no rounding drift between validators.
* Yield accrues linearly at a configurable APR/APY expressed in basis points
  (``apy_bps``; 100 bps = 1%). Pending yield for an account is:

      pending = principal * apy_bps * elapsed_seconds
                ----------------------------------------
                   BPS_DENOMINATOR * SECONDS_PER_YEAR

* Compounding folds the pending yield into the principal and resets the
  accrual clock, so future yield is earned on principal + previously
  compounded rewards (true compounding).
* Every state-changing entry point settles pending yield *before* mutating the
  balance, which keeps the accounting invariant simple and exploit-resistant.
"""

import datetime
import json
from dataclasses import dataclass

from genlayer import *


# --------------------------------------------------------------------------- #
# Error classification prefixes (GenLayer standard).                          #
#   EXPECTED  - deterministic business logic; validators must match exactly.  #
#   EXTERNAL  - external API 4xx; deterministic; must match exactly.          #
#   TRANSIENT - network / 5xx; non-deterministic; agree if both transient.    #
#   LLM_ERROR - model misbehaviour; always disagree to force validator rotation.
# The core accounting stays deterministic, but two entry points now reach into#
# GenLayer consensus for non-deterministic data (an LLM risk screen on        #
# ``stake`` and a live-APY web feed in ``update_apy_from_market``).           #
# --------------------------------------------------------------------------- #
ERROR_EXPECTED = "[EXPECTED]"
ERROR_EXTERNAL = "[EXTERNAL]"
ERROR_TRANSIENT = "[TRANSIENT]"
ERROR_LLM = "[LLM_ERROR]"

# --------------------------------------------------------------------------- #
# Economic constants.                                                         #
# --------------------------------------------------------------------------- #
SECONDS_PER_YEAR: u256 = 31_536_000      # 365 * 24 * 60 * 60
BPS_DENOMINATOR: u256 = 10_000           # 100.00% expressed in basis points
MAX_APY_BPS: u256 = 1_000_000            # safety ceiling: 10,000% APY
MAX_RISK_BPS: int = 10_000               # risk probability is bounded to [0, 100%]

# Risk band thresholds (basis points) used to reach validator agreement on a
# noisy LLM risk score. Two validators rarely produce an identical ``risk_bps``,
# so consensus is checked at band granularity, never on the exact number.
RISK_BAND_MODERATE: int = 1_500          # >= 15%  -> band 1
RISK_BAND_HIGH: int = 4_000              # >= 40%  -> band 2
RISK_BAND_EXTREME: int = 7_000           # >= 70%  -> band 3 (stake rejected)

# Live yield data source. DeFiLlama's public yields API exposes a per-pool
# history; the last sample carries the current APY (as a percentage float).
# The default pool is Lido stETH staking; the owner can repoint it on-chain.
DEFILLAMA_DEFAULT_POOL: str = "747c1d2a-c668-4682-b9f9-296708a3dd90"
DEFILLAMA_CHART_BASE: str = "https://yields.llama.fi/chart"

# Agreement tolerance for the live-APY feed: validators fetch independently and
# may see the feed tick between reads, so they agree when their derived APY is
# within 50 bps (0.50%) absolute or 10% relative of the leader's.
APY_ABS_TOLERANCE_BPS: int = 50
APY_REL_TOLERANCE: float = 0.10


# --------------------------------------------------------------------------- #
# Pure, deterministic helpers for the non-deterministic paths.                #
#                                                                             #
# They take/return plain ints so leader and validator code reuse identical    #
# logic (which keeps the derived decision reproducible) and so they can be    #
# unit-tested directly without a VM.                                          #
# --------------------------------------------------------------------------- #
def _coerce_int(raw: object) -> int:
    """Best-effort coercion of an LLM/JSON value into an int.

    Handles int, float, and strings like ``"180"`` / ``"180.0"``. Raises an
    LLM-classified error on anything non-numeric so the validator can force a
    rotation instead of committing garbage.
    """
    try:
        return int(round(float(str(raw).strip())))
    except (ValueError, TypeError):
        raise gl.vm.UserError(f"{ERROR_LLM} non-numeric value from model: {raw!r}")


def parse_risk_bps(analysis: dict) -> int:
    """Extract a bounded risk probability (bps) from an LLM risk assessment."""
    if not isinstance(analysis, dict):
        raise gl.vm.UserError(f"{ERROR_LLM} risk response is not a dict: {type(analysis)}")
    raw = analysis.get("risk_bps")
    if raw is None:
        for alt in ("risk", "probability_bps", "score"):
            if alt in analysis:
                raw = analysis[alt]
                break
    if raw is None:
        raise gl.vm.UserError(
            f"{ERROR_LLM} missing 'risk_bps'. keys={list(analysis.keys())}"
        )
    return max(0, min(_coerce_int(raw), MAX_RISK_BPS))


def risk_band(risk_bps: int) -> int:
    """Bucket a risk score into a coarse band for validator agreement.

    0: low (< 15%)   1: moderate (15-40%)   2: high (40-70%)   3: extreme (>= 70%)
    """
    if risk_bps < RISK_BAND_MODERATE:
        return 0
    if risk_bps < RISK_BAND_HIGH:
        return 1
    if risk_bps < RISK_BAND_EXTREME:
        return 2
    return 3


def parse_market_apy_bps(payload: dict) -> int:
    """Derive the current APY (basis points) from a DeFiLlama chart payload.

    The payload shape is ``{"status": "success", "data": [{..., "apy": <pct>}]}``
    ordered oldest-to-newest; the last sample is the live APY expressed as a
    percentage (e.g. ``3.15`` == 3.15%). It is converted to basis points and
    clamped to the contract's safety ceiling so a bad feed can never set an
    absurd rate.
    """
    if not isinstance(payload, dict):
        raise gl.vm.UserError(f"{ERROR_EXTERNAL} feed payload is not a JSON object")
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        raise gl.vm.UserError(f"{ERROR_EXTERNAL} feed payload has no 'data' samples")
    latest = data[-1]
    if not isinstance(latest, dict) or "apy" not in latest:
        raise gl.vm.UserError(f"{ERROR_EXTERNAL} latest sample is missing 'apy'")
    apy_bps = _coerce_int(round(float(latest["apy"]) * 100))
    return max(0, min(apy_bps, int(MAX_APY_BPS)))


def apy_in_consensus(leader_bps: int, mine_bps: int) -> bool:
    """Whether a validator's independently fetched APY agrees with the leader's.

    Agreement is granted within an absolute (50 bps) or relative (10%) band so
    a feed that ticks between independent reads does not break consensus.
    """
    hi = max(leader_bps, mine_bps)
    lo = min(leader_bps, mine_bps)
    if hi - lo <= APY_ABS_TOLERANCE_BPS:
        return True
    if lo <= 0:
        return False
    return (hi / lo) <= (1.0 + APY_REL_TOLERANCE)


@allow_storage
@dataclass
class StakeAccount:
    """Per-account staking position persisted on-chain.

    Fields are append-only: never reorder or insert, only append at the end,
    to preserve storage layout for upgradable deployments.
    """

    principal: u256          # current staked principal in atto scale (includes compounded yield)
    last_accrual_ts: u256    # unix seconds of the last settle/compound for this account
    total_compounded: u256   # lifetime yield folded into principal (statistics)
    total_deposited: u256    # lifetime principal deposited via stake() (statistics)
    total_withdrawn: u256    # lifetime amount withdrawn (statistics)
    exists: bool             # True once the account has ever staked


class SmartStakingOptimizer(gl.Contract):
    # ----- Storage fields (class-level annotations = storage slots) -------- #
    owner: Address
    apy_bps: u256                          # annual yield rate in basis points
    total_staked: u256                     # sum of every account's principal
    staker_count: u256                     # number of accounts that have ever staked
    paused: bool                           # emergency switch for deposits/compounding
    accounts: TreeMap[Address, StakeAccount]

    # --------------------------------------------------------------------- #
    # Lifecycle                                                             #
    # --------------------------------------------------------------------- #
    def __init__(self, initial_apy_bps: int) -> None:
        if initial_apy_bps < 0 or initial_apy_bps > MAX_APY_BPS:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} initial_apy_bps out of range")
        self.owner = gl.message.sender_address
        self.apy_bps = u256(initial_apy_bps)
        self.total_staked = u256(0)
        self.staker_count = u256(0)
        self.paused = False

    # --------------------------------------------------------------------- #
    # Internal helpers                                                      #
    # --------------------------------------------------------------------- #
    def _now_ts(self) -> u256:
        """Deterministic consensus timestamp (unix seconds).

        Inside the GenVM, ``datetime.datetime.now()`` is replaced with the
        block/consensus time proposed by the leader and agreed by every
        validator — it is NOT a wall-clock read, so it is safe to use directly
        in state-changing math. ``time.time()`` and friends are forbidden; this
        is the sanctioned time source.
        """
        return u256(int(datetime.datetime.now(datetime.timezone.utc).timestamp()))

    def _pending_yield(self, acct: StakeAccount, now_ts: u256) -> u256:
        """Linear yield accrued by ``acct`` between its last accrual and now."""
        if acct.principal == 0 or now_ts <= acct.last_accrual_ts:
            return u256(0)
        elapsed = now_ts - acct.last_accrual_ts
        numerator = acct.principal * self.apy_bps * elapsed
        return u256(numerator // (BPS_DENOMINATOR * SECONDS_PER_YEAR))

    def _settle(self, staker: Address, now_ts: u256) -> u256:
        """Fold any pending yield into principal and advance the clock.

        Returns the amount that was compounded. Safe to call on accounts that
        do not exist yet (no-op).
        """
        if staker not in self.accounts:
            return u256(0)
        acct = self.accounts[staker]
        pending = self._pending_yield(acct, now_ts)
        if pending > 0:
            acct.principal = u256(acct.principal + pending)
            acct.total_compounded = u256(acct.total_compounded + pending)
            self.total_staked = u256(self.total_staked + pending)
        acct.last_accrual_ts = now_ts
        return pending

    def _require_owner(self) -> None:
        if gl.message.sender_address != self.owner:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} caller is not the owner")

    def _require_active(self) -> None:
        if self.paused:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} contract is paused")

    # --------------------------------------------------------------------- #
    # 1. Staking logic                                                      #
    # --------------------------------------------------------------------- #
    @gl.public.write
    def stake(self, amount: int) -> None:
        """Stake ``amount`` (atto scale) for the caller.

        Any pending yield is compounded first so the new deposit and existing
        principal share a single, clean accrual clock.
        """
        self._require_active()
        if amount <= 0:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} stake amount must be positive")

        staker = gl.message.sender_address

        # Consensus-backed AI safety screen: every validator independently asks
        # the model whether this deposit, at the current advertised APY, looks
        # like an abnormal / exploit-shaped position. They agree on the derived
        # risk *band* (never the raw score) and the stake is rejected only when
        # that band is EXTREME. All storage mutation stays below this gate.
        if risk_band(self._assess_stake_risk(amount)) >= 3:
            raise gl.vm.UserError(
                f"{ERROR_EXPECTED} stake rejected: AI risk screen flagged extreme risk"
            )

        now_ts = self._now_ts()

        if staker not in self.accounts:
            self.accounts[staker] = StakeAccount(
                principal=u256(0),
                last_accrual_ts=now_ts,
                total_compounded=u256(0),
                total_deposited=u256(0),
                total_withdrawn=u256(0),
                exists=True,
            )
            self.staker_count = u256(self.staker_count + 1)
        else:
            # Compound everything earned up to now before adding the deposit.
            self._settle(staker, now_ts)

        acct = self.accounts[staker]
        acct.principal = u256(acct.principal + amount)
        acct.total_deposited = u256(acct.total_deposited + amount)
        self.total_staked = u256(self.total_staked + amount)

    def _assess_stake_risk(self, amount: int) -> int:
        """LLM risk screen for an incoming stake, settled through consensus.

        Leader and validators each ask the model to score how risky/abnormal the
        deposit is at the current APY, and the validator approves the leader's
        result only when it lands in the same ``risk_band``. The work is wrapped
        in ``gl.vm.run_nondet_unsafe`` so it runs as a non-deterministic block;
        no storage is touched inside the leader/validator closures (the GenVM
        forbids that), so settlement stays deterministic. Returns ``risk_bps``.
        """
        prompt = (
            "You are a DeFi staking risk model. Score how risky or anomalous the "
            "following stake request looks, considering the deposit size and the "
            "advertised annual yield. A plausibly-sized deposit at a sane APY is "
            "low risk; an implausibly high APY or an extreme, exploit-shaped "
            "deposit is high risk.\n"
            f"Deposit amount (atto scale, 1 token == 10**18): {int(amount)}\n"
            f"Advertised APY (basis points, 100 == 1%): {int(self.apy_bps)}\n"
            "Respond as compact JSON only: "
            '{"risk_bps": <integer 0-10000>, "rationale": "<short reason>"}. '
            "risk_bps is the probability of an abnormal/unsafe position in basis "
            "points (e.g. 2500 == 25%)."
        )

        def leader_fn() -> dict:
            analysis = gl.nondet.exec_prompt(prompt, response_format="json")
            return {"risk_bps": int(parse_risk_bps(analysis))}

        def validator_fn(leaders_res: gl.vm.Result) -> bool:
            if not isinstance(leaders_res, gl.vm.Return):
                return _handle_leader_error(leaders_res, leader_fn)
            mine = leader_fn()
            return risk_band(int(leaders_res.calldata["risk_bps"])) == risk_band(
                int(mine["risk_bps"])
            )

        result = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
        return int(result["risk_bps"])

    # --------------------------------------------------------------------- #
    # 2. Intelligent compounding                                            #
    # --------------------------------------------------------------------- #
    @gl.public.write
    def compound_rewards(self) -> int:
        """Compound the caller's accumulated yield into their principal.

        Returns the amount that was re-staked (atto scale).
        """
        self._require_active()
        staker = gl.message.sender_address
        if staker not in self.accounts:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} no stake found for caller")
        compounded = self._settle(staker, self._now_ts())
        return int(compounded)

    @gl.public.write
    def compound_for(self, staker: str) -> int:
        """Permissionless / keeper-triggered compounding for any account.

        Enables automated compounding bots: anyone can advance an account's
        compounding without being able to move funds. The math is identical and
        deterministic, so it can never disadvantage the account owner.
        Returns the amount that was re-staked (atto scale).
        """
        self._require_active()
        target = Address(staker)
        if target not in self.accounts:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} no stake found for target")
        compounded = self._settle(target, self._now_ts())
        return int(compounded)

    # --------------------------------------------------------------------- #
    # 3. Withdrawal logic                                                   #
    # --------------------------------------------------------------------- #
    @gl.public.write
    def withdraw(self, amount: int) -> int:
        """Withdraw ``amount`` (atto scale) of principal + compounded rewards.

        Pending yield is compounded first, so a withdrawal is always taken
        against the freshest balance. Returns the amount withdrawn.
        """
        if amount <= 0:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} withdraw amount must be positive")

        staker = gl.message.sender_address
        if staker not in self.accounts:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} no stake found for caller")

        # Settle first so accrued yield is withdrawable.
        self._settle(staker, self._now_ts())

        acct = self.accounts[staker]
        if amount > acct.principal:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} insufficient staked balance")

        acct.principal = u256(acct.principal - amount)
        acct.total_withdrawn = u256(acct.total_withdrawn + amount)
        self.total_staked = u256(self.total_staked - amount)
        return amount

    @gl.public.write
    def withdraw_max(self) -> int:
        """Withdraw the caller's entire balance (principal + compounded yield).

        Returns the total amount withdrawn.
        """
        staker = gl.message.sender_address
        if staker not in self.accounts:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} no stake found for caller")

        self._settle(staker, self._now_ts())
        acct = self.accounts[staker]
        amount = u256(acct.principal)
        if amount == 0:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} nothing to withdraw")

        acct.principal = u256(0)
        acct.total_withdrawn = u256(acct.total_withdrawn + amount)
        self.total_staked = u256(self.total_staked - amount)
        return int(amount)

    # --------------------------------------------------------------------- #
    # Owner / administration                                                #
    # --------------------------------------------------------------------- #
    @gl.public.write
    def set_apy(self, new_apy_bps: int) -> None:
        """Update the annual yield rate (basis points). Owner only."""
        self._require_owner()
        if new_apy_bps < 0 or new_apy_bps > MAX_APY_BPS:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} new_apy_bps out of range")
        self.apy_bps = u256(new_apy_bps)

    @gl.public.write
    def update_apy_from_market(self) -> int:
        """Refresh ``apy_bps`` from a live DeFiLlama yield feed via consensus.

        Each validator independently fetches the pool's APY history over HTTP
        (``gl.nondet.web.request``), derives the current APY in basis points and
        agrees with the leader when the two are within tolerance (see
        ``apy_in_consensus``). The agreed, already-clamped value is then written
        to storage *after* the non-deterministic block returns. Owner-only,
        because the APY is a protocol-wide economic parameter.

        Returns the new ``apy_bps``.
        """
        self._require_owner()
        self._require_active()

        agreed = self._fetch_market_apy_bps()
        new_apy = max(0, min(int(agreed), int(MAX_APY_BPS)))
        self.apy_bps = u256(new_apy)
        return new_apy

    def _fetch_market_apy_bps(self) -> int:
        """Fetch + parse the live APY (bps) inside a non-deterministic block.

        The consensus-critical value is the derived APY, not the raw feed bytes:
        validators re-fetch and re-parse, then agree within a small band so a
        feed that ticks between reads cannot break consensus.
        """
        url = f"{DEFILLAMA_CHART_BASE}/{DEFILLAMA_DEFAULT_POOL}"

        def leader_fn() -> dict:
            res = gl.nondet.web.request(url, method="GET")
            status_code = getattr(res, "status", 200)
            if status_code >= 500:
                raise gl.vm.UserError(f"{ERROR_TRANSIENT} yield feed {status_code}")
            if status_code >= 400:
                raise gl.vm.UserError(f"{ERROR_EXTERNAL} yield feed {status_code}")
            raw = res.body.decode("utf-8")
            try:
                payload = json.loads(raw)
            except (ValueError, TypeError):
                raise gl.vm.UserError(f"{ERROR_EXTERNAL} yield feed returned non-JSON")
            return {"apy_bps": int(parse_market_apy_bps(payload))}

        def validator_fn(leaders_res: gl.vm.Result) -> bool:
            if not isinstance(leaders_res, gl.vm.Return):
                return _handle_leader_error(leaders_res, leader_fn)
            mine = leader_fn()
            return apy_in_consensus(
                int(leaders_res.calldata["apy_bps"]), int(mine["apy_bps"])
            )

        result = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
        return int(result["apy_bps"])

    @gl.public.write
    def set_paused(self, value: bool) -> None:
        """Pause or resume deposits and compounding. Owner only.

        Withdrawals stay enabled while paused so funds are never trapped.
        """
        self._require_owner()
        self.paused = value

    @gl.public.write
    def transfer_ownership(self, new_owner: str) -> None:
        """Hand the owner role to ``new_owner``. Owner only."""
        self._require_owner()
        self.owner = Address(new_owner)

    # --------------------------------------------------------------------- #
    # Read-only views                                                       #
    # --------------------------------------------------------------------- #
    @gl.public.view
    def get_apy(self) -> int:
        return int(self.apy_bps)

    @gl.public.view
    def is_paused(self) -> bool:
        return self.paused

    @gl.public.view
    def get_owner(self) -> str:
        return self.owner.as_hex

    @gl.public.view
    def preview_pending(self, staker: str) -> int:
        """Yield that ``staker`` would compound if they acted right now."""
        target = Address(staker)
        if target not in self.accounts:
            return 0
        return int(self._pending_yield(self.accounts[target], self._now_ts()))

    @gl.public.view
    def balance_of(self, staker: str) -> int:
        """Principal of ``staker`` (does NOT include unsettled pending yield)."""
        target = Address(staker)
        if target not in self.accounts:
            return 0
        return int(self.accounts[target].principal)

    @gl.public.view
    def total_balance_of(self, staker: str) -> int:
        """Principal + live pending yield for ``staker`` (withdrawable now)."""
        target = Address(staker)
        if target not in self.accounts:
            return 0
        acct = self.accounts[target]
        return int(acct.principal + self._pending_yield(acct, self._now_ts()))

    @gl.public.view
    def get_account(self, staker: str) -> dict:
        """Full position snapshot for ``staker`` — convenient for the frontend."""
        target = Address(staker)
        if target not in self.accounts:
            return {
                "exists": False,
                "principal": 0,
                "pending_yield": 0,
                "total_balance": 0,
                "last_accrual_ts": 0,
                "total_compounded": 0,
                "total_deposited": 0,
                "total_withdrawn": 0,
            }
        acct = self.accounts[target]
        pending = self._pending_yield(acct, self._now_ts())
        return {
            "exists": True,
            "principal": int(acct.principal),
            "pending_yield": int(pending),
            "total_balance": int(acct.principal + pending),
            "last_accrual_ts": int(acct.last_accrual_ts),
            "total_compounded": int(acct.total_compounded),
            "total_deposited": int(acct.total_deposited),
            "total_withdrawn": int(acct.total_withdrawn),
        }

    @gl.public.view
    def get_stats(self) -> dict:
        """Protocol-wide statistics — convenient for dashboards."""
        return {
            "total_staked": int(self.total_staked),
            "staker_count": int(self.staker_count),
            "apy_bps": int(self.apy_bps),
            "paused": self.paused,
            "owner": self.owner.as_hex,
        }


# --------------------------------------------------------------------------- #
# Validator-side error handler (module-level, shared by both non-det methods). #
# Decides whether a validator should AGREE with a leader that raised, based on #
# the error classification prefix.                                            #
# --------------------------------------------------------------------------- #
def _handle_leader_error(leaders_res: gl.vm.Result, leader_fn) -> bool:
    leader_msg = getattr(leaders_res, "message", "") or ""
    try:
        leader_fn()
        return False  # leader failed but validator succeeded -> disagree
    except gl.vm.UserError as exc:
        validator_msg = getattr(exc, "message", "") or str(exc)
        # Deterministic failures must match exactly.
        if validator_msg.startswith(ERROR_EXPECTED) or validator_msg.startswith(ERROR_EXTERNAL):
            return validator_msg == leader_msg
        # Transient failures: agree if both sides hit one.
        if validator_msg.startswith(ERROR_TRANSIENT) and leader_msg.startswith(ERROR_TRANSIENT):
            return True
        # LLM / unknown: disagree to force validator rotation.
        return False
    except Exception:
        return False
