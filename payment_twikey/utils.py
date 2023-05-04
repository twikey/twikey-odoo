from odoo.addons.payment import utils as payment_utils
import re

def get_twikey_customer(partner):
    if not partner:
        return {}
    # Owner can be contact or account
    owner = partner
    if partner.parent_id:
        owner = partner.parent_id

    first_name, last_name = payment_utils.split_partner_name(partner.name)
    customer = {
        "firstname": first_name,
        "lastname": last_name,
        "l": partner.lang if partner.lang else "en",
        "locale": partner.lang if partner.lang else "en",
        "customerNumber": owner.id,
        "address": partner.street if partner.street else "-",
        "city": partner.city if partner.city else "",
        "zip": partner.zip if partner.zip else "",
        "country": partner.country_id.code if partner.country_id else "",
    }
    # if owner is company treat is as such
    if owner.company_type == "company" and owner.name:
        customer["companyName"] = owner.name
        if owner.vat:
            customer["coc"] = owner.vat

    if partner.mobile:
        customer["mobile"] = partner.mobile
    if partner.email:
        customer["email"] = partner.email

    return customer

def get_error_msg(msg, title='Twikey', sticky = False):
    return {
        'type': 'ir.actions.client',
        'tag': 'display_notification',
        'params': {
            'type': 'danger',
            'title': title,
            'message': msg,
            'next': {'type': 'ir.actions.act_window_close'},
            'sticky': sticky,
        }
    }

def get_success_msg(msg, title='Twikey', sticky = False):
    return {
        'type': 'ir.actions.client',
        'tag': 'display_notification',
        'params': {
            'type': 'success',
            'title': title,
            'message': msg,
            'next': {'type': 'ir.actions.act_window_close'},
            'sticky': sticky,
        }
    }

def sanitise_iban(iban):
    return re.sub(r'\W+', '', iban).upper()
