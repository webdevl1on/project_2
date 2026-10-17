const { test } = require('node:test');
const assert = require('node:assert/strict');
const { ColumnModel, LocalTableStorage, LocalPresetStorage, PresetManager, DuplicatePresetName } = require('../../app/static/js/table_state.js');
const config = { id: 'a', groups: [{key:'info',label:'Дані',columns:[
    { key:'number', label:'№', system:true, informational:false, default_visible:true },
    { key:'title', label:'Назва', informational:true, default_visible:true },
    { key:'code', label:'Код', informational:true, default_visible:false },
]}] };
function setup(id = 'a', backend = new Map()) {
    const memory = { getItem: key => backend.get(key) ?? null, setItem: (key,value) => backend.set(key,value) };
    const storage = new LocalTableStorage(id, () => {}, () => memory);
    const model = new ColumnModel(config);
    return { model, storage, backend, manager: new PresetManager(id, model, new LocalPresetStorage(storage)) };
}
test('normalisation fixes system column, removes unknowns and keeps order', () => {
    const {model} = setup();
    assert.deepEqual(model.normalise({visible:['code','title'], order:['code','number','removed','code','title']}),
        {visible:['number','code','title'], order:['number','code','title']});
    assert.deepEqual(model.defaults.visible, ['number','title']);
});
test('legacy visibility migrates without losing settings and locks numbering', () => {
    const {model,storage,backend} = setup();
    backend.set('project2:table-columns:a', JSON.stringify({version:1,visibility:{number:false,title:false,code:true}}));
    assert.deepEqual(storage.load(model).layout.visible, ['number','code']);
    storage.save({layout: model.defaults, widths:{title:200}});
    assert.equal(storage.load(model).widths.title, 200);
});
test('corrupt/empty current layouts fall back to safe defaults', () => {
    const {model,storage,backend} = setup();
    for (const raw of ['bad','null', JSON.stringify({version:2,layout:null}),JSON.stringify({version:2,layout:{visible:[]}})]) {
        backend.set('project2:table-columns:a',raw);
        assert.deepEqual(storage.load(model).layout, model.defaults);
    }
});
test('presets store IDs, table identity, format and ordered visible keys only', async () => {
    const {manager} = setup();
    const saved = await manager.save({name:'  Мій   набір  ',columns:['code','title']});
    assert.equal(saved.name, 'Мій набір');
    assert.deepEqual(saved.columns,['number','code','title']);
    assert.equal(saved.table_id,'a');
    assert.equal(saved.version,1);
    assert.ok(saved.id);
    assert.deepEqual(Object.keys(saved).sort(), ['columns','id','name','table_id','version']);
});
test('empty/long names rejected; duplicates require explicit overwrite preserving ID', async () => {
    const {manager} = setup();
    for (const name of ['','   ','x'.repeat(31)]) await assert.rejects(manager.save({name,columns:['title']}));
    const first = await manager.save({name:'Назва', columns:['title']});
    await assert.rejects(manager.save({name:'назва',columns:['code']}),DuplicatePresetName);
    assert.deepEqual((await manager.list())[0].columns,first.columns);
    const replaced = await manager.save({name:'НАЗВА',columns:['code']},{replaceId:first.id});
    assert.equal(replaced.id,first.id);
    assert.equal((await manager.list()).length,1);
    assert.deepEqual(replaced.columns,['number','code']);
});
test('rename and delete are isolated by table; no automatic preset mutation on preview', async () => {
    const a = setup(), b = setup('b',a.backend);
    const original = await a.manager.save({name:'Набір',columns:['title']});
    await b.manager.save({name:'Набір',columns:['code']});
    a.manager.preview(original).layout.visible.push('code');
    assert.deepEqual((await a.manager.list())[0],original);
    await a.manager.save({...original,name:'Інша назва'});
    assert.equal((await a.manager.list())[0].id,original.id);
    await a.manager.remove(original.id);
    assert.equal((await a.manager.list()).length,0);
    assert.equal((await b.manager.list()).length,1);
});
test('obsolete keys reported, usable keys applied, unusable preset rejected', () => {
    const {manager} = setup();
    const preset = {version:1,columns:['old','title']};
    assert.deepEqual(manager.preview(preset).missing,['old']);
    assert.deepEqual(manager.preview(preset).layout.visible,['number','title']);
    assert.deepEqual(preset.columns,['old','title']);
    assert.throws(() => manager.preview({version:1,columns:['old','number']}),/інформаційних/);
    assert.throws(() => manager.preview({version:99,columns:['title']}),/формату/);
});
test('presets without information and failed persistence do not report successful save', async () => {
    const {manager,storage} = setup();
    await assert.rejects(manager.save({name:'Без даних',columns:['number']}),/інформаційну/);
    storage.write = () => false;
    await assert.rejects(manager.save({name:'Набір',columns:['title']}),/зберегти/);
});
test('widths are finite and clamped; system numbering cannot be hidden by saved layout', () => {
    const {model} = setup();
    const widths = model.widths({title:-1,code:0,number:NaN});
    assert.equal(widths.title,100);
    assert.equal(widths.code,100);
    assert.equal(widths.number,56);
    assert.equal(model.widths({title:Infinity}).title,180);
    assert.equal(model.widths({title:100000}).title,4096);
    assert.deepEqual(model.normalise({visible:['title'],order:['title','number']}).visible,['number','title']);
});
test('UUID fallback works without secure-context randomUUID',()=>{
    const {createPresetId}=require('../../app/static/js/table_state.js');
    const id=createPresetId({getRandomValues(bytes){bytes.fill(1);return bytes;}});
    assert.match(id,/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
});
test('preset storage imposes no preset-count limit',async()=>{
    const {manager}=setup();
    for(let n=0;n<40;n++) await manager.save({name:`Набір ${n}`,columns:['title']});
    assert.equal((await manager.list()).length,40);
});
