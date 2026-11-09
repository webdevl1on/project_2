/* Bootstrap owns focus trapping/restoration, overlay, backdrop and Escape. */
(()=>{
 'use strict';const sidebar=document.getElementById('app-sidebar');if(!sidebar)return;
 const trigger=document.querySelector('[data-bs-target="#app-sidebar"]');
 sidebar.addEventListener('show.bs.offcanvas',()=>{
  trigger?.setAttribute('aria-expanded','true');
  document.querySelectorAll('[data-bs-toggle="dropdown"][aria-expanded="true"]').forEach(n=>bootstrap.Dropdown.getInstance(n)?.hide());
  document.querySelectorAll('[popover]').forEach(n=>{if(n.matches(':popover-open'))n.hidePopover();});
 });
 sidebar.addEventListener('hidden.bs.offcanvas',()=>trigger?.setAttribute('aria-expanded','false'));
 sidebar.addEventListener('click',e=>{if(e.target.closest('a[href]'))bootstrap.Offcanvas.getInstance(sidebar)?.hide();});
})();
