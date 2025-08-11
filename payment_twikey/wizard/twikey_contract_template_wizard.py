import logging

from odoo import api, fields, models

from ..twikey.client import TwikeyError
from ..utils import (
    get_error_msg,
    get_success_msg,
    get_twikey_customer,
    field_name_from_attribute,
)

_logger = logging.getLogger(__name__)

language_dict = {
    "en_US": "en",
    "fr_FR": "fr",
    "nl_NL": "nl",
    "nl_BE": "nl",
    "de_DE": "de",
    "pt_PT": "pt",
    "es_ES": "es",
    "it_IT": "it",
}

class TwikeyContractTemplateWizard(models.TransientModel):
    _name = "twikey.contract.template.wizard"
    _description = "Wizard for Select Twikey Profile"

    name = fields.Char()
    reference = fields.Char(string="Mandate number")
    partner_id = fields.Many2one(comodel_name="res.partner")

    template_id = fields.Many2one("twikey.contract.template", string="Twikey Profile id", ondelete="cascade", )

    # MAIL
    mail_template_id = fields.Many2one(comodel_name='mail.template', string="Email template", store=True, )
    mail_subject = fields.Char(string="Subject", compute='_compute_mail_subject_body_partners', store=True, )
    mail_body = fields.Html(string="Contents", sanitize_style=True, compute='_compute_mail_subject_body_partners',
                            store=True, )

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        active_id = self.env.context.get('active_id')
        active_model = self.env.context.get('active_model')
        if active_model == 'res.partner' and active_id:
            res['partner_id'] = active_id
        return res

    @api.model
    def _get_default_mail_subject(self, partner, mail_template, mail_lang):
        return self._get_mail_default_field_value_from_template(mail_template, mail_lang, partner, 'subject', )

    @api.model
    def _get_default_mail_body(self, partner, mail_template, mail_lang):
        return self._get_mail_default_field_value_from_template(
            mail_template,mail_lang,partner,'body_html',options={'post_process': True},
        )

    @api.model
    def _get_mail_default_field_value_from_template(self, mail_template, lang, partner, field, **kwargs):
        if not mail_template:
            return
        return mail_template.with_context(lang=lang)._render_field(field, partner.ids, **kwargs)[partner._origin.id]

    @api.onchange('mail_template_id')
    def _compute_mail_subject_body_partners(self):
        self.mail_template_id = self.env.ref('payment_twikey.mandate_email_invite')
        if self.mail_template_id and self.partner_id:
            lang = self.partner_id.lang
            self.mail_subject = self._get_default_mail_subject(self.partner_id, self.mail_template_id, lang)
            self.mail_body = self._get_default_mail_body(self.partner_id, self.mail_template_id, lang)
        else:
            self.mail_subject = self.mail_body = None


    def action_confirm(self):
        payload = get_twikey_customer(self.partner_id)
        payload["ct"] = self.template_id.twikey_id
        if payload.get("email"):
            payload["sendInvite"] = True

        # Get the keys
        sp_lst = [
            field_name_from_attribute(attr.name, self.template_id.twikey_id) for attr in self.template_id.twikey_attribute_ids
        ]

        lst = []
        for name, _field in self._fields.items():
            if name in sp_lst or name == "template_id":
                lst.append(name)

        get_fields = self.read(fields=lst, load="_classic_read")
        if get_fields:
            get_fields[0].pop("id")
            get_fields[0].pop("template_id")
            new_keys = []
            for key, value in get_fields[0].items():
                model_id = self.env["ir.model"].search(
                    [("model", "=", "twikey.contract.template.wizard")]
                )
                field_id = self.env["ir.model.fields"].search(
                    [("name", "=", key), ("model_id", "=", model_id.id)]
                )
                if field_id.type != "boolean" and not value:
                    get_fields[0].update({key: ""})
                key_split = key.split("_")
                if len(key_split) > 0 and key_split[0] == "x":
                    new_keys.append(key_split[1])
            final_dict = dict(zip(new_keys, list(get_fields[0].values())))
            payload.update(final_dict)
        try:
            _logger.debug("New mandate creation data: {}".format(payload))
            twikey_client = self.env["ir.config_parameter"].get_twikey_client(company=self.env.company)
            if twikey_client:
                twikey_client.refreshTokenIfRequired()
                resp_obj = twikey_client.document.create(payload)
                _logger.info("Creating new mandate with response: %s" % resp_obj)
                mandate_id = (
                    self.env["twikey.mandate.details"].create(
                        {
                            "template_id": self.template_id.id,
                            "lang": self.partner_id.lang,
                            "partner_id": payload.get("customerNumber"), # contains the partner_id
                            "reference": resp_obj.get("mndtId"),
                            "url": resp_obj.get("url"),
                            "zip": self.partner_id.zip if self.partner_id.zip else False,
                            "address": (
                                self.partner_id.street if self.partner_id.street else False
                            ),
                            "city": self.partner_id.city if self.partner_id.city else False,
                            "country_id": (
                                self.partner_id.country_id.id
                                if self.partner_id.country_id
                                else False
                            ),
                        }
                    )
                )
                mandate_id.with_context(update_feed=True).write(get_fields[0])
        except TwikeyError as e:
            errmsg = "Exception raised while creating a new Mandate:\n%s" % e
            self.env["discuss.channel"].search(
                [("name", "=", "twikey")]
            ).message_post(
                subject="Configuration",
                body=errmsg,
            )
            _logger.error(errmsg)
            return get_error_msg(
                str(e), "Exception raised while creating a new Mandate", sticky=True
            )

        return get_success_msg("Mandate invitation(s) created successfully.")
