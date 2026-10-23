/* Stop only the test process tree we started; virtualenv launchers have children. */
const {spawnSync}=require('node:child_process');
const path=require('node:path');
module.exports=async function stopServer(server){
 if(!server||server.exitCode!==null)return;
 if(process.platform==='win32')spawnSync(path.join(process.env.SystemRoot||'C:\\Windows','System32','taskkill.exe'),['/PID',String(server.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});
 else server.kill('SIGTERM');
 await new Promise(resolve=>server.exitCode!==null?resolve():server.once('exit',resolve));
};
