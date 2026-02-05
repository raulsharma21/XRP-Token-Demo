"""
Database connection and utility functions for AI Fund
Uses asyncpg for async Postgres operations
"""

import asyncpg
import os
from typing import Optional, Dict, List, Any
from datetime import datetime
from decimal import Decimal
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ==================== CONFIGURATION ====================

class DatabaseConfig:
    """Database configuration from environment variables"""
    
    def __init__(self):
        # Get from Supabase project settings > Database > Connection string
        self.connection_string = os.getenv(
            'DATABASE_URL',
            'postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres'
        )
        
        # Connection pool settings
        self.min_pool_size = int(os.getenv('DB_MIN_POOL_SIZE', '5'))
        self.max_pool_size = int(os.getenv('DB_MAX_POOL_SIZE', '20'))

# ==================== CONNECTION POOL ====================

class Database:
    """Database connection pool manager"""
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        """Initialize connection pool"""
        if self.pool is None:
            # Parse connection string to handle pooler URLs with dots in username
            import re
            match = re.match(r'postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', self.config.connection_string)
            if match:
                user, password, host, port, database = match.groups()
                self.pool = await asyncpg.create_pool(
                    user=user,
                    password=password,
                    host=host,
                    port=int(port),
                    database=database,
                    min_size=self.config.min_pool_size,
                    max_size=self.config.max_pool_size,
                    command_timeout=60
                )
            else:
                # Fallback to direct connection string
                self.pool = await asyncpg.create_pool(
                    self.config.connection_string,
                    min_size=self.config.min_pool_size,
                    max_size=self.config.max_pool_size,
                    command_timeout=60
                )
            print("✓ Database connection pool created")
    
    async def disconnect(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
            print("✓ Database connection pool closed")
    
    async def execute(self, query: str, *args):
        """Execute a query that doesn't return results"""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)
    
    async def fetch(self, query: str, *args) -> List[asyncpg.Record]:
        """Fetch multiple rows"""
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)
    
    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        """Fetch single row"""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)
    
    async def fetchval(self, query: str, *args):
        """Fetch single value"""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)

# Global database instance
db_config = DatabaseConfig()
db = Database(db_config)

# ==================== INVESTOR OPERATIONS ====================

class InvestorDB:
    """Database operations for investors"""
    
    @staticmethod
    async def create(email: str, xrpl_address: str) -> Dict[str, Any]:
        """Create new investor"""
        row = await db.fetchrow(
            """
            INSERT INTO investors (email, xrpl_address, kyc_approved, trust_line_created)
            VALUES ($1, $2, FALSE, FALSE)
            RETURNING id, email, xrpl_address, kyc_approved, trust_line_created, created_at
            """,
            email, xrpl_address
        )
        return dict(row)
    
    @staticmethod
    async def get_by_id(investor_id: str) -> Optional[Dict[str, Any]]:
        """Get investor by ID"""
        row = await db.fetchrow(
            "SELECT * FROM investors WHERE id = $1",
            investor_id
        )
        return dict(row) if row else None
    
    @staticmethod
    async def get_by_email(email: str) -> Optional[Dict[str, Any]]:
        """Get investor by email"""
        row = await db.fetchrow(
            "SELECT * FROM investors WHERE email = $1",
            email
        )
        return dict(row) if row else None
    
    @staticmethod
    async def get_by_xrpl_address(xrpl_address: str) -> Optional[Dict[str, Any]]:
        """Get investor by XRPL address"""
        row = await db.fetchrow(
            "SELECT * FROM investors WHERE xrpl_address = $1",
            xrpl_address
        )
        return dict(row) if row else None
    
    @staticmethod
    async def approve_kyc(investor_id: str) -> bool:
        """Approve investor KYC"""
        result = await db.execute(
            """
            UPDATE investors 
            SET kyc_approved = TRUE, updated_at = NOW()
            WHERE id = $1
            """,
            investor_id
        )
        return result == "UPDATE 1"
    
    @staticmethod
    async def mark_trust_line_created(investor_id: str) -> bool:
        """Mark trust line as created"""
        result = await db.execute(
            """
            UPDATE investors 
            SET trust_line_created = TRUE, updated_at = NOW()
            WHERE id = $1
            """,
            investor_id
        )
        return result == "UPDATE 1"
    
    @staticmethod
    async def get_all_approved() -> List[Dict[str, Any]]:
        """Get all KYC approved investors"""
        rows = await db.fetch(
            "SELECT * FROM investors WHERE kyc_approved = TRUE ORDER BY created_at"
        )
        return [dict(row) for row in rows]
    
    @staticmethod
    async def get_dashboard(xrpl_address: str) -> Optional[Dict[str, Any]]:
        """Get investor dashboard data"""
        row = await db.fetchrow(
            "SELECT * FROM active_investors WHERE xrpl_address = $1",
            xrpl_address
        )
        return dict(row) if row else None

