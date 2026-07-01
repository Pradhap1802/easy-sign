/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { useService } from "@web/core/utils/hooks";

export class SignRequestListController extends ListController {
    setup() {
        super.setup();
        this.actionService = useService("action");
    }

    async openRecord(record) {
        if (this.props.resModel === "sign.template") {
            window.location.href = `/sign/template/${record.resId}/edit`;
            return;
        }
        return super.openRecord(record);
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

registry.category("views").add("sign_request_list", {
    ...listView,
    Controller: SignRequestListController,
    buttonTemplate: "easy_sign.SignRequestListView.Buttons",
});
