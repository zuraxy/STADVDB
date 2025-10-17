const pkg = require('pg');
const dotenv = require('dotenv');
const { URL } = require('url');

dotenv.config({ path: '../.env' });

const { Pool } = pkg;

const connectionString = (process.env.SUPABASE_POOL_STRING || process.env.SUPABASE_CONNECTION_STRING || '').trim();

let sslOption = false;
try {
  const parsed = new URL(connectionString);
  console.log('[db] connecting to:', parsed.hostname);
  const isLocal = ['localhost', '127.0.0.1', '::1'].includes(parsed.hostname);
  if (process.env.DB_FORCE_SSL === 'true') {
    sslOption = { rejectUnauthorized: false };
  } else {
    sslOption = isLocal ? false : { rejectUnauthorized: false };
  }
} catch (err) {
  console.warn('[db] SUPABASE_POOL_STRING/DATABASE_URL missing or invalid');
}

const pool = new Pool({
  connectionString,
  ssl: sslOption,
  max: 10,
  idleTimeoutMillis: 30000,
});

pool.on('connect', () => {
  console.log('[db] 🔌 Pool connect event fired');
});

// ACTUAL check for work_mem after pool creation
(async () => {
  try {
    const client = await pool.connect();
    // Set work_mem and check value
    await client.query(`SET work_mem = '128MB';`);
    const result = await client.query('SHOW work_mem;');
    console.log('[db] ✅ work_mem:', result.rows[0].work_mem);
    client.release();
  } catch (error) {
    console.log('[db] ❌ Could not check work_mem:', error.message);
  }
})();

console.log('[db] 📦 Pool created successfully');

module.exports = { pool };