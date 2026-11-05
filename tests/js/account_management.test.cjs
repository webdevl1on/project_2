const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function setup(reply){
 let submit,focus=false,calls=0,navigation=null;
 const message={hidden:true,focus(){focus=true;}},button={disabled:false},password={value:'private-secret'},username={value:'retained-name'};
 const form={action:'https://example.test/admin/users/new',reportValidity:()=>true,addEventListener(name,callback){submit=callback;},querySelector(selector){return selector==='button'?button:message;},querySelectorAll:()=>[password]};
 vm.runInNewContext(fs.readFileSync('app/static/js/account_management.js','utf8'),{document:{querySelectorAll:()=>[form]},FormData:class{constructor(value){assert.equal(value,form);}},fetch:async(...args)=>{calls++;return reply(...args);},location:{assign(target){navigation=target;}}});
 return {send:()=>submit({preventDefault(){}}),message,button,password,username,get focus(){return focus;},get calls(){return calls;},get navigation(){return navigation;}};
}
test('account errors retain non-secret drafts, clear passwords, focus the reason and re-enable submit',async()=>{
 const value=setup(async()=>({ok:false,json:async()=>({detail:'Логін уже зайнятий.'})}));await value.send();
 assert.equal(value.username.value,'retained-name');assert.equal(value.password.value,'');assert.equal(value.message.hidden,false);assert.equal(value.message.textContent,'Логін уже зайнятий.');assert.equal(value.focus,true);assert.equal(value.button.disabled,false);assert.equal(value.navigation,null);
});
test('one pending account operation prevents duplicate submissions and redirects only on success',async()=>{
 let resolve;const pending=new Promise(done=>resolve=done);const value=setup(async()=>{await pending;return {ok:true,json:async()=>({redirect_to:'/admin/users/2'})};});
 const first=value.send();await value.send();assert.equal(value.calls,1);assert.equal(value.button.disabled,true);resolve();await first;assert.equal(value.navigation,'/admin/users/2');assert.equal(value.button.disabled,false);
});
test('a rejected connection never navigates or leaves a credential in the form',async()=>{
 const value=setup(async()=>{throw Error('Connection refused');});await value.send();assert.equal(value.password.value,'');assert.equal(value.navigation,null);assert.equal(value.message.textContent,'Connection refused');
});
