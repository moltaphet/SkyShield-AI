# pyright: reportAttributeAccessIssue=false
"""Non-deterministic integration tests (real AI + web) for SkyShield AI.

These exercise the two methods that rely on GenLayer's native capabilities and
must therefore reach a real LLM (and, for resolution, a real aviation API):

  * purchase_policy           -> AI-priced premium, validated under consensus.
  * check_flight_and_execute  -> live flight fetch + LLM parse -> payout tier.

They are marked `slow` (excluded from the default run) and skip gracefully when
the model/API is unavailable, so they never produce a flaky hard failure.

Run:
    gltest tests/integration/test_nondeterministic.py -v -s -m slow --network studionet
"""

import pytest
from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded

ATTO = 10**18
BASE_COVERAGE_ATTO = 1_000 * ATTO
FUTURE_DEPARTURE = 1_893_456_000  # 2030-01-01
PAST_DEPARTURE = 1_577_836_800    # 2020-01-01 (already departed)


def _deploy():
    factory = get_contract_factory("SkyShieldAI")
    return factory.deploy(args=[])


@pytest.mark.slow
def test_purchase_policy_ai_pricing_under_consensus():
    """The AI underwriting model prices a premium that validators agree on."""
    contract = _deploy()
    assert tx_execution_succeeded(contract.provide_liquidity(args=[50_000 * ATTO]).transact())

    try:
        receipt = contract.purchase_policy(args=["BA245", FUTURE_DEPARTURE]).transact()
    except Exception as exc:
        pytest.skip(f"LLM underwriting unavailable on this network: {exc}")

    assert tx_execution_succeeded(receipt)

    policy = contract.get_policy(args=[1]).call()
    assert policy["status"] == "ACTIVE"
    # The committed premium must be sane: positive, bounded by coverage.
    assert 0 < int(policy["premium_paid"]) <= int(policy["max_payout"])
    assert int(policy["max_payout"]) == BASE_COVERAGE_ATTO
    assert 0 <= int(policy["risk_bps"]) <= 10_000


@pytest.mark.slow
def test_check_flight_and_execute_resolves_under_consensus():
    """The autonomous resolver fetches live status and settles to a payout tier.

    Requires a reachable aviation API (configure AVIATION_API_BASE / key in the
    contract for a real run). Skips if the external call cannot complete.
    """
    contract = _deploy()
    assert tx_execution_succeeded(contract.provide_liquidity(args=[50_000 * ATTO]).transact())

    # Open via the owner fallback with a past departure so resolution is allowed.
    from gltest import create_account

    passenger = create_account()
    assert tx_execution_succeeded(
        contract.admin_open_policy(
            args=[passenger.address, "BA245", PAST_DEPARTURE, 2_000]
        ).transact()
    )

    try:
        receipt = contract.check_flight_and_execute(args=[1]).transact()
    except Exception as exc:
        pytest.skip(f"Live flight resolution unavailable on this network: {exc}")

    assert tx_execution_succeeded(receipt)
    policy = contract.get_policy(args=[1]).call()
    # However the flight resolved, the policy must no longer be ACTIVE and the
    # payout must be a valid tier of the coverage.
    assert policy["status"] in ("RESOLVED", "EXPIRED")
    assert int(policy["payout_amount"]) in (
        0,
        200 * ATTO,
        500 * ATTO,
        1_000 * ATTO,
    )
