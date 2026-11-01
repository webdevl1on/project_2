const assert=require('node:assert/strict');
const {test}=require('node:test');
const {readFileSync}=require('node:fs');
const vm=require('node:vm');
function api(){const context={CustomEvent:class{constructor(type,options){this.type=type;Object.assign(this,options);}},setTimeout,clearTimeout};vm.createContext(context);vm.runInContext(readFileSync('app/static/js/profile_ui.js','utf8'),context);return context.ProfileUI;}
function input(name,type,value){return {name,type,value,disabled:true,tagName:type==='select'?'SELECT':'INPUT',selectedIndex:2,checked:true,classList:{remove(){}},setCustomValidity(value){this.validityMessage=value;}};}
test('record reset clears actual fields and edit identity, preserving explicitly retained context',()=>{
 const fields=[input('name','text','Old'),input('id','hidden','43'),input('revision','hidden','9'),input('enabled','checkbox','on'),input('category','select','old'),input('csrf','hidden','token')];fields.namedItem=name=>fields.find(f=>f.name===name);
 const events=[],form={elements:fields,dataset:{key:'43',id:'43',revision:'9',originalStatus:'PLANNED',editing:'1',personId:'7'},reset(){fields.forEach(f=>f.value='Old default');},dispatchEvent(event){events.push(event);}};
 api().resetForm(form,{preserve:['csrf']});
 assert.equal(fields[0].value,'');assert.equal(fields[1].value,'');assert.equal(fields[2].value,'');assert.equal(fields[3].checked,false);assert.equal(fields[4].selectedIndex,0);assert.equal(fields[5].value,'token');
 assert.deepEqual(form.dataset,{personId:'7'});assert.ok(fields.filter(f=>f.name!=='csrf').every(f=>!f.disabled&&f.validityMessage===''));assert.equal(events[0].type,'profile:reset');assert.equal(events[0].bubbles,true);
});
test('editor visibility follows explicit new/edit and successful close',()=>{
 const ui=api(),editor={tagName:'DETAILS',hidden:true,open:false};ui.openEditor(editor);assert.equal(editor.hidden,false);assert.equal(editor.open,true);ui.closeEditor(editor);assert.equal(editor.hidden,true);assert.equal(editor.open,false);
});
