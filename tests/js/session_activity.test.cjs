const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
test('idle monitoring never sends a heartbeat and only trusted interaction requests activity',async()=>{
 const listeners={},calls=[];let interval;const document={querySelector:()=>({content:'csrf'}),querySelectorAll:()=>[],addEventListener:(name,cb)=>listeners[name]=cb,getElementById:()=>null};
 const window={addEventListener(){},setInterval(fn){interval=fn;},fetch:async(url,init)=>{calls.push({url,init});return new Response(JSON.stringify({idle_expires_at:new Date(Date.now()+900000).toISOString(),expires_at:new Date(Date.now()+28800000).toISOString()}),{status:200});}};
 vm.runInNewContext(fs.readFileSync('app/static/js/security_session.js','utf8'),{window,document,location:{href:'https://example.test/persons',origin:'https://example.test',pathname:'/persons',search:'',hash:''},URL,Request,Headers,Date,Infinity});
 await new Promise(resolve=>setImmediate(resolve));assert.equal(calls.length,1);interval();interval();assert.equal(calls.length,1);
 await listeners.pointerdown({isTrusted:false});assert.equal(calls.length,1);
 await listeners.pointerdown({isTrusted:true});assert.equal(calls[1].url,'/account/activity');assert.equal(new Headers(calls[1].init.headers).get('X-CSRF-Token'),'csrf');
 await listeners.keydown({isTrusted:true});assert.equal(calls.length,2);
});
