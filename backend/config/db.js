const { Pool } = require('pg');

const nodes = {
  Node1: new Pool({
    host: 'ccscloud.dlsu.edu.ph', // Use public domain
    port: 60832,                  // Ensure this maps to the correct internal port
    user: 'postgres',
    password: '',                 // Empty password works because we used 'trust'
    database: 'testdb',
  }),
  Node2: new Pool({
    host: 'ccscloud.dlsu.edu.ph',
    port: 60833,
    user: 'postgres',
    password: '',
    database: 'testdb2',
  }),
  Node3: new Pool({
    host: 'ccscloud.dlsu.edu.ph',
    port: 60834,
    user: 'postgres',
    password: '',
    database: 'testdb3',
  }),
};

module.exports = nodes;