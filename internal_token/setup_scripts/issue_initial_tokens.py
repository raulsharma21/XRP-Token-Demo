"""
Initial Token Issuance Script
Issues tokens from cold wallet to hot wallet for IPO distribution
Run this ONCE after wallet setup
"""

from xrpl.clients import JsonRpcClient
from xrpl.wallet import Wallet
from xrpl.models.transactions import Payment, TrustSet
from xrpl.models.amounts import IssuedCurrencyAmount
from xrpl.transaction import submit_and_wait
from xrpl.models.requests import AccountLines
import os
from dotenv import load_dotenv
from decimal import Decimal

load_dotenv()

# Configuration
TESTNET_URL = "https://s.altnet.rippletest.net:51234/"
CURRENCY_CODE = os.getenv('TOKEN_CURRENCY_CODE', 'IND')

# Load wallets
cold_wallet_seed = os.getenv('COLD_WALLET_SEED')
hot_wallet_seed = os.getenv('HOT_WALLET_SEED')

if not cold_wallet_seed or not hot_wallet_seed:
    print("❌ Error: COLD_WALLET_SEED and HOT_WALLET_SEED must be set in .env")
    exit(1)

cold_wallet = Wallet.from_seed(cold_wallet_seed)
hot_wallet = Wallet.from_seed(hot_wallet_seed)

print("=" * 60)
print("INITIAL TOKEN ISSUANCE")
print("=" * 60)
print(f"\nToken: {CURRENCY_CODE}")
print(f"Issuer (Cold): {cold_wallet.address}")
print(f"Recipient (Hot): {hot_wallet.address}")
print()

# Connect to XRPL
client = JsonRpcClient(TESTNET_URL)

def check_trust_line():
    """Check if hot wallet has trust line to cold wallet"""
    try:
        response = client.request(AccountLines(
            account=hot_wallet.address,
            ledger_index="validated"
        ))
        
        lines = response.result.get("lines", [])
        
        for line in lines:
            if line["account"] == cold_wallet.address and line["currency"] == CURRENCY_CODE:
                return True, line
        
        return False, None
        
    except Exception as e:
        print(f"Error checking trust line: {e}")
        return False, None

def create_trust_line(limit: str):
    """Create trust line from hot wallet to cold wallet"""
    print(f"\n1. Creating trust line: Hot → Cold for {CURRENCY_CODE}...")
    
    trust_line_tx = TrustSet(
        account=hot_wallet.address,
        limit_amount=IssuedCurrencyAmount(
            currency=CURRENCY_CODE,
            issuer=cold_wallet.address,
            value=limit,
        ),
    )
    
    try:
        response = submit_and_wait(trust_line_tx, client, hot_wallet)
        result = response.result["meta"]["TransactionResult"]
        
        if result == "tesSUCCESS":
            print(f"   ✓ Trust line created")
            print(f"   Hot wallet can now hold up to {limit} {CURRENCY_CODE}")
            return True
        else:
            print(f"   ✗ Failed: {result}")
            return False
            
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False

def authorize_trust_line():
    """Authorize trust line from cold wallet side"""
    print(f"\n2. Authorizing trust line from issuer...")
    
    # The tfSetfAuth flag (0x00010000) tells XRPL to authorize this trust line
    TF_SET_AUTH = 0x00010000
    
    authorize_tx = TrustSet(
        account=cold_wallet.address,
        limit_amount=IssuedCurrencyAmount(
            currency=CURRENCY_CODE,
            issuer=hot_wallet.address,  # Note: issuer field is the OTHER account
            value="0",  # Issuer doesn't need to set a limit
        ),
        flags=TF_SET_AUTH,
    )
    
    try:
        response = submit_and_wait(authorize_tx, client, cold_wallet)
        result = response.result["meta"]["TransactionResult"]
        
        if result == "tesSUCCESS":
            print(f"   ✓ Trust line authorized")
            print(f"   Hot wallet can now receive {CURRENCY_CODE} tokens")
            return True
        else:
            print(f"   ✗ Failed: {result}")
            return False
            
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False

