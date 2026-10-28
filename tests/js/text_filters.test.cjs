const test=require('node:test');const assert=require('node:assert/strict');
const {QueryFilterAdapter}=require('../../app/static/js/table_filters.js');
test('contains filters belong to their visible source column and retain history URL values',()=>{
 const adapter=new QueryFilterAdapter({keys:['surname','surname__contains'],column_keys:{surname__contains:'surname'}},{href:'http://example.invalid/person-positions?surname__contains=Миколаї'});
 const state=adapter.read();assert.deepEqual(adapter.withVisible(['surname'],state).values,{surname__contains:['Миколаї']});
 assert.deepEqual(adapter.withVisible([],state).values,{});
 assert.equal(adapter.urlFor(state).searchParams.get('surname__contains'),'Миколаї');
});
