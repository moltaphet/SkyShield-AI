# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
SkyShield AI - Autonomous Algorithmic Flight & Travel Insurance Protocol
========================================================================

An Intelligent Contract for the GenLayer protocol that underwrites parametric
flight-delay insurance *without traditional oracles or keepers*. SkyShield uses
GenLayer's two native superpowers directly inside consensus:

  1. Native internet connectivity ( ``gl.nondet.web`` ) to read live flight
     status straight from an aviation API, and
  2. LLM-driven reasoning ( ``gl.nondet.exec_prompt`` ) to (a) price premiums
     from delay/weather risk and (b) parse messy, free-form flight-status text
     into a structured, deterministic payout decision.

Because every validator independently re-fetches the data and re-runs the model,
the *payout tier* (not the raw, noisy API payload) is the consensus-critical
value that validators must agree on. All economic state is settled with exact
integer math in *atto* scale ( value * 10**18 ), the cross-chain convention, so
there is no floating-point drift between validators.

Architecture
------------
* ``Policy``        - a single parametric insurance position.
* ``LiquidityPool`` - modelled as contract-level fields ( ``total_assets`` /
                      ``total_shares`` / ``lp_shares`` ): a share-based
                      underwriting vault. LPs deposit GEN to back policies and
                      earn the premiums of policies that expire without a delay.

Money flow (per policy)
-----------------------
* On purchase, the premium is escrowed into the pool ( ``total_assets += premium`` )
  and the full ``max_payout`` is *reserved* ( ``locked_coverage += max_payout`` )
  so the protocol can never underwrite coverage it cannot pay.
* On resolution the granular payout is credited to the passenger's ``claimable``
  ledger and the reservation is released. Net LP equity change for a policy is
  ``premium - payout`` :
    - flight on time  -> payout 0  -> status EXPIRED  -> whole premium is LP yield.
    - flight delayed  -> partial/full payout -> status RESOLVED.

Determinism & consensus
-----------------------
* Time comes only from ``datetime.datetime.now()`` , which the GenVM replaces
  with the agreed consensus block time (NOT a wall-clock read).
* Non-deterministic work (web + LLM) is wrapped in custom validator functions
  that compare the *derived decision* (risk band / payout tier), never the raw
  bytes, following the GenLayer equivalence-principle guidance.

Safety
------
* Re-entrancy guard ( ``reentrancy_locked`` ) plus strict checks-effects-
  interactions ordering on every value-out path ( ``withdraw_liquidity`` /
  ``claim`` ).
* Duplicate-policy protection: a passenger cannot hold two ACTIVE policies for
  the same flight + departure.
* Solvency invariant: ``total_assets >= locked_coverage`` is preserved on every
  state transition, so reserved coverage can never be drained by LP withdrawals.

