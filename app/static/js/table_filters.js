/* URL adapter: no SQL or table-specific DOM dependencies. */
((root, factory) => {
    const api = factory();
    if (typeof module === "object" && module.exports) module.exports = api;
    else Object.assign(root.TableColumns ||= {}, api);
})(globalThis, () => {
    "use strict";
    class QueryFilterAdapter {
        constructor(config = {}, location = globalThis.location) {
            this.keys = config.keys || [];
            this.columnKeys = config.column_keys || {};
            this.orderParameter = config.order_parameter || "filter_order";
            this.extra = config.extra || {};
            this.location = location;
        }
        normalise(value = {}) {
            if (!value || typeof value !== "object") value = {};
            const values = Object.fromEntries(this.keys.map(key => [key,
                [...new Set((Array.isArray(value.values?.[key]) ? value.values[key] : []).filter(item => typeof item === "string" && item !== ""))],
            ]).filter(([, items]) => items.length));
            const order = [...new Set([...(Array.isArray(value.order) ? value.order : []), ...Object.keys(values)])].filter(key => values[key]?.length);
            const extra = Object.fromEntries(Object.entries(this.extra).map(([key, fallback]) => [key,
                typeof value.extra?.[key] === "string" ? value.extra[key] : fallback]));
            return { values, order, extra };
        }
        read(url = new URL(this.location.href)) {
            return this.normalise({
                values: Object.fromEntries(this.keys.map(key => [key, url.searchParams.getAll(key)])),
                order: [...(url.searchParams.get(this.orderParameter) || "").split(","), ...url.searchParams.keys()],
                extra: Object.fromEntries(Object.entries(this.extra).map(([key, fallback]) => [key, url.searchParams.get(key) ?? fallback])),
            });
        }
        withVisible(visible, filters) {
            return this.normalise({ ...filters, values: Object.fromEntries(Object.entries(filters.values).filter(([key]) => visible.includes(this.columnKeys[key] || key))) });
        }
        equal(left, right) {
            const canonical = value => {
                const normal = this.normalise(value);
                return JSON.stringify({ ...normal, values: Object.fromEntries(this.keys.filter(key => normal.values[key]).map(key => [key, [...normal.values[key]].sort()])) });
            };
            return canonical(left) === canonical(right);
        }
        urlFor(filters) {
            filters = this.normalise(filters);
            const url = new URL(this.location.href);
            this.keys.forEach(key => url.searchParams.delete(key));
            filters.order.forEach(key => filters.values[key].forEach(value => url.searchParams.append(key, value)));
            if (filters.order.length || url.searchParams.has(this.orderParameter)) url.searchParams.set(this.orderParameter, filters.order.join(","));
            Object.entries(filters.extra).forEach(([key, value]) => {
                if (value !== this.extra[key] || url.searchParams.has(key)) url.searchParams.set(key, value);
            });
            return url;
        }
        navigate(filters, { replace = false } = {}) {
            if (!this.equal(this.read(), filters)) this.location[replace ? "replace" : "assign"](this.urlFor(filters).href);
        }
    }
    return { QueryFilterAdapter };
});
