"""
XRPL Basic Transaction Test
============================
This script demonstrates:
1. Connecting to XRPL Testnet
2. Creating and funding two wallets
3. Checking balances
4. Sending XRP between wallets
5. Verifying the transaction

Run from your project directory:
    python 01_basic_transaction.py
"""

from xrpl.clients import JsonRpcClient
from xrpl.wallet import generate_faucet_wallet
from xrpl.models.transactions import Payment
from xrpl.models.requests import AccountInfo
from xrpl.transaction import submit_and_wait
from xrpl.utils import drops_to_xrp, xrp_to_drops

# =============================================================================
# STEP 1: Connect to Testnet
# =============================================================================

TESTNET_URL = "https://s.altnet.rippletest.net:51234"

print("=" * 60)
print("XRPL BASIC TRANSACTION TEST")
print("=" * 60)

print("\n[1] Connecting to XRPL Testnet...")
client = JsonRpcClient(TESTNET_URL)
print(f"    ✓ Connected to {TESTNET_URL}")

# =============================================================================
# STEP 2: Create and Fund Two Wallets
# =============================================================================

print("\n[2] Creating wallets (this may take a moment)...")

print("\n    Creating Wallet A (sender)...")
wallet_a = generate_faucet_wallet(client, debug=True)

print("\n    Creating Wallet B (receiver)...")
wallet_b = generate_faucet_wallet(client, debug=True)

print(f"\n    ✓ Wallet A: {wallet_a.address}")
print(f"    ✓ Wallet B: {wallet_b.address}")

# =============================================================================
# STEP 3: Check Initial Balances
# =============================================================================

def get_balance(client, address):
    """Get XRP balance for an address (returns in XRP, not drops)."""
    request = AccountInfo(account=address, ledger_index="validated")
    response = client.request(request)
    balance_drops = response.result["account_data"]["Balance"]
    return drops_to_xrp(balance_drops)

print("\n[3] Checking initial balances...")

balance_a_before = get_balance(client, wallet_a.address)
balance_b_before = get_balance(client, wallet_b.address)

print(f"    Wallet A: {balance_a_before} XRP")
print(f"    Wallet B: {balance_b_before} XRP")

# =============================================================================
# STEP 4: Send XRP from Wallet A to Wallet B
# =============================================================================

SEND_AMOUNT_XRP = 50  # Amount to send

print(f"\n[4] Sending {SEND_AMOUNT_XRP} XRP from Wallet A to Wallet B...")

# Build the payment transaction
payment_tx = Payment(
    account=wallet_a.address,           # Sender
    destination=wallet_b.address,       # Receiver
    amount=xrp_to_drops(SEND_AMOUNT_XRP),  # Amount in drops (1 XRP = 1,000,000 drops)
)

print(f"    Transaction built:")
print(f"      From:   {wallet_a.address}")
print(f"      To:     {wallet_b.address}")
print(f"      Amount: {SEND_AMOUNT_XRP} XRP ({xrp_to_drops(SEND_AMOUNT_XRP)} drops)")

# Submit and wait for validation
print("\n    Submitting transaction...")
response = submit_and_wait(payment_tx, client, wallet_a)

# Check the result
tx_result = response.result["meta"]["TransactionResult"]
print(f"\n    Transaction result: {tx_result}")

if tx_result == "tesSUCCESS":
    print("    ✓ Transaction successful!")
    
    # Get transaction details
    tx_hash = response.result["hash"]
    fee_drops = response.result["fee"]
    
    print(f"\n    Transaction details:")
    print(f"      Hash: {tx_hash}")
    print(f"      Fee:  {drops_to_xrp(fee_drops)} XRP ({fee_drops} drops)")
    print(f"\n    View on explorer:")
    print(f"      https://testnet.xrpl.org/transactions/{tx_hash}")
else:
    print(f"    ✗ Transaction failed: {tx_result}")

# =============================================================================
# STEP 5: Verify Final Balances
# =============================================================================

print("\n[5] Checking final balances...")

balance_a_after = get_balance(client, wallet_a.address)
balance_b_after = get_balance(client, wallet_b.address)

print(f"    Wallet A: {balance_a_after} XRP (was {balance_a_before} XRP)")
print(f"    Wallet B: {balance_b_after} XRP (was {balance_b_before} XRP)")

# Calculate actual changes
change_a = float(balance_a_after) - float(balance_a_before)
change_b = float(balance_b_after) - float(balance_b_before)

print(f"\n    Balance changes:")
print(f"      Wallet A: {change_a:+.6f} XRP (sent {SEND_AMOUNT_XRP} + fee)")
print(f"      Wallet B: {change_b:+.6f} XRP (received {SEND_AMOUNT_XRP})")

# =============================================================================
# SUMMARY
# =============================================================================

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"""
Wallets Created:
  Wallet A: {wallet_a.address}
  Wallet B: {wallet_b.address}

Transaction:
  Sent {SEND_AMOUNT_XRP} XRP from A to B
  Result: {tx_result}

View accounts on testnet explorer:
  Wallet A: https://testnet.xrpl.org/accounts/{wallet_a.address}
  Wallet B: https://testnet.xrpl.org/accounts/{wallet_b.address}

Note: These are testnet wallets with test XRP (no real value).
      Testnet may reset periodically, so don't rely on persistence.
""")

print("✓ Test complete!")