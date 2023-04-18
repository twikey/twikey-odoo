import logging

import requests

from odoo import _, exceptions, fields, models
from odoo.exceptions import UserError

from .. import twikey

_logger = logging.getLogger(__name__)


def _lang_get(self):
    return self.env["res.lang"].get_installed()


class TwikeyMandateDetails(models.Model):
    _name = "twikey.mandate.details"
    _inherit = ["portal.mixin", "mail.thread", "mail.activity.mixin"]
    _description = "Mandate details of Twikey"
    _rec_name = "partner_id"

    partner_id = fields.Many2one("res.partner", string="Customer", required=True)
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("signed", "Signed"),
            ("suspended", "Suspended"),
            ("cancelled", "Cancelled"),
        ],
        default="pending",
        required=True,
    )
    creditor_id = fields.Many2one("res.partner", string="Creditor-ID")
    reference = fields.Char(string="Mandate Reference", required=True)
    iban = fields.Char(string="IBAN")
    bic = fields.Char(string="BIC")
    contract_temp_id = fields.Many2one(
        comodel_name="twikey.contract.template", string="Contract Template"
    )
    description = fields.Text()
    lang = fields.Selection(_lang_get, string="Language")
    url = fields.Char(string="URL")

    country_id = fields.Many2one("res.country")
    city = fields.Char()
    zip = fields.Integer()
    address = fields.Char()

    def action_cancel_reason(self):
        self.ensure_one()
        wizard = self.env["mandate.cancel.reason"].create(
            {
                "mandate_id": self.id,
            }
        )
        action = self.env.ref("twikey_integration.mandate_cancel_reason_action").read()[0]
        action["res_id"] = wizard.id
        return action

    def update_feed(self):
        try:
            _logger.debug("Fetching Twikey updates")
            twikey_client = self.env["ir.config_parameter"].get_twikey_client(
                company=self.env.company
            )
            twikey_client.document.feed(OdooDocumentFeed(self.env))
        except (ValueError, requests.exceptions.RequestException) as e:
            raise UserError from e

    def write(self, values):
        self.ensure_one()
        res = super(TwikeyMandateDetails, self).write(values)

        twikey_client = self.env["ir.config_parameter"].get_twikey_client(company=self.env.company)
        if twikey_client:
            if not self._context.get("update_feed"):
                data = {}
                if self.state != "signed":
                    data["mndtId"] = (
                        values.get("reference") if values.get("reference") else self.reference
                    )
                    if "iban" in values:
                        data["iban"] = values.get("iban") or ""
                    if "bic" in values:
                        data["bic"] = values.get("bic")
                    if "lang" in values:
                        data["l"] = values.get("lang")
                    if "email" in values:
                        data["email"] = values.get("email")
                    if "mobile" in values:
                        data["mobile"] = values.get("mobile")

                    try:
                        if data != {}:
                            twikey_client.document.update(data)
                    except (ValueError, requests.exceptions.RequestException) as e:
                        raise exceptions.AccessError from e
        return res

    def unlink(self):
        for mandate in self:
            context = mandate._context
            if not context.get("update_feed"):
                mandate.update_feed()
                if mandate.state in ["signed", "cancelled"]:
                    raise UserError(
                        _("This mandate is in already signed or cancelled. It can not be deleted.")
                    )
                elif mandate.state == "pending":
                    twikey_client = mandate.env["ir.config_parameter"].get_twikey_client(
                        company=self.env.company
                    )
                    twikey_client.document.cancel(mandate.reference, "Deleted from odoo")
                    return super(TwikeyMandateDetails, mandate).unlink()
                else:
                    return super(TwikeyMandateDetails, mandate).unlink()
            else:
                return super(TwikeyMandateDetails, mandate).unlink()