The whole codebase, comments and logs are intentionally ASCII / English only.
"""

import datetime
from dataclasses import dataclass

from genlayer import *


# --------------------------------------------------------------------------- #
# Error classification prefixes (GenLayer standard).                          #
#   EXPECTED  - deterministic business logic; validators must match exactly.  #
#   EXTERNAL  - external API 4xx; deterministic; must match exactly.          #
#   TRANSIENT - network / 5xx; non-deterministic; agree if both transient.    #
#   LLM_ERROR - model misbehaviour; always disagree to force validator rotation.
# --------------------------------------------------------------------------- #
ERROR_EXPECTED = "[EXPECTED]"
ERROR_EXTERNAL = "[EXTERNAL]"
ERROR_TRANSIENT = "[TRANSIENT]"
ERROR_LLM = "[LLM_ERROR]"


# --------------------------------------------------------------------------- #
# Economic constants (all money in atto scale: 1 GEN == 10**18).              #
# --------------------------------------------------------------------------- #
ATTO: int = 10**18
BPS_DENOMINATOR: int = 10_000          # 100.00% expressed in basis points

BASE_COVERAGE_ATTO: int = 1_000 * ATTO  # max payout underwritten per policy
LOADING_BPS: int = 3_000                # protocol risk margin on top of fair odds (30%)
MIN_PREMIUM_ATTO: int = 1 * ATTO        # floor so dust flights still pay a real premium
MAX_RISK_BPS: int = 10_000              # risk probability is bounded to [0, 100%]

# Multi-stage granular payout tiers (basis points of max_payout).
DELAY_TIER_1_MIN: int = 60              # 1h  ..  2h  delay -> 20%
DELAY_TIER_2_MIN: int = 120            # 2h  ..  4h  delay -> 50%
DELAY_TIER_3_MIN: int = 240            # >4h  or CANCELLED  -> 100%
PAYOUT_BPS_TIER_1: int = 2_000          # 20%
PAYOUT_BPS_TIER_2: int = 5_000          # 50%
PAYOUT_BPS_TIER_3: int = 10_000         # 100%

# Aviation data source. The flight code is appended as ``flight_iata``. A real
# deployment supplies its own API key via the URL; the parsing layer below is
# deliberately provider-agnostic because the LLM normalizes whatever shape the
# endpoint returns into a canonical status.
AVIATION_API_BASE: str = "https://api.aviationstack.com/v1/flights"

# Policy status values (stored as plain strings; GenLayer storage has no enum).
STATUS_ACTIVE: str = "ACTIVE"
STATUS_RESOLVED: str = "RESOLVED"
STATUS_EXPIRED: str = "EXPIRED"


# --------------------------------------------------------------------------- #
# Pure, deterministic helper functions.                                       #
#                                                                             #
# These take and return plain ints/str so they can be unit-tested directly    #
# (no VM, no storage) AND reused identically by leader and validator code,    #
# which is what keeps the payout decision reproducible across validators.     #
# --------------------------------------------------------------------------- #
def payout_bps_for_delay(delay_minutes: int, cancelled: bool) -> int:
    """Map a delay (in minutes) to a payout fraction in basis points.

    Tiers (inclusive lower bound):
        cancelled or delay >= 240 min -> 100%
        120 <= delay < 240 min        ->  50%
         60 <= delay < 120 min        ->  20%
        delay < 60 min                ->   0%  (on time -> policy EXPIRES)
    """
    if cancelled:
        return PAYOUT_BPS_TIER_3
    if delay_minutes >= DELAY_TIER_3_MIN:
        return PAYOUT_BPS_TIER_3
    if delay_minutes >= DELAY_TIER_2_MIN:
        return PAYOUT_BPS_TIER_2
    if delay_minutes >= DELAY_TIER_1_MIN:
        return PAYOUT_BPS_TIER_1
    return 0


def quote_premium_atto(coverage_atto: int, risk_bps: int, loading_bps: int) -> int:
    """Fair-odds premium plus a protocol loading margin.

        expected_loss = coverage * risk_bps / 10000
        premium       = expected_loss * (1 + loading_bps / 10000)

    Clamped below by ``MIN_PREMIUM_ATTO`` and risk clamped to [0, 100%]. All
    integer math (floor division) so every validator computes the same value.
    """
    risk = max(0, min(int(risk_bps), MAX_RISK_BPS))
    expected_loss = coverage_atto * risk // BPS_DENOMINATOR
    premium = expected_loss * (BPS_DENOMINATOR + loading_bps) // BPS_DENOMINATOR
    return max(premium, MIN_PREMIUM_ATTO)


def risk_band(risk_bps: int) -> int:
    """Bucket a risk score into a coarse band for validator agreement.

    Two validators will rarely produce an identical ``risk_bps`` from an LLM, so
    consensus is checked at band granularity (plus a premium tolerance), not on
    the exact number.
        0: low    (< 15%)   1: moderate (15-40%)
        2: high   (40-70%)  3: extreme  (>= 70%)
    """
    if risk_bps < 1_500:
        return 0
    if risk_bps < 4_000:
        return 1
    if risk_bps < 7_000:
        return 2
    return 3


def _coerce_int(raw: object) -> int:
    """Best-effort coercion of an LLM/JSON value into an int.

    Handles int, float, and strings like ``"180"`` / ``" 180 "`` / ``"180.0"``.
    Raises an LLM-classified error on anything non-numeric so the validator can
    force a rotation instead of committing garbage.
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
        for alt in ("risk", "probability_bps", "delay_probability_bps", "score"):
            if alt in analysis:
                raw = analysis[alt]
                break
    if raw is None:
        raise gl.vm.UserError(
            f"{ERROR_LLM} missing 'risk_bps'. keys={list(analysis.keys())}"
        )
    return max(0, min(_coerce_int(raw), MAX_RISK_BPS))


