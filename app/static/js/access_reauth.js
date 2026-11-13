/* Reuse the existing password + MFA flow; keep the live ACL DOM and never replay a write. */
(()=>{
 const root=document.querySelector('[data-access-admin],[data-mfa-reauth-root]'),modal=document.querySelector('[data-access-reauth]');if(!root||!modal)return;
 const frame=modal.querySelector('iframe');let waiting=false;
 function show(){if(waiting)return;waiting=true;frame.src='/account/security?reauth=1';bootstrap.Modal.getOrCreateInstance(modal).show();}
 modal.addEventListener('hidden.bs.modal',()=>{waiting=false;frame.removeAttribute('src');});
 document.addEventListener('project2:mfa-required',event=>{if(new URL(event.detail.url,location.href).pathname.startsWith(root.dataset.mfaReauthPrefix||'/admin/access/')){event.preventDefault();show();}});
 window.addEventListener('message',event=>{
  if(!waiting||event.origin!==location.origin||event.source!==frame.contentWindow||event.data?.type!=='project2:mfa-confirmed')return;
  bootstrap.Modal.getInstance(modal)?.hide();
  const notice=root.querySelector('[data-access-message]');notice.textContent='Особу підтверджено. Чернетка збережена. Перевірте дані та повторно підтвердьте операцію.';notice.hidden=false;
  const error=root.querySelector('[data-access-error]');if(error)error.hidden=true;
 });
 root.addEventListener('access:reauth-needed',show);
})();
