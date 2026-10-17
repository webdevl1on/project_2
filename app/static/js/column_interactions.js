(() => {
    "use strict";
    class ColumnInteractions {
        constructor(controller) {
            this.controller = controller;
            this.table = controller.table;
            this.table.dataset.columnSizing = "";
            this.colgroup = document.createElement("colgroup");
            this.table.prepend(this.colgroup);
            this.suppressUntil = 0;
            this.headers = Array.from(this.table.querySelectorAll("thead th[data-column-key]"));
            this.headers.forEach(header => {
                const column = controller.model.columns.find(column => column.key === header.dataset.columnKey);
                const movable = !column.system && column.draggable !== false;
                header.draggable = movable;
                header.querySelectorAll("a").forEach(link => { link.draggable = false; });
                let allowed = true;
                header.addEventListener("pointerdown", event => {
                    allowed = !event.target.closest("button,input,select,textarea,form,.dropdown-menu,[data-column-resize]");
                });
                header.addEventListener("dragstart", event => {
                    if (!movable || !allowed || this.resizing) { event.preventDefault(); return; }
                    this.dragged = column.key;
                    event.dataTransfer.setData("application/x-table-column", controller.config.id);
                    event.dataTransfer.effectAllowed = "move";
                    header.classList.add("column-dragging");
                    this.suppressUntil = Infinity;
                });
                header.addEventListener("dragover", event => {
                    if (!this.dragged || !movable || column.key === this.dragged) return;
                    event.preventDefault();
                    this.clearIndicators();
                    const rect = header.getBoundingClientRect();
                    this.destination = { key: column.key, after: event.clientX > rect.x + rect.width / 2 };
                    header.classList.add(this.destination.after ? "column-drop-after" : "column-drop-before");
                });
                header.addEventListener("drop", event => {
                    if (!this.dragged || !movable || event.dataTransfer.getData("application/x-table-column") !== controller.config.id) return;
                    event.preventDefault();
                    const destination = this.destination;
                    if (destination && destination.key !== this.dragged) {
                        const layout = controller.getLayout();
                        layout.order = layout.order.filter(key => key !== this.dragged);
                        const index = layout.order.indexOf(destination.key) + (destination.after ? 1 : 0);
                        layout.order.splice(index, 0, this.dragged);
                        controller.commitLayout(layout, "drag");
                    }
                    this.finishDrag();
                });
                header.addEventListener("dragend", () => this.finishDrag());
                if (column.informational && column.resizable !== false && !column.system) this.addResize(header, column);
            });
            this.table.addEventListener("click", event => {
                if (this.resizing || Date.now() < this.suppressUntil || event.target.closest("[data-column-resize]")) {
                    event.preventDefault();
                    event.stopImmediatePropagation();
                }
            }, true);
            this.renderWidths();
        }
        clearIndicators() {
            this.headers.forEach(header => header.classList.remove("column-drop-before", "column-drop-after"));
        }
        finishDrag() {
            this.dragged = null;
            this.destination = null;
            this.clearIndicators();
            this.headers.forEach(header => header.classList.remove("column-dragging"));
            this.suppressUntil = Date.now() + 200;
        }
        addResize(header, column) {
            const handle = document.createElement("span");
            handle.dataset.columnResize = column.key;
            handle.className = "column-resize-handle";
            handle.draggable = false;
            handle.tabIndex = 0;
            handle.setAttribute("role", "separator");
            handle.setAttribute("aria-orientation", "vertical");
            handle.setAttribute("aria-label", `Змінити ширину: ${column.label}`);
            handle.setAttribute("aria-valuemin", column.min_width || 100);
            header.append(handle);
            handle.addEventListener("pointerdown", event => {
                if (event.button !== 0) return;
                event.preventDefault();
                event.stopPropagation();
                this.resizing = { key: column.key, x: event.clientX, width: header.getBoundingClientRect().width };
                this.table.classList.add("column-resizing");
                handle.setPointerCapture(event.pointerId);
            });
            handle.addEventListener("pointermove", event => {
                if (!this.resizing || this.resizing.key !== column.key) return;
                this.setWidth(column.key, this.resizing.width + event.clientX - this.resizing.x);
            });
            const end = () => {
                if (!this.resizing) return;
                this.resizing = null;
                this.table.classList.remove("column-resizing");
                this.suppressUntil = Date.now() + 200;
                this.controller.storage.save(this.controller.state);
            };
            handle.addEventListener("pointerup", end);
            handle.addEventListener("pointercancel", end);
            handle.addEventListener("lostpointercapture", end);
            handle.addEventListener("keydown", event => {
                if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
                event.preventDefault();
                event.stopPropagation();
                this.setWidth(column.key, this.controller.state.widths[column.key] + (event.key === "ArrowRight" ? 10 : -10));
                this.controller.storage.save(this.controller.state);
            });
        }
        setWidth(key, value) {
            this.controller.state.widths = this.controller.model.widths({ ...this.controller.state.widths, [key]: value });
            this.renderWidths();
        }
        renderWidths() {
            const { layout, widths } = this.controller.state;
            const cols = layout.visible.map(key => {
                const col = document.createElement("col");
                col.style.width = `${widths[key]}px`;
                return col;
            });
            this.colgroup.replaceChildren(...cols);
            this.table.style.width = `${layout.visible.reduce((total, key) => total + widths[key], 0)}px`;
            this.table.querySelectorAll("[data-column-resize]").forEach(handle => {
                handle.setAttribute("aria-valuenow", Math.round(widths[handle.dataset.columnResize]));
            });
        }
    }
    globalThis.TableColumns.ColumnInteractions = ColumnInteractions;
})();
