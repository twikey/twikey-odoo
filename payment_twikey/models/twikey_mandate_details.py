import logging

import requests
from odoo import _, fields, models
from odoo.exceptions import UserError

from ..twikey.client import TwikeyError
from ..twikey.document import DocumentFeed
from ..utils import sanitise_iban

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
    reference = fields.Char(string="Mandate Reference", index=True)
    iban = fields.Char(string="IBAN")
    bic = fields.Char(string="BIC")
    contract_temp_id = fields.Many2one(comodel_name="twikey.contract.template", string="Twikey Profile",
                                       readonly=True)
    description = fields.Text()
    lang = fields.Selection(_lang_get, string="Language")
    url = fields.Char(string="URL", readonly=True)

    country_id = fields.Many2one("res.country")
    city = fields.Char()
    zip = fields.Integer()
    address = fields.Char()

    def action_cancel_reason(self):
        self.ensure_one()
        wizard = self.env["mandate.cancel.reason"].create({"mandate_id": self.id})
        action = self.env.ref("payment_twikey.mandate_cancel_reason_action").read()[0]
        action["res_id"] = wizard.id
        return action

    def update_feed(self):
        try:
            _logger.debug(f"Fetching Twikey updates from {self.env.company.mandate_feed_pos}")
            twikey_client = self.env["ir.config_parameter"].get_twikey_client(company=self.env.company)
            if twikey_client:
                twikey_client.document.feed(OdooDocumentFeed(self.env), self.env.company.mandate_feed_pos)
        except TwikeyError as e:
            if e.error_code != "err_call_in_progress":  # ignore parallel calls
                errmsg = "Exception raised while fetching updates:\n%s" % e
                self.env['mail.channel'].search([('name', '=', 'twikey')]).message_post(subject="Mandates", body=errmsg)

    def write(self, values):
        self.ensure_one()
        res = super(TwikeyMandateDetails, self).write(values)

        try:
            twikey_client = self.env["ir.config_parameter"].get_twikey_client(company=self.env.company)
            if twikey_client:
                if not self._context.get("update_feed"):
                    data = {}
                    if self.state != "signed":
                        data["mndtId"] = values.get("reference") if values.get("reference") else self.reference
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
                        except (Exception, requests.exceptions.RequestException) as e:
                            raise UserError(_('Error sending update: %s') % (str(e)))
            return res
        except TwikeyError as e:
            raise UserError from e

    def unlink(self):
        for mandate in self:
            context = mandate._context
            if not context.get("update_feed"):
                mandate.update_feed()
                if mandate.state in ["signed", "cancelled"]:
                    raise UserError(_("This mandate is in already signed or cancelled. It can not be deleted."))
                elif mandate.state == "pending":
                    try:
                        twikey_client = mandate.env["ir.config_parameter"].get_twikey_client(company=self.env.company)
                        if twikey_client:
                            twikey_client.document.cancel(mandate.reference, "Deleted from odoo")
                    except TwikeyError as e:
                        if e.error_code != 'err_no_contract':  # Ignore as not avail in Twikey
                            raise UserError(_("This mandate could not be cancelled: %s") % e.error)
                    return super(TwikeyMandateDetails, mandate).unlink()
                else:
                    return super(TwikeyMandateDetails, mandate).unlink()
            else:
                return super(TwikeyMandateDetails, mandate).unlink()

    def is_signed(self):
        return self.state == 'signed'

    def is_creditcard(self):
        return self.contract_temp_id and self.contract_temp_id.type == "CREDITCARD"

    def get_attribute(self, name):
        ct = self.contract_temp_id.ct()
        return self.contract_temp_id and self[f"x_{name}_{ct}"]

    def is_mandatenumber_required(self):
        return self.contract_temp_id and self.contract_temp_id.mandate_number_required


