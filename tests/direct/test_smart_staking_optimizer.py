"""Direct-mode tests for the GenVault SmartStakingOptimizer contract.

Run with:  pytest tests/direct/ -v

These tests run in-memory (no server) and exercise business logic, state
transitions, access control and the timestamp-driven yield math. Time is
advanced with the ``direct_vm.warp`` cheatcode so accrual is deterministic.
"""

CONTRACT = "contracts/smart_staking_optimizer.py"

TOKEN = 10**18          # 1 token in atto scale
APY_BPS = 1000          # 10.00% annual
ONE_YEAR = 31_536_000   # seconds


def H(addr) -> str:
    """Render a test address (raw bytes) as a 0x-hex string for contract calls."""
    return "0x" + (addr if isinstance(addr, (bytes, bytearray)) else addr.as_bytes).hex()


def _deploy(direct_vm, direct_deploy, direct_owner, apy_bps=APY_BPS):
    direct_vm.sender = direct_owner
    direct_vm.warp("2025-01-01T00:00:00Z")
    # stake() now runs a consensus-backed AI risk screen (gl.nondet.exec_prompt
    # via gl.vm.run_nondet_unsafe). Direct mode has no real model, so register a
    # default low-risk (band 0) response; tests that need a different verdict can
    # override with their own direct_vm.mock_llm(...).
    direct_vm.mock_llm(
        r"DeFi staking risk model",
        '{"risk_bps": 500, "rationale": "normal deposit at a sane APY"}',
    )
    return direct_deploy(CONTRACT, initial_apy_bps=apy_bps)


# --------------------------------------------------------------------------- #
# Staking                                                                     #
# --------------------------------------------------------------------------- #
def test_stake_records_principal(direct_vm, direct_deploy, direct_owner, direct_alice):
    contract = _deploy(direct_vm, direct_deploy, direct_owner)

    direct_vm.sender = direct_alice
    contract.stake(100 * TOKEN)

    assert contract.balance_of(H(direct_alice)) == 100 * TOKEN
    stats = contract.get_stats()
    assert stats["total_staked"] == 100 * TOKEN
    assert stats["staker_count"] == 1


def test_stake_rejects_non_positive(direct_vm, direct_deploy, direct_owner, direct_alice):
    contract = _deploy(direct_vm, direct_deploy, direct_owner)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("stake amount must be positive"):
        contract.stake(0)


def test_second_stake_compounds_then_adds(direct_vm, direct_deploy, direct_owner, direct_alice):
    contract = _deploy(direct_vm, direct_deploy, direct_owner)
    direct_vm.sender = direct_alice
    contract.stake(100 * TOKEN)

    # Let a full year of yield accrue, then stake again.
    direct_vm.warp("2026-01-01T00:00:00Z")
    contract.stake(100 * TOKEN)

    # 100 + 10 (yield) + 100 = 210 tokens principal.
    assert contract.balance_of(H(direct_alice)) == 210 * TOKEN


# --------------------------------------------------------------------------- #
# Yield + compounding                                                         #
# --------------------------------------------------------------------------- #
def test_preview_pending_after_one_year(direct_vm, direct_deploy, direct_owner, direct_alice):
    contract = _deploy(direct_vm, direct_deploy, direct_owner)
    direct_vm.sender = direct_alice
    contract.stake(100 * TOKEN)

    direct_vm.warp("2026-01-01T00:00:00Z")
    # 10% of 100 tokens = 10 tokens.
    assert contract.preview_pending(H(direct_alice)) == 10 * TOKEN
    # Principal unchanged until compounded; total balance includes pending.
    assert contract.balance_of(H(direct_alice)) == 100 * TOKEN
    assert contract.total_balance_of(H(direct_alice)) == 110 * TOKEN


def test_compound_rewards_restakes_yield(direct_vm, direct_deploy, direct_owner, direct_alice):
    contract = _deploy(direct_vm, direct_deploy, direct_owner)
    direct_vm.sender = direct_alice
    contract.stake(100 * TOKEN)

    direct_vm.warp("2026-01-01T00:00:00Z")
    compounded = contract.compound_rewards()

    assert compounded == 10 * TOKEN
    assert contract.balance_of(H(direct_alice)) == 110 * TOKEN
    assert contract.preview_pending(H(direct_alice)) == 0
    acct = contract.get_account(H(direct_alice))
    assert acct["total_compounded"] == 10 * TOKEN


def test_compounding_is_exponential(direct_vm, direct_deploy, direct_owner, direct_alice):
    contract = _deploy(direct_vm, direct_deploy, direct_owner)
    direct_vm.sender = direct_alice
    contract.stake(100 * TOKEN)

    # Year 1: 100 -> 110
    direct_vm.warp("2026-01-01T00:00:00Z")
    contract.compound_rewards()
    # Year 2 yield is computed on 110, not 100 -> 11 tokens.
    direct_vm.warp("2027-01-01T00:00:00Z")
    assert contract.preview_pending(H(direct_alice)) == 11 * TOKEN


def test_compound_for_is_permissionless(direct_vm, direct_deploy, direct_owner, direct_alice, direct_bob):
    contract = _deploy(direct_vm, direct_deploy, direct_owner)
    direct_vm.sender = direct_alice
    contract.stake(100 * TOKEN)

    direct_vm.warp("2026-01-01T00:00:00Z")
    # A keeper (bob) compounds alice's position; funds stay with alice.
    direct_vm.sender = direct_bob
    compounded = contract.compound_for(H(direct_alice))
    assert compounded == 10 * TOKEN
    assert contract.balance_of(H(direct_alice)) == 110 * TOKEN


