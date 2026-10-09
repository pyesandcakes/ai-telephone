// Optional browser acceptance test: npm install --no-save playwright
const {chromium} = require('playwright');
const {spawn} = require('node:child_process');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');
(async () => {
  const runs = await fs.mkdtemp(path.join(os.tmpdir(), 'telephone-ui-'));
  const host = spawn(process.env.PYTHON || 'python', ['app.py', '--simulated-demo', '--bind', '127.0.0.1', '--port', '8766', '--runs', runs], {cwd: __dirname, windowsHide: true});
  let browser;
  try {
    const url = await new Promise((resolve, reject) => {
      let output = '';
      const timeout = setTimeout(() => reject(new Error('Host startup timed out')), 15000);
      host.stdout.on('data', chunk => {
        output += chunk;
        const match = output.match(/Controls: (http[^\s]+)/);
        if (match) {clearTimeout(timeout); resolve(match[1]);}
      });
      host.on('error', reject);
      host.on('exit', code => {if (code) reject(new Error(`Host exited ${code}`));});
    });
    browser = await chromium.launch({headless:true, ...(process.env.BROWSER_CHANNEL ? {channel: process.env.BROWSER_CHANNEL} : {})});
    const context = await browser.newContext({viewport:{width:1440,height:1000}});
    const control = await context.newPage(), image = await context.newPage(), text = await context.newPage();
    const errors = [];
    for (const page of [control,image,text]) page.on('pageerror', e => errors.push(e.message));
    await control.goto(url);
    await image.goto('http://127.0.0.1:8766/image');
    await text.goto('http://127.0.0.1:8766/text');
    await control.waitForFunction(() => document.querySelector('#prompt').readOnly);
    await control.locator('#limit').fill('18');
    await control.locator('#interval').fill('0.5');
    await control.locator('#start').click();
    await image.locator('#generation-progress').waitFor({state:'visible'});
    assert.equal(await control.locator('#reset').isDisabled(), true);
    assert.equal(await image.locator('#reset').count(), 0);
    assert.equal(await text.locator('#reset').count(), 0);
    assert.match(await image.locator('#progress-label').textContent(), /completed/);
    await control.waitForFunction(() => document.querySelector('#status').textContent.includes('completed'));
    await image.waitForFunction(() => document.querySelector('#iteration').textContent.includes('018'));
    await text.waitForFunction(() => document.querySelector('#iteration').textContent.includes('018'));
    assert.equal(await control.locator('.history-row').count(), 18);
    assert.match(await text.locator('#wall-text').textContent(), /red ring/);
    assert.equal(await image.locator('#wall-image').isVisible(), true);
    assert.equal(await image.locator('#wall-text').isVisible(), false);
    for (const page of [control, image, text]) {
      assert.equal(await page.evaluate(() => getComputedStyle(document.body).backgroundColor), 'rgb(0, 0, 0)');
    }
    assert.equal(await text.locator('#provenance').isVisible(), true);
    await control.locator('.history-row').last().getByRole('button', {name:'Replay'}).click();
    await text.waitForFunction(() => document.querySelector('#iteration').textContent.includes('001'));
    await control.getByRole('link', {name:'Present on this laptop'}).click();
    await control.waitForFunction(() => document.querySelector('#iteration').textContent.includes('001'));
    assert.equal(await control.locator('#wall-image').isVisible(), true);
    assert.equal(await control.locator('#wall-text').isVisible(), true);
    assert.equal(await control.locator('#original-prompt-panel').isVisible(), true);
    assert.match(await control.locator('#original-prompt').textContent(), /luminous red ring/);
    assert.equal(await control.locator('#wall-text').textContent(), await text.locator('#wall-text').textContent());
    await fs.mkdir(path.join(__dirname,'screenshots'), {recursive:true});
    await control.screenshot({path:path.join(__dirname,'screenshots','combined.png')});
    await control.setViewportSize({width:600,height:900});
    const bounds = await control.locator('#wall').evaluate(el => ({width:el.scrollWidth, viewport:innerWidth}));
    assert.ok(bounds.width <= bounds.viewport, 'Combined view fits a narrow screen');
    await control.screenshot({path:path.join(__dirname,'screenshots','combined-narrow.png')});
    await control.setViewportSize({width:1440,height:1000});
    await control.getByRole('link', {name:'Controls',exact:true}).click();
    await control.waitForFunction(() => document.querySelector('#status').textContent.includes('replay'));
    await control.screenshot({path:path.join(__dirname,'screenshots','control.png'),fullPage:true});
    await image.screenshot({path:path.join(__dirname,'screenshots','image.png')});
    await text.screenshot({path:path.join(__dirname,'screenshots','text.png')});
    assert.equal(await image.locator('#generation-progress').isVisible(), false);
    const combinedPage = await context.newPage();
    await combinedPage.goto('http://127.0.0.1:8766/combined');
    await combinedPage.locator('#wall-image').waitFor({state:'visible'});
    assert.equal(await combinedPage.locator('#reset').count(), 0);
    await control.locator('#reset').click();
    for (const page of [image, text, combinedPage]) {
      await page.waitForFunction(() => document.querySelector('#wall-image').hidden && document.querySelector('#wall-text').textContent === '');
      assert.equal(await page.locator('#generation-progress').isVisible(), false);
    }
    assert.equal(await control.locator('.history-row').count(), 18);
    await control.locator('.history-row').last().getByRole('button', {name:'Replay'}).click();
    await combinedPage.locator('#wall-image').waitFor({state:'visible'});
    await control.locator('#replay-reading').uncheck();
    await control.locator('#replay-interval').fill('0.5');
    await control.locator('#replay-run').click();
    await text.waitForFunction(() => document.querySelector('#connection').textContent.includes('playing saved run'));
    await text.waitForFunction(() => document.querySelector('#iteration').textContent.includes('018'));
    await control.waitForFunction(() => document.querySelector('#status').textContent.includes('playback completed'));
    assert.equal(await control.locator('.history-row').count(), 18);
    assert.match(await text.locator('#provenance').textContent(), /saved chain/);
    await control.locator('#replay-repeat').check();
    await control.locator('#replay-run').click();
    await control.waitForFunction(() => document.querySelector('#status').textContent.includes('playing saved run'));
    await control.locator('#stop').click();
    await control.waitForFunction(() => document.querySelector('#status').textContent.includes('stopped'));
    assert.deepEqual(errors, []);
    console.log('PASS: control start, 18 iterations, black backgrounds, image-only isolation, demo provenance, LAN displays, archive, replay, combined wide/narrow view, return to authenticated controls, controller-only reset clears all three displays, archive retained and replay works, live progress, whole-run playback, loop and stop, no browser errors.');
  } finally {
    if (browser) await browser.close();
    host.kill();
    await new Promise(resolve => host.exitCode !== null ? resolve() : host.once('exit',resolve));
    if (path.dirname(path.resolve(runs)) !== path.resolve(os.tmpdir()) || !path.basename(runs).startsWith('telephone-ui-')) {
      throw new Error('Refusing cleanup outside the test temporary directory');
    }
    await fs.rm(runs,{recursive:true,force:true});
  }
})().catch(error => {console.error(error); process.exitCode=1;});
