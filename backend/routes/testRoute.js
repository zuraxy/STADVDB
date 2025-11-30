const express = require('express');
const router = express.Router();
const nodes = require('../config/db');

router.get('/test/:node', async (req, res) => {
  const nodeName = req.params.node;

  if (!nodes[nodeName]) {
    return res.status(400).send(`Node ${nodeName} not found`);
  }

  try {
    const client = await nodes[nodeName].connect();
    const result = await client.query('SELECT * FROM orders;');
    client.release();
    res.send({
      node: nodeName,
      data: result.rows
    });
  } catch (err) {
    console.error(err);
    res.status(500).send('Error connecting to database');
  }
});

router.get('/test-connections', async (req, res) => {
  const results = {};
  
  try {
    // Changed 'pools' to 'nodes'
    for (const [nodeName, pool] of Object.entries(nodes)) {
      try {
        const client = await pool.connect();
        const result = await client.query('SELECT NOW()');
        results[nodeName] = {
          status: 'connected',
          timestamp: result.rows[0].now
        };
        client.release();
      } catch (error) {
        results[nodeName] = {
          status: 'failed',
          error: error.message
        };
      }
    }
    
    res.json({
      success: true,
      connections: results
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

module.exports = router;