import pkg from 'pg';
import dotenv from 'dotenv';

dotenv.config({ path: '../.env' });

const { Pool } = pkg;

const connectionString = (process.env.SUPABASE_POOL_STRING || process.env.DATABASE_URL || '').trim();

try {
  const u = new URL(connectionString);
  console.log('[db] connecting to:', u.hostname);
} catch (e) {
  console.warn('[db] SUPABASE_CONNECTION_STRING/DATABASE_URL missing or invalid');
}

export const pool = new Pool({
  connectionString,
  ssl: { rejectUnauthorized: false },
  max: 10,
  idleTimeoutMillis: 30000,
});