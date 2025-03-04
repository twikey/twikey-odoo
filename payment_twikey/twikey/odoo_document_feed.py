import logging
from ..twikey.document import DocumentFeed

_logger = logging.getLogger(__name__)


class OdooDocumentFeed(DocumentFeed):
    def __init__(self, env, company):
        self.env = env
        self.company = company
        self.res_country = self.env["res.country"]
        self.res_lang = self.env["res.lang"]
        self.res_partner = self.env["res.partner"]
        self.mandates = self.env["twikey.mandate.details"]
        self.template = self.env["twikey.contract.template"]
        self.paymentprovider = self.env["payment.provider"]

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
            country_id = self.res_country.search([("code", "=", address_line.get("Ctry"))])

        return address, zip_code, city, country_id

    def prepare_partner(self, partner_id, debtor, address, zip_code, city, country_id, email):
        """ Only update name for new partners, existing ones will update address and email info"""
        if not partner_id and "Nm" in debtor:
            partner_id = self.res_partner.search([("name", "=", debtor.get("Nm"))])

            if not partner_id:
                partner_id = self.res_partner.create({"name": debtor.get("Nm")})

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
            lang_id = self.res_lang.search([("iso_code", "=", lang)])

        if "TemplateId" in field_dict:
            temp_id = field_dict["TemplateId"]
            template_id = self.template.search([("template_id_twikey", "=", temp_id)], limit=1)

        address, zip_code, city, country_id = self.prepare_address(debtor)

        if "CtctDtls" in debtor:
            contact_details = debtor.get("CtctDtls")
            email = contact_details.get("EmailAdr") if "EmailAdr" in contact_details else False
            if "Othr" in contact_details:
                customer_number = contact_details.get("Othr")
                try:
                    lookup_id = int(customer_number)
                    _logger.debug("Got lookup_id %s" % lookup_id)
                    partner_id = self.res_partner.browse(lookup_id)
                except ValueError:
                    _logger.error("Customer had invalid number=%s." % customer_number)
                except UserError:
                    _logger.error("Customer not found by id=%s." % customer_number)
            else:
                _logger.warning("Got no customerNumber in Twikey, trying with email" % contact_details)

            if not partner_id and email:
                partner_id = self.res_partner.search([("email", "ilike", email)])
                if len(partner_id) != 1:
                    _logger.error(
                        "Incorrect number of customers found by %s skipping mandate. "
                        "Please ensure the customerNumber is set. "
                        "Found: %s" % (email, partner_id)
                    )

        partner_id = self.prepare_partner(partner_id, debtor, address, zip_code, city, country_id, email)
        if updated_doc:
            new_state = ("suspended" if reason["Rsn"] and reason["Rsn"] == "uncollectable|user" else "signed")
            mandate_id = self.mandates.search([("reference", "=", mandate_number)])
        else:
            mandate_id = self.mandates.search([("reference", "=", doc.get("MndtId"))])

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
                    field_name = field_name_from_attribute(key, temp_id)
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
            mandate_id = self.mandates.create(mandate_vals)
            partner_id.message_post(body=f"Twikey mandate {mandate_number} was activated")

        # Allow register payments
        if partner_id and mandate_id:
            providers = self.paymentprovider.search([("code", "=", 'twikey')])
            if template_id:
                _logger.debug("Finding linked providers for %s", template_id)
                # find more specific
                providers_for_profile = providers.filtered(
                    lambda x: x.twikey_template_id and x.twikey_template_id.id == template_id.id
                )
                if len(providers_for_profile) > 0:
                    providers = providers_for_profile
            for provider in providers:
                if provider.token_from_mandate(partner_id, mandate_id):
                    _logger.debug("Activating token for ref=%s", mandate_id.reference)
                    partner_id.message_post(body=f"Twikey token {mandate_id.reference} was added")

        # Allow regular refunds
        if partner_id and iban:
            customer_bank_id = self.env["res.partner.bank"].search([('acc_number', '=', iban)], limit=1)
            if not customer_bank_id:
                bank = self.env["res.bank"].search([('bic', '=', bic)], limit=1)
                if not bank:
                    bank = self.env["res.bank"].create({"name":bic, "bic":bic})
                _logger.info("Linked customer: " + str(partner_id.name) + " and iban: " + str(iban))
                try:
                    self.env["res.partner.bank"].create({
                        "partner_id": partner_id.id,
                        "bank_id": bank.id,
                        "acc_number": iban
                    })
                    partner_id.message_post(body=f"Twikey account of {partner_id.name} was added")
                except Exception as duplicate:
                    partner_id.message_post(body=f"Twikey account of {partner_id.name} was not added as probable duplicate")

    def start(self, position, number_of_updates):
        _logger.info(f"Got new {number_of_updates} document update(s) from start={position}")
        self.company.sudo().update({
            "mandate_feed_pos": position
        })

    def new_document(self, doc, evt_time):
        try:
            self.new_update_document(doc, False, doc.get("MndtId"), False)
        except Exception as e:
            _logger.exception("encountered an error in newDocument with mandate_number=%s:\n%s", doc.get("MndtId"), e)

    def updated_document(self, original_doc_number, doc, reason, evt_time):
        try:
            self.new_update_document(doc, True, original_doc_number, reason)
        except Exception as e:
            _logger.exception("encountered an error in updatedDocument with mandate_number=%s:\n%s", original_doc_number, e)

    def cancelled_document(self, doc_number, reason, evt_time):
        try:
            mandate_id = self.mandates.search([("reference", "=", doc_number)])
            if mandate_id:
                mandate_id.with_context(update_feed=True).write(
                    {"state": "cancelled", "description": "Cancelled with reason : " + reason["Rsn"]}
                )
                mandate_id.partner_id.message_post(body=f"Twikey mandate {doc_number} was cancelled")
        except Exception as e:
            _logger.exception("encountered an error in cancelDocument with mandate_number=%s:\n%s", doc_number, e)