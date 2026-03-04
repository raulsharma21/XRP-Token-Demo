"""
Fee Calculator - Pure Functions for NAV and Fee Calculations

Business rules:
- Management Fee: 2% annual (0.02 / 365 = 0.00005479 daily)
- Performance Fee: 20% on gains above fund-wide high water mark (HWM)
- Fees are withdrawn daily (no accrual)
- HWM is fund-wide, not per-investor
- NAV is always post-fee (what investors see)

Example scenarios from brief:
1. Balance=$105k, Tokens=100k, HWM=$1.00
   → Mgmt=$5.75, Perf=$1,000, Total=$1,005.75, NAV=$1.03994

2. Balance=$145k, Tokens=100k, HWM=$1.50
   → Mgmt=$7.95, Perf=$0, Total=$7.95, NAV=$1.44992
"""

from decimal import Decimal, ROUND_DOWN
from typing import Dict, Optional
from datetime import date


# ==================== CONSTANTS ====================

# Fee rates
MANAGEMENT_FEE_ANNUAL = Decimal('0.02')  # 2% per year
MANAGEMENT_FEE_DAILY = MANAGEMENT_FEE_ANNUAL / Decimal('365')  # 0.00005479...
PERFORMANCE_FEE_RATE = Decimal('0.20')  # 20%

# Precision for calculations
DECIMAL_PLACES = 8  # Balance and NAV precision
FEE_DECIMAL_PLACES = 2  # Fee amounts (USD cents)


# ==================== CORE FEE CALCULATION ====================

def calculate_daily_fees(
    trading_balance: Decimal,
    total_tokens_outstanding: Decimal,
    current_hwm: Decimal
) -> Dict[str, Decimal]:
    """
    Calculate daily management and performance fees

    Args:
        trading_balance: Current trading account balance (pre-fees)
        total_tokens_outstanding: Total IND tokens in circulation
        current_hwm: Current fund-wide high water mark

    Returns:
        Dict with:
            - nav_before_fees: NAV before any fees
            - management_fee_daily_rate: Daily rate used (0.00005479)
            - management_fee_amount: Management fee in USD
            - performance_fee_rate: Rate used (0.20)
            - performance_fee_amount: Performance fee in USD
            - performance_fee_basis: Gain per token above HWM (None if no perf fee)
            - total_fees: Total fees collected
            - trading_balance_post_fees: Balance after fees withdrawn
            - nav_per_token: Published NAV (post-fee)
            - new_hwm: New high water mark (may be unchanged)
            - hwm_increased: Whether HWM went up

    Raises:
        ValueError: If inputs are invalid (negative, zero tokens, etc.)
    """

    # Validation
    if trading_balance < 0:
        raise ValueError(f"Trading balance cannot be negative: {trading_balance}")
    if total_tokens_outstanding <= 0:
        raise ValueError(f"Tokens outstanding must be positive: {total_tokens_outstanding}")
    if current_hwm <= 0:
        raise ValueError(f"HWM must be positive: {current_hwm}")

    # Step 1: Calculate NAV before fees
    nav_before_fees = trading_balance / total_tokens_outstanding

    # Step 2: Calculate management fee (charged on balance, not NAV)
    management_fee_amount = trading_balance * MANAGEMENT_FEE_DAILY
    # Round to cents (normal rounding, not ROUND_DOWN)
    management_fee_amount = management_fee_amount.quantize(Decimal('0.01'))

    # Step 3: Calculate performance fee (only if NAV > HWM)
    performance_fee_amount = Decimal('0')
    performance_fee_basis = None

    if nav_before_fees > current_hwm:
        # Gain per token above HWM
        gain_per_token = nav_before_fees - current_hwm
        performance_fee_basis = gain_per_token

        # Total performance fee: tokens × gain × 20%
        performance_fee_amount = total_tokens_outstanding * gain_per_token * PERFORMANCE_FEE_RATE

        # Round to cents (normal rounding)
        performance_fee_amount = performance_fee_amount.quantize(Decimal('0.01'))

    # Step 4: Total fees
    total_fees = management_fee_amount + performance_fee_amount

    # Step 5: Calculate post-fee state
    trading_balance_post_fees = trading_balance - total_fees
    nav_per_token = trading_balance_post_fees / total_tokens_outstanding

    # Step 6: Determine new HWM
    # HWM only increases if post-fee NAV exceeds current HWM
    if nav_per_token > current_hwm:
        new_hwm = nav_per_token
        hwm_increased = True
    else:
        new_hwm = current_hwm
        hwm_increased = False

    return {
        # Pre-fee state
        'nav_before_fees': nav_before_fees,
        'fund_hwm_before': current_hwm,

        # Fee calculations
        'management_fee_daily_rate': MANAGEMENT_FEE_DAILY,
        'management_fee_amount': management_fee_amount,
        'performance_fee_rate': PERFORMANCE_FEE_RATE,
        'performance_fee_amount': performance_fee_amount,
        'performance_fee_basis': performance_fee_basis,
        'total_fees_collected': total_fees,

        # Post-fee state
        'trading_balance_post_fees': trading_balance_post_fees,
        'nav_per_token': nav_per_token,

        # HWM tracking
        'fund_hwm_after': new_hwm,
        'hwm_increased': hwm_increased,
    }


