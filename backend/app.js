const express = require('express')
const cors = require('cors')
const testRoutes = require('./routes/testRoute')
const fetchRoutes = require('./routes/fetchRoute')

const app = express()

// Enable CORS for all routes
app.use(cors())

app.use(express.json())

// Request logging middleware
app.use((req, res, next) => {
  const startTime = Date.now();
  
  // Capture the original res.json to log responses
  const originalJson = res.json.bind(res);
  res.json = function(data) {
    const duration = Date.now() - startTime;
    const timestamp = new Date().toLocaleTimeString();
    const status = res.statusCode;
    const statusColor = status >= 200 && status < 300 ? '✓' : '✗';
    
    console.log(`${statusColor} [${timestamp}] ${req.method} ${req.url} → ${status} (${duration}ms)`);
    
    return originalJson(data);
  };

  next();
});

app.use('/api', testRoutes);
app.use('/api/fetch',fetchRoutes);

module.exports = app;