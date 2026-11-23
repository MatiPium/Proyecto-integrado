"""Regression checks for the municipal layout and its existing workflows."""
from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse

from .models import Actividad, Cargo, Compromiso, Delegacion, Evidencia, Funcionario, Item, Periodo, Rol, SubAtencion, TipoAtencion, Vecino, Auditoria
from .segunda_views import CATALOGOS


class InterfazMunicipalTests(TestCase):
    def test_estados_compromiso_desde_edicion_y_detalle(self):
        datos = {'delegacion': self.delegacion.pk, 'responsable': self.autor.pk,
                 'descripcion': 'Compromiso de prueba', 'fecha_comprometida': date.today().isoformat(),
                 'estado': Compromiso.INGRESADO}
        self.assertEqual(self.client.post(reverse('compromiso_create'), datos).status_code, 302)
        compromiso = Compromiso.objects.get()
        self.assertEqual(compromiso.historial.count(), 1)
        editar = reverse('compromiso_update', args=[compromiso.pk])
        respuesta = self.client.post(editar, {**datos, 'estado': Compromiso.PENDIENTE})
        self.assertContains(respuesta, 'al menos 5 caracteres')
        compromiso.refresh_from_db()
        self.assertEqual(compromiso.estado, Compromiso.INGRESADO)
        self.assertEqual(compromiso.historial.count(), 1)
        self.assertEqual(self.client.post(editar, {
            **datos, 'estado': Compromiso.PENDIENTE, 'observacion': 'Pendiente de recursos',
        }).status_code, 302)
        detalle = reverse('compromiso_detalle', args=[compromiso.pk])
        for estado in (Compromiso.EN_PROCESO, Compromiso.REALIZADO):
            self.assertEqual(self.client.post(detalle, {
                'estado': estado, 'observacion': 'Avance registrado correctamente',
            }).status_code, 302)
        compromiso.refresh_from_db()
        self.assertEqual(compromiso.estado, Compromiso.REALIZADO)
        self.assertEqual(compromiso.historial.count(), 4)
        self.assertTrue(all(h.autor_id == self.usuario.pk for h in compromiso.historial.all()))
        self.assertEqual(self.client.post(detalle, {
            'estado': Compromiso.REALIZADO, 'observacion': 'Sin cambios adicionales',
        }).status_code, 302)
        self.assertEqual(compromiso.historial.count(), 4)

    def test_autocompletar_vecinos_limita_datos_al_autor_de_la_actividad(self):
        from .forms import ActividadForm
        vecino = Vecino.objects.create(nombre='Vecino local', telefono='912345678',
                                       territorio='Centro', delegacion=self.delegacion)
        otra = Delegacion.objects.create(nombre='Otra delegación')
        Vecino.objects.create(nombre='Vecino ajeno', telefono='999999999',
                              territorio='Otro', delegacion=otra)
        Vecino.objects.create(nombre='Vecino inactivo', telefono='988888888',
                              territorio='Centro', delegacion=self.delegacion, activo=False)
        self.usuario.delegacion = otra
        self.usuario.save(update_fields=['delegacion'])
        form = ActividadForm(usuario=self.usuario, instance=self.actividad)
        self.assertEqual(form.contactos_vecinos, {
            str(vecino.pk): {'nombre': 'Vecino local', 'telefono': '912345678'},
        })
        respuesta = self.client.get(reverse('actividad_update', args=[self.actividad.pk]))
        self.assertContains(respuesta, 'contactos-vecinos')
        self.assertContains(respuesta, '912345678')
        self.assertNotContains(respuesta, '999999999')
        self.assertNotContains(respuesta, '988888888')

    def test_agregar_vecino_desde_actividad(self):
        self.assertContains(self.client.get(reverse('actividad_create')), '+ Agregar vecino')
        url = reverse('actividad_agregar_vecino')
        datos = {'nuevo_vecino-nombre': 'Vecino nuevo', 'nuevo_vecino-telefono': '912345678',
                 'nuevo_vecino-territorio': 'Centro', 'nuevo_vecino-delegacion': '9999'}
        self.assertEqual(self.client.post(url, {}).status_code, 400)
        self.assertFalse(Vecino.objects.exists())
        respuesta = self.client.post(url, datos)
        self.assertEqual(respuesta.status_code, 201)
        vecino = Vecino.objects.get(pk=respuesta.json()['id'])
        self.assertEqual(vecino.delegacion_id, self.usuario.delegacion_id)
        self.assertTrue(vecino.activo)
        self.assertTrue(Auditoria.objects.filter(entidad='vecino', registro_id=str(vecino.pk)).exists())
        self.client.force_login(self.autor)
        self.assertEqual(self.client.post(url, datos).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(url, datos).status_code, 302)

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

    def test_codigos_automaticos_en_altas_y_ediciones(self):
        tipo = TipoAtencion.objects.create(nombre='Atención social', codigo='T01')
        TipoAtencion.objects.create(nombre='Consulta', codigo='T02')
        casos = [
            ('delegaciones', Delegacion, {'nombre': 'Norte', 'comuna': 'La Serena'}, 'D02'),
            ('items', Item, {'nombre': 'Seguimiento', 'cargo': self.cargo.pk, 'tipo_resultado': 'EJE'}, 'I02'),
            ('tipos', TipoAtencion, {'nombre': 'Orientación', 'activo': 'on'}, 'T03'),
            ('subatenciones', SubAtencion, {'nombre': 'Visita', 'tipo': tipo.pk}, 'S01'),
        ]
        for clave, modelo, datos, esperado in casos:
            with self.subTest(catalogo=clave):
                alta = reverse(clave + '_create')
                self.assertNotContains(self.client.get(alta), 'name="codigo"')
                self.assertRedirects(self.client.post(alta, datos), reverse(clave + '_list'))
                registro = modelo.objects.get(nombre=datos['nombre'])
                self.assertEqual(registro.codigo, esperado)
                edicion = reverse(clave + '_edit', args=[registro.pk])
                self.assertNotContains(self.client.get(edicion), 'name="codigo"')
                respuesta = self.client.post(edicion, {**datos, 'codigo': 'MANUAL'}, follow=True)
                self.assertContains(respuesta, esperado)
                registro.refresh_from_db()
                self.assertEqual(registro.codigo, esperado)

    def test_secuencia_no_reutiliza_un_codigo_eliminado(self):
        primero = TipoAtencion.objects.create(nombre='Primero')
        self.assertEqual(primero.codigo, 'T01')
        primero.delete()
        self.assertEqual(TipoAtencion.objects.create(nombre='Segundo').codigo, 'T02')

    def test_editar_item_conserva_unidad_y_ponderador(self):
        self.item.unidad = 'cantidad'
        self.item.save(update_fields=['unidad'])
        for ruta in ('item_update', 'items_edit'):
            with self.subTest(ruta=ruta):
                url = reverse(ruta, args=[self.item.pk])
                pagina = self.client.get(url)
                self.assertNotContains(pagina, 'name="unidad"')
                self.assertNotContains(pagina, 'name="ponderador"')
                respuesta = self.client.post(url, {
                    'cargo': self.cargo.pk, 'nombre': 'Seguimiento actualizado',
                    'tipo_resultado': 'EJE', 'vigente': 'on', 'puntuable': 'on',
                    'unidad': 'otra', 'ponderador': '20',
                })
                self.assertEqual(respuesta.status_code, 302)
                self.item.refresh_from_db()
                self.assertEqual(self.item.nombre, 'Seguimiento actualizado')
                self.assertEqual(self.item.unidad, 'cantidad')
                self.assertEqual(self.item.ponderador, 40)

    def test_alta_item_aplica_cinco_por_ciento_y_respeta_tope(self):
        for ruta in ('item_create', 'items_create'):
            with self.subTest(ruta=ruta):
                cargo = Cargo.objects.create(nombre=f'Cargo {ruta}')
                Item.objects.create(nombre='Existente', cargo=cargo, ponderador=95)
                url = reverse(ruta)
                pagina = self.client.get(url)
                self.assertNotContains(pagina, 'name="unidad"')
                self.assertNotContains(pagina, 'name="ponderador"')
                datos = {'cargo': cargo.pk, 'nombre': 'Nuevo', 'tipo_resultado': 'EJE',
                         'vigente': 'on', 'puntuable': 'on', 'unidad': 'otra', 'ponderador': '1'}
                self.assertEqual(self.client.post(url, datos).status_code, 302)
                nuevo = Item.objects.get(cargo=cargo, nombre='Nuevo')
                self.assertEqual(nuevo.ponderador, 5)
                self.assertEqual(nuevo.unidad, 'gestión')
                self.assertEqual(cargo.total_ponderadores, 100)

                respuesta = self.client.post(url, {**datos, 'nombre': 'Excedente'})
                self.assertContains(respuesta, 'El máximo es 100%')
                self.assertFalse(Item.objects.filter(cargo=cargo, nombre='Excedente').exists())

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
