#!/usr/bin/env python3
"""
Fund Hot Wallet (Testnet Only)

Transfers XRP from deposit wallet to hot wallet so it can process redemptions.
On production, hot wallet would be funded from Coinbase withdrawals.
"""

import os
from decimal import Decimal
from xrpl.clients import JsonRpcClient
from xrpl.models.transactions import Payment
from xrpl.transaction import submit_and_wait
from xrpl.wallet import Wallet
from dotenv import load_dotenv

load_dotenv()

# Configuration
TESTNET_URL = "https://s.altnet.rippletest.net:51234/"

DEPOSIT_WALLET_SEED = os.getenv('DEPOSIT_WALLET_SEED')
HOT_WALLET_ADDRESS = os.getenv('HOT_WALLET_ADDRESS')

def fund_hot_wallet(amount_xrp: int = 10000):
    """
    Send XRP from deposit wallet to hot wallet

    Args:
        amount_xrp: Amount of XRP to send (default 10,000)
    """
    print(f"\n{'='*60}")
    print(f"FUNDING HOT WALLET (TESTNET)")
    print(f"{'='*60}")

    # Initialize client
    client = JsonRpcClient(TESTNET_URL)

    # Load deposit wallet
    deposit_wallet = Wallet.from_seed(DEPOSIT_WALLET_SEED)

    print(f"\nFrom: {deposit_wallet.address} (Deposit Wallet)")
    print(f"To: {HOT_WALLET_ADDRESS} (Hot Wallet)")
    print(f"Amount: {amount_xrp} XRP")

    # Check deposit wallet balance
    from xrpl.models.requests import AccountInfo
    acct_info = client.request(AccountInfo(account=deposit_wallet.address))
    balance_drops = int(acct_info.result['account_data']['Balance'])
    balance_xrp = balance_drops / 1_000_000

    print(f"\nDeposit wallet balance: {balance_xrp:,.2f} XRP")

    if balance_xrp < amount_xrp + 1:  # +1 for reserve
        print(f"✗ Insufficient balance. Need at least {amount_xrp + 1} XRP")
        return False

    # Create payment
    payment_tx = Payment(
        account=deposit_wallet.address,
        destination=HOT_WALLET_ADDRESS,
        amount=str(amount_xrp * 1_000_000)  # Convert to drops
    )

    print(f"\nSending transaction...")

    try:
        response = submit_and_wait(payment_tx, client, deposit_wallet)
        result = response.result["meta"]["TransactionResult"]

        if result == "tesSUCCESS":
            tx_hash = response.result['hash']
            print(f"\n✓ Hot wallet funded successfully!")
            print(f"TX Hash: {tx_hash}")
            print(f"Explorer: https://testnet.xrpl.org/transactions/{tx_hash}")

            # Check new balance
            hot_acct_info = client.request(AccountInfo(account=HOT_WALLET_ADDRESS))
            hot_balance_drops = int(hot_acct_info.result['account_data']['Balance'])
            hot_balance_xrp = hot_balance_drops / 1_000_000
            print(f"\nHot wallet new balance: {hot_balance_xrp:,.2f} XRP")

            print(f"\n{'='*60}")
            print(f"✓ READY TO PROCESS REDEMPTIONS")
            print(f"{'='*60}\n")
            return True
        else:
            print(f"✗ Transaction failed: {result}")
            return False

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


if __name__ == "__main__":
    import sys

    # Get amount from command line or use default
    amount = int(sys.argv[1]) if len(sys.argv) > 1 else 10000

    print("\n⚠️  WARNING: This only works on testnet!")
    print("On production, hot wallet is funded from Coinbase withdrawals.")

    response = input(f"\nFund hot wallet with {amount} XRP? (y/N): ")
    if response.lower() == 'y':
        fund_hot_wallet(amount)
    else:
        print("Cancelled.")
