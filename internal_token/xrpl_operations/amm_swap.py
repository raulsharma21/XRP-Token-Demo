#!/usr/bin/env python3
"""
AMM Token Swap
Swap between XRP and tokens using the AMM pool
"""

from xrpl.clients import JsonRpcClient
from xrpl.wallet import Wallet
from xrpl.models.transactions import Payment
from xrpl.models.amounts import IssuedCurrencyAmount
from xrpl.models.requests import AMMInfo, AccountInfo, AccountLines
from xrpl.transaction import submit_and_wait
from xrpl.utils import drops_to_xrp, xrp_to_drops
import os
from pathlib import Path
from dotenv import load_dotenv
from decimal import Decimal

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
print("AMM TOKEN SWAP")
print("=" * 60)
print(f"Network: {'TESTNET' if USE_TESTNET else 'MAINNET'}")
print(f"Token:   {TOKEN_CURRENCY}")
print()

if not TOKEN_ISSUER:
    print("❌ TOKEN_ISSUER_ADDRESS not found in .env")
    exit(1)

client = JsonRpcClient(NETWORK_URL)

def get_xrp_balance(address: str):
    """Get XRP balance"""
    try:
        response = client.request(AccountInfo(
            account=address,
            ledger_index="validated"
        ))
        balance_drops = response.result["account_data"]["Balance"]
        return drops_to_xrp(balance_drops)
    except:
        return None

def get_token_balance(address: str):
    """Get token balance"""
    try:
        response = client.request(AccountLines(
            account=address,
            ledger_index="validated"
        ))
        lines = response.result.get("lines", [])
        for line in lines:
            if line["account"] == TOKEN_ISSUER and line["currency"] == TOKEN_CURRENCY:
                return Decimal(line["balance"])
        return Decimal("0")
    except:
        return None

def check_pool_exists():
    """Check if AMM pool exists and get info"""
    try:
        amm_info_request = AMMInfo(
            asset=IssuedCurrencyAmount(
                currency=TOKEN_CURRENCY,
                issuer=TOKEN_ISSUER,
                value="0"
            ),
            asset2={"currency": "XRP"}
        )
        
        response = client.request(amm_info_request)
        
        if response.is_successful():
            amm_data = response.result.get("amm", {})
            return amm_data
        return None
    except:
        return None

def estimate_swap_output(amount_in: Decimal, reserve_in: Decimal, reserve_out: Decimal, fee_percent: Decimal):
    """Estimate output amount for a swap (constant product formula with fees)"""
    # AMM formula: (x * y = k)
    # Output = (amount_in * reserve_out) / (reserve_in + amount_in)
    # With fee: amount_in_after_fee = amount_in * (1 - fee)
    
    fee_multiplier = Decimal("1") - (fee_percent / Decimal("100"))
    amount_in_after_fee = amount_in * fee_multiplier
    
    numerator = amount_in_after_fee * reserve_out
    denominator = reserve_in + amount_in_after_fee
    
    result = numerator / denominator
    
    # Round to 15 significant digits (XRPL max is 16, leave buffer)
    return _round_to_precision(result, 15)

def _round_to_precision(value: Decimal, sig_digits: int) -> Decimal:
    """Round Decimal to specified number of significant digits"""
    if value == 0:
        return Decimal("0")
    
    # Convert to string in scientific notation, then truncate
    str_value = f"{value:.{sig_digits-1}e}"
    return Decimal(str_value)

# Check if pool exists
print("Checking AMM pool...")
pool_info = check_pool_exists()

if not pool_info:
    print("❌ No AMM pool found!")
    print("   Create one first: python create_amm_pool.py")
    exit(1)

pool_account = pool_info.get("account", "")
trading_fee = Decimal(pool_info.get("trading_fee", 50)) / Decimal("10000")  # Convert from basis points
trading_fee_percent = trading_fee * Decimal("100")

