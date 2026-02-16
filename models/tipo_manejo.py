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
    ]