from odoo import models, fields, api, _
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)


class StockLot(models.Model):
    _inherit = 'stock.lot'

    tipo_manejo_id = fields.Many2one(
        'residuo.tipo.manejo',
        string='Tipo de Manejo',
        tracking=True,
    )

    clasificacion_corrosivo = fields.Boolean(string='Corrosivo (C)', tracking=True)
    clasificacion_reactivo = fields.Boolean(string='Reactivo (R)', tracking=True)
    clasificacion_explosivo = fields.Boolean(string='Explosivo (E)', tracking=True)
    clasificacion_toxico = fields.Boolean(string='Tóxico (T)', tracking=True)
    clasificacion_inflamable = fields.Boolean(string='Inflamable (I)', tracking=True)
    clasificacion_biologico = fields.Boolean(string='Biológico (B)', tracking=True)

    clasificaciones_display = fields.Char(
        string='CRETIB',
        compute='_compute_clasificaciones_display',
        store=True,
    )

    fecha_recepcion_residuo = fields.Date(
        string='Fecha de Recepción',
        tracking=True,
    )

    fecha_caducidad_residuo = fields.Date(
        string='Fecha de Caducidad',
        compute='_compute_fecha_caducidad',
        store=True,
        tracking=True,
    )

    dias_restantes_caducidad = fields.Integer(
        string='Días Restantes',
        compute='_compute_dias_restantes',
    )

    caducidad_estado = fields.Selection(
        [('ok', 'Vigente'), ('warning', 'Próximo a vencer'), ('expired', 'Vencido')],
        string='Estado Caducidad',
        compute='_compute_dias_restantes',
    )

    @api.depends(
        'clasificacion_corrosivo', 'clasificacion_reactivo',
        'clasificacion_explosivo', 'clasificacion_toxico',
        'clasificacion_inflamable', 'clasificacion_biologico',
    )
    def _compute_clasificaciones_display(self):
        mapping = [
            ('clasificacion_corrosivo', 'C'), ('clasificacion_reactivo', 'R'),
            ('clasificacion_explosivo', 'E'), ('clasificacion_toxico', 'T'),
            ('clasificacion_inflamable', 'I'), ('clasificacion_biologico', 'B'),
        ]
        for rec in self:
            rec.clasificaciones_display = ', '.join(
                code for field, code in mapping if getattr(rec, field)
            )

    @api.depends('fecha_recepcion_residuo')
    def _compute_fecha_caducidad(self):
        for rec in self:
            if rec.fecha_recepcion_residuo:
                rec.fecha_caducidad_residuo = rec.fecha_recepcion_residuo + relativedelta(months=5)
            else:
                rec.fecha_caducidad_residuo = False

    @api.depends('fecha_caducidad_residuo')
    def _compute_dias_restantes(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.fecha_caducidad_residuo:
                delta = (rec.fecha_caducidad_residuo - today).days
                rec.dias_restantes_caducidad = delta
                if delta < 0:
                    rec.caducidad_estado = 'expired'
                elif delta <= 30:
                    rec.caducidad_estado = 'warning'
                else:
                    rec.caducidad_estado = 'ok'
            else:
                rec.dias_restantes_caducidad = 0
                rec.caducidad_estado = False

    @api.model
    def _cron_alertas_caducidad_residuos(self):
        today = fields.Date.context_today(self)
        target_date = today + relativedelta(days=30)

        lotes = self.search([('fecha_caducidad_residuo', '=', target_date)])

        for lote in lotes:
            existing = self.env['mail.activity'].search([
                ('res_model', '=', 'stock.lot'),
                ('res_id', '=', lote.id),
                ('summary', 'like', 'Caducidad de residuo'),
            ], limit=1)
            if existing:
                continue

            lote.activity_schedule(
                act_type_xmlid='mail.mail_activity_data_warning',
                date_deadline=lote.fecha_caducidad_residuo,
                summary=_('Caducidad de residuo peligroso: %s') % lote.name,
                note=_(
                    'El lote <b>%s</b> del producto <b>%s</b> caduca el <b>%s</b>. '
                    'Quedan 30 días para darle tratamiento.'
                ) % (
                    lote.name,
                    lote.product_id.display_name,
                    lote.fecha_caducidad_residuo.strftime('%d/%m/%Y'),
                ),
            )
            _logger.info('Actividad de caducidad creada para lote %s', lote.name)