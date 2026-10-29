const {test}=require('node:test');
const assert=require('node:assert/strict');
const {AppearanceModel,PALETTE}=require('../../app/static/js/table_appearance.js');
test('absent/malformed appearance starts with compatible defaults',()=>{
 const model=new AppearanceModel(['name','number']);
 for(const value of [null,[],{version:99},'invalid'])assert.deepEqual(model.normalise(value),{version:1,rowHeight:40,fontSize:14,scale:100,fonts:{},fills:{}});
});
test('row height, global/column fonts and scale are constrained independently',()=>{
 const state=new AppearanceModel(['name']).normalise({version:1,rowHeight:-100,fontSize:100,scale:200,fonts:{name:80,unknown:12}});
 assert.equal(state.rowHeight,24);assert.equal(state.fontSize,28);assert.equal(state.scale,100);assert.deepEqual(state.fonts,{name:32});
 assert.equal(new AppearanceModel([]).normalise({version:1,rowHeight:Infinity}).rowHeight,40);
});
test('fills use stable record and known column keys with an allowlisted palette',()=>{
 const first=JSON.stringify(['position:501','name']),second=JSON.stringify(['person:2','name']);
 const state=new AppearanceModel(['name']).normalise({version:1,fills:{[first]:PALETTE[0],[second]:PALETTE[1],invalid:PALETTE[2],[JSON.stringify(['position:2','missing'])]:PALETTE[0],[JSON.stringify(['position:3','name'])]:'url(javascript:invalid)'}});
 assert.deepEqual(state.fills,{[first]:PALETTE[0],[second]:PALETTE[1]});
});
