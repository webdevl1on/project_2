(() => {
    "use strict";

    document.querySelectorAll("[data-column-picker]").forEach(picker => {
        const config = JSON.parse(picker.querySelector("[data-column-config]").textContent);
        const table = document.getElementById(config.id);
        if (!table) return;

        const columns = config.groups.flatMap(group => group.columns);
        const defaults = Object.fromEntries(columns.map(column => [column.key, column.default_visible]));
        const storageKey = `project2:table-columns:${config.id}`;
        const choices = Array.from(picker.querySelectorAll("[data-column-choice]"));
        const groups = Array.from(picker.querySelectorAll("[data-column-group]"));
        const applyButton = picker.querySelector("[data-column-apply]");
        const toggle = picker.querySelector("[data-column-toggle]");
        const error = picker.querySelector("[data-column-error]");
        const storageError = picker.querySelector("[data-column-storage-error]");

        const hasInformation = visibility => columns.some(column =>
            column.informational && visibility[column.key]);

        // This key-to-boolean map can also represent a future named preset.
        // New columns inherit defaults; removed keys and malformed values are ignored.
        function normaliseVisibility(value) {
            const visibility = Object.fromEntries(columns.map(column => [
                column.key,
                typeof value?.[column.key] === "boolean" ? value[column.key] : defaults[column.key],
            ]));
            return hasInformation(visibility) ? visibility : { ...defaults };
        }

        function loadVisibility() {
            try {
                const saved = JSON.parse(localStorage.getItem(storageKey));
                if (saved?.version === 1 && saved.visibility && !Array.isArray(saved.visibility)
                    && typeof saved.visibility === "object") {
                    return normaliseVisibility(saved.visibility);
                }
            } catch {
                // Unavailable storage or invalid JSON must not break the table.
            }
            return { ...defaults };
        }

        let applied = loadVisibility();
        let draft = { ...applied };

        function renderVisibility() {
            table.querySelectorAll("[data-column-key]").forEach(cell => {
                if (Object.hasOwn(applied, cell.dataset.columnKey)) {
                    cell.hidden = !applied[cell.dataset.columnKey];
                }
            });
            table.querySelectorAll("[data-column-empty]").forEach(cell => {
                cell.colSpan = columns.filter(column => applied[column.key]).length;
            });
        }

        function renderDraft() {
            choices.forEach(choice => {
                choice.checked = draft[choice.dataset.columnChoice];
            });
            groups.forEach(group => {
                const children = Array.from(group.querySelectorAll("[data-column-choice]"));
                const selected = children.filter(choice => choice.checked).length;
                const checkbox = group.querySelector("[data-column-group-choice]");
                checkbox.checked = selected === children.length;
                checkbox.indeterminate = selected > 0 && selected < children.length;
            });
            const valid = hasInformation(draft);
            error.hidden = valid;
            applyButton.disabled = !valid;
        }

        choices.forEach(choice => {
            choice.addEventListener("change", () => {
                draft[choice.dataset.columnChoice] = choice.checked;
                renderDraft();
            });
        });

        groups.forEach(group => {
            const checkbox = group.querySelector("[data-column-group-choice]");
            checkbox.addEventListener("change", () => {
                group.querySelectorAll("[data-column-choice]").forEach(choice => {
                    draft[choice.dataset.columnChoice] = checkbox.checked;
                });
                renderDraft();
            });
            const expand = group.querySelector("[data-column-expand]");
            expand.addEventListener("click", () => {
                const expanded = expand.getAttribute("aria-expanded") !== "true";
                expand.setAttribute("aria-expanded", String(expanded));
                group.querySelector("[data-column-children]").hidden = !expanded;
                group.querySelector("[data-column-chevron]").textContent = expanded ? "▾" : "▸";
            });
        });

        picker.querySelector("[data-column-all]").addEventListener("click", () => {
            draft = Object.fromEntries(columns.map(column => [column.key, true]));
            renderDraft();
        });
        picker.querySelector("[data-column-reset]").addEventListener("click", () => {
            draft = { ...defaults };
            renderDraft();
        });
        applyButton.addEventListener("click", () => {
            if (!hasInformation(draft)) return;
            applied = { ...draft };
            renderVisibility();
            storageError.hidden = true;
            try {
                localStorage.setItem(storageKey, JSON.stringify({ version: 1, visibility: applied }));
            } catch {
                storageError.hidden = false;
            }
            bootstrap.Dropdown.getOrCreateInstance(toggle).hide();
            toggle.focus();
        });
        picker.addEventListener("show.bs.dropdown", () => {
            draft = { ...applied };
            renderDraft();
        });
        picker.addEventListener("hidden.bs.dropdown", () => {
            draft = { ...applied };
            renderDraft();
        });

        renderVisibility();
        renderDraft();
    });
})();
