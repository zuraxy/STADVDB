const express = require('express');
const cors = require('cors'); 
const {pool} = require('./db'); 
const queries = require('./queries');

const app = express();

app.use(cors());
app.use(express.json());

app.get('/query1', async (req, res) => {
  const startStr = req.query.start || '2024-01-01';
  const endStr = req.query.end || '2024-12-31';
  const category = req.query.category || null;
  const granularity = req.query.granularity || 'month';
  
  const startDateId = parseInt(startStr.replace(/-/g, ''));
  const endDateId = parseInt(endStr.replace(/-/g, ''));
  
  const params = [startDateId, endDateId, category, granularity];

  const startTime = process.hrtime.bigint();
  try {
    console.log('Running query1 with params:', params);
    const result = await pool.query(queries.QUERY1, params);
    const endTime = process.hrtime.bigint();
    const durationMs = Number(endTime - startTime) / 1e6;
    console.log('Query1 result rows:', result.rows.length, `took ${durationMs.toFixed(2)} ms`);
    res.json({ durationMs: durationMs.toFixed(2), rows: result.rows });
  } catch (err) {
    console.error('Query1 error:', err);
    res.status(500).json({ error: err && (err.message || String(err)) || 'Internal error' });
  }
});

app.get('/query2', async (req, res) => {
  const startTime = process.hrtime.bigint();
  try {
    const result = await pool.query(queries.QUERY2);
    const endTime = process.hrtime.bigint();
    const durationMs = Number(endTime - startTime) / 1e6;
    console.log('Query2 result rows:', result.rows.length, `took ${durationMs.toFixed(2)} ms`);
    res.json({ durationMs: durationMs.toFixed(2), rows: result.rows });
  } catch (err) {
    console.error('Query2 error:', err);
    res.status(500).json({ error: err && (err.message || String(err)) || 'Internal error' });
  }
});

app.get('/query3', async (req, res) => {
  const N = req.query.no || 10;
  const country = req.query.country || null;
  const city = req.query.city || null;
  const category = req.query.category || null;

  const params = [N, country, city, category];

  const startTime = process.hrtime.bigint();
  try {
    console.log('Running query3 with params:', params);
    const results = await pool.query(queries.QUERY3, params);
    const endTime = process.hrtime.bigint();
    const durationMs = Number(endTime - startTime) / 1e6;
    console.log('Query3 result rows:', results.rows.length, `took ${durationMs.toFixed(2)} ms`);
    res.json({ durationMs: durationMs.toFixed(2), rows: results.rows });
  } catch (err) {
    console.error('Query3 error:', err);
    res.status(500).json({ error: err && (err.message || String(err)) || 'Internal error' });
  }
});

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
    console.error('Query5 error:', err);
    res.status(500).json({ error: err.message || String(err) });
  }
});

app.get('/query6', async (req, res) => {
  const year = req.query.year ? parseInt(req.query.year) : null;
  const month = req.query.month ? parseInt(req.query.month) : null;
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


// Query 7: Top Percentile Riders
app.get('/query7', async (req, res) => {
  const country = req.query.country || "Philippines";
  const percentile_threshold = req.query.percentile || 10;
  const year = req.query.year ? parseInt(req.query.year) : 2025;
  const quarter = req.query.quarter ? parseInt(req.query.quarter) : 1;
  let prevYear = year;
  let prevQuarter = quarter - 1;

  if (quarter === 1) {
    prevQuarter = 4;
    prevYear = year - 1;
  }

  const params = [year,quarter,prevYear,prevQuarter,country,percentile_threshold];

  const startTime = process.hrtime.bigint();
  try {
    console.log('Running query7 with params:', params);
    const results = await pool.query(queries.QUERY7, params);
    const endTime = process.hrtime.bigint();
    const durationMs = Number(endTime - startTime) / 1e6;
    console.log('Query7 result rows:', results.rows.length, `took ${durationMs.toFixed(2)} ms`);
    res.json({ durationMs: durationMs.toFixed(2), rows: results.rows });
  } catch (err) {
    console.error('Query7 error:', err);
    res.status(500).json({ error: err.message || String(err) });
  }
});

app.get('/query8', async (req, res) => {

  const year = req.query.year || 2025;                
  const country = req.query.country || null;         
  const city = req.query.city || null;                
  const category = req.query.category || null;      

  const params = [year, country, city, category];

  const startTime = process.hrtime.bigint();
  try {
    console.log('Running QUERY8 with params:', params);
    const results = await pool.query(queries.QUERY8, params);
    const endTime = process.hrtime.bigint();
    const durationMs = Number(endTime - startTime) / 1e6;

    console.log(
      `Query8 result rows: ${results.rows.length} (took ${durationMs.toFixed(2)} ms)`
    );

    res.json({
      durationMs: durationMs.toFixed(2),
      rows: results.rows,
    });
  } catch (err) {
    console.error('Query8 error:', err);
    res.status(500).json({ error: err.message || String(err) });
  }
});

// Query 9: Enhanced Revenue ROLLUP
app.get('/query9', async (req, res) => {
  const year = req.query.year ? parseInt(req.query.year) : 2025;                
  const country = req.query.country || null;         
  const city = req.query.city || null;                
  const category = req.query.category || null;      

  const params = [year, country, city, category];

  const startTime = process.hrtime.bigint();
  try {
    console.log('Running query9 with params:', params);
    const results = await pool.query(queries.QUERY9, params);
    const endTime = process.hrtime.bigint();
    const durationMs = Number(endTime - startTime) / 1e6;
    console.log('Query9 result rows:', results.rows.length, `took ${durationMs.toFixed(2)} ms`);
    res.json({ durationMs: durationMs.toFixed(2), rows: results.rows });
  } catch (err) {
    console.error('Query9 error:', err);
    res.status(500).json({ error: err.message || String(err) });
  }
});

module.exports = app;