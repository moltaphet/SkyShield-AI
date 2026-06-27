"""Direct-mode tests for the SkyShield AI flight-insurance contract.

Run from the repo root with:  pytest tests/direct/ -v
(use the project's Python 3.12 venv: .venv/bin/python -m pytest tests/direct/ -q)

Direct mode runs in-memory (no server, no validators), so it exercises the
*deterministic* surface only: the payout-tier and premium math (through the
public view methods), the share-based pool accounting, the full policy
lifecycle via the owner fallback entry points, access control, and every guard
that reverts BEFORE a non-deterministic web/LLM call is reached.

The non-deterministic methods themselves -- ``purchase_policy`` (AI pricing) and
the live-fetch half of ``check_flight_and_execute`` -- require real validators
and are covered by the integration plan in tests/integration/, not here.
Time is advanced with the ``direct_vm.warp`` cheatcode so timestamps are
deterministic.
"""

CONTRACT = "contracts/sky_shield_ai.py"

GEN = 10**18                 # 1 GEN in atto scale
BASE_COVERAGE = 1_000 * GEN  # max payout per policy (matches contract constant)

# A scheduled-departure timestamp safely in the future relative to the warp
# clock below (2030-01-01), so resolution-time guards see "not departed yet".
FUTURE_DEPARTURE = 1_893_456_000  # 2030-01-01T00:00:00Z


def H(addr) -> str:
    """Render a test address (raw bytes) as a 0x-hex string for contract calls."""
    return "0x" + (addr if isinstance(addr, (bytes, bytearray)) else addr.as_bytes).hex()


def _deploy(direct_vm, direct_deploy, direct_owner):
    direct_vm.sender = direct_owner
    direct_vm.warp("2025-01-01T00:00:00Z")
    return direct_deploy(CONTRACT)


def _fund_pool(contract, direct_vm, lp, amount):
    direct_vm.sender = lp
    return contract.provide_liquidity(amount)


# --------------------------------------------------------------------------- #
# Payout tiers (pure logic exercised through the quote_payout view)           #
# --------------------------------------------------------------------------- #
def test_payout_tiers(direct_vm, direct_deploy, direct_owner):
    c = _deploy(direct_vm, direct_deploy, direct_owner)
    # On time -> no payout.
    assert c.quote_payout(0, False) == 0
    assert c.quote_payout(59, False) == 0
    # 1h..2h -> 20%.
    assert c.quote_payout(60, False) == 200 * GEN
    assert c.quote_payout(119, False) == 200 * GEN
    # 2h..4h -> 50%.
    assert c.quote_payout(120, False) == 500 * GEN
    assert c.quote_payout(239, False) == 500 * GEN
    # >4h -> 100%.
    assert c.quote_payout(240, False) == 1_000 * GEN
    assert c.quote_payout(600, False) == 1_000 * GEN
    # Cancelled -> 100% regardless of delay.
    assert c.quote_payout(0, True) == 1_000 * GEN


def test_premium_pricing(direct_vm, direct_deploy, direct_owner):
    c = _deploy(direct_vm, direct_deploy, direct_owner)
    # risk 20% -> expected loss 200 GEN -> +30% loading -> 260 GEN.
    assert c.preview_premium(2_000) == 260 * GEN
    # risk 50% -> 500 GEN expected -> 650 GEN.
    assert c.preview_premium(5_000) == 650 * GEN
    # Floored at the minimum premium for near-zero risk.
    assert c.preview_premium(0) == 1 * GEN
    # Risk is clamped at 100%.
    assert c.preview_premium(99_999) == c.preview_premium(10_000)


# --------------------------------------------------------------------------- #
# Liquidity provision and share accounting                                    #
# --------------------------------------------------------------------------- #
def test_first_lp_bootstraps_one_to_one(direct_vm, direct_deploy, direct_owner, direct_alice):
    c = _deploy(direct_vm, direct_deploy, direct_owner)
    minted = _fund_pool(c, direct_vm, direct_alice, 10_000 * GEN)

    assert minted == 10_000 * GEN
    stats = c.get_pool_stats()
    assert stats["total_assets"] == 10_000 * GEN
    assert stats["total_shares"] == 10_000 * GEN
    assert stats["available_liquidity"] == 10_000 * GEN
    assert stats["lp_count"] == 1
    pos = c.lp_position(H(direct_alice))
    assert pos["shares"] == 10_000 * GEN
    assert pos["redeemable_value"] == 10_000 * GEN


