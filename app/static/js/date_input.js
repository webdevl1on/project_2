((root, factory) => {
    const api = factory();
    if (typeof module === "object" && module.exports) module.exports = api;
    else { Object.assign(root.TableDates ||= {}, api); api.initialiseDateInputs(); }
})(globalThis, () => {
    "use strict";
    function validParts(day, month, year, policy = {}) {
        const values = [day, month, year];
        if (values.some(value => value !== null && !Number.isInteger(value))) return false;
        if (day !== null && (day < 1 || day > 31)) return false;
        if (month !== null && (month < 1 || month > 12)) return false;
        if (year !== null && (year < (policy.min_year || 1) || year > (policy.max_year || 9999))) return false;
        if (policy.system || ((policy.required || (!policy.allow_partial && values.some(value => value !== null))) && values.includes(null))) return false;
        const leapYear = year ?? 2000;
        const leap = leapYear % 4 === 0 && (leapYear % 100 !== 0 || leapYear % 400 === 0);
        const lengths = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
        return day === null || month === null || day <= lengths[month - 1];
    }
    function initialiseDateInputs() {
        document.querySelectorAll("[data-date-input]").forEach(group => {
            const policy = JSON.parse(group.dataset.datePolicy);
            const inputs = ["day", "month", "year"].map(part => group.querySelector(`[data-date-part="${part}"]`));
            const validate = () => {
                inputs.forEach(input => input.setCustomValidity(""));
                const parts = inputs.map(input => input.value === "" ? null : Number(input.value));
                if (!validParts(...parts, policy)) inputs[0].setCustomValidity("Перевірте повноту та календарні складові дати.");
            };
            inputs.forEach(input => input.addEventListener("input", validate));
            group.closest("form")?.addEventListener("submit", event => {
                validate();
                if (!group.closest("form").checkValidity()) { event.preventDefault(); group.closest("form").reportValidity(); }
            });
        });
    }
    return { validParts, initialiseDateInputs };
});
