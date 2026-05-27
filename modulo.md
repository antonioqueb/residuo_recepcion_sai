## ./__init__.py
```py
from . import models
```

## ./__manifest__.py
```py
{
    'name': 'Recepción de Residuos',
    'version': '19.0.2.0.0',
    'summary': 'Gestión de recepción de residuos peligrosos desde órdenes de venta',
    'category': 'Inventory',
    'author': 'Alphaqueb Consulting',
    'license': 'LGPL-3',
    'depends': ['sale_management', 'stock', 'product', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/secuencia_recepcion.xml',
        'data/tipo_manejo_data.xml',
        'data/cron_caducidad.xml',

        'views/recepcion_views.xml',      # ← primero
        'views/tipo_manejo_views.xml',    # ← después
        'views/stock_lot_views.xml',
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': True,
}```

## ./data/cron_caducidad.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo noupdate="1">
    <record id="cron_alerta_caducidad_residuos" model="ir.cron">
        <field name="name">Alertas de Caducidad de Residuos Peligrosos</field>
        <field name="model_id" ref="stock.model_stock_lot"/>
        <field name="state">code</field>
        <field name="code">model._cron_alertas_caducidad_residuos()</field>
        <field name="interval_number">1</field>
        <field name="interval_type">days</field>
        <field name="active">True</field>
    </record>
</odoo>```

## ./data/secuencia_recepcion.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo noupdate="1">
    <record id="seq_residuo_recepcion" model="ir.sequence">
        <field name="name">Recepción de Residuos</field>
        <field name="code">residuo.recepcion.seq</field>
        <field name="prefix">REC-%(year)s-%(month)s-</field>
        <field name="padding">4</field>
        <field name="number_increment">1</field>
        <field name="implementation">no_gap</field>
        <field name="use_date_range">True</field>
    </record>
</odoo>
```

## ./data/tipo_manejo_data.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo noupdate="1">
    <record id="tipo_manejo_incineracion" model="residuo.tipo.manejo">
        <field name="name">Incineración</field>
        <field name="code">INC</field>
        <field name="description">Destrucción térmica de residuos peligrosos</field>
        <field name="sequence">10</field>
    </record>
    <record id="tipo_manejo_confinamiento" model="residuo.tipo.manejo">
        <field name="name">Confinamiento</field>
        <field name="code">CON</field>
        <field name="description">Disposición final en celda de confinamiento controlado</field>
        <field name="sequence">20</field>
    </record>
    <record id="tipo_manejo_reciclaje" model="residuo.tipo.manejo">
        <field name="name">Reciclaje</field>
        <field name="code">REC</field>
        <field name="description">Recuperación y reutilización de materiales</field>
        <field name="sequence">30</field>
    </record>
    <record id="tipo_manejo_tratamiento" model="residuo.tipo.manejo">
        <field name="name">Tratamiento Físico-Químico</field>
        <field name="code">TFQ</field>
        <field name="description">Tratamiento mediante procesos físicos o químicos</field>
        <field name="sequence">40</field>
    </record>
    <record id="tipo_manejo_bioremediacion" model="residuo.tipo.manejo">
        <field name="name">Biorremediación</field>
        <field name="code">BIO</field>
        <field name="description">Tratamiento biológico de residuos</field>
        <field name="sequence">50</field>
    </record>
    <record id="tipo_manejo_coprocesamiento" model="residuo.tipo.manejo">
        <field name="name">Co-procesamiento</field>
        <field name="code">COP</field>
        <field name="description">Uso como combustible alterno en hornos cementeros</field>
        <field name="sequence">60</field>
    </record>
    <record id="tipo_manejo_estabilizacion" model="residuo.tipo.manejo">
        <field name="name">Estabilización / Solidificación</field>
        <field name="code">EST</field>
        <field name="description">Tratamiento para reducir la movilidad de contaminantes</field>
        <field name="sequence">70</field>
    </record>
</odoo>```

## ./models/__init__.py
```py
from . import tipo_manejo
from . import stock_lot
from . import recepcion
from . import sale_order```

## ./models/recepcion.py
```py
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
    es_recoleccion = fields.Boolean(string="Es un servicio de recolección")```

## ./models/sale_order.py
```py
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
        }```

## ./models/stock_lot.py
```py
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
            _logger.info('Actividad de caducidad creada para lote %s', lote.name)```

## ./models/tipo_manejo.py
```py
from odoo import models, fields


