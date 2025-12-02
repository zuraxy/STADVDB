import { test, expect } from '@playwright/test';

test.describe('Concurrency Tests', () => {
  
  test('concurrent order updates - 2 users editing same order', async ({ browser }) => {
    // Create 2 independent browser contexts (simulating 2 different users)
    const context1 = await browser.newContext();
    const context2 = await browser.newContext();
    
    const page1 = await context1.newPage();
    const page2 = await context2.newPage();

    console.log('🌐 Opening app in both browsers...');
    await Promise.all([
      page1.goto('http://ccscloud.dlsu.edu.ph:60232/'),
      page2.goto('http://ccscloud.dlsu.edu.ph:60232/')
    ]);

    console.log('⏳ Waiting 12 seconds...');
    await page1.waitForTimeout(12000);

    console.log('📋 Both users navigating to Order Management...');
    await Promise.all([
      page1.getByRole('tab', { name: 'Order Management' }).click(),
      page2.getByRole('tab', { name: 'Order Management' }).click()
    ]);

    console.log('⏳ Waiting 12 seconds...');
    await page1.waitForTimeout(12000);

    console.log('✏️ Both users clicking Edit on the first order...');
    await Promise.all([
      page1.locator('table tbody tr').first().getByRole('button').filter({ has: page1.locator('svg') }).first().click(),
      page2.locator('table tbody tr').first().getByRole('button').filter({ has: page2.locator('svg') }).first().click()
    ]);

    console.log('⏳ Waiting 12 seconds...');
    await page1.waitForTimeout(12000);

    console.log('🔢 Both users changing quantities (5 and 10)...');
    await Promise.all([
      (async () => {
        const input = page1.getByTestId('edit-quantity-input');
        await input.waitFor({ state: 'visible' });
        await input.evaluate((el, value) => {
          el.value = value;
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }, '5');
      })(),
      (async () => {
        const input = page2.getByTestId('edit-quantity-input');
        await input.waitFor({ state: 'visible' });
        await input.evaluate((el, value) => {
          el.value = value;
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }, '10');
      })()
    ]);

    console.log('⏳ Waiting 12 seconds...');
    await page1.waitForTimeout(12000);

    console.log('💾 Both users clicking Save at the same time...');
    await Promise.all([
      page1.getByRole('button').filter({ has: page1.locator('svg.lucide-save') }).click(),
      page2.getByRole('button').filter({ has: page2.locator('svg.lucide-save') }).click()
    ]);

    console.log('⏳ Waiting for save to complete...');
    await page1.waitForTimeout(3000);

    console.log('✅ Checking final result...');
    const row1 = await page1.locator('table tbody tr:first-child').textContent();
    const row2 = await page2.locator('table tbody tr:first-child').textContent();
    
    console.log('User 1 sees:', row1);
    console.log('User 2 sees:', row2);
    console.log('Test complete! Check which update won.');

    await context1.close();
    await context2.close();
  });

  test('concurrent order creation - 2 users creating orders', async ({ browser }) => {
    const context1 = await browser.newContext();
    const context2 = await browser.newContext();
    
    const page1 = await context1.newPage();
    const page2 = await context2.newPage();

    console.log('🌐 Opening app in both browsers...');
    await Promise.all([
      page1.goto('http://ccscloud.dlsu.edu.ph:60232/'),
      page2.goto('http://ccscloud.dlsu.edu.ph:60232/')
    ]);

    console.log('⏳ Waiting 12 seconds...');
    await page1.waitForTimeout(12000);

    console.log('📋 Both users navigating to Order Management...');
    await Promise.all([
      page1.getByRole('tab', { name: 'Order Management' }).click(),
      page2.getByRole('tab', { name: 'Order Management' }).click()
    ]);

    console.log('⏳ Waiting 12 seconds...');
    await page1.waitForTimeout(12000);

    console.log('➕ Both users clicking New Order...');
    await Promise.all([
      page1.getByRole('button', { name: 'New Order' }).click(),
      page2.getByRole('button', { name: 'New Order' }).click()
    ]);

    console.log('⏳ Waiting 12 seconds...');
    await page1.waitForTimeout(12000);

    console.log('🔢 Both users entering quantities (3 and 7)...');
    await Promise.all([
      (async () => {
        const input = page1.getByTestId('create-quantity-input');
        await input.waitFor({ state: 'visible' });
        await input.evaluate((el, value) => {
          el.value = value;
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }, '3');
      })(),
      (async () => {
        const input = page2.getByTestId('create-quantity-input');
        await input.waitFor({ state: 'visible' });
        await input.evaluate((el, value) => {
          el.value = value;
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }, '7');
      })()
    ]);

    console.log('⏳ Waiting 12 seconds...');
    await page1.waitForTimeout(12000);

    console.log('💾 Both users creating orders at the same time...');
    await Promise.all([
      page1.getByRole('button', { name: 'Create Order' }).click(),
      page2.getByRole('button', { name: 'Create Order' }).click()
    ]);

    console.log('⏳ Waiting for creation to complete...');
    await page1.waitForTimeout(3000);

    console.log('✅ Both orders should be created successfully!');

    await context1.close();
    await context2.close();
  });

  test('concurrent partition moves - update order to move between nodes', async ({ browser }) => {
    const context1 = await browser.newContext();
    const context2 = await browser.newContext();
    
    const page1 = await context1.newPage();
    const page2 = await context2.newPage();

    console.log('🌐 Opening app in both browsers...');
    await Promise.all([
      page1.goto('http://ccscloud.dlsu.edu.ph:60232/'),
      page2.goto('http://ccscloud.dlsu.edu.ph:60232/')
    ]);

    console.log('⏳ Waiting 12 seconds...');
    await page1.waitForTimeout(12000);

    console.log('📋 Both users navigating to Order Management...');
    await Promise.all([
      page1.getByRole('tab', { name: 'Order Management' }).click(),
      page2.getByRole('tab', { name: 'Order Management' }).click()
    ]);

    console.log('⏳ Waiting 12 seconds...');
    await page1.waitForTimeout(12000);

    console.log('✏️ Both users editing the same order...');
    await Promise.all([
      page1.locator('table tbody tr').first().getByRole('button').filter({ has: page1.locator('svg') }).first().click(),
      page2.locator('table tbody tr').first().getByRole('button').filter({ has: page2.locator('svg') }).first().click()
    ]);

    console.log('⏳ Waiting 12 seconds...');
    await page1.waitForTimeout(12000);

    console.log('🔄 Both users changing quantities (3 for node1, 8 for node2)...');
    await Promise.all([
      (async () => {
        const input = page1.getByTestId('edit-quantity-input');
        await input.waitFor({ state: 'visible' });
        await input.evaluate((el, value) => {
          el.value = value;
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }, '3');
      })(),
      (async () => {
        const input = page2.getByTestId('edit-quantity-input');
        await input.waitFor({ state: 'visible' });
        await input.evaluate((el, value) => {
          el.value = value;
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }, '8');
      })()
    ]);

    console.log('⏳ Waiting 12 seconds...');
    await page1.waitForTimeout(12000);

    console.log('💾 Both users saving (triggering partition moves)...');
    await Promise.all([
      page1.getByRole('button').filter({ has: page1.locator('svg.lucide-save') }).click(),
      page2.getByRole('button').filter({ has: page2.locator('svg.lucide-save') }).click()
    ]);

    console.log('⏳ Waiting for replication...');
    await page1.waitForTimeout(5000);

    console.log('✅ Check Database Dashboard to see which partition the order ended up in!');

    await context1.close();
    await context2.close();
  });

});