def issue_tokens(amount: str):
    """Issue tokens from cold wallet to hot wallet"""
    print(f"\n3. Issuing {amount} {CURRENCY_CODE} tokens...")
    
    issue_tx = Payment(
        account=cold_wallet.address,
        destination=hot_wallet.address,
        amount=IssuedCurrencyAmount(
            currency=CURRENCY_CODE,
            issuer=cold_wallet.address,
            value=amount,
        ),
    )
    
    try:
        response = submit_and_wait(issue_tx, client, cold_wallet)
        result = response.result["meta"]["TransactionResult"]
        
        if result == "tesSUCCESS":
            print(f"   ✓ Tokens issued!")
            print(f"   Transaction: {response.result['hash']}")
            print(f"\n   Cold wallet obligation: -{amount}")
            print(f"   Hot wallet balance: +{amount}")
            return True, response.result['hash']
        else:
            print(f"   ✗ Failed: {result}")
            return False, None
            
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False, None

def verify_balance():
    """Verify hot wallet token balance"""
    print(f"\n4. Verifying balance...")
    
    try:
        response = client.request(AccountLines(
            account=hot_wallet.address,
            ledger_index="validated"
        ))
        
        lines = response.result.get("lines", [])
        
        for line in lines:
            if line["account"] == cold_wallet.address and line["currency"] == CURRENCY_CODE:
                balance = line["balance"]
                print(f"   ✓ Hot wallet balance: {balance} {CURRENCY_CODE}")
                return balance
        
        print(f"   ⚠ No {CURRENCY_CODE} balance found")
        return "0"
        
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return "0"

def main():
    """Main issuance flow"""
    
    # Step 0: Check if trust line already exists
    print("Checking existing trust line...")
    exists, existing_line = check_trust_line()
    
    if exists:
        print(f"✓ Trust line already exists")
        print(f"  Current balance: {existing_line['balance']} {CURRENCY_CODE}")
        print(f"  Limit: {existing_line['limit']}")
        
        # Ask if they want to issue more
        current_balance = Decimal(existing_line['balance'])
        if current_balance > 0:
            print(f"\n⚠ Hot wallet already has {current_balance} {CURRENCY_CODE}")
            response = input("Issue more tokens? (y/N): ")
            if response.lower() != 'y':
                print("Cancelled.")
                return
    else:
        print("No trust line found. Will create one.")
    
    # Get issuance amount
    print("\n" + "=" * 60)
    print("How many tokens do you want to issue?")
    print("=" * 60)
    print("\nRecommendations:")
    print("  • For demo/testing: 1,000,000 (1M)")
    print("  • For small IPO: 10,000,000 (10M)")
    print("  • For production: Based on your total raise")
    print()
    
    amount_input = input("Enter amount (or press Enter for 1,000,000): ").strip()
    
    if not amount_input:
        amount = "1000000"
        print(f"Using default: {amount}")
    else:
        try:
            # Validate it's a number
            float(amount_input.replace(",", ""))
            amount = amount_input.replace(",", "")
        except ValueError:
            print("Invalid amount. Using default: 1,000,000")
            amount = "1000000"
    
    # Set trust line limit (should be >= issuance amount)
    trust_limit = str(int(float(amount) * 2))  # 2x the issuance for safety
    
    print(f"\n" + "=" * 60)
    print("STARTING ISSUANCE")
    print("=" * 60)
    print(f"Amount to issue: {amount} {CURRENCY_CODE}")
    print(f"Trust line limit: {trust_limit} {CURRENCY_CODE}")
    print()
    
    response = input("Proceed? (y/N): ")
    if response.lower() != 'y':
        print("Cancelled.")
        return
    
    # Execute issuance flow
    if not exists:
        # Create trust line
        if not create_trust_line(trust_limit):
            print("\n❌ Failed to create trust line")
            return
        
        # Authorize trust line
        if not authorize_trust_line():
            print("\n❌ Failed to authorize trust line")
            return
    
    # Issue tokens
    success, tx_hash = issue_tokens(amount)
    
    if not success:
        print("\n❌ Failed to issue tokens")
        return
    
    # Verify
    balance = verify_balance()
    
    # Summary
    print("\n" + "=" * 60)
    print("✓ ISSUANCE COMPLETE")
    print("=" * 60)
    print(f"\nToken: {CURRENCY_CODE}")
    print(f"Amount issued: {amount}")
    print(f"Hot wallet balance: {balance}")
    print(f"Transaction hash: {tx_hash}")
    
    # Explorer link
    print(f"\n🔗 View on explorer:")
    print(f"https://testnet.xrpl.org/transactions/{tx_hash}")
    
    print("\n✓ Hot wallet is now ready to distribute tokens to investors!")

if __name__ == "__main__":
    main()