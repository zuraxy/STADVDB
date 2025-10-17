import { pool } from './db.js';

async function testConnection() {
    try {
        console.log('Testing database connection...');
        const result = await pool.query('SELECT 1 as test');
        console.log('✅ Database connected successfully');
        console.log('Test result:', result.rows[0]);
        await pool.end();
    } catch (error) {
        console.error('❌ Database connection failed:', error.message);
    }
}

testConnection();