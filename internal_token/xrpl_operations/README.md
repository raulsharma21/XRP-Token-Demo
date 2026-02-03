# XRPL Operations

Command-line tools for XRPL operations and AMM trading.

## Available Scripts

### 📤 `send_xrp.py` - Send XRP Between Wallets

Transfer XRP from one wallet to another.

**Usage:**
```bash
python send_xrp.py
```

**Features:**
- Send from any wallet (seed or configured wallet)
- Shows balances before & after
- Optional destination tag support
- Transaction confirmation
- Explorer links

---

### 🔗 `create_trust_line.py` - Create Trust Line

Allows an investor wallet to receive tokens.

**Usage:**
```bash
python create_trust_line.py
```

**Features:**
- Checks if trust line already exists
- Shows XRP balance
- Configurable trust line limit (default: 1M)
- Next steps guidance

---

### 🏊 `create_amm_pool.py` - Create AMM Pool

One-time setup to create the liquidity pool.

**Usage:**
```bash
python create_amm_pool.py
```

**Features:**
- Checks if pool already exists
- Configurable initial liquidity
- Configurable trading fee
- Balance verification
- Pool info display

**Note:** Run this ONCE to create the pool. Uses hot wallet.

---

### 💱 `amm_swap.py` - Swap Tokens via AMM

Trade between XRP and tokens using the AMM pool.

**Usage:**
```bash
python amm_swap.py
```

**Features:**
- Buy tokens with XRP or sell tokens for XRP
- Shows pool reserves and current price
- Estimates output before swapping
- 10% slippage tolerance built-in
- Before/after balance display

---

## Quick Start Workflows

### For Admins - Initial Setup
```bash
# 1. Create wallets (one-time)
cd ..
python setup_wallets.py

# 2. Issue initial tokens (one-time)
python issue_initial_tokens.py

# 3. Create AMM pool (one-time)
cd xrpl_operations
python create_amm_pool.py
```

### For Investors - Getting Started
```bash
# 1. Create trust line to receive tokens
python create_trust_line.py

# 2. Wait for admin to authorize trust line
# (via API: POST /api/investors/{id}/trust-line/authorize)

# 3. Make a purchase or trade on AMM
python amm_swap.py
```

### For Admins - Operations
```bash
# Send test XRP to investor
python send_xrp.py

# Choose: Hot/Cold/Deposit wallet as sender
# Enter investor address as recipient
```

### For Trading - Secondary Market
```bash
# Buy tokens with XRP
python amm_swap.py
# Choose option 1

# Sell tokens for XRP
python amm_swap.py
# Choose option 2
```

---

## Common Patterns

### Complete Investor Flow
1. **Create trust line** → `python create_trust_line.py`
2. **Get admin approval** → Contact admin for KYC
3. **Make purchase** → Use API or send payment to deposit wallet
4. **Receive tokens** → Automatic via monitor
5. **Trade on AMM** → `python amm_swap.py`

### Admin Operations
1. **Send test XRP** → `python send_xrp.py`
2. **Setup new investor** → Use API endpoints
3. **Manual transfers** → Use `send_xrp.py` for wallet-to-wallet XRP

---

## Configuration

All scripts read from `../.env`:
- Network (testnet/mainnet) auto-detected
- Token configuration (currency code, issuer)
- Wallet seeds (for configured wallets)

## Security Notes

⚠️ **Wallet Seeds:**
- Seeds are entered interactively (not stored)
- Never commit wallet seeds to git
- For production, use hardware wallets

⚠️ **Testnet vs Mainnet:**
- Always test on testnet first
- Double-check network before sending real XRP
- Testnet XRP has no value

## Troubleshooting

**"Token not found in .env"**
→ Make sure `TOKEN_ISSUER_ADDRESS` is set in `.env`

**"No AMM pool found"**
→ Run `python create_amm_pool.py` first (admin only)

**"Trust line already exists"**
→ You're good! Skip to the next step

**"tecPATH_DRY" error in swap**
→ Pool might have insufficient liquidity, try smaller amount

---

## Technical Details

### AMM Swap Formula
Uses constant product formula: `x * y = k`
- Output = `(input * reserve_out) / (reserve_in + input)`
- With trading fee deduction

### Transaction Flags
- `tfPartialPayment` (131072) - Allows flexible delivery amounts
- Slippage tolerance: 10% (90% minimum output)

### Precision Limits
- XRPL issued currency: Max 16 significant digits
- Scripts auto-round to 15 digits for safety

---

**All scripts are interactive and require confirmation before executing transactions.**
