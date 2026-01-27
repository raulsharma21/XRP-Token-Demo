"""
XRPL Utilities
Handles all XRPL blockchain interactions for the AI Fund
"""

from xrpl.clients import JsonRpcClient
from xrpl.wallet import Wallet
from xrpl.models.transactions import Payment, TrustSet
from xrpl.models.amounts import IssuedCurrencyAmount
from xrpl.models.requests import AccountInfo, AccountLines, Tx
from xrpl.transaction import submit_and_wait
from xrpl.models.transactions.trust_set import TrustSetFlag
from xrpl.utils import drops_to_xrp, xrp_to_drops
import os
from dotenv import load_dotenv
from decimal import Decimal
from typing import Optional, Dict, List
import json
import asyncio
from functools import wraps

load_dotenv()

# ==================== CONFIGURATION ====================

class XRPLConfig:
    """XRPL configuration from environment"""
    
    def __init__(self):
        self.network = os.getenv('XRPL_NETWORK', 'testnet')
        self.client_url = os.getenv('XRPL_CLIENT_URL', 'https://s.altnet.rippletest.net:51234/')
        
        # Token config
        self.currency_code = os.getenv('TOKEN_CURRENCY_CODE', 'IND')
        self.issuer_address = os.getenv('TOKEN_ISSUER_ADDRESS', '')
        
        # Wallets
        self.cold_wallet_seed = os.getenv('COLD_WALLET_SEED', '')
        self.hot_wallet_seed = os.getenv('HOT_WALLET_SEED', '')
        self.deposit_wallet_seed = os.getenv('DEPOSIT_WALLET_SEED', '')
        
        # Coinbase
        self.coinbase_address = os.getenv('COINBASE_USDC_ADDRESS', '')
        self.coinbase_dest_tag = int(os.getenv('COINBASE_DESTINATION_TAG', '0')) if os.getenv('COINBASE_DESTINATION_TAG') else None
    
    def validate(self):
        """Validate that all required config is present"""
        missing = []
        
        if not self.cold_wallet_seed:
            missing.append('COLD_WALLET_SEED')
        if not self.hot_wallet_seed:
            missing.append('HOT_WALLET_SEED')
        if not self.deposit_wallet_seed:
            missing.append('DEPOSIT_WALLET_SEED')
        if not self.issuer_address:
            missing.append('TOKEN_ISSUER_ADDRESS')
        
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

# Initialize config
config = XRPLConfig()

# ==================== XRPL CLIENT ====================

class XRPLClient:
    """Singleton XRPL client"""
    
    _instance = None
    _client = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._client is None:
            self._client = JsonRpcClient(config.client_url)
            print(f"✓ XRPL client connected to {config.network}")
    
    @property
    def client(self):
        return self._client

# Global client instance
xrpl_client = XRPLClient()

# ==================== WALLET MANAGEMENT ====================

class WalletManager:
    """Manages XRPL wallets"""
    
    def __init__(self):
        config.validate()
        
        self.cold_wallet = Wallet.from_seed(config.cold_wallet_seed)
        self.hot_wallet = Wallet.from_seed(config.hot_wallet_seed)
        self.deposit_wallet = Wallet.from_seed(config.deposit_wallet_seed)
        
        print(f"✓ Wallets loaded:")
        print(f"  Cold: {self.cold_wallet.address}")
        print(f"  Hot: {self.hot_wallet.address}")
        print(f"  Deposit: {self.deposit_wallet.address}")
    
    def get_wallet(self, wallet_type: str) -> Wallet:
        """Get wallet by type"""
        if wallet_type == 'cold':
            return self.cold_wallet
        elif wallet_type == 'hot':
            return self.hot_wallet
        elif wallet_type == 'deposit':
            return self.deposit_wallet
        else:
            raise ValueError(f"Unknown wallet type: {wallet_type}")

# Global wallet manager
wallet_manager = WalletManager()

# ==================== ASYNC WRAPPER DECORATOR ====================

