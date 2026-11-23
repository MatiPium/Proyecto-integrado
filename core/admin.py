"""Panel de administración: útil para cargar datos rápido durante el desarrollo."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (Actividad, AtencionCiudadana, Auditoria, Cargo, Carta, Compromiso,
                     CredencialActivacion, Delegacion, DocumentoCarta, Evidencia, Funcionario,
                     HistorialCarta, HistorialCompromiso, HistorialResponsable, Item,
                     MetaFuncionario, Notificacion, Periodo, ReclamoFelicitacion,
                     RevisionActividad, Rol, Territorio, Validacion)


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
    list_display = ("codigo", "nombre", "sector", "activa")
    readonly_fields = ("codigo",)
    search_fields = ("nombre",)


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "cargo", "ponderador", "vigente", "puntuable", "tipo_resultado")
    readonly_fields = ("codigo",)
    list_filter = ("cargo", "vigente")


@admin.register(MetaFuncionario)
class MetaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "funcionario", "item", "periodo", "valor_objetivo", "ponderacion", "definida_por")
    list_filter = ("periodo", "funcionario__delegacion")

    def save_model(self, request, obj, form, change):
        obj.guardar_validada()


@admin.register(Actividad)
class ActividadAdmin(admin.ModelAdmin):
    list_display = ("codigo", "fecha", "funcionario", "item", "estado_verificacion", "estado_evidencia")
    list_filter = ("item__cargo", "funcionario__delegacion", "fecha")
    search_fields = ("solicitud", "accion")

    def has_delete_permission(self, request, obj=None):
        # Las actividades se eliminan desde el flujo que comprueba cierre y evidencias.
        return False


@admin.register(Evidencia)
class EvidenciaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "actividad", "momento", "estado", "cargada_en")
    list_filter = ("estado", "momento")


@admin.register(Compromiso)
class CompromisoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "descripcion", "delegacion", "responsable", "fecha_comprometida", "estado")
    list_filter = ("estado", "delegacion")


@admin.register(ReclamoFelicitacion)
class ReclamoAdmin(admin.ModelAdmin):
    list_display = ("tipo", "canal", "delegacion", "funcionario", "estado", "fecha")
    list_filter = ("tipo", "canal", "delegacion", "estado")


admin.site.register([Rol, Cargo, Periodo, Validacion, HistorialCompromiso, HistorialResponsable,
                     Notificacion, Auditoria, Territorio, Carta, HistorialCarta, DocumentoCarta,
                     RevisionActividad, AtencionCiudadana, CredencialActivacion])
admin.site.site_header = "SGR · Delegaciones Municipales de La Serena"
admin.site.site_title = "SGR"