class TipoManejo(models.Model):
    _name = 'residuo.tipo.manejo'
    _description = 'Tipo de Manejo de Residuos'
    _order = 'sequence, name'

    name = fields.Char(string='Nombre', required=True)
    code = fields.Char(string='Código', required=True)
    description = fields.Text(string='Descripción')
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
    )

    _sql_constraints = [
        ('code_company_uniq', 'unique(code, company_id)',
         'El código del tipo de manejo debe ser único por compañía.'),
    ]```

## ./views/recepcion_views.xml
```xml
<?xml version="1.0" encoding="UTF-8"?>
<odoo>
    <record id="view_residuo_recepcion_form" model="ir.ui.view">
        <field name="name">residuo.recepcion.form</field>
        <field name="model">residuo.recepcion</field>
        <field name="arch" type="xml">
            <form string="Recepción de Residuos">
                <header>
                    <button name="action_confirmar" type="object"
                            string="Confirmar Recepción" class="btn-primary"
                            invisible="estado != 'borrador'"
                            confirm="¿Ha verificado productos destino, tipo de manejo y clasificación CRETIB?"/>
                    <button name="action_cancelar" type="object" string="Cancelar"
                            invisible="estado not in ('borrador', 'confirmado')"/>
                    <button name="action_borrador" type="object"
                            string="Volver a Borrador"
                            invisible="estado != 'cancelado'"/>
                    <field name="estado" widget="statusbar"
                           statusbar_visible="borrador,confirmado"/>
                </header>
                <sheet>
                    <div class="oe_title">
                        <h1><field name="name" readonly="1"/></h1>
                    </div>
                    <group>
                        <group>
                            <field name="sale_order_id" readonly="estado != 'borrador'"/>
                            <field name="partner_id" readonly="estado != 'borrador'"/>
                            <field name="fecha_recepcion" readonly="estado != 'borrador'"/>
                        </group>
                        <group>
                            <field name="picking_id" readonly="1"/>
                            <field name="company_id" groups="base.group_multi_company"/>
                        </group>
                    </group>
                    <notebook>
                        <page string="Residuos Recolectados">
                            <div class="alert alert-info" role="alert"
                                 invisible="estado != 'borrador'">
                                <strong>Instrucciones:</strong>
                                Verifique la descripción, seleccione el producto,
                                asigne el <b>Tipo de Manejo</b> y verifique la clasificación <b>CRETIB</b>.
                                Al confirmar, esta información se propagará al lote.
                            </div>
                            <field name="linea_ids" readonly="estado != 'borrador'">
                                <list editable="bottom" create="false" delete="true">
                                    <field name="descripcion_origen"
                                           string="Descripción Manifiesto"
                                           readonly="1" force_save="1" decoration-bf="1"/>
                                    <field name="product_id" string="Producto Destino"
                                           placeholder="Seleccione consumible..."
                                           options="{'no_create': True, 'no_open': True}"/>
                                    <field name="lote_asignado" string="Lote (Manifiesto)"/>
                                    <field name="cantidad"/>
                                    <field name="tipo_manejo_id" string="Tipo de Manejo"
                                           options="{'no_create_edit': True}"/>
                                    <field name="clasificacion_corrosivo" string="C"/>
                                    <field name="clasificacion_reactivo" string="R"/>
                                    <field name="clasificacion_explosivo" string="E"/>
                                    <field name="clasificacion_toxico" string="T"/>
                                    <field name="clasificacion_inflamable" string="I"/>
                                    <field name="clasificacion_biologico" string="B"/>
                                    <field name="clasificaciones_display" string="CRETIB" optional="hide"/>
                                    <field name="unidad" readonly="1" optional="hide"/>
                                    <field name="categoria" readonly="1" optional="hide"/>
                                </list>
                            </field>
                        </page>
                        <page string="Notas">
                            <field name="notas" placeholder="Notas internas..."/>
                        </page>
                    </notebook>
                </sheet>
                <chatter/>
            </form>
        </field>
    </record>

    <record id="view_residuo_recepcion_list" model="ir.ui.view">
        <field name="name">residuo.recepcion.list</field>
        <field name="model">residuo.recepcion</field>
        <field name="arch" type="xml">
            <list>
                <field name="name" decoration-bf="1"/>
                <field name="sale_order_id" optional="show"/>
                <field name="partner_id"/>
                <field name="fecha_recepcion"/>
                <field name="picking_id" optional="hide"/>
                <field name="estado"
                       decoration-success="estado == 'confirmado'"
                       decoration-muted="estado == 'cancelado'"
                       decoration-info="estado == 'borrador'" widget="badge"/>
            </list>
        </field>
    </record>

    <record id="view_residuo_recepcion_search" model="ir.ui.view">
        <field name="name">residuo.recepcion.search</field>
        <field name="model">residuo.recepcion</field>
        <field name="arch" type="xml">
            <search>
                <field name="name"/>
                <field name="sale_order_id"/>
                <field name="partner_id"/>
                <filter string="Borrador" name="borrador" domain="[('estado', '=', 'borrador')]"/>
                <filter string="Confirmado" name="confirmado" domain="[('estado', '=', 'confirmado')]"/>
                <filter string="Cancelado" name="cancelado" domain="[('estado', '=', 'cancelado')]"/>
                <separator/>
                <filter string="Hoy" name="hoy"
                        domain="[('fecha_recepcion', '=', context_today().strftime('%Y-%m-%d'))]"/>
                <filter string="Cliente" name="group_partner" context="{'group_by': 'partner_id'}"/>
                <filter string="Estado" name="group_estado" context="{'group_by': 'estado'}"/>
            </search>
        </field>
    </record>

    <record id="action_residuo_recepcion" model="ir.actions.act_window">
        <field name="name">Recolecciones</field>
        <field name="res_model">residuo.recepcion</field>
        <field name="view_mode">list,form</field>
        <field name="context">{'search_default_borrador': 1}</field>
    </record>

    <menuitem id="menu_residuo_root" name="Recolecciones" sequence="10"
              web_icon="residuo_recepcion_sai,static/description/icon.png"/>
    <menuitem id="menu_residuo_recepcion" name="Recepciones"
              parent="menu_residuo_root" action="action_residuo_recepcion" sequence="10"/>
