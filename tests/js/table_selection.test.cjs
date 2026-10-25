const {test}=require('node:test');
const assert=require('node:assert/strict');
const {exportCells}=require('../../app/static/js/table_selection.js');
test('TSV preserves rows and quotes tabs, newlines and double quotes',()=>{
    assert.equal(exportCells([['one','two'],['a\tb','a\nb'],['"quoted"','']]).text,'one\ttwo\n"a\tb"\t"a\nb"\n"""quoted"""\t');
});
test('Word escapes markup and preserves multiline cells in real table structure',()=>{
    const data=exportCells([['<script>&"\'','one\ntwo'],['-','15._.1990']]);
    assert.match(data.html,/<table/);assert.match(data.html,/&lt;script&gt;&amp;&quot;&#39;/);
    assert.match(data.html,/one<br>two/);assert.equal((data.html.match(/<td /g)||[]).length,4);
    assert.ok(!data.html.includes('<script>'));
});
