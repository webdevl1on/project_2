const test = require('node:test');
const assert = require('node:assert/strict');
const { NameDraft } = require('../../app/static/js/name_cases.js');

test('dictionary fills an empty draft without replacing the original word', () => {
    const draft = new NameDraft('ТЕСТОСЛАВ', 'male');
    assert.equal(draft.apply({genitive:'Тестослава'}), true);
    assert.equal(draft.base, 'ТЕСТОСЛАВ');
    assert.equal(draft.forms.genitive, 'Тестослава');
    assert.equal(draft.forms.dative, '');
    assert.equal(draft.stale, false);
});
test('manual correction survives automatic lookup; overwrite needs explicit confirmation', () => {
    const draft = new NameDraft('Тестослав', 'male');
    draft.apply({genitive:'Словникового'});
    draft.edit('genitive','Особистого');
    assert.equal(draft.apply({genitive:'Словникового'}), false);
    assert.equal(draft.forms.genitive, 'Особистого');
    assert.equal(draft.apply({genitive:'Словникового'}, true), true);
    assert.equal(draft.forms.genitive, 'Словникового');
});
test('changing the word retains visible values but marks them stale until clear or explicit reuse', () => {
    const draft = new NameDraft('Тестослав','male');
    draft.apply({genitive:'Тестослава'});
    draft.identity('Інше','male');
    assert.equal(draft.stale,true);
    assert.equal(draft.apply({genitive:'Іншого'}),false);
    assert.equal(draft.forms.genitive,'Тестослава');
    draft.clear();
    assert.equal(draft.stale,false);
    assert.equal(draft.hasForms,false);
    assert.equal(draft.apply({genitive:'Іншого'}),true);
});
test('changing sex invalidates snapshots even when the spelling is identical', () => {
    const draft = new NameDraft('Сокіл','male');
    draft.apply({genitive:'Сокола'});
    draft.identity('Сокіл','female');
    assert.equal(draft.stale,true);
    draft.keep();
    assert.equal(draft.stale,false);
    assert.equal(draft.manual,true);
    assert.equal(draft.apply({genitive:'Сокіл'}),false);
});
test('restored server-error drafts remain manual and preserve their original binding', () => {
    const draft = new NameDraft('Нове','male',{genitive:'Старого'},'Старе','female');
    assert.equal(draft.stale,true);
    assert.equal(draft.apply({genitive:'Нового'}),false);
    draft.identity('Старе','female');
    assert.equal(draft.stale,false);
    assert.equal(draft.forms.genitive,'Старого');
});
test('identity and manual edits invalidate in-flight lookup revisions', () => {
    const draft = new NameDraft('Тестослав','male');
    const before = draft.revision;
    draft.edit('dative','Особистому');
    assert.notEqual(draft.revision,before);
    const pending = draft.revision;
    draft.identity('Інший','male');
    assert.notEqual(draft.revision,pending);
    assert.equal(draft.stale,true);
});
