# XRP Token Demo - Tokenized Investment Fund

Complete end-to-end tokenized investment fund on XRP Ledger with automated investor onboarding, KYC compliance, and real-time transaction monitoring.

## Features

- Investor onboarding API with KYC approval
- Automated trust line management
- Token issuance and distribution
- Real-time transaction monitoring
- PostgreSQL/Supabase integration
- Fully async implementation


```bash
# 1. Install
git clone https://github.com/yourusername/XRP-Token-Demo.git
cd XRP-Token-Demo
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cd internal_token
cp .env.example .env
# Edit .env with your database URL

# 3. Setup wallets and issue tokens
python setup_wallets.py
python issue_initial_tokens.py

# 4. Run services
python api.py              # Terminal 1
python monitor.py          # Terminal 2
python test_e2e.py         # Terminal 3 (test)
```

## Project Structure

```
internal_token/              # Main application
├── api.py                  # FastAPI server
├── database.py             # Database layer
├── xrpl_utils.py           # XRPL utilities
├── monitor.py              # Transaction monitor
├── setup_wallets.py        # Wallet setup
├── test_e2e.py             # E2E tests
└── xrpl_operations/        # XRPL operation tools
    ├── send_xrp.py         # Send XRP between wallets
    ├── create_trust_line.py  # Create trust lines
    ├── create_amm_pool.py  # Create AMM pool
    └── amm_swap.py         # Swap tokens via AMM

examples/                   # Demo scripts & tutorials
```

## Key Endpoints

- `POST /api/onboard` - Register investor
- `POST /api/investors/{id}/kyc/approve` - Approve KYC
- `POST /api/investors/{id}/trust-line/authorize` - Authorize trust line
- `POST /api/purchases` - Initiate purchase
- `GET /api/investors/{id}/dashboard` - Portfolio view

Full API docs: `http://localhost:8000/docs` after running `python api.py`

## How It Works

1. **Investor creates** trust line to token issuer
2. **Admin approves** trust line (KYC gate)
3. **Investor sends** payment to deposit wallet
4. **Monitor detects** payment and auto-issues tokens
5. **Tokens appear** in investor's wallet

## Troubleshooting

**`tecPATH_DRY` error**: Hot wallet has no tokens → Run `python issue_initial_tokens.py`

**Trust line not found**: Investor must create trust line before receiving tokens

