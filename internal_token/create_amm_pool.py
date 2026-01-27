"""
AMM Pool Setup for AI Fund
Creates XRPL AMM pool for secondary trading
"""

from xrpl.clients import JsonRpcClient
from xrpl.wallet import Wallet
from xrpl.models.transactions import AMMCreate, AMMDeposit
from xrpl.models.amounts import IssuedCurrencyAmount
from xrpl.models.requests import AMMInfo
from xrpl.transaction import submit_and_wait
from xrpl.utils import xrp_to_drops
import os
from dotenv import load_dotenv
from decimal import Decimal

load_dotenv()

# Configuration
TESTNET_URL = "https://s.altnet.rippletest.net:51234/"
TOKEN_CURRENCY = os.getenv('TOKEN_CURRENCY_CODE', 'IND')
TOKEN_ISSUER = os.getenv('COLD_WALLET_ADDRESS', '')

print("=" * 60)
print("AMM POOL SETUP")
print("=" * 60)
print(f"Token: {TOKEN_CURRENCY}")
print(f"Issuer: {TOKEN_ISSUER}")
print()

def create_amm_pool():
    """
    Create AMM pool for IND/XRP trading
    
    Initial liquidity: 10,000 IND + 10,000 XRP (1:1 ratio)
    This allows investors to trade on secondary market
    """
    
    client = JsonRpcClient(TESTNET_URL)
    
    # Load hot wallet (has token inventory)
    hot_wallet_seed = os.getenv('HOT_WALLET_SEED')
    if not hot_wallet_seed:
        print("✗ HOT_WALLET_SEED not found in .env")
        return None
    
    hot_wallet = Wallet.from_seed(hot_wallet_seed)
    print(f"Using hot wallet: {hot_wallet.address}")
    
    # Check XRP balance
    from xrpl.models.requests import AccountInfo
    try:
        account_info = client.request(AccountInfo(
            account=hot_wallet.address,
            ledger_index="validated"
        ))
        xrp_balance = int(account_info.result["account_data"]["Balance"]) / 1_000_000
        print(f"Current XRP balance: {xrp_balance} XRP")
        
        if xrp_balance < 110:  # Need 100 XRP + 10 XRP reserve for AMM
            print(f"\n⚠️ WARNING: Low XRP balance!")
            print(f"   You have: {xrp_balance} XRP")
            print(f"   You need: ~110 XRP (100 for pool + 10 for AMM account reserve)")
            print(f"\n💡 Solution: Get more testnet XRP from faucet:")
            print(f"   https://faucet.altnet.rippletest.net/")
            print(f"   Enter address: {hot_wallet.address}")
            return None
    except Exception as e:
        print(f"⚠️ Could not check balance: {e}")
    
    # Pool parameters
    print("\n" + "=" * 60)
    print("Pool Configuration")
    print("=" * 60)
    
    token_amount = input("Enter IND token amount for pool (default 100): ").strip() or "100"
    xrp_amount = input("Enter XRP amount for pool (default 100): ").strip() or "100"
    trading_fee = input("Enter trading fee in basis points (default 50 = 0.5%): ").strip() or "50"
    
    print(f"\nCreating pool with:")
    print(f"  {token_amount} {TOKEN_CURRENCY}")
    print(f"  {xrp_amount} XRP")
    print(f"  Trading fee: {int(trading_fee)/100}%")
    
    confirm = input("\nProceed? (y/N): ")
    if confirm.lower() != 'y':
        print("Cancelled.")
        return None
    
    try:
        # Create AMM
        print("\nCreating AMM pool...")
        
        amm_create = AMMCreate(
            account=hot_wallet.address,
            amount=IssuedCurrencyAmount(
                currency=TOKEN_CURRENCY,
                issuer=TOKEN_ISSUER,
                value=token_amount
            ),
            amount2=xrp_to_drops(int(xrp_amount)),
            trading_fee=int(trading_fee)  # 50 = 0.5%
        )
        
        response = submit_and_wait(amm_create, client, hot_wallet)
        result = response.result["meta"]["TransactionResult"]
        
        if result == "tesSUCCESS":
            tx_hash = response.result["hash"]
            print(f"✓ AMM pool created!")
            print(f"  TX: {tx_hash}")
            print(f"  Explorer: https://testnet.xrpl.org/transactions/{tx_hash}")
            
            # Get AMM info
            print("\nFetching pool info...")
            amm_info_request = AMMInfo(
                asset=IssuedCurrencyAmount(
                    currency=TOKEN_CURRENCY,
                    issuer=TOKEN_ISSUER,
                    value="0"
                ),
                asset2={"currency": "XRP"}
            )
            
            amm_response = client.request(amm_info_request)
            amm_data = amm_response.result.get("amm", {})
            
            print("\n" + "=" * 60)
            print("POOL CREATED SUCCESSFULLY")
            print("=" * 60)
            print(f"\nAMM Account: {amm_data.get('account', 'N/A')}")
            print(f"LP Token: {amm_data.get('lp_token', {}).get('currency', 'N/A')}")
            print(f"Trading Fee: {amm_data.get('trading_fee', 0) / 100}%")
            
            # Save pool address to .env
            pool_address = amm_data.get('account', '')
            if pool_address:
                print(f"\n✓ Add to .env:")
                print(f"POOL_ADDRESS={pool_address}")
            
            return {
                'pool_address': pool_address,
                'tx_hash': tx_hash,
                'token_amount': token_amount,
                'xrp_amount': xrp_amount,
                'trading_fee': int(trading_fee)
            }
        else:
            print(f"✗ Failed: {result}")
            return None
            
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

def check_pool_exists():
    """Check if AMM pool already exists"""
    
    client = JsonRpcClient(TESTNET_URL)
    
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
            print("✓ Pool already exists!")
            print(f"  AMM Account: {amm_data.get('account', 'N/A')}")
            print(f"  LP Token: {amm_data.get('lp_token', {}).get('currency', 'N/A')}")
            return True
        else:
            return False
            
    except Exception as e:
        # Pool doesn't exist
        return False

if __name__ == "__main__":
    print("\nChecking for existing pool...")
    
    if check_pool_exists():
        print("\nPool already created. No action needed.")
        print("To view pool: Use XRPL explorer or call GET /api/pool/info")
    else:
        print("\nNo pool found. Creating new AMM pool...\n")
        result = create_amm_pool()
        
        if result:
            print("\n✓ Setup complete!")
            print("\nNext steps:")
            print("  1. Add POOL_ADDRESS to .env")
            print("  2. Update system_config table: pool_created = true")
            print("  3. Restart API server")
            print("  4. Test trading via frontend")
        else:
            print("\n✗ Setup failed")