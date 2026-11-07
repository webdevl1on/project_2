const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function client(reply=()=>new Response('{}',{status:200})){
 const calls=[],meta={content:'current-token'},fields=[{value:'current-token'}],banners=[];
 const document={querySelector:()=>meta,querySelectorAll:()=>fields,addEventListener(){},getElementById:()=>banners[0]||null,createElement:()=>({style:{},append(){},setAttribute(){}}),body:{append:n=>banners.push(n)}};
 const window={addEventListener(){},fetch:async(input,init)=>{calls.push({input,init});return reply();}};
 vm.runInNewContext(fs.readFileSync('app/static/js/security_session.js','utf8'),{window,document,location:{href:'https://example.test/persons',origin:'https://example.test',pathname:'/persons',search:'',hash:''},URL,Request,Headers});
 return {window,calls,meta,fields,banners};
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
