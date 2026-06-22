/** @odoo-module **/

import { KanbanController } from "@web/views/kanban/kanban_controller";
import { registry } from "@web/core/registry";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { useService } from "@web/core/utils/hooks";

export class SignRequestKanbanController extends KanbanController {
    setup() {
        super.setup();
        this.actionService = useService("action");
    }

    async onClickUploadPdf() {
        this.actionService.doAction({
            name: "Upload PDF",
            type: "ir.actions.act_window",
            res_model: "sign.upload.pdf.wizard",
            views: [[false, "form"]],
            target: "new",
        });
    }
}

registry.category("views").add("sign_request_kanban", {
    ...kanbanView,
    Controller: SignRequestKanbanController,
    buttonTemplate: "easy_sign.SignRequestKanbanView.Buttons",
});
