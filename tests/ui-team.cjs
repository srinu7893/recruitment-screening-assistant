const {chromium}=require('playwright');
const {spawn,spawnSync}=require('node:child_process');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const assert=require('node:assert/strict');
(async()=>{
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'screening-team-'));
 const password=crypto.randomBytes(24).toString('hex'),initial=crypto.randomBytes(24).toString('hex'),replacement=crypto.randomBytes(24).toString('hex');
 const salt=crypto.randomBytes(16),digest=crypto.pbkdf2Sync(password,salt,600000,32,'sha256').toString('hex');
 const accounts=JSON.stringify([{username:'admin',name:'Admin',role:'admin',password_hash:`pbkdf2_sha256$600000$${salt.toString('hex')}$${digest}`}]);
 const server=spawn(process.env.PYTHON||'python',['-m','tests.team_ui_server'],{env:{...process.env,TEST_UI_DATABASE:path.join(directory,'app.sqlite3'),SCREENING_AUTH_MODE:'password',SCREENING_PASSWORD_ACCOUNTS:accounts,K_SERVICE:'',DATABASE_URL:'',SCREENING_SCAN_MODE:'off'},stdio:['ignore','pipe','pipe']});
 let browser;
 try{
  await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Test server startup timeout')),15000);server.stdout.on('data',v=>{if(String(v).includes('Team test server ready')){clearTimeout(timer);resolve();}});server.on('exit',v=>{clearTimeout(timer);reject(Error('Test server exited '+v));});});
  browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  async function login(user,secret){await page.locator('#username-field:not([hidden])').waitFor();await page.fill('#username',user);await page.fill('#token',secret);await page.click('#login-form button');await page.locator('#workspace:not([hidden])').waitFor();}
  await page.goto('http://127.0.0.1:18768');await login('admin',password);
  await page.click('[data-tab="roles"]');await page.fill('#role-title','Support');await page.fill('#role-version','support:v1');
  await page.fill('[data-field="phrases"]','');await page.getByText('Preview matching before approval',{exact:true}).click();await page.click('#role-preview');await page.getByText('python-api: Add at least one matching phrase.',{exact:true}).waitFor();
  await page.check('#approve');await page.click('#role-form button.primary');await page.waitForFunction(()=>document.getElementById('notice').textContent.includes('matching phrases'));
  await page.fill('[data-field="phrases"]','Python\nSQL');await page.fill('#role-preview-text','Used Python to investigate a service.');await page.click('#role-preview');await page.locator('#role-preview-result blockquote').waitFor();
  assert.match(await page.locator('#role-preview-result').textContent(),/Python, SQL/);await page.check('#approve');await page.click('#role-form button.primary');await page.locator('.role-card').waitFor();
  await page.click('[data-tab="intake"]');await page.fill('#profile-text','FAIL-ONCE fictional check. Used Python to support services.');await page.click('#paste-form button.primary');await page.locator('#run-rows').getByText('Processing failed',{exact:true}).waitFor();await page.locator('#run-rows').getByRole('button',{name:'Review →'}).first().click();await page.locator('#detail[open]').waitFor();assert.match(await page.locator('#detail-content').textContent(),/could not be reached/);await page.locator('#detail-content').getByRole('button',{name:'Retry screening',exact:true}).click();await page.click('#close-detail');await page.locator('#run-rows').getByText('Needs review',{exact:true}).waitFor({timeout:15000});assert.equal(await page.locator('#run-rows').getByText('Processing failed',{exact:true}).count(),1);
  await page.click('[data-tab="automation"]');await page.waitForFunction(()=>document.getElementById('agent-inbox-path').textContent.includes('unavailable'));
  assert.equal(await page.locator('#automation-inbox').isVisible(),false);assert.equal(await page.locator('#automation-feed').isVisible(),false);assert.equal(await page.locator('#automation-enabled').isDisabled(),true);assert.equal(await page.locator('#agent-run').isDisabled(),true);
  await page.click('[data-tab="team"]');await page.fill('#account-username','reviewer');await page.fill('#account-name','Test Reviewer');await page.selectOption('#account-role','viewer');await page.fill('#account-password',initial);await page.fill('#team-admin-password',password);await page.click('#account-form button');await page.locator('#team-accounts h3').getByText('reviewer',{exact:true}).waitFor();
  const account=page.locator('#team-accounts .panel').filter({has:page.getByRole('heading',{name:'reviewer',exact:true})});
  await page.fill('#team-admin-password',password);await account.getByRole('button',{name:'Issue recovery code',exact:true}).click();await page.waitForFunction(()=>document.getElementById('account-recovery-output').textContent.includes('Send privately:'));
  const code=(await page.locator('#account-recovery-output').textContent()).split('Send privately: ')[1];assert.equal(code.length,43);assert.equal(await page.inputValue('#team-admin-password'),'');
  await page.click('#clear-recovery');assert.equal(await page.locator('#account-recovery-output').textContent(),'');
  await page.click('#operations-check');await page.waitForFunction(()=>document.getElementById('operations-status').textContent.includes('"database": "connected"'));
  fs.mkdirSync('test-results',{recursive:true});await page.screenshot({path:'test-results/team-operations.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);await page.setViewportSize({width:1440,height:1000});
  await page.click('#logout');await page.locator('#login:not([hidden])').waitFor();await page.locator('#recovery-panel:not([hidden])').waitFor();await page.locator('#recovery-panel summary').click();
  await page.fill('#recovery-user','reviewer');await page.fill('#recovery-code',code);await page.fill('#recovery-password',replacement);await page.click('#recovery-form button');await page.getByText('Password updated. Sign in with your new password.',{exact:true}).waitFor();
  await login('reviewer',replacement);await page.click('[data-tab="team"]');assert.equal(await page.locator('#team-admin').isVisible(),false);
  assert.equal(await page.evaluate(async()=>(await fetch('/accounts')).status),403);
  assert.deepEqual(errors,[]);console.log('Team workflow passed: phrase preview, linked failed-review retry, source availability, account creation, recovery, operations and viewer isolation.');
 }finally{if(browser)await browser.close();if(server.exitCode===null){if(process.platform==='win32')spawnSync(path.join(process.env.SystemRoot||'C:\\Windows','System32','taskkill.exe'),['/PID',String(server.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});else server.kill('SIGTERM');await new Promise(resolve=>server.exitCode!==null?resolve():server.once('exit',resolve));}fs.rmSync(directory,{recursive:true,force:true,maxRetries:20,retryDelay:200});}
})().catch(e=>{console.error(e);process.exitCode=1;});