print(f"✓ Pool found: {pool_account}")
print(f"  Trading fee: {trading_fee_percent}%")

# Get pool reserves
amount = pool_info.get("amount", {})
amount2 = pool_info.get("amount2", {})

# Determine which is token and which is XRP
if isinstance(amount, dict) and amount.get("currency") == TOKEN_CURRENCY:
    token_reserve = Decimal(amount.get("value", "0"))
    xrp_reserve = Decimal(amount2) / Decimal("1000000")  # Convert drops to XRP
else:
    token_reserve = Decimal(amount2.get("value", "0"))
    xrp_reserve = Decimal(amount) / Decimal("1000000")

print(f"  Token reserve: {token_reserve} {TOKEN_CURRENCY}")
print(f"  XRP reserve: {xrp_reserve} XRP")

# Get user wallet
print("\nYOUR WALLET")
print("-" * 60)
print("Enter your wallet seed:")
user_seed = input("Seed (starts with 's'): ").strip()

if not user_seed.startswith('s'):
    print("❌ Invalid seed format")
    exit(1)

try:
    user_wallet = Wallet.from_seed(user_seed)
    xrp_balance = get_xrp_balance(user_wallet.address)
    token_balance = get_token_balance(user_wallet.address)
    
    print(f"✓ Wallet: {user_wallet.address}")
    print(f"  XRP balance: {xrp_balance if xrp_balance else 'N/A'}")
    print(f"  {TOKEN_CURRENCY} balance: {token_balance if token_balance is not None else 'N/A'}")
except Exception as e:
    print(f"❌ Error loading wallet: {e}")
    exit(1)

# Choose swap direction
print("\nSWAP DIRECTION")
print("-" * 60)
print("1. Buy tokens (XRP → tokens)")
print("2. Sell tokens (tokens → XRP)")
direction = input("Choice (1/2): ").strip()

if direction == "1":
    # Buy tokens with XRP
    swap_type = "buy"
    print(f"\nBuying {TOKEN_CURRENCY} with XRP")
    print(f"Your XRP balance: {xrp_balance}")
    
    amount_in = input(f"Enter XRP amount to spend: ").strip()
    try:
        amount_in = Decimal(amount_in)
        if amount_in <= 0 or amount_in >= xrp_balance:
            raise ValueError("Invalid amount")
    except:
        print("❌ Invalid amount")
        exit(1)
    
    # Estimate output
    estimated_output = estimate_swap_output(amount_in, xrp_reserve, token_reserve, trading_fee_percent)
    
    print(f"\nEstimated output: ~{estimated_output:.4f} {TOKEN_CURRENCY}")
    print(f"Price: ~{amount_in/estimated_output:.6f} XRP per {TOKEN_CURRENCY}")
    
elif direction == "2":
    # Sell tokens for XRP
    swap_type = "sell"
    print(f"\nSelling {TOKEN_CURRENCY} for XRP")
    print(f"Your {TOKEN_CURRENCY} balance: {token_balance}")
    
    amount_in = input(f"Enter {TOKEN_CURRENCY} amount to sell: ").strip()
    try:
        amount_in = Decimal(amount_in)
        if amount_in <= 0 or amount_in > token_balance:
            raise ValueError("Invalid amount")
    except:
        print("❌ Invalid amount")
        exit(1)
    
    # Estimate output
    estimated_output = estimate_swap_output(amount_in, token_reserve, xrp_reserve, trading_fee_percent)
    
    print(f"\nEstimated output: ~{estimated_output:.4f} XRP")
    print(f"Price: ~{amount_in/estimated_output:.6f} {TOKEN_CURRENCY} per XRP")
else:
    print("❌ Invalid choice")
    exit(1)

