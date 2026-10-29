/* Selection uses existing keyed DOM/layout; clipboard preferences are per table. */
((root, factory) => {
    const api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    else Object.assign(root.TableColumns ||= {}, api);
})(globalThis, () => {
    'use strict';
    const escapeHTML = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
    function exportCells(matrix) {
        const quote = value => /[\t\r\n"]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value;
        return {
            text: matrix.map(row => row.map(value => quote(String(value))).join('\t')).join('\n'),
            html: '<table style="border-collapse:collapse"><tbody>' + matrix.map(row => '<tr>' + row.map(value =>
                '<td style="border:1px solid #808080;padding:4px;white-space:pre-wrap">' + escapeHTML(value).replace(/\r\n|\r|\n/g, '<br>') + '</td>').join('') + '</tr>').join('') + '</tbody></table>',
        };
    }
    function legacyCopy(payload, html) {
        const previous = document.activeElement;
        const textarea = document.createElement('textarea');
        textarea.value = payload.text;
        textarea.style.cssText = 'position:fixed;left:-10000px;top:0';
        document.body.append(textarea); textarea.select();
        let supplied = false;
        const listener = event => {
            if (!event.clipboardData) return;
            event.preventDefault();
            try {
                event.clipboardData.setData('text/plain', payload.text);
                if (html) event.clipboardData.setData('text/html', payload.html);
                supplied = !html || Array.from(event.clipboardData.types).includes('text/html');
            } catch { supplied = false; }
        };
        document.addEventListener('copy', listener);
        let success = false;
        try { success = document.execCommand('copy') && supplied; } catch { /* Report failure below. */ }
        finally { document.removeEventListener('copy', listener); textarea.remove(); previous?.focus({preventScroll:true}); }
        return success;
    }
    async function writeClipboard(payload, format) {
        if (format === 'word') {
            try {
                if (!navigator.clipboard?.write || !globalThis.ClipboardItem) throw new Error('HTML unavailable');
                await navigator.clipboard.write([new ClipboardItem({
                    'text/html': new Blob([payload.html], {type:'text/html'}),
                    'text/plain': new Blob([payload.text], {type:'text/plain'}),
                })]);
                return 'html';
            } catch { if (legacyCopy(payload, true)) return 'html'; }
        }
        try {
            if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
            await navigator.clipboard.writeText(payload.text);
        } catch {
            if (!legacyCopy(payload, false)) throw new Error('Не вдалося скопіювати. Перевірте дозвіл браузера на буфер обміну.');
        }
        return 'text';
    }
    const interactive = target => target.closest('input,textarea,select,button,a,[contenteditable]:not([contenteditable="false"]),[role="textbox"]');
    class TableSelection {
        constructor(controller) {
            this.controller = controller; this.table = controller.table; this.picker = controller.picker;
            this.selected = new Set(); this.anchor = null;
            this.mode='cells';this.columnAnchor=null;
            this.picker.querySelector('[data-selection-mode]')?.addEventListener('change',event=>{this.mode=event.target.value;this.anchor=null;this.columnAnchor=null;});
            this.picker.querySelector('[data-selection-clear]')?.addEventListener('click',()=>this.clear());
            this.button = this.picker.querySelector('[data-table-copy]');
            this.status = this.picker.querySelector('[data-copy-status]');
            this.storageKey = `project2:table-copy:${controller.config.id}`;
            const saved = controller.storage.read(this.storageKey, {});
            this.format = saved.version === 1 && saved.format === 'word' ? 'word' : 'excel';
            this.picker.querySelectorAll('[data-copy-format]').forEach(input => {
                input.checked = input.value === this.format;
                input.addEventListener('change', () => {
                    this.format = input.value;
                    controller.storage.write(this.storageKey, {version:1, format:this.format});
                });
            });
            this.table.tabIndex = 0;
            this.table.classList.add('table-cell-selection');
            this.table.addEventListener('pointerdown', event => {
                if (event.button !== 0 || interactive(event.target)) return;
                const cell = event.target.closest('td[data-column-key]');
                if (!this.grid().flat().includes(cell)) return;
                event.preventDefault(); window.getSelection()?.removeAllRanges(); this.table.focus({preventScroll:true});
                this.status.textContent = '';
                this.base = event.ctrlKey || event.metaKey ? new Set(this.selected) : new Set();
                if (!event.shiftKey || !this.anchor || !this.grid().flat().includes(this.anchor)) this.anchor = cell;
                this.dragging = true; this.table.classList.add('table-selection-dragging'); this.range(cell);
                this.pointerStart=[event.clientX,event.clientY];this.pointerMoved=false;
                const gesture=this.rangeCells(cell);
                this.toggleCells=(event.ctrlKey||event.metaKey)&&!event.shiftKey&&gesture.every(value=>this.base.has(value))?gesture:null;
            });
            document.addEventListener('pointermove', event => {
                if (!this.dragging) return;
                if(Math.hypot(event.clientX-this.pointerStart[0],event.clientY-this.pointerStart[1])>3)this.pointerMoved=true;
                const cell = document.elementFromPoint(event.clientX, event.clientY)?.closest('td[data-column-key]');
                if (this.grid().flat().includes(cell)) this.range(cell);
            });
            const stop = event => {
                if(this.dragging&&event.type==='pointerup'&&this.toggleCells&&!this.pointerMoved){this.toggleCells.forEach(cell=>this.selected.delete(cell));this.render();}
                this.toggleCells=null;this.dragging = false; this.table.classList.remove('table-selection-dragging');
            };
            document.addEventListener('pointerup', stop); document.addEventListener('pointercancel', stop);
            window.addEventListener('blur', stop);
            this.table.addEventListener('keydown', event => {
                if (interactive(event.target)) return;
                if (event.key === 'Escape') { this.clear(); return; }

            });
            this.button.addEventListener('click', () => this.copy()); this.render();
        }
        grid() {
            const columns = this.controller.model.columns;
            return Array.from(this.table.tBodies).flatMap(body => Array.from(body.rows)).filter(row => !row.hidden).map(row =>
                Array.from(row.cells).filter(cell => {
                    const column = columns.find(column => column.key === cell.dataset.columnKey);
                    return column && (column.informational || column.system) && !cell.hidden && getComputedStyle(cell).display !== 'none';
                })).filter(row => row.length);
        }
        selectColumn(key,event={}) {
            const grid=this.grid(),keys=grid[0]?.map(cell=>cell.dataset.columnKey)||[];
            const start=event.shiftKey&&keys.includes(this.columnAnchor)?keys.indexOf(this.columnAnchor):keys.indexOf(key),end=keys.indexOf(key);
            const chosen=keys.slice(Math.min(start,end),Math.max(start,end)+1);
            const cells=grid.flat().filter(cell=>chosen.includes(cell.dataset.columnKey));
            if (!cells.length) return;
            window.getSelection()?.removeAllRanges();
            const additive=event.ctrlKey||event.metaKey,remove=additive&&cells.every(cell=>this.selected.has(cell));
            if(!additive)this.selected.clear();cells.forEach(cell=>remove?this.selected.delete(cell):this.selected.add(cell));
            if(!event.shiftKey)this.columnAnchor=key;
            this.anchor=cells[0]; this.dragging=false; this.table.classList.remove('table-selection-dragging');
            this.status.textContent=''; this.render(); this.table.focus({preventScroll:true});
        }
        range(end) {
            this.selected = new Set(this.base);
            this.rangeCells(end).forEach(cell=>this.selected.add(cell));this.render();
        }
        rangeCells(end) {
            const grid = this.grid(), locate = cell => {
                const row = grid.findIndex(row => row.includes(cell)); return [row, grid[row]?.indexOf(cell)];
            };
            let [r1,c1] = locate(this.anchor), [r2,c2] = locate(end);
            if (r1 < 0 || r2 < 0) return [];
            if(this.mode==='rows'){c1=0;c2=grid[0].length-1;}
            if(this.mode==='columns'){r1=0;r2=grid.length-1;}
            const cells=[];
            for (let r=Math.min(r1,r2);r<=Math.max(r1,r2);r++)
                for (let c=Math.min(c1,c2);c<=Math.max(c1,c2);c++) if (grid[r][c]) cells.push(grid[r][c]);
            return cells;
        }
        render() {
            this.table.querySelectorAll('td[data-column-key]').forEach(cell => cell.classList.toggle('table-cell-selected', this.selected.has(cell)));
            this.button.disabled = !this.selected.size;
        }
        clear() { this.selected.clear(); this.anchor=null; this.columnAnchor=null;this.dragging=false; this.table.classList.remove('table-selection-dragging'); this.render(); }
        matrix() {
            const grid = this.grid(), positions=[];
            grid.forEach((row,r) => row.forEach((cell,c) => { if (this.selected.has(cell)) positions.push([r,c]); }));
            if (!positions.length) return [];
            const rows=positions.map(p=>p[0]), cols=positions.map(p=>p[1]), result=[];
            for (let r=Math.min(...rows);r<=Math.max(...rows);r++) {
                const row=[];
                for (let c=Math.min(...cols);c<=Math.max(...cols);c++) {
                    const cell=grid[r][c];
                    // Explicit display values exclude forms, icons and controls. Plain cells
                    // in future tables are supported by a clone with interactive UI removed.
                    const clean = node => {
                        const clone=node.cloneNode(true);
                        clone.querySelectorAll('input,textarea,select,button,form,[contenteditable],svg,[aria-hidden="true"],[role="img"],[data-icon],.bi,.fa').forEach(node=>node.remove());
                        clone.querySelectorAll('a').forEach(node=>node.replaceWith(...node.childNodes));
                        return clone.textContent;
                    };
                    let value='';
                    if (this.selected.has(cell)) {
                        const values=cell.querySelectorAll('[data-column-value]');
                        if (values.length) value=Array.from(values).filter(node=>!node.closest('form,button,input,select,textarea')).map(clean).join(' ');
                        else value=clean(cell).trim();
                    }
                    row.push(value);
                }
                result.push(row);
            }
            return result;
        }
        async copy() {
            const matrix=this.matrix(); if (!matrix.length) { this.clear(); return; }
            try {
                const kind=await writeClipboard(exportCells(matrix),this.format);
                this.status.textContent=this.format==='word' && kind!=='html' ? 'HTML для Word недоступний. Скопійовано лише текст TSV.' : (kind==='html' ? 'Скопійовано таблицю для Word.' : 'Скопійовано TSV для Excel.');
            } catch(error) { this.status.textContent=error.message; }
        }
    }
    return {exportCells, writeClipboard, TableSelection};
});
