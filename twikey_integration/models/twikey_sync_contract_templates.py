import requests

from odoo import _, exceptions, models
from odoo.exceptions import UserError

from ..twikey.client import TwikeyError

Field_Type = {
    "text": "char",
    "number": "integer",
    "amount": "float",
    "select": "selection",
    "plan": "char",
    "email": "char",
    "url": "char",
    "checkbox": "boolean",
    "iban": "char",
    "multi": "char",
}


class SyncContractTemplates(models.AbstractModel):
    _name = "twikey.sync.contract.templates"
    _description = "Profiles in Twikey"

    def fetch_contract_templates(self):
        try:
            twikey_client = self.env["ir.config_parameter"].get_twikey_client(company=self.env.company)
            if twikey_client:
                twikey_client.refreshTokenIfRequired()
                try:
                    response = requests.get(
                        twikey_client.api_base + "/template",
                        headers=twikey_client.headers(),
                        timeout=15,
                    )
                    if response.status_code == 200:
                        return response.json()
                    else:
                        raise UserError(_("Error on syncing contract templates.") + "\n" + response.text)

                except (ValueError, requests.exceptions.RequestException) as e:
                    raise exceptions.AccessError from e
            else:
                return False
        except TwikeyError as e:
            raise UserError from e

    def search_create_template(self, ct, response):
        name = response.get("name")

        template_id = self.env["twikey.contract.template"].search(
            [("template_id_twikey", "=", ct), ("active", "in", [True, False])]
        )
        if not template_id:
            template_id = self.env["twikey.contract.template"].create(
                {
                    "template_id_twikey": ct,
                    "name": name,
                    "active": response.get("active"),
                    "type": response.get("type"),
                    "mandate_number_required": not response.get("mandateNumberRequired"),
                }
            )
            self.env['mail.channel'].sudo().search([('name', '=', 'twikey')]) \
                .message_post(subject="Configuration", body=f"Added template {name} (#{ct})")

        return template_id

    def create_search_fields(self, attribute_name, model, field_type, select_list, attr):
        fields = (
            self.env["ir.model.fields"]
            .sudo()
            .search(
                [
                    ("name", "=", attribute_name),
                    ("model_id", "=", model.id),
                ]
            )
        )

        if not fields and field_type != "iban":
            ir_fields = (
                self.env["ir.model.fields"]
                .sudo()
                .create(
                    {
                        "name": attribute_name,
                        "field_description": attr.get("description"),
                        "model_id": model.id,
                        "ttype": Field_Type[field_type],
                        "store": True,
                        "readonly": attr.get("readonly"),
                        "selection": str(select_list) if select_list != [] else "",
                    }
                )
            )

            return ir_fields

    def process_new_mandate_field_views(self, mandate_field_list, template_id):
        inherit_mandate_id = self.env.ref("twikey_integration.mandate_details_view_twikey_form")
        mandate_arch_base = _(
            '<?xml version="1.0"?>' "<data>" '<field name="url" position="after">\n'
        )
        if template_id.mandate_number_required:
            mandate_arch_base += f"""\t<field name="reference" 
                            attrs="{{
                                'required':[('contract_temp_id', '!=', {template_id.id})],
                                'invisible':[('contract_temp_id', '!=', {template_id.id})],
                                'readonly': [('state', '!=', 'pending')]
                            }}"/>\n"""

        for mandate in mandate_field_list:
            if mandate.required:
                mandate_arch_base += f"""\t<field name="{mandate.name}" 
                    attrs="{{'invisible': [('contract_temp_id', '!=', {template_id.id})], 'required': [('contract_temp_id', '=', {template_id.id})]}}"/>\n"""
            else:
                mandate_arch_base += f"""\t<field name="{mandate.name}" 
                    attrs="{{'invisible':[('contract_temp_id', '!=', {template_id.id})]}}"/>\n"""

        mandate_arch_base += _("</field>" "</data>")
        self.env["ir.ui.view"].sudo().create(
            {
                "name": f"mandate.dynamic.fields.{template_id.template_id_twikey}",
                "type": "form",
                "model": "twikey.mandate.details",
                "mode": "extension",
                "inherit_id": inherit_mandate_id.id,
                "arch_base": mandate_arch_base,
                "active": True,
            }
        )

    def process_new_field_views(self, fields_list, template_id):
        inherit_id = self.env.ref("twikey_integration.contract_template_wizard_view_twikey_form")
        arch_base = _(
            '<?xml version="1.0"?>' "<data>" '<field name="template_id" position="after">\n'
        )

        if template_id.mandate_number_required:
            arch_base += f"""\t<field name="reference" 
                            attrs="{{'required': [('template_id', '=', {template_id.id})], 'invisible':[('template_id', '!=', {template_id.id})]}}"/>\n"""

        for field in fields_list:
            if field.required:
                arch_base += f"""\t<field name="{field.name}" 
                    attrs="{{'invisible':[('template_id', '!=', {template_id.id})], 'required': [('template_id', '=', {template_id.id})]}}"/>\n"""
            else:
                arch_base += f"""\t<field name="{field.name}" attrs="{{'invisible': [('template_id', '!=', {template_id.id})]}}"/>\n"""

        arch_base += _("</field>" "</data>")
        self.env["ir.ui.view"].sudo().create(
            {
                "name": f"attribute.dynamic.fields.{template_id.template_id_twikey}",
                "type": "form",
                "model": "twikey.contract.template.wizard",
                "mode": "extension",
                "inherit_id": inherit_id.id,
                "arch_base": arch_base,
                "active": True,
            }
        )

    def process_contract_attribute(self, template_id, response):
        ct = response.get("id")
        fields_list = []
        mandate_field_list = []
        for attr in response.get("Attributes"):
            if template_id.is_creditcard() and attr.get("name") not in ["_expiry","_last","_cctype",]:
                continue
            select_list = []
            field_type = attr.get("type")
            if field_type == "select" and attr.get("Options"):
                select_list = [
                    (str(selection), str(selection)) for selection in attr.get("Options")
                ]

            attribute_name = "x_" + attr.get("name") + "_" + str(ct)

            model_id = self.env["ir.model"].search([("model", "=", "twikey.contract.template.wizard")])
            ir_fields = self.create_search_fields(
                attribute_name, model_id, field_type, select_list, attr
            )
            if ir_fields is not None:
                fields_list.append(ir_fields)

            mandate_model_id = self.env["ir.model"].search([("model", "=", "twikey.mandate.details")])
            ir_fields = self.create_search_fields(
                attribute_name, mandate_model_id, field_type, select_list, attr
            )
            if ir_fields is not None:
                mandate_field_list.append(ir_fields)

            attr_vals = {
                "contract_template_id": template_id.template_id_twikey,
                "name": attr.get("name"),
                "type": Field_Type[attr.get("type")],
            }
            if template_id.twikey_attribute_ids:
                if attr.get("name") not in template_id.twikey_attribute_ids.mapped("name"):
                    template_id.write({"twikey_attribute_ids": [(0, 0, attr_vals)]})
            else:
                template_id.write({"twikey_attribute_ids": [(0, 0, attr_vals)]})

        return fields_list, mandate_field_list

    def twikey_sync_contract_templates(self):
        resp_obj = self.fetch_contract_templates()

        if resp_obj:
            twikey_temp_list = []
            for response in resp_obj:
                ct = response.get("id")
                twikey_temp_list.append(ct)

                template_id = self.search_create_template(ct, response)
                if response.get("Attributes"):

                    fields_list, mandate_field_list = self.process_contract_attribute(
                        template_id, response
                    )

                    if fields_list:
                        self.process_new_field_views(fields_list, template_id)

                    if mandate_field_list or template_id.mandate_number_required:
                        self.process_new_mandate_field_views(mandate_field_list, template_id)

                elif template_id.mandate_number_required: # field for mandatory ref
                    self.process_new_field_views([], template_id)
                    self.process_new_mandate_field_views([], template_id)

            temp_list = [
                template.template_id_twikey
                for template in self.env["twikey.contract.template"].search([("active", "in", [True, False])])
            ]

            diff_list = []
            for temp_diff in temp_list:
                if temp_diff not in twikey_temp_list:
                    diff_list.append(temp_diff)

            if diff_list:
                for to_delete in diff_list:
                    template_ids = self.env["twikey.contract.template"].search(
                        [("template_id_twikey", "=", to_delete), ("active", "in", [True, False])]
                    )
                    if template_ids:
                        template_ids.unlink()
            return True
        return False
