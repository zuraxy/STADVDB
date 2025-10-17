import { pool } from './db.js';
import * as queries from './queries.js';

async function listAllIndexes() {
  console.log('📊 Listing all indexes in the database...');
  
  try {
    const result = await pool.query(`
      SELECT 
        tablename, 
        indexname, 
        indexdef 
      FROM pg_indexes 
      WHERE schemaname = 'public'
      ORDER BY tablename, indexname;
    `);
    
    if (result.rows.length === 0) {
      console.log('No indexes found! All have been dropped.');
    } else {
      console.log(`Found ${result.rows.length} indexes:`);
      result.rows.forEach(row => {
        console.log(`- ${row.tablename}: ${row.indexname}`);
      });
    }
  } catch (error) {
    console.error('Error listing indexes:', error.message);
  }
}

async function configureSessionSettings() {
    console.log('🔧 Manually configuring session settings...');
    
    try {
        // Force configuration on the current connection
        // await pool.query(`
        //     SET work_mem = '64MB';
        //     SET max_parallel_workers_per_gather = 2;
        //     SET enable_hashagg = on;
        //     SET random_page_cost = 1.1;
        //     SET effective_cache_size = '2GB';
        // `);

        await pool.query(`
            RESET work_mem;
            RESET max_parallel_workers_per_gather;
            RESET enable_hashagg;
            RESET random_page_cost;
            RESET effective_cache_size;
        `);

        console.log('✅ Session settings configured manually\n');
    } catch (error) {
        console.log('⚠️  Could not configure session:', error.message);
    }
}

async function refreshDatabaseStats() {
    console.log('🔄 Refreshing database statistics (one time)...');
    
    const start = performance.now();
    
    try {
        await pool.query(`
            ANALYZE fact_orders;
            ANALYZE dim_user;
            ANALYZE dim_product;
            ANALYZE dim_date;
            ANALYZE dim_rider;
        `);
        
        const end = performance.now();
        console.log(`✅ Statistics updated in ${(end - start).toFixed(2)}ms\n`);
    } catch (error) {
        console.error('⚠️  Warning: Could not update statistics:', error.message);
    }
}

async function verifyOptimalSettings() {
    console.log('🔧 Verifying optimal database settings...');
    
    try {
        const settingsToCheck = [
            'work_mem',
            'max_parallel_workers_per_gather',
            'enable_hashagg',
            'random_page_cost',
            'effective_cache_size'
        ];
        
        for (const setting of settingsToCheck) {
            const result = await pool.query(`SHOW ${setting}`);
            const value = result.rows[0][setting];
            console.log(`  ⚙️  ${setting}: ${value}`);
        }
        
        // Check if we have optimal values
        const workMemResult = await pool.query(`SHOW work_mem`);
        const workMem = workMemResult.rows[0].work_mem;
        
        if (workMem.includes('128MB') || workMem.includes('64MB')) {
            console.log('  ✅ Optimal settings detected!\n');
        } else {
            console.log('  ⚠️  Default settings detected - optimization may not be active\n');
        }
        
    } catch (error) {
        console.error('  ❌ Could not verify settings:', error.message);
    }
}

async function analyzeQueryPlan(queryName, query, params = []) {
    console.log(`\n🔍 Analyzing execution plan for ${queryName}...`);
    
    try {
        // Get the execution plan
        const explainQuery = `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ${query}`;
        const result = params.length > 0 
            ? await pool.query(explainQuery, params)
            : await pool.query(explainQuery);
        
        const plan = result.rows[0]['QUERY PLAN'][0];
        
        console.log(`  ⏱️  Execution Time: ${plan['Execution Time']?.toFixed(2)}ms`);
        console.log(`  📊 Planning Time: ${plan['Planning Time']?.toFixed(2)}ms`);
        
        // Check for index usage
        const planText = JSON.stringify(plan, null, 2);
        const indexScans = (planText.match(/Index.*Scan/g) || []).length;
        const seqScans = (planText.match(/Seq Scan/g) || []).length;
        
        console.log(`  🚀 Index Scans: ${indexScans}`);
        console.log(`  🐌 Sequential Scans: ${seqScans}`);
        
        if (indexScans > 0) {
            console.log(`  ✅ Using indexes efficiently!`);
        } else {
            console.log(`  ⚠️  No indexes detected - might need optimization`);
        }
        
        // Show buffer usage
        if (plan.Buffers) {
            console.log(`  💾 Shared Buffers Hit: ${plan.Buffers['Shared Hit Blocks'] || 0}`);
            console.log(`  💿 Shared Buffers Read: ${plan.Buffers['Shared Read Blocks'] || 0}`);
        }
        
    } catch (error) {
        console.error(`  ❌ Could not analyze plan:`, error.message);
    }
}

