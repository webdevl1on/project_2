(() => {
    "use strict";
    const api = globalThis.TableColumns;
    const button = (text, className, action) => {
        const node = document.createElement("button");
        node.type = "button";
        node.className = className;
        node.textContent = text;
        node.addEventListener("click", action);
        return node;
    };

    class PresetPanel {
        constructor(controller, storage = new api.LocalPresetStorage(controller.storage)) {
            this.controller = controller;
            this.root = controller.picker;
            this.model = controller.model;
            this.manager = new api.PresetManager(controller.config.id, this.model, storage);
            this.saveModal = this.root.querySelector("[data-preset-save-modal]");
            this.editorModal = this.root.querySelector("[data-preset-editor-modal]");
            this.deleteModal = this.root.querySelector("[data-preset-delete-modal]");
            this.nameInput = this.saveModal.querySelector("[data-preset-name]");
            this.editName = this.editorModal.querySelector("[data-preset-editor-name]");
            this.editSave = this.editorModal.querySelector("[data-preset-editor-save]");
            this.editorTree = new api.CheckboxTree(this.root.querySelector("[data-preset-editor-tree]"), controller.config, visibility => {
                this.editColumns = this.editColumns.filter(key => visibility[key]);
                this.model.keys.forEach(key => {
                    if (visibility[key] && !this.editColumns.includes(key)) this.editColumns.push(key);
                });
                this.renderEditor();
            }, { hideSelected: true });
            this.root.querySelectorAll("[data-preset-create]").forEach(node => node.addEventListener("click", () => this.openSave()));
            this.saveModal.querySelector("form").addEventListener("submit", event => { event.preventDefault(); this.savePreset(); });
            this.saveModal.querySelector("[data-preset-overwrite]").addEventListener("click", () => this.savePreset(this.conflictId));
            this.saveModal.querySelector("[data-preset-back]").addEventListener("click", () => {
                this.conflict(null);
                this.nameInput.focus();
            });
            this.editorModal.querySelector("form").addEventListener("submit", event => { event.preventDefault(); this.saveEditor(); });
            this.editName.addEventListener("input", () => this.updateEditorSave());
            this.editorModal.querySelector("[data-preset-delete]").addEventListener("click", () => {
                this.deleteModal.querySelector("[data-preset-delete-message]").textContent = `Видалити пресет «${this.editing.name}»?`;
                this.showError(this.deleteModal, "[data-preset-delete-error]", "");
                this.switchModal(this.editorModal, this.deleteModal);
            });
            this.deleteModal.querySelector("[data-preset-delete-cancel]").addEventListener("click", () => this.switchModal(this.deleteModal, this.editorModal));
            this.deleteModal.querySelector("[data-preset-delete-confirm]").addEventListener("click", async () => {
                try {
                    await this.manager.remove(this.editing.id);
                    bootstrap.Modal.getOrCreateInstance(this.deleteModal).hide();
                    await this.renderPresets();
                } catch (error) { this.showError(this.deleteModal, "[data-preset-delete-error]", error.message); }
            });
            this.saveModal.addEventListener("shown.bs.modal", () => this.nameInput.focus());
            this.editorModal.addEventListener("shown.bs.modal", () => this.editName.focus());
            this.ready = this.renderPresets();
        }
        switchModal(from, to) {
            from.addEventListener("hidden.bs.modal", () => bootstrap.Modal.getOrCreateInstance(to).show(), { once: true });
            bootstrap.Modal.getOrCreateInstance(from).hide();
        }
        showError(modal, selector, text) {
            const node = modal.querySelector(selector);
            node.textContent = text;
            node.hidden = !text;
        }
        conflict(id) {
            this.conflictId = id;
            this.nameInput.readOnly = Boolean(id);
            this.saveModal.querySelector("[data-preset-conflict]").hidden = !id;
            this.saveModal.querySelector("[data-preset-save-actions]").hidden = Boolean(id);
        }
        openSave() {
            this.pendingColumns = this.controller.getLayout().visible;
            this.nameInput.value = "";
            this.conflict(null);
            this.showError(this.saveModal, "[data-preset-save-error]", "");
            bootstrap.Dropdown.getInstance(this.controller.toggle)?.hide();
            bootstrap.Modal.getOrCreateInstance(this.saveModal).show();
        }
        async savePreset(replaceId) {
            const buttons = this.saveModal.querySelectorAll("button");
            buttons.forEach(node => { node.disabled = true; });
            try {
                await this.manager.save({ name: this.nameInput.value, columns: this.pendingColumns }, { replaceId });
                bootstrap.Modal.getOrCreateInstance(this.saveModal).hide();
                await this.renderPresets();
            } catch (error) {
                if (error instanceof api.DuplicatePresetName) this.conflict(error.preset.id);
                else this.showError(this.saveModal, "[data-preset-save-error]", error.message);
            } finally { buttons.forEach(node => { node.disabled = false; }); }
        }
        async renderPresets() {
            const list = this.root.querySelector("[data-preset-list]");
            const presets = await this.manager.list();
            list.replaceChildren();
            presets.forEach(preset => {
                const item = document.createElement("div");
                item.className = "preset-item";
                const group = document.createElement("div");
                group.className = "btn-group preset-button";
                const apply = button(preset.name, "btn btn-outline-primary preset-name", () => {
                    try {
                        const preview = this.manager.preview(preset);
                        this.controller.notice(preview.missing.length ? `Застарілий пресет. Недоступні колонки: ${preview.missing.join(", ")}. Застосовано доступні колонки.` : "");
                        this.controller.commitLayout(preview.layout, "preset");
                    } catch (error) { this.controller.notice(error.message); }
                });
                apply.dataset.presetApply = preset.id;
                const edit = button("⚙", "btn btn-outline-secondary", () => this.openEditor(preset));
                edit.dataset.presetEdit = preset.id;
                edit.setAttribute("aria-label", `Налаштувати пресет «${preset.name}»`);
                group.append(apply, edit);
                item.append(group);
                const missing = this.model.missing(preset);
                if (missing.length || preset.version !== 1) {
                    const warning = document.createElement("small");
                    warning.className = "d-block text-warning";
                    warning.dataset.presetStale = "";
                    warning.textContent = missing.length ? `Застарілий: недоступні ${missing.join(", ")}` : "Непідтримувана версія";
                    item.append(warning);
                }
                list.append(item);
            });
        }
        openEditor(preset) {
            this.editing = api.clone(preset);
            this.editName.value = preset.name;
            this.editColumns = this.model.normalise({ visible: preset.columns, order: preset.columns }).visible;
            this.baseline = JSON.stringify({ name: preset.name, columns: this.editColumns });
            const missing = this.model.missing(preset);
            const warning = this.editorModal.querySelector("[data-preset-editor-warning]");
            warning.textContent = missing.length ? `Недоступні колонки: ${missing.join(", ")}. Збереження змін оновить список доступних колонок.` : "";
            warning.hidden = !missing.length;
            this.showError(this.editorModal, "[data-preset-editor-error]", "");
            this.renderEditor();
            bootstrap.Modal.getOrCreateInstance(this.editorModal).show();
        }
        renderEditor() {
            const list = this.editorModal.querySelector("[data-preset-selected]");
            list.replaceChildren();
            this.editColumns.forEach((key, index) => {
                const column = this.model.columns.find(column => column.key === key);
                const row = document.createElement("div");
                row.className = "preset-selected-row";
                row.dataset.presetSelectedKey = key;
                const label = document.createElement("label");
                const checkbox = document.createElement("input");
                checkbox.type = "checkbox";
                checkbox.className = "form-check-input me-2";
                checkbox.checked = true;
                checkbox.disabled = Boolean(column.system);
                checkbox.addEventListener("change", () => {
                    this.editColumns = this.editColumns.filter(value => value !== key);
                    this.renderEditor();
                });
                label.append(checkbox, document.createTextNode(column.label));
                const move = delta => {
                    const target = index + delta;
                    [this.editColumns[index], this.editColumns[target]] = [this.editColumns[target], this.editColumns[index]];
                    this.renderEditor();
                };
                const up = button("↑", "btn btn-sm btn-outline-secondary", () => move(-1));
                up.dataset.presetUp = key;
                up.setAttribute("aria-label", `Перемістити вище: ${column.label}`);
                up.disabled = Boolean(column.system) || index === 0 || this.model.system.includes(this.editColumns[index - 1]);
                const down = button("↓", "btn btn-sm btn-outline-secondary", () => move(1));
                down.dataset.presetDown = key;
                down.setAttribute("aria-label", `Перемістити нижче: ${column.label}`);
                down.disabled = Boolean(column.system) || index === this.editColumns.length - 1;
                row.append(label, up, down);
                list.append(row);
            });
            this.editorTree.setValue(Object.fromEntries(this.model.keys.map(key => [key, this.editColumns.includes(key)])));
            this.updateEditorSave();
        }
        updateEditorSave() {
            let name;
            let error = "";
            try { name = this.manager.name(this.editName.value); } catch (failure) { error = failure.message; }
            if (!this.model.hasInformation(this.editColumns)) error = "Виберіть хоча б одну інформаційну колонку.";
            this.showError(this.editorModal, "[data-preset-editor-error]", error);
            this.editSave.disabled = Boolean(error) || this.baseline === JSON.stringify({ name, columns: this.editColumns });
        }
        async saveEditor() {
            if (this.editSave.disabled) return;
            this.editSave.disabled = true;
            try {
                await this.manager.save({ id: this.editing.id, name: this.editName.value, columns: this.editColumns });
                bootstrap.Modal.getOrCreateInstance(this.editorModal).hide();
                await this.renderPresets();
            } catch (error) {
                this.showError(this.editorModal, "[data-preset-editor-error]", error.message);
                this.editSave.disabled = false;
            }
        }
    }
    api.PresetPanel = PresetPanel;
})();
