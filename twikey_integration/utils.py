from odoo.addons.payment import utils as payment_utils

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

def format_partner_name(partner_name):
    """ Format the partner name to comply with the payload structure of the API request.

    :param str partner_name: The name of the partner making the payment.
    :return: The formatted partner name.
    :rtype: dict
    """

    return {
        'firstName': first_name,
        'lastName': last_name,
    }


def format_partner_address(partner):
    """ Format the partner address to comply with the payload structure of the API request.

    :param res.partner partner: The partner making the payment.
    :return: The formatted partner address.
    :rtype: dict
    """
    street_data = partner._get_street_split()
    return {
        'city': partner.city,
        'country': partner.country_id.code or 'ZZ',  # 'ZZ' if the country is not known.
        'stateOrProvince': partner.state_id.code,
        'postalCode': partner.zip,
        # Fill in the address fields if the format is supported, or fallback to the raw address.
        'street': street_data.get('street_name', partner.street),
        'houseNumberOrName': street_data.get('street_number'),
    }