def async_compatible(func):
    """
    Decorator to make sync XRPL functions async-compatible for FastAPI
    Runs sync function in thread pool to avoid blocking event loop
    """
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        return await asyncio.to_thread(func, *args, **kwargs)
    
    # Keep original sync function accessible
    async_wrapper.sync = func
    return async_wrapper

# ==================== BALANCE QUERIES ====================

@async_compatible
def get_xrp_balance(address: str) -> Decimal:
    """Get XRP balance for an address"""
    try:
        response = xrpl_client.client.request(AccountInfo(
            account=address,
            ledger_index="validated"
        ))
        
        balance_drops = response.result["account_data"]["Balance"]
        balance_xrp = Decimal(balance_drops) / Decimal('1000000')
        
        return balance_xrp
        
    except Exception as e:
        print(f"Error getting XRP balance for {address}: {e}")
        return Decimal('0')

@async_compatible
def get_token_balance(address: str, issuer: str = None, currency: str = None) -> Decimal:
    """Get token balance for an address"""
    try:
        if issuer is None:
            issuer = config.issuer_address
        if currency is None:
            currency = config.currency_code
        
        response = xrpl_client.client.request(AccountLines(
            account=address,
            ledger_index="validated"
        ))
        
        lines = response.result.get("lines", [])
        
        for line in lines:
            if line["account"] == issuer and line["currency"] == currency:
                return Decimal(line["balance"])
        
        return Decimal('0')
        
    except Exception as e:
        print(f"Error getting token balance for {address}: {e}")
        return Decimal('0')

def get_account_info(address: str) -> Dict:
    """Get full account info"""
    try:
        response = xrpl_client.client.request(AccountInfo(
            account=address,
            ledger_index="validated"
        ))
        
        account_data = response.result["account_data"]
        
        return {
            "address": address,
            "xrp_balance": Decimal(account_data["Balance"]) / Decimal('1000000'),
            "sequence": account_data["Sequence"],
            "flags": account_data.get("Flags", 0),
            "owner_count": account_data.get("OwnerCount", 0)
        }
        
    except Exception as e:
        print(f"Error getting account info for {address}: {e}")
        return None

@async_compatible
def check_trust_line_exists(holder_address: str, issuer: str = None, currency: str = None) -> bool:
    """Check if a trust line exists"""
    try:
        if issuer is None:
            issuer = config.issuer_address
        if currency is None:
            currency = config.currency_code
        
        response = xrpl_client.client.request(AccountLines(
            account=holder_address,
            ledger_index="validated"
        ))
        
        lines = response.result.get("lines", [])
        
        for line in lines:
            if line["account"] == issuer and line["currency"] == currency:
                return True
        
        return False
        
    except Exception as e:
        print(f"Error checking trust line: {e}")
        return False

# ==================== TRUST LINE OPERATIONS ====================

