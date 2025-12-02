# STADVDB MCO2
notes:
software installed in VMs done via:
`sudo apt update`
`sudo apt install -y postgresql postgresql-contrib python3 python3-venv python3-pip git gh`

updated postgres from pg14 to pg18 (pg14 isnt in standard ubuntu library yet hence use link)
`sudo sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'`
`sudo apt install gnupg gnupg1 gnupg2`
`wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -`
`sudo apt update`
`sudo apt install postgresql-18`
`sudo systemctl stop postgresql@14-main`
`sudo systemctl disable postgresql@14-main`
`sudo systemctl enable postgresql@18-main`
`sudo systemctl start postgresql`
`psql --version` should now be 18.1

`sudo -i -u postgres` to enter postgres user
`psql` to enter postgres from user

`\q` to exit postgres
`exit` to get to root

`pg_lsclusters` to check port
`root@STADVDB44-ServerX:~# sudo systemctl <start>/<stop>/<restart> postgresql` to restart/stop server
`sudo nano /etc/postgresql/18/main/postgresql.conf` to configurate port et al

`CREATE DATABASE nodexdb;` to create database
`sudo -u postgres psql -c "SELECT version();"` to check database version
`postgres-# psql -d nodexdb` to go to database
`nodexdb=# \dt` to describe structure
`nodexdb=# SELECT * FROM public.orders LIMIT 50;` to viewrows

To find a file within our cloned stadvdb folder:
`postgres@STADVDB44-Server0:~$ find ~/STADVDB -name "truncated_dump.sql"`

To use our sql dump and load to database:
`postgres@STADVDB44-Server0:~$ psql -d nodexdb -f /root/STADVDB/MCO2.ETLs/truncated_dump.sql`
`cd STADVDB; git pull` from root to update
`rm -r STADVDB` to delete repo

to reset schema for node1 and 2
`psql -U postgres -d node2db -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"`
`psql -U postgres -d node2db -f <(pg_dump -U postgres -d node1db --schema-only)`
`psql -U postgres -d node2db -f /STADVDB/MCO2.ETLs/schema_only_dump.sql`

initialize node1 and node2:
`psql -U postgres -d node2db -c "\copy orders FROM '/STADVDB/MCO2.ETLs/node2.csv' CSV HEADER"`
`ALTER TABLE orders ADD CONSTRAINT qty_1to5 CHECK (quantity <= 5);` on node1
`ALTER TABLE orders ADD CONSTRAINT qty_6to10 CHECK (quantity > 5);` on node2

install to py to all vms
`sudo apt update`
`sudo apt install -y python3.10 python3.10-venv python3-pip`
`cd /path/to/your/checkout/replication`
`python3 -m venv .venv`
`source .venv/bin/activate`
`pip install --upgrade pip`
`pip install -r requirements.txt`

to make a new user:
`sudo -u postgres psql <<'SQL'`
`CREATE ROLE app_user WITH LOGIN PASSWORD 'password'; GRANT CONNECT ON DATABASE node2db TO app_user; `
`\c node2db`
`GRANT USAGE ON SCHEMA public TO app_user; GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.orders TO app_user; GRANT SELECT, INSERT, UPDATE ON TABLE public.op_log TO app_user; GRANT SELECT, INSERT ON TABLE public.log_acknowledgements TO app_user; GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO app_user;`

env node0:
export DATABASE_DSN="postgresql://app_user:password@localhost:3306/node0db"
export NODE_NAME="node0"
export PEER_NODES="http://10.2.14.133:8001,http://10.2.14.134:8002"
export POLL_INTERVAL="5"
export DEFAULT_MASTER="node0"
export PROMOTED="false"
export PARTITION_RULE="5"

env node1:
export DATABASE_DSN="postgresql://app_user:password@localhost:3306/node1db"
export NODE_NAME="node1"
export PEER_NODES="http://10.2.14.132:8000,http://10.2.14.134:8002"
export DEFAULT_MASTER="node0"
export PROMOTED="false"
export PARTITION_RULE="5"

env node2:
export DATABASE_DSN="postgresql://app_user:password@localhost:3306/node2db"
export NODE_NAME="node2"
export PEER_NODES="http://10.2.14.133:8001,http://10.2.14.134:8002"
export POLL_INTERVAL="5"
export DEFAULT_MASTER="node0"
export PROMOTED="false"
export PARTITION_RULE="5"

start from root:
# Node0 shell (on VM0)
cd ~/STADVDB/replication
export DATABASE_DSN="postgresql://app_user:password@localhost:3306/node0db"
export NODE_NAME="node0"
export DEFAULT_MASTER="node0"
export DEFAULT_MASTER_URL="http://VM0_IP:8000"
# Peers are node1 + node2
export PEER_NODES='[{"name":"node1","url":"http://VM1_IP:8001"},{"name":"node2","url":"http://VM2_IP:8002"}]'
export POLL_INTERVAL="5"
export APPLIER_INTERVAL="2"
export PROMOTED="false"
export PARTITION_RULE="5"

curl http://localhost:8000/health

source replication/.venv/bin/activate
uvicorn replication.main:app --host 0.0.0.0 --port 8000

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

===========================================================================================
OPLOG_ACKNOWLEDGEMENTS
===========================================================================================
CREATE TABLE IF NOT EXISTS log_acknowledgements (
  op_id uuid REFERENCES op_log(op_id) ON DELETE CASCADE,
  node text NOT NULL,
  ack_ts timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (op_id, node)
);

===========================================================================================
REPLICATION_CURSORS
===========================================================================================

CREATE TABLE IF NOT EXISTS replication_cursors (
  node TEXT PRIMARY KEY,
  last_lamport BIGINT NOT NULL
);


===========================================================================================