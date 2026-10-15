"""Panel de administración: útil para cargar datos rápido durante el desarrollo."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (Actividad, Auditoria, Cargo, Compromiso, Delegacion, Evidencia, Funcionario,
                     HistorialCompromiso, Item, MetaFuncionario, Notificacion, Periodo,
                     ReclamoFelicitacion, Rol, Validacion)


@admin.register(Funcionario)
class FuncionarioAdmin(UserAdmin):
    list_display = ("username", "get_full_name", "delegacion", "cargo", "rol", "is_active")
    list_filter = ("delegacion", "cargo", "rol", "is_active")
    fieldsets = UserAdmin.fieldsets + (
        ("Datos del SGR", {"fields": ("delegacion", "cargo", "rol", "telefono")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Datos del SGR", {"fields": ("delegacion", "cargo", "rol", "telefono")}),
    )


@admin.register(Delegacion)
class DelegacionAdmin(admin.ModelAdmin):
    list_display = ("nombre", "sector", "activa")
    search_fields = ("nombre",)


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("nombre", "cargo", "ponderador", "vigente")
    list_filter = ("cargo", "vigente")


@admin.register(MetaFuncionario)
class MetaAdmin(admin.ModelAdmin):
    list_display = ("funcionario", "item", "periodo", "valor_objetivo", "definida_por")
    list_filter = ("periodo", "funcionario__delegacion")


@admin.register(Actividad)
class ActividadAdmin(admin.ModelAdmin):
    list_display = ("fecha", "funcionario", "item", "estado_evidencia")
    list_filter = ("item__cargo", "funcionario__delegacion", "fecha")
    search_fields = ("solicitud", "accion")


@admin.register(Evidencia)
class EvidenciaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "actividad", "momento", "estado", "cargada_en")
    list_filter = ("estado", "momento")


@admin.register(Compromiso)
class CompromisoAdmin(admin.ModelAdmin):
    list_display = ("descripcion", "delegacion", "responsable", "fecha_comprometida", "estado")
    list_filter = ("estado", "delegacion")


@admin.register(ReclamoFelicitacion)
class ReclamoAdmin(admin.ModelAdmin):
    list_display = ("tipo", "canal", "delegacion", "funcionario", "estado", "fecha")
    list_filter = ("tipo", "canal", "delegacion", "estado")


admin.site.register([Rol, Cargo, Periodo, Validacion, HistorialCompromiso, Notificacion, Auditoria])
admin.site.site_header = "SGR · Delegaciones Municipales de La Serena"
admin.site.site_title = "SGR"
