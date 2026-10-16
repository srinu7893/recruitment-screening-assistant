/* End-to-end automatic intake, durable records and restart checks. Synthetic data only. */
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const crypto=require('node:crypto');
const assert=require('node:assert/strict');
(async()=>{
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'screening-agent-'));
 const inbox=path.join(directory,'inbox');fs.mkdirSync(inbox);
 const token=crypto.randomBytes(32).toString('hex');
 let server,browser;
 async function start(){
  server=spawn(process.env.PYTHON||'python',['-m','screening.server','--db',path.join(directory,'app.sqlite3'),'--port','18766','--provider','demo'],{env:{...process.env,SCREENING_API_TOKEN:token,SCREENING_INBOX_DIR:inbox,SCREENING_SCAN_MODE:'off',SCREENING_AUTH_MODE:'token',SCREENING_ACCOUNTS:'',DATABASE_URL:'',K_SERVICE:'',SCREENING_SYNC_SECONDS:'0'},stdio:['ignore','pipe','pipe']});
  await new Promise((resolve,reject)=>{let stderr='';const timer=setTimeout(()=>reject(Error('Agent server startup timed out: '+stderr)),15000);server.stderr.on('data',c=>stderr+=c);server.on('error',reject);server.once('exit',code=>{clearTimeout(timer);reject(Error('Agent server exited '+code+': '+stderr));});server.stdout.on('data',c=>{if(String(c).includes('Recruiter workspace:')){clearTimeout(timer);resolve();}});});
 }
 async function stop(){if(!server||server.exitCode!==null)return;server.kill('SIGTERM');await new Promise(resolve=>server.once('exit',resolve));}
 function resume(name,text){const p=path.join(inbox,name);fs.writeFileSync(p,text);fs.utimesSync(p,new Date(1000),new Date(1000));}
 async function api(route,body){const response=await fetch('http://127.0.0.1:18766'+route,{method:body===undefined?'GET':'POST',headers:{Authorization:'Bearer '+token,...(body===undefined?{}:{'Content-Type':'application/json'})},body:body===undefined?undefined:JSON.stringify(body)});const value=await response.json();assert(response.ok,JSON.stringify(value));return value;}
 async function until(fn){const end=Date.now()+20000;while(Date.now()<end){if(await fn())return;await new Promise(r=>setTimeout(r,200));}throw Error('Timed out waiting for agent processing');}
 try{
  await start();browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:18766');await page.fill('#token',token);await page.click('#login-form button');await page.locator('#workspace:not([hidden])').waitFor();
  await page.click('[data-tab="roles"]');await page.fill('#role-title','Support engineer');await page.fill('#role-version','automation:v1');await page.check('#approve');await page.click('#role-form button.primary');await page.locator('.role-card').waitFor();
  await page.click('[data-tab="automation"]');await page.selectOption('#automation-role','automation:v1');await page.check('#automation-inbox');await page.click('#automation-form button.primary');await page.waitForFunction(()=>document.getElementById('notice').textContent.includes('Automation saved'));
  resume('first.txt','Maintained fictional Python services and investigated Linux logs.');
  await page.click('#agent-run');await until(async()=>(await api('/jobs')).some(j=>j.status==='completed'));
  console.log('PASS: manual source check extracts, queues and screens a resume');
  resume('second.txt','Designed a fictional PostgreSQL service and supported production incidents.');
  await page.check('#automation-enabled');await page.click('#automation-form button.primary');await page.waitForFunction(()=>document.getElementById('notice').textContent.includes('Automation saved'));
  await until(async()=>(await api('/jobs')).filter(j=>j.status==='completed').length===2);
  console.log('PASS: scheduled agent picks up a new resume without a source-check click');
  await page.click('#agent-run');await until(async()=>(await api('/automation')).running===false);assert.equal((await api('/jobs')).length,2);
  resume('invalid.txt',Buffer.from([0xff,0xfe,0xff]));await page.click('#agent-run');
  await page.getByRole('button',{name:'Retry import',exact:true}).waitFor();await page.getByRole('button',{name:'Retry import',exact:true}).click();
  await until(async()=>(await api('/automation')).records.some(r=>r.status==='retry_requested'));
  await page.click('#agent-run');await until(async()=>(await api('/automation')).records.some(r=>r.status==='failed'));
  console.log('PASS: failures are visible and an explicit retry is tracked');
  await stop();await start();assert.equal((await api('/automation')).settings.enabled,true);assert.equal((await api('/jobs')).length,2);assert.equal((await api('/runs')).runs.length,2);
  console.log('PASS: settings and reviews survive server restart without duplicate import');
  await page.reload();await page.fill('#token',token);await page.click('#login-form button');await page.locator('#workspace:not([hidden])').waitFor();await page.click('[data-tab="automation"]');await page.locator('#agent-records tbody tr').first().waitFor();
  fs.mkdirSync('test-results',{recursive:true});await page.screenshot({path:'test-results/automation-desktop.png',fullPage:true});
  await page.getByRole('button',{name:'Open review',exact:true}).first().click();await page.locator('#detail[open]').waitFor();await page.screenshot({path:'test-results/automation-review.png',fullPage:true});await page.click('#close-detail');
  await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);await page.screenshot({path:'test-results/automation-mobile.png',fullPage:true});assert.deepEqual(errors,[]);
  console.log('PASS: tracked review links, desktop/mobile layouts and no script errors');
 }finally{if(browser)await browser.close();await stop();fs.rmSync(directory,{recursive:true,force:true,maxRetries:10,retryDelay:200});}
})().catch(error=>{console.error(error);process.exitCode=1;});
