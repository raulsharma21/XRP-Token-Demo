"""
XRPL Transaction Monitor
Watches deposit wallet for incoming USDC and automatically processes purchases
"""

from xrpl.clients import JsonRpcClient
from xrpl.wallet import Wallet
from xrpl.models.transactions import Payment
from xrpl.models.amounts import IssuedCurrencyAmount
from xrpl.models.requests import AccountTx, Subscribe, Unsubscribe
from xrpl.transaction import submit_and_wait
from xrpl.asyncio.clients import AsyncWebsocketClient
import asyncio
import os
from dotenv import load_dotenv
from decimal import Decimal
from datetime import datetime
import sys

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import our modules
from database import (
    db, init_database,
    PurchaseDB, InvestorDB, RedemptionDB, FundStateDB, SystemConfigDB
)
from xrpl_utils import (
    wallet_manager,
    config as xrpl_config,
    issue_tokens,
    forward_usdc_to_coinbase
)
from redemption_processor import detect_and_process_redemption
from fee_calculator import calculate_subscription_tokens

load_dotenv()

# Configuration
TESTNET_WS_URL = "wss://s.altnet.rippletest.net:51233/"
MAINNET_WS_URL = "wss://s1.ripple.com:51233/"

USE_TESTNET = os.getenv('XRPL_NETWORK', 'testnet') == 'testnet'
WS_URL = TESTNET_WS_URL if USE_TESTNET else MAINNET_WS_URL

# USDC issuer (you'll need to set this)
USDC_ISSUER = os.getenv('USDC_ISSUER_ADDRESS', '')

print("=" * 60)
print("XRPL TRANSACTION MONITOR")
print("=" * 60)
print(f"Network: {'TESTNET' if USE_TESTNET else 'MAINNET'}")
print(f"Monitoring: {wallet_manager.deposit_wallet.address}")
print(f"Token: {xrpl_config.currency_code}")
print("=" * 60)

