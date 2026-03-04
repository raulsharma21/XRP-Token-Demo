"""
Trading Account Client Interface
Handles balance queries and fee withdrawals from trading account

This module provides an abstract interface for trading account operations
with a manual implementation for testing. Real exchange API integration
(Coinbase, etc.) can be added by implementing the same interface.
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Dict, Optional
from datetime import datetime
import asyncio

# Import database for persistence
from database import SystemConfigDB


# ==================== ABSTRACT INTERFACE ====================

class TradingAccountClient(ABC):
    """
    Abstract interface for trading account operations

    All trading account implementations must provide:
    - get_balance(): Query current balance
    - withdraw_fees(): Withdraw fees to creator wallet
    """

    @abstractmethod
    async def get_balance(self) -> Decimal:
        """
        Get current trading account balance

        Returns:
            Decimal: Current balance in USD (or USDC equivalent)
        """
        pass

    @abstractmethod
    async def withdraw_fees(self, amount: Decimal, destination: str, reason: str = "fee_collection") -> Dict:
        """
        Withdraw fees from trading account

        Args:
            amount: Amount to withdraw (in USD/USDC)
            destination: Destination wallet address
            reason: Reason for withdrawal (e.g., "fee_collection", "redemption")

        Returns:
            Dict with:
                - success: bool
                - tx_hash: Optional[str] (transaction hash if real withdrawal)
                - new_balance: Decimal (balance after withdrawal)
                - message: str
        """
        pass

    async def get_info(self) -> Dict:
        """
        Get information about the trading account client

        Returns:
            Dict with client type, status, and other metadata
        """
        return {
            "type": self.__class__.__name__,
            "is_placeholder": isinstance(self, ManualBalanceClient)
        }


# ==================== MANUAL IMPLEMENTATION (FOR TESTING) ====================

class ManualBalanceClient(TradingAccountClient):
    """
    Manual balance client for testing

    Stores balance in system_config table for persistence.
    Allows manual balance updates via set_balance().
    Fee withdrawals are simulated (logged but not sent to blockchain).

    Usage:
        client = ManualBalanceClient()
        await client.initialize()

        # Set initial balance
        await client.set_balance(Decimal('100000'))

        # Query balance
        balance = await client.get_balance()

        # Simulate fee withdrawal
        result = await client.withdraw_fees(
            amount=Decimal('1000'),
            destination='rCreatorWallet...',
            reason='daily_fees'
        )
    """

    CONFIG_KEY_BALANCE = 'trading_account_balance'
    CONFIG_KEY_LAST_WITHDRAWAL = 'trading_account_last_withdrawal'
    DEFAULT_BALANCE = Decimal('100000')  # Default test balance

    def __init__(self):
        """Initialize manual balance client"""
        self._initialized = False

    async def initialize(self) -> None:
        """
        Initialize client and set default balance if none exists

        Call this once after creating the client
        """
        existing_balance = await SystemConfigDB.get(self.CONFIG_KEY_BALANCE)

        if existing_balance is None:
            # First time setup - set default balance
            await SystemConfigDB.set(
                self.CONFIG_KEY_BALANCE,
                str(self.DEFAULT_BALANCE)
            )
            print(f"✓ Initialized manual trading account with ${self.DEFAULT_BALANCE:,.2f}")

        self._initialized = True

    async def get_balance(self) -> Decimal:
        """
        Get current trading account balance from database

        Returns:
            Decimal: Current balance
        """
        if not self._initialized:
            await self.initialize()

        balance_str = await SystemConfigDB.get(self.CONFIG_KEY_BALANCE)

        if balance_str is None:
            # Fallback to default
            return self.DEFAULT_BALANCE

        return Decimal(balance_str)

    async def set_balance(self, new_balance: Decimal) -> None:
        """
        Manually set trading account balance

        Args:
            new_balance: New balance to set

        Raises:
            ValueError: If balance is negative
        """
        if new_balance < 0:
            raise ValueError("Balance cannot be negative")

        if not self._initialized:
            await self.initialize()

        await SystemConfigDB.set(
            self.CONFIG_KEY_BALANCE,
            str(new_balance)
        )

        print(f"✓ Updated trading account balance to ${new_balance:,.2f}")

    async def withdraw_fees(
        self,
        amount: Decimal,
        destination: str,
        reason: str = "fee_collection"
    ) -> Dict:
        """
        Simulate fee withdrawal

        Deducts amount from balance but doesn't actually send funds.
        Logs the withdrawal for record-keeping.

        Args:
            amount: Amount to withdraw
            destination: Destination wallet address
            reason: Reason for withdrawal

        Returns:
            Dict with success status and simulated tx hash
        """
        if amount < 0:
            return {
                "success": False,
                "error": "Withdrawal amount cannot be negative",
                "new_balance": await self.get_balance()
            }

        if amount == 0:
            return {
                "success": True,
                "tx_hash": None,
                "new_balance": await self.get_balance(),
                "message": "No withdrawal needed (amount = 0)"
            }

        current_balance = await self.get_balance()

        if amount > current_balance:
            return {
                "success": False,
                "error": f"Insufficient balance: ${current_balance:,.2f} available, ${amount:,.2f} requested",
                "new_balance": current_balance
            }

        # Deduct from balance
        new_balance = current_balance - amount
        await self.set_balance(new_balance)

        # Generate simulated tx hash (for logging purposes)
        simulated_tx_hash = f"simulated-{datetime.utcnow().timestamp():.0f}-{reason}"

        # Log the withdrawal
        withdrawal_log = {
            "timestamp": datetime.utcnow().isoformat(),
            "amount": str(amount),
            "destination": destination,
            "reason": reason,
            "balance_before": str(current_balance),
            "balance_after": str(new_balance),
            "simulated": True
        }

        await SystemConfigDB.set(
            self.CONFIG_KEY_LAST_WITHDRAWAL,
            str(withdrawal_log)
        )

        print(f"[SIMULATED WITHDRAWAL]")
        print(f"  Amount: ${amount:,.2f}")
        print(f"  Reason: {reason}")
        print(f"  Destination: {destination}")
        print(f"  Balance: ${current_balance:,.2f} → ${new_balance:,.2f}")
        print(f"  Simulated TX: {simulated_tx_hash}")

        return {
            "success": True,
            "tx_hash": simulated_tx_hash,
            "new_balance": new_balance,
            "amount": amount,
            "simulated": True,
            "message": f"Simulated withdrawal of ${amount:,.2f} for {reason}"
        }

    async def get_info(self) -> Dict:
        """Get information about this manual client"""
        info = await super().get_info()
        info.update({
            "initialized": self._initialized,
            "current_balance": str(await self.get_balance()) if self._initialized else None,
            "persistence": "system_config table"
        })
        return info


# ==================== FUTURE IMPLEMENTATIONS ====================

class CoinbaseClient(TradingAccountClient):
    """
    Placeholder for future Coinbase API integration

    To implement:
    1. Initialize with Coinbase API credentials
    2. Implement get_balance() using Coinbase API
    3. Implement withdraw_fees() to trigger real withdrawals
    4. Handle authentication, rate limiting, errors

    Example implementation outline:

    ```python
    def __init__(self, api_key: str, api_secret: str):
        self.client = CoinbaseClient(api_key, api_secret)

    async def get_balance(self) -> Decimal:
        # Query Coinbase account balance
        accounts = self.client.get_accounts()
        usdc_account = next(a for a in accounts if a.currency == 'USDC')
        return Decimal(usdc_account.balance.amount)

    async def withdraw_fees(self, amount, destination, reason):
        # Create real XRPL withdrawal via Coinbase
        withdrawal = self.client.create_withdrawal(
            amount=str(amount),
            currency='USDC',
            crypto_address=destination
        )
        return {
            'success': True,
            'tx_hash': withdrawal.id,
            'new_balance': await self.get_balance()
        }
    ```
    """

    def __init__(self):
        raise NotImplementedError(
            "CoinbaseClient not yet implemented. Use ManualBalanceClient for testing."
        )

    async def get_balance(self) -> Decimal:
        raise NotImplementedError()

    async def withdraw_fees(self, amount: Decimal, destination: str, reason: str = "fee_collection") -> Dict:
        raise NotImplementedError()


# ==================== FACTORY FUNCTION ====================

async def get_trading_client(client_type: str = "manual") -> TradingAccountClient:
    """
    Factory function to create trading account client

    Args:
        client_type: Type of client ("manual", "coinbase", etc.)

    Returns:
        Initialized TradingAccountClient instance

    Example:
        client = await get_trading_client("manual")
        balance = await client.get_balance()
    """
    if client_type == "manual":
        client = ManualBalanceClient()
        await client.initialize()
        return client
    elif client_type == "coinbase":
        raise NotImplementedError("Coinbase client not yet implemented")
    else:
        raise ValueError(f"Unknown client type: {client_type}")


# ==================== TESTING ====================

async def test_manual_client():
    """Test manual balance client"""
    from database import init_database, close_database

    print("\n" + "=" * 60)
    print("Testing Manual Trading Account Client")
    print("=" * 60)

    # Initialize database
    await init_database()

    try:
        # Initialize client
        client = ManualBalanceClient()
        await client.initialize()

        # Get info
        info = await client.get_info()
        print(f"\nClient Info: {info}")

        # Get initial balance
        balance = await client.get_balance()
        print(f"\nInitial Balance: ${balance:,.2f}")

        # Set a test balance
        print("\nSetting balance to $150,000...")
        await client.set_balance(Decimal('150000'))

        # Verify new balance
        balance = await client.get_balance()
        print(f"New Balance: ${balance:,.2f}")

        # Test fee withdrawal
        print("\nSimulating fee withdrawal of $1,000...")
        result = await client.withdraw_fees(
            amount=Decimal('1000'),
            destination='rCreatorWallet123',
            reason='daily_management_fees'
        )

        print(f"\nWithdrawal Result:")
        print(f"  Success: {result['success']}")
        print(f"  TX Hash: {result['tx_hash']}")
        print(f"  New Balance: ${result['new_balance']:,.2f}")

        # Test insufficient balance
        print("\nTesting insufficient balance (trying to withdraw $200,000)...")
        result = await client.withdraw_fees(
            amount=Decimal('200000'),
            destination='rCreatorWallet123',
            reason='test_insufficient'
        )

        print(f"\nWithdrawal Result:")
        print(f"  Success: {result['success']}")
        print(f"  Error: {result.get('error', 'None')}")

        print("\n" + "=" * 60)
        print("Manual Client Tests Complete!")
        print("=" * 60)

    finally:
        await close_database()


if __name__ == "__main__":
    # Run tests
    import sys
    sys.path.append('..')

    asyncio.run(test_manual_client())
