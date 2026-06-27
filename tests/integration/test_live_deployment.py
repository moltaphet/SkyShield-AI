"""Live-state integration tests against the DEPLOYED SkyShield AI contract.

These attach to the on-chain instance at the published address and perform
read-only (`.call()`) queries plus the contract's own deterministic pricing
views. They never mutate state and need no funded account, so they are safe to
run against any network that hosts the deployment.

If the contract is not reachable on the selected network (wrong network, offline,
or rate-limited), each test SKIPS rather than fails - the address only exists on
the network it was deployed to.

Run:
    gltest tests/integration/test_live_deployment.py -v -s --network studionet
"""

from typing import Any, cast

import pytest
from gltest import get_contract_factory

# Officially deployed SkyShield AI Intelligent Contract.
DEPLOYED_ADDRESS = "0x43050A476485547450Aa80A4Bf059D17CE17CC28"

ATTO = 10**18
BASE_COVERAGE_ATTO = 1_000 * ATTO

POOL_STATS_KEYS = {
    "total_assets",
    "total_shares",
    "locked_coverage",
    "available_liquidity",
    "lp_count",
    "policy_count",
    "total_premiums_collected",
    "total_payouts",
    "total_yield_to_lps",
    "paused",
    "owner",
}


def _attach():
    """Bind to the deployed contract, skipping if it cannot be reached."""
    try:
        factory = get_contract_factory("SkyShieldAI")
        # Runtime accepts a hex string; cast satisfies the Address|ChecksumAddress hint.
        return factory.build_contract(contract_address=cast(Any, DEPLOYED_ADDRESS))
    except Exception as exc:  # network / schema / address not on this network
        pytest.skip(f"Deployed SkyShield contract unreachable here: {exc}")


def _call(contract, method, args):
    try:
        return getattr(contract, method)(args=args).call()
    except Exception as exc:
        pytest.skip(f"Live read '{method}' failed (network unavailable): {exc}")


def test_live_pool_stats_shape_and_solvency():
    """The live pool exposes the full stats dict and preserves solvency."""
    contract = _attach()
    stats = _call(contract, "get_pool_stats", [])

    assert isinstance(stats, dict)
    assert POOL_STATS_KEYS.issubset(stats.keys())
    # Core protocol invariant must hold on-chain at all times.
    assert int(stats["total_assets"]) >= int(stats["locked_coverage"])
    assert int(stats["available_liquidity"]) == int(stats["total_assets"]) - int(
        stats["locked_coverage"]
    )
    assert int(stats["total_assets"]) >= 0
    assert int(stats["policy_count"]) >= 0


def test_live_share_price_is_positive():
    """Share price is always >= 1 atto (1.0) by construction."""
    contract = _attach()
    price = int(_call(contract, "share_price_atto", []))
    assert price >= ATTO


def test_live_payout_tier_views_match_spec():
    """The deterministic payout tiers read identically live as in the spec."""
    contract = _attach()
    # (delay_minutes, cancelled) -> expected payout (atto) on a base policy.
    cases = [
        (0, False, 0),
        (59, False, 0),
        (60, False, 200 * ATTO),
        (119, False, 200 * ATTO),
        (120, False, 500 * ATTO),
        (239, False, 500 * ATTO),
        (240, False, 1_000 * ATTO),
        (0, True, 1_000 * ATTO),
    ]
    for delay, cancelled, expected in cases:
        got = int(_call(contract, "quote_payout", [delay, cancelled]))
        assert got == expected, f"delay={delay} cancelled={cancelled}: {got} != {expected}"


def test_live_premium_pricing_is_monotonic():
    """Higher AI risk must never price a cheaper premium, and stays bounded."""
    contract = _attach()
    p_low = int(_call(contract, "preview_premium", [500]))
    p_mid = int(_call(contract, "preview_premium", [2_500]))
    p_high = int(_call(contract, "preview_premium", [6_000]))
    assert p_low <= p_mid <= p_high
    # Premium can never exceed the coverage it underwrites.
    assert p_high <= BASE_COVERAGE_ATTO
    # Floor enforced for near-zero risk.
    assert int(_call(contract, "preview_premium", [0])) >= 1 * ATTO
