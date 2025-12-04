import { test, expect } from '@playwright/test';

/**
 * Concurrency Control Tests - Isolation Level Anomalies
 * 
 * This test suite validates non-repeatable read and phantom read scenarios
 * across different isolation levels using the transaction orchestrator API.
 */

const API_BASE = 'http://ccscloud.dlsu.edu.ph:60232/api';

test.describe('Isolation Level Anomaly Tests', () => {
  
  test('non-repeatable read - READ COMMITTED isolation', async ({ request }) => {
    console.log('🔍 Testing NON-REPEATABLE READ with READ COMMITTED isolation...');
    
    // Start orchestration run
    const response = await request.post(`${API_BASE}/orchestrator/run`, {
      data: {
        scenario: 'NON_REPEATABLE_READ',
        isolation_level: 'READ_COMMITTED',
        node_x: 'node0',
        node_y: 'node1',
        new_value_1: 4,  // Writer will update to this value (must be 1-5 due to qty_1to5 constraint)
      }
    });
    
    expect(response.ok()).toBeTruthy();
    const runData = await response.json();
    console.log('Run started:', runData.run_id);
    
    // Wait for completion
    await new Promise(resolve => setTimeout(resolve, 5000));
    
    // Check status
    const statusResponse = await request.get(`${API_BASE}/orchestrator/status/${runData.run_id}`);
    expect(statusResponse.ok()).toBeTruthy();
    const status = await statusResponse.json();
    
    console.log('Run status:', status.status);
    console.log('Verdict:', status.result_summary?.verdict);
    
    // Get logs
    const logsResponse = await request.get(`${API_BASE}/orchestrator/logs/${runData.run_id}`);
    const logs = await logsResponse.json();
    
    console.log('📊 Execution Times:');
    for (const [actor, times] of Object.entries(status.result_summary?.execution_times || {})) {
      console.log(`  ${actor}:`);
      console.log(`    Total: ${times.total_seconds?.toFixed(3)}s`);
      console.log(`    Transaction: ${times.transaction_seconds?.toFixed(3)}s`);
      console.log(`    Net (no delays): ${times.net_execution_seconds?.toFixed(3)}s`);
    }
    
    // Verify non-repeatable read was detected with READ COMMITTED
    expect(status.result_summary?.verdict).toContain('Non-repeatable read');
  });

  test('non-repeatable read - REPEATABLE READ isolation', async ({ request }) => {
    console.log('🔍 Testing NON-REPEATABLE READ with REPEATABLE READ isolation...');
    
    const response = await request.post(`${API_BASE}/orchestrator/run`, {
      data: {
        scenario: 'NON_REPEATABLE_READ',
        isolation_level: 'REPEATABLE_READ',
        node_x: 'node0',
        node_y: 'node1',
        new_value_1: 3,  // Must be 1-5 due to qty_1to5 constraint
      }
    });
    
    expect(response.ok()).toBeTruthy();
    const runData = await response.json();
    console.log('Run started:', runData.run_id);
    
    await new Promise(resolve => setTimeout(resolve, 5000));
    
    const statusResponse = await request.get(`${API_BASE}/orchestrator/status/${runData.run_id}`);
    const status = await statusResponse.json();
    
    console.log('Run status:', status.status);
    console.log('Verdict:', status.result_summary?.verdict);
    
    console.log('📊 Execution Times:');
    for (const [actor, times] of Object.entries(status.result_summary?.execution_times || {})) {
      console.log(`  ${actor}:`);
      console.log(`    Total: ${times.total_seconds?.toFixed(3)}s`);
      console.log(`    Transaction: ${times.transaction_seconds?.toFixed(3)}s`);
      console.log(`    Net (no delays): ${times.net_execution_seconds?.toFixed(3)}s`);
    }
    
    // Verify non-repeatable read was prevented with REPEATABLE READ
    expect(status.result_summary?.verdict).toContain('No non-repeatable read');
  });

  test('phantom read - READ COMMITTED isolation', async ({ request }) => {
    console.log('👻 Testing PHANTOM READ with READ COMMITTED isolation...');
    
    const response = await request.post(`${API_BASE}/orchestrator/run`, {
      data: {
        scenario: 'PHANTOM_READ',
        isolation_level: 'READ_COMMITTED',
        node_x: 'node0',
        node_y: 'node1',
        new_value_1: 7,  // Insert a row with quantity=7
      }
    });
    
    expect(response.ok()).toBeTruthy();
    const runData = await response.json();
    console.log('Run started:', runData.run_id);
    
    await new Promise(resolve => setTimeout(resolve, 5000));
    
    const statusResponse = await request.get(`${API_BASE}/orchestrator/status/${runData.run_id}`);
    const status = await statusResponse.json();
    
    console.log('Run status:', status.status);
    console.log('Verdict:', status.result_summary?.verdict);
    
    console.log('📊 Execution Times:');
    for (const [actor, times] of Object.entries(status.result_summary?.execution_times || {})) {
      console.log(`  ${actor}:`);
      console.log(`    Total: ${times.total_seconds?.toFixed(3)}s`);
      console.log(`    Transaction: ${times.transaction_seconds?.toFixed(3)}s`);
      console.log(`    Net (no delays): ${times.net_execution_seconds?.toFixed(3)}s`);
    }
    
    // Get actor results to check phantom detection
    const readerResult = Object.values(status.result_summary?.actor_results || {}).find(
      r => r.role === 'read_range'
    );
    
    console.log('📈 Range scan results:');
    console.log(`  Initial count: ${readerResult?.details?.initial_count}`);
    console.log(`  Final count: ${readerResult?.details?.final_count}`);
    console.log(`  Phantom detected: ${readerResult?.details?.phantom_detected}`);
    
    // Verify phantom read was detected with READ COMMITTED
    expect(status.result_summary?.verdict).toContain('Phantom read');
  });

  test('phantom read - SERIALIZABLE isolation', async ({ request }) => {
    console.log('👻 Testing PHANTOM READ with SERIALIZABLE isolation...');
    
    const response = await request.post(`${API_BASE}/orchestrator/run`, {
      data: {
        scenario: 'PHANTOM_READ',
        isolation_level: 'SERIALIZABLE',
        node_x: 'node0',
        node_y: 'node1',
        new_value_1: 6,
      }
    });
    
    expect(response.ok()).toBeTruthy();
    const runData = await response.json();
    console.log('Run started:', runData.run_id);
    
    await new Promise(resolve => setTimeout(resolve, 5000));
    
    const statusResponse = await request.get(`${API_BASE}/orchestrator/status/${runData.run_id}`);
    const status = await statusResponse.json();
    
    console.log('Run status:', status.status);
    console.log('Verdict:', status.result_summary?.verdict);
    
    console.log('📊 Execution Times:');
    for (const [actor, times] of Object.entries(status.result_summary?.execution_times || {})) {
      console.log(`  ${actor}:`);
      console.log(`    Total: ${times.total_seconds?.toFixed(3)}s`);
      console.log(`    Transaction: ${times.transaction_seconds?.toFixed(3)}s`);
      console.log(`    Net (no delays): ${times.net_execution_seconds?.toFixed(3)}s`);
    }
    
    const readerResult = Object.values(status.result_summary?.actor_results || {}).find(
      r => r.role === 'read_range'
    );
    
    console.log('📈 Range scan results:');
    console.log(`  Initial count: ${readerResult?.details?.initial_count}`);
    console.log(`  Final count: ${readerResult?.details?.final_count}`);
    console.log(`  Phantom detected: ${readerResult?.details?.phantom_detected}`);
    
    // Verify phantom read was prevented with SERIALIZABLE
    // Note: In Postgres SERIALIZABLE, one transaction might abort with serialization error
    if (status.result_summary?.serialization_conflicts?.length > 0) {
      console.log('⚠️ Serialization conflict occurred (expected for SERIALIZABLE)');
      expect(status.result_summary.serialization_conflicts.length).toBeGreaterThan(0);
    } else {
      expect(status.result_summary?.verdict).toContain('No phantom read');
    }
  });

  test('execution time measurement validation', async ({ request }) => {
    console.log('⏱️ Testing execution time measurement...');
    
    // Run a simple READ_WRITE scenario with known delay
    const response = await request.post(`${API_BASE}/orchestrator/run`, {
      data: {
        scenario: 'READ_WRITE',
        isolation_level: 'READ_COMMITTED',
        node_x: 'node0',
        node_y: 'node1',
        new_value_1: 42,
      }
    });
    
    expect(response.ok()).toBeTruthy();
    const runData = await response.json();
    
    await new Promise(resolve => setTimeout(resolve, 5000));
    
    const statusResponse = await request.get(`${API_BASE}/orchestrator/status/${runData.run_id}`);
    const status = await statusResponse.json();
    
    console.log('📊 Detailed Execution Time Breakdown:');
    for (const [actor, times] of Object.entries(status.result_summary?.execution_times || {})) {
      console.log(`\n${actor}:`);
      console.log(`  ├─ Total time: ${times.total_seconds?.toFixed(3)}s`);
      console.log(`  ├─ Transaction time: ${times.transaction_seconds?.toFixed(3)}s`);
      console.log(`  ├─ Delay time: ${times.delay_seconds?.toFixed(3)}s`);
      console.log(`  └─ Net execution: ${times.net_execution_seconds?.toFixed(3)}s`);
      
      // Verify that net execution time is reasonable (transaction time minus delays)
      expect(times.net_execution_seconds).toBeGreaterThanOrEqual(0);
      expect(times.total_seconds).toBeGreaterThanOrEqual(times.transaction_seconds || 0);
    }
    
    // Verify execution time structure exists for all actors
    const actorCount = Object.keys(status.result_summary?.actor_results || {}).length;
    const timeCount = Object.keys(status.result_summary?.execution_times || {}).length;
    expect(timeCount).toBe(actorCount);
  });

});
