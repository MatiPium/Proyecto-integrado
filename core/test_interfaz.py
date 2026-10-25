"""Regression checks for the municipal layout and its existing workflows."""
from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse

from .models import Actividad, Cargo, Delegacion, Evidencia, Funcionario, Item, Periodo, Rol
from .segunda_views import CATALOGOS


class InterfazMunicipalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.delegacion = Delegacion.objects.create(nombre="Centro")
        cls.cargo = Cargo.objects.create(nombre="Gestor territorial")
        cls.item = Item.objects.create(nombre="Atención de solicitudes", cargo=cls.cargo, ponderador=40)
        rol = Rol.objects.create(codigo=Rol.COORDINADOR)
        cls.usuario = Funcionario.objects.create_user("coordinacion_ui", rol=rol, delegacion=cls.delegacion)
        cls.autor = Funcionario.objects.create_user("autor_ui", delegacion=cls.delegacion, cargo=cls.cargo)
        cls.periodo = Periodo.objects.create(nombre="Período de prueba", fecha_inicio=date.today() - timedelta(days=1), fecha_termino=date.today() + timedelta(days=30))
        cls.actividad = Actividad.objects.create(funcionario=cls.autor, item=cls.item, fecha=date.today(), solicitud="Solicitud de atención vecinal", accion="Inspección realizada en terreno")
        cls.evidencia = Evidencia.objects.create(actividad=cls.actividad, archivo="evidencias/prueba.png")

    def setUp(self):
        self.client.force_login(self.usuario)

    def test_paginas_y_formularios_renderizan_sin_enlaces_rotos(self):
        routes = ['inicio', 'actividad_list', 'actividad_create', 'verificacion_list',
                  'compromiso_list', 'compromiso_create', 'indicadores', 'meta_list',
                  'meta_create', 'periodo_list', 'periodo_create', 'reclamo_list',
                  'reclamo_create', 'auditoria', 'funcionario_list', 'funcionario_create',
                  'cargo_list', 'cargo_create', 'atencion_list', 'atencion_create']
        routes += [clave + suffix for clave in CATALOGOS for suffix in ('_list', '_create')]
        for route in routes:
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'core/css/sgr.css')
                self.assertContains(response, 'aria-label="Navegación principal"')
        for route, pk in [('actividad_detalle', self.actividad.pk), ('actividad_update', self.actividad.pk),
                          ('actividad_delete', self.actividad.pk), ('verificacion_detalle', self.evidencia.pk),
                          ('funcionario_update', self.usuario.pk), ('roles_edit', self.usuario.rol_id)]:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(reverse(route, args=[pk])).status_code, 200)

    def test_acceso_anonimo_y_recuperacion(self):
        self.client.logout()
        for route in ('login', 'recuperar_solicitar', 'recuperar_validar'):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'auth-brand')
        self.assertRedirects(self.client.get(reverse('actividad_list')), reverse('login') + '?next=' + reverse('actividad_list'))

    def test_exportaciones_de_mantenedores_siguen_disponibles(self):
        for clave in CATALOGOS:
            with self.subTest(catalogo=clave):
                url = reverse(clave + '_excel')
                page = self.client.get(reverse(clave + '_list'), {'q': 'Centro & sector'})
                self.assertContains(page, url + '?q=Centro%20%26%20sector')
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    def test_botones_de_verificacion_conservan_validacion_y_aprobacion(self):
        url = reverse('verificacion_detalle', args=[self.evidencia.pk])
        response = self.client.post(url, {'decision': Evidencia.RECHAZADA, 'observacion': ''})
        self.assertEqual(response.status_code, 200)
        self.evidencia.refresh_from_db()
        self.assertEqual(self.evidencia.estado, Evidencia.PENDIENTE)
        response = self.client.post(url, {'decision': Evidencia.APROBADA, 'observacion': ''})
        self.assertRedirects(response, reverse('verificacion_list'))
        self.evidencia.refresh_from_db()
        self.assertEqual(self.evidencia.estado, Evidencia.APROBADA)
