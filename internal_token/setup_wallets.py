"""
XRPL Wallet Setup for AI Fund
Creates and configures cold, hot, and deposit wallets
"""

from xrpl.clients import JsonRpcClient
from xrpl.wallet import generate_faucet_wallet, Wallet
from xrpl.transaction import submit_and_wait
from xrpl.models.transactions import AccountSet
from xrpl.models.transactions.account_set import AccountSetAsfFlag
from xrpl.models.requests import AccountInfo
import os
from dotenv import load_dotenv
import json

load_dotenv()

# Configuration
TESTNET_URL = "https://s.altnet.rippletest.net:51234/"
MAINNET_URL = "https://s1.ripple.com:51234/"

# Token configuration
TOKEN_CURRENCY_CODE = os.getenv('TOKEN_CURRENCY_CODE', 'IND')

# Choose network
USE_TESTNET = os.getenv('XRPL_NETWORK', 'testnet') == 'testnet'
NETWORK_URL = TESTNET_URL if USE_TESTNET else MAINNET_URL

print("=" * 60)
print("XRPL WALLET SETUP FOR AI FUND")
print("=" * 60)
print(f"\nNetwork: {'TESTNET' if USE_TESTNET else 'MAINNET'}")
print(f"Token: {TOKEN_CURRENCY_CODE}")
print()

