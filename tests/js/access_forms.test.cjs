const test=require('node:test'),assert=require('node:assert/strict');
const choices=require('../../app/static/js/access_choices.js'),dateTime=require('../../app/static/js/profile_datetimes.js');
test('authorized units retain stable IDs and disambiguate duplicate names by their full paths',()=>{
 const rows=[{key:'unit:1',id:1,scope_type:'unit',label:'1 батальйон',parent:null},{key:'unit:2',id:2,scope_type:'unit',label:'2 рота',parent:'unit:1'},{key:'unit:3',id:3,scope_type:'unit',label:'3 взвод',parent:'unit:2'},{key:'unit:4',id:4,scope_type:'unit',label:'2 батальйон',parent:null},{key:'unit:5',id:5,scope_type:'unit',label:'3 взвод',parent:'unit:4'},{key:'unit:6',id:6,scope_type:'unit',label:'Лише контекст',parent:'unit:1',manageable:[]},{key:'position:9',id:9,scope_type:'position',label:'Посада'}];
 const options=choices.units(rows);assert.deepEqual(options.find(o=>o.id===3),{id:3,label:'1 батальйон / 2 рота / 3 взвод'});assert.equal(options.find(o=>o.id===5).label,'2 батальйон / 3 взвод');assert.ok(!options.some(o=>o.id===6||o.id===9));
 assert.deepEqual(choices.filter(options,'1 БАТАЛЬЙОН / 2 РОТА / 3'),[{id:3,label:'1 батальйон / 2 рота / 3 взвод'}]);
});
test('local date/time UI yields the same timezone-free datetime-local contract',()=>{
 assert.equal(dateTime.compose('29.02.2024','09:05'),'2024-02-29T09:05');assert.equal(dateTime.compose('01.12.2026','00:00'),'2026-12-01T00:00');assert.equal(dateTime.compose('31.12.2026','23:59'),'2026-12-31T23:59');assert.equal(dateTime.compose('',''),'');
 for(const [day,time] of [['29.02.2025','09:00'],['01.01.2026','24:00'],['01.01.2026','09:60'],['01.01.2026','9:30'],['01.01.2026',''],['','09:00']])assert.throws(()=>dateTime.compose(day,time));
});
