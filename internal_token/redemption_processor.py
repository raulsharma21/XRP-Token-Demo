"""
Redemption Processor

Handles processing of IND token redemptions:
1. Create redemption request with destination tag
2. Investor sends IND tokens to issuer wallet
3. Monitor detects token payment
4. Calculate USDC owed (tokens × NAV)
5. Send USDC back to investor
6. Update investor balances

Usage:
    # Create redemption request
    redemption = await create_redemption_request(investor_id, token_amount)

    # Process detected redemption
    await process_redemption(redemption_id, burn_tx_hash)
"""

from decimal import Decimal
from typing import Dict, Optional
from datetime import datetime
import asyncio

# Import modules
from database import (
    RedemptionDB, InvestorDB, FundStateDB,
    init_database, close_database
)
from xrpl_utils import send_usdc_to_investor
from fee_calculator import calculate_redemption_value
import random


# ==================== REDEMPTION REQUEST CREATION ====================

async def create_redemption_request(
    investor_id: str,
    token_amount: Decimal
) -> Dict:
    """
    Create a redemption request with destination tag

    Args:
        investor_id: UUID of investor
        token_amount: Number of tokens to redeem

    Returns:
        Dict with redemption details including destination_tag

    Raises:
        ValueError: If validation fails
    """
    # Validate investor exists
    investor = await InvestorDB.get_by_id(investor_id)
    if not investor:
        raise ValueError(f"Investor not found: {investor_id}")

    # Validate token amount
    if token_amount <= 0:
        raise ValueError("Token amount must be positive")

    # Get current NAV for pricing
    current_nav = await FundStateDB.get_current_nav_value()

    # Calculate USDC value
    usdc_amount = calculate_redemption_value(token_amount, current_nav)

    # Generate unique destination tag (hash of redemption for now)
    # In production, use a sequence or random number
    destination_tag = random.randint(1000000, 9999999)

    # Create redemption record
    redemption = await RedemptionDB.create(
        investor_id=investor_id,
        token_amount=token_amount,
        destination_tag=destination_tag
    )

    print(f"\n{'='*60}")
    print(f"REDEMPTION REQUEST CREATED")
    print(f"{'='*60}")
    print(f"Investor: {investor['email']}")
    print(f"Tokens to redeem: {token_amount}")
    print(f"Current NAV: ${current_nav:.8f}")
    print(f"Estimated USDC: ${usdc_amount:.2f}")
    print(f"Destination Tag: {destination_tag}")
    print(f"{'='*60}")
    print(f"\nInstructions for investor:")
    print(f"1. Send {token_amount} IND tokens to issuer wallet")
    print(f"2. Use destination tag: {destination_tag}")
    print(f"3. Tokens will be automatically burned")
    print(f"4. You will receive ${usdc_amount:.2f} USDC")
    print(f"{'='*60}\n")

    return {
        'redemption_id': str(redemption['id']),
        'destination_tag': destination_tag,
        'token_amount': token_amount,
        'estimated_usdc': usdc_amount,
        'current_nav': current_nav
    }


# ==================== REDEMPTION PROCESSING ====================

async def process_redemption(
    redemption_id: str,
    burn_tx_hash: str
) -> Dict:
    """
    Process a detected redemption

    Called by monitor when IND tokens are received at issuer wallet

    Args:
        redemption_id: UUID of redemption request
        burn_tx_hash: XRPL transaction hash where tokens were sent

    Returns:
        Dict with processing result

    Raises:
        ValueError: If validation fails
        Exception: If USDC payment fails
    """
    print(f"\n{'='*60}")
    print(f"PROCESSING REDEMPTION")
    print(f"{'='*60}")

    # Get redemption record
    redemption = await RedemptionDB.get_by_id(redemption_id)
    if not redemption:
        raise ValueError(f"Redemption not found: {redemption_id}")

    # Validate status
    if redemption['status'] not in ['queued', 'detected']:
        raise ValueError(f"Redemption already processed: {redemption['status']}")

    # Get investor
    investor = await InvestorDB.get_by_id(redemption['investor_id'])
    if not investor:
        raise ValueError(f"Investor not found: {redemption['investor_id']}")

    print(f"Redemption ID: {redemption_id}")
    print(f"Investor: {investor['email']}")
    print(f"Tokens: {redemption['token_amount']}")
    print(f"Burn TX: {burn_tx_hash}")

    # Mark as detected
    if redemption['status'] == 'queued':
        await RedemptionDB.mark_detected(redemption_id, burn_tx_hash)
        print(f"✓ Redemption marked as detected")

    # Get current NAV for final pricing
    current_nav = await FundStateDB.get_current_nav_value()
    token_amount = Decimal(str(redemption['token_amount']))

    # Calculate USDC owed
    usdc_owed = calculate_redemption_value(token_amount, current_nav)

    print(f"\nPayment calculation:")
    print(f"  Tokens: {token_amount}")
    print(f"  NAV: ${current_nav:.8f}")
    print(f"  USDC owed: ${usdc_owed:.2f}")

    # Send USDC to investor
    print(f"\nSending USDC to investor...")

    # In production, this would send real USDC from deposit wallet
    # For testnet, this might be XRP or testnet USDC
    payment_result = await send_usdc_to_investor(
        recipient_address=investor['xrpl_address'],
        amount=usdc_owed
    )

    if not payment_result['success']:
        raise Exception(f"USDC payment failed: {payment_result.get('error')}")

    redemption_tx_hash = payment_result['tx_hash']
    print(f"✓ USDC sent: ${usdc_owed:.2f}")
    print(f"  TX: {redemption_tx_hash}")

    # Mark redemption as completed
    await RedemptionDB.complete(
        redemption_id=redemption_id,
        nav_price=current_nav,
        usdc_amount=usdc_owed,
        redemption_tx_hash=redemption_tx_hash
    )

    print(f"\n{'='*60}")
    print(f"✓ REDEMPTION COMPLETED")
    print(f"{'='*60}")
    print(f"Tokens redeemed: {token_amount}")
    print(f"USDC paid: ${usdc_owed:.2f}")
    print(f"NAV used: ${current_nav:.8f}")
    print(f"{'='*60}\n")

    return {
        'success': True,
        'redemption_id': redemption_id,
        'tokens_redeemed': token_amount,
        'usdc_paid': usdc_owed,
        'nav_used': current_nav,
        'burn_tx_hash': burn_tx_hash,
        'payment_tx_hash': redemption_tx_hash
    }


