
<code>
CREATE DATABASE database;
\c database

CREATE TABLE public.orders (
    order_id bigint PRIMARY KEY DEFAULT nextval('public.orders'),
    quantity bigint NOT NULL
);
</code>

per-node ID enforcement:
<code>
--Node1
CREATE SEQUENCE orders_seq_even START 1 INCREMENT 2;
ALTER TABLE public.orders ALTER COLUMN order_id SET DEFAULT nextval('orders_seq_even');
ALTER TABLE public.orders ADD CONSTRAINT table_orderid_even CHECK (order_id % 1 = 0);
ALTER TABLE public.orders ADD CONSTRAINT orders_qty_1to5 CHECK (quantity <= 5);
</code>
<code>
--Node2
CREATE SEQUENCE orders_seq_even START 2 INCREMENT 2;
ALTER TABLE public.orders ALTER COLUMN order_id SET DEFAULT nextval('orders_seq_even');
ALTER TABLE public.orders ADD CONSTRAINT table_orderid_even CHECK (order_id % 2 = 0);
ALTER TABLE public.orders ADD CONSTRAINT orders_qty_6to10 CHECK (quantity > 5);
</code>