
const express = require('express');
const app = express();
const {pool} = require('./db'); 
const queries = require('./queries')
app.use(express.json());

app.get('/query1', async (req, res) => {


  const start = req.query.start || '2024-01-01';
  const end = req.query.end || '2024-12-31';
  const category = req.query.category || null;
  const granularity = req.query.granularity || 'month';
  const params = [start, end, category, granularity];

  try {
    const result = await pool.query(queries.QUERY1,params);
    res.json(result.rows);
  } catch (err) {

    res.status(500).json({ error: err && (err.message || String(err)) || 'Internal error' });
  }
});

app.get('/query2',async (req,res)=>{

  try{
    const result = await pool.query(queries.QUERY2);
    res.json(result.rows);
  } catch(err){
    res.status(500).json({ error: err && (err.message || String(err)) || 'Internal error' });
  }
})
module.exports = app;