async function testQueryPerformance(queryName, query, params = []) {
    console.log(`\n🧪 Testing ${queryName}...`);
    
    // First, analyze the execution plan
    await analyzeQueryPlan(queryName, query, params);
    
    const iterations = 3;
    const times = [];
    
    for (let i = 0; i < iterations; i++) {
        const start = performance.now();
        
        try {
            // All queries are now simple - no SET/RESET handling needed!
            const result = params.length > 0 
                ? await pool.query(query, params)
                : await pool.query(query);
            
            const end = performance.now();
            const executionTime = end - start;
            
            if (result && result.rows) {
                times.push(executionTime);
                console.log(`  Run ${i + 1}: ${executionTime.toFixed(2)}ms (${result.rows.length} rows)`);
            } else {
                console.log(`  Run ${i + 1}: ${executionTime.toFixed(2)}ms (no result)`);
            }
            
        } catch (error) {
            console.error(`  ❌ Error in run ${i + 1}:`, error.message);
        }
    }
    
    if (times.length > 0) {
        const avgTime = times.reduce((a, b) => a + b, 0) / times.length;
        const minTime = Math.min(...times);
        const maxTime = Math.max(...times);
        
        console.log(`  📊 Average: ${avgTime.toFixed(2)}ms | Min: ${minTime.toFixed(2)}ms | Max: ${maxTime.toFixed(2)}ms`);
    }
}

async function runPerformanceTests() {
    console.log('🚀 Starting Query Performance Tests\n');
    
    try {
        console.log('Testing database connection...');
        await pool.query('SELECT 1');
        console.log('✅ Database connected\n');

        await listAllIndexes();
        
        // First, manually configure settings (since onConnect isn't working)
        await configureSessionSettings();
        
        // Then verify settings were applied correctly
        await verifyOptimalSettings();
        
        // Run ANALYZE once before all tests
        await refreshDatabaseStats();
        
        // Test ALL queries with FULL datasets
        await testQueryPerformance('QUERY1 - Revenue Rollup', queries.QUERY1, [20200101, 20241231, null, 'day']);
        await testQueryPerformance('QUERY2 - Customer Distribution', queries.QUERY2);
        await testQueryPerformance('QUERY3 - Top Products', queries.QUERY3, [100, null, null, null]);
        await testQueryPerformance('QUERY4 - Moving Average', queries.QUERY4, [null]);
        await testQueryPerformance('QUERY5 - Rider Rankings', queries.QUERY5, [null]);
        await testQueryPerformance('QUERY6 - Vehicle Deliveries', queries.QUERY6, [null, null]);
        
        // QUERY7 - Top Percentile Riders (NOW FIXED!)
        // Parameters: [country, city, category, percentile_threshold, year, quarter]
        await testQueryPerformance('QUERY7 - Top Percentile Riders', queries.QUERY7, [null, null, null, 50, 2024, 4]);
        
        await testQueryPerformance('QUERY8 - Revenue ROLLUP', queries.QUERY8, [2025, null, null, null]);
        await testQueryPerformance('QUERY9 - Enhanced Revenue ROLLUP', queries.QUERY9, [2025, null, null, null]);
        
    } catch (error) {
        console.error('❌ Test suite failed:', error);
    } finally {
        console.log('\n🏁 Tests completed. Closing connection...');
        try {
            await pool.end();
            console.log('✅ Connection closed successfully');
        } catch (closeError) {
            console.error('❌ Error closing connection:', closeError.message);
        }
    }
}

// Actually run the tests
runPerformanceTests().catch((error) => {
    console.error('❌ Fatal error:', error);
    process.exit(1);
});