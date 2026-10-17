const {test}=require('node:test');
const assert=require('node:assert/strict');
const {TableHistory}=require('../../app/static/js/table_history.js');
const state=n=>({layout:{visible:['number',String(n)],order:['number',String(n)]},filters:{values:{},order:[],extra:{}}});
test('history retains five snapshots and disables movement at both ends',()=>{
    const history=new TableHistory();
    for(let n=0;n<8;n++) history.push(state(n));
    assert.equal(history.entries.length,5);assert.deepEqual(history.current,state(7));
    assert.equal(history.move(1),null);
    for(let n=6;n>=3;n--) assert.deepEqual(history.move(-1),state(n));
    assert.equal(history.canBack,false);assert.equal(history.canForward,true);
    assert.equal(history.move(-1),null);assert.equal(history.move(5),null);
});
test('a new state after undo discards the future branch, consecutive duplicates ignored',()=>{
    const history=new TableHistory();[0,1,2].forEach(n=>history.push(state(n)));
    history.move(-1);history.push(state(9));
    assert.deepEqual(history.entries,[state(0),state(1),state(9)]);
    assert.equal(history.canForward,false);
    assert.equal(history.push(state(9)),false);assert.equal(history.entries.length,3);
});
test('serialised history restores its cursor and forward states after reload',()=>{
    const history=new TableHistory();[0,1,2].forEach(n=>history.push(state(n)));history.move(-1);
    const restored=new TableHistory(JSON.parse(JSON.stringify(history)));
    assert.deepEqual(restored.current,state(1));assert.deepEqual(restored.move(1),state(2));
});
test('snapshots cannot be mutated through caller-owned objects or getters',()=>{
    const history=new TableHistory(),original=state(0);history.push(original);
    original.layout.visible.push('bad');const current=history.current;current.layout.order.reverse();
    assert.deepEqual(history.current,state(0));
});
test('browser traversal seeks an existing snapshot without duplicating it',()=>{
    const history=new TableHistory();[0,1,2].forEach(n=>history.push(state(n)));
    history.seek(state(0));assert.equal(history.cursor,0);assert.equal(history.entries.length,3);
    history.seek(state(2));assert.equal(history.cursor,2);assert.equal(history.entries.length,3);
});
