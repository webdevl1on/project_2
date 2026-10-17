/* The same native checkbox tree is used in the dropdown and preset editor. */
(() => {
    "use strict";
    class CheckboxTree {
        constructor(root, config, onChange, { hideSelected = false } = {}) {
            this.root = root;
            this.config = config;
            this.onChange = onChange;
            this.hideSelected = hideSelected;
            this.columns = config.groups.flatMap(group => group.columns);
            this.choices = Array.from(root.querySelectorAll("[data-column-choice]"));
            this.groups = Array.from(root.querySelectorAll("[data-column-group]"));
            this.choices.forEach(choice => {
                const column = this.columns.find(column => column.key === choice.dataset.columnChoice);
                choice.disabled = Boolean(column.system);
                choice.addEventListener("change", () => {
                    this.value[choice.dataset.columnChoice] = choice.checked;
                    this.changed();
                });
            });
            this.groups.forEach(group => {
                const checkbox = group.querySelector("[data-column-group-choice]");
                checkbox.disabled = Array.from(group.querySelectorAll("[data-column-choice]")).every(choice => choice.disabled);
                checkbox.addEventListener("change", () => {
                    group.querySelectorAll("[data-column-choice]").forEach(choice => {
                        if (!choice.disabled) this.value[choice.dataset.columnChoice] = checkbox.checked;
                    });
                    this.changed();
                });
                const expand = group.querySelector("[data-column-expand]");
                expand.addEventListener("click", () => {
                    const expanded = expand.getAttribute("aria-expanded") !== "true";
                    expand.setAttribute("aria-expanded", String(expanded));
                    group.querySelector("[data-column-children]").hidden = !expanded;
                    group.querySelector("[data-column-chevron]").textContent = expanded ? "▾" : "▸";
                });
            });
        }
        changed() {
            this.setValue(this.value);
            this.onChange({ ...this.value });
        }
        setValue(value) {
            this.value = { ...value };
            this.choices.forEach(choice => {
                if (choice.disabled) this.value[choice.dataset.columnChoice] = true;
                choice.checked = Boolean(this.value[choice.dataset.columnChoice]);
                choice.closest("[data-column-choice-row]").hidden = this.hideSelected && choice.checked;
            });
            this.groups.forEach(group => {
                const children = Array.from(group.querySelectorAll("[data-column-choice]"));
                const count = children.filter(choice => choice.checked).length;
                const checkbox = group.querySelector("[data-column-group-choice]");
                checkbox.checked = count === children.length;
                checkbox.indeterminate = count > 0 && count < children.length;
            });
        }
    }
    Object.assign(globalThis.TableColumns ||= {}, { CheckboxTree });
})();
