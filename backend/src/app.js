
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

  const startTime = process.hrtime.bigint();
  try {
    console.log('Running query1 with params:', params);
    const result = await pool.query(queries.QUERY1,params);
    const endTime = process.hrtime.bigint();
    const durationMs = Number(endTime - startTime) / 1e6;
    console.log('Query1 result rows:', result.rows.length, `took ${durationMs.toFixed(2)} ms`);
    res.json({ durationMs: durationMs.toFixed(2), rows: result.rows });
  } catch (err) {
    res.status(500).json({ error: err && (err.message || String(err)) || 'Internal error' });
  }
});

app.get('/query2',async (req,res)=>{

  const startTime = process.hrtime.bigint();
  try{
    const result = await pool.query(queries.QUERY2);
    const endTime = process.hrtime.bigint();
    const durationMs = Number(endTime - startTime) / 1e6;
    console.log('Query2 result rows:', result.rows.length, `took ${durationMs.toFixed(2)} ms`);
    res.json({ durationMs: durationMs.toFixed(2), rows: result.rows });
  } catch(err){
    res.status(500).json({ error: err && (err.message || String(err)) || 'Internal error' });
  }
})

app.get('/query3',async(req,res)=>{
  const N  = req.query.no || 100
  const country =req.query.country || null
  const city = req.query.city || null
  const category = req.query.category || null

  const params = [N,country,city,category]

  const startTime = process.hrtime.bigint();
  try{
    console.log('Running query3 with params:', params);
    const results = await pool.query(queries.QUERY3,params)
    const endTime = process.hrtime.bigint();
    const durationMs = Number(endTime - startTime) / 1e6;
    console.log('Query3 result rows:', results.rows.length, `took ${durationMs.toFixed(2)} ms`);
    res.json({ durationMs: durationMs.toFixed(2), rows: results.rows });
  }catch(err){
    res.status(500).json({ error: err && (err.message || String(err)) || 'Internal error' });
  }

})


app.get('/query4', async (req, res) => {
  const country = req.query.country || null;
  const params = [country];
  
  const startTime = process.hrtime.bigint();
  try {
    console.log('Running query4 with params:', params);
    const results = await pool.query(queries.QUERY4, params);
    const endTime = process.hrtime.bigint();
    const durationMs = Number(endTime - startTime) / 1e6;
    console.log('Query4 result rows:', results.rows.length, `took ${durationMs.toFixed(2)} ms`);
    res.json({ durationMs: durationMs.toFixed(2), rows: results.rows });
  } catch (err) {
    console.error('Query4 error:', err);
    res.status(500).json({ error: err.message || String(err) });
  }
});

app.get('/query5', async (req, res) => {
  const country = req.query.country || null;
  const params = [country];
  
  const startTime = process.hrtime.bigint();
  try {
    console.log('Running query5 with params:', params);
    const results = await pool.query(queries.QUERY5, params);
    const endTime = process.hrtime.bigint();
    const durationMs = Number(endTime - startTime) / 1e6;
    console.log('Query5 result rows:', results.rows.length, `took ${durationMs.toFixed(2)} ms`);
    res.json({ durationMs: durationMs.toFixed(2), rows: results.rows });
  } catch (err) {
    console.error('Query4 error:', err);
    res.status(500).json({ error: err.message || String(err) });
  }
});

app.get('/query5', async (req, res) => {
  const country = req.query.country || null;
  const params = [country];
  
  const startTime = process.hrtime.bigint();
  try {
    console.log('Running query5 with params:', params);
    const results = await pool.query(queries.QUERY5, params);
    const endTime = process.hrtime.bigint();
    const durationMs = Number(endTime - startTime) / 1e6;
    console.log('Query5 result rows:', results.rows.length, `took ${durationMs.toFixed(2)} ms`);
    res.json({ durationMs: durationMs.toFixed(2), rows: results.rows });
  } catch (err) {
    console.error('Query4 error:', err);
    res.status(500).json({ error: err.message || String(err) });
  }
});

app.get('/query6', async (req, res) => {
  const year = req.query.year || null;
  const month = req.query.month || null;
  const params = [year, month];

  const startTime = process.hrtime.bigint();
  try {
    console.log('Running query6 with params:', params);
    const results = await pool.query(queries.QUERY6, params);
    const endTime = process.hrtime.bigint();
    const durationMs = Number(endTime - startTime) / 1e6;
    console.log('Query6 result rows:', results.rows.length, `took ${durationMs.toFixed(2)} ms`);
    res.json({ durationMs: durationMs.toFixed(2), rows: results.rows });
  } catch (err) {
    console.error('Query6 error:', err);
    res.status(500).json({ error: err.message || String(err) });
  }
});


app.get('/query7', async (req, res) => {
  const start = req.query.start || '2024-01-01';
  const end = req.query.end || '2024-12-31';
  const top_percent = req.query.top || 20;
  const granularity = req.query.granularity || 'month';
  const params = [start, end, top_percent, granularity];

  const startTime = process.hrtime.bigint();
  try {
    console.log('Running query8 with params:', params);
    const results = await pool.query(queries.QUERY8, params);
    const endTime = process.hrtime.bigint();
    const durationMs = Number(endTime - startTime) / 1e6;
    console.log('Query8 result rows:', results.rows.length, `took ${durationMs.toFixed(2)} ms`);
    res.json({ durationMs: durationMs.toFixed(2), rows: results.rows });
  } catch (err) {
    console.error('Query8 error:', err);
    res.status(500).json({ error: err.message || String(err) });
  }
});
module.exports = app;
