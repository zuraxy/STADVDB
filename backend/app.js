const express = require('express')
const testRoutes = require('./routes/testRoute')


const app = express()
app.use(express.json())
app.use('/api', testRoutes);


module.exports = app;