# Transaction summary
print("\n" + "=" * 60)
print("TRANSACTION SUMMARY")
print("=" * 60)
print(f"Wallet:        {user_wallet.address}")
print(f"Direction:     {swap_type.upper()}")
if swap_type == "buy":
    print(f"Sending:       {amount_in} XRP (max)")
    print(f"Receiving:     ~{estimated_output:.4f} {TOKEN_CURRENCY} (estimated)")
    print(f"Min receive:   {estimated_output * Decimal('0.90'):.4f} {TOKEN_CURRENCY} (10% slippage)")
else:
    print(f"Sending:       {amount_in} {TOKEN_CURRENCY} (max)")
    print(f"Receiving:     ~{estimated_output:.4f} XRP (estimated)")
    print(f"Min receive:   {estimated_output * Decimal('0.90'):.4f} XRP (10% slippage)")
print(f"Trading fee:   {trading_fee_percent}%")
print()

proceed = input("Execute swap? (y/N): ")
if proceed.lower() != 'y':
    print("Cancelled.")
    exit(0)

# Execute swap
print("\n" + "=" * 60)
print("EXECUTING SWAP")
print("=" * 60)
print("Submitting to XRPL...")

try:
    # For swaps through AMM, we need to send to a different address then back
    # Workaround: Use the pool address as intermediary, or send to issuer
    # Actually, let's use the issuer as destination for token purchases
    
    if swap_type == "buy":
        # Buy tokens with XRP - send XRP to issuer, receive tokens
        min_output = _round_to_precision(estimated_output * Decimal("0.90"), 15)  # 10% slippage
        
        payment_tx = Payment(
            account=user_wallet.address,
            destination=TOKEN_ISSUER,  # Send to token issuer (they'll route through AMM)
            amount=IssuedCurrencyAmount(
                currency=TOKEN_CURRENCY,
                issuer=TOKEN_ISSUER,
                value=str(min_output)
            ),
            send_max=xrp_to_drops(float(amount_in)),
            flags=131072,  # tfPartialPayment flag
        )
    else:
        # Sell tokens for XRP - send tokens to issuer, receive XRP
        min_output_xrp = estimated_output * Decimal("0.90")  # 10% slippage
        
        payment_tx = Payment(
            account=user_wallet.address,
            destination=TOKEN_ISSUER,  # Send to token issuer (they'll route through AMM)
            amount=xrp_to_drops(float(min_output_xrp)),
            send_max=IssuedCurrencyAmount(
                currency=TOKEN_CURRENCY,
                issuer=TOKEN_ISSUER,
                value=str(_round_to_precision(amount_in, 15))
            ),
            flags=131072,  # tfPartialPayment flag
        )
    
    response = submit_and_wait(payment_tx, client, user_wallet)
    result = response.result["meta"]["TransactionResult"]
    tx_hash = response.result["hash"]
    fee_drops = response.result.get("Fee", "12")
    
    print()
    if result == "tesSUCCESS":
        print("✓ Swap successful!")
        print(f"\nTransaction details:")
        print(f"  Hash: {tx_hash}")
        print(f"  Fee:  {drops_to_xrp(fee_drops)} XRP")
        
        # Get new balances
        new_xrp_balance = get_xrp_balance(user_wallet.address)
        new_token_balance = get_token_balance(user_wallet.address)
        
        print(f"\nNew balances:")
        print(f"  XRP: {new_xrp_balance}")
        print(f"  {TOKEN_CURRENCY}: {new_token_balance}")
        
        explorer_url = "https://testnet.xrpl.org" if USE_TESTNET else "https://livenet.xrpl.org"
        print(f"\n🔗 View on explorer:")
        print(f"  {explorer_url}/transactions/{tx_hash}")
    else:
        print(f"❌ Swap failed: {result}")
        print("\nCommon issues:")
        print("  - Insufficient balance")
        print("  - No trust line for token")
        print("  - Slippage too high (price moved)")
        print("  - Pool liquidity too low")
        exit(1)
        
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

print("\n" + "=" * 60)
print("DONE!")
print("=" * 60)