class TransactionMonitor:
    """Monitors XRPL transactions and processes deposits and redemptions"""

    def __init__(self):
        self.deposit_address = wallet_manager.deposit_wallet.address
        self.issuer_address = wallet_manager.cold_wallet.address  # Issuer = cold wallet
        self.running = False
        self.processed_txs = set()  # Track processed transactions
    
    async def process_usdc_deposit(self, message: dict):
        """
        Process incoming USDC deposit
        
        Steps:
        1. Find matching purchase record by destination tag
        2. Verify amount matches
        3. Forward USDC to Coinbase
        4. Issue tokens to investor
        5. Update purchase status
        """
        try:
            # Extract transaction details from message
            tx = message.get('tx_json') or message.get('transaction')
            if not tx:
                print("✗ No transaction data in message")
                return
            
            tx_hash = message.get('hash')
            amount_data = tx.get('Amount') or tx.get('DeliverMax')
            destination = tx.get('Destination')
            destination_tag = tx.get('DestinationTag')
            sender = tx.get('Account')
            
            print(f"\n{'='*60}")
            print(f"Processing deposit transaction: {tx_hash}")
            print(f"{'='*60}")
            
            # Verify it's to our deposit wallet
            if destination != self.deposit_address:
                print(f"⊘ Not for deposit wallet, skipping")
                return
            
            # Check if already processed
            if tx_hash in self.processed_txs:
                print(f"⊘ Already processed, skipping")
                return
            
            # Parse amount
            if isinstance(amount_data, dict):
                # Issued currency (USDC, tokens, etc.)
                currency = amount_data.get('currency')
                issuer = amount_data.get('issuer')
                value = amount_data.get('value')
                
                print(f"Amount: {value} {currency}")
                print(f"Issuer: {issuer}")
                print(f"From: {sender}")
                print(f"Destination Tag: {destination_tag}")
                
                # For now, we'll accept any issued currency as "USDC-like"
                # In production, verify issuer == USDC_ISSUER
                if USDC_ISSUER and issuer != USDC_ISSUER:
                    print(f"⚠ Warning: Issuer doesn't match configured USDC issuer")
                    print(f"  Expected: {USDC_ISSUER}")
                    print(f"  Got: {issuer}")
                
                usdc_amount = Decimal(value)
                
            else:
                # XRP payment (in drops)
                drops = int(amount_data)
                xrp_amount = Decimal(drops) / Decimal('1000000')
                
                print(f"Amount: {xrp_amount} XRP ({drops} drops)")
                print(f"From: {sender}")
                print(f"Destination Tag: {destination_tag}")
                
                # On testnet, accept XRP as proxy for USDC
                print(f"⚠ XRP payment detected - treating as testnet USDC proxy")
                usdc_amount = xrp_amount
            
            # Find purchase record by destination tag
            if not destination_tag:
                print(f"✗ No destination tag - cannot match to purchase")
                print(f"  Manual intervention required for {tx_hash}")
                return
            
            purchase = await PurchaseDB.get_pending_by_tag(destination_tag)
            
            if not purchase:
                print(f"✗ No pending purchase found for destination tag {destination_tag}")
                print(f"  Manual intervention required for {tx_hash}")
                return
            
            print(f"✓ Found purchase: {purchase['id']}")
            
            # Verify amount matches (within 1% tolerance for fees)
            expected_amount = Decimal(str(purchase['usdc_amount']))
            tolerance = expected_amount * Decimal('0.01')
            
            if abs(usdc_amount - expected_amount) > tolerance:
                print(f"⚠ Amount mismatch!")
                print(f"  Expected: {expected_amount}")
                print(f"  Received: {usdc_amount}")
                print(f"  Difference: {abs(usdc_amount - expected_amount)}")
                # Continue anyway, but log it
            
            # Get investor info
            investor = await InvestorDB.get_by_id(purchase['investor_id'])
            if not investor:
                print(f"✗ Investor not found: {purchase['investor_id']}")
                return
            
            print(f"Investor: {investor['email']} ({investor['xrpl_address']})")
            
            # Update purchase status to 'forwarded'
            await PurchaseDB.update_status(
                purchase_id=str(purchase['id']),
                status='forwarded',
                deposit_tx_hash=tx_hash
            )
            
            # Step 1: Forward USDC to Coinbase (skip for testnet if no Coinbase setup)
            print(f"\n1. Forwarding USDC to Coinbase...")
            if xrpl_config.coinbase_address and USDC_ISSUER:
                forward_result = await forward_usdc_to_coinbase(usdc_amount, from_wallet='deposit')
                
                if forward_result['success']:
                    print(f"   ✓ Forwarded {usdc_amount} USDC")
                    print(f"   TX: {forward_result['tx_hash']}")
                    forward_tx_hash = forward_result['tx_hash']
                else:
                    print(f"   ✗ Forward failed: {forward_result['error']}")
                    forward_tx_hash = None
                    # Continue anyway to issue tokens
            else:
                print(f"   ⊘ Skipping forward (Coinbase not configured for testnet)")
                forward_tx_hash = None
            
            # Step 2: Calculate token amount based on current NAV
            print(f"\n2. Calculating token amount...")

            # Check if IPO is active
            ipo_phase = await SystemConfigDB.get('ipo_phase')
            is_ipo_active = ipo_phase == 'active' if ipo_phase else True

            if is_ipo_active:
                # IPO phase: Fixed $1.00 pricing (1:1 ratio)
                current_nav = Decimal('1.00')
                token_amount = usdc_amount
                print(f"   IPO phase: Using fixed $1.00 pricing")
            else:
                # Post-IPO: Use current NAV
                current_nav = await FundStateDB.get_current_nav_value()
                token_amount = calculate_subscription_tokens(usdc_amount, current_nav)
                print(f"   Post-IPO: Using dynamic NAV ${current_nav:.8f}")

            print(f"   USDC: ${usdc_amount}")
            print(f"   NAV: ${current_nav:.8f}")
            print(f"   Tokens to issue: {token_amount}")

            # Step 3: Issue tokens to investor
            print(f"\n3. Issuing tokens to investor...")

            issue_result = await issue_tokens(investor['xrpl_address'], token_amount)
            
            if issue_result['success']:
                print(f"   ✓ Issued {token_amount} {xrpl_config.currency_code}")
                print(f"   TX: {issue_result['tx_hash']}")
                
                # Update purchase as completed
                await PurchaseDB.update_status(
                    purchase_id=str(purchase['id']),
                    status='completed',
                    forward_tx_hash=forward_tx_hash,
                    issue_tx_hash=issue_result['tx_hash'],
                    token_amount=token_amount
                )
                
                print(f"\n✓ Purchase completed successfully!")
                print(f"  Investor: {investor['email']}")
                print(f"  Tokens issued: {token_amount} {xrpl_config.currency_code}")
                
                # Mark as processed
                self.processed_txs.add(tx_hash)
                
            else:
                print(f"   ✗ Token issuance failed: {issue_result['error']}")
                
                # Update status as failed
                await PurchaseDB.update_status(
                    purchase_id=str(purchase['id']),
                    status='failed',
                    forward_tx_hash=forward_tx_hash
                )
                
                print(f"✗ Purchase failed - manual intervention required")
            
        except Exception as e:
            print(f"✗ Error processing deposit: {e}")
            import traceback
            traceback.print_exc()

    async def process_token_redemption(self, message: dict):
        """
        Process incoming IND token redemption

        Steps:
        1. Find matching redemption record by destination tag
        2. Verify token amount
        3. Calculate USDC owed (tokens × NAV)
        4. Send USDC to investor
        5. Update redemption status
        """
        try:
            # Extract transaction details
            tx = message.get('tx_json') or message.get('transaction')
            if not tx:
                print("✗ No transaction data in message")
                return

            tx_hash = message.get('hash')
            amount_data = tx.get('Amount') or tx.get('DeliverMax')
            destination = tx.get('Destination')
            destination_tag = tx.get('DestinationTag')
            sender = tx.get('Account')

            print(f"\n{'='*60}")
            print(f"Processing redemption transaction: {tx_hash}")
            print(f"{'='*60}")

            # Verify it's to our issuer wallet
            if destination != self.issuer_address:
                print(f"⊘ Not for issuer wallet, skipping")
                return

            # Check if already processed
            if tx_hash in self.processed_txs:
                print(f"⊘ Already processed, skipping")
                return

            # Parse amount - should be IND tokens
            if isinstance(amount_data, dict):
                currency = amount_data.get('currency')
                issuer = amount_data.get('issuer')
                value = amount_data.get('value')

                print(f"Amount: {value} {currency}")
                print(f"Issuer: {issuer}")
                print(f"From: {sender}")
                print(f"Destination Tag: {destination_tag}")

                # Verify it's IND tokens
                if currency != xrpl_config.currency_code:
                    print(f"⊘ Wrong currency (expected {xrpl_config.currency_code}, got {currency})")
                    return

                if issuer != self.issuer_address:
                    print(f"⊘ Wrong issuer (expected {self.issuer_address}, got {issuer})")
                    return

                token_amount = Decimal(value)

            else:
                # XRP payment - not a redemption
                print(f"⊘ XRP payment, not a token redemption")
                return

            # Process redemption via redemption_processor
            success = await detect_and_process_redemption(
                tx_hash=tx_hash,
                sender=sender,
                destination=destination,
                destination_tag=destination_tag,
                token_amount=token_amount,
                issuer_address=self.issuer_address
            )

            if success:
                # Mark as processed
                self.processed_txs.add(tx_hash)
                print(f"\n✓ Redemption processed successfully")
            else:
                print(f"\n✗ Redemption processing failed - may need manual intervention")

        except Exception as e:
            print(f"✗ Error processing redemption: {e}")
            import traceback
            traceback.print_exc()

    async def handle_transaction(self, message: dict):
        """Handle incoming transaction from websocket"""
        try:
            print(f"\nDEBUG: Received message type: {message.get('type')}")
            
            # Check if this is a transaction notification
            if message.get('type') != 'transaction':
                print(f"DEBUG: Skipping - not a transaction message")
                return
            
            # Get transaction data (websocket uses tx_json, not transaction)
            tx = message.get('tx_json') or message.get('transaction')
            if not tx:
                print(f"DEBUG: No transaction data found")
                return
            
            # Add hash to tx if not present
            if 'hash' not in tx and 'hash' in message:
                tx['hash'] = message['hash']
            
            print(f"DEBUG: Transaction type: {tx.get('TransactionType')}")
            print(f"DEBUG: Hash: {tx.get('hash')}")
            
            # Only process successful Payment transactions
            if tx.get('TransactionType') != 'Payment':
                print(f"DEBUG: Skipping - not a Payment")
                return
            
            # Check if validated
            validated = message.get('validated', False)
            print(f"DEBUG: Validated: {validated}")
            if not validated:
                print(f"⊘ Transaction not yet validated, waiting...")
                return
            
            # Check transaction result
            meta = message.get('meta', {})
            result = meta.get('TransactionResult')
            print(f"DEBUG: Transaction result: {result}")
            
            if result != 'tesSUCCESS':
                print(f"⊘ Transaction failed: {result}")
                return
            
            # Route based on destination
            tx = message.get('tx_json') or message.get('transaction')
            destination = tx.get('Destination')

            if destination == self.deposit_address:
                print(f"DEBUG: Routing to USDC deposit handler...")
                await self.process_usdc_deposit(message)
            elif destination == self.issuer_address:
                print(f"DEBUG: Routing to redemption handler...")
                await self.process_token_redemption(message)
            else:
                print(f"DEBUG: Transaction not for monitored wallets, skipping")
            
        except Exception as e:
            print(f"Error handling transaction: {e}")
            import traceback
            traceback.print_exc()
    
    async def start_monitoring(self):
        """Start monitoring the deposit wallet via websocket"""
        
        print(f"\nConnecting to XRPL websocket...")
        print(f"URL: {WS_URL}\n")
        
        async with AsyncWebsocketClient(WS_URL) as client:
            print(f"✓ Connected to XRPL")
            
            # Subscribe to both deposit wallet (for subscriptions) and issuer wallet (for redemptions)
            subscribe_request = Subscribe(
                accounts=[self.deposit_address, self.issuer_address]
            )

            await client.send(subscribe_request)
            print(f"✓ Subscribed to deposit wallet: {self.deposit_address}")
            print(f"✓ Subscribed to issuer wallet: {self.issuer_address}")
            print(f"\n🔍 Monitoring for:")
            print(f"   - USDC deposits (subscriptions)")
            print(f"   - IND token payments (redemptions)")
            print(f"   Press Ctrl+C to stop\n")
            
            self.running = True
            
            # Listen for messages
            async for message in client:
                if not self.running:
                    break
                
                try:
                    await self.handle_transaction(message)
                except Exception as e:
                    print(f"Error in message loop: {e}")
                    continue
    
    async def check_missed_payments(self):
        """
        Check XRPL for payments that arrived while monitor was down
        Matches XRPL transactions to pending purchases by destination tag
        """
        print("\nChecking for missed payments on startup...")
        
        from xrpl.asyncio.clients import AsyncJsonRpcClient
        
        try:
            # Step 1: Get all pending purchases
            pending = await PurchaseDB.get_all_pending()
            
            if not pending:
                print("No pending purchases found.")
                return
            
            print(f"Found {len(pending)} pending purchase(s)")
            
            # Step 2: Get account transactions with proper parameters
            client = AsyncJsonRpcClient(xrpl_config.client_url)
            
            # Request more transactions by specifying ledger range
            response = await client.request(AccountTx(
                account=self.deposit_address,
                ledger_index_min=-1,  # earliest ledger
                ledger_index_max=-1,  # latest ledger  
                limit=400
            ))
            
            all_txs = response.result.get('transactions', [])
            print(f"  Fetched {len(all_txs)} transactions from XRPL")
                
            # Step 3: For each pending purchase, search for matching transaction
            for purchase in pending:
                dest_tag = purchase['destination_tag']
                print(f"\n  Searching for payment with destination tag {dest_tag}...")
                
                # Search for matching transaction
                matched_tx = None
                for tx_data in all_txs:
                    # Use tx_json not tx!
                    tx = tx_data.get('tx_json', {})
                    meta = tx_data.get('meta', {})
                    tx_hash = tx_data.get('hash')
                    
                    # Check if this is our payment
                    if (tx.get('TransactionType') == 'Payment' and
                        tx.get('Destination') == self.deposit_address and
                        tx.get('DestinationTag') == dest_tag and
                        meta.get('TransactionResult') == 'tesSUCCESS'):
                        
                        matched_tx = {
                            'tx': tx,
                            'meta': meta,
                            'hash': tx_hash
                        }
                        break
                
                # Step 4: If found, process the payment
                if matched_tx:
                    tx_hash = matched_tx['hash']
                    print(f"    ✓ Found transaction: {tx_hash}")
                    
                    # Check if this transaction was already processed in another purchase
                    existing_purchase = await PurchaseDB.get_by_deposit_tx(tx_hash)
                    if existing_purchase:
                        print(f"    ⊘ Transaction already processed in purchase {existing_purchase['id']}")
                        print(f"       Skipping to avoid duplicate issuance")
                        continue
                    
                    # Create message structure for process_usdc_deposit
                    message = {
                        'type': 'transaction',
                        'tx_json': matched_tx['tx'],
                        'hash': tx_hash,
                        'meta': matched_tx['meta'],
                        'validated': True
                    }
                    
                    # Process the deposit
                    await self.process_usdc_deposit(message)
                else:
                    print(f"    ⊘ Payment not found (not yet sent)")
            
            print("\n✓ Missed payment check complete")
            
        except Exception as e:
            print(f"Error checking missed payments: {e}")
            import traceback
            traceback.print_exc()
    
    def stop(self):
        """Stop monitoring"""
        self.running = False
        print("\n\nStopping monitor...")

async def main():
    """Main entry point"""
    
    # Initialize database
    await init_database()
    
    # Create monitor
    monitor = TransactionMonitor()
    
    try:
        # Check for payments that arrived while monitor was down
        await monitor.check_missed_payments()
        
        # Start monitoring
        await monitor.start_monitoring()
        
    except KeyboardInterrupt:
        print("\n\nReceived Ctrl+C, shutting down...")
        monitor.stop()
    except Exception as e:
        print(f"\n✗ Monitor error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        from database import close_database
        await close_database()
        print("✓ Monitor stopped")

if __name__ == "__main__":
    print("\nStarting transaction monitor...\n")
    asyncio.run(main())