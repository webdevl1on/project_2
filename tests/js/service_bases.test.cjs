const { test } = require('node:test');
const assert = require('node:assert/strict');
const { activeKind, mayReplace } = require('../../app/static/js/service_bases.js');
test('basis form recognizes only explicit service types', () => {
    assert.equal(activeKind('mobilization'), 'mobilization');
    assert.equal(activeKind('contract'), 'contract');
    assert.equal(activeKind('legacy text'), '');
});
test('directory suggestion requires consent before replacing document wording', () => {
    assert.equal(mayReplace('', 'Офіційна назва', () => {throw Error('unnecessary confirmation');}), true);
    assert.equal(mayReplace('Історична назва', 'Нова назва', () => false), false);
    assert.equal(mayReplace('Історична назва', 'Нова назва', () => true), true);
});
