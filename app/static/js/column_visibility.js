(() => {
    "use strict";
    const api = globalThis.TableColumns;

    class ColumnController {
        constructor(picker) {
            this.picker = picker;
            this.config = JSON.parse(picker.querySelector("[data-column-config]").textContent);
            this.table = document.getElementById(this.config.id);
            this.model = new api.ColumnModel(this.config);
            this.storageError = picker.querySelector("[data-column-storage-error]");
            this.storage = new api.LocalTableStorage(this.config.id, () => { this.storageError.hidden = false; });
            this.state = this.storage.load(this.model);
            this.state.widths = this.model.widths(this.state.widths);
            const filterConfig = picker.querySelector("[data-column-filters]");
            this.filterAdapter = new api.QueryFilterAdapter(filterConfig ? JSON.parse(filterConfig.textContent) : {});
            this.filters = this.filterAdapter.read();
            this.applyButton = picker.querySelector("[data-column-apply]");
            this.toggle = picker.querySelector("[data-column-toggle]");
            this.error = picker.querySelector("[data-column-error]");
            this.draft = this.model.visibility(this.state.layout);
            this.tree = new api.CheckboxTree(picker.querySelector("[data-visibility-tree]"), this.config, value => {
                this.draft = value;
                this.renderDraft();
            });

            picker.querySelector("[data-column-all]").addEventListener("click", () => {
                this.draft = Object.fromEntries(this.model.keys.map(key => [key, true]));
                this.renderDraft();
            });
            picker.querySelector("[data-column-reset]").addEventListener("click", () => {
                this.draft = this.model.visibility(this.model.defaults);
                this.renderDraft();
            });
            this.applyButton.addEventListener("click", () => {
                const layout = this.model.fromVisibility(this.draft, this.state.layout.order);
                if (!this.model.hasInformation(layout.visible)) return;
                bootstrap.Dropdown.getOrCreateInstance(this.toggle).hide();
                this.commitLayout(layout, "checkbox");
                this.toggle.focus();
            });
            const dropdown = picker.querySelector("[data-visibility-dropdown]");
            for (const event of ["show.bs.dropdown", "hidden.bs.dropdown"]) {
                dropdown.addEventListener(event, () => {
                    this.draft = this.model.visibility(this.state.layout);
                    this.renderDraft();
                });
            }
            this.renderVisibility();
            this.renderDraft();
            this.presets = new api.PresetPanel(this);
            this.interactions = new api.ColumnInteractions(this);
            this.timeline = new api.TableTimeline(this);
            this.timeline.initialise();
            if (api.TableSelection) this.selection = new api.TableSelection(this);
            if (api.TableAppearance) this.appearance = new api.TableAppearance(this);
            this.table.addEventListener("click", event => {
                const select = event.target.closest("[data-column-select]");
                if (select && this.selection) {
                    const key=select.closest("[data-column-key]")?.dataset.columnKey;
                    bootstrap.Dropdown.getOrCreateInstance(select.closest(".dropdown").querySelector("[data-bs-toggle=dropdown]")).hide();
                    this.selection.selectColumn(key,event); return;
                }
                const button = event.target.closest("[data-column-hide]");
                if (!button) return;
                const key = button.closest("[data-column-key]")?.dataset.columnKey;
                const column = this.model.columns.find(column => column.key === key);
                if (!column || column.system) return;
                const layout = this.getLayout();
                layout.visible = layout.visible.filter(value => value !== key);
                if (!this.model.hasInformation(layout.visible)) {
                    this.notice("Залиште видимою хоча б одну інформаційну колонку."); return;
                }
                bootstrap.Dropdown.getOrCreateInstance(button.closest(".dropdown").querySelector("[data-bs-toggle=dropdown]")).hide();
                this.commitLayout(layout, "header-hide");
            });
            picker.dataset.columnsReady = "true";
        }
        getLayout() { return api.clone(this.state.layout); }
        commitLayout(layout, source = "manual") {
            layout = this.model.normalise(layout);
            if (!this.model.hasInformation(layout.visible)) return;
            this.timeline.changeLayout(layout);
            this.picker.dispatchEvent(new CustomEvent("columnlayout:change", { detail: { layout: this.getLayout(), source } }));
        }
        renderVisibility() {
            this.selection?.clear();
            const { visible, order } = this.state.layout;
            this.table.querySelectorAll("tr").forEach(row => {
                const cells = new Map(Array.from(row.children).filter(cell => cell.hasAttribute("data-column-key"))
                    .map(cell => [cell.dataset.columnKey, cell]));
                order.forEach(key => {
                    const cell = cells.get(key);
                    if (cell) { cell.hidden = !visible.includes(key); row.append(cell); }
                });
            });
            this.table.querySelectorAll("[data-column-empty]").forEach(cell => { cell.colSpan = visible.length; });
            this.interactions?.renderWidths();
        }
        renderDraft() {
            this.tree.setValue(this.draft);
            const valid = this.model.hasInformation(this.model.keys.filter(key => this.draft[key]));
            this.error.hidden = valid;
            this.applyButton.disabled = !valid;
        }
        notice(text) {
            const node = this.picker.querySelector("[data-preset-notice]");
            node.textContent = text;
            node.hidden = !text;
        }
    }

    api.controllers = new Map();
    document.querySelectorAll("[data-column-picker]").forEach(picker => {
        const controller = new ColumnController(picker);
        api.controllers.set(controller.config.id, controller);
    });
})();
