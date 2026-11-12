/* Labels and search come only from authorized matrix metadata; submitted values stay IDs. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.AccessChoices=api;})(globalThis,()=>{
 const normal=value=>String(value).normalize('NFC').toLocaleLowerCase('uk');
 function units(rows){const nodes=new Map(rows.filter(r=>r.scope_type==='unit').map(r=>[r.key,r]));return [...nodes.values()].filter(r=>!r.manageable||r.manageable.length).map(row=>{const parts=[],seen=new Set();let current=row;while(current&&!seen.has(current.key)){seen.add(current.key);parts.unshift(current.label);current=nodes.get(current.parent);}return {id:row.id,label:parts.join(' / ')};});}
 function filter(options,query){const key=normal(query).trim();return options.filter(o=>normal(o.label).includes(key));}
 function mount(root,key){const select=root.querySelector(`[data-access-choice="${key}"]`),search=root.querySelector(`[data-access-choice-search="${key}"]`);if(!select)return {update(){}};let options=[];
  const render=()=>{const previous=select.value;select.replaceChildren(new Option(key==='template'?'Виберіть шаблон':'Виберіть підрозділ',''));for(const item of filter(options,search.value))select.add(new Option(item.label,item.id));select.value=[...select.options].some(o=>o.value===previous)?previous:'';};
  search.addEventListener('input',render);return {update(next){options=next;render();}};
 }
 return {units,filter,mount};
});