</odoo>```

## ./views/sale_order_views.xml
```xml
<?xml version="1.0" encoding="UTF-8"?>
<odoo>
    <!-- Vista heredada del formulario de Sale Order -->
    <record id="view_order_form_inherit_recepcion" model="ir.ui.view">
        <field name="name">sale.order.form.recepcion.inherit</field>
        <field name="model">sale.order</field>
        <field name="inherit_id" ref="sale.view_order_form"/>
        <field name="arch" type="xml">
            <xpath expr="//div[@name='button_box']" position="inside">
                <button class="oe_stat_button" type="object"
                        name="action_ver_recepciones"
                        invisible="recepcion_count == 0"
                        icon="fa-truck">
                    <field name="recepcion_count" widget="statinfo"
                           string="Recepciones"/>
                </button>
            </xpath>
        </field>
    </record>
</odoo>```

## ./views/stock_lot_views.xml
```xml
<?xml version="1.0" encoding="UTF-8"?>
<odoo>
    <record id="view_stock_lot_form_residuo" model="ir.ui.view">
        <field name="name">stock.lot.form.residuo</field>
        <field name="model">stock.lot</field>
        <field name="inherit_id" ref="stock.view_production_lot_form"/>
        <field name="arch" type="xml">
            <xpath expr="//sheet" position="inside">
                <notebook position="inside">
                    <page string="Residuo Peligroso" name="residuo_peligroso">
                        <div class="alert alert-danger" role="alert"
                             invisible="caducidad_estado != 'expired'">
                            <strong>⚠️ VENCIDO:</strong> Este lote ha superado la fecha límite de tratamiento.
                        </div>
                        <div class="alert alert-warning" role="alert"
                             invisible="caducidad_estado != 'warning'">
                            <strong>⏰ PRÓXIMO A VENCER:</strong> Quedan
                            <field name="dias_restantes_caducidad" class="d-inline"/> días
                            para la fecha límite de tratamiento.
                        </div>
                        <group col="2">
                            <group string="Manejo y Caducidad">
                                <field name="tipo_manejo_id" options="{'no_create_edit': True}"/>
                                <field name="fecha_recepcion_residuo"/>
                                <field name="fecha_caducidad_residuo"/>
                                <field name="dias_restantes_caducidad"/>
                                <field name="caducidad_estado" widget="badge"
                                       decoration-success="caducidad_estado == 'ok'"
                                       decoration-warning="caducidad_estado == 'warning'"
                                       decoration-danger="caducidad_estado == 'expired'"/>
                            </group>
                            <group string="Clasificación CRETIB">
                                <field name="clasificacion_corrosivo"/>
                                <field name="clasificacion_reactivo"/>
                                <field name="clasificacion_explosivo"/>
                                <field name="clasificacion_toxico"/>
                                <field name="clasificacion_inflamable"/>
                                <field name="clasificacion_biologico"/>
                                <field name="clasificaciones_display"/>
                            </group>
                        </group>
                    </page>
                </notebook>
            </xpath>
        </field>
    </record>

    <record id="view_stock_lot_list_residuo" model="ir.ui.view">
        <field name="name">stock.lot.list.residuo</field>
        <field name="model">stock.lot</field>
        <field name="inherit_id" ref="stock.view_production_lot_tree"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='product_id']" position="after">
                <field name="tipo_manejo_id" optional="show"/>
                <field name="clasificaciones_display" string="CRETIB" optional="show"/>
                <field name="fecha_caducidad_residuo" optional="show"
                       decoration-danger="caducidad_estado == 'expired'"
                       decoration-warning="caducidad_estado == 'warning'"/>
                <field name="dias_restantes_caducidad" optional="hide"/>
                <field name="caducidad_estado" widget="badge" optional="show"
                       decoration-success="caducidad_estado == 'ok'"
                       decoration-warning="caducidad_estado == 'warning'"
                       decoration-danger="caducidad_estado == 'expired'"/>
            </xpath>
        </field>
    </record>

    <record id="view_stock_lot_search_residuo" model="ir.ui.view">
        <field name="name">stock.lot.search.residuo</field>
        <field name="model">stock.lot</field>
        <field name="inherit_id" ref="stock.search_product_lot_filter"/>
        <field name="arch" type="xml">
            <xpath expr="//search" position="inside">
                <field name="tipo_manejo_id"/>
                <separator/>
                <filter string="Próximos a vencer (30 días)" name="proximos_vencer"
                        domain="[('fecha_caducidad_residuo', '&gt;=', (context_today()).strftime('%Y-%m-%d')),
                                 ('fecha_caducidad_residuo', '&lt;=', (context_today() + datetime.timedelta(days=30)).strftime('%Y-%m-%d'))]"/>
                <filter string="Vencidos" name="vencidos"
                        domain="[('fecha_caducidad_residuo', '&lt;', context_today().strftime('%Y-%m-%d'))]"/>
                <separator/>
                <filter string="Tipo de Manejo" name="group_tipo_manejo"
                        context="{'group_by': 'tipo_manejo_id'}"/>
            </xpath>
        </field>
    </record>
