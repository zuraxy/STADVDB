const { Pool } = require('pg');
require('dotenv').config();

const nodes = {
  Node1: new Pool({
    host: process.env.NODE1_HOST ,
    port: process.env.NODE1_PORT ,
    user: process.env.NODE1_USER ,
    password: process.env.NODE1_PASSWORD ,
    database: process.env.NODE1_DB ,
  }),
  Node2: new Pool({
    host: process.env.NODE2_HOST ,
    port: process.env.NODE2_PORT,
    user: process.env.NODE2_USER,
    password: process.env.NODE2_PASSWORD,
    database: process.env.NODE2_DB,
  }),
  Node3: new Pool({
    host: process.env.NODE3_HOST,
    port: process.env.NODE3_PORT,
    user: process.env.NODE3_USER,
    password: process.env.NODE3_PASSWORD,
    database: process.env.NODE3_DB ,
  }),
};

// Test connections
const testConnections = async () => {
  for (const [nodeName, pool] of Object.entries(nodes)) {
    try {
      const client = await pool.connect();
      const result = await client.query('SELECT NOW()');
      console.log(` ${nodeName} connected:`, result.rows[0].now);
      client.release();
    } catch (error) {
      console.error(` ${nodeName} connection failed:`, error.message);
    }
  }
};

// Export both nodes and testConnections
module.exports = nodes;
module.exports.testConnections = testConnections;