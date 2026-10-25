/* Run from the repository root:
 * PYTHON=.venv/bin/python CHROMIUM_PATH=/usr/bin/chromium node tests/browser/column_visibility.cjs
 * Requires Playwright for Node; Bootstrap is fetched from the same CDN as the page.
 */
const assert = require("node:assert/strict");
const { spawn, execFileSync } = require("node:child_process");
const net = require("node:net");
const path = require("node:path");
const { chromium } = require("playwright");

async function main() {
    const root = path.resolve(__dirname, "../..");
    const port = await new Promise(resolve => {
        const socket = net.createServer();
        socket.listen(0, "127.0.0.1", () => {
            const port = socket.address().port;
            socket.close(() => resolve(port));
        });
    });
    const base = `http://127.0.0.1:${port}`;
    const assets = {};
    for (const version of ["5.3.3", "5.3.8"]) {
        for (const file of ["js/bootstrap.bundle.min.js", "css/bootstrap.min.css"]) {
            assets[`${version}/${file}`] = execFileSync("curl", ["--fail", "--silent", "--show-error", "--location",
                `https://cdn.jsdelivr.net/npm/bootstrap@${version}/dist/${file}`]);
        }
    }
    const server = spawn(process.env.PYTHON || "python3",
        ["-m", "tests.browser.serve_column_visibility", String(port)], { cwd: root });
    let serverOutput = "";
    server.stderr.on("data", data => { serverOutput += data; });
    let browser;
    try {
        let ready = false;
        for (let attempt = 0; attempt < 100; attempt += 1) {
            if (server.exitCode !== null) throw new Error(serverOutput);
            try {
                if ((await fetch(`${base}/person-positions`)).ok) { ready = true; break; }
            } catch { /* Server is still starting. */ }
            await new Promise(resolve => setTimeout(resolve, 100));
        }
        assert.ok(ready, serverOutput || "Test server did not start");
        browser = await chromium.launch({
            ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}),
            headless: true,
            args: ["--no-sandbox"],
        });
        const context = await browser.newContext();
        context.setDefaultTimeout(10000);
        context.setDefaultNavigationTimeout(20000);
        await context.route("https://cdn.jsdelivr.net/npm/bootstrap@*/dist/**", route => {
            const file = route.request().url().split("/dist/")[1];
            const version = route.request().url().split("bootstrap@")[1].split("/")[0];
            return route.fulfill({ body: assets[`${version}/${file}`], contentType: file.endsWith(".js") ? "application/javascript" : "text/css" });
        });
        const suites = ["presets", "layout", "filters", "history", "integration", "dates", "domain_dates", "catalog", "copy", "staff"];
        if (process.env.COLUMN_STAGE) {
            assert.ok(suites.includes(process.env.COLUMN_STAGE));
            await require(`./${process.env.COLUMN_STAGE}.cjs`)({ context, base });
            return;
        }
        const page = await context.newPage();
        const errors = [];
        context.on("page", tab => tab.on("pageerror", error => errors.push(error.message)));
        page.on("pageerror", error => errors.push(error.message));
        const picker = page.locator("[data-column-picker]");
        const table = page.locator("#person-positions");
        const toggle = picker.locator("[data-column-toggle]");
        const choice = key => picker.locator(`[data-visibility-tree] [data-column-choice="${key}"]`);
        const group = key => picker.locator(`[data-visibility-tree] [data-column-group]:has([aria-controls$="-group-${key}"])`);
        const visibleHeaders = () => table.locator("thead th:visible").count();
        const visit = (query = "") => page.goto(`${base}/person-positions${query}`);
        const apply = () => picker.locator("[data-column-apply]").click();
        async function scenario(name, check) { await check(); console.log(`PASS: ${name}`); }

        await scenario("defaults without saved settings", async () => {
            await visit();
            assert.equal(await visibleHeaders(), 12);
            assert.equal(await table.locator("tbody tr").count(), 3);
            assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem("project2:table-history:person-positions")).entries.length), 1);
        });

        await scenario("whole group, partial indeterminate, collapse and apply", async () => {
            await toggle.click();
            const positionGroup = group("position");
            const checkbox = positionGroup.locator("[data-column-group-choice]");
            await checkbox.check();
            await checkbox.uncheck();
            assert.equal(await positionGroup.locator("[data-column-choice]:checked").count(), 0);
            await checkbox.check();
            assert.equal(await positionGroup.locator("[data-column-choice]:checked").count(), 11);
            await checkbox.uncheck();
            assert.equal(await visibleHeaders(), 12); // Draft does not change the table yet.
            await choice("position_number").check();
            assert.equal(await checkbox.evaluate(element => element.indeterminate), true);
            await positionGroup.locator("[data-column-expand]").click();
            assert.equal(await choice("position_number").isVisible(), false);
            await positionGroup.locator("[data-column-expand]").click();
            assert.equal(await choice("position_number").isChecked(), true);
            await apply();
            assert.equal(await visibleHeaders(), 9);
            assert.equal(await table.locator('td[data-column-key="unit_short"]:visible').count(), 0);
            assert.equal(await table.locator("tbody tr").count(), 3);
        });

        await scenario("reload persistence and closing without applying", async () => {
            await page.reload();
            assert.equal(await visibleHeaders(), 9);
            await toggle.click();
            await choice("surname").uncheck();
            await page.keyboard.press("Escape");
            assert.equal(await table.locator('th[data-column-key="surname"]').isVisible(), true);
            await toggle.click();
            assert.equal(await choice("surname").isChecked(), true);
            await picker.locator("[data-column-reset]").click();
            assert.equal(await picker.locator("[data-visibility-tree] [data-column-choice]:checked").count(), 12);
            assert.equal(await visibleHeaders(), 9);
            await apply();
            assert.equal(await visibleHeaders(), 12);
        });

        await scenario("cannot hide every informational column; show all", async () => {
            await toggle.click();
            await group("position").locator("[data-column-group-choice]").check();
            await group("position").locator("[data-column-group-choice]").uncheck();
            await group("person").locator("[data-column-group-choice]").check();
            await group("person").locator("[data-column-group-choice]").uncheck();
            await group("rank").locator("[data-column-group-choice]").check();
            await group("rank").locator("[data-column-group-choice]").uncheck();
            assert.equal(await picker.locator("[data-column-apply]").isDisabled(), true);
            assert.equal(await picker.locator("[data-column-error]").isVisible(), true);
            assert.equal(await choice("row_number").isChecked(), true);
            assert.equal(await choice("assignment").isChecked(), true);
            await picker.locator("[data-column-all]").click();
            assert.equal(await picker.locator("[data-column-apply]").isEnabled(), true);
            await apply();
        });

        await scenario("malformed storage, obsolete keys and invalid selections", async () => {
            const values = ["broken json", "null", "[]", JSON.stringify({ version: 99 }),
                JSON.stringify({ version: 1, visibility: { removed: false, surname: "wrong" } }),
                JSON.stringify({ version: 1, visibility: Object.fromEntries(
                    ["position_number", "unit_short", "name_short", "name_nominative", "rank", "full_name", "surname", "name", "patronymic", "birth_date"].map(key => [key, false])) })];
            for (const value of values) {
                await page.evaluate(value => localStorage.setItem("project2:table-columns:person-positions", value), value);
                await page.reload();
                assert.equal(await visibleHeaders(), 12);
            }
        });

        await scenario("unrelated hidden columns preserve visible cascade filters, sorting and assignment forms", async () => {
            await toggle.click();
            await choice("surname").uncheck();
            await choice("name_short").uncheck();
            await apply();
            await table.locator('th[data-column-key="unit_short"] [data-bs-toggle="dropdown"]').click();
            const menu = page.locator('[data-filter-key="unit_short"]');
            await menu.locator('input[value="Перший"]').check();
            await Promise.all([page.waitForURL(url => url.searchParams.has("unit_short")), menu.locator(".apply-filter").click()]);
            assert.equal(await table.locator("tbody tr").count(), 2);
            assert.equal(await table.locator('th[data-column-key="surname"]').isVisible(), false);
            await Promise.all([page.waitForURL(url => url.searchParams.get("direction") === "desc"),
                table.locator('th[data-column-key="position_number"] .position-column-heading > a').click()]);
            assert.deepEqual((await table.locator('td[data-column-key="position_number"]').allTextContents()).map(value => value.trim()), ["20", "10"]);
            const url = page.url();
            assert.equal(new URL(url).searchParams.get("filter_order"), "unit_short");
            await toggle.click();
            await choice("rank").uncheck();
            await apply();
            assert.equal(page.url(), url);
            const form = table.locator("tbody tr").first().locator("form");
            await form.locator('[data-person-label]').click();
            await form.locator('[data-person-option=""]').click();
            await form.locator('[type=submit]').click();
            await page.locator('#staff-assignment-confirm').waitFor({state:'visible'});
            await Promise.all([page.waitForNavigation(),page.locator('[data-assignment-confirm-yes]').click()]);
            assert.equal(await table.locator("tbody tr").first().locator('[data-person-value]').inputValue(), "");
            const restored=table.locator("tbody tr").first().locator("form");
            await restored.locator('[data-person-label]').click();
            await restored.locator('[data-person-option="2"]').click();
            await Promise.all([page.waitForNavigation(),restored.locator('[type=submit]').click()]);
            assert.equal(await table.locator("tbody tr").first().locator('[data-person-value]').inputValue(), "2");
            assert.equal(new URL(page.url()).searchParams.get('filter_order'),'unit_short');
            assert.equal(new URL(page.url()).searchParams.get('direction'),'desc');
            assert.equal(await visibleHeaders(), 9);
        });

        await scenario("empty-table colspan follows visibility", async () => {
            await visit("?position_number=999999");
            assert.equal(await table.locator("[data-column-empty]").getAttribute("colspan"), String(await visibleHeaders()));
        });

        await scenario("reusable component, independent storage and configured hidden default", async () => {
            await page.goto(`${base}/_column-test/two-tables`);
            const first = picker.nth(0);
            const second = picker.nth(1);
            assert.equal(await page.locator('#example-first th[data-column-key="code"]').isVisible(), false);
            await first.locator("[data-column-toggle]").click();
            await first.locator('[data-visibility-tree] [data-column-choice="code"]').check();
            await first.locator('[data-visibility-tree] [data-column-choice="title"]').uncheck();
            await first.locator("[data-column-apply]").click();
            assert.equal(await page.locator('#example-first th[data-column-key="code"]').isVisible(), true);
            assert.equal(await page.locator('#example-second th[data-column-key="code"]').isVisible(), false);
            await page.reload();
            assert.equal(await page.locator('#example-first th[data-column-key="title"]').isVisible(), false);
            await first.locator("[data-column-toggle]").click();
            await first.locator("[data-column-reset]").click();
            assert.equal(await first.locator('[data-visibility-tree] [data-column-choice="title"]').isChecked(), true);
            assert.equal(await first.locator('[data-visibility-tree] [data-column-choice="code"]').isChecked(), false);
            await first.locator("[data-column-apply]").click();
            assert.equal(await page.locator('#example-first th[data-column-key="code"]').isVisible(), false);
            await second.locator("[data-column-toggle]").click();
            await second.locator('[data-visibility-tree] [data-column-choice="title"]').uncheck();
            assert.equal(await second.locator("[data-column-apply]").isDisabled(), true);
        });

        await scenario("storage denial does not break column controls", async () => {
            const blocked = await context.newPage();
            await blocked.addInitScript(() => {
                Object.defineProperty(window, "localStorage", { get() { throw new Error("Storage denied"); } });
            });
            await blocked.goto(`${base}/person-positions`);
            await blocked.locator("[data-column-toggle]").click();
            await blocked.locator('[data-visibility-tree] [data-column-choice="surname"]').uncheck();
            await blocked.locator("[data-column-apply]").click();
            assert.equal(await blocked.locator('th[data-column-key="surname"]').isVisible(), false);
            assert.equal(await blocked.locator("[data-column-storage-error]").isVisible(), true);
            await blocked.close();
        });

        await scenario("mobile dropdown fits viewport and no JavaScript errors", async () => {
            await visit();
            await page.setViewportSize({ width: 390, height: 844 });
            await toggle.click();
            const box = await picker.locator(".column-visibility-menu").boundingBox();
            assert.ok(box.x >= 0 && box.x + box.width <= 390);
            assert.deepEqual(errors, []);
        });
        for (const suite of suites) { await context.request.post(base+"/_column-test/reset"); await require(`./${suite}.cjs`)({ context, base }); }
    } finally {
        if (browser) await browser.close();
        server.kill();
    }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
