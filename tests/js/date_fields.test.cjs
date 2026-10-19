const { test } = require("node:test");
const assert = require("node:assert/strict");
const { validParts } = require("../../app/static/js/date_input.js");
const { normalPriority, changeDateURL } = require("../../app/static/js/date_filter.js");
const { QueryFilterAdapter } = require("../../app/static/js/table_filters.js");
const { TableHistory } = require("../../app/static/js/table_history.js");

test("input validates exact/partial dates and calendar together", () => {
    const partial = { allow_partial: true, max_year: 2026 };
    assert.equal(validParts(29, 2, null, partial), true);
    assert.equal(validParts(31, 2, null, partial), false);
    assert.equal(validParts(29, 2, 2023, partial), false);
    assert.equal(validParts(null, null, 1995, partial), true);
    assert.equal(validParts(1, 1, 2027, partial), false);
    assert.equal(validParts(1, 1, 9999, { required: true }), true);
    assert.equal(validParts(null, 2, 2024, { required: true }), false);
    assert.equal(validParts(1, 1, 2000, { system: true }), false);
});

test("priority accepts all six permutations and rejects duplicates", () => {
    for (const value of [["year", "month", "day"], ["year", "day", "month"], ["month", "year", "day"],
        ["month", "day", "year"], ["day", "year", "month"], ["day", "month", "year"]]) assert.deepEqual(normalPriority(value), value);
    assert.deepEqual(normalPriority(["day", "day", "year"]), ["year", "month", "day"]);
});

test("date filter URL retains other filters and the existing cascade position", () => {
    const original = "http://local/table?unit_short=Перший&birth_date=old&surname=Тест&filter_order=unit_short,birth_date,surname&sort_by=rank&direction=desc";
    const url = changeDateURL(original, "birth_date", { mode: "parts", years: [1995], incomplete_only: false });
    assert.equal(url.searchParams.get("unit_short"), "Перший");
    assert.equal(url.searchParams.get("sort_by"), "rank");
    assert.equal(url.searchParams.get("filter_order"), "unit_short,birth_date,surname");
    const cleared = changeDateURL(url.href, "birth_date", {});
    assert.equal(cleared.searchParams.has("birth_date"), false);
    assert.equal(cleared.searchParams.get("filter_order"), "unit_short,surname");
    const first = changeDateURL(original, "birth_date", { years: [1996, 1995, 1996] });
    const second = changeDateURL(first.href, "birth_date", { years: [1995, 1996] });
    assert.equal(first.href, second.href);
});

test("date filter shares hidden-column cleanup, undo and redo with existing adapter", () => {
    const location = { href: "http://local/table?unit_short=Перший&birth_date=encoded&filter_order=unit_short,birth_date&birth_date_priority=month,day,year&sort_by=birth_date" };
    const adapter = new QueryFilterAdapter({ keys: ["unit_short", "birth_date"] }, location);
    const before = adapter.read();
    const after = adapter.withVisible(["unit_short"], before);
    const history = new TableHistory(); history.push(before); history.push(after);
    assert.deepEqual(adapter.read(adapter.urlFor(history.move(-1))), before);
    assert.equal(adapter.urlFor(history.move(1)).searchParams.has("birth_date"), false);
    assert.equal(adapter.urlFor(after).searchParams.get("birth_date_priority"), "month,day,year");
});
