from odoo import api, fields, models, exceptions,_
from collections.abc import Mapping
import logging

_logger = logging.getLogger(__name__)

MODULE_UNINSTALL_FLAG = '_force_unlink'
INSERT_QUERY = "INSERT INTO {table} ({cols}) VALUES {rows} RETURNING id"
UPDATE_QUERY = "UPDATE {table} SET {assignment} WHERE {condition} RETURNING id"

def query_insert(cr, table, rows):
    """ Insert rows in a table. ``rows`` is a list of dicts, all with the same
        set of keys. Return the ids of the new rows.
    """
    if isinstance(rows, Mapping):
        rows = [rows]
    cols = list(rows[0])
    query = INSERT_QUERY.format(
        table=table,
        cols=",".join(cols),
        rows=",".join("%s" for row in rows),
    )
    params = [tuple(row[col] for col in cols) for row in rows]
    cr.execute(query, params)
    return [row[0] for row in cr.fetchall()]

def query_update(cr, table, values, selectors):
    """ Update the table with the given values (dict), and use the columns in
        ``selectors`` to select the rows to update.
    """
    setters = set(values) - set(selectors)
    query = UPDATE_QUERY.format(
        table=table,
        assignment=",".join("{0}=%({0})s".format(s) for s in setters),
        condition=" AND ".join("{0}=%({0})s".format(s) for s in selectors),
    )
    cr.execute(query, values)
    return [row[0] for row in cr.fetchall()]

class IrModelFields(models.Model):
    _inherit = 'ir.model.fields'

    def _reflect_model(self, model):
        """ Reflect the given model's fields. """
        self.clear_caches()
        by_label = {}
        if model != self.env['contract.template.wizard'] and model != self.env['mandate.details']:
            for field in model._fields.values():
                if field.string in by_label:
                    _logger.warning('Two fields (%s, %s) of %s have the same label: %s.',
                                    field.name, by_label[field.string], model, field.string)
                else:
                    by_label[field.string] = field.name

        cr = self._cr
        module = self._context.get('module')
        fields_data = self._existing_field_data(model._name)
        to_insert = []
        to_xmlids = []
        for name, field in model._fields.items():
            old_vals = fields_data.get(name)
            new_vals = self._reflect_field_params(field)
            if old_vals is None:
                to_insert.append(new_vals)
            elif any(old_vals[key] != new_vals[key] for key in new_vals):
                ids = query_update(cr, self._table, new_vals, ['model', 'name'])
                record = self.browse(ids)
                keys = [key for key in new_vals if old_vals[key] != new_vals[key]]
                self.pool.post_init(record.modified, keys)
                old_vals.update(new_vals)
            if module and (module == model._original_module or module in field._modules):
                # remove this and only keep the else clause if version >= saas-12.4
                if field.manual:
                    self.pool.loaded_xmlids.add(
                        '%s.field_%s__%s' % (module, model._name.replace('.', '_'), name))
                else:
                    to_xmlids.append(name)

        if to_insert:
            # insert missing fields
            ids = query_insert(cr, self._table, to_insert)
            records = self.browse(ids)
            self.pool.post_init(records.modified, to_insert[0])
            self.clear_caches()

        if to_xmlids:
            # create or update their corresponding xml ids
            fields_data = self._existing_field_data(model._name)
            prefix = '%s.field_%s__' % (module, model._name.replace('.', '_'))
            self.env['ir.model.data']._update_xmlids([
                dict(xml_id=prefix + name, record=self.browse(fields_data[name]['id']))
                for name in to_xmlids
            ])

        if not self.pool._init:
            # remove ir.model.fields that are not in self._fields
            fields_data = self._existing_field_data(model._name)
            extra_names = set(fields_data) - set(model._fields)
            if extra_names:
                # add key MODULE_UNINSTALL_FLAG in context to (1) force the
                # removal of the fields and (2) not reload the registry
                records = self.browse([fields_data.pop(name)['id'] for name in extra_names])
                records.with_context(**{MODULE_UNINSTALL_FLAG: True}).unlink()
