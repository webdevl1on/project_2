((root, factory) => {
    const api = factory();
    if (typeof module === "object" && module.exports) module.exports = api;
    else { root.NameCaseForms = api; api.initialise(); }
})(globalThis, () => {
    "use strict";
    const cases = ["genitive", "dative", "accusative", "instrumental", "locative", "vocative"];
    const clean = value => String(value || "").normalize("NFC").trim();

    class NameDraft {
        constructor(base, sex, forms = {}, boundBase = base, boundSex = sex) {
            this.base = clean(base); this.sex = sex || "";
            this.forms = Object.fromEntries(cases.map(key => [key, forms[key] || ""]));
            this.boundBase = clean(boundBase); this.boundSex = boundSex || "";
            this.manual = this.hasForms; this.revision = 0;
        }
        get hasForms() { return Object.values(this.forms).some(value => clean(value)); }
        get stale() { return this.hasForms && (this.boundBase !== this.base || this.boundSex !== this.sex); }
        identity(base, sex) { this.base = clean(base); this.sex = sex || ""; this.revision += 1; }
        edit(key, value) {
            if (!this.hasForms) { this.boundBase = this.base; this.boundSex = this.sex; }
            this.forms[key] = value; this.manual = true; this.revision += 1;
        }
        apply(values, confirmed = false) {
            if ((this.manual || this.stale) && this.hasForms && !confirmed) return false;
            this.forms = Object.fromEntries(cases.map(key => [key, values[key] || ""]));
            this.boundBase = this.base; this.boundSex = this.sex; this.manual = false;
            return true;
        }
        clear() {
            this.forms = Object.fromEntries(cases.map(key => [key, ""]));
            this.boundBase = this.base; this.boundSex = this.sex; this.manual = false; this.revision += 1;
        }
        keep() { this.boundBase = this.base; this.boundSex = this.sex; this.manual = true; this.revision += 1; }
    }

    function initialise() {
        document.querySelectorAll("[data-name-case-form]").forEach(form => {
            const gender = () => form.querySelector('[name="sex"]:checked')?.value || form.dataset.fixedSex || "";
            const details = form.querySelector("[data-person-details]");
            function showDetails() {
                if (details) { details.hidden = !gender(); details.disabled = !gender(); }
            }
            const controllers = [];
            form.querySelectorAll("[data-name-part]").forEach(group => {
                const base = group.querySelector("[data-base-word]");
                const inputs = Object.fromEntries([...group.querySelectorAll("[data-case]")].map(input => [input.dataset.case, input]));
                const boundBase = group.querySelector("[data-bound-base]");
                const boundSex = group.querySelector("[data-bound-sex]");
                const verified = group.querySelector("[data-case-verified]");
                const status = group.querySelector("[data-case-status]");
                const useDictionary = group.querySelector("[data-use-dictionary]");
                const actions = group.querySelector("[data-stale-actions]");
                const draft = new NameDraft(base.value, gender(), Object.fromEntries(cases.map(key => [key, inputs[key].value])), boundBase.value, boundSex.value);
                let suggestion = null;
                function render(message) {
                    boundBase.value = draft.boundBase; boundSex.value = draft.boundSex;
                    actions.hidden = !draft.stale;
                    const validationInput = base.readOnly ? inputs.genitive : base;
                    validationInput.setCustomValidity(draft.stale ? "Перевірте старі відмінки після зміни слова або статі." : "");
                    status.textContent = draft.stale ? "Увага: відмінки не відповідають поточному слову або статі." : message || "Форми збережено у поточній чернетці.";
                    group.classList.toggle("border-danger", draft.stale);
                }
                function writeInputs() { cases.forEach(key => { inputs[key].value = draft.forms[key]; }); verified.checked = false; }
                function changeIdentity() {
                    draft.identity(base.value, gender()); suggestion = null; useDictionary.hidden = true;
                    if (draft.stale) verified.checked = false;
                    render();
                }
                async function lookup() {
                    draft.identity(base.value, gender());
                    const revision = draft.revision;
                    if (!draft.base || !draft.sex) {
                        render(draft.sex ? "Основне слово не заповнене." : "Спочатку внесіть стать; ручні форми залишаються доступними.");
                        return;
                    }
                    const params = new URLSearchParams({ kind: group.dataset.namePart, word: draft.base, sex: draft.sex });
                    try {
                        const response = await fetch(`/name-dictionaries/lookup?${params}`, { headers: { Accept: "application/json" } });
                        const result = await response.json();
                        if (revision !== draft.revision) return;
                        if (!response.ok) throw new Error(result.detail || "Не вдалося перевірити словник.");
                        suggestion = result.found ? result.forms : null;
                        useDictionary.hidden = !suggestion;
                        if (suggestion && draft.apply(suggestion)) { writeInputs(); useDictionary.hidden = true; }
                        render(result.message);
                    } catch (error) {
                        if (revision === draft.revision) render(error.message || "Словник недоступний; введені форми збережено.");
                    }
                }
                base.addEventListener("input", changeIdentity);
                base.addEventListener("blur", lookup);
                Object.entries(inputs).forEach(([key, input]) => input.addEventListener("input", () => {
                    draft.edit(key, input.value); verified.checked = false; render("Ручне значення збережено; словник не перезапише його без підтвердження.");
                }));
                useDictionary.addEventListener("click", () => {
                    if (!suggestion) return;
                    if (draft.hasForms && !window.confirm("Замінити поточні відмінки формами зі словника? Ручні виправлення буде замінено.")) return;
                    draft.apply(suggestion, true); writeInputs(); useDictionary.hidden = true; render("Застосовано словник. Перевірте форми для цієї людини.");
                });
                group.querySelector("[data-clear-cases]").addEventListener("click", () => {
                    draft.clear(); writeInputs(); render("Старі форми очищено. Заповніть нові або перевірте словник.");
                });
                group.querySelector("[data-keep-cases]").addEventListener("click", () => {
                    if (!window.confirm("Залишити ці форми для нового слова або статі? Перевірте кожен відмінок вручну.")) return;
                    draft.keep(); verified.checked = false; render("Форми залишено за вашим підтвердженням; потрібна перевірка.");
                });
                render("Невідомі відмінки можна залишити порожніми.");
                controllers.push({ changeIdentity });
            });
            form.querySelectorAll('[name="sex"]').forEach(input => input.addEventListener("change", () => {
                showDetails(); controllers.forEach(controller => controller.changeIdentity());
            }));
            showDetails();
            for (const key of JSON.parse(form.dataset.errorFields || "[]")) {
                form.elements.namedItem(key)?.classList?.add("is-invalid");
            }
            form.addEventListener("submit", event => {
                if (!form.checkValidity()) { event.preventDefault(); form.reportValidity(); return; }
                const submitter = event.submitter;
                if (submitter) setTimeout(() => { submitter.disabled = true; }, 0);
            });
            const invalid = form.querySelector(".is-invalid");
            if (invalid) { invalid.closest("details")?.setAttribute("open", ""); invalid.focus(); }
        });
    }
    return { NameDraft, initialise };
});