def test_second_lp_minted_pro_rata(direct_vm, direct_deploy, direct_owner, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_owner)
    _fund_pool(c, direct_vm, direct_alice, 10_000 * GEN)
    # No yield yet, so bob deposits at par and gets proportional shares.
    minted = _fund_pool(c, direct_vm, direct_bob, 5_000 * GEN)
    assert minted == 5_000 * GEN
    assert c.get_pool_stats()["total_shares"] == 15_000 * GEN


def test_provide_liquidity_rejects_zero(direct_vm, direct_deploy, direct_owner, direct_alice):
    c = _deploy(direct_vm, direct_deploy, direct_owner)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("deposit amount must be positive"):
        c.provide_liquidity(0)


def test_withdraw_liquidity_credits_claimable(direct_vm, direct_deploy, direct_owner, direct_alice):
    c = _deploy(direct_vm, direct_deploy, direct_owner)
    _fund_pool(c, direct_vm, direct_alice, 10_000 * GEN)

    direct_vm.sender = direct_alice
    credited = c.withdraw_liquidity(4_000 * GEN)
    assert credited == 4_000 * GEN
    assert c.claimable_of(H(direct_alice)) == 4_000 * GEN
    # Pool shrank by the redemption.
    assert c.get_pool_stats()["total_assets"] == 6_000 * GEN
    assert c.lp_position(H(direct_alice))["shares"] == 6_000 * GEN


def test_withdraw_more_shares_than_held_reverts(direct_vm, direct_deploy, direct_owner, direct_alice):
    c = _deploy(direct_vm, direct_deploy, direct_owner)
    _fund_pool(c, direct_vm, direct_alice, 1_000 * GEN)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("insufficient LP shares"):
        c.withdraw_liquidity(2_000 * GEN)


def test_claim_pays_and_zeroes(direct_vm, direct_deploy, direct_owner, direct_alice):
    c = _deploy(direct_vm, direct_deploy, direct_owner)
    _fund_pool(c, direct_vm, direct_alice, 10_000 * GEN)
    direct_vm.sender = direct_alice
    c.withdraw_liquidity(3_000 * GEN)

    paid = c.claim()
    assert paid == 3_000 * GEN
    assert c.claimable_of(H(direct_alice)) == 0


def test_claim_nothing_reverts(direct_vm, direct_deploy, direct_owner, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_owner)
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("nothing to claim"):
        c.claim()


# --------------------------------------------------------------------------- #
# Policy lifecycle (owner fallback path = deterministic core of the AI path)  #
# --------------------------------------------------------------------------- #
def _open_policy(c, direct_vm, direct_owner, passenger, risk_bps=2_000, flight="AA100"):
    direct_vm.sender = direct_owner
    return c.admin_open_policy(H(passenger), flight, FUTURE_DEPARTURE, risk_bps)


def test_purchase_escrows_premium_and_reserves_coverage(
    direct_vm, direct_deploy, direct_owner, direct_alice, direct_bob
):
    c = _deploy(direct_vm, direct_deploy, direct_owner)
    _fund_pool(c, direct_vm, direct_alice, 10_000 * GEN)

    pid = _open_policy(c, direct_vm, direct_owner, direct_bob, risk_bps=2_000)
    assert pid == 1

    p = c.get_policy(pid)
    assert p["status"] == "ACTIVE"
    # as_hex is EIP-55 checksummed (mixed case); compare case-insensitively.
    assert p["passenger"].lower() == H(direct_bob).lower()
    assert p["premium_paid"] == 260 * GEN
    assert p["max_payout"] == 1_000 * GEN

    stats = c.get_pool_stats()
    assert stats["total_assets"] == 10_260 * GEN          # premium escrowed
    assert stats["locked_coverage"] == 1_000 * GEN        # coverage reserved
    assert stats["available_liquidity"] == 9_260 * GEN


def test_duplicate_active_policy_rejected(
    direct_vm, direct_deploy, direct_owner, direct_alice, direct_bob
):
    c = _deploy(direct_vm, direct_deploy, direct_owner)
    _fund_pool(c, direct_vm, direct_alice, 10_000 * GEN)
    _open_policy(c, direct_vm, direct_owner, direct_bob)
    with direct_vm.expect_revert("ACTIVE policy already exists"):
        _open_policy(c, direct_vm, direct_owner, direct_bob)


