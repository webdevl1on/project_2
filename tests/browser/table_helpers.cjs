async function openAssignment(row) {
    const editor=row.locator('[data-assignment-editor]');
    if(await editor.isHidden())await row.locator('[data-assignment-toggle]').click();
    await editor.waitFor({state:'visible'});
}
async function openStaffActions(page){
    const details=page.locator('.page-heading > details');
    if(!await details.evaluate(node=>node.open))await details.locator(':scope > summary').click();
}
module.exports={openAssignment,openStaffActions};
