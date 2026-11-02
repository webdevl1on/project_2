/* Shared rendering only: event semantics and day counts are supplied by services. */
((root, factory) => {
    const api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    else root.EventUI = api;
})(globalThis, () => {
    'use strict';
    function badge(item) {
        const node = document.createElement('span');
        node.className = `event-badge event-tone-${item.tone}`; node.title = item.description || item.name;
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('aria-hidden', 'true');
        const use = document.createElementNS(svg.namespaceURI, 'use'); use.setAttribute('href', `#event-icon-${item.icon}`); svg.append(use);
        const text = document.createElement('span'); text.textContent = item.label; node.append(svg, text); return node;
    }
    function csvCell(value) {
        let text = String(value ?? '');
        if (/^[\s]*[=+\-@]/.test(text)) text = "'" + text;
        return '"' + text.replace(/"/g, '""') + '"';
    }
    function csv(rows) { return '\uFEFF' + rows.map(row => row.map(csvCell).join(';')).join('\r\n'); }
    function download(rows, filename) {
        const url = URL.createObjectURL(new Blob([csv(rows)], {type: 'text/csv;charset=utf-8'}));
        const a = document.createElement('a'); a.href = url; a.download = filename; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    return {badge, csvCell, csv, download};
});
