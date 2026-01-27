"""
End-to-End Test Script
Tests the complete investor flow from onboarding to receiving tokens
"""

import asyncio
import datetime
import requests
from xrpl.clients import JsonRpcClient
from xrpl.wallet import generate_faucet_wallet, Wallet
from xrpl.models.transactions import Payment, TrustSet
from xrpl.models.amounts import IssuedCurrencyAmount
from xrpl.transaction import submit_and_wait
from decimal import Decimal
import os
from dotenv import load_dotenv
import time

load_dotenv()

# Configuration
API_BASE_URL = "http://localhost:8000"
TESTNET_URL = "https://s.altnet.rippletest.net:51234/"

TOKEN_CURRENCY = os.getenv('TOKEN_CURRENCY_CODE', 'IND')
TOKEN_ISSUER = os.getenv('COLD_WALLET_ADDRESS', '')
DEPOSIT_WALLET = os.getenv('DEPOSIT_WALLET_ADDRESS', '')

# Colors for output
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_step(step_num, title):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}")
    print(f"STEP {step_num}: {title}")
    print(f"{'='*60}{Colors.END}")

def print_success(message):
    print(f"{Colors.GREEN}✓ {message}{Colors.END}")

def print_warning(message):
    print(f"{Colors.YELLOW}⚠ {message}{Colors.END}")

def print_error(message):
    print(f"{Colors.RED}✗ {message}{Colors.END}")

def print_info(message):
    print(f"  {message}")

