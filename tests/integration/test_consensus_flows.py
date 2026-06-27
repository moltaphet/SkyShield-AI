# pyright: reportAttributeAccessIssue=false
"""Consensus integration tests for SkyShield AI.

These deploy a FRESH instance on the selected network and exercise the
deterministic economic lifecycle end-to-end under full leader + validator
consensus (every write goes through `.transact()` and must report success).

They cover the same money paths as the deployed contract without depending on
its live state, so they are reproducible on studionet / localnet / GLSim.

Run:
    gltest tests/integration/test_consensus_flows.py -v -s --network studionet
"""

from gltest import create_account, get_contract_factory
from gltest.assertions import tx_execution_failed, tx_execution_succeeded

ATTO = 10**18
BASE_COVERAGE_ATTO = 1_000 * ATTO
# Far-future departure (2030-01-01) so resolution-time guards are satisfied
# only via the owner fallback, never accidentally by the autonomous path.
FUTURE_DEPARTURE = 1_893_456_000


def _deploy():
    factory = get_contract_factory("SkyShieldAI")
    return factory.deploy(args=[])


def _fund(contract, amount_atto):
    receipt = contract.provide_liquidity(args=[amount_atto]).transact()
    assert tx_execution_succeeded(receipt)


def test_liquidity_provision_under_consensus():
    contract = _deploy()
    _fund(contract, 10_000 * ATTO)

    stats = contract.get_pool_stats(args=[]).call()
    assert int(stats["total_assets"]) == 10_000 * ATTO
    assert int(stats["total_shares"]) == 10_000 * ATTO
    assert int(stats["available_liquidity"]) == 10_000 * ATTO


def test_policy_lifecycle_delayed_payout_under_consensus():
    contract = _deploy()
    _fund(contract, 10_000 * ATTO)
    passenger = create_account()

    opened = contract.admin_open_policy(
        args=[passenger.address, "BA245", FUTURE_DEPARTURE, 2_000]
    ).transact()
    assert tx_execution_succeeded(opened)

    policy = contract.get_policy(args=[1]).call()
    assert policy["status"] == "ACTIVE"
    assert int(policy["max_payout"]) == BASE_COVERAGE_ATTO
    assert int(policy["premium_paid"]) == 260 * ATTO  # risk 20% + 30% loading

    # 3h delay -> 50% tier.
    resolved = contract.admin_resolve_policy(args=[1, 180, False]).transact()
    assert tx_execution_succeeded(resolved)

    policy = contract.get_policy(args=[1]).call()
    assert policy["status"] == "RESOLVED"
    assert int(policy["payout_amount"]) == 500 * ATTO
    assert int(contract.claimable_of(args=[passenger.address]).call()) == 500 * ATTO


def test_all_payout_tiers_under_consensus():
    contract = _deploy()
    _fund(contract, 20_000 * ATTO)
    passenger = create_account()

    # (flight, delay_minutes, cancelled) -> expected payout (atto).
    scenarios = [
        ("AA100", 0, False, 0),            # on time   -> EXPIRED
        ("AA200", 75, False, 200 * ATTO),  # 1h-2h     -> 20%
        ("AA300", 150, False, 500 * ATTO), # 2h-4h     -> 50%
        ("AA400", 300, False, 1_000 * ATTO),  # >4h    -> 100%
        ("AA500", 0, True, 1_000 * ATTO),  # cancelled -> 100%
    ]
    for i, (flight, delay, cancelled, expected) in enumerate(scenarios, start=1):
        opened = contract.admin_open_policy(
            args=[passenger.address, flight, FUTURE_DEPARTURE, 3_000]
        ).transact()
        assert tx_execution_succeeded(opened)
        resolved = contract.admin_resolve_policy(args=[i, delay, cancelled]).transact()
        assert tx_execution_succeeded(resolved)

        policy = contract.get_policy(args=[i]).call()
        assert int(policy["payout_amount"]) == expected
        assert policy["status"] == ("EXPIRED" if expected == 0 else "RESOLVED")


def test_duplicate_active_policy_rejected_under_consensus():
    contract = _deploy()
    _fund(contract, 10_000 * ATTO)
    passenger = create_account()

    first = contract.admin_open_policy(
        args=[passenger.address, "BA245", FUTURE_DEPARTURE, 2_000]
    ).transact()
    assert tx_execution_succeeded(first)

    # Same passenger + flight + departure while ACTIVE must be rejected.
    dup = contract.admin_open_policy(
        args=[passenger.address, "BA245", FUTURE_DEPARTURE, 2_000]
    ).transact()
    assert tx_execution_failed(dup)


def test_underwriting_blocked_without_liquidity_under_consensus():
    contract = _deploy()  # no liquidity provided
    passenger = create_account()
    blocked = contract.admin_open_policy(
        args=[passenger.address, "BA245", FUTURE_DEPARTURE, 2_000]
    ).transact()
    assert tx_execution_failed(blocked)
