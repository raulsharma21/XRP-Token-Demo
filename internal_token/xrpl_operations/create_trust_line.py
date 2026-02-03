#!/usr/bin/env python3
"""
Create Trust Line to Token Issuer
Allows an investor wallet to receive and hold tokens
"""

from xrpl.clients import JsonRpcClient
from xrpl.wallet import Wallet
from xrpl.models.transactions import TrustSet
from xrpl.models.amounts import IssuedCurrencyAmount
from xrpl.models.requests import AccountInfo, AccountLines
from xrpl.transaction import submit_and_wait
from xrpl.utils import drops_to_xrp
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
TOKEN_CURRENCY = os.getenv('TOKEN_CURRENCY_CODE', 'IND')
TOKEN_ISSUER = os.getenv('TOKEN_ISSUER_ADDRESS', '')

print("=" * 60)
print("CREATE TRUST LINE TO TOKEN ISSUER")
print("=" * 60)
print(f"Network: {'TESTNET' if USE_TESTNET else 'MAINNET'}")
print(f"Token:   {TOKEN_CURRENCY}")
print(f"Issuer:  {TOKEN_ISSUER}")
print()

if not TOKEN_ISSUER:
    print("❌ TOKEN_ISSUER_ADDRESS not found in .env")
    exit(1)

client = JsonRpcClient(NETWORK_URL)

def get_balance(address: str):
    """Get XRP balance"""
    try:
        response = client.request(AccountInfo(
            account=address,
            ledger_index="validated"
        ))
        balance_drops = response.result["account_data"]["Balance"]
        return drops_to_xrp(balance_drops)
    except Exception as e:
        return None

def check_existing_trust_line(address: str) -> bool:
    """Check if trust line already exists"""
    try:
        response = client.request(AccountLines(
            account=address,
            ledger_index="validated"
        ))
        lines = response.result.get("lines", [])
        for line in lines:
            if line["account"] == TOKEN_ISSUER and line["currency"] == TOKEN_CURRENCY:
                return True
        return False
    except:
        return False

# Get investor wallet seed
print("INVESTOR WALLET")
print("-" * 60)
print("Enter your wallet seed:")
investor_seed = input("Seed (starts with 's'): ").strip()

if not investor_seed.startswith('s'):
    print("❌ Invalid seed format")
    exit(1)

try:
    investor_wallet = Wallet.from_seed(investor_seed)
    xrp_balance = get_balance(investor_wallet.address)
    print(f"✓ Wallet loaded: {investor_wallet.address}")
    print(f"  XRP Balance: {xrp_balance}")
    
    # Check if trust line already exists
    if check_existing_trust_line(investor_wallet.address):
        print(f"\n⚠️  Trust line already exists for {TOKEN_CURRENCY}!")
        print("You can already receive tokens.")
        exit(0)
        
except Exception as e:
    print(f"❌ Error loading wallet: {e}")
    exit(1)

# Set trust line limit
print("\nTRUST LINE LIMIT")
print("-" * 60)
print("How many tokens do you want to be able to hold?")
print("(This is your maximum balance, you can set it high)")
limit_input = input("Limit (default: 1000000): ").strip()
limit = limit_input if limit_input else "1000000"

# Summary
print("\n" + "=" * 60)
print("TRANSACTION SUMMARY")
print("=" * 60)
print(f"Your address:  {investor_wallet.address}")
print(f"Token:         {TOKEN_CURRENCY}")
print(f"Issuer:        {TOKEN_ISSUER}")
print(f"Trust limit:   {limit}")
print()

proceed = input("Create trust line? (y/N): ")
if proceed.lower() != 'y':
    print("Cancelled.")
    exit(0)

# Create trust line
print("\n" + "=" * 60)
print("CREATING TRUST LINE")
print("=" * 60)
print("Submitting to XRPL...")

trust_tx = TrustSet(
    account=investor_wallet.address,
    limit_amount=IssuedCurrencyAmount(
        currency=TOKEN_CURRENCY,
        issuer=TOKEN_ISSUER,
        value=limit,
    ),
)

try:
    response = submit_and_wait(trust_tx, client, investor_wallet)
    result = response.result["meta"]["TransactionResult"]
    tx_hash = response.result["hash"]
    fee_drops = response.result.get("Fee", "12")
    
    print()
    if result == "tesSUCCESS":
        print("✓ Trust line created successfully!")
        print(f"\nTransaction details:")
        print(f"  Hash: {tx_hash}")
        print(f"  Fee:  {drops_to_xrp(fee_drops)} XRP")
        
        explorer_url = "https://testnet.xrpl.org" if USE_TESTNET else "https://livenet.xrpl.org"
        print(f"\n🔗 View on explorer:")
        print(f"  {explorer_url}/transactions/{tx_hash}")
        
        print(f"\n✓ You can now receive up to {limit} {TOKEN_CURRENCY} tokens")
        print(f"\n⚠️  Next step: Admin must authorize your trust line (KYC)")
        print(f"   Use API: POST /api/investors/{{id}}/trust-line/authorize")
    else:
        print(f"❌ Transaction failed: {result}")
        exit(1)
        
except Exception as e:
    print(f"\n❌ Error: {e}")
    exit(1)

print("\n" + "=" * 60)
print("DONE!")
print("=" * 60)
