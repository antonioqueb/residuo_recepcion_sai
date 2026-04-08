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
}