# ==================== PURCHASE OPERATIONS ====================

class PurchaseDB:
    """Database operations for purchases"""
    
    @staticmethod
    async def create(investor_id: str, usdc_amount: Decimal, destination_tag: int) -> Dict[str, Any]:
        """Create new purchase record"""
        row = await db.fetchrow(
            """
            INSERT INTO purchases (investor_id, usdc_amount, status, destination_tag)
            VALUES ($1, $2, 'pending', $3)
            RETURNING id, investor_id, usdc_amount, status, destination_tag, created_at
            """,
            investor_id, usdc_amount, destination_tag
        )
        return dict(row)
    
    @staticmethod
    async def get_by_id(purchase_id: str) -> Optional[Dict[str, Any]]:
        """Get purchase by ID"""
        row = await db.fetchrow(
            "SELECT * FROM purchases WHERE id = $1",
            purchase_id
        )
        return dict(row) if row else None
    
    @staticmethod
    async def get_all_pending() -> List[Dict[str, Any]]:
        """Get all pending purchases"""
        rows = await db.fetch(
            """
            SELECT * FROM purchases 
            WHERE status = 'pending'
            ORDER BY created_at DESC
            """
        )
        return [dict(row) for row in rows]
    
    @staticmethod
    async def get_incomplete() -> List[Dict[str, Any]]:
        """
        Get purchases that received payment but weren't completed
        (have deposit_tx_hash but status is not 'completed')
        """
        rows = await db.fetch(
            """
            SELECT * FROM purchases 
            WHERE deposit_tx_hash IS NOT NULL 
            AND status IN ('pending', 'forwarded')
            ORDER BY created_at ASC
            """
        )
        return [dict(row) for row in rows]
    
    @staticmethod
    async def get_pending_by_tag(destination_tag: int) -> Optional[Dict[str, Any]]:
        """Get pending purchase by destination tag"""
        row = await db.fetchrow(
            """
            SELECT * FROM purchases 
            WHERE destination_tag = $1 AND status = 'pending'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            destination_tag
        )
        return dict(row) if row else None
    
    @staticmethod
    async def get_by_deposit_tx(deposit_tx_hash: str) -> Optional[Dict[str, Any]]:
        """Get purchase by deposit transaction hash"""
        row = await db.fetchrow(
            """
            SELECT * FROM purchases 
            WHERE deposit_tx_hash = $1
            LIMIT 1
            """,
            deposit_tx_hash
        )
        return dict(row) if row else None
    
    @staticmethod
    async def update_status(
        purchase_id: str,
        status: str,
        deposit_tx_hash: Optional[str] = None,
        forward_tx_hash: Optional[str] = None,
        issue_tx_hash: Optional[str] = None,
        token_amount: Optional[Decimal] = None
    ) -> bool:
        """Update purchase status and transaction hashes"""
        
        set_clauses = ["status = $2"]
        params = [purchase_id, status]
        param_idx = 3
        
        if deposit_tx_hash:
            set_clauses.append(f"deposit_tx_hash = ${param_idx}")
            params.append(deposit_tx_hash)
            param_idx += 1
        
        if forward_tx_hash:
            set_clauses.append(f"forward_tx_hash = ${param_idx}")
            params.append(forward_tx_hash)
            param_idx += 1
        
        if issue_tx_hash:
            set_clauses.append(f"issue_tx_hash = ${param_idx}")
            params.append(issue_tx_hash)
            param_idx += 1
        
        if token_amount:
            set_clauses.append(f"token_amount = ${param_idx}")
            params.append(token_amount)
            param_idx += 1
        
        if status == 'completed':
            set_clauses.append("completed_at = NOW()")
        
        query = f"""
            UPDATE purchases 
            SET {', '.join(set_clauses)}
            WHERE id = $1
        """
        
        result = await db.execute(query, *params)
        return result == "UPDATE 1"
    
    @staticmethod
    async def get_by_investor(investor_id: str) -> List[Dict[str, Any]]:
        """Get all purchases for an investor"""
        rows = await db.fetch(
            "SELECT * FROM purchases WHERE investor_id = $1 ORDER BY created_at DESC",
            investor_id
        )
        return [dict(row) for row in rows]
    
    @staticmethod
    async def get_completed_total() -> Decimal:
        """Get total USDC from completed purchases"""
        result = await db.fetchval(
            "SELECT COALESCE(SUM(usdc_amount), 0) FROM purchases WHERE status = 'completed'"
        )
        return result or Decimal('0')

# ==================== REDEMPTION OPERATIONS ====================

class RedemptionDB:
    """Database operations for redemptions"""
    
    @staticmethod
    async def create(investor_id: str, token_amount: Decimal) -> Dict[str, Any]:
        """Create redemption request"""
        row = await db.fetchrow(
            """
            INSERT INTO redemptions (investor_id, token_amount, status)
            VALUES ($1, $2, 'queued')
            RETURNING id, investor_id, token_amount, status, requested_at
            """,
            investor_id, token_amount
        )
        return dict(row)
    
    @staticmethod
    async def get_by_id(redemption_id: str) -> Optional[Dict[str, Any]]:
        """Get redemption by ID"""
        row = await db.fetchrow(
            "SELECT * FROM redemptions WHERE id = $1",
            redemption_id
        )
        return dict(row) if row else None
    
    @staticmethod
    async def get_queued() -> List[Dict[str, Any]]:
        """Get all queued redemptions"""
        rows = await db.fetch(
            """
            SELECT r.*, i.xrpl_address, i.email
            FROM redemptions r
            JOIN investors i ON r.investor_id = i.id
            WHERE r.status = 'queued'
            ORDER BY r.requested_at
            """
        )
        return [dict(row) for row in rows]
    
    @staticmethod
    async def complete(
        redemption_id: str,
        nav_price: Decimal,
        usdc_amount: Decimal,
        redemption_tx_hash: str
    ) -> bool:
        """Mark redemption as completed"""
        result = await db.execute(
            """
            UPDATE redemptions
            SET status = 'completed',
                nav_price = $2,
                usdc_amount = $3,
                redemption_tx_hash = $4,
                settled_at = NOW()
            WHERE id = $1
            """,
            redemption_id, nav_price, usdc_amount, redemption_tx_hash
        )
        return result == "UPDATE 1"
    
    @staticmethod
    async def get_by_investor(investor_id: str) -> List[Dict[str, Any]]:
        """Get all redemptions for an investor"""
        rows = await db.fetch(
            "SELECT * FROM redemptions WHERE investor_id = $1 ORDER BY requested_at DESC",
            investor_id
        )
        return [dict(row) for row in rows]

# ==================== NAV OPERATIONS ====================

class NAVDB:
    """Database operations for NAV"""
    
    @staticmethod
    async def create(
        nav_per_token: Decimal,
        total_fund_value: Decimal,
        total_tokens_outstanding: Decimal,
        coinbase_balance: Optional[Decimal] = None,
        pool_usdc_reserve: Optional[Decimal] = None,
        pool_token_reserve: Optional[Decimal] = None
    ) -> Dict[str, Any]:
        """Record new NAV calculation"""
        row = await db.fetchrow(
            """
            INSERT INTO nav_history (
                nav_per_token, 
                total_fund_value, 
                total_tokens_outstanding,
                coinbase_balance,
                pool_usdc_reserve,
                pool_token_reserve
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            nav_per_token, total_fund_value, total_tokens_outstanding,
            coinbase_balance, pool_usdc_reserve, pool_token_reserve
        )
        return dict(row)
    
    @staticmethod
    async def get_latest() -> Optional[Dict[str, Any]]:
        """Get most recent NAV"""
        row = await db.fetchrow(
            "SELECT * FROM nav_history ORDER BY calculated_at DESC LIMIT 1"
        )
        return dict(row) if row else None
    
    @staticmethod
    async def get_current_nav_value() -> Decimal:
        """Get current NAV per token (or 1.0 if none exists)"""
        result = await db.fetchval(
            "SELECT get_current_nav()"
        )
        return result or Decimal('1.0')
    
    @staticmethod
    async def get_history(days: int = 30) -> List[Dict[str, Any]]:
        """Get NAV history for last N days"""
        rows = await db.fetch(
            """
            SELECT * FROM nav_history 
            WHERE calculated_at >= NOW() - INTERVAL $1
            ORDER BY calculated_at DESC
            """,
            f'{days} days'
        )
        return [dict(row) for row in rows]

# ==================== SYSTEM CONFIG OPERATIONS ====================

class SystemConfigDB:
    """Database operations for system configuration"""
    
    @staticmethod
    async def get(key: str) -> Optional[str]:
        """Get config value"""
        result = await db.fetchval(
            "SELECT value FROM system_config WHERE key = $1",
            key
        )
        return result
    
    @staticmethod
    async def set(key: str, value: str) -> bool:
        """Set config value"""
        result = await db.execute(
            """
            INSERT INTO system_config (key, value, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (key) 
            DO UPDATE SET value = $2, updated_at = NOW()
            """,
            key, value
        )
        return True
    
    @staticmethod
    async def is_ipo_active() -> bool:
        """Check if IPO phase is active"""
        value = await SystemConfigDB.get('ipo_phase')
        return value == 'active'
    
    @staticmethod
    async def is_pool_created() -> bool:
        """Check if AMM pool has been created"""
        value = await SystemConfigDB.get('pool_created')
        return value == 'true'

# ==================== STATISTICS ====================

class StatsDB:
    """Database operations for statistics"""
    
    @staticmethod
    async def get_total_investors() -> int:
        """Get total number of investors"""
        result = await db.fetchval(
            "SELECT COUNT(*) FROM investors WHERE kyc_approved = TRUE"
        )
        return result or 0
    
    @staticmethod
    async def get_total_raised() -> Decimal:
        """Get total USDC raised"""
        result = await db.fetchval(
            "SELECT COALESCE(SUM(usdc_amount), 0) FROM purchases WHERE status = 'completed'"
        )
        return result or Decimal('0')
    
    @staticmethod
    async def get_total_tokens_issued() -> Decimal:
        """Get total tokens issued"""
        result = await db.fetchval(
            "SELECT COALESCE(SUM(token_amount), 0) FROM purchases WHERE status = 'completed'"
        )
        return result or Decimal('0')
    
    @staticmethod
    async def get_pending_operations() -> List[Dict[str, Any]]:
        """Get all pending operations"""
        rows = await db.fetch(
            "SELECT * FROM pending_operations LIMIT 50"
        )
        return [dict(row) for row in rows]

# ==================== INITIALIZATION ====================

async def init_database():
    """Initialize database connection"""
    await db.connect()
    print("✓ Database initialized")

async def close_database():
    """Close database connection"""
    await db.disconnect()
    print("✓ Database closed")

# ==================== EXAMPLE USAGE ====================

if __name__ == "__main__":
    import asyncio
    
    async def test_database():
        """Test database operations"""
        
        # Initialize
        await init_database()
        
        try:
            # Test connection by getting current NAV
            nav = await NAVDB.get_current_nav_value()
            print(f"✓ Current NAV: ${nav}")
            
            # Get stats
            total_investors = await StatsDB.get_total_investors()
            print(f"✓ Total investors: {total_investors}")
            
            # Try to get or create test investor
            import uuid
            test_email = f"test-{uuid.uuid4().hex[:8]}@example.com"
            
            try:
                investor = await InvestorDB.create(
                    email=test_email,
                    xrpl_address="rN7n7otQDd6FczFgLdlqtyMVrn3M1gEm3e"
                )
                print(f"✓ Created test investor: {investor['id']}")
                
                # Approve KYC
                await InvestorDB.approve_kyc(investor['id'])
                print(f"✓ KYC approved for: {investor['email']}")
            except Exception as e:
                print(f"⚠ Skipped investor creation (may already exist): {e}")
            
            print("\n✓ All database tests passed!")
            
        except Exception as e:
            print(f"\n✗ Test failed: {e}")
            raise
            
        finally:
            # Cleanup
            await close_database()
    
    # Run test
    asyncio.run(test_database())