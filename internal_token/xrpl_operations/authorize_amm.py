"""
Authorize the AMM's trust line
Required because issuer has RequireAuth enabled for KYC compliance
"""

from xrpl.clients import JsonRpcClient
from xrpl.wallet import Wallet
from xrpl.models.transactions import TrustSet, TrustSetFlag
from xrpl.models.amounts import IssuedCurrencyAmount
from xrpl.transaction import submit_and_wait
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from parent directory (internal_token/)
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

TESTNET_URL = "https://s.altnet.rippletest.net:51234/"
AMM_ACCOUNT = "r4rE1HozSpKMU6eXtS5Q4oSKkkXiMrotfA"  # Your AMM pool address
TOKEN_CURRENCY = os.getenv('TOKEN_CURRENCY_CODE', 'IND')

def authorize_amm_trustline():
    """Authorize the AMM's trust line to allow token trading"""
    
    client = JsonRpcClient(TESTNET_URL)
    
    # Load COLD wallet (the ISSUER)
    cold_wallet_seed = os.getenv('COLD_WALLET_SEED')
    if not cold_wallet_seed:
        print("✗ COLD_WALLET_SEED not found in .env")
        return False
    
    cold_wallet = Wallet.from_seed(cold_wallet_seed)
    print(f"Issuer account: {cold_wallet.address}")
    print(f"Authorizing AMM: {AMM_ACCOUNT}")
    print(f"Token: {TOKEN_CURRENCY}")
    
    # TrustSet with tfSetAuth flag to authorize the AMM
    trust_set = TrustSet(
        account=cold_wallet.address,
        limit_amount=IssuedCurrencyAmount(
            currency=TOKEN_CURRENCY,
            issuer=AMM_ACCOUNT,
            value="0"
        ),
        flags=TrustSetFlag.TF_SET_AUTH
    )
    
    try:
        print("\nSending authorization transaction...")
        response = submit_and_wait(trust_set, client, cold_wallet)
        result = response.result["meta"]["TransactionResult"]
        
        if result == "tesSUCCESS":
            tx_hash = response.result["hash"]
            print(f"\n✓ AMM trust line AUTHORIZED!")
            print(f"  TX: {tx_hash}")
            print(f"  Explorer: https://testnet.xrpl.org/transactions/{tx_hash}")
            print("\n🎉 IND->XRP swaps should now work!")
            return True
        else:
            print(f"✗ Failed: {result}")
            return False
            
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("AUTHORIZE AMM TRUST LINE")
    print("=" * 60)
    print()
    print("This script authorizes the AMM pool to trade your token.")
    print("Required because your issuer has RequireAuth enabled.")
    print()
    authorize_amm_trustline()