# --------------------------------------------------------------------------- #
# Withdrawals                                                                  #
# --------------------------------------------------------------------------- #
def test_partial_withdraw(direct_vm, direct_deploy, direct_owner, direct_alice):
    contract = _deploy(direct_vm, direct_deploy, direct_owner)
    direct_vm.sender = direct_alice
    contract.stake(100 * TOKEN)

    direct_vm.warp("2026-01-01T00:00:00Z")
    # Settles to 110, then withdraws 40 -> 70 remains.
    withdrawn = contract.withdraw(40 * TOKEN)
    assert withdrawn == 40 * TOKEN
    assert contract.balance_of(H(direct_alice)) == 70 * TOKEN


def test_withdraw_more_than_balance_reverts(direct_vm, direct_deploy, direct_owner, direct_alice):
    contract = _deploy(direct_vm, direct_deploy, direct_owner)
    direct_vm.sender = direct_alice
    contract.stake(100 * TOKEN)
    with direct_vm.expect_revert("insufficient staked balance"):
        contract.withdraw(1000 * TOKEN)


def test_withdraw_max_empties_position(direct_vm, direct_deploy, direct_owner, direct_alice):
    contract = _deploy(direct_vm, direct_deploy, direct_owner)
    direct_vm.sender = direct_alice
    contract.stake(100 * TOKEN)

    direct_vm.warp("2026-01-01T00:00:00Z")
    total = contract.withdraw_max()
    assert total == 110 * TOKEN
    assert contract.balance_of(H(direct_alice)) == 0
    assert contract.get_stats()["total_staked"] == 0


def test_withdraw_without_stake_reverts(direct_vm, direct_deploy, direct_owner, direct_bob):
    contract = _deploy(direct_vm, direct_deploy, direct_owner)
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("no stake found"):
        contract.withdraw(1)


# --------------------------------------------------------------------------- #
# Administration / access control                                             #
# --------------------------------------------------------------------------- #
def test_only_owner_sets_apy(direct_vm, direct_deploy, direct_owner, direct_alice):
    contract = _deploy(direct_vm, direct_deploy, direct_owner)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("not the owner"):
        contract.set_apy(2000)

    direct_vm.sender = direct_owner
    contract.set_apy(2000)
    assert contract.get_apy() == 2000


def test_pause_blocks_staking_but_allows_withdraw(direct_vm, direct_deploy, direct_owner, direct_alice):
    contract = _deploy(direct_vm, direct_deploy, direct_owner)
    direct_vm.sender = direct_alice
    contract.stake(100 * TOKEN)

    direct_vm.sender = direct_owner
    contract.set_paused(True)

    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("contract is paused"):
        contract.stake(10 * TOKEN)

    # Withdrawals remain available so funds are never trapped.
    assert contract.withdraw_max() == 100 * TOKEN


# --------------------------------------------------------------------------- #
# Consensus-backed AI / live-market paths (non-deterministic)                 #
# --------------------------------------------------------------------------- #
def test_stake_rejected_when_ai_flags_extreme_risk(
    direct_vm, direct_deploy, direct_owner, direct_alice
):
    contract = _deploy(direct_vm, direct_deploy, direct_owner)
    # Override the default low-risk screen with an EXTREME (band 3) verdict.
    direct_vm.clear_mocks()
    direct_vm.mock_llm(
        r"DeFi staking risk model",
        '{"risk_bps": 9000, "rationale": "implausible APY, exploit-shaped"}',
    )
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("AI risk screen flagged extreme risk"):
        contract.stake(100 * TOKEN)
    # Nothing was persisted: the gate sits above all storage mutation.
    assert contract.balance_of(H(direct_alice)) == 0


def test_ai_validator_agrees_on_same_risk_band(
    direct_vm, direct_deploy, direct_owner, direct_alice
):
    contract = _deploy(direct_vm, direct_deploy, direct_owner)
    direct_vm.sender = direct_alice
    contract.stake(100 * TOKEN)
    # Leader scored band 0 (risk_bps 500). A validator that independently scores
    # a different-but-same-band value (risk_bps 900) must still agree.
    assert direct_vm.run_validator(leader_result={"risk_bps": 900}) is True
    # A validator landing in a different band (band 2) disagrees.
    assert direct_vm.run_validator(leader_result={"risk_bps": 5000}) is False


def test_update_apy_from_market_sets_live_rate(
    direct_vm, direct_deploy, direct_owner
):
    contract = _deploy(direct_vm, direct_deploy, direct_owner)
    # DeFiLlama chart shape: oldest-to-newest samples; last carries live APY (%).
    direct_vm.mock_web(
        r"yields\.llama\.fi/chart",
        {
            "status": 200,
            "body": '{"status":"success","data":['
            '{"timestamp":"2025-01-01","apy":3.10},'
            '{"timestamp":"2025-01-02","apy":4.25}]}',
        },
    )
    direct_vm.sender = direct_owner
    new_apy = contract.update_apy_from_market()
    assert new_apy == 425                       # 4.25% -> 425 bps
    assert contract.get_apy() == 425


def test_update_apy_from_market_is_owner_only(
    direct_vm, direct_deploy, direct_owner, direct_alice
):
    contract = _deploy(direct_vm, direct_deploy, direct_owner)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("not the owner"):
        contract.update_apy_from_market()
