((root, factory) => {
    const api = factory();
    if (typeof module === "object" && module.exports) module.exports = api;
    else { Object.assign(root.TableDates ||= {}, api); document.querySelectorAll("[data-date-menu]").forEach(menu => new api.DateMenu(menu)); }
})(globalThis, () => {
    "use strict";
    const DEFAULT = ["year", "month", "day"];
    const clone = value => JSON.parse(JSON.stringify(value));
    const normalPriority = value => Array.isArray(value) && value.length === 3 && new Set(value).size === 3 && value.every(part => DEFAULT.includes(part)) ? [...value] : [...DEFAULT];
    function changeDateURL(current, key, spec) {
        const url = new URL(current);
        // Same canonical field/selection order as DateFilter.to_json on the server.
        spec = { days: spec.days || [], end: spec.end || null, incomplete_only: !!spec.incomplete_only,
            mode: spec.mode || "parts", months: spec.months || [], start: spec.start || null, years: spec.years || [] };
        for (const part of ["days", "months", "years"]) spec[part] = [...new Set(spec[part])].sort((a, b) => a - b);
        if (spec.mode === "parts") { spec.start = null; spec.end = null; }
        else { spec.days = []; spec.months = []; spec.years = []; }
        const active = spec.incomplete_only || spec.years?.length || spec.months?.length || spec.days?.length || spec.start || spec.end;
        url.searchParams.delete(key);
        if (active) url.searchParams.set(key, JSON.stringify(spec));
        let order = (url.searchParams.get("filter_order") || "").split(",").filter(Boolean).filter(value => value !== key);
        // Updating an active filter retains its cascade position.
        const previous = (new URL(current).searchParams.get("filter_order") || "").split(",").filter(Boolean);
        if (active) { order = previous.includes(key) ? previous : [...order, key]; }
        url.searchParams.set("filter_order", [...new Set(order)].join(","));
        return url;
    }
    class DateMenu {
        constructor(menu) {
            this.menu = menu;
            this.key = menu.dataset.dateColumnKey;
            this.table = menu.dataset.dateTableId;
            this.field = JSON.parse(menu.dataset.dateField);
            this.initial = JSON.parse(menu.dataset.dateState);
            this.options = JSON.parse(menu.dataset.dateOptions);
            this.parameter = `${this.key}_priority`;
            this.storageKey = `project2:date-priority:${this.table}:${this.key}`;
            this.priority = normalPriority(JSON.parse(menu.dataset.datePriority));
            try {
                const saved = JSON.parse(localStorage.getItem(this.storageKey));
                if (!new URL(location.href).searchParams.has(this.parameter) && saved?.version === 1) this.priority = normalPriority(saved.priority);
            } catch { /* Invalid/unavailable storage: retain server defaults. */ }
            const url = new URL(location.href);
            if (!url.searchParams.has(this.parameter) && url.searchParams.get("sort_by") === this.key && this.priority.join(",") !== DEFAULT.join(",")) {
                url.searchParams.set(this.parameter, this.priority.join(","));
                location.replace(url.href);
                return;
            }
            this.restore();
            menu.querySelector("[data-date-mode]").addEventListener("change", event => { this.draft.mode = event.target.value; this.renderMode(); });
            menu.querySelectorAll("[data-date-search]").forEach(input => input.addEventListener("input", () => this.renderChoices(input.dataset.dateSearch)));
            menu.querySelector("[data-date-cancel]").addEventListener("click", () => { this.restore(); this.close(); });
            menu.parentElement.addEventListener("hidden.bs.dropdown", () => this.restore());
            menu.querySelector("[data-date-clear]").addEventListener("click", () => {
                location.assign(changeDateURL(location.href, this.key, {}).href);
            });
            menu.querySelector("[data-date-apply]").addEventListener("click", () => this.apply());
            menu.querySelectorAll("[data-date-sort]").forEach(button => button.addEventListener("click", () => this.sort(button.dataset.dateSort)));
        }
        close() { bootstrap.Dropdown.getOrCreateInstance(this.menu.previousElementSibling).hide(); }
        error(message) { const node = this.menu.querySelector("[data-date-error]"); node.textContent = message; node.hidden = !message; }
        restore() {
            this.draft = clone(this.initial);
            this.draftPriority = [...this.priority];
            this.error("");
            this.menu.querySelector("[data-date-mode]").value = this.draft.mode;
            this.menu.querySelectorAll("[data-date-boundary]").forEach(input => { input.value = this.draft[input.dataset.dateBoundary] || ""; });
            const incomplete = this.menu.querySelector("[data-date-incomplete]");
            if (incomplete) incomplete.checked = this.draft.incomplete_only;
            this.menu.querySelectorAll("[data-date-search]").forEach(input => { input.value = ""; });
            ["years", "months", "days"].forEach(part => this.renderChoices(part));
            this.renderPriority(); this.renderMode();
        }
        renderMode() {
            this.menu.querySelector("[data-date-parts]").hidden = this.draft.mode !== "parts";
            this.menu.querySelector("[data-date-range]").hidden = this.draft.mode !== "range";
        }
        renderChoices(part) {
            const target = this.menu.querySelector(`[data-date-choices="${part}"]`);
            const search = this.menu.querySelector(`[data-date-search="${part}"]`).value.trim();
            const available = part === "years" ? (this.options.years || []) : Array.from({ length: part === "months" ? 12 : 31 }, (_, index) => index + 1);
            const values = [...new Set([...available, ...(this.draft[part] || [])])];
            if (part === "years" && /^\d{1,4}$/.test(search) && Number(search) >= this.field.min_year && Number(search) <= this.field.max_year) values.push(Number(search));
            target.replaceChildren();
            [...new Set(values)].sort((a, b) => part === "years" ? b - a : a - b).filter(value => String(value).includes(search)).forEach(value => {
                const label = document.createElement("label"); label.className = "date-choice";
                const checkbox = document.createElement("input"); checkbox.type = "checkbox"; checkbox.value = value;
                checkbox.checked = (this.draft[part] || []).includes(value);
                checkbox.addEventListener("change", () => {
                    this.draft[part] = (this.draft[part] || []).filter(item => item !== value);
                    if (checkbox.checked) this.draft[part].push(value);
                });
                label.append(checkbox, ` ${value}`); target.append(label);
            });
        }
        renderPriority() {
            const target = this.menu.querySelector("[data-date-priority-list]"); target.replaceChildren();
            this.draftPriority.forEach((part, index) => {
                const row = document.createElement("div"); row.className = "date-priority-row"; row.dataset.datePriorityPart = part;
                const label = document.createElement("span"); label.textContent = { year: "Рік", month: "Місяць", day: "День" }[part]; row.append(label);
                for (const delta of [-1, 1]) {
                    const button = document.createElement("button"); button.type = "button"; button.textContent = delta < 0 ? "↑" : "↓";
                    button.className = "btn btn-sm btn-outline-secondary"; button.dataset.dateMove = delta;
                    button.setAttribute("aria-label", `${label.textContent}: ${delta < 0 ? "вище" : "нижче"}`);
                    button.disabled = index + delta < 0 || index + delta >= 3;
                    button.addEventListener("click", () => { [this.draftPriority[index], this.draftPriority[index + delta]] = [this.draftPriority[index + delta], this.draftPriority[index]]; this.renderPriority(); });
                    row.append(button);
                }
                target.append(row);
            });
        }
        persistPriority() {
            try { localStorage.setItem(this.storageKey, JSON.stringify({ version: 1, priority: this.draftPriority })); return true; }
            catch { this.error("Не вдалося зберегти пріоритет у браузері."); return false; }
        }
        sort(direction) {
            this.persistPriority(); // URL still preserves the priority when storage is unavailable.
            const url = new URL(location.href);
            url.searchParams.set("sort_by", this.key); url.searchParams.set("direction", direction);
            url.searchParams.set(this.parameter, this.draftPriority.join(",")); location.assign(url.href);
        }
        apply() {
            const spec = clone(this.draft);
            spec.incomplete_only = this.menu.querySelector("[data-date-incomplete]")?.checked || false;
            this.menu.querySelectorAll("[data-date-boundary]").forEach(input => { spec[input.dataset.dateBoundary] = input.value || null; });
            if (spec.mode === "parts") { spec.start = null; spec.end = null; }
            else { spec.years = []; spec.months = []; spec.days = []; }
            if (spec.start && spec.end && spec.start > spec.end) { this.error("Дата «Від» не може бути пізнішою за «До»."); return; }
            this.persistPriority();
            const url = changeDateURL(location.href, this.key, spec);
            url.searchParams.set(this.parameter, this.draftPriority.join(","));
            if (this.draftPriority.join(",") !== this.priority.join(",")) url.searchParams.set("sort_by", this.key);
            location.assign(url.href);
        }
    }
    return { normalPriority, changeDateURL, DateMenu };
});
