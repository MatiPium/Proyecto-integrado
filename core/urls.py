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
