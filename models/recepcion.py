from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class ResiduoRecepcion(models.Model):
    _name = 'residuo.recepcion'
    _description = 'Recepción de Residuos Peligrosos'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(
        string='Referencia',
        default=lambda self: _('Nueva'),
        readonly=True, copy=False, tracking=True,
    )
    sale_order_id = fields.Many2one(
        'sale.order', string='Orden de Venta',
        required=False, tracking=True, ondelete='restrict',
    )
    partner_id = fields.Many2one(
        'res.partner', string='Cliente / Generador',
        compute='_compute_partner_id', store=True,
        readonly=False, required=True, tracking=True,
    )
    picking_id = fields.Many2one(
        'stock.picking', string='Entrada de Inventario',
        readonly=True, copy=False,
    )
    estado = fields.Selection(
        [('borrador', 'Borrador'), ('confirmado', 'Confirmado'), ('cancelado', 'Cancelado')],
        default='borrador', string='Estado', tracking=True, copy=False,
    )
    linea_ids = fields.One2many('residuo.recepcion.linea', 'recepcion_id', string='Residuos Recolectados')
    notas = fields.Html(string='Notas')
    fecha_recepcion = fields.Date(
        string='Fecha de Recepción', default=fields.Date.context_today, tracking=True,
    )
    company_id = fields.Many2one(
        'res.company', string='Compañía',
        default=lambda self: self.env.company, required=True,
    )

    @api.depends('sale_order_id')
    def _compute_partner_id(self):
        for rec in self:
            if rec.sale_order_id:
                rec.partner_id = rec.sale_order_id.partner_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nueva')) == _('Nueva'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'residuo.recepcion.seq') or _('Nueva')
        return super().create(vals_list)

    def action_confirmar(self):
        for rec in self:
            if rec.estado != 'borrador':
                raise UserError(_('La recepción ya ha sido confirmada.'))
            if not rec.linea_ids:
                raise UserError(_('Debe agregar al menos un residuo a recolectar.'))

            for linea in rec.linea_ids:
                if not linea.product_id:
                    raise UserError(
                        _('Debe seleccionar el "Producto Destino" para el residuo: %s')
                        % (linea.descripcion_origen or 'Sin descripción'))
                if linea.product_id.type != 'consu':
                    raise ValidationError(
                        _('El producto "%s" debe ser de tipo Consumible.') % linea.product_id.name)
                if linea.cantidad <= 0:
                    raise ValidationError(
                        _('La cantidad del producto %s debe ser mayor a 0.') % linea.product_id.display_name)

            picking = rec._crear_picking()
            rec.write({'estado': 'confirmado', 'picking_id': picking.id})
            rec._propagar_datos_a_lotes()

    def _propagar_datos_a_lotes(self):
        """Al confirmar, escribe CRETIB + tipo_manejo + fecha_recepcion en el stock.lot."""
        self.ensure_one()
        for linea in self.linea_ids:
            if not linea.lote_asignado:
                continue
            lote = self.env['stock.lot'].search([
                ('name', '=', linea.lote_asignado),
                ('product_id', '=', linea.product_id.id),
                ('company_id', '=', self.company_id.id),
            ], limit=1)
            if not lote:
                continue
            vals = {
                'fecha_recepcion_residuo': self.fecha_recepcion or fields.Date.context_today(self),
                'clasificacion_corrosivo': linea.clasificacion_corrosivo,
                'clasificacion_reactivo': linea.clasificacion_reactivo,
                'clasificacion_explosivo': linea.clasificacion_explosivo,
                'clasificacion_toxico': linea.clasificacion_toxico,
                'clasificacion_inflamable': linea.clasificacion_inflamable,
                'clasificacion_biologico': linea.clasificacion_biologico,
            }
            if linea.tipo_manejo_id:
                vals['tipo_manejo_id'] = linea.tipo_manejo_id.id
            lote.write(vals)

    def _crear_picking(self):
        self.ensure_one()
        stock_location_cliente = (
            self.partner_id.property_stock_customer
            or self.env.ref('stock.stock_location_customers'))
        stock_location_destino = self.env.ref('stock.stock_location_stock')
        picking_type_in = self.env.ref('stock.picking_type_in')

        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type_in.id,
            'location_id': stock_location_cliente.id,
            'location_dest_id': stock_location_destino.id,
            'origin': self.name,
            'partner_id': self.partner_id.id,
            'scheduled_date': self.fecha_recepcion or fields.Date.context_today(self),
        })

        for linea in self.linea_ids:
            move = self.env['stock.move'].create({
                'description_picking': linea.product_id.display_name,
                'product_id': linea.product_id.id,
                'product_uom_qty': linea.cantidad,
                'product_uom': linea.product_id.uom_id.id,
                'picking_id': picking.id,
                'location_id': stock_location_cliente.id,
                'location_dest_id': stock_location_destino.id,
            })
            move_line_vals = {
                'move_id': move.id,
                'picking_id': picking.id,
                'product_id': linea.product_id.id,
                'product_uom_id': linea.product_id.uom_id.id,
                'quantity': linea.cantidad,
                'location_id': stock_location_cliente.id,
                'location_dest_id': stock_location_destino.id,
            }
            if linea.lote_asignado:
                lote_existente = self.env['stock.lot'].search([
                    ('name', '=', linea.lote_asignado),
                    ('product_id', '=', linea.product_id.id),
                    ('company_id', '=', self.company_id.id),
                ], limit=1)
                if lote_existente:
                    move_line_vals['lot_id'] = lote_existente.id
                else:
                    move_line_vals['lot_name'] = linea.lote_asignado
            self.env['stock.move.line'].create(move_line_vals)

        picking.action_confirm()
        picking.action_assign()

        if picking.state in ('assigned', 'confirmed'):
            ctx = self.env.context.copy()
            ctx.update({'skip_backorder': True})
            try:
                res = picking.with_context(ctx).button_validate()
                if isinstance(res, dict) and res.get('res_model') == 'stock.backorder.confirmation':
                    wizard = self.env['stock.backorder.confirmation'].with_context(
                        **res.get('context', {})).create({})
                    wizard.process()
            except ValidationError as e:
                raise UserError(
                    _("Se creó la entrada %s pero error al validar: %s") % (picking.name, str(e)))
        else:
            raise UserError(_('No se pudo reservar el inventario.'))
        return picking

    def action_cancelar(self):
        for rec in self:
            if rec.estado == 'cancelado':
                raise UserError(_('La recepción ya está cancelada.'))
            if rec.picking_id and rec.picking_id.state == 'done':
                raise UserError(_('No se puede cancelar porque el picking ya fue validado.'))
            if rec.picking_id and rec.picking_id.state != 'done':
                rec.picking_id.action_cancel()
            rec.write({'estado': 'cancelado'})

    def action_borrador(self):
        for rec in self:
            if rec.estado != 'cancelado':
                raise UserError(_('Solo se puede pasar a borrador desde estado cancelado.'))
            rec.write({'estado': 'borrador', 'picking_id': False})


