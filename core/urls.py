"""Rutas de la aplicación core (SGR)."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.InicioView.as_view(), name="inicio"),

    # Delegaciones
    path("delegaciones/", views.DelegacionList.as_view(), name="delegacion_list"),
    path("delegaciones/nueva/", views.DelegacionCreate.as_view(), name="delegacion_create"),
    path("delegaciones/<int:pk>/editar/", views.DelegacionUpdate.as_view(), name="delegacion_update"),
    path("delegaciones/<int:pk>/eliminar/", views.DelegacionDelete.as_view(), name="delegacion_delete"),

    # Cargos
    path("cargos/", views.CargoList.as_view(), name="cargo_list"),
    path("cargos/nuevo/", views.CargoCreate.as_view(), name="cargo_create"),
    path("cargos/<int:pk>/editar/", views.CargoUpdate.as_view(), name="cargo_update"),
    path("cargos/<int:pk>/eliminar/", views.CargoDelete.as_view(), name="cargo_delete"),

    # Ítems
    path("items/", views.ItemList.as_view(), name="item_list"),
    path("items/nuevo/", views.ItemCreate.as_view(), name="item_create"),
    path("items/<int:pk>/editar/", views.ItemUpdate.as_view(), name="item_update"),
    path("items/<int:pk>/eliminar/", views.ItemDelete.as_view(), name="item_delete"),

    # Períodos
    path("periodos/", views.PeriodoList.as_view(), name="periodo_list"),
    path("periodos/nuevo/", views.PeriodoCreate.as_view(), name="periodo_create"),
    path("periodos/<int:pk>/editar/", views.PeriodoUpdate.as_view(), name="periodo_update"),
    path("periodos/<int:pk>/eliminar/", views.PeriodoDelete.as_view(), name="periodo_delete"),

    # Funcionarios
    path("funcionarios/", views.FuncionarioList.as_view(), name="funcionario_list"),
    path("funcionarios/nuevo/", views.FuncionarioCreate.as_view(), name="funcionario_create"),
    path("funcionarios/<int:pk>/editar/", views.FuncionarioUpdate.as_view(), name="funcionario_update"),
    path("funcionarios/<int:pk>/eliminar/", views.FuncionarioDelete.as_view(), name="funcionario_delete"),

    # Metas
    path("metas/", views.MetaList.as_view(), name="meta_list"),
    path("metas/nueva/", views.MetaCreate.as_view(), name="meta_create"),
    path("metas/<int:pk>/editar/", views.MetaUpdate.as_view(), name="meta_update"),
    path("metas/<int:pk>/eliminar/", views.MetaDelete.as_view(), name="meta_delete"),

    # Actividades y evidencias
    path("actividades/", views.ActividadList.as_view(), name="actividad_list"),
    path("actividades/nueva/", views.ActividadCreate.as_view(), name="actividad_create"),
    path("actividades/<int:pk>/", views.ActividadDetalle.as_view(), name="actividad_detalle"),
    path("actividades/<int:pk>/editar/", views.ActividadUpdate.as_view(), name="actividad_update"),
    path("actividades/<int:pk>/eliminar/", views.ActividadDelete.as_view(), name="actividad_delete"),

    # Verificación (CU-08)
    path("verificacion/", views.BandejaVerificacion.as_view(), name="verificacion_list"),
    path("verificacion/<int:pk>/", views.VerificarEvidencia.as_view(), name="verificacion_detalle"),

    # Agenda colectiva
    path("agenda/", views.CompromisoList.as_view(), name="compromiso_list"),
    path("agenda/nuevo/", views.CompromisoCreate.as_view(), name="compromiso_create"),
    path("agenda/<int:pk>/", views.CompromisoDetalle.as_view(), name="compromiso_detalle"),
    path("agenda/<int:pk>/editar/", views.CompromisoUpdate.as_view(), name="compromiso_update"),
    path("agenda/<int:pk>/eliminar/", views.CompromisoDelete.as_view(), name="compromiso_delete"),

    # Reclamos y felicitaciones
    path("reclamos/", views.ReclamoList.as_view(), name="reclamo_list"),
    path("reclamos/nuevo/", views.ReclamoCreate.as_view(), name="reclamo_create"),
    path("reclamos/<int:pk>/editar/", views.ReclamoUpdate.as_view(), name="reclamo_update"),
    path("reclamos/<int:pk>/eliminar/", views.ReclamoDelete.as_view(), name="reclamo_delete"),

    # Indicadores y auditoría
    path("indicadores/", views.IndicadoresView.as_view(), name="indicadores"),
    path("auditoria/", views.AuditoriaList.as_view(), name="auditoria"),
]


# Módulos de la entrega II (nombres de rutas independientes de los CRUD anteriores)
from . import segunda_views as sv
for _clave in sv.CATALOGOS:
    _lista,_crear,_editar=sv.catalogo_clases(_clave)
    urlpatterns.extend([
        path(f'mantenedores/{_clave}/',_lista.as_view(),name=f'{_clave}_list'),
        path(f'mantenedores/{_clave}/nuevo/',_crear.as_view(),name=f'{_clave}_create'),
        path(f'mantenedores/{_clave}/<int:pk>/editar/',_editar.as_view(),name=f'{_clave}_edit'),
        path(f'mantenedores/{_clave}/<int:pk>/desactivar/',sv.catalogo_desactivar,{'clave':_clave},name=f'{_clave}_disable'),
        path(f'mantenedores/{_clave}/excel/',sv.exportar_catalogo,{'clave':_clave},name=f'{_clave}_excel'),
    ])
urlpatterns += [
    path('atenciones/',sv.AtencionList.as_view(),name='atencion_list'),
    path('atenciones/nueva/',sv.AtencionCreate.as_view(),name='atencion_create'),
    path('atenciones/<int:pk>/editar/',sv.AtencionUpdate.as_view(),name='atencion_update'),
    path('api/subatenciones/',sv.subatenciones_json,name='subatenciones_json'),
    path('contexto/delegacion/',sv.cambiar_delegacion,name='cambiar_delegacion'),
    path('recuperar/',sv.recuperar_solicitar,name='recuperar_solicitar'),
    path('recuperar/codigo/',sv.recuperar_validar,name='recuperar_validar'),
    path('recuperar/nueva-clave/',sv.recuperar_nueva,name='recuperar_nueva'),
]

urlpatterns += [path('funcionarios/excel/',sv.exportar_usuarios,name='usuarios_excel')]

from . import comunidad_views as cv
for _clave, (_modelo, _form, _nombre, _campo, _activo) in cv.MODULOS.items():
    _base = {'model': _modelo, 'clave': _clave}
    urlpatterns += [
        path(f'comunidad/{_clave}/', type(f'{_clave}List', (cv.TerritorialList,), _base).as_view(), name=f'{_clave}_list'),
        path(f'comunidad/{_clave}/nuevo/', type(f'{_clave}Create', (cv.TerritorialCreate,), dict(_base, form_class=_form)).as_view(), name=f'{_clave}_create'),
        path(f'comunidad/{_clave}/<int:pk>/', type(f'{_clave}Detalle', (cv.TerritorialDetalle,), _base).as_view(), name=f'{_clave}_detalle'),
        path(f'comunidad/{_clave}/<int:pk>/editar/', type(f'{_clave}Update', (cv.TerritorialUpdate,), dict(_base, form_class=_form)).as_view(), name=f'{_clave}_update'),
        path(f'comunidad/{_clave}/<int:pk>/desactivar/', cv.desactivar, {'clave': _clave}, name=f'{_clave}_disable'),
    ]
urlpatterns += [path('reclamos/<int:pk>/validar/', cv.validar_felicitacion, name='felicitacion_validar')]