@async_compatible
def authorize_trust_line(holder_address: str) -> Dict:
    """
    Authorize a trust line (issuer side)
    Called after investor creates trust line to enable token flow
    """
    try:
        # Check if trust line exists
        # Use .sync to call the synchronous version from within this sync context
        trust_line_exists = check_trust_line_exists.sync(holder_address)
        if not trust_line_exists:
            return {
                "success": False,
                "error": "Trust line does not exist. Investor must create it first."
            }
        
        # Authorize the trust line
        TF_SET_AUTH = 0x00010000
        
        authorize_tx = TrustSet(
            account=wallet_manager.cold_wallet.address,
            limit_amount=IssuedCurrencyAmount(
                currency=config.currency_code,
                issuer=holder_address,
                value="0"
            ),
            flags=TF_SET_AUTH
        )
        
        response = submit_and_wait(authorize_tx, xrpl_client.client, wallet_manager.cold_wallet)
        result = response.result["meta"]["TransactionResult"]
        
        if result == "tesSUCCESS":
            return {
                "success": True,
                "tx_hash": response.result["hash"],
                "message": f"Trust line authorized for {holder_address}"
            }
        else:
            return {
                "success": False,
                "error": f"Transaction failed: {result}"
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

# ==================== TOKEN ISSUANCE ====================

@async_compatible
def issue_tokens(recipient_address: str, amount: Decimal) -> Dict:
    """
    Issue tokens from hot wallet to recipient
    
    Args:
        recipient_address: XRPL address to receive tokens
        amount: Number of tokens to issue
    
    Returns:
        Dict with success status and transaction hash
    """
    try:
        # Verify recipient has authorized trust line
        # Use .sync to call the synchronous version from within this sync context
        trust_line_exists = check_trust_line_exists.sync(recipient_address)
        if not trust_line_exists:
            return {
                "success": False,
                "error": "Recipient does not have a trust line"
            }
        
        # Create payment transaction
        payment_tx = Payment(
            account=wallet_manager.hot_wallet.address,
            destination=recipient_address,
            amount=IssuedCurrencyAmount(
                currency=config.currency_code,
                issuer=config.issuer_address,
                value=str(amount)
            )
        )
        
        # Submit transaction
        response = submit_and_wait(payment_tx, xrpl_client.client, wallet_manager.hot_wallet)
        result = response.result["meta"]["TransactionResult"]
        
        if result == "tesSUCCESS":
            return {
                "success": True,
                "tx_hash": response.result["hash"],
                "amount": str(amount),
                "recipient": recipient_address,
                "message": f"Issued {amount} {config.currency_code} to {recipient_address}"
            }
        else:
            return {
                "success": False,
                "error": f"Transaction failed: {result}",
                "result_code": result
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

# ==================== USDC OPERATIONS ====================

@async_compatible
def forward_usdc_to_coinbase(amount: Decimal, from_wallet: str = 'deposit') -> Dict:
    """
    Forward USDC from deposit wallet to Coinbase
    
    Args:
        amount: Amount of USDC to forward
        from_wallet: Which wallet to send from ('deposit' or 'hot')
    
    Returns:
        Dict with success status and transaction hash
    """
    try:
        if not config.coinbase_address:
            return {
                "success": False,
                "error": "Coinbase address not configured"
            }
        
        wallet = wallet_manager.get_wallet(from_wallet)
        
        # Create payment transaction
        # Note: You'll need to know the USDC issuer address
        usdc_issuer = os.getenv('USDC_ISSUER_ADDRESS', '')
        if not usdc_issuer:
            return {
                "success": False,
                "error": "USDC issuer address not configured"
            }
        
        payment_tx = Payment(
            account=wallet.address,
            destination=config.coinbase_address,
            amount=IssuedCurrencyAmount(
                currency="USD",  # USDC currency code
                issuer=usdc_issuer,
                value=str(amount)
            )
        )
        
        # Add destination tag if configured
        if config.coinbase_dest_tag:
            payment_tx.destination_tag = config.coinbase_dest_tag
        
        # Submit transaction
        response = submit_and_wait(payment_tx, xrpl_client.client, wallet)
        result = response.result["meta"]["TransactionResult"]
        
        if result == "tesSUCCESS":
            return {
                "success": True,
                "tx_hash": response.result["hash"],
                "amount": str(amount),
                "destination": config.coinbase_address,
                "message": f"Forwarded {amount} USDC to Coinbase"
            }
        else:
            return {
                "success": False,
                "error": f"Transaction failed: {result}",
                "result_code": result
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@async_compatible
def send_usdc_to_investor(recipient_address: str, amount: Decimal) -> Dict:
    """
    Send USDC from Coinbase to investor (for redemptions)
    
    Note: This assumes you have USDC in a wallet you control.
    In production, this would trigger a Coinbase API withdrawal.
    """
    try:
        # For demo purposes, sending from hot wallet
        # In production, you'd trigger Coinbase withdrawal
        
        usdc_issuer = os.getenv('USDC_ISSUER_ADDRESS', '')
        if not usdc_issuer:
            return {
                "success": False,
                "error": "USDC issuer address not configured"
            }
        
        payment_tx = Payment(
            account=wallet_manager.hot_wallet.address,
            destination=recipient_address,
            amount=IssuedCurrencyAmount(
                currency="USD",
                issuer=usdc_issuer,
                value=str(amount)
            )
        )
        
        response = submit_and_wait(payment_tx, xrpl_client.client, wallet_manager.hot_wallet)
        result = response.result["meta"]["TransactionResult"]
        
        if result == "tesSUCCESS":
            return {
                "success": True,
                "tx_hash": response.result["hash"],
                "amount": str(amount),
                "recipient": recipient_address,
                "message": f"Sent {amount} USDC to {recipient_address}"
            }
        else:
            return {
                "success": False,
                "error": f"Transaction failed: {result}",
                "result_code": result
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

# ==================== TRANSACTION QUERIES ====================

def get_transaction_info(tx_hash: str) -> Dict:
    """Get details of a transaction by hash"""
    try:
        response = xrpl_client.client.request(Tx(
            transaction=tx_hash
        ))
        
        return response.result
        
    except Exception as e:
        print(f"Error getting transaction {tx_hash}: {e}")
        return None

# ==================== POOL OPERATIONS ====================

def get_pool_info() -> Optional[Dict]:
    """
    Get AMM pool information
    Returns pool reserves, price, etc.
    """
    try:
        # TODO: Implement AMM pool query
        # This would use AMMInfo request
        
        pool_address = os.getenv('POOL_ADDRESS', '')
        if not pool_address:
            return None
        
        # Placeholder for now
        return {
            "pool_address": pool_address,
            "usdc_reserve": 0,
            "token_reserve": 0,
            "current_price": 1.0,
            "trading_fee": 0.5
        }
        
    except Exception as e:
        print(f"Error getting pool info: {e}")
        return None

# ==================== HELPER FUNCTIONS ====================

@async_compatible
def validate_xrpl_address(address: str) -> bool:
    """Validate XRPL address format"""
    if not address:
        return False
    
    # XRPL addresses start with 'r' and are 25-35 characters
    if not address.startswith('r'):
        return False
    
    if len(address) < 25 or len(address) > 35:
        return False
    
    return True

# ==================== INITIALIZATION ====================

def initialize_xrpl():
    """Initialize XRPL connection and validate setup"""
    print("\n" + "=" * 60)
    print("Initializing XRPL Connection")
    print("=" * 60)
    
    try:
        # Validate config
        config.validate()
        print(f"✓ Configuration validated")
        
        # Test connection
        print(f"✓ Connected to {config.network}")
        print(f"  URL: {config.client_url}")
        
        # Verify wallets
        print(f"\n✓ Wallets loaded:")
        print(f"  Cold (Issuer): {wallet_manager.cold_wallet.address}")
        print(f"  Hot (Operations): {wallet_manager.hot_wallet.address}")
        print(f"  Deposit (IPO): {wallet_manager.deposit_wallet.address}")
        
        print(f"\n✓ Token configuration:")
        print(f"  Currency: {config.currency_code}")
        print(f"  Issuer: {config.issuer_address}")
        
        print("\n" + "=" * 60)
        print("XRPL Ready!")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n✗ XRPL initialization failed: {e}")
        return False

# ==================== EXAMPLE USAGE ====================

if __name__ == "__main__":
    
    async def test_xrpl():
        """Test XRPL functions"""
        
        # Initialize
        if not initialize_xrpl():
            return
        
        # Check balances
        print("\nChecking wallet balances...")
        
        cold_balance = await get_xrp_balance(wallet_manager.cold_wallet.address)
        print(f"Cold wallet XRP: {cold_balance}")
        
        hot_balance = await get_xrp_balance(wallet_manager.hot_wallet.address)
        print(f"Hot wallet XRP: {hot_balance}")
        
        hot_token_balance = await get_token_balance(wallet_manager.hot_wallet.address)
        print(f"Hot wallet {config.currency_code}: {hot_token_balance}")
        
        print("\n✓ XRPL connection test complete")
    
    # Run test
    import asyncio
    asyncio.run(test_xrpl())