def test_underwriting_blocked_without_liquidity(
    direct_vm, direct_deploy, direct_owner, direct_bob
):
    c = _deploy(direct_vm, direct_deploy, direct_owner)
    # No LP funds: premium alone cannot back the 1000 GEN coverage.
    with direct_vm.expect_revert("insufficient pool liquidity"):
        _open_policy(c, direct_vm, direct_owner, direct_bob)


def test_on_time_flight_expires_and_becomes_lp_yield(
    direct_vm, direct_deploy, direct_owner, direct_alice, direct_bob
):
    c = _deploy(direct_vm, direct_deploy, direct_owner)
    _fund_pool(c, direct_vm, direct_alice, 10_000 * GEN)
    pid = _open_policy(c, direct_vm, direct_owner, direct_bob)

    direct_vm.sender = direct_owner
    res = c.admin_resolve_policy(pid, 0, False)
    assert res["status"] == "EXPIRED"
    assert res["payout_amount"] == 0

    stats = c.get_pool_stats()
    assert stats["locked_coverage"] == 0                  # reservation released
    assert stats["total_yield_to_lps"] == 260 * GEN       # premium retained
    # Alice's shares are now worth the original deposit plus the premium yield.
    assert c.lp_position(H(direct_alice))["redeemable_value"] == 10_260 * GEN
    assert c.share_price_atto() > GEN


def test_delayed_flight_pays_passenger(
    direct_vm, direct_deploy, direct_owner, direct_alice, direct_bob
):
    c = _deploy(direct_vm, direct_deploy, direct_owner)
    _fund_pool(c, direct_vm, direct_alice, 10_000 * GEN)
    pid = _open_policy(c, direct_vm, direct_owner, direct_bob)

    direct_vm.sender = direct_owner
    res = c.admin_resolve_policy(pid, 180, False)         # 3h delay -> 50%
    assert res["status"] == "RESOLVED"
    assert res["payout_bps"] == 5_000
    assert res["payout_amount"] == 500 * GEN

    assert c.claimable_of(H(direct_bob)) == 500 * GEN
    stats = c.get_pool_stats()
    assert stats["locked_coverage"] == 0
    assert stats["total_payouts"] == 500 * GEN
    # Pool: 10000 + 260 premium - 500 payout = 9760.
    assert stats["total_assets"] == 9_760 * GEN


def test_cancelled_flight_pays_full(
    direct_vm, direct_deploy, direct_owner, direct_alice, direct_bob
):
    c = _deploy(direct_vm, direct_deploy, direct_owner)
    _fund_pool(c, direct_vm, direct_alice, 10_000 * GEN)
    pid = _open_policy(c, direct_vm, direct_owner, direct_bob)

    direct_vm.sender = direct_owner
    res = c.admin_resolve_policy(pid, 0, True)            # cancelled -> 100%
    assert res["payout_amount"] == 1_000 * GEN
    assert c.claimable_of(H(direct_bob)) == 1_000 * GEN


def test_double_resolve_is_blocked(
    direct_vm, direct_deploy, direct_owner, direct_alice, direct_bob
):
    c = _deploy(direct_vm, direct_deploy, direct_owner)
    _fund_pool(c, direct_vm, direct_alice, 10_000 * GEN)
    pid = _open_policy(c, direct_vm, direct_owner, direct_bob)

    direct_vm.sender = direct_owner
    c.admin_resolve_policy(pid, 300, False)               # full payout, RESOLVED
    with direct_vm.expect_revert("policy already resolved"):
        c.admin_resolve_policy(pid, 300, False)


def test_resolved_policy_slot_allows_new_purchase(
    direct_vm, direct_deploy, direct_owner, direct_alice, direct_bob
):
    c = _deploy(direct_vm, direct_deploy, direct_owner)
    _fund_pool(c, direct_vm, direct_alice, 10_000 * GEN)
    pid1 = _open_policy(c, direct_vm, direct_owner, direct_bob)
    direct_vm.sender = direct_owner
    c.admin_resolve_policy(pid1, 0, False)                # EXPIRED, frees the dedup slot
    # Same passenger + flight can be insured again now that the prior is closed.
    pid2 = _open_policy(c, direct_vm, direct_owner, direct_bob)
    assert pid2 == pid1 + 1


