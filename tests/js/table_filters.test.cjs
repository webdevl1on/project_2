const {test}=require('node:test');
const assert=require('node:assert/strict');
const {QueryFilterAdapter}=require('../../app/static/js/table_filters.js');
const config={keys:['unit','code'],order_parameter:'filter_order',extra:{occupancy:'all'}};
test('hidden filters removed; remaining multi-values, cascade order, unrelated query and sort preserved',()=>{
    const adapter=new QueryFilterAdapter(config,{href:'http://test/table?unit=A&code=1&code=2&filter_order=unit,code&sort_by=title&direction=desc&unknown=keep&occupancy=occupied'});
    const next=adapter.withVisible(['code'],adapter.read());
    assert.deepEqual(next.values,{code:['1','2']});assert.deepEqual(next.order,['code']);
    const url=adapter.urlFor(next);
    assert.equal(url.searchParams.has('unit'),false);
    assert.equal(url.searchParams.get('filter_order'),'code');
    assert.equal(url.searchParams.get('sort_by'),'title');assert.equal(url.searchParams.get('direction'),'desc');
    assert.equal(url.searchParams.get('unknown'),'keep');assert.equal(url.searchParams.get('occupancy'),'occupied');
});
test('navigation is performed only for real filter changes and does not loop',()=>{
    let calls=0;
    const location={href:'http://test/table?unit=A',replace(url){calls++;this.href=url;},assign(url){calls++;this.href=url;}};
    const adapter=new QueryFilterAdapter(config,location);
    const next=adapter.withVisible(['code'],adapter.read());
    adapter.navigate(next,{replace:true});adapter.navigate(next,{replace:true});
    assert.equal(calls,1);assert.equal(new URL(location.href).searchParams.has('unit'),false);
});
test('normalisation handles repeated values, missing order, and malformed saved snapshots',()=>{
    const adapter=new QueryFilterAdapter(config,{href:'http://test/table?code=2&code=1&code=1&unit=A'});
    const filters=adapter.read();assert.deepEqual(filters.order,['code','unit']);
    assert.equal(adapter.equal(filters,{...filters,values:{unit:['A'],code:['1','2']}}),true);
    assert.deepEqual(adapter.normalise({values:{unit:'bad'},order:'bad'}),{values:{},order:[],extra:{occupancy:'all'}});
});
