async function openAssignment(row) {
    const editor=row.locator('[data-assignment-editor]');
    // A real drag/resize intentionally suppresses accidental table clicks for 200 ms.
    if(await editor.isHidden())await row.locator('[data-assignment-toggle]').click({delay:250});
    await editor.waitFor({state:'visible'});
}
async function openStaffActions(page){
    const details=page.locator('.page-heading > details');
    if(!await details.evaluate(node=>node.open))await details.locator(':scope > summary').click();
}
module.exports={openAssignment,openStaffActions};