</odoo>```

## ./views/tipo_manejo_views.xml
```xml
<?xml version="1.0" encoding="UTF-8"?>
<odoo>
    <record id="view_tipo_manejo_list" model="ir.ui.view">
        <field name="name">residuo.tipo.manejo.list</field>
        <field name="model">residuo.tipo.manejo</field>
        <field name="arch" type="xml">
            <list editable="bottom">
                <field name="sequence" widget="handle"/>
                <field name="code"/>
                <field name="name"/>
                <field name="description"/>
                <field name="active" optional="hide"/>
            </list>
        </field>
    </record>

    <record id="view_tipo_manejo_form" model="ir.ui.view">
        <field name="name">residuo.tipo.manejo.form</field>
        <field name="model">residuo.tipo.manejo</field>
        <field name="arch" type="xml">
            <form string="Tipo de Manejo">
                <sheet>
                    <group>
                        <group>
                            <field name="name"/>
                            <field name="code"/>
                        </group>
                        <group>
                            <field name="sequence"/>
                            <field name="active"/>
                            <field name="company_id" groups="base.group_multi_company"/>
                        </group>
                    </group>
                    <group>
                        <field name="description"/>
                    </group>
                </sheet>
            </form>
        </field>
    </record>

    <record id="action_tipo_manejo" model="ir.actions.act_window">
        <field name="name">Tipos de Manejo</field>
        <field name="res_model">residuo.tipo.manejo</field>
        <field name="view_mode">list,form</field>
    </record>

    <menuitem id="menu_tipo_manejo"
              name="Tipos de Manejo"
              parent="menu_residuo_root"
              action="action_tipo_manejo"
              sequence="50"/>
</odoo>```

