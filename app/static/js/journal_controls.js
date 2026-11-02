/* Calendar navigation and journal-only layout preferences; no personnel writes. */
((root, factory) => { const api=factory(); if(typeof module==='object'&&module.exports)module.exports=api;else root.JournalControls=api; })(globalThis,()=>{
    'use strict';
    const MONTHS=['Січень','Лютий','Березень','Квітень','Травень','Червень','Липень','Серпень','Вересень','Жовтень','Листопад','Грудень'];
    function monthRange(year,month){
        if(!Number.isInteger(year)||year<1||year>9999||!Number.isInteger(month)||month<1||month>12)throw Error('Оберіть коректні місяць і рік.');
        const leap=year%4===0&&(year%100!==0||year%400===0),days=[31,leap?29:28,31,30,31,30,31,31,30,31,30,31][month-1];
        const prefix=String(year).padStart(4,'0')+'-'+String(month).padStart(2,'0')+'-';return {start:prefix+'01',end:prefix+days};
    }
    function initialise(model){
        const form=document.querySelector('[data-journal-filters]'),table=document.querySelector('.event-timeline');
        if(!form||!table)return;
        const key='project2:event-journal:layout:v1',extras={row_number:48,position_number:90,position_short:180};
        let saved={};try{saved=JSON.parse(localStorage.getItem(key))||{};}catch{/* Defaults if storage is unavailable. */}
        let width=Number(saved.nameWidth);width=Number.isFinite(width)?Math.max(100,Math.min(600,width)):172;
        const store=()=>{try{localStorage.setItem(key,JSON.stringify({nameWidth:width,columns:Object.fromEntries([...document.querySelectorAll('[data-journal-column]')].map(el=>[el.dataset.journalColumn,el.checked]))}));}catch{/* Current session still works. */}};
        function layout(){
            let extra=0;
            for(const input of document.querySelectorAll('[data-journal-column]')){const name=input.dataset.journalColumn;for(const cell of table.querySelectorAll(`[data-journal-extra="${name}"]`)){cell.hidden=!input.checked;cell.style.width=extras[name]+'px';}if(input.checked)extra+=extras[name];}
            table.style.setProperty('--journal-name-width',width+'px');
            table.style.width=(width+112+extra+model.buckets.length*58)+'px';
        }
        for(const input of document.querySelectorAll('[data-journal-column]')){input.checked=saved.columns?.[input.dataset.journalColumn]===true;input.addEventListener('change',()=>{layout();store();});}
        const resizer=table.querySelector('.event-name-resizer');
        resizer.addEventListener('click',e=>e.stopPropagation());
        resizer.addEventListener('pointerdown',e=>{if(e.button!==0)return;e.preventDefault();e.stopPropagation();const x=e.clientX,initial=width;resizer.setPointerCapture(e.pointerId);resizer.classList.add('is-resizing');const move=event=>{width=Math.max(100,Math.min(600,initial+event.clientX-x));layout();};const finish=()=>{resizer.removeEventListener('pointermove',move);resizer.removeEventListener('pointerup',finish);resizer.removeEventListener('pointercancel',finish);resizer.classList.remove('is-resizing');store();};resizer.addEventListener('pointermove',move);resizer.addEventListener('pointerup',finish);resizer.addEventListener('pointercancel',finish);});
        resizer.addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight'].includes(e.key))return;e.preventDefault();width=Math.max(100,Math.min(600,width+(e.key==='ArrowLeft'?-10:10)));layout();store();});
        document.addEventListener('journal:rendered',layout);layout();
        const month=document.querySelector('[data-month-select]'),year=document.querySelector('[data-month-year]');
        MONTHS.forEach((label,index)=>month.add(new Option(label,String(index+1))));
        year.value=Number(model.options.start.slice(0,4));month.value=Number(model.options.start.slice(5,7));
        document.querySelector('[data-month-title]').textContent=MONTHS[+month.value-1]+' '+year.value+' ▾';
        function apply(y,m){try{const range=monthRange(y,m);form.elements.start.value=range.start;form.elements.end.value=range.end;year.setCustomValidity('');form.requestSubmit();}catch(error){year.setCustomValidity(error.message);year.reportValidity();}}
        document.querySelector('[data-month-apply]').addEventListener('click',()=>apply(+year.value,+month.value));
        for(const button of document.querySelectorAll('[data-month-step]'))button.addEventListener('click',()=>{let y=+model.options.start.slice(0,4),m=+model.options.start.slice(5,7)+Number(button.dataset.monthStep);if(m===0){m=12;y--;}if(m===13){m=1;y++;}apply(y,m);});
        year.addEventListener('input',()=>year.setCustomValidity(''));
    }
    return {monthRange,initialise};
});
