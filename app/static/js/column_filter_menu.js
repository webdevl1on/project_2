/* Shared checkbox-value menu used by staff and calendar tables. */
((root,factory)=>{const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else Object.assign(root.TableColumns ||= {},api);})(globalThis,()=>{
 'use strict';
 function filterValues(initial,available,checked){return [...new Set([...initial.filter(v=>!available.includes(v)),...checked])];}
 function bindValueFilter(menu,{initialValues=[],onApply}){
  const boxes=()=>[...menu.querySelectorAll('input[type=checkbox]')];
  const restore=()=>boxes().forEach(input=>input.checked=initialValues.includes(input.value));
  menu.querySelector('.filter-search').addEventListener('input',event=>{const query=event.target.value.trim().toLocaleLowerCase('uk');menu.querySelectorAll('.filter-option').forEach(option=>option.hidden=!option.textContent.toLocaleLowerCase('uk').includes(query));});
  menu.querySelector('.select-all-filter').addEventListener('click',()=>boxes().filter(input=>!input.closest('.filter-option').hidden).forEach(input=>input.checked=true));
  menu.querySelector('.deselect-filter').addEventListener('click',()=>boxes().forEach(input=>input.checked=false));
  menu.querySelector('.clear-filter').addEventListener('click',()=>onApply([]));
  menu.querySelector('.apply-filter').addEventListener('click',()=>onApply(filterValues(initialValues,boxes().map(input=>input.value),boxes().filter(input=>input.checked).map(input=>input.value))));
  menu.querySelector('.cancel-filter').addEventListener('click',()=>{restore();bootstrap.Dropdown.getOrCreateInstance(menu.closest('.dropdown').querySelector('[data-bs-toggle=dropdown]')).hide();});
  menu.closest('.dropdown').addEventListener('hidden.bs.dropdown',restore);restore();
  return {update(values,options){initialValues=values;const container=menu.querySelector('.filter-options');container.replaceChildren();for(const option of options){const label=document.createElement('label'),input=document.createElement('input');label.className='dropdown-item-text d-block filter-option';input.type='checkbox';input.value=option.value;label.append(input,document.createTextNode(' '+option.label));container.append(label);}restore();menu.querySelector('.filter-search').dispatchEvent(new Event('input'));}};
 }
 return {bindValueFilter,filterValues};
});
