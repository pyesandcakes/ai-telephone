// Optional browser acceptance test: npm install --no-save playwright
const {chromium} = require('playwright');
const {spawn} = require('node:child_process');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');
(async () => {
  const runs = await fs.mkdtemp(path.join(os.tmpdir(), 'telephone-ui-'));
  const host = spawn(process.env.PYTHON || 'python', ['app.py', '--demo', '--bind', '127.0.0.1', '--port', '8766', '--runs', runs], {cwd: __dirname, windowsHide: true});
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
    await control.locator('#prompt').fill('A red umbrella above a swimming pool');
    await control.locator('#limit').fill('2');
    await control.locator('#interval').fill('0');
    await control.locator('#start').click();
    await control.waitForFunction(() => document.querySelector('#status').textContent.includes('completed'));
    await image.waitForFunction(() => document.querySelector('#iteration').textContent.includes('002'));
    await text.waitForFunction(() => document.querySelector('#iteration').textContent.includes('002'));
    assert.equal(await control.locator('.history-row').count(), 2);
    assert.match(await text.locator('#wall-text').textContent(), /flat field/);
    assert.equal(await image.locator('#wall-image').isVisible(), true);
    await control.locator('.history-row').last().getByRole('button', {name:'Replay'}).click();
    await text.waitForFunction(() => document.querySelector('#iteration').textContent.includes('001'));
    await control.getByRole('link', {name:'Present on this laptop'}).click();
    await control.waitForFunction(() => document.querySelector('#iteration').textContent.includes('001'));
    assert.equal(await control.locator('#wall-image').isVisible(), true);
    assert.equal(await control.locator('#wall-text').isVisible(), true);
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
    assert.deepEqual(errors, []);
    console.log('PASS: control start, two iterations, LAN displays, archive, replay, combined wide/narrow view, return to authenticated controls, no browser errors.');
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
