/* Synthetic fixture driver: complete the real second factor, never bypass the server. */
const crypto=require('node:crypto');const codes=new Map();
function totp(secret){const alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';let bits='';for(const c of secret)bits+=alphabet.indexOf(c).toString(2).padStart(5,'0');const key=Buffer.from((bits.match(/.{8}/g)||[]).map(v=>parseInt(v,2)));const counter=Buffer.alloc(8);counter.writeBigUInt64BE(BigInt(Math.floor(Date.now()/30000)));const digest=crypto.createHmac('sha1',key).update(counter).digest(),offset=digest[19]&15;return String((digest.readUInt32BE(offset)&0x7fffffff)%1000000).padStart(6,'0');}
async function complete(request,base,post=request.post.bind(request),onlyVerify=false){
 const stateResponse=await request.get(base+'/auth/mfa/state');if(!stateResponse.ok())throw Error(await stateResponse.text());const state=await stateResponse.json();
 const call=async(path,data)=>{const r=await post(base+'/auth/mfa/'+path,{data,headers:{'X-CSRF-Token':state.csrf_token}});if(!r.ok())throw Error(await r.text());return r;};
 if(!state.verified){
  if(state.kind==='setup'){const setup=await(await call('totp/start',{})).json();const result=await(await call('totp/confirm',{code:totp(setup.secret)})).json();codes.set(state.username,result.codes);}
  else{const code=codes.get(state.username)?.shift();if(!code)throw Error('No fixture backup code for '+state.username);await call('prove',{method:'backup',code});}
 }
 if(onlyVerify)return state;return call('finish',{});
}
module.exports={complete,totp,verify:(request,base)=>complete(request,base,request.post.bind(request),true)};
