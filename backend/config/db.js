const { Pool } = require('pg');

const nodes = {
  Node1: new Pool({
    host: 'ccscloud.dlsu.edu.ph', // Use public domain
    port: 60832,                  // Ensure this maps to the correct internal port
    user: 'postgres',
    password: '',                 // Empty password works because we used 'trust'
    database: 'node0db',
  }),
  Node2: new Pool({
    host: 'ccscloud.dlsu.edu.ph',
    port: 60833,
    user: 'postgres',
    password: '',
    database: 'node1db',
  }),
  Node3: new Pool({
    host: 'ccscloud.dlsu.edu.ph',
    port: 60834,
    user: 'postgres',
    password: '',
    database: 'node2db',
  }),
};
// Test connections
const testConnections = async () => {
  for (const [nodeName, pool] of Object.entries(pools)) {
    try {
      const client = await pool.connect();
      const result = await client.query('SELECT NOW()');
      console.log(`✓ ${nodeName} connected:`, result.rows[0].now);
      client.release();
    } catch (error) {
      console.error(`✗ ${nodeName} connection failed:`, error.message);
    }
  }
};


module.exports.testConnections = testConnections;
module.exports = nodes;