def setup_wallets():
    """Create and configure all necessary wallets"""
    
    client = JsonRpcClient(NETWORK_URL)
    
    wallets = {}
    
    # ========================================
    # STEP 1: CREATE WALLETS
    # ========================================
    
    print("STEP 1: Creating Wallets")
    print("-" * 60)
    
    if USE_TESTNET:
        # For testnet, use faucet to fund wallets
        print("\n1. Creating Cold Wallet (Token Issuer)...")
        cold_wallet = generate_faucet_wallet(client, debug=False)
        print(f"   ✓ Address: {cold_wallet.address}")
        print(f"   ✓ Funded with testnet XRP")
        
        print("\n2. Creating Hot Wallet (Operational)...")
        hot_wallet = generate_faucet_wallet(client, debug=False)
        print(f"   ✓ Address: {hot_wallet.address}")
        print(f"   ✓ Funded with testnet XRP")
        
        print("\n3. Creating Deposit Wallet (Receives IPO deposits)...")
        deposit_wallet = generate_faucet_wallet(client, debug=False)
        print(f"   ✓ Address: {deposit_wallet.address}")
        print(f"   ✓ Funded with testnet XRP")
        
    else:
        # For mainnet, generate wallets but they need manual funding
        print("\n⚠️  MAINNET MODE - Wallets need manual funding!")
        print("   Generate wallets and send at least 12 XRP to each\n")
        
        cold_wallet = Wallet.create()
        print(f"1. Cold Wallet: {cold_wallet.address}")
        print(f"   Seed: {cold_wallet.seed}")
        print(f"   ⚠️  FUND THIS ADDRESS WITH 12+ XRP\n")
        
        hot_wallet = Wallet.create()
        print(f"2. Hot Wallet: {hot_wallet.address}")
        print(f"   Seed: {hot_wallet.seed}")
        print(f"   ⚠️  FUND THIS ADDRESS WITH 12+ XRP\n")
        
        deposit_wallet = Wallet.create()
        print(f"3. Deposit Wallet: {deposit_wallet.address}")
        print(f"   Seed: {deposit_wallet.seed}")
        print(f"   ⚠️  FUND THIS ADDRESS WITH 12+ XRP\n")
        
        input("Press Enter after funding all wallets...")
    
    wallets = {
        'cold': cold_wallet,
        'hot': hot_wallet,
        'deposit': deposit_wallet
    }
    
    # ========================================
    # STEP 2: CONFIGURE COLD WALLET (ISSUER)
    # ========================================
    
    print("\n" + "=" * 60)
    print("STEP 2: Configuring Cold Wallet (Token Issuer)")
    print("-" * 60)
    
    # Enable Default Ripple (REQUIRED for tokens to transfer between third parties)
    print("\n1. Enabling Default Ripple...")
    print("   (Allows tokens to transfer between investors)")
    
    default_ripple_tx = AccountSet(
        account=cold_wallet.address,
        set_flag=AccountSetAsfFlag.ASF_DEFAULT_RIPPLE,
    )
    
    response = submit_and_wait(default_ripple_tx, client, cold_wallet)
    result = response.result["meta"]["TransactionResult"]
    
    if result == "tesSUCCESS":
        print("   ✓ Default Ripple enabled")
    else:
        print(f"   ✗ Failed: {result}")
        return None
    
    # Enable Require Auth (REQUIRED for KYC/compliance)
    print("\n2. Enabling Require Auth...")
    print("   (You must authorize each trust line - KYC gate)")
    
    require_auth_tx = AccountSet(
        account=cold_wallet.address,
        set_flag=AccountSetAsfFlag.ASF_REQUIRE_AUTH,
    )
    
    response = submit_and_wait(require_auth_tx, client, cold_wallet)
    result = response.result["meta"]["TransactionResult"]
    
    if result == "tesSUCCESS":
        print("   ✓ Require Auth enabled")
    else:
        print(f"   ✗ Failed: {result}")
        return None
    
    # Optional: Enable Clawback (for regulatory compliance)
    enable_clawback = input("\n3. Enable Clawback? (allows recovering tokens from holders) [y/N]: ")
    
    if enable_clawback.lower() == 'y':
        print("   Enabling Clawback...")
        
        clawback_tx = AccountSet(
            account=cold_wallet.address,
            set_flag=AccountSetAsfFlag.ASF_ALLOW_TRUSTLINE_CLAWBACK,
        )
        
        response = submit_and_wait(clawback_tx, client, cold_wallet)
        result = response.result["meta"]["TransactionResult"]
        
        if result == "tesSUCCESS":
            print("   ✓ Clawback enabled")
        else:
            print(f"   ✗ Failed: {result}")
    else:
        print("   ⊘ Clawback not enabled")
    
    # ========================================
    # STEP 3: VERIFY WALLET BALANCES
    # ========================================
    
    print("\n" + "=" * 60)
    print("STEP 3: Verifying Wallet Balances")
    print("-" * 60)
    
    for wallet_name, wallet in wallets.items():
        response = client.request(AccountInfo(
            account=wallet.address,
            ledger_index="validated"
        ))
        
        balance_drops = response.result["account_data"]["Balance"]
        balance_xrp = int(balance_drops) / 1_000_000
        
        print(f"\n{wallet_name.upper()} Wallet:")
        print(f"  Address: {wallet.address}")
        print(f"  Balance: {balance_xrp} XRP")
        
        if balance_xrp < 10:
            print(f"  ⚠️  WARNING: Low balance! Need at least 10 XRP")
    
    # ========================================
    # STEP 4: SAVE WALLET CONFIGURATION
    # ========================================
    
    print("\n" + "=" * 60)
    print("STEP 4: Saving Wallet Configuration")
    print("-" * 60)
    
    # Create wallet config for .env
    config = {
        'network': 'testnet' if USE_TESTNET else 'mainnet',
        'network_url': NETWORK_URL,
        'token_currency_code': TOKEN_CURRENCY_CODE,
        'wallets': {
            'cold': {
                'address': cold_wallet.address,
                'seed': cold_wallet.seed,
                'purpose': 'Token issuer - KEEP SECURE!'
            },
            'hot': {
                'address': hot_wallet.address,
                'seed': hot_wallet.seed,
                'purpose': 'Operational wallet - holds token inventory'
            },
            'deposit': {
                'address': deposit_wallet.address,
                'seed': deposit_wallet.seed,
                'purpose': 'Receives IPO deposits - monitored 24/7'
            }
        }
    }
    
    # Save to JSON file
    with open('wallet_config.json', 'w') as f:
        json.dump(config, f, indent=2)
    
    print("\n✓ Wallet configuration saved to: wallet_config.json")
    
    # Prepare .env variables
    env_vars = f"""
# ==================== XRPL CONFIGURATION ====================
# Network: mainnet or testnet (Generated by setup_wallets.py)
XRPL_NETWORK={'testnet' if USE_TESTNET else 'mainnet'}
XRPL_CLIENT_URL={NETWORK_URL}

# Token Configuration
TOKEN_CURRENCY_CODE={TOKEN_CURRENCY_CODE}
TOKEN_ISSUER_ADDRESS={cold_wallet.address}

# Wallet Addresses and Seeds
COLD_WALLET_ADDRESS={cold_wallet.address}
COLD_WALLET_SEED={cold_wallet.seed}

HOT_WALLET_ADDRESS={hot_wallet.address}
HOT_WALLET_SEED={hot_wallet.seed}

DEPOSIT_WALLET_ADDRESS={deposit_wallet.address}
DEPOSIT_WALLET_SEED={deposit_wallet.seed}
"""
    
    # Check if .env exists and ask user
    env_file_path = '.env'
    if os.path.exists(env_file_path):
        print("\n⚠️  .env file already exists!")
        response = input("Overwrite wallet configuration in .env? (y/N): ")
        
        if response.lower() == 'y':
            # Read existing .env
            with open(env_file_path, 'r') as f:
                existing_content = f.read()
            
            # Remove old XRPL/wallet configuration sections
            import re
            
            # Remove both old format (# ==== XRPL CONFIGURATION ====) and new format (# XRPL Configuration (Generated...))
            # Pattern 1: Old format with equals signs
            pattern1 = r'# ={2,} XRPL CONFIGURATION ={2,}.*?(?=# ={2,}|$)'
            cleaned_content = re.sub(pattern1, '', existing_content, flags=re.DOTALL)
            
            # Pattern 2: New format generated by this script
            pattern2 = r'# XRPL Configuration \(Generated by setup_wallets\.py\).*?DEPOSIT_WALLET_SEED=.*?(?=\n(?:#|$)|\Z)'
            cleaned_content = re.sub(pattern2, '', cleaned_content, flags=re.DOTALL)
            
            # Also remove standalone duplicate token/wallet lines that might exist
            lines_to_remove = [
                'XRPL_NETWORK=',
                'XRPL_CLIENT_URL=',
                'TOKEN_CURRENCY_CODE=',
                'TOKEN_ISSUER_ADDRESS=',
                'COLD_WALLET_ADDRESS=',
                'COLD_WALLET_SEED=',
                'HOT_WALLET_ADDRESS=',
                'HOT_WALLET_SEED=',
                'DEPOSIT_WALLET_ADDRESS=',
                'DEPOSIT_WALLET_SEED='
            ]
            
            # Split into lines, filter out duplicates
            lines = cleaned_content.split('\n')
            filtered_lines = []
            for line in lines:
                # Keep non-XRPL lines, or the first occurrence in the XRPL section
                should_skip = False
                for pattern in lines_to_remove:
                    if line.strip().startswith(pattern):
                        should_skip = True
                        break
                if not should_skip:
                    filtered_lines.append(line)
            
            cleaned_content = '\n'.join(filtered_lines)
            
            # Clean up multiple consecutive blank lines
            cleaned_content = re.sub(r'\n{3,}', '\n\n', cleaned_content)
            
            # Append new configuration
            with open(env_file_path, 'w') as f:
                f.write(cleaned_content.strip() + '\n\n' + env_vars.strip() + '\n')
            
            print(f"✓ Wallet configuration written to {env_file_path}")
        else:
            print("✗ Skipped writing to .env")
            print("\n" + "=" * 60)
            print("ADD THESE TO YOUR .env FILE:")
            print("=" * 60)
            print(env_vars)
    else:
        # Create new .env file
        with open(env_file_path, 'w') as f:
            f.write(env_vars.strip() + '\n')
        
        print(f"✓ Wallet configuration written to {env_file_path}")
    
    print("\n⚠️  SECURITY WARNING:")
    print("   - NEVER commit wallet seeds to git!")
    print("   - Store cold wallet seed in secure offline storage")
    print("   - Add wallet_config.json and .env to .gitignore")
    
    # ========================================
    # STEP 5: SUMMARY
    # ========================================
    
    print("\n" + "=" * 60)
    print("SETUP COMPLETE!")
    print("=" * 60)
    
    print(f"\n✓ Network: {'TESTNET' if USE_TESTNET else 'MAINNET'}")
    print(f"✓ Token: {TOKEN_CURRENCY_CODE}")
    print(f"✓ Issuer configured with:")
    print(f"  - Default Ripple: ✓")
    print(f"  - Require Auth: ✓")
    print(f"  - Clawback: {'✓' if enable_clawback.lower() == 'y' else '⊘'}")
    
    print(f"\n✓ Wallets created:")
    print(f"  - Cold (Issuer): {cold_wallet.address}")
    print(f"  - Hot (Operations): {hot_wallet.address}")
    print(f"  - Deposit (IPO): {deposit_wallet.address}")
    
    if USE_TESTNET:
        print(f"\n🔗 View on Explorer:")
        print(f"  Cold: https://testnet.xrpl.org/accounts/{cold_wallet.address}")
        print(f"  Hot: https://testnet.xrpl.org/accounts/{hot_wallet.address}")
        print(f"  Deposit: https://testnet.xrpl.org/accounts/{deposit_wallet.address}")
    
    print("\nNext steps:")
    print("  1. Add the .env variables shown above")
    print("  2. Secure your wallet seeds (especially cold wallet!)")
    print("  3. Run the token issuance script to mint initial tokens")
    
    return config

# ========================================
# RUN SETUP
# ========================================

if __name__ == "__main__":
    config = setup_wallets()
    
    if config:
        print("\n✓ Setup successful!")
    else:
        print("\n✗ Setup failed - check errors above")