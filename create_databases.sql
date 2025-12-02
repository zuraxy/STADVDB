-- Create databases for the distributed system
-- Run with: psql -U postgres -f create_databases.sql

-- Create databases
CREATE DATABASE node0db;
CREATE DATABASE node1db;
CREATE DATABASE node2db;

-- List all databases
\l
