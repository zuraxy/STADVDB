--
-- PostgreSQL database dump
--

\restrict BjKMbipXdr0cbiSY7rFpkvBOUZRn6H6f5prN8ZAVCHd3yERDOMqzd1eZSWSRRoT

-- Dumped from database version 18.0
-- Dumped by pg_dump version 18.0

-- Started on 2025-11-30 19:25:59

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- TOC entry 3 (class 3079 OID 17556)
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- TOC entry 4980 (class 0 OID 0)
-- Dependencies: 3
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- TOC entry 2 (class 3079 OID 17545)
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;


--
-- TOC entry 4981 (class 0 OID 0)
-- Dependencies: 2
-- Name: EXTENSION "uuid-ossp"; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Drop existing tables, indexes, and constraints if they exist
--

DROP TABLE IF EXISTS public.log_acknowledgements CASCADE;
DROP TABLE IF EXISTS public.op_log CASCADE;
DROP TABLE IF EXISTS public.orders CASCADE;
DROP TABLE IF EXISTS public.replication_cursors CASCADE;

--
-- TOC entry 223 (class 1259 OID 17624)
-- Name: log_acknowledgements; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.log_acknowledgements (
    op_id uuid NOT NULL,
    node text NOT NULL,
    ack_ts timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.log_acknowledgements OWNER TO postgres;

--
-- TOC entry 222 (class 1259 OID 17606)
-- Name: op_log; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.op_log (
    op_id uuid DEFAULT gen_random_uuid() NOT NULL,
    origin_node text NOT NULL,
    op_type text NOT NULL,
    table_name text NOT NULL,
    row_id uuid NOT NULL,
    payload jsonb,
    ts timestamp with time zone DEFAULT now(),
    lamport bigint DEFAULT 0,
    applied boolean DEFAULT false,
    applied_ts timestamp with time zone
);


ALTER TABLE public.op_log OWNER TO postgres;

--
-- TOC entry 221 (class 1259 OID 17594)
-- Name: orders; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.orders (
    order_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    quantity integer NOT NULL,
    payload jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.orders OWNER TO postgres;

--
-- TOC entry: replication_cursors; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.replication_cursors (
    node text PRIMARY KEY,
    last_lamport bigint NOT NULL
);


ALTER TABLE public.replication_cursors OWNER TO postgres;

--
-- TOC entry 4826 (class 2606 OID 17634)
-- Name: log_acknowledgements log_acknowledgements_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.log_acknowledgements
    ADD CONSTRAINT log_acknowledgements_pkey PRIMARY KEY (op_id, node);


--
-- TOC entry 4824 (class 2606 OID 17621)
-- Name: op_log op_log_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.op_log
    ADD CONSTRAINT op_log_pkey PRIMARY KEY (op_id);


--
-- TOC entry 4820 (class 2606 OID 17605)
-- Name: orders orders_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_pkey PRIMARY KEY (order_id);


--
-- TOC entry 4821 (class 1259 OID 17623)
-- Name: idx_oplog_lamport; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX IF NOT EXISTS idx_oplog_lamport ON public.op_log USING btree (lamport);


--
-- TOC entry 4822 (class 1259 OID 17622)
-- Name: idx_oplog_origin_ts; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX IF NOT EXISTS idx_oplog_origin_ts ON public.op_log USING btree (origin_node, ts);


--
-- TOC entry 4827 (class 2606 OID 17635)
-- Name: log_acknowledgements log_acknowledgements_op_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.log_acknowledgements
    ADD CONSTRAINT log_acknowledgements_op_id_fkey FOREIGN KEY (op_id) REFERENCES public.op_log(op_id) ON DELETE CASCADE;


-- Completed on 2025-11-30 19:26:00

--
-- PostgreSQL database dump complete
--

\unrestrict BjKMbipXdr0cbiSY7rFpkvBOUZRn6H6f5prN8ZAVCHd3yERDOMqzd1eZSWSRRoT

