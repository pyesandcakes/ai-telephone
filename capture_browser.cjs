// Capture genuine browser views of a saved real run, without touching other tabs.
const {chromium} = require('playwright');
const {spawn} = require('node:child_process');
const fs = require('node:fs/promises');
const path = require('node:path');
(async () => {
  const run = path.resolve(process.argv[2]);
  const out = path.resolve(process.argv[3] || 'promotional-output/screenshots');
  const manifest = JSON.parse(await fs.readFile(path.join(run,'manifest.json'),'utf8'));
  if (manifest.demo) throw new Error('Use a real run for promotional screenshots');
  await fs.mkdir(out,{recursive:true});
  const platformFolder = `${process.platform === 'darwin' ? 'darwin' : 'windows'}-${process.arch === 'arm64' ? 'arm64' : process.platform === 'win32' ? 'amd64' : 'x86_64'}`;
  const relativePython = process.platform === 'win32' ? ['Scripts','python.exe'] : ['bin','python'];
  const candidates = [path.join(__dirname,'.runtime',platformFolder,...relativePython), path.join(__dirname,process.platform === 'win32' ? '.venv' : '.venv-mac',...relativePython)];
  let python = process.env.PYTHON;
  if (!python) {
    for (const candidate of candidates) { try { await fs.access(candidate); python = candidate; break; } catch {} }
  }
  python ||= process.platform === 'win32' ? 'python' : 'python3';
  const host = spawn(python,['app.py','--runs',path.dirname(run),'--bind','127.0.0.1','--port','8767'],{cwd:__dirname,windowsHide:true});
  let browser;
  try {
    const url = await new Promise((resolve,reject) => {
      let result='';
      host.stdout.on('data',bytes=>{result+=bytes; const match=result.match(/Controls: (http[^\s]+)/); if(match)resolve(match[1]);});
      host.on('error',reject);
      host.on('exit',code=>{if(code)reject(new Error('Host failed'));});
      setTimeout(()=>reject(new Error('Host did not start')),15000).unref();
    });
    const token = new URL(url).hash.slice(7);
    const records = (await fs.readdir(run)).filter(name=>/^\d{6}\.json$/.test(name)).sort();
    const last = JSON.parse(await fs.readFile(path.join(run,records.at(-1)),'utf8'));
    const res=await fetch('http://127.0.0.1:8767/api/replay',{method:'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:JSON.stringify({run:manifest.id,iteration:last.iteration})});
    if(!res.ok)throw new Error(await res.text());
    browser=await chromium.launch({headless:true});
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    await page.goto(url);
    await page.waitForFunction(()=>document.querySelector('#preview-image').getAttribute('src'));
    await page.screenshot({path:path.join(out,'control-and-history.png'),fullPage:true});
    for(const view of ['combined','image','text']){
      await page.goto(`http://127.0.0.1:8767/${view}`);
      await page.waitForFunction(()=>document.querySelector('#iteration').textContent.includes('Iteration'));
      await page.screenshot({path:path.join(out,`${view}-display.png`)});
    }
    await page.goto('http://127.0.0.1:8767/combined');
    await page.setViewportSize({width:600,height:900});
    await page.waitForFunction(()=>document.querySelector('#iteration').textContent.includes('Iteration'));
    await page.screenshot({path:path.join(out,'combined-portrait.png')});
    console.log('Saved actual browser screenshots:',out);
  } finally {
    if(browser)await browser.close();
    host.kill();
    await new Promise(resolve=>host.exitCode!==null?resolve():host.once('exit',resolve));
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
