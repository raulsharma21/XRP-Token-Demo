"""
NAV Calculator - Daily NAV Calculation Orchestration

This module orchestrates the daily NAV calculation process:
1. Get trading account balance
2. Get total tokens outstanding
3. Calculate fees (management + performance)
4. Withdraw fees from trading account
5. Save fund_state to database
6. Update system HWM

Usage:
    from nav_calculator import calculate_and_save_nav

    result = await calculate_and_save_nav()
    print(f"NAV calculated: ${result['nav_per_token']}")
"""

from decimal import Decimal
from datetime import date, datetime
from typing import Dict, Optional
import asyncio

# Import our modules
from database import (
    init_database, close_database,
    FundStateDB, SystemConfigDB, StatsDB
)
from trading_account import get_trading_client, ManualBalanceClient
from fee_calculator import calculate_daily_fees
from xrpl_utils import wallet_manager


# ==================== HELPER FUNCTIONS ====================

async def get_total_tokens_outstanding() -> Decimal:
    """
    Get total IND tokens in circulation

    Sums up all completed purchases (tokens issued)

    Returns:
        Decimal: Total tokens outstanding
    """
    total = await StatsDB.get_total_tokens_issued()
    return Decimal(str(total))


async def get_creator_wallet_address() -> str:
    """
    Get creator wallet address for fee destination

    Returns:
        str: XRPL address of creator wallet
    """
    # In your setup, the cold wallet is the issuer (creator)
    return wallet_manager.cold_wallet.address


# ==================== MAIN NAV CALCULATION ====================

async def calculate_and_save_nav(
    calculation_date: Optional[date] = None,
    notes: Optional[str] = None
) -> Dict:
    """
    Calculate daily NAV and save to database

    This is the main orchestration function that:
    1. Gets trading balance from trading account client
    2. Gets total tokens outstanding from database
    3. Gets current fund HWM
    4. Calculates fees using fee_calculator
    5. Withdraws fees from trading account (simulated)
    6. Saves fund_state record to database
    7. Updates system config HWM

    Args:
        calculation_date: Date for this calculation (defaults to today)
        notes: Optional notes to save with calculation

    Returns:
        Dict with calculation results and metadata

    Raises:
        ValueError: If calculation fails validation
        Exception: If database or trading account operations fail
    """

    if calculation_date is None:
        calculation_date = date.today()

    print(f"\n{'='*60}")
    print(f"NAV CALCULATION - {calculation_date}")
    print(f"{'='*60}")

    # Step 1: Get trading account balance
    print("\n1. Getting trading account balance...")
    trading_client = await get_trading_client("manual")
    trading_balance = await trading_client.get_balance()
    print(f"   Trading balance: ${trading_balance:,.2f}")

    # Step 2: Get total tokens outstanding
    print("\n2. Getting total tokens outstanding...")
    total_tokens = await get_total_tokens_outstanding()
    print(f"   Total tokens: {total_tokens:,.2f}")

    # Validation
    if total_tokens == 0:
        raise ValueError("Cannot calculate NAV: No tokens outstanding")

    # Step 3: Get current fund HWM
    print("\n3. Getting current fund HWM...")
    current_hwm = await FundStateDB.get_current_hwm()
    print(f"   Current HWM: ${current_hwm:.8f}")

    # Step 4: Calculate fees
    print("\n4. Calculating fees...")
    fee_result = calculate_daily_fees(
        trading_balance=trading_balance,
        total_tokens_outstanding=total_tokens,
        current_hwm=current_hwm
    )

    print(f"   NAV before fees: ${fee_result['nav_before_fees']:.8f}")
    print(f"   Management fee: ${fee_result['management_fee_amount']:,.2f}")
    print(f"   Performance fee: ${fee_result['performance_fee_amount']:,.2f}")
    print(f"   Total fees: ${fee_result['total_fees_collected']:,.2f}")
    print(f"   NAV after fees: ${fee_result['nav_per_token']:.8f}")

    if fee_result['hwm_increased']:
        print(f"   ✓ HWM increased: ${fee_result['fund_hwm_after']:.8f}")
    else:
        print(f"   - HWM unchanged: ${fee_result['fund_hwm_after']:.8f}")

    # Step 5: Withdraw fees from trading account
    print("\n5. Withdrawing fees from trading account...")

    if fee_result['total_fees_collected'] > 0:
        creator_address = await get_creator_wallet_address()

        withdrawal_result = await trading_client.withdraw_fees(
            amount=fee_result['total_fees_collected'],
            destination=creator_address,
            reason=f"daily_fees_{calculation_date}"
        )

        if not withdrawal_result['success']:
            raise Exception(f"Fee withdrawal failed: {withdrawal_result.get('error')}")

        fee_tx_hash = withdrawal_result['tx_hash']
        print(f"   ✓ Fees withdrawn: ${fee_result['total_fees_collected']:,.2f}")
        print(f"   TX: {fee_tx_hash}")
    else:
        fee_tx_hash = None
        print(f"   - No fees to withdraw")

    # Step 6: Save fund_state to database
    print("\n6. Saving fund state to database...")

    fund_state_record = await FundStateDB.create(
        calculation_date=calculation_date,
        trading_balance_pre_fees=trading_balance,
        total_tokens_outstanding=total_tokens,
        nav_before_fees=fee_result['nav_before_fees'],
        fund_hwm_before=fee_result['fund_hwm_before'],
        management_fee_daily_rate=fee_result['management_fee_daily_rate'],
        management_fee_amount=fee_result['management_fee_amount'],
        performance_fee_rate=fee_result['performance_fee_rate'],
        performance_fee_amount=fee_result['performance_fee_amount'],
        performance_fee_basis=fee_result['performance_fee_basis'],
        total_fees_collected=fee_result['total_fees_collected'],
        trading_balance_post_fees=fee_result['trading_balance_post_fees'],
        nav_per_token=fee_result['nav_per_token'],
        fund_hwm_after=fee_result['fund_hwm_after'],
        hwm_increased=fee_result['hwm_increased'],
        fee_withdrawal_tx_hash=fee_tx_hash,
        notes=notes
    )

    print(f"   ✓ Fund state saved (ID: {fund_state_record['id']})")

    # Step 7: Update system config HWM if it increased
    if fee_result['hwm_increased']:
        print("\n7. Updating system config HWM...")
        await SystemConfigDB.set('fund_hwm', str(fee_result['fund_hwm_after']))
        print(f"   ✓ HWM updated to ${fee_result['fund_hwm_after']:.8f}")
    else:
        print("\n7. HWM unchanged, no update needed")

    # Done!
    print(f"\n{'='*60}")
    print(f"✓ NAV CALCULATION COMPLETE")
    print(f"{'='*60}")
    print(f"\nPublished NAV: ${fee_result['nav_per_token']:.8f}")
    print(f"Fund HWM: ${fee_result['fund_hwm_after']:.8f}")
    print(f"Total Fees Collected: ${fee_result['total_fees_collected']:,.2f}")
    print(f"{'='*60}\n")

    return {
        'success': True,
        'calculation_date': calculation_date,
        'nav_per_token': fee_result['nav_per_token'],
        'nav_before_fees': fee_result['nav_before_fees'],
        'fund_hwm_after': fee_result['fund_hwm_after'],
        'total_fees_collected': fee_result['total_fees_collected'],
        'management_fee_amount': fee_result['management_fee_amount'],
        'performance_fee_amount': fee_result['performance_fee_amount'],
        'hwm_increased': fee_result['hwm_increased'],
        'trading_balance_post_fees': fee_result['trading_balance_post_fees'],
        'total_tokens_outstanding': total_tokens,
        'fund_state_id': fund_state_record['id']
    }


