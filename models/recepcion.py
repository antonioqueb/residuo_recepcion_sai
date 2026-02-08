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
        readonly=True,
        copy=False,
        tracking=True,
    )
    
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Orden de Venta',
        required=False, 
        tracking=True,
        ondelete='restrict',
    )
    
    # ELIMINADO: manifiesto_id 
    # (Se inyectará desde el módulo manifiesto_ambiental para evitar Error de Dependencia Circular)

    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente / Generador',
        compute='_compute_partner_id',
        store=True,
        readonly=False,
        required=True,
        tracking=True,
    )

    picking_id = fields.Many2one(
        'stock.picking',
        string='Entrada de Inventario',
        readonly=True,
        copy=False,
    )
    
    estado = fields.Selection(
        selection=[
            ('borrador', 'Borrador'),
            ('confirmado', 'Confirmado'),
            ('cancelado', 'Cancelado'),
        ],
        default='borrador',
        string='Estado',
        tracking=True,
        copy=False,
    )
    
    linea_ids = fields.One2many(
        'residuo.recepcion.linea',
        'recepcion_id',
        string='Residuos Recolectados',
    )
    
    notas = fields.Html(string='Notas')
    
    fecha_recepcion = fields.Date(
        string='Fecha de Recepción',
        default=fields.Date.context_today,
        tracking=True,
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        required=True,
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
                    'residuo.recepcion.seq'
                ) or _('Nueva')
        return super().create(vals_list)

    def action_confirmar(self):
        for rec in self:
            if rec.estado != 'borrador':
                raise UserError(_('La recepción ya ha sido confirmada.'))
            if not rec.linea_ids:
                raise UserError(_('Debe agregar al menos un residuo a recolectar.'))

            # Validar que todas las líneas tengan producto seleccionado
            for linea in rec.linea_ids:
                if not linea.product_id:
                    raise UserError(
                        _('Debe seleccionar el "Producto Destino" para el residuo: %s') 
                        % (linea.descripcion_origen or 'Sin descripción')
                    )
                
                # Doble validación de seguridad para tipo consu
                if linea.product_id.type != 'consu':
                     raise ValidationError(
                        _('El producto seleccionado "%s" debe ser de tipo Consumible (consu).') 
                        % linea.product_id.name
                    )

                if linea.cantidad <= 0:
                    raise ValidationError(
                        _('La cantidad del producto %s debe ser mayor a 0.')
                        % linea.product_id.display_name
                    )

            picking = rec._crear_picking()
            rec.write({
                'estado': 'confirmado',
                'picking_id': picking.id,
            })

    def _crear_picking(self):
        self.ensure_one()
        stock_location_cliente = (
            self.partner_id.property_stock_customer
            or self.env.ref('stock.stock_location_customers')
        )
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
            # Crear movimiento
            move = self.env['stock.move'].create({
                'name': linea.product_id.display_name,
                'product_id': linea.product_id.id,
                'product_uom_qty': linea.cantidad,
                'product_uom': linea.product_id.uom_id.id,
                'picking_id': picking.id,
                'location_id': stock_location_cliente.id,
                'location_dest_id': stock_location_destino.id,
            })
            
            # Crear línea detallada con lote asignado
            move_line_vals = {
                'move_id': move.id,
                'picking_id': picking.id,
                'product_id': linea.product_id.id,
                'product_uom_id': linea.product_id.uom_id.id,
                'quantity': linea.cantidad,
                'location_id': stock_location_cliente.id,
                'location_dest_id': stock_location_destino.id,
            }
            
            # Asignar el número de manifiesto como nombre de lote
            if linea.lote_asignado:
                move_line_vals['lot_name'] = linea.lote_asignado
                
            self.env['stock.move.line'].create(move_line_vals)

        picking.action_confirm()
        picking.action_assign()

        if picking.state in ('assigned', 'confirmed'):
            # Intentar validar automáticamente evitando wizards
            ctx = self.env.context.copy()
            ctx.update({'skip_backorder': True})
            
            res = picking.with_context(ctx).button_validate()
            if isinstance(res, dict) and res.get('res_model') == 'stock.backorder.confirmation':
                wizard = self.env['stock.backorder.confirmation'].with_context(
                    **res.get('context', {})
                ).create({})
                wizard.process()
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

    recepcion_id = fields.Many2one(
        'residuo.recepcion',
        string='Recepción',
        ondelete='cascade',
        required=True,
    )

    # Campo izquierdo: Nota/Descripción original del manifiesto
    descripcion_origen = fields.Char(
        string='Descripción Manifiesto',
        readonly=True,
        help="Nombre del residuo tal como aparece en el manifiesto."
    )

    # Campo derecho: Selector de producto (limpio al inicio)
    product_id = fields.Many2one(
        'product.product',
        string='Producto Destino',
        required=False,  # No requerido al crear, sí al confirmar
        domain=[('type', '=', 'consu')], # Solo consumibles
        context={'create': False},
        help="Seleccione el producto consumible correspondiente."
    )

    # Campo de lote: Número de manifiesto
    lote_asignado = fields.Char(
        string='Lote / Manifiesto',
        help="Número de lote asignado (corresponde al número de manifiesto)"
    )

    cantidad = fields.Float(string='Cantidad', required=True, default=0.0)
    
    unidad = fields.Char(
        string='Unidad de Medida',
        related='product_id.uom_id.name',
        readonly=True,
    )
    
    categoria = fields.Char(
        string='Categoría',
        related='product_id.categ_id.name',
        readonly=True,
    )

    @api.constrains('cantidad')
    def _check_cantidad(self):
        for linea in self:
            if linea.cantidad <= 0:
                raise ValidationError(_('La cantidad debe ser mayor a 0.'))

class ProductTemplate(models.Model):
    _inherit = 'product.template'
    es_recoleccion = fields.Boolean(string="Es un servicio de recolección")