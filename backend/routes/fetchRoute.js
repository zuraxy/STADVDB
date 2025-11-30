const express = require('express');
const router = express.Router();
const nodes = require('../config/db');


router.get('/allOrder', async(req,res)=>{
    try{
        const page = parseInt(req.query.page) || 1;
        const limit = parseInt(req.query.limit) || 10;
        const offset = (page - 1) * limit;

        const client = await nodes["Node1"].connect();
        
        // Get total count
        const countResult = await client.query('SELECT COUNT(*) FROM orders;');
        const total = parseInt(countResult.rows[0].count);
        
        // Get paginated data
        const result = await client.query(
            'SELECT order_id, quantity FROM orders ORDER BY order_id LIMIT $1 OFFSET $2;',
            [limit, offset]
        );
        
        client.release();
        
        res.json({
            success: true,
            data: result.rows,
            pagination: {
                page,
                limit,
                total,
                totalPages: Math.ceil(total / limit)
            }
        });

    }catch(err){
        console.error(err);
        res.status(500).send('Error connecting to database');
    }
});

module.exports = router;