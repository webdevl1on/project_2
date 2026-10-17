((root, factory) => {
    const api = factory();
    if (typeof module === "object" && module.exports) module.exports = api;
    else Object.assign(root.TableColumns ||= {}, api);
})(globalThis, () => {
    "use strict";
    const clone = value => JSON.parse(JSON.stringify(value));
    const same = (left, right) => JSON.stringify(left) === JSON.stringify(right);

    class TableHistory {
        constructor(saved = {}, limit = 5) {
            this.limit = limit;
            const entries = Array.isArray(saved?.entries) ? saved.entries : [];
            const offset = Math.max(0, entries.length - limit);
            this.entries = clone(entries.slice(offset));
            this.cursor = this.entries.length ? Math.max(0, Math.min(this.entries.length - 1,
                Number.isInteger(saved.cursor) ? saved.cursor - offset : this.entries.length - 1)) : -1;
        }
        get current() { return this.cursor >= 0 ? clone(this.entries[this.cursor]) : null; }
        get canBack() { return this.cursor > 0; }
        get canForward() { return this.cursor < this.entries.length - 1; }
        push(snapshot) {
            if (same(this.current, snapshot)) return false;
            this.entries = this.entries.slice(0, this.cursor + 1);
            this.entries.push(clone(snapshot));
            if (this.entries.length > this.limit) this.entries.shift();
            this.cursor = this.entries.length - 1;
            return true;
        }
        move(delta) {
            if (delta !== -1 && delta !== 1) return null;
            if ((delta < 0 && !this.canBack) || (delta > 0 && !this.canForward)) return null;
            this.cursor += delta;
            return this.current;
        }
        seek(snapshot) {
            const index = this.entries.findLastIndex(entry => same(entry, snapshot));
            if (index < 0) this.push(snapshot);
            else this.cursor = index;
        }
        toJSON() { return { version: 1, entries: clone(this.entries), cursor: this.cursor }; }
    }

    class TableTimeline {
        constructor(controller) {
            this.controller = controller;
            this.adapter = controller.filterAdapter;
            this.key = `project2:table-history:${controller.config.id}`;
            const saved = controller.storage.read(this.key, {});
            const entries = saved?.version === 1 && Array.isArray(saved.entries) ? saved.entries.map(entry => this.validSnapshot(entry)) : [];
            this.history = new TableHistory(entries.every(Boolean) ? { ...saved, entries } : {});
            this.back = controller.picker.querySelector("[data-table-back]");
            this.forward = controller.picker.querySelector("[data-table-forward]");
            this.back.addEventListener("click", () => this.travel(-1));
            this.forward.addEventListener("click", () => this.travel(1));
            window.addEventListener("pageshow", event => { if (event.persisted) this.restoreBrowser(); });
            window.addEventListener("popstate", () => this.restoreBrowser());
        }
        snapshot(layout, filters) {
            filters = this.adapter.normalise(filters);
            // Value order in an IN filter has no meaning; cascade order does.
            Object.values(filters.values).forEach(values => values.sort());
            return { layout: this.controller.model.normalise(layout), filters };
        }
        validSnapshot(value) {
            if (!value?.layout || !Array.isArray(value.layout.visible) || !Array.isArray(value.layout.order) || !value.filters) return null;
            const layout = this.controller.model.normalise(value.layout);
            if (!this.controller.model.hasInformation(layout.visible)) return null;
            return this.snapshot(layout, this.adapter.withVisible(layout.visible, this.adapter.normalise(value.filters)));
        }
        browserSnapshot() {
            const marker = window.history.state?.tableColumns?.[this.controller.config.id];
            return marker?.path === location.pathname ? this.validSnapshot(marker.snapshot) : null;
        }
        initialise() {
            const traversal = performance.getEntriesByType("navigation")[0]?.type === "back_forward";
            const previous = traversal ? this.browserSnapshot() : null;
            if (previous) this.controller.state.layout = previous.layout;
            this.controller.filters = this.adapter.withVisible(this.controller.state.layout.visible, this.adapter.read());
            const snapshot = this.snapshot(this.controller.state.layout, this.controller.filters);
            if (previous) this.history.seek(snapshot);
            else this.history.push(snapshot);
            this.finish(snapshot, true);
        }
        stamp(snapshot) {
            window.history.replaceState({ ...window.history.state, tableColumns: {
                ...window.history.state?.tableColumns,
                [this.controller.config.id]: { path: location.pathname, snapshot: clone(snapshot) },
            } }, "");
        }
        persist() {
            this.controller.storageError.hidden = true;
            this.controller.storage.save(this.controller.state);
            this.controller.storage.write(this.key, this.history.toJSON());
            this.back.disabled = !this.history.canBack;
            this.forward.disabled = !this.history.canForward;
        }
        finish(snapshot, replace = false) {
            this.controller.state.layout = clone(snapshot.layout);
            this.controller.filters = clone(snapshot.filters);
            this.controller.renderVisibility();
            this.controller.draft = this.controller.model.visibility(snapshot.layout);
            this.controller.renderDraft();
            this.persist();
            if (this.adapter.equal(this.adapter.read(), snapshot.filters)) this.stamp(snapshot);
            else this.adapter.navigate(snapshot.filters, { replace });
        }
        changeLayout(layout) {
            const before = this.snapshot(this.controller.state.layout, this.controller.filters);
            this.history.push(before);
            const next = this.snapshot(layout, this.adapter.withVisible(layout.visible, this.controller.filters));
            this.history.push(next);
            this.finish(next);
        }
        travel(delta) {
            const snapshot = this.history.move(delta);
            if (snapshot) this.finish(snapshot);
        }
        restoreBrowser() {
            const previous = this.browserSnapshot();
            if (!previous) return;
            const snapshot = this.snapshot(previous.layout, this.adapter.withVisible(previous.layout.visible, this.adapter.read()));
            this.history.seek(snapshot);
            this.finish(snapshot, true);
        }
    }
    return { TableHistory, TableTimeline };
});