# --------------------------------------------------------------------------- #
# Solvency: reserved coverage cannot be withdrawn by LPs                       #
# --------------------------------------------------------------------------- #
def test_lp_cannot_withdraw_reserved_coverage(
    direct_vm, direct_deploy, direct_owner, direct_alice, direct_bob
):
    c = _deploy(direct_vm, direct_deploy, direct_owner)
    _fund_pool(c, direct_vm, direct_alice, 1_000 * GEN)   # exactly one policy's worth
    _open_policy(c, direct_vm, direct_owner, direct_bob)  # locks 1000 GEN coverage

    # Only ~260 GEN of premium is unreserved; a full exit must fail.
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("available"):
        c.withdraw_liquidity(1_000 * GEN)

    # A small redemption within the available band succeeds.
    credited = c.withdraw_liquidity(200 * GEN)
    assert credited > 0


# --------------------------------------------------------------------------- #
# check_flight_and_execute deterministic guards (revert before any web call)   #
# --------------------------------------------------------------------------- #
def test_resolve_unknown_policy_reverts(direct_vm, direct_deploy, direct_owner):
    c = _deploy(direct_vm, direct_deploy, direct_owner)
    with direct_vm.expect_revert("unknown policy_id"):
        c.check_flight_and_execute(999)


def test_resolve_before_departure_reverts(
    direct_vm, direct_deploy, direct_owner, direct_alice, direct_bob
):
    c = _deploy(direct_vm, direct_deploy, direct_owner)
    _fund_pool(c, direct_vm, direct_alice, 10_000 * GEN)
    pid = _open_policy(c, direct_vm, direct_owner, direct_bob)  # departs in 2030
    # Clock is 2025, so the flight has not departed: must revert before any fetch.
    with direct_vm.expect_revert("has not departed yet"):
        c.check_flight_and_execute(pid)


def test_resolve_inactive_policy_reverts(
    direct_vm, direct_deploy, direct_owner, direct_alice, direct_bob
):
    c = _deploy(direct_vm, direct_deploy, direct_owner)
    _fund_pool(c, direct_vm, direct_alice, 10_000 * GEN)
    pid = _open_policy(c, direct_vm, direct_owner, direct_bob)
    direct_vm.sender = direct_owner
    c.admin_resolve_policy(pid, 0, False)                 # now EXPIRED
    with direct_vm.expect_revert("not ACTIVE"):
        c.check_flight_and_execute(pid)


# --------------------------------------------------------------------------- #
# Access control / administration                                             #
# --------------------------------------------------------------------------- #
def test_only_owner_opens_fallback_policy(
    direct_vm, direct_deploy, direct_owner, direct_alice, direct_bob
):
    c = _deploy(direct_vm, direct_deploy, direct_owner)
    _fund_pool(c, direct_vm, direct_alice, 10_000 * GEN)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("not the owner"):
        c.admin_open_policy(H(direct_bob), "AA100", FUTURE_DEPARTURE, 2_000)


def test_only_owner_pauses(direct_vm, direct_deploy, direct_owner, direct_alice):
    c = _deploy(direct_vm, direct_deploy, direct_owner)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("not the owner"):
        c.set_paused(True)


def test_pause_blocks_deposits_but_allows_exit(
    direct_vm, direct_deploy, direct_owner, direct_alice
):
    c = _deploy(direct_vm, direct_deploy, direct_owner)
    _fund_pool(c, direct_vm, direct_alice, 10_000 * GEN)

    direct_vm.sender = direct_owner
    c.set_paused(True)

    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("contract is paused"):
        c.provide_liquidity(1_000 * GEN)

    # Exits remain open so LP funds are never trapped.
    assert c.withdraw_liquidity(1_000 * GEN) == 1_000 * GEN


def test_purchase_validates_inputs(direct_vm, direct_deploy, direct_owner, direct_alice):
    c = _deploy(direct_vm, direct_deploy, direct_owner)
    _fund_pool(c, direct_vm, direct_alice, 10_000 * GEN)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("flight_code is required"):
        c.purchase_policy("", FUTURE_DEPARTURE)
    with direct_vm.expect_revert("departure_timestamp must be positive"):
        c.purchase_policy("AA100", 0)


def test_transfer_ownership(direct_vm, direct_deploy, direct_owner, direct_alice):
    c = _deploy(direct_vm, direct_deploy, direct_owner)
    direct_vm.sender = direct_owner
    c.transfer_ownership(H(direct_alice))
    # Old owner can no longer administer.
    with direct_vm.expect_revert("not the owner"):
        c.set_paused(True)
    # New owner can.
    direct_vm.sender = direct_alice
    c.set_paused(True)
    assert c.get_pool_stats()["paused"] is True
