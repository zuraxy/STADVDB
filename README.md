# STADVDB MCO2
notes:
software installed in VMs done via:
`sudo apt update`
`sudo apt install -y postgresql postgresql-contrib python3 python3-venv python3-pip git gh`

`sudo -i -u postgres` to enter postgres user
`psql` to enter postgres from user

`\q` to exit postgres
`exit` to get to root

`pg_lsclusters` to check port
`root@STADVDB44-ServerX:~# sudo systemctl <stop>/<restart> postgresql` to start/stop server
`sudo nano /etc/postgresql/14/main/postgresql.conf` to configurate port et al

`CREATE DATABASE nodexdb;` to create database

To find a file within our cloned stadvdb folder:
`postgres@STADVDB44-Server0:~$ find ~/STADVDB -name "truncated_dump.sql"`

To use our sql dump and load to database:
`postgres@STADVDB44-Server0:~$ psql -d node0db -f /var/lib/postgresql/STADVDB/MCO2.ETLs/truncated_dump.sql`

==========================================================================================
UUID TABLE SCHEMA FOR ALL NODES
=========================================================================================
-- for uuid, use built-in (uuid functions)[https://www.postgresql.org/docs/current/functions-uuid.html] such as gen_random_uuid(), uuidv4(), or uuidv7(). perhaps need to install uuid-ossp.

CREATE EXTENSION IF NOT EXISTS uuid-ossp;

CREATE TABLE IF NOT EXISTS orders (
  order_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  quantity int NOT NULL,
  payload jsonb,         -- self contained data. This helps our oplog and makes a particular row/record be standalone.
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

-- On Node1:
ALTER TABLE orders ADD CONSTRAINT qty_1to5 CHECK (quantity <= 5);

-- On Node2:
ALTER TABLE orders ADD CONSTRAINT qty_6to10 CHECK (quantity > 5);
=========================================================================================
Logs
=========================================================================================
CREATE TABLE op_log (
  op_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),  -- unique event id
  origin_node text NOT NULL,                         -- 'node1','node2','node3'
  op_type text NOT NULL,                             -- 'INSERT','UPDATE','DELETE'
  table_name text NOT NULL,                          -- 'orders'
  row_id uuid NOT NULL,                              -- the PK of the row affected
  payload jsonb,                                     -- entire row (for insert/update)
  ts timestamptz DEFAULT now(),
  lamport bigint DEFAULT 0,                          -- Lamport timestamp (see below)
  applied boolean DEFAULT false,
  applied_ts timestamptz
);
CREATE INDEX idx_oplog_origin_ts ON op_log(origin_node, ts);
CREATE INDEX idx_oplog_lamport ON op_log(lamport);

CREATE TABLE IF NOT EXISTS log_acknowledgements (
  op_id uuid REFERENCES op_log(op_id) ON DELETE CASCADE,
  node text NOT NULL,
  ack_ts timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (op_id, node)
);

===========================================================================================