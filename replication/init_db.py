"""Initialize database schema for all nodes.

This script creates the necessary tables (orders, op_log, log_acknowledgements)
and applies the appropriate constraints for each node.
"""

import asyncio
import sys
from typing import Optional

import asyncpg


# SQL to create tables
CREATE_ORDERS_TABLE = """
CREATE TABLE IF NOT EXISTS orders (
    order_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    quantity int NOT NULL,
    payload jsonb,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);
"""

CREATE_OP_LOG_TABLE = """
CREATE TABLE IF NOT EXISTS op_log (
    op_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    origin_node text NOT NULL,
    op_type text NOT NULL,
    table_name text NOT NULL,
    row_id uuid NOT NULL,
    payload jsonb,
    ts timestamptz DEFAULT now(),
    lamport bigint DEFAULT 0,
    applied boolean DEFAULT false,
    applied_ts timestamptz
);

CREATE INDEX IF NOT EXISTS idx_oplog_origin_ts ON op_log(origin_node, ts);
CREATE INDEX IF NOT EXISTS idx_oplog_lamport ON op_log(lamport);
CREATE INDEX IF NOT EXISTS idx_oplog_applied ON op_log(applied) WHERE NOT applied;
"""

CREATE_ACK_TABLE = """
CREATE TABLE IF NOT EXISTS log_acknowledgements (
    op_id uuid REFERENCES op_log(op_id) ON DELETE CASCADE,
    node text NOT NULL,
    ack_ts timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (op_id, node)
);
"""

# Constraints for fragment nodes
NODE1_CONSTRAINT = """
DO $$ 
BEGIN
    -- Drop existing constraint if it exists
    IF EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'qty_1to5'
    ) THEN
        ALTER TABLE orders DROP CONSTRAINT qty_1to5;
    END IF;
    
    -- Add constraint for Node 1 (quantity 1-5)
    ALTER TABLE orders ADD CONSTRAINT qty_1to5 CHECK (quantity >= 1 AND quantity <= 5);
END $$;
"""

NODE2_CONSTRAINT = """
DO $$ 
BEGIN
    -- Drop existing constraint if it exists
    IF EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'qty_6to10'
    ) THEN
        ALTER TABLE orders DROP CONSTRAINT qty_6to10;
    END IF;
    
    -- Add constraint for Node 2 (quantity 6-10)
    ALTER TABLE orders ADD CONSTRAINT qty_6to10 CHECK (quantity >= 6 AND quantity <= 10);
END $$;
"""


async def init_node(dsn: str, node_name: str, apply_constraint: Optional[str] = None) -> None:
    """Initialize a single node's database."""
    print(f"\n{'='*60}")
    print(f"Initializing {node_name}...")
    print(f"{'='*60}")
    
    try:
        conn = await asyncpg.connect(dsn=dsn)
        
        # Create tables
        print("  ✓ Creating orders table...")
        await conn.execute(CREATE_ORDERS_TABLE)
        
        print("  ✓ Creating op_log table...")
        await conn.execute(CREATE_OP_LOG_TABLE)
        
        print("  ✓ Creating log_acknowledgements table...")
        await conn.execute(CREATE_ACK_TABLE)
        
        # Apply constraint if specified
        if apply_constraint:
            print(f"  ✓ Applying partition constraint...")
            await conn.execute(apply_constraint)
        
        # Check tables
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('orders', 'op_log', 'log_acknowledgements')
            ORDER BY table_name
        """)
        
        print(f"  ✓ Tables created: {', '.join([t['table_name'] for t in tables])}")
        
        # Check constraints
        constraints = await conn.fetch("""
            SELECT conname, pg_get_constraintdef(oid) as definition
            FROM pg_constraint
            WHERE conrelid = 'orders'::regclass
            AND conname LIKE 'qty_%'
        """)
        
        if constraints:
            for c in constraints:
                print(f"  ✓ Constraint: {c['conname']}")
        else:
            print(f"  • No partition constraints (Central node)")
        
        # Count existing orders
        count = await conn.fetchval("SELECT COUNT(*) FROM orders")
        print(f"  • Current orders count: {count}")
        
        await conn.close()
        print(f"✅ {node_name} initialized successfully!")
        
    except Exception as e:
        print(f"❌ Error initializing {node_name}: {e}")
        raise


async def main() -> None:
    """Initialize all three nodes."""
    print("\n" + "="*60)
    print("DISTRIBUTED DATABASE INITIALIZATION")
    print("="*60)
    
    # Get PostgreSQL password (from command line arg or prompt)
    import getpass
    if len(sys.argv) > 1:
        password = sys.argv[1]
    else:
        password = getpass.getpass("Enter PostgreSQL password: ")
    
    if not password:
        print("❌ Password is required!")
        sys.exit(1)
    
    # Define DSNs for each node
    node0_dsn = f"postgresql://postgres:{password}@localhost:5432/node0db"
    node1_dsn = f"postgresql://postgres:{password}@localhost:5432/node1db"
    node2_dsn = f"postgresql://postgres:{password}@localhost:5432/node2db"
    
    try:
        # Initialize Node 0 (Central - no constraint)
        await init_node(node0_dsn, "Node 0 (Central)", apply_constraint=None)
        
        # Initialize Node 1 (Fragment: quantity 1-5)
        await init_node(node1_dsn, "Node 1 (Fragment: qty 1-5)", apply_constraint=NODE1_CONSTRAINT)
        
        # Initialize Node 2 (Fragment: quantity 6-10)
        await init_node(node2_dsn, "Node 2 (Fragment: qty 6-10)", apply_constraint=NODE2_CONSTRAINT)
        
        print("\n" + "="*60)
        print("✅ ALL NODES INITIALIZED SUCCESSFULLY!")
        print("="*60)
        print("\nNext steps:")
        print("  1. Start the backend nodes: .\\start-nodes.ps1")
        print("  2. Start the frontend: .\\start-frontend.ps1")
        print("  3. Open http://localhost:5173 in your browser")
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"\n❌ Initialization failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
