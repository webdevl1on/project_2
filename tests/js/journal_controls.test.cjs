const {test}=require('node:test');const assert=require('node:assert/strict');
const {monthRange}=require('../../app/static/js/journal_controls.js');
test('month boundaries cover leap years and century calendar rules',()=>{
 assert.deepEqual(monthRange(2024,2),{start:'2024-02-01',end:'2024-02-29'});
 assert.equal(monthRange(2026,2).end,'2026-02-28');assert.equal(monthRange(1900,2).end,'1900-02-28');assert.equal(monthRange(2000,2).end,'2000-02-29');
 assert.equal(monthRange(2026,11).end,'2026-11-30');assert.equal(monthRange(9999,12).end,'9999-12-31');assert.equal(monthRange(1,1).start,'0001-01-01');
});
test('month selection rejects impossible years and months',()=>{for(const [y,m] of [[0,1],[10000,1],[2026,0],[2026,13],[2026,1.5],[NaN,1]])assert.throws(()=>monthRange(y,m));});
const {shiftDay}=require('../../app/static/js/journal_controls.js');
test('staff day navigation crosses month/year/leap boundaries without DST arithmetic',()=>{
 assert.equal(shiftDay('2026-12-31',1),'2027-01-01');assert.equal(shiftDay('2026-03-01',-1),'2026-02-28');assert.equal(shiftDay('2024-03-01',-1),'2024-02-29');assert.equal(shiftDay('2026-10-25',1),'2026-10-26');
 for(const value of ['2026-02-30','_.03.2026','0000-01-01'])assert.throws(()=>shiftDay(value,1));assert.throws(()=>shiftDay('0001-01-01',-1));assert.throws(()=>shiftDay('9999-12-31',1));
});
const {filterValues}=require('../../app/static/js/column_filter_menu.js');
test('shared filter menu preserves values outside current cascade and removes unchecked available values',()=>{
 assert.deepEqual(filterValues(['hidden','available'],['available','new'],['new','new']),['hidden','new']);assert.deepEqual(filterValues([],['a','b'],['a','b']),['a','b']);
});
