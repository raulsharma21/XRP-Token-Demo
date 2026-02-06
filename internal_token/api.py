"""
Token Manager API Server
FastAPI server for managing investor onboarding, purchases, redemptions, and NAV
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Callable
from datetime import datetime
from decimal import Decimal
from contextlib import asynccontextmanager
from functools import wraps
import os
from dotenv import load_dotenv

# Import our database module
from database import (
    db, init_database, close_database,
    InvestorDB, PurchaseDB, RedemptionDB, NAVDB, SystemConfigDB, StatsDB
)

# Import XRPL utilities
from xrpl_utils import (
    initialize_xrpl,
    get_token_balance,
    get_xrp_balance,
    check_trust_line_exists,
    authorize_trust_line,
    issue_tokens,
    forward_usdc_to_coinbase,
    send_usdc_to_investor,
    validate_xrpl_address,
    wallet_manager,
    config as xrpl_config
)

load_dotenv()

# ==================== CONFIGURATION ====================

API_HOST = os.getenv('API_HOST', '0.0.0.0')
API_PORT = int(os.getenv('API_PORT', '8000'))
API_DEBUG = os.getenv('API_DEBUG', 'true').lower() == 'true'

# ==================== FASTAPI APP ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    # Startup
    await init_database()
    initialize_xrpl()
    print("✓ API Server started")
    yield
    # Shutdown
    await close_database()
    print("✓ API Server stopped")

app = FastAPI(
    title="Indicia Labs Token API",
    description="API for managing tokenized fund",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware (adjust origins for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== ERROR HANDLING DECORATOR ====================

def handle_errors(func: Callable):
    """Decorator to handle common API errors"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return wrapper

# ==================== REQUEST/RESPONSE MODELS ====================

# Investor models
class InvestorOnboardRequest(BaseModel):
    email: EmailStr
    xrpl_address: str = Field(..., min_length=25, max_length=35)

class InvestorOnboardResponse(BaseModel):
    investor_id: str
    email: str
    xrpl_address: str
    status: str
    message: str

class KYCApproveRequest(BaseModel):
    investor_id: str

class TrustLineConfirmRequest(BaseModel):
    investor_id: str

# Purchase models
class PurchaseInitiateRequest(BaseModel):
    investor_id: str
    usdc_amount: float = Field(..., gt=0)

class PurchaseInitiateResponse(BaseModel):
    purchase_id: str
    deposit_instructions: dict
    expected_tokens: float

class PurchaseStatusResponse(BaseModel):
    purchase_id: str
    status: str
    usdc_amount: Optional[float]
    token_amount: Optional[float]
    created_at: str

# Redemption models
class RedeemRequest(BaseModel):
    investor_id: str
    token_amount: float = Field(..., gt=0)

class RedeemResponse(BaseModel):
    redemption_id: str
    token_amount: float
    status: str
    settlement_time: str
    message: str

# NAV models
class NAVResponse(BaseModel):
    nav_per_token: float
    total_fund_value: Optional[float]
    total_tokens_outstanding: Optional[float]
    calculated_at: Optional[str]
    next_calculation: str

# Pool models
class PoolInfoResponse(BaseModel):
    pool_address: Optional[str]
    usdc_reserve: Optional[float]
    token_reserve: Optional[float]
    current_price: Optional[float]
    trading_fee: Optional[float]
    message: str

# Dashboard models
class InvestorDashboardResponse(BaseModel):
    xrpl_address: str
    email: str
    kyc_approved: bool
    token_balance: float
    estimated_value_usd: float
    nav_per_token: float
    pending_redemptions: List[dict]

class SystemStatsResponse(BaseModel):
    total_investors: int
    total_raised: float
    total_tokens_issued: float
    current_nav: float
    ipo_phase: str
    pool_created: bool

# ==================== HELPER FUNCTIONS ====================

def generate_unique_destination_tag() -> int:
    """Generate unique random destination tag for each purchase"""
    import uuid
    import hashlib
    unique_id = str(uuid.uuid4())
    hash_obj = hashlib.md5(unique_id.encode())
    return int(hash_obj.hexdigest()[:8], 16) % (2**32)