class OdooDocumentFeed(DocumentFeed):
    def __init__(self, env):
        self.env = env

    @staticmethod
    def splmtr_as_dict(doc):
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
        """ Only update name for new partners, existing ones will update address and email info"""
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
                    "email": email if email else '',
                }
            )

        return partner_id

    def new_update_document(self, doc, updated_doc, mandate_number, reason):
        partner_id = False
        debtor = doc.get("Dbtr")
        iban = doc.get("DbtrAcct")
        bic = doc.get("DbtrAgt").get("FinInstnId").get("BICFI")
        template_id = False
        lang_id = False

        field_dict = self.splmtr_as_dict(doc)
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
            email = contact_details.get("EmailAdr") if "EmailAdr" in contact_details else False
            if "Othr" in contact_details:
                customer_number = contact_details.get("Othr")
                try:
                    lookup_id = int(customer_number)
                    _logger.debug("Got lookup_id %s" % lookup_id)
                    partner_id = self.env["res.partner"].browse(lookup_id)
                except UserError:
                    _logger.error("Customer not found by id=%s." % customer_number)
            else:
                _logger.warning("Got no customerNumber in Twikey, trying with email" % contact_details)

            if not partner_id and email:
                partner_id = self.env["res.partner"].search([("email", "ilike", email)])
                if len(partner_id) != 1:
                    _logger.error(
                        "Incorrect number of customers found by %s skipping mandate. "
                        "Please ensure the customerNumber is set. "
                        "Found: %s" % (email, partner_id)
                    )

        partner_id = self.prepare_partner(partner_id, debtor, address, zip_code, city, country_id, email)
        if updated_doc:
            new_state = ("suspended" if reason["Rsn"] and reason["Rsn"] == "uncollectable|user" else "signed")
            mandate_id = self.env["twikey.mandate.details"].search([("reference", "=", mandate_number)])
        else:
            mandate_id = self.env["twikey.mandate.details"].search([("reference", "=", doc.get("MndtId"))])

        mandate_vals = {
            "partner_id": partner_id.id if partner_id else False,
            "state": new_state if updated_doc else "signed",
            "lang": lang_id.code if lang_id else False,
            "contract_temp_id": template_id.id if template_id else False,
            "iban": iban if iban else False,
            "bic": bic if bic else False,
        }
        # add attributes to it
        if template_id:
            attributes = template_id.twikey_attribute_ids.mapped("name")
            for key in attributes:
                if key in field_dict:
                    value = field_dict[key]
                    field_name = "x_" + key + "_" + str(temp_id)
                    mandate_vals[field_name] = value

        if mandate_id:
            if updated_doc:
                mandate_vals["reference"] = doc.get("MndtId")
            mandate_id.with_context(update_feed=True).write(mandate_vals)
            if reason:
                update_reason = reason["Rsn"]
                partner_id.message_post(body=f"Twikey mandate {mandate_number} was updated ({update_reason})")
            else:
                partner_id.message_post(body=f"Twikey mandate {mandate_number} was added")
        else:
            mandate_vals["reference"] = doc.get("MndtId")
            mandate_vals["address"] = address
            mandate_vals["zip"] = zip_code
            mandate_vals["city"] = city
            mandate_vals["country_id"] = country_id.id if country_id else 0
            mandate_id = self.env["twikey.mandate.details"].sudo().create(mandate_vals)
            partner_id.message_post(body=f"Twikey mandate {mandate_number} was added")

        # Allow register payments
        if partner_id and mandate_id:
            providers = self.env['payment.acquirer'].sudo().search([("provider", "=", 'twikey')])
            if template_id:
                _logger.debug("Finding linked providers for %s", template_id)
                # find more specific
                providers_for_profile = providers.filtered(
                    lambda x: x.twikey_template_id and x.twikey_template_id == template_id.id)
                if len(providers_for_profile) > 0:
                    providers = providers_for_profile
            for provider in providers:
                if provider.token_from_mandate(partner_id, mandate_id):
                    _logger.debug("Activating token for : %s", mandate_id.reference)
                    partner_id.message_post(body=f"Twikey token {mandate_number} was added")

        # Allow regular refunds
        if partner_id and iban:
            customer_bank_id = partner_id.bank_ids.filtered(lambda x: sanitise_iban(x.acc_number) == iban)
            if not customer_bank_id:
                _logger.info("Linked customer: " + str(partner_id.name) + " and iban: " + str(iban))
                self.env["res.partner.bank"].create({"partner_id": partner_id.id, "acc_number": iban})
                partner_id.message_post(body=f"Twikey account of {partner_id.name} was added")

    def start(self, position, number_of_updates):
        _logger.info(f"Got new {number_of_updates} document update(s) from start={position}")
        self.env.company.update({
            "mandate_feed_pos": position
        })

    def newDocument(self, doc):
        try:
            self.new_update_document(doc, False, False, False)
        except Exception as e:
            _logger.exception("encountered an error in newDocument with mandate_number=%s:\n%s", doc.get("MndtId"), e)

    def updatedDocument(self, mandate_number, doc, reason):
        try:
            self.new_update_document(doc, True, mandate_number, reason)
        except Exception as e:
            _logger.exception("encountered an error in updatedDocument with mandate_number=%s:\n%s", mandate_number, e)

    def cancelDocument(self, mandate_number, rsn):
        try:
            mandate_id = self.env["twikey.mandate.details"].search([("reference", "=", mandate_number)])
            if mandate_id:
                mandate_id.with_context(update_feed=True).write(
                    {"state": "cancelled", "description": "Cancelled with reason : " + rsn["Rsn"]}
                )
                mandate_id.partner_id.message_post(body=f"Twikey mandate {mandate_number} was cancelled")
        except Exception as e:
            _logger.exception("encountered an error in cancelDocument with mandate_number=%s:\n%s", mandate_number, e)