def parse_flight_status(analysis: dict) -> tuple:
    """Normalize an LLM-parsed flight status into ``(delay_minutes, cancelled)``.

    Accepts a variety of key spellings the model might emit and treats an
    explicit cancelled/diverted status as a full-payout event.
    """
    if not isinstance(analysis, dict):
        raise gl.vm.UserError(f"{ERROR_LLM} status response is not a dict: {type(analysis)}")

    status = str(analysis.get("status", analysis.get("flight_status", ""))).strip().upper()

    cancelled_raw = analysis.get("cancelled", analysis.get("is_cancelled"))
    cancelled = bool(cancelled_raw) or status in ("CANCELLED", "CANCELED", "DIVERTED")

    delay_raw = analysis.get("delay_minutes")
    if delay_raw is None:
        for alt in ("delay", "delay_min", "delayed_minutes", "minutes_delayed"):
            if alt in analysis:
                delay_raw = analysis[alt]
                break
    delay_minutes = 0 if delay_raw is None else max(0, _coerce_int(delay_raw))
    return delay_minutes, cancelled


# --------------------------------------------------------------------------- #
# On-chain Policy record.                                                      #
# Fields are append-only: never reorder or insert, only append, to preserve   #
# storage layout for upgradable deployments.                                  #
# --------------------------------------------------------------------------- #
@allow_storage
@dataclass
class Policy:
    policy_id: u256
    passenger: Address
    flight_code: str
    departure_timestamp: u256      # unix seconds the flight is scheduled to leave
    premium_paid: u256             # atto GEN the passenger paid into the pool
    max_payout: u256               # atto GEN coverage (reserved while ACTIVE)
    payout_amount: u256            # atto GEN actually paid out on resolution
    status: str                    # STATUS_ACTIVE / STATUS_RESOLVED / STATUS_EXPIRED
    risk_bps: u256                 # risk score the premium was priced from
    delay_minutes: u256            # observed delay at resolution time
    created_at: u256               # consensus timestamp of purchase
    resolved_at: u256              # consensus timestamp of resolution (0 while ACTIVE)


