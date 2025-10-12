
const express = require('express');
const app = express();
const {pool} = require('./db'); 
const queries = require('./queries')
app.use(express.json());

app.get('/query1', async (req, res) => {
  const params = ['2024-01-01', '2024-12-31', null, 'month'];
  try {
    const result = await pool.query(queries.QUERY1,params);
    res.json(result.rows);
  } catch (err) {

    res.status(500).json({ error: err && (err.message || String(err)) || 'Internal error' });
  }
});

module.exports = app;