# ==================== SUBSCRIPTION PRICING ====================

def calculate_subscription_tokens(
    usdc_amount: Decimal,
    current_nav: Decimal
) -> Decimal:
    """
    Calculate how many tokens to issue for a subscription

    During IPO: NAV = $1.00 (fixed)
    Post-IPO: NAV = latest calculated NAV

    Args:
        usdc_amount: Amount of USDC invested
        current_nav: Current NAV per token

    Returns:
        Decimal: Number of tokens to issue

    Example:
        $1,000 USDC at $1.04 NAV → 961.54 tokens
    """
    if usdc_amount <= 0:
        raise ValueError(f"USDC amount must be positive: {usdc_amount}")
    if current_nav <= 0:
        raise ValueError(f"NAV must be positive: {current_nav}")

    tokens = usdc_amount / current_nav

    # Round to 8 decimal places
    return tokens.quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)


# ==================== REDEMPTION PRICING ====================

def calculate_redemption_value(
    token_amount: Decimal,
    current_nav: Decimal
) -> Decimal:
    """
    Calculate USDC value for a redemption

    Args:
        token_amount: Number of tokens being redeemed
        current_nav: Current NAV per token

    Returns:
        Decimal: USDC amount owed to investor

    Example:
        500 tokens at $1.04 NAV → $520.00 USDC
    """
    if token_amount <= 0:
        raise ValueError(f"Token amount must be positive: {token_amount}")
    if current_nav <= 0:
        raise ValueError(f"NAV must be positive: {current_nav}")

    usdc_value = token_amount * current_nav

    # Round to cents
    return usdc_value.quantize(Decimal('0.01'), rounding=ROUND_DOWN)


# ==================== HELPER FUNCTIONS ====================

def format_fee_summary(fee_result: Dict[str, Decimal]) -> str:
    """
    Format fee calculation result as human-readable string

    Args:
        fee_result: Result from calculate_daily_fees()

    Returns:
        Formatted summary string
    """
    lines = [
        "=" * 60,
        "Daily Fee Calculation Summary",
        "=" * 60,
        "",
        "PRE-FEE STATE:",
        f"  NAV before fees: ${fee_result['nav_before_fees']:.8f}",
        f"  Fund HWM: ${fee_result['fund_hwm_before']:.2f}",
        "",
        "FEES COLLECTED:",
        f"  Management fee (daily): ${fee_result['management_fee_amount']:.2f}",
        f"  Performance fee (20%): ${fee_result['performance_fee_amount']:.2f}",
    ]

    if fee_result['performance_fee_basis']:
        lines.append(f"    (Gain above HWM: ${fee_result['performance_fee_basis']:.8f} per token)")

    lines.extend([
        f"  Total fees: ${fee_result['total_fees_collected']:.2f}",
        "",
        "POST-FEE STATE:",
        f"  Balance after fees: ${fee_result['trading_balance_post_fees']:.2f}",
        f"  NAV per token: ${fee_result['nav_per_token']:.8f}",
        f"  New HWM: ${fee_result['fund_hwm_after']:.8f}",
    ])

    if fee_result['hwm_increased']:
        lines.append(f"  ✓ HWM increased")
    else:
        lines.append(f"  - HWM unchanged")

    lines.append("=" * 60)

    return "\n".join(lines)


# ==================== TESTING SCENARIOS ====================