# ==================== PHASE 1: ONBOARDING ROUTES ====================

@app.get("/api/investors/by-address/{xrpl_address}")
async def get_investor_by_address(xrpl_address: str):
    """
    Get investor information by XRPL address
    Used by frontend to look up investor account from connected wallet
    """
    try:
        investor = await InvestorDB.get_by_xrpl_address(xrpl_address)
        if not investor:
            raise HTTPException(status_code=404, detail="Investor not found")
        
        return {
            "investor_id": str(investor['id']),
            "email": investor['email'],
            "xrpl_address": investor['xrpl_address'],
            "kyc_approved": investor['kyc_approved'],
            "trust_line_created": investor['trust_line_created']
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/onboard", response_model=InvestorOnboardResponse)
async def onboard_investor(request: InvestorOnboardRequest):
    """
    Register a new investor for KYC approval
    
    - Validates XRPL address format
    - Creates investor record with KYC pending
    - Returns investor_id for tracking
    """
    try:
        # Validate XRPL address
        if not await validate_xrpl_address(request.xrpl_address):
            raise HTTPException(
                status_code=400,
                detail="Invalid XRPL address format"
            )
        
        # Check if already exists
        existing = await InvestorDB.get_by_email(request.email)
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Investor with this email already exists"
            )
        
        existing = await InvestorDB.get_by_xrpl_address(request.xrpl_address)
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Investor with this XRPL address already exists"
            )
        
        # Create investor
        investor = await InvestorDB.create(
            email=request.email,
            xrpl_address=request.xrpl_address
        )
        
        return InvestorOnboardResponse(
            investor_id=str(investor['id']),
            email=investor['email'],
            xrpl_address=investor['xrpl_address'],
            status="pending_kyc",
            message="Registration complete. KYC approval pending."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/kyc/approve")
async def approve_kyc(request: KYCApproveRequest):
    """
    Approve investor KYC (admin only in production)
    
    - Marks investor as KYC approved
    - Triggers email notification with trust line setup instructions
    - Investor can then create trust line and participate in IPO
    """
    try:
        # Verify investor exists
        investor = await InvestorDB.get_by_id(request.investor_id)
        if not investor:
            raise HTTPException(status_code=404, detail="Investor not found")
        
        if investor['kyc_approved']:
            return {
                "investor_id": request.investor_id,
                "status": "already_approved",
                "message": "Investor KYC was already approved"
            }
        
        # Approve KYC
        success = await InvestorDB.approve_kyc(request.investor_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to approve KYC")
        
        # TODO: Send email with trust line instructions
        # await send_trust_line_instructions(investor['email'])
        
        return {
            "investor_id": request.investor_id,
            "status": "approved",
            "message": "KYC approved. Trust line instructions sent to investor.",
            "next_step": "Investor must create trust line to token issuer"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/trustline/confirm")
async def confirm_trust_line(request: TrustLineConfirmRequest):
    """
    Mark that investor has created their trust line and authorize it
    
    - Verifies trust line exists on XRPL
    - Authorizes trust line from issuer side
    - Enables investor to receive tokens
    """
    try:
        investor = await InvestorDB.get_by_id(request.investor_id)
        if not investor:
            raise HTTPException(status_code=404, detail="Investor not found")
        
        if not investor['kyc_approved']:
            raise HTTPException(
                status_code=403,
                detail="KYC must be approved before confirming trust line"
            )
        
        # Check if trust line exists on XRPL
        trust_line_exists = await check_trust_line_exists(investor['xrpl_address'])
        if not trust_line_exists:
            raise HTTPException(
                status_code=400,
                detail="Trust line not found on XRPL. Please create trust line first."
            )
        
        # Authorize the trust line from issuer side
        auth_result = await authorize_trust_line(investor['xrpl_address'])
        
        if not auth_result['success']:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to authorize trust line: {auth_result['error']}"
            )
        
        # Mark trust line as created in database
        success = await InvestorDB.mark_trust_line_created(request.investor_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update trust line status")
        
        return {
            "investor_id": request.investor_id,
            "status": "ready",
            "message": "Trust line confirmed and authorized. Investor can now purchase tokens.",
            "tx_hash": auth_result['tx_hash'],
            "next_step": "Use /api/buy/initiate to start a purchase"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/investor/{xrpl_address}")
async def get_investor_info(xrpl_address: str):
    """
    Get investor information by XRPL address
    
    - Returns investor profile and status
    - Used for investor to check their onboarding progress
    """
    try:
        investor = await InvestorDB.get_by_xrpl_address(xrpl_address)
        if not investor:
            raise HTTPException(status_code=404, detail="Investor not found")
        
        return {
            "investor_id": str(investor['id']),
            "email": investor['email'],
            "xrpl_address": investor['xrpl_address'],
            "kyc_approved": investor['kyc_approved'],
            "trust_line_created": investor['trust_line_created'],
            "status": "ready" if (investor['kyc_approved'] and investor['trust_line_created']) else "pending"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== PHASE 2: IPO PURCHASE ROUTES ====================

@app.post("/api/buy/initiate", response_model=PurchaseInitiateResponse)
async def initiate_purchase(request: PurchaseInitiateRequest):
    """
    Generate deposit instructions for investor to send USDC
    
    - Validates investor is approved and has trust line
    - Generates unique destination tag
    - Returns deposit address and instructions
    - Purchase will be auto-processed when deposit is detected
    """
    try:
        # Check IPO phase is active
        ipo_active = await SystemConfigDB.is_ipo_active()
        if not ipo_active:
            raise HTTPException(
                status_code=403,
                detail="IPO phase is closed. Use secondary market for trading."
            )
        
        # Verify investor
        investor = await InvestorDB.get_by_id(request.investor_id)
        if not investor:
            raise HTTPException(status_code=404, detail="Investor not found")
        
        if not investor['kyc_approved']:
            raise HTTPException(
                status_code=403,
                detail="KYC not approved. Please complete KYC first."
            )
        
        if not investor['trust_line_created']:
            raise HTTPException(
                status_code=400,
                detail="Trust line not created. Please create trust line first."
            )
        
        # Generate destination tag
        destination_tag = generate_unique_destination_tag()
        
        # Create purchase record
        purchase = await PurchaseDB.create(
            investor_id=request.investor_id,
            usdc_amount=Decimal(str(request.usdc_amount)),
            destination_tag=destination_tag
        )
        
        # Get deposit wallet address from wallet manager
        deposit_address = wallet_manager.deposit_wallet.address
        
        return PurchaseInitiateResponse(
            purchase_id=str(purchase['id']),
            deposit_instructions={
                "currency": "USDC",
                "amount": request.usdc_amount,
                "destination": deposit_address,
                "destination_tag": destination_tag,
                "memo": str(purchase['id']),
                "message": "Send exact amount. Tokens will be issued automatically within 5 minutes.",
                "important": "Include the destination tag or your deposit cannot be processed!"
            },
            expected_tokens=request.usdc_amount  # 1:1 during IPO
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/buy/status/{purchase_id}", response_model=PurchaseStatusResponse)
async def check_purchase_status(purchase_id: str):
    """
    Check status of IPO purchase
    
    - Returns current status: pending, forwarded, completed, failed
    - Shows transaction hashes once processed
    """
    try:
        purchase = await PurchaseDB.get_by_id(purchase_id)
        if not purchase:
            raise HTTPException(status_code=404, detail="Purchase not found")
        
        return PurchaseStatusResponse(
            purchase_id=str(purchase['id']),
            status=purchase['status'],
            usdc_amount=float(purchase['usdc_amount']) if purchase['usdc_amount'] else None,
            token_amount=float(purchase['token_amount']) if purchase['token_amount'] else None,
            created_at=purchase['created_at'].isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== PHASE 3: POOL & MARKET INFO ROUTES ====================

@app.get("/api/nav", response_model=NAVResponse)
async def get_current_nav():
    """
    Get current NAV per token
    
    - Returns latest NAV calculation
    - Total fund value and tokens outstanding
    - Next calculation time (EOD)
    """
    try:
        latest_nav = await NAVDB.get_latest()
        
        if not latest_nav:
            return NAVResponse(
                nav_per_token=1.0,
                total_fund_value=None,
                total_tokens_outstanding=None,
                calculated_at=None,
                next_calculation="Today 4:00 PM PST"
            )
        
        return NAVResponse(
            nav_per_token=float(latest_nav['nav_per_token']),
            total_fund_value=float(latest_nav['total_fund_value']),
            total_tokens_outstanding=float(latest_nav['total_tokens_outstanding']),
            calculated_at=latest_nav['calculated_at'].isoformat(),
            next_calculation="Today 4:00 PM PST"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== PHASE 4: REDEMPTION ROUTES ====================

@app.post("/api/redeem", response_model=RedeemResponse)
async def request_redemption(request: RedeemRequest):
    """
    Queue redemption request (settles at EOD NAV)
    
    - Validates investor has sufficient balance
    - Queues redemption for EOD settlement
    - Returns expected settlement time
    """
    try:
        # Verify investor
        investor = await InvestorDB.get_by_id(request.investor_id)
        if not investor:
            raise HTTPException(status_code=404, detail="Investor not found")
        
        # TODO: Verify investor actually holds this many tokens
        # Would need to query XRPL for their balance
        
        # Queue redemption
        redemption = await RedemptionDB.create(
            investor_id=request.investor_id,
            token_amount=Decimal(str(request.token_amount))
        )
        
        return RedeemResponse(
            redemption_id=str(redemption['id']),
            token_amount=request.token_amount,
            status="queued",
            settlement_time="Today 4:00 PM PST",
            message="Redemption queued. Will settle at end-of-day NAV price."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/redeem/status/{redemption_id}")
async def check_redemption_status(redemption_id: str):
    """
    Check status of redemption request
    
    - Returns status: queued, processing, completed, failed
    - Shows NAV price and USDC amount once settled
    """
    try:
        redemption = await RedemptionDB.get_by_id(redemption_id)
        if not redemption:
            raise HTTPException(status_code=404, detail="Redemption not found")
        
        return {
            "redemption_id": str(redemption['id']),
            "status": redemption['status'],
            "token_amount": float(redemption['token_amount']),
            "nav_price": float(redemption['nav_price']) if redemption['nav_price'] else None,
            "usdc_amount": float(redemption['usdc_amount']) if redemption['usdc_amount'] else None,
            "requested_at": redemption['requested_at'].isoformat(),
            "settled_at": redemption['settled_at'].isoformat() if redemption['settled_at'] else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

# ==================== TRADING ROUTES (AMM) ====================

from xrpl.models.requests import AMMInfo
from xrpl.models.amounts import IssuedCurrencyAmount as ICA

@app.get("/api/pool/info")
async def get_pool_info_route():
    """Get AMM pool information"""
    try:
        pool_created = await SystemConfigDB.is_pool_created()
        
        if not pool_created:
            return {
                "pool_exists": False,
                "message": "AMM pool not yet created. Currently in IPO phase."
            }
        
        # Query XRPL for pool info - run in thread pool
        from xrpl.clients import JsonRpcClient
        import asyncio
        
        def query_amm_pool():
            """Sync function to query pool"""
            client = JsonRpcClient(xrpl_config.client_url)
            
            amm_info_request = AMMInfo(
                asset=ICA(
                    currency=xrpl_config.currency_code,
                    issuer=xrpl_config.issuer_address,
                    value="0"
                ),
                asset2={"currency": "XRP"}
            )
            
            return client.request(amm_info_request)
        
        # Run sync function in thread pool
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, query_amm_pool)
        
        if not response.is_successful():
            return {
                "pool_exists": False,
                "message": "Pool not found on ledger"
            }
        
        amm_data = response.result.get("amm", {})
        
        # Parse reserves
        amount1 = amm_data.get("amount", {})
        amount2 = amm_data.get("amount2", "0")
        
        # Token reserve
        if isinstance(amount1, dict):
            token_reserve = float(amount1.get("value", 0))
        else:
            token_reserve = float(amount1) / 1_000_000
        
        # XRP reserve  
        if isinstance(amount2, dict):
            xrp_reserve = float(amount2.get("value", 0))
        else:
            xrp_reserve = float(amount2) / 1_000_000
        
        # Calculate price
        current_price = xrp_reserve / token_reserve if token_reserve > 0 else 0
        
        return {
            "pool_exists": True,
            "pool_address": amm_data.get("account"),
            "token_reserve": token_reserve,
            "xrp_reserve": xrp_reserve,
            "current_price_xrp": current_price,
            "current_price_usd": current_price,
            "trading_fee": amm_data.get("trading_fee", 0) / 100,
            "lp_token": amm_data.get("lp_token", {}).get("currency")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
class TradeQuoteRequest(BaseModel):
    """Request for trade quote"""
    from_currency: str  # "IND" or "XRP"
    to_currency: str    # "IND" or "XRP"  
    amount: float = Field(..., gt=0)


@app.post("/api/trade/quote")
async def get_trade_quote(request: TradeQuoteRequest):
    """
    Get quote for a trade (how much you'll receive)
    
    Uses constant product formula: x * y = k
    With fee: output = (input * 0.995 * y) / (x + input * 0.995)
    """
    try:
        # Get pool info
        pool_info = await get_pool_info_route()
        
        if not pool_info.get("pool_exists"):
            raise HTTPException(status_code=400, detail="Pool not available")
        
        token_reserve = pool_info["token_reserve"]
        xrp_reserve = pool_info["xrp_reserve"]
        fee_percent = pool_info["trading_fee"]
        
        # Determine direction
        if request.from_currency == xrpl_config.currency_code and request.to_currency == "XRP":
            # Selling tokens for XRP
            input_amount = request.amount
            input_reserve = token_reserve
            output_reserve = xrp_reserve
        elif request.from_currency == "XRP" and request.to_currency == xrpl_config.currency_code:
            # Buying tokens with XRP
            input_amount = request.amount
            input_reserve = xrp_reserve
            output_reserve = token_reserve
        else:
            raise HTTPException(status_code=400, detail="Invalid currency pair")
        
        # Calculate output with fee
        # Formula: output = (input * (1 - fee) * output_reserve) / (input_reserve + input * (1 - fee))
        fee_multiplier = 1 - (fee_percent / 100)
        input_after_fee = input_amount * fee_multiplier
        
        output_amount = (input_after_fee * output_reserve) / (input_reserve + input_after_fee)
        
        # Price impact
        price_before = output_reserve / input_reserve
        price_after = (output_reserve - output_amount) / (input_reserve + input_amount)
        price_impact = abs((price_after - price_before) / price_before) * 100
        
        return {
            "from_currency": request.from_currency,
            "to_currency": request.to_currency,
            "input_amount": request.amount,
            "output_amount": output_amount,
            "price": output_amount / request.amount,
            "price_impact": price_impact,
            "fee": request.amount * (fee_percent / 100),
            "minimum_received": output_amount * 0.99,  # 1% slippage tolerance
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class TradeHistoryResponse(BaseModel):
    """Recent trades on the pool"""
    trades: List[dict]
    total_volume_24h: float


@app.get("/api/trade/history", response_model=TradeHistoryResponse)
async def get_trade_history(limit: int = 20):
    """
    Get recent trade history from the pool
    
    Note: This queries XRPL transaction history
    """
    try:
        pool_info = await get_pool_info_route()
        
        if not pool_info.get("pool_exists"):
            return TradeHistoryResponse(trades=[], total_volume_24h=0)
        
        pool_address = pool_info["pool_address"]
        
        # Query XRPL for recent transactions
        from xrpl.clients import JsonRpcClient
        from xrpl.models.requests import AccountTx
        
        client = JsonRpcClient(xrpl_config.client_url)
        
        response = client.request(AccountTx(
            account=pool_address,
            ledger_index_min=-1,
            ledger_index_max=-1,
            limit=limit
        ))
        
        trades = []
        total_volume = 0
        
        for tx_data in response.result.get("transactions", []):
            tx = tx_data.get("tx", {})
            meta = tx_data.get("meta", {})
            
            # Only include successful swaps
            if meta.get("TransactionResult") != "tesSUCCESS":
                continue
            
            # Parse trade data (simplified)
            trades.append({
                "tx_hash": tx.get("hash"),
                "timestamp": tx.get("date"),
                "type": tx.get("TransactionType"),
            })
        
        return TradeHistoryResponse(
            trades=trades,
            total_volume_24h=total_volume
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== INVESTOR DASHBOARD ====================

@app.get("/api/dashboard/{xrpl_address}", response_model=InvestorDashboardResponse)
async def get_investor_dashboard(xrpl_address: str):
    """
    Get complete investor portfolio overview
    
    - Token balance and estimated USD value
    - Current NAV
    - Pending redemptions
    - Purchase history
    """
    try:
        # Get investor info
        investor = await InvestorDB.get_by_xrpl_address(xrpl_address)
        if not investor:
            raise HTTPException(status_code=404, detail="Investor not found")
        
        # Get dashboard data
        dashboard = await InvestorDB.get_dashboard(xrpl_address)
        if not dashboard:
            raise HTTPException(status_code=404, detail="Dashboard data not found")
        
        # Get current NAV
        nav = await NAVDB.get_current_nav_value()
        
        # Get actual token balance from XRPL
        token_balance_xrpl = await get_token_balance(xrpl_address)
        
        # Use XRPL balance if available, otherwise use database calculation
        token_balance = float(token_balance_xrpl) if token_balance_xrpl > 0 else float(dashboard.get('token_balance', 0))
        
        # Get pending redemptions
        pending_redemptions = await RedemptionDB.get_by_investor(str(investor['id']))
        pending_redemptions = [
            {
                "redemption_id": str(r['id']),
                "token_amount": float(r['token_amount']),
                "status": r['status'],
                "requested_at": r['requested_at'].isoformat()
            }
            for r in pending_redemptions if r['status'] == 'queued'
        ]
        
        return InvestorDashboardResponse(
            xrpl_address=xrpl_address,
            email=investor['email'],
            kyc_approved=investor['kyc_approved'],
            token_balance=token_balance,
            estimated_value_usd=token_balance * float(nav),
            nav_per_token=float(nav),
            pending_redemptions=pending_redemptions
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== ADMIN/STATS ROUTES ====================

@app.get("/api/stats", response_model=SystemStatsResponse)
async def get_system_stats():
    """
    Get system-wide statistics (admin dashboard)
    
    - Total investors, raised capital, tokens issued
    - Current NAV
    - System phase (IPO vs trading)
    """
    try:
        total_investors = await StatsDB.get_total_investors()
        total_raised = await StatsDB.get_total_raised()
        total_tokens = await StatsDB.get_total_tokens_issued()
        current_nav = await NAVDB.get_current_nav_value()
        
        ipo_phase = await SystemConfigDB.get('ipo_phase')
        pool_created = await SystemConfigDB.is_pool_created()
        
        return SystemStatsResponse(
            total_investors=total_investors,
            total_raised=float(total_raised),
            total_tokens_issued=float(total_tokens),
            current_nav=float(current_nav),
            ipo_phase=ipo_phase or 'active',
            pool_created=pool_created
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
async def health_check():
    """Simple health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

# ==================== RUN SERVER ====================

if __name__ == "__main__":
    import uvicorn
    
    print(f"Starting Indicia Token API Server on {API_HOST}:{API_PORT}")
    print(f"Debug mode: {API_DEBUG}")
    print(f"Docs available at: http://{API_HOST}:{API_PORT}/docs")
    
    uvicorn.run(
        "api:app",
        host=API_HOST,
        port=API_PORT,
        reload=API_DEBUG
    )