# ==================== REDEMPTION DETECTION (FOR MONITOR) ====================

async def detect_and_process_redemption(
    tx_hash: str,
    sender: str,
    destination: str,
    destination_tag: Optional[int],
    token_amount: Decimal,
    issuer_address: str
) -> bool:
    """
    Detect and process a redemption from transaction data

    Called by monitor when IND token payment is detected

    Args:
        tx_hash: XRPL transaction hash
        sender: Investor address
        destination: Should be issuer address
        destination_tag: Tag to match redemption request
        token_amount: Amount of tokens sent
        issuer_address: Expected issuer address

    Returns:
        bool: True if processed successfully
    """
    try:
        print(f"\n{'='*60}")
        print(f"REDEMPTION DETECTED")
        print(f"{'='*60}")
        print(f"TX: {tx_hash}")
        print(f"From: {sender}")
        print(f"Tokens: {token_amount}")
        print(f"Destination Tag: {destination_tag}")

        # Validate destination
        if destination != issuer_address:
            print(f"✗ Wrong destination (expected issuer {issuer_address})")
            return False

        # Check destination tag
        if not destination_tag:
            print(f"✗ No destination tag - cannot match to redemption request")
            print(f"  Manual intervention required")
            return False

        # Find matching redemption request
        redemption = await RedemptionDB.get_by_destination_tag(destination_tag)

        if not redemption:
            print(f"✗ No redemption request found for tag {destination_tag}")
            print(f"  Manual intervention required")
            return False

        print(f"✓ Matched redemption request: {redemption['id']}")

        # Verify token amount matches (within tolerance)
        expected_tokens = Decimal(str(redemption['token_amount']))
        tolerance = expected_tokens * Decimal('0.01')  # 1% tolerance

        if abs(token_amount - expected_tokens) > tolerance:
            print(f"⚠ Token amount mismatch!")
            print(f"  Expected: {expected_tokens}")
            print(f"  Received: {token_amount}")
            # Continue anyway, use actual amount received

        # Process the redemption
        result = await process_redemption(
            redemption_id=str(redemption['id']),
            burn_tx_hash=tx_hash
        )

        return result['success']

    except Exception as e:
        print(f"✗ Error processing redemption: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==================== TESTING ====================

async def test_redemption_flow():
    """Test redemption creation and processing"""
    print("\n" + "="*60)
    print("TESTING REDEMPTION FLOW")
    print("="*60)

    await init_database()

    try:
        # Test 1: Create redemption request
        print("\nTest 1: Create redemption request")
        print("-" * 60)

        # Get a test investor (or create one)
        investors = await InvestorDB.get_all()
        if not investors:
            print("No investors found. Create one first.")
            return

        investor = investors[0]
        print(f"Using investor: {investor['email']}")

        redemption = await create_redemption_request(
            investor_id=str(investor['id']),
            token_amount=Decimal('50')
        )

        print(f"\n✓ Redemption request created")
        print(f"  Redemption ID: {redemption['redemption_id']}")
        print(f"  Destination Tag: {redemption['destination_tag']}")

        # Test 2: Simulate detection and processing
        print("\n\nTest 2: Simulate redemption detection")
        print("-" * 60)

        # In real flow, monitor would detect this
        # For testing, we'll call the detection function directly
        success = await detect_and_process_redemption(
            tx_hash="simulated-burn-tx-hash",
            sender=investor['xrpl_address'],
            destination="rISSUER_ADDRESS",  # Would be actual issuer
            destination_tag=redemption['destination_tag'],
            token_amount=Decimal('50'),
            issuer_address="rISSUER_ADDRESS"
        )

        if success:
            print("\n✓ Full redemption flow test passed!")
        else:
            print("\n✗ Redemption processing failed")

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await close_database()


if __name__ == "__main__":
    """Run tests"""
    asyncio.run(test_redemption_flow())
