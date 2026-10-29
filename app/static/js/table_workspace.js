/* Layout-only behaviour; no personnel requests or business decisions. */
(() => {
    'use strict';
    if(matchMedia('(max-width:600px)').matches)document.querySelectorAll('[data-table-filters]').forEach(panel=>panel.open=false);
    document.querySelectorAll('.table-viewport').forEach(viewport=>{
        const measure=()=>viewport.style.setProperty('--viewport-top',`${Math.max(0,viewport.getBoundingClientRect().top)}px`);
        measure();window.addEventListener('resize',measure);document.addEventListener('toggle',()=>requestAnimationFrame(measure),true);
        new ResizeObserver(measure).observe(document.body);
        // Native top-layer popovers retain DOM ancestry/listeners and escape overflow clipping.
        viewport.querySelectorAll('[data-bs-toggle="dropdown"]').forEach(toggle=>{
            const menu=toggle.parentElement.querySelector(':scope > .dropdown-menu');if(!menu)return;
            let openedScroll=null;
            const close=()=>{if(typeof menu.hidePopover==='function'&&menu.matches(':popover-open'))menu.hidePopover();menu.classList.remove('table-floating-menu');};
            toggle.addEventListener('shown.bs.dropdown',()=>{
                openedScroll=[viewport.scrollLeft,viewport.scrollTop];
                menu.classList.add('table-floating-menu');
                if(typeof menu.showPopover==='function'){menu.setAttribute('popover','manual');menu.showPopover();}
                const rect=toggle.getBoundingClientRect(),width=menu.getBoundingClientRect().width,height=menu.getBoundingClientRect().height;
                const left=Math.max(6,Math.min(rect.left,innerWidth-width-6));
                const below=rect.bottom+height<=innerHeight-8;
                const top=below?rect.bottom+3:Math.max(6,rect.top-height-3);
                menu.style.setProperty('left',`${left}px`,'important');menu.style.setProperty('top',`${top}px`,'important');
                menu.style.setProperty('max-height',`${Math.max(80,Math.min(innerHeight-12,below?innerHeight-top-8:rect.top-8))}px`,'important');
            });
            toggle.addEventListener('hidden.bs.dropdown',close);
            viewport.addEventListener('scroll',()=>{
                // An automatic scroll bringing the toggle into view can be delivered after
                // shown.bs.dropdown. It must not immediately close the newly opened menu.
                if(openedScroll&&(viewport.scrollLeft!==openedScroll[0]||viewport.scrollTop!==openedScroll[1]))bootstrap.Dropdown.getInstance(toggle)?.hide();
            });
            window.addEventListener('resize',()=>bootstrap.Dropdown.getInstance(toggle)?.hide());
        });
    });
    const table=document.querySelector('#person-positions');if(!table)return;
    let opened=null;
    const editor=row=>row.querySelector('[data-assignment-editor]');
    const button=row=>row.querySelector('[data-assignment-toggle]');
    function collapse(row){editor(row).hidden=true;row.classList.remove('assignment-editing');button(row).setAttribute('aria-expanded','false');}
    function open(row){if(opened&&opened!==row)collapse(opened);editor(row).hidden=false;row.classList.add('assignment-editing');button(row).setAttribute('aria-expanded','true');opened=row;}
    table.querySelectorAll('[data-assignment-editor]').forEach(node=>{
        const row=node.closest('tr'),snapshots=new Map();
        const values=form=>JSON.stringify([...new FormData(form)].filter(([key])=>key!=='token'));
        node.querySelectorAll('form').forEach(form=>snapshots.set(form,values(form)));
        const dirty=()=>{const changed=[...snapshots].some(([form,value])=>values(form)!==value);row.dataset.assignmentDirty=String(changed);row.querySelector('[data-assignment-draft]').hidden=!changed;};
        for(const event of ['input','change','personpicked'])node.addEventListener(event,dirty);
        node.querySelector('[data-assignment-close]').addEventListener('click',()=>{collapse(row);opened=null;});
        node.querySelector('[data-assignment-cancel]').addEventListener('click',()=>{
            if(row.dataset.assignmentDirty==='true'&&!window.confirm('Скасувати незбережені зміни цієї форми?'))return;
            node.querySelectorAll('form').forEach(form=>{
                form.reset();const original=new Map(JSON.parse(snapshots.get(form)));
                // Hidden inputs reflect .value into their defaultValue, unlike text/date inputs.
                // Restore their original snapshot explicitly (and discard prepared tokens).
                [...form.elements].filter(input=>input.type==='hidden').forEach(input=>input.value=original.get(input.name)||'');
            });
            node.querySelectorAll('[data-assignment-status],[data-personnel-message]').forEach(status=>status.textContent='');
            queueMicrotask(()=>{dirty();collapse(row);opened=null;});
        });
    });
    table.addEventListener('click',event=>{
        const cell=event.target.closest('td[data-column-key="assignment"]');if(!cell)return;
        const row=cell.closest('tr');
        if(event.target.closest('[data-assignment-toggle]')){if(opened===row){collapse(row);opened=null;}else open(row);return;}
        if(!event.target.closest('a,button,input,select,textarea,form,[data-assignment-editor]'))open(row);
    });
})();
