/* Pure column/preset logic and replaceable persistence. Also usable by Node tests. */
((root, factory) => {
    const api = factory();
    if (typeof module === "object" && module.exports) module.exports = api;
    else Object.assign(root.TableColumns ||= {}, api);
})(globalThis, () => {
    "use strict";
    const clone = value => JSON.parse(JSON.stringify(value));
    const unique = values => [...new Set(values)];
    function createPresetId(crypto = globalThis.crypto) {
        if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
        // randomUUID is unavailable on ordinary HTTP LAN pages; getRandomValues is supported there.
        const bytes = crypto.getRandomValues(new Uint8Array(16));
        bytes[6] = (bytes[6] & 15) | 64;
        bytes[8] = (bytes[8] & 63) | 128;
        const hex = Array.from(bytes, value => value.toString(16).padStart(2, "0")).join("");
        return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
    }

    class ColumnModel {
        constructor(config) {
            this.config = config;
            this.columns = config.groups.flatMap(group => group.columns);
            this.keys = this.columns.map(column => column.key);
            this.system = this.columns.filter(column => column.system).map(column => column.key);
            this.defaults = this.normalise({ visible: this.columns.filter(column => column.default_visible).map(column => column.key) });
        }
        hasInformation(keys) {
            return this.columns.some(column => column.informational && keys.includes(column.key));
        }
        normalise(value = {}) {
            if (!value || typeof value !== "object") value = {};
            const order = unique([...this.system, ...(Array.isArray(value.order) ? value.order : []), ...this.keys])
                .filter(key => this.keys.includes(key));
            const visible = unique([...this.system, ...(Array.isArray(value.visible) ? value.visible : [])]);
            return { visible: order.filter(key => visible.includes(key)), order };
        }
        visibility(layout) {
            return Object.fromEntries(this.keys.map(key => [key, layout.visible.includes(key)]));
        }
        fromVisibility(visibility, order = this.keys) {
            return this.normalise({ visible: this.keys.filter(key => visibility[key]), order });
        }
        fromPreset(preset) {
            const available = preset.columns.filter(key => this.keys.includes(key));
            if (!this.hasInformation(available)) throw new Error("У пресеті не залишилося доступних інформаційних колонок.");
            return this.normalise({ visible: available, order: available });
        }
        missing(preset) {
            return preset.columns.filter(key => !this.keys.includes(key));
        }
        widths(value = {}) {
            if (!value || typeof value !== "object") value = {};
            return Object.fromEntries(this.columns.map(column => {
                const minimum = column.min_width || (column.system ? 56 : 100);
                const fallback = column.width || (column.system ? 56 : column.informational ? 180 : 360);
                const width = Number.isFinite(value[column.key]) ? value[column.key] : fallback;
                return [column.key, Math.min(4096, Math.max(minimum, width))];
            }));
        }
    }

    class LocalTableStorage {
        constructor(tableId, onError = () => {}, backend = () => globalThis.localStorage) {
            this.tableId = tableId;
            this.onError = onError;
            this.backend = backend;
        }
        read(key, fallback) {
            try { return JSON.parse(this.backend().getItem(key)) ?? clone(fallback); }
            catch { return clone(fallback); }
        }
        write(key, value) {
            try { this.backend().setItem(key, JSON.stringify(value)); return true; }
            catch { this.onError(); return false; }
        }
        load(model) {
            const saved = this.read(`project2:table-columns:${this.tableId}`, {});
            let layout;
            if (saved?.version === 2) layout = model.normalise(saved.layout);
            else if (saved?.version === 1 && saved.visibility && typeof saved.visibility === "object" && !Array.isArray(saved.visibility)) {
                const values = Object.fromEntries(model.columns.map(column => [column.key,
                    typeof saved.visibility[column.key] === "boolean" ? saved.visibility[column.key] : column.default_visible]));
                layout = model.fromVisibility(values);
            }
            if (!layout || !model.hasInformation(layout.visible)) layout = clone(model.defaults);
            return { layout, widths: saved?.version === 2 && saved.widths && typeof saved.widths === "object" ? saved.widths : {} };
        }
        save(state) {
            return this.write(`project2:table-columns:${this.tableId}`, { version: 2, ...state });
        }
    }

    // An API-backed implementation can supply the same async methods later.
    class PresetStorage {
        async list(tableId) { throw new Error("Implement list(tableId)"); }
        async put(preset) { throw new Error("Implement put(preset)"); }
        async remove(tableId, id) { throw new Error("Implement remove(tableId, id)"); }
    }

    class LocalPresetStorage extends PresetStorage {
        constructor(storage) { super(); this.storage = storage; }
        key(tableId) { return `project2:table-presets:${tableId}`; }
        async list(tableId) {
            const saved = this.storage.read(this.key(tableId), {});
            return Array.isArray(saved?.presets) ? saved.presets.filter(preset =>
                preset && preset.table_id === tableId && typeof preset.id === "string" &&
                typeof preset.name === "string" && Array.isArray(preset.columns) &&
                preset.columns.every(key => typeof key === "string")) : [];
        }
        async put(preset) {
            const list = await this.list(preset.table_id);
            const index = list.findIndex(item => item.id === preset.id);
            if (index < 0) list.push(clone(preset));
            else list[index] = clone(preset);
            if (!this.storage.write(this.key(preset.table_id), { version: 1, presets: list })) {
                throw new Error("Браузер не дозволив зберегти пресет.");
            }
            return clone(preset);
        }
        async remove(tableId, id) {
            const list = (await this.list(tableId)).filter(preset => preset.id !== id);
            if (!this.storage.write(this.key(tableId), { version: 1, presets: list })) {
                throw new Error("Браузер не дозволив видалити пресет.");
            }
        }
    }

    class DuplicatePresetName extends Error {
        constructor(preset) {
            super("Пресет із такою назвою вже існує.");
            this.preset = preset;
        }
    }

    class PresetManager {
        constructor(tableId, model, storage) {
            this.tableId = tableId;
            this.model = model;
            this.storage = storage;
        }
        name(value) {
            const name = value.trim().replace(/\s+/g, " ");
            if (!name) throw new Error("Введіть назву пресету.");
            if (name.length > 30) throw new Error("Назва пресету може містити до 30 символів.");
            return name;
        }
        async list() { return this.storage.list(this.tableId); }
        async save({ id, name, columns }, { replaceId } = {}) {
            name = this.name(name);
            const list = await this.list();
            const existing = list.find(preset => preset.id !== id &&
                preset.name.toLocaleLowerCase("uk") === name.toLocaleLowerCase("uk"));
            if (existing && existing.id !== replaceId) throw new DuplicatePresetName(existing);
            const layout = this.model.normalise({ visible: columns, order: columns });
            if (!this.model.hasInformation(layout.visible)) throw new Error("Виберіть хоча б одну інформаційну колонку.");
            const preset = {
                version: 1, id: existing?.id || id || createPresetId(),
                table_id: this.tableId, name, columns: layout.visible,
            };
            return this.storage.put(preset);
        }
        async remove(id) { return this.storage.remove(this.tableId, id); }
        preview(preset) {
            if (preset.version !== 1) throw new Error("Версія формату пресету не підтримується.");
            return { layout: this.model.fromPreset(preset), missing: this.model.missing(preset) };
        }
    }

    return { clone, createPresetId, ColumnModel, LocalTableStorage, PresetStorage, LocalPresetStorage, PresetManager, DuplicatePresetName };
});