# ==================== NAV HISTORY QUERY ====================

async def get_nav_history(days: int = 30) -> list:
    """
    Get NAV history for last N days

    Args:
        days: Number of days to retrieve

    Returns:
        List of fund_state records
    """
    return await FundStateDB.get_history(days=days)


async def get_latest_nav() -> Optional[Dict]:
    """
    Get latest NAV calculation

    Returns:
        Dict with latest fund_state, or None if no calculation exists
    """
    return await FundStateDB.get_latest()


async def display_nav_summary():
    """Display summary of latest NAV calculation"""
    latest = await get_latest_nav()

    if not latest:
        print("\nNo NAV calculation found. Run calculate_and_save_nav() first.")
        return

    print(f"\n{'='*60}")
    print(f"LATEST NAV CALCULATION")
    print(f"{'='*60}")
    print(f"Date: {latest['calculation_date']}")
    print(f"Calculated at: {latest['calculated_at']}")
    print(f"\nNAV per token: ${latest['nav_per_token']:.8f}")
    print(f"Fund HWM: ${latest['fund_hwm_after']:.8f}")
    print(f"\nFees collected:")
    print(f"  Management: ${latest['management_fee_amount']:,.2f}")
    print(f"  Performance: ${latest['performance_fee_amount']:,.2f}")
    print(f"  Total: ${latest['total_fees_collected']:,.2f}")
    print(f"\nFund state:")
    print(f"  Total tokens: {latest['total_tokens_outstanding']:,.2f}")
    print(f"  Balance (post-fees): ${latest['trading_balance_post_fees']:,.2f}")
    print(f"{'='*60}\n")


# ==================== TESTING ====================

async def test_nav_calculation():
    """Test NAV calculation with current data"""
    print("\n" + "="*60)
    print("TESTING NAV CALCULATION")
    print("="*60)

    # Initialize database
    await init_database()

    try:
        # Show current state
        print("\nCurrent State:")
        trading_client = await get_trading_client("manual")
        balance = await trading_client.get_balance()
        tokens = await get_total_tokens_outstanding()
        hwm = await FundStateDB.get_current_hwm()

        print(f"  Trading balance: ${balance:,.2f}")
        print(f"  Total tokens: {tokens:,.2f}")
        print(f"  Current HWM: ${hwm:.8f}")

        if tokens == 0:
            print("\n⚠ No tokens outstanding yet.")
            print("  You need to have completed purchases first.")
            print("  This is normal for initial testing.\n")
            return

        # Run calculation
        result = await calculate_and_save_nav(
            notes="Test calculation from nav_calculator.py"
        )

        # Show result
        print("\n✓ Test completed successfully!")

        # Show latest NAV summary
        await display_nav_summary()

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        raise

    finally:
        await close_database()


if __name__ == "__main__":
    """Run test NAV calculation"""
    asyncio.run(test_nav_calculation())
