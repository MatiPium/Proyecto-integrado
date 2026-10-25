"""Pruebas de los CRUD y de las validaciones principales."""

from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import (Actividad, Cargo, Compromiso, Delegacion, Evidencia, Funcionario, Item,
                     MetaFuncionario, Periodo, Rol, Validacion)


class BaseDatos(TestCase):
    def setUp(self):
        self.deleg = Delegacion.objects.create(nombre="Las Compañías")
        self.cargo = Cargo.objects.create(nombre="Gestor Social")
        self.item = Item.objects.create(cargo=self.cargo, nombre="Visita a terreno", ponderador=40)
        self.periodo = Periodo.objects.create(nombre="T3", fecha_inicio=date.today() - timedelta(days=30),
                                              fecha_termino=date.today() + timedelta(days=30))
        rol_func = Rol.objects.create(codigo=Rol.FUNCIONARIO)
        rol_coord = Rol.objects.create(codigo=Rol.COORDINADOR)
        rol_verif = Rol.objects.create(codigo=Rol.VERIFICADOR)
        self.func = Funcionario.objects.create_user("camila", password="clave12345", rol=rol_func,
                                                    delegacion=self.deleg, cargo=self.cargo)
        self.coord = Funcionario.objects.create_user("coord", password="clave12345", rol=rol_coord)
        self.verif = Funcionario.objects.create_user("pedro", password="clave12345", rol=rol_verif,
                                                     delegacion=self.deleg)


class ValidacionesModelo(BaseDatos):
    def test_ponderadores_no_superan_100(self):
        item = Item(cargo=self.cargo, nombre="Otro ítem", ponderador=70)
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_actividad_no_acepta_fecha_futura(self):
        actividad = Actividad(funcionario=self.func, item=self.item, fecha=date.today() + timedelta(days=1),
                              solicitud="Solicitud de prueba larga", accion="Acción ejecutada de prueba")
        with self.assertRaises(ValidationError):
            actividad.full_clean()

    def test_solo_coordinacion_define_metas(self):
        meta = MetaFuncionario(funcionario=self.func, item=self.item, periodo=self.periodo,
                               valor_objetivo=10, definida_por=self.func)
        with self.assertRaises(ValidationError):
            meta.full_clean()

    def test_rechazo_exige_observacion(self):
        actividad = Actividad.objects.create(funcionario=self.func, item=self.item, fecha=date.today(),
                                             solicitud="Solicitud de prueba larga", accion="Acción de prueba larga")
        evidencia = Evidencia.objects.create(actividad=actividad, archivo="evidencias/x.jpg")
        validacion = Validacion(evidencia=evidencia, verificador=self.verif, decision=Evidencia.RECHAZADA)
        with self.assertRaises(ValidationError):
            validacion.full_clean()

    def test_nadie_valida_su_propia_evidencia(self):
        actividad = Actividad.objects.create(funcionario=self.func, item=self.item, fecha=date.today(),
                                             solicitud="Solicitud de prueba larga", accion="Acción de prueba larga")
        evidencia = Evidencia.objects.create(actividad=actividad, archivo="evidencias/x.jpg")
        validacion = Validacion(evidencia=evidencia, verificador=self.func,
                                decision=Evidencia.APROBADA, observacion="ok")
        with self.assertRaises(ValidationError):
            validacion.full_clean()

    def test_codigo_de_evidencia_se_genera_solo(self):
        actividad = Actividad.objects.create(funcionario=self.func, item=self.item, fecha=date.today(),
                                             solicitud="Solicitud de prueba larga", accion="Acción de prueba larga")
        evidencia = Evidencia.objects.create(actividad=actividad, archivo="evidencias/x.jpg")
        self.assertTrue(evidencia.codigo.startswith("GES"))

    def test_avance_cuenta_solo_evidencia_aprobada(self):
        meta = MetaFuncionario.objects.create(funcionario=self.func, item=self.item, periodo=self.periodo,
                                              valor_objetivo=10, definida_por=self.coord)
        actividad = Actividad.objects.create(funcionario=self.func, item=self.item, fecha=date.today(),
                                             solicitud="Solicitud de prueba larga", accion="Acción de prueba larga",
                                             contacto_nombre='Vecina de prueba', contacto_telefono='912345678')
        evidencia = Evidencia.objects.create(actividad=actividad, archivo="evidencias/x.jpg")
        self.assertEqual(meta.avance, 0)
        Validacion.objects.create(evidencia=evidencia, verificador=self.verif,
                                  decision=Evidencia.APROBADA, observacion="Conforme")
        self.assertEqual(meta.avance, 1)


class CrudVistas(BaseDatos):
    def test_crear_delegacion_requiere_coordinacion(self):
        self.client.login(username="camila", password="clave12345")
        respuesta = self.client.post(reverse("delegacion_create"), {"nombre": "Centro", "activa": True})
        self.assertFalse(Delegacion.objects.filter(nombre="Centro").exists())
        self.assertEqual(respuesta.status_code, 302)  # redirige al inicio con mensaje de error

    def test_coordinacion_crea_y_edita_delegacion(self):
        self.client.login(username="coord", password="clave12345")
        self.client.post(reverse("delegacion_create"), {"nombre": "Centro", "activa": True})
        delegacion = Delegacion.objects.get(nombre="Centro")
        self.client.post(reverse("delegacion_update", args=[delegacion.pk]),
                         {"nombre": "Centro Histórico", "activa": True})
        delegacion.refresh_from_db()
        self.assertEqual(delegacion.nombre, "Centro Histórico")

    def test_formulario_actividad_muestra_error_de_validacion(self):
        self.client.login(username="camila", password="clave12345")
        respuesta = self.client.post(reverse("actividad_create"), {
            "fecha": date.today(), "item": self.item.pk,
            "solicitud": "Solicitud de prueba larga", "accion": "corta",
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "al menos 10 caracteres")
        self.assertEqual(Actividad.objects.count(), 0)

    def test_compromiso_sin_fecha_no_se_guarda(self):
        self.client.login(username="camila", password="clave12345")
        respuesta = self.client.post(reverse("compromiso_create"), {
            "delegacion": self.deleg.pk, "descripcion": "Poda de árboles",
            "responsable": self.func.pk, "estado": Compromiso.INGRESADO,
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Compromiso.objects.count(), 0)

    def test_cambio_de_estado_genera_historial(self):
        self.client.login(username="camila", password="clave12345")
        compromiso = Compromiso.objects.create(delegacion=self.deleg, responsable=self.func,
                                               descripcion="Retiro de escombros",
                                               fecha_comprometida=date.today() + timedelta(days=5))
        self.client.post(reverse("compromiso_detalle", args=[compromiso.pk]),
                         {"estado": Compromiso.EN_PROCESO, "observacion": "Se deriva a DISERCO."})
        compromiso.refresh_from_db()
        self.assertEqual(compromiso.estado, Compromiso.EN_PROCESO)
        self.assertEqual(compromiso.historial.count(), 1)

    def test_listados_responden(self):
        self.client.login(username="coord", password="clave12345")
        for nombre in ["inicio", "delegacion_list", "cargo_list", "item_list", "periodo_list",
                       "funcionario_list", "meta_list", "actividad_list", "verificacion_list",
                       "compromiso_list", "reclamo_list", "indicadores", "auditoria"]:
            with self.subTest(url=nombre):
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 200)
