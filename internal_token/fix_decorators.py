#!/usr/bin/env python3
"""
Script to add @handle_errors decorator and remove try/except blocks from API endpoints
"""

import re

# Read the file
with open('api.py', 'r') as f:
    content = f.read()

# Pattern to find endpoints that need fixing (those without @handle_errors)
# Find @app.{method} followed by async def, then find try/except blocks inside
pattern = r'(@app\.(get|post|put|delete)\([^)]+\))\n(async def [^:]+:)\n(\s+"""[^"]*""")\n(\s+try:)([\s\S]*?)(\s+except HTTPException:\n\s+raise\n\s+except Exception as e:\n\s+raise HTTPException\(status_code=500, detail=str\(e\)\))'

def fix_endpoint(match):
    decorator = match.group(1)
    func_def = match.group(3)
    docstring = match.group(4)
    body = match.group(6)
    
    # Remove indentation from body (it was indented under try:)
    lines = body.split('\n')
    fixed_lines = []
    for line in lines:
        if line.strip():  # Only process non-empty lines
            # Remove one level of indentation (4 spaces)
            if line.startswith('        '):
                fixed_lines.append(line[4:])
            else:
                fixed_lines.append(line)
        else:
            fixed_lines.append(line)
    
    fixed_body = '\n'.join(fixed_lines)
    
    # Check if @handle_errors is already there
    if '@handle_errors' not in decorator:
        return f'{decorator}\n@handle_errors\n{func_def}\n{docstring}\n{fixed_body}'
    else:
        return match.group(0)  # Return unchanged if decorator already exists

# Apply the fix
fixed_content = re.sub(pattern, fix_endpoint, content)

# Write back
with open('api.py', 'w') as f:
    f.write(fixed_content)

print("✓ Fixed API decorators")
