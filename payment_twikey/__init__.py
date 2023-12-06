import logging

from lxml import html

from odoo import SUPERUSER_ID, api

from odoo.addons.payment import reset_payment_provider, setup_provider

from . import controllers, models, wizard


def insert_twikey_url_in_email_templates(env):
    for document_type, template_ref in (
            ("invoice", "account.email_template_edi_invoice"),
            ("credit note", "account.email_template_edi_credit_note"),
    ):
        template = env.ref(template_ref)
        snippet = html.fragment_fromstring(
            f"""\
<t t-if="object.twikey_url">
    <br /><br />
    <a t-att-href="object.twikey_url">
        Click to open this {document_type} in Twikey
    </a>
</t>"""
        )
        try:
            root = html.fragment_fromstring(template.body_html)
            root.find("p").append(snippet)
            template.body_html = html.tostring(root, pretty_print=True, encoding="unicode")
        except Exception as ex:
            logging.getLogger("odoo.addons.payment_twikey.post_init_hook").warning(
                "Could not insert Twikey URL into mail template %s: %s" % (
                    template_ref, ex,
                )
            )


def post_init_hook(cr, registry):
    setup_provider(cr, registry, 'twikey')
    env = api.Environment(cr, SUPERUSER_ID, {})
    insert_twikey_url_in_email_templates(env)


def uninstall_hook(cr, registry):
    reset_payment_provider(cr, registry, 'twikey')
