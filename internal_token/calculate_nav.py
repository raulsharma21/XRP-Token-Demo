#!/usr/bin/env python3
"""
Calculate Daily NAV - Manual Execution Script

Run this script to manually calculate and publish the daily NAV.

In production, this would run automatically at 00:00 UTC daily.
For testing, run it manually whenever you want to calculate NAV.

Usage:
    python calculate_nav.py                    # Calculate NAV for today
    python calculate_nav.py --show             # Show latest NAV
    python calculate_nav.py --history 7        # Show last 7 days
    python calculate_nav.py --date 2026-02-20  # Calculate for specific date

Examples:
    # After setting trading balance to $105,000
    python update_trading_balance.py 105000
    python calculate_nav.py

    # View results
    python calculate_nav.py --show
"""

import asyncio
import sys
from datetime import date, datetime
from database import init_database, close_database, FundStateDB
from nav_calculator import (
    calculate_and_save_nav,
    display_nav_summary,
    get_nav_history
)


async def run_calculation(calculation_date: date = None, notes: str = None):
    """Run NAV calculation"""
    try:
        result = await calculate_and_save_nav(
            calculation_date=calculation_date,
            notes=notes
        )

        print("\n" + "="*60)
        print("CALCULATION SUCCESSFUL")
        print("="*60)
        print(f"Date: {result['calculation_date']}")
        print(f"NAV: ${result['nav_per_token']:.8f}")
        print(f"HWM: ${result['fund_hwm']:.8f}")
        print(f"Fees: ${result['total_fees']:,.2f}")
        print("="*60)
        print("\nThis NAV is now published and will be used for:")
        print("  - New subscriptions (tokens = USDC / NAV)")
        print("  - Redemptions (USDC = tokens × NAV)")
        print("  - Investor dashboard displays")
        print("="*60 + "\n")

        return True

    except ValueError as e:
        print(f"\n✗ Calculation failed: {e}\n")
        return False
    except Exception as e:
        print(f"\n✗ Error: {e}\n")
        import traceback
        traceback.print_exc()
        return False


async def show_latest():
    """Show latest NAV calculation"""
    await display_nav_summary()


async def show_history(days: int):
    """Show NAV history"""
    print(f"\n{'='*60}")
    print(f"NAV HISTORY - Last {days} Days")
    print(f"{'='*60}\n")

    history = await get_nav_history(days=days)

    if not history:
        print("No NAV calculations found.\n")
        return

    print(f"{'Date':<12} {'NAV':<12} {'HWM':<12} {'Mgmt Fee':<12} {'Perf Fee':<12}")
    print("-" * 60)

    for record in history:
        print(
            f"{str(record['calculation_date']):<12} "
            f"${record['nav_per_token']:<11.6f} "
            f"${record['fund_hwm_after']:<11.6f} "
            f"${record['management_fee_amount']:<11.2f} "
            f"${record['performance_fee_amount']:<11.2f}"
        )

    print(f"\nTotal records: {len(history)}\n")


async def check_if_already_calculated_today():
    """Check if NAV was already calculated today"""
    today = date.today()
    existing = await FundStateDB.get_by_date(today)

    if existing:
        print(f"\n⚠ NAV already calculated for {today}")
        print(f"   NAV: ${existing['nav_per_token']:.8f}")
        print(f"   Calculated at: {existing['calculated_at']}")
        print(f"\nDo you want to recalculate? This will replace the existing record.")

        response = input("Recalculate? (y/n): ").strip().lower()
        return response in ['y', 'yes']

    return True


def print_usage():
    """Print usage information"""
    print(__doc__)


async def main():
    """Main entry point"""
    # Initialize database
    await init_database()

    try:
        args = sys.argv[1:]

        if not args:
            # No arguments - run calculation for today
            should_run = await check_if_already_calculated_today()
            if should_run:
                await run_calculation()

        elif args[0] in ['-h', '--help', 'help']:
            # Show help
            print_usage()

        elif args[0] in ['-s', '--show', 'show']:
            # Show latest NAV
            await show_latest()

        elif args[0] in ['--history', '-l', 'list']:
            # Show history
            days = int(args[1]) if len(args) > 1 else 30
            await show_history(days)

        elif args[0] in ['--date', '-d']:
            # Calculate for specific date
            if len(args) < 2:
                print("✗ Error: Missing date")
                print("Usage: python calculate_nav.py --date YYYY-MM-DD")
                return

            calc_date = datetime.strptime(args[1], '%Y-%m-%d').date()
            await run_calculation(calculation_date=calc_date)

        else:
            print(f"✗ Error: Unknown argument '{args[0]}'")
            print_usage()

    except KeyboardInterrupt:
        print("\n\nCalculation cancelled.\n")

    except Exception as e:
        print(f"\n✗ Error: {e}\n")
        raise

    finally:
        # Close database
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
