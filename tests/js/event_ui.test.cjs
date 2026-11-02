const test = require('node:test'), assert = require('node:assert/strict');
const {csv, csvCell} = require('../../app/static/js/event_ui.js');
test('CSV preserves Ukrainian text, quotes, multiline values and UTF-8 BOM', () => {
    assert.equal(csv([['ПІБ','Період'],['Тестенко','рядок "один"\nдва']]), '\uFEFF"ПІБ";"Період"\r\n"Тестенко";"рядок ""один""\nдва"');
});
test('CSV protects spreadsheet formula-like text without executing or truncating it', () => {
    for (const value of ['=1+1','+SUM(A1)','-1','@SUM(A1)','\t=1']) assert.ok(csvCell(value).startsWith('"\''));
    assert.equal(csvCell('звичайний текст'), '"звичайний текст"');
});
