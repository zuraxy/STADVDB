const express = require('express');
const router = express.Router();
const nodes = require('../db');

router.get('/test/:node', async (req, res) => {
  const nodeName = req.params.node;

  if (!nodes[nodeName]) {
    return res.status(400).send(`Node ${nodeName} not found`);
  }

  try {
    const client = await nodes[nodeName].connect();
    const result = await client.query('SELECT * FROM users;');
    client.release();
    res.send({
      node: nodeName,
      data:result.rows
    });
  } catch (err) {
    console.error(err);
    res.status(500).send('Error connecting to database');
  }
});

module.exports = router;