class SkyShieldAI(gl.Contract):
    # ----- Ownership / lifecycle ------------------------------------------- #
    owner: Address
    paused: bool                   # blocks new policies + LP deposits (not exits)
    reentrancy_locked: bool        # re-entrancy guard for value-out paths

    # ----- Liquidity pool (share-based underwriting vault) ----------------- #
    total_assets: u256             # GEN backing the pool (LP deposits + premiums - payouts)
    total_shares: u256             # total LP shares minted
    locked_coverage: u256          # sum of max_payout reserved by ACTIVE policies
    lp_shares: TreeMap[Address, u256]
    claimable: TreeMap[Address, u256]   # pull-payment ledger (passengers + exiting LPs)

    # ----- Policies -------------------------------------------------------- #
    next_policy_id: u256
    policies: TreeMap[u256, Policy]
    # passenger|flight|departure -> policy_id of the most recent registration,
    # used to reject a duplicate ACTIVE policy for the same flight.
    active_key_to_policy: TreeMap[str, u256]

    # ----- Protocol statistics (dashboards) -------------------------------- #
    policy_count: u256
    lp_count: u256
    total_premiums_collected: u256
    total_payouts: u256
    total_yield_to_lps: u256       # premiums retained from EXPIRED (on-time) policies

    # --------------------------------------------------------------------- #
    # Lifecycle                                                             #
    # --------------------------------------------------------------------- #
    def __init__(self) -> None:
        self.owner = gl.message.sender_address
        self.paused = False
        self.reentrancy_locked = False
        self.total_assets = u256(0)
        self.total_shares = u256(0)
        self.locked_coverage = u256(0)
        self.next_policy_id = u256(1)
        self.policy_count = u256(0)
        self.lp_count = u256(0)
        self.total_premiums_collected = u256(0)
        self.total_payouts = u256(0)
        self.total_yield_to_lps = u256(0)

    # --------------------------------------------------------------------- #
    # Internal helpers                                                      #
    # --------------------------------------------------------------------- #
    def _now_ts(self) -> u256:
        """Deterministic consensus timestamp (unix seconds).

        Inside the GenVM, ``datetime.datetime.now()`` is the block time proposed
        by the leader and agreed by every validator - it is NOT a wall-clock
        read, so it is safe to use directly in state-changing logic.
        """
        return u256(int(datetime.datetime.now(datetime.timezone.utc).timestamp()))

    def _require_owner(self) -> None:
        if gl.message.sender_address != self.owner:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} caller is not the owner")

    def _require_active(self) -> None:
        if self.paused:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} contract is paused")

    def _enter(self) -> None:
        """Acquire the re-entrancy lock; revert if already held."""
        if self.reentrancy_locked:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} re-entrant call rejected")
        self.reentrancy_locked = True

    def _exit(self) -> None:
        self.reentrancy_locked = False

    def _available_liquidity(self) -> u256:
        """Free GEN that is not reserved against ACTIVE coverage."""
        if self.total_assets <= self.locked_coverage:
            return u256(0)
        return u256(self.total_assets - self.locked_coverage)

    def _dedup_key(self, passenger: Address, flight_code: str, departure_timestamp: int) -> str:
        return f"{passenger.as_hex}|{flight_code}|{int(departure_timestamp)}"

    def _credit(self, account: Address, amount: u256) -> None:
        """Add ``amount`` to an account's pull-payment balance."""
        if amount == 0:
            return
        current = self.claimable[account] if account in self.claimable else u256(0)
        self.claimable[account] = u256(current + amount)

    # --------------------------------------------------------------------- #
    # 1. Liquidity provision (LP side) - fully deterministic                #
    # --------------------------------------------------------------------- #
    @gl.public.write
    def provide_liquidity(self, amount: int) -> int:
        """Deposit ``amount`` (atto GEN) into the underwriting pool.

        Shares are minted pro-rata to the current pool value so an LP can never
        dilute existing providers. In production the deposit must be backed by
        ``gl.message.value`` ; ``amount`` is the parameterized atto figure that
        mirrors it and keeps the accounting unit-testable in direct mode.

        Returns the number of pool shares minted.
        """
        self._require_active()
        if amount <= 0:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} deposit amount must be positive")

        provider = gl.message.sender_address

        if self.total_shares == 0 or self.total_assets == 0:
            minted = u256(amount)              # bootstrap: 1 share == 1 atto
        else:
            minted = u256(amount * self.total_shares // self.total_assets)
        if minted == 0:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} deposit too small to mint a share")

        if provider not in self.lp_shares:
            self.lp_count = u256(self.lp_count + 1)
            self.lp_shares[provider] = u256(0)

        self.lp_shares[provider] = u256(self.lp_shares[provider] + minted)
        self.total_shares = u256(self.total_shares + minted)
        self.total_assets = u256(self.total_assets + amount)
        return int(minted)

    @gl.public.write
    def withdraw_liquidity(self, shares: int) -> int:
        """Burn ``shares`` and move the redeemed GEN to the caller's claim ledger.

        Guarded against re-entrancy and ordered checks-effects-interactions: all
        share/asset bookkeeping is committed *before* the funds become claimable.
        An LP can only redeem against *available* (un-reserved) liquidity, so
        active policy coverage can never be pulled out from under passengers.

        Returns the atto GEN credited to the caller's claimable balance.
        """
        if shares <= 0:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} share amount must be positive")

        provider = gl.message.sender_address
        held = self.lp_shares[provider] if provider in self.lp_shares else u256(0)
        if shares > held:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} insufficient LP shares")

        self._enter()

        gross = u256(shares * self.total_assets // self.total_shares)
        if gross > self._available_liquidity():
            self._exit()
            raise gl.vm.UserError(
                f"{ERROR_EXPECTED} redemption exceeds available (un-reserved) liquidity"
            )

        # Effects first.
        self.lp_shares[provider] = u256(held - shares)
        self.total_shares = u256(self.total_shares - shares)
        self.total_assets = u256(self.total_assets - gross)

        # Interaction (pull-payment ledger; real transfer happens on claim()).
        self._credit(provider, gross)

        self._exit()
        return int(gross)

    # --------------------------------------------------------------------- #
    # 2. Policy purchase - dynamic AI risk pricing (NON-DETERMINISTIC)      #
    # --------------------------------------------------------------------- #
    @gl.public.write
    def purchase_policy(self, flight_code: str, departure_timestamp: int) -> int:
        """Buy parametric delay coverage for ``flight_code``.

        The premium is priced dynamically: a quick internal AI 'web-scrape'
        risk model estimates the probability the flight is delayed >= 1h or
        cancelled, and the premium is the fair-odds expected loss plus the
        protocol loading margin. Coverage (``max_payout``) is fixed per policy.

        Consensus: validators independently re-run the model. They agree when
        the leader's risk lands in the same ``risk_band`` and the premium is
        within a +/-25% tolerance - the noisy raw score is never compared
        directly. Returns the new ``policy_id``.
        """
        self._require_active()
        if not flight_code or not flight_code.strip():
            raise gl.vm.UserError(f"{ERROR_EXPECTED} flight_code is required")
        if departure_timestamp <= 0:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} departure_timestamp must be positive")

        passenger = gl.message.sender_address
        self._reject_duplicate(passenger, flight_code, departure_timestamp)

        quote = self._assess_risk_quote(flight_code.strip(), int(departure_timestamp))
        return self._mint_policy(
            passenger,
            flight_code.strip(),
            int(departure_timestamp),
            int(quote["risk_bps"]),
            int(quote["premium"]),
        )

    def _assess_risk_quote(self, flight_code: str, departure_timestamp: int) -> dict:
        """Non-deterministic risk assessment wrapped in a custom validator.

        Leader and validators each ask the model for a delay-risk probability
        and derive a premium from it; the validator approves the leader's quote
        if it falls in the same risk band and premium tolerance.
        """
        prompt = (
            "You are an aviation delay-risk underwriting model. Using your "
            "knowledge of historical on-time performance, typical routing and "
            "seasonal weather patterns, estimate the probability that the flight "
            "below is delayed by at least 60 minutes OR cancelled.\n"
            f"Flight code (IATA): {flight_code}\n"
            f"Scheduled departure (unix seconds, UTC): {departure_timestamp}\n"
            "Respond as compact JSON only: "
            '{"risk_bps": <integer 0-10000>, "rationale": "<short reason>"}. '
            "risk_bps is the probability in basis points (e.g. 2500 == 25%)."
        )

        def leader_fn() -> dict:
            analysis = gl.nondet.exec_prompt(prompt, response_format="json")
            risk = parse_risk_bps(analysis)
            premium = quote_premium_atto(BASE_COVERAGE_ATTO, risk, LOADING_BPS)
            return {"risk_bps": int(risk), "premium": int(premium)}

        def validator_fn(leaders_res: gl.vm.Result) -> bool:
            if not isinstance(leaders_res, gl.vm.Return):
                return _handle_leader_error(leaders_res, leader_fn)
            mine = leader_fn()
            leader_risk = int(leaders_res.calldata["risk_bps"])
            leader_premium = int(leaders_res.calldata["premium"])
            if risk_band(leader_risk) != risk_band(mine["risk_bps"]):
                return False
            if leader_premium <= 0 or mine["premium"] <= 0:
                return leader_premium == mine["premium"]
            ratio = leader_premium / mine["premium"]
            return 0.75 <= ratio <= 1.3333

        return gl.vm.run_nondet_unsafe(leader_fn, validator_fn)

    def _reject_duplicate(
        self, passenger: Address, flight_code: str, departure_timestamp: int
    ) -> None:
        key = self._dedup_key(passenger, flight_code, departure_timestamp)
        if key in self.active_key_to_policy:
            existing_id = self.active_key_to_policy[key]
            if (
                existing_id in self.policies
                and self.policies[existing_id].status == STATUS_ACTIVE
            ):
                raise gl.vm.UserError(
                    f"{ERROR_EXPECTED} an ACTIVE policy already exists for this flight"
                )

    def _mint_policy(
        self,
        passenger: Address,
        flight_code: str,
        departure_timestamp: int,
        risk_bps: int,
        premium: int,
    ) -> int:
        """Deterministic core of policy creation: escrow premium, reserve
        coverage, persist the record. Reused by the AI path and the owner
        fallback so both share identical accounting.
        """
        max_payout = BASE_COVERAGE_ATTO

        # Escrow the premium into the pool, then verify the pool can still cover
        # the newly reserved payout. A revert here rolls the whole tx back.
        self.total_assets = u256(self.total_assets + premium)
        if self._available_liquidity() < max_payout:
            raise gl.vm.UserError(
                f"{ERROR_EXPECTED} insufficient pool liquidity to underwrite this policy"
            )
        self.locked_coverage = u256(self.locked_coverage + max_payout)

        policy_id = self.next_policy_id
        now_ts = self._now_ts()
        self.policies[policy_id] = Policy(
            policy_id=u256(policy_id),
            passenger=passenger,
            flight_code=flight_code,
            departure_timestamp=u256(departure_timestamp),
            premium_paid=u256(premium),
            max_payout=u256(max_payout),
            payout_amount=u256(0),
            status=STATUS_ACTIVE,
            risk_bps=u256(max(0, min(risk_bps, MAX_RISK_BPS))),
            delay_minutes=u256(0),
            created_at=now_ts,
            resolved_at=u256(0),
        )

        self.active_key_to_policy[
            self._dedup_key(passenger, flight_code, departure_timestamp)
        ] = u256(policy_id)
        self.next_policy_id = u256(policy_id + 1)
        self.policy_count = u256(self.policy_count + 1)
        self.total_premiums_collected = u256(self.total_premiums_collected + premium)
        return int(policy_id)

    # --------------------------------------------------------------------- #
    # 3. Autonomous resolution - live flight data + LLM (NON-DETERMINISTIC) #
    # --------------------------------------------------------------------- #
    @gl.public.write
    def check_flight_and_execute(self, policy_id: int) -> dict:
        """Self-triggering execution hook (keeper-less).

        Anyone - including a GenLayer autonomous/scheduled transaction - may call
        this once a flight's scheduled departure has passed. It fetches the live
        flight status over HTTP, uses the LLM to parse the raw status into a
        delay decision, and settles the policy with the granular payout tier:

            1h .. 2h  delay        -> 20% of max_payout
            2h .. 4h  delay        -> 50% of max_payout
            > 4h delay or CANCELLED -> 100% of max_payout
            on time                 -> 0%, policy EXPIRES, premium becomes LP yield

        The consensus-critical value is the *payout tier*, not the raw API bytes:
        validators re-fetch, re-parse and agree only on the derived tier.
        """
        if policy_id not in self.policies:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} unknown policy_id")
        policy = self.policies[policy_id]
        if policy.status != STATUS_ACTIVE:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} policy is not ACTIVE")
        if self._now_ts() < policy.departure_timestamp:
            raise gl.vm.UserError(
                f"{ERROR_EXPECTED} flight has not departed yet; cannot resolve"
            )

        decision = self._fetch_flight_decision(policy.flight_code)
        delay_minutes = int(decision["delay_minutes"])
        payout_bps = int(decision["payout_bps"])
        return self._apply_resolution(int(policy_id), payout_bps, delay_minutes)

    def _fetch_flight_decision(self, flight_code: str) -> dict:
        """Fetch + LLM-parse live flight status into an agreed payout tier.

        Leader and validators both hit the aviation API and parse it; the
        validator agrees only when its independently derived ``payout_bps`` tier
        matches the leader's. Raw delay minutes are reported for the record but
        are NOT the consensus gate (only the tier is), so minor numeric drift
        between providers cannot break consensus.
        """
        url = f"{AVIATION_API_BASE}?flight_iata={flight_code}"

        def leader_fn() -> dict:
            res = gl.nondet.web.request(url, method="GET")
            status_code = getattr(res, "status", 200)
            if status_code >= 500:
                raise gl.vm.UserError(f"{ERROR_TRANSIENT} aviation API {status_code}")
            if status_code >= 400:
                raise gl.vm.UserError(f"{ERROR_EXTERNAL} aviation API {status_code}")
            raw = res.body.decode("utf-8")

            parse_prompt = (
                "You are given the raw response from a flight-status API. "
                "Extract the current status of the single most relevant flight.\n"
                f"RAW RESPONSE:\n{raw}\n\n"
                "Respond as compact JSON only: "
                '{"status": "<SCHEDULED|ACTIVE|LANDED|DELAYED|CANCELLED|DIVERTED>", '
                '"delay_minutes": <integer minutes of delay, 0 if none>, '
                '"cancelled": <true|false>}.'
            )
            analysis = gl.nondet.exec_prompt(parse_prompt, response_format="json")
            delay_minutes, cancelled = parse_flight_status(analysis)
            return {
                "delay_minutes": int(delay_minutes),
                "payout_bps": int(payout_bps_for_delay(delay_minutes, cancelled)),
            }

        def validator_fn(leaders_res: gl.vm.Result) -> bool:
            if not isinstance(leaders_res, gl.vm.Return):
                return _handle_leader_error(leaders_res, leader_fn)
            mine = leader_fn()
            # Only the derived payout tier must match - the money decision.
            return int(leaders_res.calldata["payout_bps"]) == int(mine["payout_bps"])

        return gl.vm.run_nondet_unsafe(leader_fn, validator_fn)

    def _apply_resolution(self, policy_id: int, payout_bps: int, delay_minutes: int) -> dict:
        """Deterministic settlement core shared by the autonomous path and the
        owner fallback. Pays the granular payout, releases the reservation and
        records EXPIRED (on time) vs RESOLVED (delayed)."""
        policy = self.policies[policy_id]
        if policy.status != STATUS_ACTIVE:
            # Idempotency / double-resolve guard: never pay a policy twice.
            raise gl.vm.UserError(f"{ERROR_EXPECTED} policy already resolved")

        max_payout = policy.max_payout
        bps = max(0, min(int(payout_bps), BPS_DENOMINATOR))
        payout = u256(int(max_payout) * bps // BPS_DENOMINATOR)

        # Release the reservation regardless of outcome.
        self.locked_coverage = u256(self.locked_coverage - max_payout)

        if payout > 0:
            self.total_assets = u256(self.total_assets - payout)
            self._credit(policy.passenger, payout)
            policy.status = STATUS_RESOLVED
            self.total_payouts = u256(self.total_payouts + payout)
        else:
            # On-time flight: the escrowed premium stays in the pool as LP yield.
            policy.status = STATUS_EXPIRED
            self.total_yield_to_lps = u256(self.total_yield_to_lps + policy.premium_paid)

        policy.payout_amount = u256(payout)
        policy.delay_minutes = u256(max(0, int(delay_minutes)))
        policy.resolved_at = self._now_ts()

        return {
            "policy_id": int(policy_id),
            "status": policy.status,
            "payout_bps": int(bps),
            "payout_amount": int(payout),
            "delay_minutes": int(policy.delay_minutes),
        }

    # --------------------------------------------------------------------- #
    # 4. Pull-payment claim - single value-out chokepoint                   #
    # --------------------------------------------------------------------- #
    @gl.public.write
    def claim(self) -> int:
        """Withdraw the caller's accrued balance (payouts + redeemed LP value).

        This is the only path where GEN actually leaves the contract, so it is
        the natural place to enforce the re-entrancy guard and checks-effects-
        interactions ordering: the ledger is zeroed before the (production)
        transfer. Returns the atto GEN paid out.
        """
        account = gl.message.sender_address
        amount = self.claimable[account] if account in self.claimable else u256(0)
        if amount == 0:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} nothing to claim")

        self._enter()
        # Effect: zero the ledger before the external interaction.
        self.claimable[account] = u256(0)
        # Interaction: a production deployment transfers ``amount`` to ``account``
        # here via the GenLayer value-transfer primitive.
        self._exit()
        return int(amount)

    # --------------------------------------------------------------------- #
    # 5. Owner fallbacks (oracle-bypass / emergency + deterministic testing) #
    # --------------------------------------------------------------------- #
    @gl.public.write
    def admin_open_policy(
        self, passenger: str, flight_code: str, departure_timestamp: int, risk_bps: int
    ) -> int:
        """Open a policy with an explicitly supplied risk score (no LLM call).

        Purpose: (a) deterministic direct-mode testing of the pool/policy
        accounting, and (b) an emergency fallback if the pricing model endpoint
        is unavailable. Owner-only so it can never be used to underprice
        coverage in normal operation.
        """
        self._require_owner()
        self._require_active()
        if not flight_code or not flight_code.strip():
            raise gl.vm.UserError(f"{ERROR_EXPECTED} flight_code is required")
        if departure_timestamp <= 0:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} departure_timestamp must be positive")
        target = Address(passenger)
        self._reject_duplicate(target, flight_code.strip(), int(departure_timestamp))
        premium = quote_premium_atto(BASE_COVERAGE_ATTO, int(risk_bps), LOADING_BPS)
        return self._mint_policy(
            target, flight_code.strip(), int(departure_timestamp), int(risk_bps), int(premium)
        )

    @gl.public.write
    def admin_resolve_policy(self, policy_id: int, delay_minutes: int, cancelled: bool) -> dict:
        """Settle a policy from an explicit delay (no web/LLM call).

        Purpose: deterministic testing of every payout tier, and an emergency
        fallback if the aviation API is permanently unreachable. Owner-only. The
        delay -> tier mapping is identical to the autonomous path.
        """
        self._require_owner()
        if policy_id not in self.policies:
            raise gl.vm.UserError(f"{ERROR_EXPECTED} unknown policy_id")
        bps = payout_bps_for_delay(int(delay_minutes), bool(cancelled))
        return self._apply_resolution(int(policy_id), int(bps), int(delay_minutes))

    @gl.public.write
    def set_paused(self, value: bool) -> None:
        """Pause/resume new policies and LP deposits. Exits stay open. Owner-only."""
        self._require_owner()
        self.paused = value

    @gl.public.write
    def transfer_ownership(self, new_owner: str) -> None:
        """Hand the owner role to ``new_owner``. Owner-only."""
        self._require_owner()
        self.owner = Address(new_owner)

    # --------------------------------------------------------------------- #
    # Read-only views                                                       #
    # --------------------------------------------------------------------- #
    @gl.public.view
    def preview_premium(self, risk_bps: int) -> int:
        """Premium (atto GEN) that a given risk score would price to."""
        return int(quote_premium_atto(BASE_COVERAGE_ATTO, int(risk_bps), LOADING_BPS))

    @gl.public.view
    def quote_payout(self, delay_minutes: int, cancelled: bool) -> int:
        """Atto GEN a base policy would pay for a given delay/cancellation."""
        bps = payout_bps_for_delay(int(delay_minutes), bool(cancelled))
        return int(BASE_COVERAGE_ATTO * bps // BPS_DENOMINATOR)

    @gl.public.view
    def get_policy(self, policy_id: int) -> dict:
        if policy_id not in self.policies:
            return {"exists": False}
        p = self.policies[policy_id]
        return {
            "exists": True,
            "policy_id": int(p.policy_id),
            "passenger": p.passenger.as_hex,
            "flight_code": p.flight_code,
            "departure_timestamp": int(p.departure_timestamp),
            "premium_paid": int(p.premium_paid),
            "max_payout": int(p.max_payout),
            "payout_amount": int(p.payout_amount),
            "status": p.status,
            "risk_bps": int(p.risk_bps),
            "delay_minutes": int(p.delay_minutes),
            "created_at": int(p.created_at),
            "resolved_at": int(p.resolved_at),
        }

    @gl.public.view
    def claimable_of(self, account: str) -> int:
        target = Address(account)
        if target not in self.claimable:
            return 0
        return int(self.claimable[target])

    @gl.public.view
    def lp_position(self, account: str) -> dict:
        """LP share balance and its current redeemable value (atto GEN)."""
        target = Address(account)
        shares = int(self.lp_shares[target]) if target in self.lp_shares else 0
        if self.total_shares == 0 or shares == 0:
            value = 0
        else:
            value = int(shares * self.total_assets // self.total_shares)
        return {
            "shares": shares,
            "redeemable_value": value,
            "available_value": min(value, int(self._available_liquidity())),
        }

    @gl.public.view
    def share_price_atto(self) -> int:
        """Value of one share * 10**18, for off-chain display."""
        if self.total_shares == 0:
            return ATTO
        return int(self.total_assets * ATTO // self.total_shares)

    @gl.public.view
    def get_pool_stats(self) -> dict:
        return {
            "total_assets": int(self.total_assets),
            "total_shares": int(self.total_shares),
            "locked_coverage": int(self.locked_coverage),
            "available_liquidity": int(self._available_liquidity()),
            "lp_count": int(self.lp_count),
            "policy_count": int(self.policy_count),
            "total_premiums_collected": int(self.total_premiums_collected),
            "total_payouts": int(self.total_payouts),
            "total_yield_to_lps": int(self.total_yield_to_lps),
            "paused": self.paused,
            "owner": self.owner.as_hex,
        }


# --------------------------------------------------------------------------- #
# Validator-side error handler (module-level so it is shared by both non-det  #
# methods). Decides whether a validator should AGREE with a leader that       #
# raised, based on the error classification prefix.                           #
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
