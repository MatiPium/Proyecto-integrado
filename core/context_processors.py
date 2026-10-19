"""Presentation metadata for the shared municipal layout."""


def interfaz(request):
    route = request.resolver_match.url_name if request.resolver_match else ''
    section = route.split('_')[0] if route else ''
    groups = [
        ('inicio', 'Inicio', 'inicio', ('inicio',)),
        ('actividades', 'Actividades', 'actividad_list', ('actividad', 'atencion')),
        ('evidencias', 'Evidencias', 'verificacion_list', ('verificacion',)),
        ('agenda', 'Agenda colectiva', 'compromiso_list', ('compromiso',)),
        ('metas', 'Metas e indicadores', 'indicadores', ('indicadores', 'meta', 'periodo')),
        ('reclamos', 'Reclamos / felicitaciones', 'reclamo_list', ('reclamo',)),
        ('auditoria', 'Auditoría', 'auditoria', ('auditoria',)),
        ('administracion', 'Administración', 'funcionario_list',
         ('funcionario', 'delegacion', 'delegaciones', 'roles', 'cargo', 'item', 'items', 'tipos', 'subatenciones')),
    ]
    active = next((key for key, _, _, sections in groups if section in sections), '')
    if route == 'actividad_detalle':
        active = 'evidencias'
    pages = {
        'inicio': ('Mi tablero', 'Gestión y seguimiento de resultados municipales'),
        'actividad': ('Actividades', 'Registro diario de actividades por funcionario'),
        'atencion': ('Atenciones ciudadanas', 'Registro y seguimiento de la atención a vecinos'),
        'verificacion': ('Evidencias pendientes', 'Revisión de evidencias por delegación'),
        'compromiso': ('Agenda colectiva', 'Seguimiento de compromisos y responsables'),
        'indicadores': ('Tablero de cumplimiento', 'Indicadores ponderados y semáforo por delegación'),
        'meta': ('Metas del período', 'Coordinación · configuración por funcionario y período'),
        'periodo': ('Períodos de gestión', 'Configuración de plazos y umbrales de cumplimiento'),
        'reclamo': ('Reclamos y felicitaciones', 'Canal unificado de atención ciudadana'),
        'auditoria': ('Registro de auditoría', 'Trazabilidad de operaciones: quién, qué y cuándo'),
        'funcionario': ('Gestión de funcionarios', 'Administración de cuentas, cargos y roles'),
        'delegacion': ('Delegaciones', 'Administración de las delegaciones municipales'),
        'delegaciones': ('Delegaciones', 'Administración de las delegaciones municipales'),
        'roles': ('Roles', 'Perfiles de acceso al sistema'),
        'cargo': ('Cargos', 'Configuración de cargos municipales'),
        'item': ('Ítems de gestión', 'Actividades, unidades y ponderadores'),
        'items': ('Ítems de gestión', 'Actividades, unidades y ponderadores'),
        'tipos': ('Tipos de atención', 'Clasificación de la atención ciudadana'),
        'subatenciones': ('Subatenciones', 'Detalle de los tipos de atención'),
    }
    overrides = {
        'actividad_create': 'Registrar actividad', 'actividad_update': 'Editar actividad',
        'actividad_detalle': 'Adjuntar evidencia', 'verificacion_detalle': 'Verificar evidencia',
        'meta_create': 'Definir metas', 'meta_update': 'Editar meta',
        'reclamo_create': 'Registrar reclamo o felicitación',
        'compromiso_create': 'Nuevo compromiso', 'compromiso_detalle': 'Detalle del compromiso',
        'funcionario_create': 'Nuevo funcionario', 'funcionario_update': 'Editar funcionario',
    }
    submenus = {
        'administracion': [('Funcionarios', 'funcionario_list'), ('Delegaciones', 'delegaciones_list'),
                           ('Roles', 'roles_list'), ('Cargos', 'cargo_list'), ('Ítems', 'items_list'),
                           ('Tipos de atención', 'tipos_list'), ('Subatenciones', 'subatenciones_list')],
        'metas': [('Tablero', 'indicadores'), ('Metas', 'meta_list'), ('Períodos', 'periodo_list')],
        'actividades': [('Actividades', 'actividad_list'), ('Atenciones ciudadanas', 'atencion_list')],
    }
    title, subtitle = pages.get(section, ('Sistema de Gestión de Resultados', 'Delegaciones Municipales de La Serena'))
    return {
        'ui_navigation': [{'label': label, 'route': target, 'active': key == active}
                          for key, label, target, _ in groups],
        'ui_title': overrides.get(route, title), 'ui_subtitle': subtitle,
        'ui_back_route': section + '_list' if section in pages and section not in ('inicio', 'indicadores', 'auditoria') else 'inicio',
        'ui_subnavigation': [{'label': label, 'route': target, 'active': section == target.split('_')[0]}
                             for label, target in submenus.get(active, [])],
    }
