#!/usr/bin/env python3
"""
Toggle IPO Phase

Helper script to switch between IPO and post-IPO pricing modes.

IPO Phase (active):
  - Subscriptions use fixed $1.00 pricing
  - 1 USDC = 1 token

Post-IPO Phase (closed):
  - Subscriptions use current NAV pricing
  - Tokens = USDC / NAV

Usage:
    python toggle_ipo_phase.py              # Show current status
    python toggle_ipo_phase.py active       # Set IPO phase active ($1.00 pricing)
    python toggle_ipo_phase.py closed       # Set IPO phase closed (NAV pricing)
"""

import asyncio
import sys
from database import init_database, close_database, SystemConfigDB, FundStateDB


async def show_current_status():
    """Display current IPO phase status"""
    ipo_phase = await SystemConfigDB.get('ipo_phase')
    nav = await FundStateDB.get_current_nav_value()

    print(f"\n{'='*60}")
    print(f"CURRENT PRICING MODE")
    print(f"{'='*60}")
    print(f"IPO Phase: {ipo_phase or 'active (default)'}")
    print(f"Current NAV: ${nav:.8f}")

    if ipo_phase == 'active' or not ipo_phase:
        print(f"\nPricing: FIXED $1.00 (IPO mode)")
        print(f"  - Subscriptions: 1 USDC = 1 token")
        print(f"  - Redemptions: Use current NAV (${nav:.8f})")
    else:
        print(f"\nPricing: DYNAMIC NAV (Post-IPO mode)")
        print(f"  - Subscriptions: Tokens = USDC / ${nav:.8f}")
        print(f"  - Redemptions: USDC = tokens × ${nav:.8f}")

    print(f"{'='*60}\n")


async def set_ipo_phase(phase: str):
    """Set IPO phase to active or closed"""
    if phase not in ['active', 'closed']:
        print(f"✗ Invalid phase: {phase}")
        print("  Must be 'active' or 'closed'")
        return

    # Update system config
    await SystemConfigDB.set('ipo_phase', phase)

    print(f"\n{'='*60}")
    print(f"IPO PHASE UPDATED")
    print(f"{'='*60}")
    print(f"New status: {phase}")

    if phase == 'active':
        print(f"\n✓ IPO phase activated")
        print(f"  - Subscriptions now use fixed $1.00 pricing")
        print(f"  - All investors get 1:1 token ratio")
    else:
        nav = await FundStateDB.get_current_nav_value()
        print(f"\n✓ IPO phase closed")
        print(f"  - Subscriptions now use NAV pricing (${nav:.8f})")
        print(f"  - Token amounts calculated dynamically")

    print(f"{'='*60}\n")

    # Show new status
    await show_current_status()


async def main():
    """Main entry point"""
    await init_database()

    try:
        args = sys.argv[1:]

        if not args:
            # No arguments - show current status
            await show_current_status()
        elif args[0] in ['-h', '--help', 'help']:
            # Show help
            print(__doc__)
        elif args[0] in ['active', 'closed']:
            # Set IPO phase
            await set_ipo_phase(args[0])
        else:
            print(f"✗ Unknown argument: {args[0]}")
            print("Usage: python toggle_ipo_phase.py [active|closed]")

    except Exception as e:
        print(f"\n✗ Error: {e}\n")
        raise

    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
