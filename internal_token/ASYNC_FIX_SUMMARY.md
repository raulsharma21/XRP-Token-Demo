# Async/Sync Compatibility Fix

## Problem
FastAPI is async, but XRPL functions (`check_trust_line_exists()`, `issue_tokens()`, etc.) were synchronous and used a sync XRPL client. When FastAPI (running in an async event loop) called these functions, it caused blocking issues.

## Solution
Implemented an `@async_compatible` decorator that wraps synchronous XRPL functions to run in a thread pool using `asyncio.to_thread()`. This approach:

1. **Doesn't block the event loop** - Sync operations run in separate threads
2. **Maintains compatibility** - Original sync functions accessible via `.sync` attribute
3. **Works with FastAPI** - Functions can be `await`ed in async endpoints
4. **No XRPL library changes** - We keep using the sync `JsonRpcClient`

## Changes Made

### 1. `xrpl_utils.py`
Added decorator and applied to all XRPL interaction functions:

```python
def async_compatible(func):
    """Make sync XRPL functions async-compatible for FastAPI"""
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        return await asyncio.to_thread(func, *args, **kwargs)
    
    async_wrapper.sync = func  # Keep sync version accessible
    return async_wrapper
```

**Functions decorated:**
- `get_xrp_balance()`
- `get_token_balance()`
- `check_trust_line_exists()`
- `authorize_trust_line()`
- `issue_tokens()`
- `forward_usdc_to_coinbase()`
- `send_usdc_to_investor()`
- `validate_xrpl_address()`

### 2. `api.py`
Updated all calls to XRPL functions to use `await`:

```python
# Before
if not validate_xrpl_address(request.xrpl_address):
    raise HTTPException(...)

# After
if not await validate_xrpl_address(request.xrpl_address):
    raise HTTPException(...)
```

**Updated calls in:**
- `POST /api/onboard` - Validates XRPL address
- `POST /api/investors/{id}/trust-line/authorize` - Checks and authorizes trust line
- `GET /api/investors/{id}/dashboard` - Gets token balance

### 3. `monitor.py`
Updated transaction monitor to await XRPL functions:

```python
# Before (incorrect - missing await)
forward_result = forward_usdc_to_coinbase(usdc_amount, from_wallet='deposit')

# Before (incorrect - using run_in_executor)
loop = asyncio.get_event_loop()
issue_result = await loop.run_in_executor(
    None,
    issue_tokens,
    investor['xrpl_address'],
    token_amount
)

# After (correct - using await with decorator)
forward_result = await forward_usdc_to_coinbase(usdc_amount, from_wallet='deposit')
issue_result = await issue_tokens(investor['xrpl_address'], token_amount)
```

**Note:** The decorator handles thread pool execution internally via `asyncio.to_thread()`, so you should use simple `await` calls, not `run_in_executor()`.

## Testing

Run the test script to verify everything works:

```bash
cd internal_token
python test_async_xrpl.py
```

This tests:
- Async function calls work correctly
- Balance queries function properly
- Trust line checks operate as expected
- Address validation works

## Benefits

1. **No blocking** - FastAPI event loop isn't blocked by XRPL operations
2. **Better performance** - Multiple XRPL calls can run concurrently
3. **Clean code** - Simple decorator pattern, minimal changes to existing code
4. **Backwards compatible** - Sync access still available via `.sync` attribute if needed

## Alternative Considered

We considered using `xrpl.asyncio.AsyncJsonRpcClient`, but that would have required:
- Rewriting all XRPL functions to be async
- Converting all `submit_and_wait()` calls to async versions
- More extensive testing

The decorator approach was simpler and required minimal code changes.

## Important: Calling Decorated Functions from Sync Context

When an async-decorated function needs to call another async-decorated function **from within its sync execution context**, you must use the `.sync` attribute to access the original synchronous version:

```python
@async_compatible
def issue_tokens(recipient_address: str, amount: Decimal) -> Dict:
    # WRONG - will fail because we're in a sync thread context
    # trust_line_exists = check_trust_line_exists(recipient_address)
    
    # CORRECT - use .sync to call the original sync version
    trust_line_exists = check_trust_line_exists.sync(recipient_address)
```

This is necessary because:
1. Decorated functions run in a thread pool via `asyncio.to_thread()`
2. You can't `await` inside a non-async function
3. The `.sync` attribute preserves access to the original synchronous implementation

**Affected functions:**
- `issue_tokens()` calls `check_trust_line_exists.sync()`
- `authorize_trust_line()` calls `check_trust_line_exists.sync()`

## Notes

- The sync XRPL client (`JsonRpcClient`) is still used under the hood
- Thread pool overhead is minimal for typical XRPL operations
- For high-frequency calls, consider caching results (e.g., balance queries)
- Always use `.sync` when calling decorated functions from within other decorated functions