class OdooDocumentFeed(twikey.document.DocumentFeed):
    def __init__(self, env):
        self.env = env

    def splmtrAsDict(self, doc):
        field_dict = {}
        if "SplmtryData" in doc:
            lst = doc.get("SplmtryData")
            for ls in lst:
                field_dict[ls["Key"]] = ls["Value"]
        return field_dict

    def prepare_address(self, debtor):
        address = False
        zip_code = False
        city = False
        country_id = False
        if debtor and "PstlAdr" in debtor:
            address_line = debtor.get("PstlAdr")
            address = address_line.get("AdrLine") if address_line.get("AdrLine") else False
            zip_code = address_line.get("PstCd") if address_line.get("PstCd") else False
            city = address_line.get("TwnNm") if address_line.get("TwnNm") else False
            country_id = self.env["res.country"].search([("code", "=", address_line.get("Ctry"))])

        return address, zip_code, city, country_id

    def prepare_partner(self, partner_id, debtor, address, zip_code, city, country_id, email):
        if not partner_id and "Nm" in debtor:
            partner_id = self.env["res.partner"].search([("name", "=", debtor.get("Nm"))])

            if not partner_id:
                partner_id = self.env["res.partner"].create({"name": debtor.get("Nm")})

        if partner_id:
            partner_id.with_context(update_feed=True).write(
                {
                    "street": address,
                    "zip": zip_code,
                    "city": city,
                    "country_id": country_id.id if country_id else False,
                    "email": email,
                }
            )

        return partner_id

    def new_update_document(self, doc, updatedDoc, mandate_number, reason):
        partner_id = False
        debtor = doc.get("Dbtr")
        iban = doc.get("DbtrAcct")
        bic = doc.get("DbtrAgt").get("FinInstnId").get("BICFI")
        template_id = False
        lang_id = False

        field_dict = self.splmtrAsDict(doc)
        if "Language" in field_dict:
            lang = field_dict["Language"]
            lang_id = self.env["res.lang"].search([("iso_code", "=", lang)])

        if "TemplateId" in field_dict:
            temp_id = field_dict["TemplateId"]
            template_id = self.env["twikey.contract.template"].search(
                [("template_id_twikey", "=", temp_id)], limit=1
            )

        address, zip_code, city, country_id = self.prepare_address(debtor)

        if "CtctDtls" in debtor:
            contact_details = debtor.get("CtctDtls")
            email = contact_details.get("EmailAdr")
            if "Othr" in contact_details:
                customer_number = contact_details.get("Othr")
                try:
                    lookup_id = int(customer_number)
                    _logger.debug("Got lookup_id %s" % lookup_id)
                    partner_id = self.env["res.partner"].browse(lookup_id)
                except UserError:
                    _logger.error("Customer not found by id=%s skipping mandate." % customer_number)
            else:
                _logger.warning(
                    "Got no customerNumber in Twikey, trying with email" % contact_details
                )

            if "EmailAdr" in contact_details:
                partner_id = self.env["res.partner"].search([("email", "ilike", email)])
                if len(partner_id) != 1:
                    _logger.error(
                        "Incorrect number of customers found by %s skipping mandate. "
                        "Please ensure the customerNumber is set. "
                        "Found: %s" % (email, partner_id)
                    )

        partner_id = self.prepare_partner(
            partner_id, debtor, address, zip_code, city, country_id, email
        )

        if updatedDoc:
            new_state = (
                "suspended" if reason["Rsn"] and reason["Rsn"] == "uncollectable|user" else "signed"
            )
            mandate_id = self.env["twikey.mandate.details"].search(
                [("reference", "=", mandate_number)]
            )
        else:
            mandate_id = self.env["twikey.mandate.details"].search(
                [("reference", "=", doc.get("MndtId"))]
            )

        if mandate_id:
            mandate_vals = {
                "partner_id": partner_id.id if partner_id else False,
                "state": new_state if updatedDoc else "signed",
                "lang": lang_id.code if lang_id else False,
                "contract_temp_id": template_id.id if template_id else False,
                "iban": iban if iban else False,
                "bic": bic if bic else False,
            }
            if updatedDoc:
                mandate_vals["reference"] = doc.get("MndtId")

            mandate_id.with_context(update_feed=True).write(mandate_vals)
        else:
            mandate_vals = {
                "partner_id": partner_id.id if partner_id else False,
                "state": new_state if updatedDoc else "signed",
                "lang": lang_id.code if lang_id else False,
                "contract_temp_id": template_id.id if template_id else False,
                "reference": doc.get("MndtId"),
                "iban": iban if iban else False,
                "bic": bic if bic else False,
            }
            self.env["twikey.mandate.details"].sudo().create(mandate_vals)

        if template_id:
            attributes = template_id.twikey_attribute_ids.mapped("name")
            for key in field_dict:
                if key in attributes:
                    value = field_dict[key]
                    field_name = "x_" + key + "_" + str(temp_id)
                    mandate_vals.update({field_name: value})

    def newDocument(self, doc):
        self.new_update_document(doc, False, False, False)

    def updatedDocument(self, mandate_number, doc, reason):
        self.new_update_document(doc, True, mandate_number, reason)

    def cancelDocument(self, mandateNumber, rsn):
        mandate_id = self.env["twikey.mandate.details"].search([("reference", "=", mandateNumber)])
        if mandate_id:
            mandate_id.with_context(update_feed=True).write(
                {"state": "cancelled", "description": "Cancelled with reason : " + rsn["Rsn"]}
            )
        else:
            self.env["twikey.mandate.details"].sudo().create(
                {"reference": mandateNumber, "state": "cancelled"}
            )
