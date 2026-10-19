/* Real browser: password login, cookie restoration, rules upload, logout. */
const {chromium}=require('playwright');
const {spawn,spawnSync}=require('node:child_process');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const assert=require('node:assert/strict');
(async()=>{
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'screening-password-'));
 const password=crypto.randomBytes(24).toString('hex');
 const salt=crypto.randomBytes(16);
 const digest=crypto.pbkdf2Sync(password,salt,600000,32,'sha256').toString('hex');
 const accounts=JSON.stringify([{username:'admin',name:'Administrator',role:'admin',password_hash:`pbkdf2_sha256$600000$${salt.toString('hex')}$${digest}`}]);
 const server=spawn(process.env.PYTHON||'python',['-m','screening.server','--provider','rules','--db',path.join(directory,'app.sqlite3'),'--port','18767'],{env:{...process.env,SCREENING_AUTH_MODE:'password',SCREENING_PASSWORD_ACCOUNTS:accounts,DATABASE_URL:'',K_SERVICE:'',SCREENING_SCAN_MODE:'off',SCREENING_INBOX_DIR:'',SCREENING_PUBLIC_URL:'',SCREENING_SYNC_SECONDS:'0'},stdio:['ignore','pipe','pipe']});
 let browser;
 try{
  await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Startup timeout')),15000);server.stdout.on('data',chunk=>{if(String(chunk).includes('Recruiter workspace:')){clearTimeout(timer);resolve();}});server.on('exit',code=>{clearTimeout(timer);reject(Error('Server exited '+code));});});
  browser=await chromium.launch({headless:true,args:['--no-sandbox']});
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:18767');
  await page.locator('#username-field:not([hidden])').waitFor();
  await page.fill('#username','admin');await page.fill('#token','incorrect');await page.click('#login-form button');
  await page.getByText('invalid_credentials',{exact:true}).waitFor();
  await page.fill('#token',password);await page.click('#login-form button');await page.locator('#workspace:not([hidden])').waitFor();
  assert.equal(await page.locator('#mode').textContent(),'LOCAL EVIDENCE MATCHING');
  await page.reload();await page.locator('#workspace:not([hidden])').waitFor();
  const result=await page.evaluate(async()=>{
   const session=await (await fetch('/auth/session')).json();
   const headers={'Content-Type':'application/json','X-CSRF-Token':session.csrf};
   const role={role_version:'browser:v1',title:'Engineer',criteria:[{id:'python',description:'Experience with "Python"',required:true,question:'Describe your Python work.'}]};
   const approved=await fetch('/roles',{method:'POST',headers,body:JSON.stringify(role)});
   return approved.status;
  });assert.equal(result,201);
  await page.click('#refresh');await page.click('[data-tab="intake"]');
  await page.setInputFiles('#files',{name:'fictional.txt',mimeType:'text/plain',buffer:Buffer.from('Built Python services for a fictional project.')});
  await page.click('#upload-form button.primary');
  await page.waitForFunction(()=>document.getElementById('upload-progress').textContent.includes('1 queued'));
  await page.click('[data-tab="pipeline"]');await page.locator('#run-rows tr').first().waitFor({timeout:15000});
  await page.locator('#run-rows tr').first().getByRole('button',{name:'Review →'}).click();
  await page.locator('#detail[open]').waitFor();
  assert.match(await page.locator('#detail-content').textContent(),/Literal mention found/);
  await page.click('#close-detail');
  fs.mkdirSync('test-results',{recursive:true});await page.screenshot({path:'test-results/password-rules.png',fullPage:true});
  await page.click('#logout');await page.locator('#login:not([hidden])').waitFor();
  assert.equal(await page.evaluate(async()=>(await fetch('/health')).status),401);
  assert.deepEqual(errors,[]);
  console.log('Password browser acceptance passed: invalid password, login, refresh, rules upload, evidence review, logout.');
 }finally{
  if(browser)await browser.close();
  if(server.exitCode===null){
   // Windows virtualenv launchers can leave their Python child holding SQLite.
   if(process.platform==='win32')spawnSync(path.join(process.env.SystemRoot||'C:\\Windows','System32','taskkill.exe'),['/PID',String(server.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});
   else server.kill('SIGTERM');
   await new Promise(resolve=>server.exitCode!==null?resolve():server.once('exit',resolve));
  }
  fs.rmSync(directory,{recursive:true,force:true,maxRetries:20,retryDelay:200});
 }
})().catch(error=>{console.error(error);process.exit(1);});
