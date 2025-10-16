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
  // allow forcing SSL via env var for cloud DBs (e.g. SUPABASE)
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
  
  // Add more logging
  async onConnect(client) {
    console.log('[db] 🔧 onConnect triggered!!!'); // This should show if it runs
    try {
      const testResult = await client.query('SHOW is_superuser');
      console.log('[db] User privileges:', testResult.rows[0].is_superuser);
      
      await client.query(`
        SET work_mem = '128MB';
        SET enable_hashagg = on;
        SET random_page_cost = 1.1;
      `);
      console.log('[db] ✅ Connection configured with available optimizations');
    } catch (error) {
      console.log('[db] ❌ Using default settings (pooler limitations):', error.message);
    }
  }
});

// Add this to see pool events
pool.on('connect', () => {
  console.log('[db] 🔌 Pool connect event fired');
});

console.log('[db] 📦 Pool created successfully');

// CHANGE THIS LINE - Use CommonJS export instead of ES module export
module.exports = { pool };