class ResiduoRecepcionLinea(models.Model):
    _name = 'residuo.recepcion.linea'
    _description = 'Detalle de Residuos Recolectados'

    recepcion_id = fields.Many2one('residuo.recepcion', string='Recepción', ondelete='cascade', required=True)
    descripcion_origen = fields.Char(string='Descripción Manifiesto', readonly=True)
    product_id = fields.Many2one(
        'product.product', string='Producto Destino',
        required=False, domain=[('type', '=', 'consu')], context={'create': False},
    )
    lote_asignado = fields.Char(string='Lote / Manifiesto')
    cantidad = fields.Float(string='Cantidad', required=True, default=0.0)
    unidad = fields.Char(related='product_id.uom_id.name', readonly=True)
    categoria = fields.Char(related='product_id.categ_id.name', readonly=True)

    # --- Tipo de Manejo ---
    tipo_manejo_id = fields.Many2one('residuo.tipo.manejo', string='Tipo de Manejo')

    # --- CRETIB (heredable desde manifiesto, editable) ---
    clasificacion_corrosivo = fields.Boolean(string='C')
    clasificacion_reactivo = fields.Boolean(string='R')
    clasificacion_explosivo = fields.Boolean(string='E')
    clasificacion_toxico = fields.Boolean(string='T')
    clasificacion_inflamable = fields.Boolean(string='I')
    clasificacion_biologico = fields.Boolean(string='B')

    clasificaciones_display = fields.Char(
        string='CRETIB', compute='_compute_clasificaciones_display', store=True,
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
        for linea in self:
            linea.clasificaciones_display = ', '.join(
                code for field, code in mapping if getattr(linea, field))

    @api.constrains('cantidad')
    def _check_cantidad(self):
        for linea in self:
            if linea.cantidad <= 0:
                raise ValidationError(_('La cantidad debe ser mayor a 0.'))


class ProductTemplate(models.Model):
    _inherit = 'product.template'
    es_recoleccion = fields.Boolean(string="Es un servicio de recolección")