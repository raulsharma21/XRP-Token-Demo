#!/usr/bin/env python3
"""
Send XRP between wallets
Quick utility for manual XRP transfers
"""

from xrpl.clients import JsonRpcClient
from xrpl.wallet import Wallet
from xrpl.models.transactions import Payment
from xrpl.models.requests import AccountInfo
from xrpl.transaction import submit_and_wait
from xrpl.utils import drops_to_xrp, xrp_to_drops
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from parent directory (internal_token/)
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# Configuration
TESTNET_URL = "https://s.altnet.rippletest.net:51234/"
USE_TESTNET = os.getenv('XRPL_NETWORK', 'testnet') == 'testnet'
NETWORK_URL = TESTNET_URL if USE_TESTNET else os.getenv('XRPL_CLIENT_URL', TESTNET_URL)

print("=" * 60)
print("SEND XRP BETWEEN WALLETS")
print("=" * 60)
print(f"Network: {'TESTNET' if USE_TESTNET else 'MAINNET'}")
print()

client = JsonRpcClient(NETWORK_URL)

def get_balance(address: str):
    """Get XRP balance for an address"""
    try:
        response = client.request(AccountInfo(
            account=address,
            ledger_index="validated"
        ))
        balance_drops = response.result["account_data"]["Balance"]
        return drops_to_xrp(balance_drops)
    except Exception as e:
        return None

# Get sender wallet
print("SENDER WALLET")
print("-" * 60)
print("Enter sender wallet seed (or press Enter to use configured wallet):")
sender_seed = input("Seed: ").strip()

if not sender_seed:
    # Try to use a configured wallet
    print("\nWhich configured wallet to use as sender?")
    print("  1. Cold Wallet")
    print("  2. Hot Wallet")
    print("  3. Deposit Wallet")
    choice = input("Choice (1/2/3): ").strip()
    
    if choice == '1':
        sender_seed = os.getenv('COLD_WALLET_SEED')
    elif choice == '2':
        sender_seed = os.getenv('HOT_WALLET_SEED')
    elif choice == '3':
        sender_seed = os.getenv('DEPOSIT_WALLET_SEED')
    else:
        print("❌ Invalid choice")
        exit(1)
    
    if not sender_seed:
        print("❌ Wallet seed not found in .env")
        exit(1)

try:
    sender_wallet = Wallet.from_seed(sender_seed)
    sender_balance = get_balance(sender_wallet.address)
    print(f"✓ Sender: {sender_wallet.address}")
    print(f"  Balance: {sender_balance} XRP")
except Exception as e:
    print(f"❌ Error loading sender wallet: {e}")
    exit(1)

# Get recipient address
print("\nRECIPIENT")
print("-" * 60)
recipient_address = input("Enter recipient address: ").strip()

if not recipient_address.startswith('r'):
    print("❌ Invalid XRPL address")
    exit(1)

# Check recipient balance (optional, might not exist yet)
recipient_balance = get_balance(recipient_address)
print(f"✓ Recipient: {recipient_address}")
if recipient_balance is not None:
    print(f"  Current balance: {recipient_balance} XRP")
else:
    print(f"  (Account not yet activated or not found)")

# Get amount
print("\nAMOUNT")
print("-" * 60)
amount_input = input("Enter amount to send (XRP): ").strip()

try:
    amount_xrp = float(amount_input)
    if amount_xrp <= 0:
        raise ValueError("Amount must be positive")
except ValueError as e:
    print(f"❌ Invalid amount: {e}")
    exit(1)

# Optional: Destination tag
print("\nDESTINATION TAG (optional)")
print("-" * 60)
dest_tag_input = input("Destination tag (press Enter to skip): ").strip()
dest_tag = int(dest_tag_input) if dest_tag_input else None

# Summary
print("\n" + "=" * 60)
print("TRANSACTION SUMMARY")
print("=" * 60)
print(f"From:   {sender_wallet.address}")
print(f"To:     {recipient_address}")
print(f"Amount: {amount_xrp} XRP ({xrp_to_drops(amount_xrp)} drops)")
if dest_tag:
    print(f"Tag:    {dest_tag}")
print(f"Fee:    ~0.000012 XRP (auto)")
print()

proceed = input("Send transaction? (y/N): ")
if proceed.lower() != 'y':
    print("Cancelled.")
    exit(0)

# Build and send transaction
print("\n" + "=" * 60)
print("SENDING TRANSACTION")
print("=" * 60)

payment_tx_args = {
    "account": sender_wallet.address,
    "destination": recipient_address,
    "amount": xrp_to_drops(amount_xrp),
}

if dest_tag:
    payment_tx_args["destination_tag"] = dest_tag

payment_tx = Payment(**payment_tx_args)

try:
    print("Submitting to XRPL...")
    response = submit_and_wait(payment_tx, client, sender_wallet)
    
    result = response.result["meta"]["TransactionResult"]
    tx_hash = response.result["hash"]
    fee_drops = response.result.get("Fee", "12")
    
    print()
    if result == "tesSUCCESS":
        print("✓ Transaction successful!")
        print(f"\nTransaction details:")
        print(f"  Hash: {tx_hash}")
        print(f"  Fee:  {drops_to_xrp(fee_drops)} XRP")
        
        # Get new balances
        new_sender_balance = get_balance(sender_wallet.address)
        new_recipient_balance = get_balance(recipient_address)
        
        print(f"\nNew balances:")
        print(f"  Sender:    {new_sender_balance} XRP")
        print(f"  Recipient: {new_recipient_balance} XRP")
        
        explorer_url = "https://testnet.xrpl.org" if USE_TESTNET else "https://livenet.xrpl.org"
        print(f"\n🔗 View on explorer:")
        print(f"  {explorer_url}/transactions/{tx_hash}")
    else:
        print(f"❌ Transaction failed: {result}")
        exit(1)
        
except Exception as e:
    print(f"\n❌ Error: {e}")
    exit(1)

print("\n" + "=" * 60)
print("DONE!")
print("=" * 60)
