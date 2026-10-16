/* Standalone offline showcase acceptance; no backend or credentials required. */
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
(async () => {
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('file://' + path.resolve('showcase/index.html').replaceAll('\\','/'));
    assert.equal(await page.locator('.candidate').count(), 6);
    console.log('PASS: six fictional profiles render');
    await page.click('#tour-next');
    assert.match(await page.locator('#tour').textContent(), /1 \/ 5/);
    console.log('PASS: guided tour');
    await page.selectOption('#filter','needs_clarification');
    assert.equal(await page.locator('.candidate').count(),3);
    await page.selectOption('#filter','recommend_interview');
    assert.equal(await page.locator('.candidate').count(),2);
    console.log('PASS: scenario filters');
    await page.locator('.candidate').first().click();
    await page.getByText('What if the role requirements change?',{exact:true}).click();
    await page.getByLabel('Cloud or container operations',{exact:true}).check();
    assert.match(await page.locator('#detail').textContent(),/Preview: Needs clarification/);
    console.log('PASS: requirement-change preview');
    const download = page.waitForEvent('download');
    await page.getByRole('button',{name:'Download sample resume (.txt)',exact:true}).click();
    assert.equal((await download).suggestedFilename(),'PS-101.txt');
    console.log('PASS: sample resume download');
    fs.mkdirSync('test-results',{recursive:true});
    await page.screenshot({path:'test-results/showcase-desktop.png',fullPage:true});
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),true);
    await page.screenshot({path:'test-results/showcase-mobile.png',fullPage:true});
    assert.deepEqual(errors,[]);
    console.log('PASS: mobile layout and no browser script errors');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