class E2ETest:
    def __init__(self):
        self.client = JsonRpcClient(TESTNET_URL)
        self.investor_wallet = None
        self.investor_id = None
        self.purchase_id = None
        self.destination_tag = None
        
    def test_api_health(self):
        """Test that API is running"""
        print_step(1, "Check API Server")
        
        try:
            response = requests.get(f"{API_BASE_URL}/api/health", timeout=5)
            if response.status_code == 200:
                print_success("API server is running")
                print_info(f"Response: {response.json()}")
                return True
            else:
                print_error(f"API returned status {response.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            print_error("Cannot connect to API server")
            print_info("Make sure to run: python api.py")
            return False
        except Exception as e:
            print_error(f"Error: {e}")
            return False
    
    def create_investor_wallet(self):
        """Create a test investor wallet on testnet"""
        print_step(2, "Create Investor Wallet")
        
        try:
            print_info("Requesting testnet XRP from faucet...")
            self.investor_wallet = generate_faucet_wallet(self.client, debug=False)
            
            print_success("Investor wallet created and funded")
            print_info(f"Address: {self.investor_wallet.address}")
            print_info(f"Seed: {self.investor_wallet.seed} (save this!)")
            print_info(f"Explorer: https://testnet.xrpl.org/accounts/{self.investor_wallet.address}")
            return True
            
        except Exception as e:
            print_error(f"Failed to create wallet: {e}")
            return False
    
    def onboard_investor(self):
        """Onboard investor via API"""
        print_step(3, "Onboard Investor")
        
        try:
            time = int(datetime.datetime.now().timestamp())
            data = {
                "email": f"test_{time}.investor@example.com",
                "xrpl_address": self.investor_wallet.address
            }
            
            response = requests.post(f"{API_BASE_URL}/api/onboard", json=data)
            
            if response.status_code == 200:
                result = response.json()
                self.investor_id = result['investor_id']
                
                print_success("Investor onboarded")
                print_info(f"Investor ID: {self.investor_id}")
                print_info(f"Email: {result['email']}")
                print_info(f"Status: {result['status']}")
                return True
            else:
                print_error(f"Onboarding failed: {response.text}")
                return False
                
        except Exception as e:
            print_error(f"Error: {e}")
            return False
    
    def approve_kyc(self):
        """Approve investor KYC"""
        print_step(4, "Approve KYC")
        
        try:
            data = {"investor_id": self.investor_id}
            
            response = requests.post(f"{API_BASE_URL}/api/kyc/approve", json=data)
            
            if response.status_code == 200:
                result = response.json()
                
                print_success("KYC approved")
                print_info(f"Status: {result['status']}")
                print_info(f"Next step: {result.get('next_step', 'N/A')}")
                return True
            else:
                print_error(f"KYC approval failed: {response.text}")
                return False
                
        except Exception as e:
            print_error(f"Error: {e}")
            return False
    
    def create_trust_line(self):
        """Investor creates trust line to token"""
        print_step(5, "Create Trust Line (Investor Side)")
        
        try:
            print_info(f"Creating trust line: Investor → Token Issuer")
            print_info(f"Token: {TOKEN_CURRENCY}")
            print_info(f"Issuer: {TOKEN_ISSUER}")
            
            trust_tx = TrustSet(
                account=self.investor_wallet.address,
                limit_amount=IssuedCurrencyAmount(
                    currency=TOKEN_CURRENCY,
                    issuer=TOKEN_ISSUER,
                    value="1000000"  # Max 1M tokens
                )
            )
            
            response = submit_and_wait(trust_tx, self.client, self.investor_wallet)
            result = response.result["meta"]["TransactionResult"]
            
            if result == "tesSUCCESS":
                print_success("Trust line created")
                print_info(f"TX: {response.result['hash']}")
                return True
            else:
                print_error(f"Failed: {result}")
                return False
                
        except Exception as e:
            print_error(f"Error: {e}")
            return False
    
    def confirm_trust_line(self):
        """Confirm trust line via API (triggers authorization)"""
        print_step(6, "Confirm & Authorize Trust Line")
        
        try:
            data = {"investor_id": self.investor_id}
            
            response = requests.post(f"{API_BASE_URL}/api/trustline/confirm", json=data)
            
            if response.status_code == 200:
                result = response.json()
                
                print_success("Trust line confirmed and authorized")
                print_info(f"Status: {result['status']}")
                print_info(f"Authorization TX: {result.get('tx_hash', 'N/A')}")
                return True
            else:
                print_error(f"Trust line confirmation failed: {response.text}")
                print_error(f"Error code: {response.status_code}")
                return False
                
        except Exception as e:
            print_error(f"Error: {e}")
            return False
    
    def initiate_purchase(self, amount=100):
        """Initiate token purchase"""
        print_step(7, "Initiate Purchase")
        
        try:
            data = {
                "investor_id": self.investor_id,
                "usdc_amount": amount
            }
            
            response = requests.post(f"{API_BASE_URL}/api/buy/initiate", json=data)
            
            if response.status_code == 200:
                result = response.json()
                self.purchase_id = result['purchase_id']
                instructions = result['deposit_instructions']
                self.destination_tag = instructions['destination_tag']
                
                print_success("Purchase initiated")
                print_info(f"Purchase ID: {self.purchase_id}")
                print_info(f"Amount: {instructions['amount']} {instructions['currency']}")
                print_info(f"Destination: {instructions['destination']}")
                print_info(f"Destination Tag: {self.destination_tag}")
                print_info(f"Expected tokens: {result['expected_tokens']} {TOKEN_CURRENCY}")
                return True
            else:
                print_error(f"Purchase initiation failed: {response.text}")
                return False
                
        except Exception as e:
            print_error(f"Error: {e}")
            return False
    
    def simulate_usdc_deposit(self, amount=100):
        """Simulate USDC deposit (using IND tokens as proxy on testnet)"""
        print_step(8, "Simulate USDC Deposit")
        
        print_warning("On testnet, we'll send IND tokens to simulate USDC deposit")
        print_info("In production, investor would send real USDC")
        
        try:
            # For testnet demo, we need the investor to have some tokens to send
            # In real scenario, they'd send USDC from an exchange
            
            print_info(f"Sending {amount} tokens to deposit wallet...")
            print_info(f"From: {self.investor_wallet.address}")
            print_info(f"To: {DEPOSIT_WALLET}")
            print_info(f"Destination Tag: {self.destination_tag}")
            
            # For testnet, we'll send XRP as a proxy
            # (In production this would be USDC)
            payment_tx = Payment(
                account=self.investor_wallet.address,
                destination=DEPOSIT_WALLET,
                destination_tag=self.destination_tag,
                amount=str(int(amount * 1_000_000))  # Convert to drops for XRP
            )
            
            response = submit_and_wait(payment_tx, self.client, self.investor_wallet)
            result = response.result["meta"]["TransactionResult"]
            
            if result == "tesSUCCESS":
                tx_hash = response.result['hash']
                print_success("Deposit sent")
                print_info(f"TX: {tx_hash}")
                print_info(f"Explorer: https://testnet.xrpl.org/transactions/{tx_hash}")
                
                print_info("\n⏳ Waiting for monitor to process (10 seconds)...")
                time.sleep(10)
                return True
            else:
                print_error(f"Failed: {result}")
                return False
                
        except Exception as e:
            print_error(f"Error: {e}")
            return False
    
    def check_purchase_status(self):
        """Check purchase status"""
        print_step(9, "Check Purchase Status")
        
        try:
            response = requests.get(f"{API_BASE_URL}/api/buy/status/{self.purchase_id}")
            
            if response.status_code == 200:
                result = response.json()
                
                status = result['status']
                print_info(f"Purchase ID: {result['purchase_id']}")
                print_info(f"Status: {status}")
                
                if result.get('token_amount'):
                    print_info(f"Tokens issued: {result['token_amount']} {TOKEN_CURRENCY}")
                
                if status == 'completed':
                    print_success("Purchase completed!")
                    return True
                elif status == 'pending':
                    print_warning("Still pending - monitor may not have processed yet")
                    return False
                else:
                    print_info(f"Status: {status}")
                    return False
            else:
                print_error(f"Failed to check status: {response.text}")
                return False
                
        except Exception as e:
            print_error(f"Error: {e}")
            return False
    
    def verify_token_balance(self):
        """Verify investor received tokens"""
        print_step(10, "Verify Token Balance")
        
        try:
            from xrpl.models.requests import AccountLines
            
            print_info("Checking investor's token balance on XRPL...")
            
            response = self.client.request(AccountLines(
                account=self.investor_wallet.address,
                ledger_index="validated"
            ))
            
            lines = response.result.get("lines", [])
            
            for line in lines:
                if line["currency"] == TOKEN_CURRENCY and line["account"] == TOKEN_ISSUER:
                    balance = line["balance"]
                    print_success(f"Investor has {balance} {TOKEN_CURRENCY}")
                    return True
            
            print_warning(f"No {TOKEN_CURRENCY} balance found yet")
            print_info("This could mean the monitor hasn't processed the deposit yet")
            return False
            
        except Exception as e:
            print_error(f"Error: {e}")
            return False
    
    def check_dashboard(self):
        """Check investor dashboard"""
        print_step(11, "Check Investor Dashboard")
        
        try:
            response = requests.get(f"{API_BASE_URL}/api/dashboard/{self.investor_wallet.address}")
            
            if response.status_code == 200:
                result = response.json()
                
                print_success("Dashboard data retrieved")
                print_info(f"Email: {result['email']}")
                print_info(f"Token balance: {result['token_balance']} {TOKEN_CURRENCY}")
                print_info(f"Estimated value: ${result['estimated_value_usd']:.2f}")
                print_info(f"Current NAV: ${result['nav_per_token']:.2f}")
                return True
            else:
                print_error(f"Failed to get dashboard: {response.text}")
                return False
                
        except Exception as e:
            print_error(f"Error: {e}")
            return False

def main():
    """Run the complete E2E test"""
    
    print(f"\n{Colors.BOLD}{'='*60}")
    print("END-TO-END TEST: Complete Investor Flow")
    print(f"{'='*60}{Colors.END}\n")
    
    print("This test will:")
    print("  1. Check API is running")
    print("  2. Create investor wallet")
    print("  3. Onboard investor")
    print("  4. Approve KYC")
    print("  5. Create trust line")
    print("  6. Authorize trust line")
    print("  7. Initiate purchase")
    print("  8. Simulate deposit")
    print("  9. Check purchase status")
    print("  10. Verify token balance")
    print("  11. Check dashboard")
    
    print(f"\n{Colors.YELLOW}Prerequisites:{Colors.END}")
    print("  • API server running (python api.py)")
    print("  • Transaction monitor running (python monitor.py)")
    print("  • Database initialized")
    print("  • Wallets configured with tokens issued")
    
    response = input(f"\n{Colors.BOLD}Ready to start? (y/N): {Colors.END}")
    if response.lower() != 'y':
        print("Test cancelled.")
        return
    
    # Run tests
    test = E2ETest()
    
    results = []
    
    # Step 1: API Health
    results.append(("API Health", test.test_api_health()))
    if not results[-1][1]:
        print_error("\n❌ API not running. Please start: python api.py")
        return
    
    # Step 2: Create wallet
    results.append(("Create Wallet", test.create_investor_wallet()))
    if not results[-1][1]:
        return
    
    # Step 3: Onboard
    results.append(("Onboard", test.onboard_investor()))
    if not results[-1][1]:
        return
    
    # Step 4: Approve KYC
    results.append(("Approve KYC", test.approve_kyc()))
    if not results[-1][1]:
        return
    
    # Step 5: Create trust line
    results.append(("Create Trust Line", test.create_trust_line()))
    if not results[-1][1]:
        return
    
    # Step 6: Confirm trust line
    results.append(("Confirm Trust Line", test.confirm_trust_line()))
    if not results[-1][1]:
        return
    
    # Step 7: Initiate purchase
    results.append(("Initiate Purchase", test.initiate_purchase(amount=10)))
    if not results[-1][1]:
        return
    
    # Step 8: Simulate deposit
    print_warning("\n⚠️ NOTE: On testnet, we're sending 10 XRP to simulate USDC deposit")
    print_warning("The monitor will detect it and process it as a deposit")
    print_warning("In production, this would be real USDC from Coinbase/Exchange\n")
    
    results.append(("Simulate Deposit", test.simulate_usdc_deposit(amount=10)))
    if not results[-1][1]:
        return
    
    # Step 9: Check status
    results.append(("Check Status", test.check_purchase_status()))
    
    # Step 10: Verify balance
    results.append(("Verify Balance", test.verify_token_balance()))
    
    # Step 11: Dashboard
    results.append(("Check Dashboard", test.check_dashboard()))
    
    # Summary
    print(f"\n{Colors.BOLD}{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}{Colors.END}\n")
    
    for step, success in results:
        status = f"{Colors.GREEN}✓{Colors.END}" if success else f"{Colors.RED}✗{Colors.END}"
        print(f"{status} {step}")
    
    passed = sum(1 for _, s in results if s)
    total = len(results)
    
    print(f"\n{Colors.BOLD}Results: {passed}/{total} passed{Colors.END}")
    
    if passed == total:
        print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 ALL TESTS PASSED!{Colors.END}")
        print("\nYour system is working end-to-end!")
    else:
        print(f"\n{Colors.YELLOW}Some steps failed - check errors above{Colors.END}")

if __name__ == "__main__":
    main()