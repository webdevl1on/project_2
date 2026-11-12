const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function client(reply=()=>new Response('{}',{status:200}),handled=false){
 const events=[],calls=[],meta={content:'current-token'},fields=[{value:'current-token'}],banners=[];
 const document={dispatchEvent:e=>{events.push(e);return !handled;},querySelector:()=>meta,querySelectorAll:()=>fields,addEventListener(){},getElementById:()=>banners[0]||null,createElement:()=>({style:{},append(){},setAttribute(){}}),body:{append:n=>banners.push(n),prepend:n=>banners.push(n)}};
 const window={addEventListener(){},fetch:async(input,init)=>{calls.push({input,init});return reply();}};
 vm.runInNewContext(fs.readFileSync('app/static/js/security_session.js','utf8'),{window,document,location:{href:'https://example.test/persons',origin:'https://example.test',pathname:'/persons',search:'',hash:''},URL,Request,Headers,CustomEvent:class {constructor(type,options){this.type=type;Object.assign(this,options);}}});
 return {window,calls,meta,fields,banners,events};
}
test('same-origin unsafe fetch supplies CSRF and preserves explicit invalid token',async()=>{
 const {window,calls}=client();await window.fetch('/persons/1/contacts',{method:'POST',body:'draft'});
 assert.equal(new Headers(calls[0].init.headers).get('X-CSRF-Token'),'current-token');assert.equal(calls[0].init.body,'draft');
 await window.fetch('/persons/1/contacts',{method:'POST',headers:{'X-CSRF-Token':'wrong'}});assert.equal(new Headers(calls[1].init.headers).get('X-CSRF-Token'),'wrong');
});
test('CSRF never leaks to another origin and is not added to a read',async()=>{
 const {window,calls}=client();await window.fetch('https://other.test/upload',{method:'POST'});await window.fetch('/persons');
 assert.equal(calls[0].init.headers,undefined);assert.equal(calls[1].init.headers,undefined);
});
test('Request objects retain method/body semantics and receive a same-origin token',async()=>{
 const {window,calls}=client();const original=new Request('https://example.test/persons/1/contacts',{method:'POST',body:'data'});
 await window.fetch(original);assert.equal(calls[0].input,original);assert.equal(new Headers(calls[0].init.headers).get('X-CSRF-Token'),'current-token');
});

test('personal re-login refreshes the page token and native form fields',async()=>{
 const {window,meta,fields}=client(()=>new Response(JSON.stringify({csrf_token:'renewed-token'}),{status:200}));
 await window.fetch('/auth/mfa/finish',{method:'POST',body:'credentials'});
 assert.equal(meta.content,'renewed-token');assert.equal(fields[0].value,'renewed-token');
});

test('MFA UI hook can keep drafts in place; unhandled pages retain their existing fallback',async()=>{
 const reply=()=>new Response(JSON.stringify({detail:'MFA_REAUTH_REQUIRED: підтвердження'}),{status:403});
 const handled=client(reply,true);await handled.window.fetch('/admin/access/users/2/matrix',{method:'POST'});assert.equal(handled.events[0].type,'project2:mfa-required');assert.equal(handled.events[0].cancelable,true);assert.equal(handled.banners.length,0);
 const ordinary=client(reply);await ordinary.window.fetch('/account/security/backup',{method:'POST'});assert.equal(ordinary.banners.length,1);
 const csrf=client(()=>new Response(JSON.stringify({detail:'Неправильний CSRF'}),{status:403}));await csrf.window.fetch('/admin/access/users/2/matrix',{method:'POST'});assert.equal(csrf.events.length,0);
});
