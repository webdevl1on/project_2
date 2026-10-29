/* Presentation state is table-local; presets/history keep their existing contracts. */
((root,factory)=>{
    const api=factory();
    if(typeof module==='object'&&module.exports)module.exports=api;
    else Object.assign(root.TableColumns ||= {},api);
})(globalThis,()=>{
    'use strict';
    const PALETTE=['#fff3cd','#d1e7dd','#cfe2ff','#f8d7da','#e2e3e5'];
    const bounded=(value,min,max,fallback)=>typeof value==='number'&&Number.isFinite(value)?Math.min(max,Math.max(min,Math.round(value))):fallback;
    class AppearanceModel {
        constructor(keys){this.keys=keys;}
        normalise(value={}){
            if(!value||typeof value!=='object'||value.version!==1)value={};
            const fonts={},fills={};
            for(const key of this.keys)if(typeof value.fonts?.[key]==='number')fonts[key]=bounded(value.fonts[key],10,32,14);
            if(value.fills&&typeof value.fills==='object'&&!Array.isArray(value.fills))for(const [key,color] of Object.entries(value.fills)){
                try{const pair=JSON.parse(key);if(Array.isArray(pair)&&pair.length===2&&typeof pair[0]==='string'&&pair[0].length<=120&&this.keys.includes(pair[1])&&PALETTE.includes(color))fills[key]=color;}catch{/* Ignore malformed or obsolete annotations. */}
            }
            return {version:1,rowHeight:bounded(value.rowHeight,24,180,40),fontSize:bounded(value.fontSize,10,28,14),scale:[75,90,100,110,125].includes(value.scale)?value.scale:100,fonts,fills};
        }
    }
    class TableAppearance {
        constructor(controller){
            controller.appearance=this;
            this.controller=controller;this.table=controller.table;this.picker=controller.picker;
            this.model=new AppearanceModel(controller.model.keys);this.key=`project2:table-appearance:${controller.config.id}`;
            this.state=this.model.normalise(controller.storage.read(this.key,{}));
            const pick=selector=>this.picker.querySelector(selector);
            this.height=pick('[data-row-height]');this.custom=pick('[data-row-height-custom]');
            this.font=pick('[data-table-font]');this.scale=pick('[data-table-scale]');this.column=pick('[data-font-column]');this.columnFont=pick('[data-column-font]');
            this.height?.addEventListener('change',()=>{
                this.custom.disabled=this.height.value!=='custom';
                if(this.height.value==='custom'){this.custom.focus();return;}
                this.update({rowHeight:Number(this.height.value)});
            });
            this.custom?.addEventListener('change',()=>this.update({rowHeight:Number(this.custom.value)}));
            this.font?.addEventListener('change',()=>this.update({fontSize:Number(this.font.value)}));
            this.scale?.addEventListener('change',()=>this.update({scale:Number(this.scale.value)}));
            this.column?.addEventListener('change',()=>this.renderFontInput());
            this.columnFont?.addEventListener('change',()=>{
                const fonts={...this.state.fonts};if(this.columnFont.value==='')delete fonts[this.column.value];else fonts[this.column.value]=Number(this.columnFont.value);
                this.update({fonts});
            });
            pick('[data-column-font-reset]')?.addEventListener('click',()=>{const fonts={...this.state.fonts};delete fonts[this.column.value];this.update({fonts});});
            this.picker.querySelectorAll('[data-cell-fill]').forEach(button=>button.addEventListener('click',()=>{
                const selected=controller.selection?.selected;if(!selected?.size){controller.notice('Спочатку виділіть клітинки, рядки або колонки.');return;}
                const fills={...this.state.fills};for(const cell of selected){const key=this.cellKey(cell);if(!key)continue;if(button.dataset.cellFill)fills[key]=button.dataset.cellFill;else delete fills[key];}
                this.update({fills});
            }));
            this.apply();
        }
        cellKey(cell){const row=cell.closest('tr')?.dataset.rowKey;return row?JSON.stringify([row,cell.dataset.columnKey]):null;}
        update(changes){this.state=this.model.normalise({...this.state,...changes});this.controller.storage.write(this.key,this.state);this.apply();}
        renderFontInput(){if(this.columnFont)this.columnFont.value=this.state.fonts[this.column.value]||'';}
        apply(){
            const s=this.state,scale=s.scale/100;this.table.dataset.tableStyled='';
            this.table.style.setProperty('--table-row-height',`${s.rowHeight*scale}px`);
            this.table.style.setProperty('--table-font-size',`${s.fontSize*scale}px`);
            this.table.style.setProperty('--table-cell-pad',`${4*scale}px`);
            this.table.querySelectorAll('[data-column-key]').forEach(cell=>{
                cell.style.fontSize=`${(s.fonts[cell.dataset.columnKey]||s.fontSize)*scale}px`;
                if(cell.tagName!=='TD')return;const color=s.fills[this.cellKey(cell)];
                cell.toggleAttribute('data-user-fill',!!color);if(color)cell.style.setProperty('--table-user-fill',color);else cell.style.removeProperty('--table-user-fill');
            });
            if(this.height){this.height.value=[28,40,64].includes(s.rowHeight)?String(s.rowHeight):'custom';this.custom.value=s.rowHeight;this.custom.disabled=this.height.value!=='custom';this.font.value=s.fontSize;this.scale.value=s.scale;this.renderFontInput();}
            this.controller.interactions.renderWidths();
        }
    }
    return {AppearanceModel,TableAppearance,PALETTE};
});
