/* Same-origin CSRF for legacy fetch callers; ordinary forms carry server tokens. */
(() => {
 'use strict';if(window.Project2Session)return;
 const csrf=()=>document.querySelector('meta[name="project2-csrf"]')?.content||'';
 const original=window.fetch.bind(window);
 function expired(){
  if(document.getElementById('session-expired'))return;
  const box=document.createElement('div');box.id='session-expired';box.className='alert alert-warning position-fixed top-0 start-50 translate-middle-x';box.style.zIndex='2000';box.setAttribute('role','alert');
  box.append('Сесія завершилася. Введені значення залишилися у формі. ');
  const link=document.createElement('a');link.textContent='Увійти знову';link.href='/auth/login?return_to='+encodeURIComponent(location.pathname+location.search+location.hash);box.append(link);document.body.append(box);
 }
 window.fetch=async(input,init={})=>{
  const url=new URL(input instanceof Request?input.url:String(input),location.href);
  const method=(init.method||(input instanceof Request?input.method:'GET')).toUpperCase();
  const local=url.origin===location.origin;
  if(local&&!['GET','HEAD','OPTIONS'].includes(method)){
   const headers=new Headers(init.headers||(input instanceof Request?input.headers:undefined));
   if(!headers.has('X-CSRF-Token')&&csrf())headers.set('X-CSRF-Token',csrf());
   init={...init,headers};
  }
  const response=await original(input,init);
  if(local&&url.pathname==='/auth/mfa/finish'&&response.ok){
   try{const data=await response.clone().json();if(data.csrf_token){const meta=document.querySelector('meta[name="project2-csrf"]');if(meta)meta.content=data.csrf_token;document.querySelectorAll('form input[name=csrf]').forEach(input=>{input.value=data.csrf_token;input.defaultValue=data.csrf_token;});}}catch{}
  }
  if(local&&response.status===403){try{const detail=(await response.clone().json()).detail;if(typeof detail==='string'&&detail.startsWith('MFA_REAUTH_REQUIRED')){
   const handled=!document.dispatchEvent(new CustomEvent('project2:mfa-required',{cancelable:true,detail:{url:url.href}}));
   if(!handled&&!document.getElementById('mfa-reauth-needed')){const box=document.createElement('div');box.id='mfa-reauth-needed';box.className='alert alert-warning';box.append('Потрібне свіже підтвердження особи. ');const link=document.createElement('a');link.href='/account/security';link.textContent='Підтвердити пароль і MFA';box.append(link);document.body.prepend(box);}
  }}catch{}}
  if(local&&response.status===401&&url.pathname!='/auth/login')expired();
  return response;
 };
 document.addEventListener('submit',async event=>{
  const button=event.target.closest('[data-personal-logout]');if(!button)return;event.preventDefault();
  try{const response=await fetch('/auth/logout',{method:'POST'});if(response.ok||response.status===401)location.assign('/auth/login');else expired();}catch{expired();}
 });
 window.addEventListener('pageshow',event=>{if(event.persisted)location.reload();});
 // A trusted interaction triggers a bounded server update; polling itself never renews idle time.
 if(typeof window.setInterval==='function'&&csrf()){
  let idle=0,absolute=0,lastSent=0,warning=null;
  const deadlines=data=>{if(data.idle_expires_at)idle=Date.parse(data.idle_expires_at);if(data.expires_at)absolute=Date.parse(data.expires_at);};
  original('/auth/me').then(async r=>{if(r.ok)deadlines(await r.json());}).catch(()=>{});
  document.addEventListener('pointerdown',activity,{passive:true});document.addEventListener('keydown',activity,{passive:true});
  async function activity(event){if(!event.isTrusted||Date.now()-lastSent<60000)return;lastSent=Date.now();try{const r=await window.fetch('/account/activity',{method:'POST'});if(r.ok){deadlines(await r.json());warning?.remove();warning=null;}}catch{}}
  window.setInterval(()=>{const remaining=Math.min(idle||Infinity,absolute||Infinity)-Date.now();if(remaining<=0)expired();else if(remaining<120000&&!warning){warning=document.createElement('div');warning.className='alert alert-warning';warning.setAttribute('role','alert');warning.textContent='Сесія незабаром завершиться. Дія на сторінці продовжить її лише в межах 8 годин.';document.body.prepend(warning);}},10000);
 }
 window.Project2Session={expired};
})();