def test_scenario_1():
    """
    Test Scenario 1 from brief: Performance fee charged

    Balance: $105,000
    Tokens: 100,000
    HWM: $1.00

    Expected:
    - NAV before fees: $1.05
    - Management fee: $5.75
    - Performance fee: $1,000.00
    - Total fees: $1,005.75
    - NAV after fees: $1.03994
    - New HWM: $1.03994
    """
    print("\nTest Scenario 1: Performance Fee Charged")
    print("-" * 60)

    result = calculate_daily_fees(
        trading_balance=Decimal('105000'),
        total_tokens_outstanding=Decimal('100000'),
        current_hwm=Decimal('1.00')
    )

    print(format_fee_summary(result))

    # Verify against expected values
    assert result['management_fee_amount'] == Decimal('5.75'), \
        f"Management fee mismatch: {result['management_fee_amount']} != 5.75"

    assert result['performance_fee_amount'] == Decimal('1000.00'), \
        f"Performance fee mismatch: {result['performance_fee_amount']} != 1000.00"

    assert result['total_fees_collected'] == Decimal('1005.75'), \
        f"Total fees mismatch: {result['total_fees_collected']} != 1005.75"

    # NAV calculation: (105000 - 1005.75) / 100000 = 103994.25 / 100000 = 1.0399425
    expected_nav = Decimal('103994.25') / Decimal('100000')
    assert result['nav_per_token'] == expected_nav, \
        f"NAV mismatch: {result['nav_per_token']} != {expected_nav}"

    assert result['fund_hwm_after'] == expected_nav, \
        f"New HWM mismatch: {result['fund_hwm_after']} != {expected_nav}"

    assert result['hwm_increased'] is True, "HWM should have increased"

    print("\n✓ Scenario 1 PASSED - All values match expected results")


def test_scenario_2():
    """
    Test Scenario 2 from brief: No performance fee (below HWM)

    Balance: $145,000
    Tokens: 100,000
    HWM: $1.50

    Expected:
    - NAV before fees: $1.45
    - Management fee: $7.95
    - Performance fee: $0
    - Total fees: $7.95
    - NAV after fees: $1.44992
    - New HWM: $1.50 (unchanged)
    """
    print("\nTest Scenario 2: No Performance Fee (Below HWM)")
    print("-" * 60)

    result = calculate_daily_fees(
        trading_balance=Decimal('145000'),
        total_tokens_outstanding=Decimal('100000'),
        current_hwm=Decimal('1.50')
    )

    print(format_fee_summary(result))

    # Verify against expected values
    assert result['management_fee_amount'] == Decimal('7.95'), \
        f"Management fee mismatch: {result['management_fee_amount']} != 7.95"

    assert result['performance_fee_amount'] == Decimal('0'), \
        f"Performance fee mismatch: {result['performance_fee_amount']} != 0"

    assert result['total_fees_collected'] == Decimal('7.95'), \
        f"Total fees mismatch: {result['total_fees_collected']} != 7.95"

    # NAV calculation: (145000 - 7.95) / 100000 = 144992.05 / 100000 = 1.4499205
    expected_nav = Decimal('144992.05') / Decimal('100000')
    assert result['nav_per_token'] == expected_nav, \
        f"NAV mismatch: {result['nav_per_token']} != {expected_nav}"

    assert result['fund_hwm_after'] == Decimal('1.50'), \
        f"HWM should remain at 1.50, got {result['fund_hwm_after']}"

    assert result['hwm_increased'] is False, "HWM should not have increased"

    print("\n✓ Scenario 2 PASSED - All values match expected results")


def test_subscription_and_redemption():
    """Test subscription and redemption pricing"""
    print("\nTest Subscription and Redemption Pricing")
    print("-" * 60)

    # Test subscription
    nav = Decimal('1.03994')
    usdc = Decimal('1000')
    tokens = calculate_subscription_tokens(usdc, nav)
    expected_tokens = usdc / nav

    print(f"\nSubscription Test:")
    print(f"  USDC invested: ${usdc}")
    print(f"  NAV: ${nav}")
    print(f"  Tokens issued: {tokens}")
    print(f"  Expected: {expected_tokens}")

    assert tokens == expected_tokens.quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)
    print("  ✓ Subscription calculation correct")

    # Test redemption
    redeem_tokens = Decimal('500')
    usdc_owed = calculate_redemption_value(redeem_tokens, nav)
    expected_usdc = (redeem_tokens * nav).quantize(Decimal('0.01'), rounding=ROUND_DOWN)

    print(f"\nRedemption Test:")
    print(f"  Tokens redeemed: {redeem_tokens}")
    print(f"  NAV: ${nav}")
    print(f"  USDC owed: ${usdc_owed}")
    print(f"  Expected: ${expected_usdc}")

    assert usdc_owed == expected_usdc
    print("  ✓ Redemption calculation correct")


# ==================== MAIN ====================

if __name__ == "__main__":
    """Run all test scenarios"""
    print("\n" + "=" * 60)
    print("FEE CALCULATOR - TEST SUITE")
    print("=" * 60)

    try:
        test_scenario_1()
        test_scenario_2()
        test_subscription_and_redemption()

        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
        print("\nFee calculation module is working correctly!")
        print("All values match the specifications from the brief.\n")

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}\n")
        raise
    except Exception as e:
        print(f"\n✗ ERROR: {e}\n")
        raise
