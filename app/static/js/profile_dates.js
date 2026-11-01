/* Exact calendar dates at the UI boundary; original named controls remain ISO. */
((root,factory)=>{
 const api=factory();
 if(typeof module==='object'&&module.exports)module.exports=api;
 else{root.ProfileDates=api;api.enhance(document);new MutationObserver(records=>{for(const r of records)for(const n of r.addedNodes)if(n.nodeType===1)api.enhance(n);}).observe(document.body,{childList:true,subtree:true});}
})(globalThis,()=>{
 'use strict';
 function valid(day,month,year){const leap=year%4===0&&(year%100!==0||year%400===0);return year>=1&&year<=9999&&month>=1&&month<=12&&day>=1&&day<=[31,leap?29:28,31,30,31,30,31,31,30,31,30,31][month-1];}
 function parse(value){if(!value)return '';const m=/^(\d{2})\.(\d{2})\.(\d{4})$/.exec(value);if(!m||!valid(+m[1],+m[2],+m[3]))throw Error('Введіть коректну повну дату ДД.ММ.РРРР.');return `${m[3]}-${m[2]}-${m[1]}`;}
 function format(value){if(!value)return '';const m=/^(\d{4})-(\d{2})-(\d{2})$/.exec(value);if(!m||!valid(+m[3],+m[2],+m[1]))return String(value);return `${m[3]}.${m[2]}.${m[1]}`;}
 function display(value){if(Array.isArray(value))return value.map(display);if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,display(v)]));return typeof value==='string'?format(value):value;}
 let sequence=0;
 function enhance(scope){
  globalThis.TableDates?.initialiseDateInputs?.(scope);
  const inputs=[...(scope.matches?.('input[type=date]')?[scope]:[]),...scope.querySelectorAll('input[type=date]:not([data-date-calendar])')];
  for(const canonical of inputs){
   if(canonical.dataset.dateCalendar!==undefined||canonical.dataset.exactDateCanonical!==undefined)continue;
   const text=document.createElement('input'),button=document.createElement('button'),calendar=document.createElement('input'),wrapper=document.createElement('span');
   wrapper.className='profile-exact-date d-flex gap-1 align-items-center position-relative';canonical.before(wrapper);wrapper.append(canonical,text,button,calendar);
   text.type='text';text.className=canonical.className||'form-control';text.placeholder='ДД.ММ.РРРР';text.inputMode='numeric';text.maxLength=10;text.autocomplete='off';text.dataset.exactDateFor=canonical.name;
   const id=canonical.id||`profile-date-${++sequence}`;text.id=id+'-display';
   for(const label of document.querySelectorAll('label[for]'))if(label.htmlFor===canonical.id&&canonical.id)label.htmlFor=text.id;
   const label=canonical.getAttribute('aria-label');text.setAttribute('aria-label',label||canonical.closest('label')?.textContent.trim()||'Дата ДД.ММ.РРРР');
   button.type='button';button.className='btn btn-outline-secondary';button.textContent='▦';button.setAttribute('aria-label','Вибрати дату в календарі');button.title='Вибрати дату в календарі';
   calendar.type='date';calendar.dataset.dateCalendar='';calendar.tabIndex=-1;calendar.setAttribute('aria-label','Календар');calendar.style.cssText='position:absolute;width:1px;height:1px;opacity:0;right:0;bottom:0;';
   canonical.dataset.exactDateCanonical='';canonical.type='hidden';
   const descriptor=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value');
   const sync=()=>{text.value=format(descriptor.get.call(canonical));text.required=canonical.required;text.disabled=canonical.disabled;text.readOnly=canonical.readOnly;button.disabled=canonical.disabled||canonical.readOnly;text.setCustomValidity('');calendar.value=descriptor.get.call(canonical);calendar.min=canonical.min;calendar.max=canonical.max;};
   Object.defineProperty(canonical,'value',{configurable:true,get(){return descriptor.get.call(this);},set(value){descriptor.set.call(this,value??'');sync();}});
   function entered(){try{const iso=parse(text.value);if(iso&&((canonical.min&&iso<canonical.min)||(canonical.max&&iso>canonical.max)))throw Error('Дата поза дозволеним діапазоном.');descriptor.set.call(canonical,iso);text.setCustomValidity('');calendar.value=iso;canonical.dispatchEvent(new Event('input',{bubbles:true}));canonical.dispatchEvent(new Event('change',{bubbles:true}));}catch(error){descriptor.set.call(canonical,'');text.setCustomValidity(error.message);}}
   text.addEventListener('input',entered);text.addEventListener('change',entered);
   button.addEventListener('click',()=>{calendar.value=canonical.value;if(calendar.showPicker)calendar.showPicker();else{calendar.style.cssText='';calendar.focus();}});
   calendar.addEventListener('change',()=>{canonical.value=calendar.value;canonical.dispatchEvent(new Event('input',{bubbles:true}));canonical.dispatchEvent(new Event('change',{bubbles:true}));});
   canonical.addEventListener('change',()=>{if(text.validationMessage==='')sync();});
   canonical.form?.addEventListener('reset',()=>setTimeout(sync,0));canonical.form?.addEventListener('profile:reset',sync);
   canonical.focus=options=>text.focus(options);
   new MutationObserver(()=>{text.required=canonical.required;text.disabled=canonical.disabled;text.readOnly=canonical.readOnly;button.disabled=canonical.disabled||canonical.readOnly;}).observe(canonical,{attributes:true,attributeFilter:['required','disabled','readonly','min','max']});sync();
  }
 }
 return {parse,format,display,valid,enhance};
});
