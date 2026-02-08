from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)

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
    
    # Campo inyectado por dependencia inversa (manifiesto)
    # Lo declaramos aquí explícitamente para evitar errores si el mixin falla
    manifiesto_id = fields.Many2one(
        'manifiesto.ambiental',
        string='Manifiesto de Origen',
        readonly=True,
        tracking=True,
    )

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

            for linea in rec.linea_ids:
                if not linea.product_id:
                    raise UserError(
                        _('Debe seleccionar el "Producto Destino" para el residuo: %s') 
                        % (linea.descripcion_origen or 'Sin descripción')
                    )
                
                # Validación ligera para permitir productos almacenables (storable)
                # que son necesarios para llevar control de stock.
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

        # 1. Crear el Picking (Cabecera)
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type_in.id,
            'location_id': stock_location_cliente.id,
            'location_dest_id': stock_location_destino.id,
            'origin': self.name,
            'partner_id': self.partner_id.id,
            'scheduled_date': self.fecha_recepcion or fields.Date.context_today(self),
        })

        for linea in self.linea_ids:
            # === CORRECCIÓN CRÍTICA: Asegurar Configuración del Producto ===
            # Si el producto tiene tracking 'serial' (Único), fallará al recibir granel.
            # Lo forzamos a 'lot' (Lotes) o lo activamos si estaba en 'none' y tenemos lote.
            if linea.lote_asignado and linea.product_id.tracking != 'lot':
                try:
                    _logger.info("Autocorrigiendo tracking del producto %s a 'lot'", linea.product_id.name)
                    linea.product_id.sudo().write({'tracking': 'lot'})
                except Exception as e:
                    _logger.warning("No se pudo cambiar el tracking del producto: %s", str(e))

            # 2. Crear Stock Move
            move = self.env['stock.move'].create({
                'description_picking': linea.product_id.display_name, # Odoo 19: description_picking
                'product_id': linea.product_id.id,
                'product_uom_qty': linea.cantidad,
                'product_uom': linea.product_id.uom_id.id, # Odoo 19: campo legado en move
                'picking_id': picking.id,
                'location_id': stock_location_cliente.id,
                'location_dest_id': stock_location_destino.id,
            })
            
            # 3. Preparar Stock Move Line
            move_line_vals = {
                'move_id': move.id,
                'picking_id': picking.id,
                'product_id': linea.product_id.id,
                'product_uom_id': linea.product_id.uom_id.id, # Odoo 19: campo _id en move.line
                'quantity': linea.cantidad,
                'location_id': stock_location_cliente.id,
                'location_dest_id': stock_location_destino.id,
            }
            
            # === LÓGICA DE LOTES ROBUSTA ===
            if linea.lote_asignado:
                # Limpiar espacios en blanco que causan errores de búsqueda
                lote_nombre = linea.lote_asignado.strip()
                
                # Buscar lote existente EXACTO para evitar errores de "Ya existe"
                lote_existente = self.env['stock.lot'].search([
                    ('name', '=', lote_nombre),
                    ('product_id', '=', linea.product_id.id),
                    ('company_id', '=', self.company_id.id)
                ], limit=1)

                if lote_existente:
                    # Si existe, USAMOS EL ID. Esto evita el error "Serial number already assigned"
                    # siempre y cuando el producto sea tracking='lot'.
                    move_line_vals['lot_id'] = lote_existente.id
                else:
                    # Si no existe, pasamos el NOMBRE para que Odoo lo cree al vuelo
                    move_line_vals['lot_name'] = lote_nombre
                
            self.env['stock.move.line'].create(move_line_vals)

        # 4. Confirmar y Validar
        picking.action_confirm()
        picking.action_assign()

        if picking.state in ('assigned', 'confirmed'):
            ctx = self.env.context.copy()
            ctx.update({'skip_backorder': True})
            
            try:
                # Intentar validar automáticamente
                res = picking.with_context(ctx).button_validate()
                
                # Manejar wizard de backorder si aparece
                if isinstance(res, dict) and res.get('res_model') == 'stock.backorder.confirmation':
                    wizard = self.env['stock.backorder.confirmation'].with_context(
                        **res.get('context', {})
                    ).create({})
                    wizard.process()
                    
            except ValidationError as e:
                # Si falla la validación automática (ej. bloqueo de fecha o lote),
                # no rompemos todo el proceso, dejamos el picking creado en estado 'Asignado'
                # para que el usuario lo revise manualmente.
                picking.message_post(body=f"⚠️ La validación automática falló, favor de validar manualmente. Error: {str(e)}")
                return picking # Retornamos el picking creado aunque no validado
        else:
            raise UserError(_('No se pudo reservar el inventario. Verifique disponibilidad.'))

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
    descripcion_origen = fields.Char(
        string='Descripción Manifiesto',
        readonly=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Producto Destino',
        required=False,
        # Quitamos el domain estricto de consu para permitir almacenables con lotes
        context={'create': False},
    )
    lote_asignado = fields.Char(
        string='Lote / Manifiesto',
    )
    cantidad = fields.Float(string='Cantidad', required=True, default=0.0)
    unidad = fields.Char(related='product_id.uom_id.name', readonly=True)
    categoria = fields.Char(related='product_id.categ_id.name', readonly=True)

    @api.constrains('cantidad')
    def _check_cantidad(self):
        for linea in self:
            if linea.cantidad <= 0:
                raise ValidationError(_('La cantidad debe ser mayor a 0.'))

class ProductTemplate(models.Model):
    _inherit = 'product.template'
    es_recoleccion = fields.Boolean(string="Es un servicio de recolección")