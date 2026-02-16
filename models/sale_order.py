from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    recepcion_ids = fields.One2many(
        'residuo.recepcion',
        'sale_order_id',
        string='Recepciones',
    )
    recepcion_count = fields.Integer(
        string='Recepciones',
        compute='_compute_recepcion_count',
    )

    @api.depends('recepcion_ids')
    def _compute_recepcion_count(self):
        for order in self:
            order.recepcion_count = len(order.recepcion_ids)

    def action_confirm(self):
        res = super().action_confirm()
        for order in self:
            recepcion = self.env['residuo.recepcion'].create({
                'sale_order_id': order.id,
'partner_id': order.partner_id.id,
            })
            _logger.info(
                'Recepción creada automáticamente: %s (ID: %s) para SO: %s',
                recepcion.name, recepcion.id, order.name,
            )
        return res

    def action_ver_recepciones(self):
        self.ensure_one()
        if self.recepcion_count == 1:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'residuo.recepcion',
                'view_mode': 'form',
                'res_id': self.recepcion_ids[0].id,
                'context': {'default_sale_order_id': self.id},
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Recepciones'),
            'res_model': 'residuo.recepcion',
            'view_mode': 'list,form',
            'domain': [('sale_order_id', '=', self.id)],
            'context': {'default_sale_order_id': self.id},
        }