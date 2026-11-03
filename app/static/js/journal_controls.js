/* Calendar navigation and journal-only layout preferences; no personnel writes. */
((root, factory) => { const api=factory(); if(typeof module==='object'&&module.exports)module.exports=api;else root.JournalControls=api; })(globalThis,()=>{
    'use strict';
    const MONTHS=['Січень','Лютий','Березень','Квітень','Травень','Червень','Липень','Серпень','Вересень','Жовтень','Листопад','Грудень'];
    function monthRange(year,month){
        if(!Number.isInteger(year)||year<1||year>9999||!Number.isInteger(month)||month<1||month>12)throw Error('Оберіть коректні місяць і рік.');
        const leap=year%4===0&&(year%100!==0||year%400===0),days=[31,leap?29:28,31,30,31,30,31,31,30,31,30,31][month-1];
        const prefix=String(year).padStart(4,'0')+'-'+String(month).padStart(2,'0')+'-';return {start:prefix+'01',end:prefix+days};
    }
    function shiftDay(value,delta){const date=new Date(value+'T12:00:00Z');if(!/^\d{4}-\d{2}-\d{2}$/.test(value)||Number.isNaN(date.valueOf())||value.startsWith('0000')||date.toISOString().slice(0,10)!==value)throw Error('Введіть повну календарну дату ДД.ММ.РРРР.');date.setUTCDate(date.getUTCDate()+delta);const result=date.toISOString().slice(0,10);if(!/^\d{4}-/.test(result)||result.startsWith('0000'))throw Error('Дата поза межами календаря.');return result;}
    function initialise(model){
        const form=document.querySelector('[data-journal-filters]'),table=document.querySelector('.event-timeline');
        if(!form||!table)return;
        const key='project2:event-journal:layout:v1',extras={row_number:48,position_number:90,position_short:180};
        let saved={};try{saved=JSON.parse(localStorage.getItem(key))||{};}catch{/* Defaults if storage is unavailable. */}
        let width=Number(saved.nameWidth);width=Number.isFinite(width)?Math.max(100,Math.min(600,width)):172;
        const keys=[...table.querySelectorAll('thead th[data-column-key]')].map(th=>th.dataset.columnKey);
        const labels=Object.fromEntries(model.columns.map(c=>[c.key,c.label]));
        const columns=keys.map(key=>({key,label:labels[key],system:key==='row_number',informational:key!=='row_number',draggable:key!=='row_number',resizable:false,default_visible:!Object.hasOwn(extras,key),width:key==='name'?width:key==='unit'?112:extras[key]||58,min_width:key==='name'?100:40}));
        const modelColumns=new TableColumns.ColumnModel({id:'event-journal',groups:[{columns}]}),state={layout:modelColumns.normalise({order:saved.order,visible:keys}),widths:modelColumns.widths({name:width})};
        const store=()=>{try{localStorage.setItem(key,JSON.stringify({nameWidth:width,order:state.layout.order,wrap:document.querySelector('[data-journal-wrap]').checked,selectionMode:document.querySelector('[data-selection-mode]').value,columns:Object.fromEntries([...document.querySelectorAll('[data-journal-column]')].map(el=>[el.dataset.journalColumn,el.checked]))}));}catch{/* Current session still works. */}};
        let interactions;
        const filterAdapter=new TableColumns.QueryFilterAdapter({keys:Object.keys(model.facets),column_keys:Object.fromEntries(model.columns.filter(c=>c.filter_key).map(c=>[c.filter_key,c.key]))});
        function layout(){
            const visible=keys.filter(key=>!Object.hasOwn(extras,key)||document.querySelector(`[data-journal-column="${key}"]`).checked);
            state.layout={order:modelColumns.normalise(state.layout).order,visible:[]};state.layout.visible=state.layout.order.filter(key=>visible.includes(key));
            for(const row of table.rows){const cells=new Map([...row.children].filter(c=>c.dataset.columnKey).map(c=>[c.dataset.columnKey,c]));const ordered=state.layout.order.map(key=>cells.get(key)).filter(Boolean);for(const cell of ordered)cell.hidden=!visible.includes(cell.dataset.columnKey);const existing=[...row.children].filter(c=>c.dataset.columnKey);if(existing.some((cell,index)=>cell!==ordered[index]))for(const cell of ordered)row.append(cell);}
            for(const cell of table.querySelectorAll('[data-journal-empty]'))cell.colSpan=visible.length;
            state.widths.name=width;table.style.setProperty('--journal-name-width',width+'px');
            interactions?.renderWidths();
        }
        for(const input of document.querySelectorAll('[data-journal-column]')){input.checked=saved.columns?.[input.dataset.journalColumn]===true;input.addEventListener('change',()=>{controller.selection?.clear();layout();store();filterAdapter.navigate(filterAdapter.withVisible(state.layout.visible,filterAdapter.read()));});}
        const preferences=new TableColumns.LocalTableStorage('event-journal');
        const controller={table,config:{id:'event-journal',dragHandleSelector:'.journal-column-heading>[data-journal-sort]',textSelection:true,cellClipboardShortcuts:true},model:modelColumns,state,picker:document.querySelector('[data-journal-copy-tools]'),storage:{save:store,read:(...args)=>preferences.read(...args),write:(...args)=>preferences.write(...args)},getLayout:()=>structuredClone(state.layout),commitLayout:next=>{state.layout=modelColumns.normalise(next);layout();store();}};
        const mode=controller.picker.querySelector('[data-selection-mode]');mode.value=['text','cells','rows','columns'].includes(saved.selectionMode)?saved.selectionMode:'text';
        controller.selection=new TableColumns.TableSelection(controller);table.dataset.journalSelection=mode.value;
        mode.addEventListener('change',()=>{controller.selection.clear();table.dataset.journalSelection=mode.value;store();});
        const wrap=document.querySelector('[data-journal-wrap]');wrap.checked=saved.wrap===true;table.classList.toggle('event-journal-wrap',wrap.checked);wrap.addEventListener('change',()=>{table.classList.toggle('event-journal-wrap',wrap.checked);store();});
        const menus=new Map();for(const menu of document.querySelectorAll('[data-journal-filter-key]')){const key=menu.dataset.journalFilterKey;menus.set(key,TableColumns.bindValueFilter(menu,{initialValues:model.active_filters[key]||[],onApply:values=>{const filters=filterAdapter.read();filters.values[key]=values;filterAdapter.navigate(filters);}}));}
        document.addEventListener('journal:model',event=>{model=event.detail;for(const [key,menu] of menus)menu.update(model.active_filters[key]||[],model.facets[key]||[]);});
        const cleanURL=new URL(location.href);for(const key of [...cleanURL.searchParams.keys()])if(key.startsWith('jf_')&&!Object.hasOwn(model.facets,key))cleanURL.searchParams.delete(key);if(cleanURL.href!==location.href){cleanURL.searchParams.set('filter_order',model.filter_order.join(','));history.replaceState(null,'',cleanURL);}
        document.querySelectorAll('[data-journal-select-column]').forEach(button=>button.addEventListener('click',event=>{mode.value='columns';mode.dispatchEvent(new Event('change'));bootstrap.Dropdown.getOrCreateInstance(button.closest('.dropdown').querySelector('[data-bs-toggle=dropdown]')).hide();controller.selection.selectColumn(button.dataset.journalSelectColumn,event);}));
        function snapshot(value){try{shiftDay(value,0);const url=new URL(location.href);url.searchParams.set('as_of',value);location.assign(url.href);}catch(error){const input=form.querySelector('[data-exact-date-for=as_of]');input.setCustomValidity(error.message);input.reportValidity();}}
        for(const button of document.querySelectorAll('[data-staff-day]'))button.addEventListener('click',()=>{try{snapshot(shiftDay(form.elements.as_of.value,Number(button.dataset.staffDay)));}catch(error){const input=form.querySelector('[data-exact-date-for=as_of]');input.setCustomValidity(error.message);input.reportValidity();}});
        document.querySelector('[data-staff-today]').addEventListener('click',async event=>{const button=event.currentTarget;button.disabled=true;try{const url=new URL(location.href);url.searchParams.delete('as_of');const response=await fetch('/events/data'+url.search,{cache:'no-store'}),data=await response.json();if(!response.ok)throw Error(data.detail || 'Не вдалося отримати поточну дату.');snapshot(data.today);}catch(error){const message=document.querySelector('[data-journal-message]');message.textContent=error.message;message.className='alert alert-warning';}finally{button.disabled=false;}});
        form.elements.as_of.addEventListener('change',()=>{if(form.elements.as_of.value && form.elements.as_of.value!==model.options.as_of)snapshot(form.elements.as_of.value);});
        table.querySelector('.event-name-resizer').dataset.columnResize='name';
        interactions=new TableColumns.ColumnInteractions(controller);
        const resizer=table.querySelector('.event-name-resizer');
        resizer.draggable=false;
        resizer.addEventListener('click',e=>e.stopPropagation());
        resizer.addEventListener('pointerdown',e=>{if(e.button!==0)return;e.preventDefault();e.stopPropagation();const x=e.clientX,initial=width;interactions.resizing={key:'name'};table.classList.add('column-resizing');resizer.setPointerCapture(e.pointerId);resizer.classList.add('is-resizing');const move=event=>{width=Math.max(100,Math.min(600,initial+event.clientX-x));layout();};const finish=()=>{interactions.resizing=null;interactions.suppressUntil=Date.now()+200;table.classList.remove('column-resizing');resizer.removeEventListener('pointermove',move);resizer.removeEventListener('pointerup',finish);resizer.removeEventListener('pointercancel',finish);resizer.removeEventListener('lostpointercapture',finish);resizer.classList.remove('is-resizing');store();};resizer.addEventListener('pointermove',move);resizer.addEventListener('pointerup',finish);resizer.addEventListener('pointercancel',finish);resizer.addEventListener('lostpointercapture',finish);});
        resizer.addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight'].includes(e.key))return;e.preventDefault();width=Math.max(100,Math.min(600,width+(e.key==='ArrowLeft'?-10:10)));layout();store();});
        document.addEventListener('journal:rendered',()=>{controller.selection.clear();layout();});layout();filterAdapter.navigate(filterAdapter.withVisible(state.layout.visible,filterAdapter.read()),{replace:true});
        const month=document.querySelector('[data-month-select]'),year=document.querySelector('[data-month-year]');
        MONTHS.forEach((label,index)=>month.add(new Option(label,String(index+1))));
        year.value=Number(model.options.start.slice(0,4));month.value=Number(model.options.start.slice(5,7));
        document.querySelector('[data-month-title]').textContent=MONTHS[+month.value-1]+' '+year.value+' ▾';
        function apply(y,m){try{const range=monthRange(y,m);form.elements.start.value=range.start;form.elements.end.value=range.end;year.setCustomValidity('');form.requestSubmit();}catch(error){year.setCustomValidity(error.message);year.reportValidity();}}
        document.querySelector('[data-month-apply]').addEventListener('click',()=>apply(+year.value,+month.value));
        for(const button of document.querySelectorAll('[data-month-step]'))button.addEventListener('click',()=>{let y=+model.options.start.slice(0,4),m=+model.options.start.slice(5,7)+Number(button.dataset.monthStep);if(m===0){m=12;y--;}if(m===13){m=1;y++;}apply(y,m);});
        year.addEventListener('input',()=>year.setCustomValidity(''));
    }
    return {monthRange,shiftDay,initialise};
});
