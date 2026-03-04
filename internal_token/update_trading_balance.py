#!/usr/bin/env python3
"""
Update Trading Account Balance (Manual Entry)

Simple script to manually update the trading account balance for testing
NAV calculations. This simulates having a balance in your trading account
without needing real exchange API integration.

Usage:
    python update_trading_balance.py                    # Interactive mode
    python update_trading_balance.py 105000             # Set to $105,000
    python update_trading_balance.py --show             # Show current balance
    python update_trading_balance.py --add 5000         # Add $5,000
    python update_trading_balance.py --subtract 2000    # Subtract $2,000

Examples:
    # Simulate trading gains
    python update_trading_balance.py 105000

    # Simulate trading loss
    python update_trading_balance.py 95000

    # Check current balance
    python update_trading_balance.py --show
"""

import asyncio
import sys
from decimal import Decimal
from database import init_database, close_database
from trading_account import ManualBalanceClient


async def show_balance():
    """Display current trading account balance"""
    client = ManualBalanceClient()
    await client.initialize()

    balance = await client.get_balance()
    print(f"\n{'=' * 60}")
    print(f"Trading Account Balance")
    print(f"{'=' * 60}")
    print(f"Current Balance: ${balance:,.2f}")
    print(f"{'=' * 60}\n")


async def set_balance(new_balance: Decimal):
    """Set trading account balance to specific value"""
    client = ManualBalanceClient()
    await client.initialize()

    old_balance = await client.get_balance()

    print(f"\n{'=' * 60}")
    print(f"Updating Trading Account Balance")
    print(f"{'=' * 60}")
    print(f"Old Balance: ${old_balance:,.2f}")
    print(f"New Balance: ${new_balance:,.2f}")

    change = new_balance - old_balance
    if change > 0:
        print(f"Change:      +${change:,.2f} ({change/old_balance*100:+.2f}%)")
    elif change < 0:
        print(f"Change:      -${abs(change):,.2f} ({change/old_balance*100:.2f}%)")
    else:
        print(f"Change:      $0.00 (no change)")

    print(f"{'=' * 60}")

    # Confirm
    confirm = input("\nConfirm update? (y/n): ").strip().lower()
    if confirm not in ['y', 'yes']:
        print("Update cancelled.")
        return

    await client.set_balance(new_balance)
    print("\n✓ Balance updated successfully!\n")


async def adjust_balance(amount: Decimal):
    """Add or subtract from current balance"""
    client = ManualBalanceClient()
    await client.initialize()

    old_balance = await client.get_balance()
    new_balance = old_balance + amount

    if new_balance < 0:
        print(f"\n✗ Error: Resulting balance would be negative (${new_balance:,.2f})")
        print(f"  Current balance: ${old_balance:,.2f}")
        print(f"  Adjustment: ${amount:,.2f}")
        print(f"  Cannot proceed.\n")
        return

    print(f"\n{'=' * 60}")
    print(f"Adjusting Trading Account Balance")
    print(f"{'=' * 60}")
    print(f"Current Balance: ${old_balance:,.2f}")
    print(f"Adjustment:      ${amount:+,.2f}")
    print(f"New Balance:     ${new_balance:,.2f}")
    print(f"{'=' * 60}")

    # Confirm
    confirm = input("\nConfirm adjustment? (y/n): ").strip().lower()
    if confirm not in ['y', 'yes']:
        print("Adjustment cancelled.")
        return

    await client.set_balance(new_balance)
    print("\n✓ Balance adjusted successfully!\n")


async def interactive_mode():
    """Interactive mode for balance updates"""
    client = ManualBalanceClient()
    await client.initialize()

    current = await client.get_balance()

    print(f"\n{'=' * 60}")
    print(f"Trading Account Balance - Interactive Mode")
    print(f"{'=' * 60}")
    print(f"Current Balance: ${current:,.2f}")
    print(f"{'=' * 60}\n")

    while True:
        try:
            user_input = input("Enter new balance (or 'q' to quit): ").strip()

            if user_input.lower() in ['q', 'quit', 'exit']:
                print("Exiting.\n")
                break

            # Parse input
            new_balance = Decimal(user_input.replace(',', '').replace('$', ''))

            if new_balance < 0:
                print("✗ Balance cannot be negative. Try again.\n")
                continue

            await set_balance(new_balance)
            break

        except (ValueError, KeyboardInterrupt):
            print("\n✗ Invalid input. Please enter a number.\n")
            continue


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
            # No arguments - interactive mode
            await interactive_mode()

        elif args[0] in ['-h', '--help', 'help']:
            # Show help
            print_usage()

        elif args[0] in ['-s', '--show', 'show']:
            # Show current balance
            await show_balance()

        elif args[0] in ['-a', '--add', 'add']:
            # Add to balance
            if len(args) < 2:
                print("✗ Error: Missing amount to add")
                print("Usage: python update_trading_balance.py --add AMOUNT")
                return

            amount = Decimal(args[1].replace(',', '').replace('$', ''))
            await adjust_balance(amount)

        elif args[0] in ['-s', '--subtract', 'subtract']:
            # Subtract from balance
            if len(args) < 2:
                print("✗ Error: Missing amount to subtract")
                print("Usage: python update_trading_balance.py --subtract AMOUNT")
                return

            amount = -Decimal(args[1].replace(',', '').replace('$', ''))
            await adjust_balance(amount)

        else:
            # Direct balance set
            try:
                new_balance = Decimal(args[0].replace(',', '').replace('$', ''))
                await set_balance(new_balance)
            except ValueError:
                print(f"✗ Error: Invalid balance '{args[0]}'")
                print_usage()

    except Exception as e:
        print(f"\n✗ Error: {e}\n")
        raise

    finally:
        # Close database
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
