/* Shared rendering only: event semantics and day counts are supplied by services. */
((root, factory) => {
    const api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    else root.EventUI = api;
})(globalThis, () => {
    'use strict';
    function colour(node,item){if(/^#[0-9a-f]{6}$/i.test(item.background||''))node.style.backgroundColor=item.background;if(/^#[0-9a-f]{6}$/i.test(item.foreground||''))node.style.color=item.foreground;if(item.accent_color && CSS.supports('color',item.accent_color))node.style.backgroundColor=`color-mix(in srgb,${item.accent_color} ${item.mix}%,white)`;}
    function badge(item) {
        const node = document.createElement('span');
        node.className = `event-badge event-tone-${item.tone}`; node.title = item.description || item.name;
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('aria-hidden', 'true');
        const use = document.createElementNS(svg.namespaceURI, 'use'); use.setAttribute('href', `#event-icon-${item.icon}`); svg.append(use);
        const text = document.createElement('span'); text.textContent = item.label; node.append(svg, text);colour(node,item);if(item.mirage)node.classList.add('event-mirage'); return node;
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
    return {colour,badge, csvCell, csv, download};
});
