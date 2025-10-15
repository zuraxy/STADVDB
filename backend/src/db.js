// ...existing code...
import pkg from 'pg';
import dotenv from 'dotenv';
import { URL } from 'url';

dotenv.config({ path: '../.env' });

const { Pool } = pkg;

const connectionString = (process.env.SUPABASE_POOL_STRING || process.env.SUPABASE_CONNECTION_STRING || '').trim();

let sslOption = false;
try {
  const parsed = new URL(connectionString);
  console.log('[db] connecting to:', parsed.hostname);
  const isLocal = ['localhost', '127.0.0.1', '::1'].includes(parsed.hostname);
  // allow forcing SSL via env var for cloud DBs (e.g. SUPABASE)
  if (process.env.DB_FORCE_SSL === 'true') {
    sslOption = { rejectUnauthorized: false };
  } else {
    sslOption = isLocal ? false : { rejectUnauthorized: false };
  }
} catch (err) {
  console.warn('[db] SUPABASE_POOL_STRING/DATABASE_URL missing or invalid');
}

export const pool = new Pool({
  connectionString,
  ssl: sslOption,
  max: 10,
  idleTimeoutMillis: 30000,
});
// ...existing code...