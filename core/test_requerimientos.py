"""Regresión del incremento territorial y reglas de puntuación RN-01 a RN-13."""
from datetime import date, datetime, time, timedelta
from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from .models import (Actividad, Ausencia, Cargo, Compromiso, Delegacion, Evidencia, Funcionario,
                     Hito, Item, Membresia, MetaFuncionario, Organizacion, Periodo,
                     ReclamoFelicitacion, Rol, Vecino, AtencionCiudadana, TipoAtencion, SubAtencion)
from .calendario import dias_habiles
from .indicadores import tablero


class RequerimientosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.delegacion = Delegacion.objects.create(nombre='Centro', sector='Centro histórico')
        cls.otra_delegacion = Delegacion.objects.create(nombre='Rural')
        cls.cargo = Cargo.objects.create(nombre='Gestor social')
        cls.item = Item.objects.create(cargo=cls.cargo, nombre='Taller realizado', ponderador=100)
        roles = {codigo: Rol.objects.create(codigo=codigo) for codigo, _ in Rol.OPCIONES}
        cls.func = Funcionario.objects.create_user('func', rol=roles[Rol.FUNCIONARIO], cargo=cls.cargo, delegacion=cls.delegacion)
        cls.otro = Funcionario.objects.create_user('otro', rol=roles[Rol.FUNCIONARIO], cargo=cls.cargo, delegacion=cls.otra_delegacion)
        cls.delegado = Funcionario.objects.create_user('delegado', rol=roles[Rol.DELEGADO], cargo=cls.cargo, delegacion=cls.delegacion)
        cls.coord = Funcionario.objects.create_user('coord', rol=roles[Rol.COORDINADOR])
        cls.admin = Funcionario.objects.create_user('admin', rol=roles[Rol.ADMINISTRADOR])
        cls.periodo = Periodo.objects.create(nombre='Mayo', fecha_inicio=date(2026, 5, 4), fecha_termino=date(2026, 5, 15))
        cls.meta = MetaFuncionario.objects.create(funcionario=cls.func, item=cls.item, periodo=cls.periodo,
                                                 valor_objetivo=10, definida_por=cls.coord)
        cls.vecino = Vecino.objects.create(nombre='Vecina de prueba', telefono='912345678', territorio='Centro', delegacion=cls.delegacion)
        cls.organizacion = Organizacion.objects.create(nombre='Junta Centro', tipo='JV', domicilio_legal='Calle 123',
            territorio='Centro', delegacion=cls.delegacion, fecha_constitucion=date(2000, 1, 1),
            fecha_inscripcion=date(2000, 2, 1), registro_personalidad='PJ-1', numero_registro='REG-1')
        cls.hito = Hito.objects.create(nombre='Festival', descripcion='Festival del barrio', fecha_inicio=date(2026, 5, 15),
            delegacion=cls.delegacion, territorio='Centro', creado_por=cls.delegado)
        cls.hito.responsables.add(cls.func)

    def setUp(self):
        reloj = patch('django.utils.timezone.localdate', return_value=date(2026, 5, 11))
        reloj.start()
        self.addCleanup(reloj.stop)
        self.client.force_login(self.func)

    def actividad(self, aprobada=False, **datos):
        valores = dict(funcionario=self.func, item=self.item, fecha=date(2026, 5, 11),
                       solicitud='Solicitud de taller vecinal', accion='Taller ejecutado en el barrio',
                       contacto_nombre='Vecina de prueba', contacto_telefono='912345678')
        valores.update(datos)
        a = Actividad.objects.create(**valores)
        if aprobada:
            Evidencia.objects.create(actividad=a, archivo='evidencias/prueba.jpg', estado=Evidencia.APROBADA)
        return a

    def datos_actividad(self, **datos):
        valores = dict(fecha='2026-05-11', item=self.item.pk, solicitud='Solicitud de taller vecinal',
                       accion='Taller ejecutado en el barrio', clasificacion='EJE', origen='EXT',
                       contacto_nombre='Vecina de prueba', contacto_telefono='912345678')
        valores.update(datos)
        return valores

    def felicitacion(self, **datos):
        self.item.tipo_resultado = 'FEL'
        self.item.save(update_fields=['tipo_resultado'])
        valores = dict(tipo='FEL', canal='MAIL', delegacion=self.delegacion, funcionario=self.func,
                       vecino='Vecina de prueba', telefono='912345678', descripcion='Felicitaciones por la gestión',
                       proviene_de_vecino=True, dirigida_a='DEL', respaldo='felicitaciones/carta.pdf',
                       actividad=self.actividad(clasificacion='FEL'))
        valores.update(datos)
        return ReclamoFelicitacion.objects.create(**valores)

    def test_ejecucion_con_datos_y_evidencia_cuenta_una_vez(self):
        a = self.actividad(aprobada=True)
        Evidencia.objects.create(actividad=a, archivo='evidencias/segunda.jpg', estado=Evidencia.APROBADA)
        self.assertEqual(self.meta.avance, 1)

    def test_contacto_incompleto_se_conserva_sin_puntaje(self):
        for campo in ('contacto_nombre', 'contacto_telefono'):
            with self.subTest(campo=campo):
                a = self.actividad(aprobada=True, **{campo: '  '})
                self.assertFalse(a.genera_puntaje)
        self.assertEqual(Actividad.objects.count(), 2)
        self.assertEqual(self.meta.avance, 0)

    def test_coordinacion_y_otra_gestion_no_puntuan(self):
        for clasificacion in ('COO', 'OTR'):
            self.actividad(aprobada=True, clasificacion=clasificacion)
        self.assertEqual(self.meta.avance, 0)

    def test_delegado_beneficiario_fuerza_otra_gestion(self):
        a = self.actividad(aprobada=True, beneficiario_funcionario=self.delegado)
        self.assertEqual(a.clasificacion, 'OTR')
        self.assertFalse(a.genera_puntaje)

    def test_catalogo_no_puntuable_no_genera_resultado(self):
        self.item.puntuable = False
        self.item.save()
        self.assertFalse(self.actividad(aprobada=True).genera_puntaje)

    def test_octava_actividad_rechazada_desde_modelo_y_formulario(self):
        for _ in range(7):
            self.actividad()
        with self.assertRaisesMessage(ValidationError, 'siete'):
            self.actividad()
        response = self.client.post(reverse('actividad_create'), self.datos_actividad())
        self.assertContains(response, 'siete actividades')
        self.assertEqual(Actividad.objects.count(), 7)

    def test_no_puntuables_no_consumen_cupo_y_otro_dia_tiene_cupo(self):
        for _ in range(7):
            self.actividad()
        self.actividad(clasificacion='COO')
        self.actividad(contacto_nombre='')
        self.actividad(fecha=date(2026, 5, 8))
        self.assertEqual(Actividad.objects.count(), 10)

    def test_editar_septima_no_se_cuenta_a_si_misma(self):
        actividades = [self.actividad() for _ in range(7)]
        a = actividades[-1]
        a.accion = 'Taller finalizado correctamente'
        a.save()

    def test_completar_datos_no_permite_eludir_limite(self):
        a = self.actividad(contacto_telefono='')
        for _ in range(7):
            self.actividad()
        a.contacto_telefono = '999999999'
        with self.assertRaisesMessage(ValidationError, 'siete'):
            a.save()

    def test_lunes_siguiente_abierto_y_martes_cerrado(self):
        self.actividad(fecha=date(2026, 5, 4))
        self.actividad(fecha=date(2026, 5, 8))
        with patch('django.utils.timezone.localdate', return_value=date(2026, 5, 12)):
            with self.assertRaisesMessage(ValidationError, 'cerrada'):
                self.actividad(fecha=date(2026, 5, 8))

    def test_no_se_puede_mover_actividad_cerrada_a_otra_semana(self):
        a = self.actividad(fecha=date(2026, 5, 8))
        with patch('django.utils.timezone.localdate', return_value=date(2026, 5, 12)):
            a.fecha = date(2026, 5, 12)
            with self.assertRaisesMessage(ValidationError, 'cerrada'):
                a.save()
            response = self.client.post(reverse('actividad_delete', args=[a.pk]))
            self.assertEqual(response.status_code, 302)
            self.assertTrue(Actividad.objects.filter(pk=a.pk).exists())

    def test_tope_120_conserva_ejecuciones_adicionales(self):
        self.meta.valor_objetivo = 2
        self.meta.save()
        for _ in range(4):
            self.actividad(aprobada=True)
        self.assertEqual(self.meta.avance, 3)
        self.assertEqual(Actividad.objects.count(), 4)
        self.assertEqual(self.meta.cumplimiento, 120)
        self.assertEqual(self.meta.resultado_ponderado, 120)

    def test_editar_ejecucion_invalida_evidencia_anterior(self):
        a = self.actividad(aprobada=True)
        a.accion = 'Otra ejecución diferente de la original'
        a.save()
        self.assertFalse(a.genera_puntaje)
        self.assertEqual(a.evidencias.get().estado, Evidencia.PENDIENTE)

    def test_edicion_por_coordinacion_conserva_autor(self):
        a = self.actividad()
        self.client.force_login(self.coord)
        response = self.client.post(reverse('actividad_update', args=[a.pk]), self.datos_actividad())
        self.assertEqual(response.status_code, 302)
        a.refresh_from_db()
        self.assertEqual(a.funcionario, self.func)

    def test_vecino_aporta_contacto(self):
        a = self.actividad(vecino=self.vecino, contacto_nombre='', contacto_telefono='')
        self.assertEqual(a.contacto_nombre, self.vecino.nombre)
        self.assertEqual(a.contacto_telefono, self.vecino.telefono)

    def test_membresia_modela_dirigente_en_relacion(self):
        Membresia.objects.create(vecino=self.vecino, organizacion=self.organizacion, rol='DIR', cargo='Presidenta')
        self.assertTrue(self.vecino.pertenece_junta)
        self.assertEqual(self.vecino.membresias.get().rol, 'DIR')

    def test_membresia_rechaza_otra_delegacion(self):
        self.organizacion.delegacion = self.otra_delegacion
        self.organizacion.save()
        with self.assertRaises(ValidationError):
            Membresia(vecino=self.vecino, organizacion=self.organizacion).full_clean()

    def test_crud_vecino_y_desactivacion_preserva_relacion(self):
        datos = dict(nombre='Nuevo vecino', telefono='987654321', territorio='Norte', delegacion=self.delegacion.pk, activo=True)
        response = self.client.post(reverse('vecino_create'), datos)
        self.assertEqual(response.status_code, 302)
        nuevo = Vecino.objects.get(nombre='Nuevo vecino')
        datos['telefono'] = '912312312'
        self.client.post(reverse('vecino_update', args=[nuevo.pk]), datos)
        nuevo.refresh_from_db()
        self.assertEqual(nuevo.telefono, '912312312')
        self.assertEqual(self.client.get(reverse('vecino_disable', args=[nuevo.pk])).status_code, 405)
        self.client.post(reverse('vecino_disable', args=[nuevo.pk]))
        nuevo.refresh_from_db()
        self.assertFalse(nuevo.activo)

    def test_acceso_a_vecino_ajeno_denegado(self):
        self.client.force_login(self.otro)
        for sufijo in ('detalle', 'update'):
            self.assertEqual(self.client.get(reverse('vecino_' + sufijo, args=[self.vecino.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('vecino_disable', args=[self.vecino.pk])).status_code, 404)

    def test_hitos_solo_delegado_o_administrador(self):
        for usuario, esperado in ((self.func, 403), (self.coord, 403), (self.delegado, 200), (self.admin, 200)):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(reverse('hito_create')).status_code, esperado)

    def test_hito_recurrente_requiere_periodicidad(self):
        self.hito.recurrente = True
        with self.assertRaises(ValidationError):
            self.hito.full_clean()

    def test_ejecucion_de_tarea_hito_es_interna(self):
        tarea = Compromiso.objects.create(hito=self.hito, responsable=self.func, delegacion=self.delegacion,
            descripcion='Preparar y ejecutar festival', fecha_comprometida=date(2026, 5, 15))
        a = self.actividad(tarea_hito=tarea, origen='EXT')
        self.assertEqual(a.origen, 'INT')
        self.assertEqual(a.hito, self.hito)
        with self.assertRaises(ValidationError):
            self.actividad(hito=self.hito, funcionario=self.otro)

    def test_hito_no_acepta_responsables_ajenos(self):
        self.client.force_login(self.delegado)
        response = self.client.post(reverse('hito_create'), dict(nombre='Evento ajeno', descripcion='Festival comunal',
            fecha_inicio='2026-05-15', territorio='Centro', delegacion=self.delegacion.pk,
            estado='PLA', responsables=[self.otro.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Hito.objects.filter(nombre='Evento ajeno').exists())

    def test_felicitacion_pendiente_y_mensaje_personal_no_puntuan(self):
        f = self.felicitacion(dirigida_a='PERS')
        self.assertFalse(f.actividad.genera_puntaje)
        with self.assertRaises(ValidationError):
            f.validar(self.delegado)

    def test_felicitacion_validada_cuenta_una_vez(self):
        f = self.felicitacion()
        self.assertEqual(self.meta.avance, 0)
        f.validar(self.delegado)
        Evidencia.objects.create(actividad=f.actividad, archivo='evidencias/x.jpg', estado=Evidencia.APROBADA)
        self.assertEqual(self.meta.avance, 1)

    def test_felicitacion_sin_respaldo_o_sin_vecino_no_se_valida(self):
        for datos in ({'respaldo': ''}, {'proviene_de_vecino': False}, {'telefono': ''}, {'vecino': ''}):
            with self.subTest(datos=datos):
                f = self.felicitacion(**datos)
                with self.assertRaises(ValidationError):
                    f.validar(self.delegado)

    def test_solo_delegado_valida_y_post_no_admite_suplantacion(self):
        f = self.felicitacion()
        for usuario in (self.func, self.coord, self.admin):
            self.client.force_login(usuario)
            self.assertEqual(self.client.post(reverse('felicitacion_validar', args=[f.pk])).status_code, 403)
        self.client.force_login(self.delegado)
        self.assertEqual(self.client.post(reverse('felicitacion_validar', args=[f.pk])).status_code, 302)
        f.refresh_from_db()
        self.assertEqual(f.validada_por, self.delegado)

    def test_editar_felicitacion_revoca_validacion(self):
        f = self.felicitacion()
        f.validar(self.delegado)
        f.descripcion = 'Se cambia el contenido de la felicitación'
        f.save()
        self.assertIsNone(f.validada_por)
        self.assertEqual(self.meta.avance, 0)

    def test_ausencia_proporcional_sin_duplicar_superposiciones(self):
        for inicio, fin in ((date(2026, 5, 4), date(2026, 5, 6)), (date(2026, 5, 6), date(2026, 5, 8))):
            Ausencia.objects.create(funcionario=self.func, tipo='VAC', fecha_inicio=inicio, fecha_termino=fin,
                                    motivo='Vacaciones autorizadas', registrada_por=self.delegado)
        self.assertEqual(self.meta.meta_ajustada, 5)
        self.assertEqual(self.meta.avance_esperado, 20)
        self.actividad(aprobada=True)
        self.assertEqual(self.meta.semaforo, 'verde')

    def test_feriados_y_fines_de_semana_no_son_laborables(self):
        self.assertEqual(dias_habiles(date(2026, 4, 30), date(2026, 5, 4)), {date(2026, 4, 30), date(2026, 5, 4)})
        self.assertNotIn(date(2026, 9, 18), dias_habiles(date(2026, 9, 14), date(2026, 9, 20)))

    def test_ausencia_de_todo_periodo_no_divide_por_cero(self):
        Ausencia.objects.create(funcionario=self.func, tipo='LIC', fecha_inicio=self.periodo.fecha_inicio,
            fecha_termino=self.periodo.fecha_termino, motivo='Licencia autorizada', registrada_por=self.delegado)
        self.assertEqual(self.meta.meta_ajustada, 0)
        self.assertEqual(self.meta.semaforo, 'sin_meta')
        self.assertEqual(self.meta.cumplimiento, 0)

    def test_ausencias_solo_delegado_de_su_delegacion(self):
        self.assertEqual(self.client.get(reverse('ausencia_create')).status_code, 403)
        self.client.force_login(self.delegado)
        datos = dict(funcionario=self.func.pk, tipo='ADM', fecha_inicio='2026-05-05', fecha_termino='2026-05-05', motivo='Permiso autorizado', activa=True)
        self.assertEqual(self.client.post(reverse('ausencia_create'), datos).status_code, 302)
        datos['funcionario'] = self.otro.pk
        self.assertEqual(self.client.post(reverse('ausencia_create'), datos).status_code, 200)
        self.assertEqual(Ausencia.objects.count(), 1)

    def test_tablero_no_diluye_resultados_con_personas_sin_metas(self):
        self.actividad(aprobada=True)
        datos = tablero(self.periodo, Delegacion.objects.filter(pk=self.delegacion.pk))
        self.assertEqual(datos['delegaciones'][0]['evaluados'], 1)
        self.assertEqual(datos['delegaciones'][0]['cumplimiento'], 10)
        self.assertEqual(datos['delegaciones'][0]['sin_meta'], 1)
        self.assertTrue(datos['equipos'])
        self.assertTrue(datos['territorios'])

    def test_paginas_nuevas_renderizan_y_tablero_limita_delegacion(self):
        self.client.force_login(self.delegado)
        for clave, obj in (('vecino', self.vecino), ('organizacion', self.organizacion), ('hito', self.hito)):
            for sufijo in ('list', 'create'):
                with self.subTest(ruta=clave + '_' + sufijo):
                    self.assertEqual(self.client.get(reverse(clave + '_' + sufijo)).status_code, 200)
            for sufijo in ('detalle', 'update'):
                with self.subTest(ruta=clave + '_' + sufijo):
                    self.assertEqual(self.client.get(reverse(clave + '_' + sufijo, args=[obj.pk])).status_code, 200)
        for ruta in ('membresia_list', 'membresia_create', 'ausencia_list', 'ausencia_create', 'indicadores'):
            self.assertEqual(self.client.get(reverse(ruta)).status_code, 200)
        response = self.client.get(reverse('indicadores'))
        self.assertNotContains(response, self.otra_delegacion.nombre)

    def test_atencion_sin_telefono_no_puntua_mediante_ejecucion(self):
        tipo = TipoAtencion.objects.create(codigo='SOC', nombre='Social')
        sub = SubAtencion.objects.create(codigo='TAL', nombre='Taller', tipo=tipo)
        solicitud = AtencionCiudadana.objects.create(solicitante='Vecina', telefono='', tipo=tipo, subatencion=sub,
            descripcion='Solicitud de un taller', responsable=self.func, delegacion=self.delegacion)
        a = self.actividad(atencion=solicitud, aprobada=True)
        self.assertFalse(a.genera_puntaje)

    def test_edicion_actividad_ajena_y_detalle_denegados(self):
        a = self.actividad()
        self.client.force_login(self.otro)
        for sufijo in ('update', 'detalle'):
            self.assertEqual(self.client.get(reverse('actividad_' + sufijo, args=[a.pk])).status_code, 404)

    def test_alcanzar_tope_permite_mas_de_siete_registros_sin_puntaje(self):
        self.meta.valor_objetivo = 1
        self.meta.save()
        self.actividad(aprobada=True)
        self.actividad(aprobada=True)
        for _ in range(8):
            a = self.actividad(aprobada=True)
            self.assertTrue(a.sin_puntaje_por_tope)
        self.assertEqual(Actividad.objects.count(), 10)
        self.assertEqual(self.meta.cumplimiento, 120)
        self.assertEqual(self.meta.avance, 2)

    def test_felicitacion_exige_item_de_felicitaciones(self):
        a = self.actividad(clasificacion='FEL', aprobada=True)
        self.assertFalse(a.es_candidata)
        self.assertFalse(a.genera_puntaje)

    def test_post_hito_crea_responsables_y_tarea(self):
        self.client.force_login(self.delegado)
        response = self.client.post(reverse('hito_create'), dict(nombre='Navidad territorial', descripcion='Entrega de regalos',
            fecha_inicio='2026-12-20', territorio='Centro', delegacion=self.delegacion.pk, recursos='Juguetes y transporte',
            estado='PLA', responsables=[self.func.pk], recurrente=True, periodicidad='Anual'))
        self.assertEqual(response.status_code, 302)
        hito = Hito.objects.get(nombre='Navidad territorial')
        self.assertEqual(hito.creado_por, self.delegado)
        self.assertEqual(list(hito.responsables.all()), [self.func])
        response = self.client.post(reverse('compromiso_create'), dict(hito=hito.pk, delegacion=self.delegacion.pk,
            descripcion='Preparar listado y ejecutar entrega', responsable=self.func.pk, fecha_comprometida='2026-12-20', estado='ING'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(hito.tareas.count(), 1)

    def test_crud_organizacion_y_membresia(self):
        datos = dict(nombre='Club vecinal', tipo='OC', domicilio_legal='Calle Norte 123', territorio='Centro',
            delegacion=self.delegacion.pk, fecha_constitucion='2020-01-01', fecha_inscripcion='2020-02-01',
            registro_personalidad='PJ-Club', numero_registro='REG-Club', activa=True)
        self.assertEqual(self.client.post(reverse('organizacion_create'), datos).status_code, 302)
        org = Organizacion.objects.get(nombre='Club vecinal')
        self.assertEqual(self.client.post(reverse('membresia_create'), dict(vecino=self.vecino.pk,
            organizacion=org.pk, rol='DIR', cargo='Secretaria', activa=True)).status_code, 302)
        membresia = Membresia.objects.get(organizacion=org)
        self.assertEqual(self.client.get(reverse('membresia_detalle', args=[membresia.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('membresia_update', args=[membresia.pk])).status_code, 200)
        self.client.post(reverse('organizacion_disable', args=[org.pk]))
        self.assertTrue(Membresia.objects.filter(pk=membresia.pk).exists())

    def test_ausencia_cancelada_restablece_meta(self):
        ausencia = Ausencia.objects.create(funcionario=self.func, tipo='ADM', fecha_inicio=date(2026, 5, 4),
            fecha_termino=date(2026, 5, 4), motivo='Permiso autorizado', registrada_por=self.delegado)
        self.assertEqual(self.meta.meta_ajustada, 9)
        self.client.force_login(self.delegado)
        self.assertEqual(self.client.get(reverse('ausencia_detalle', args=[ausencia.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('ausencia_update', args=[ausencia.pk])).status_code, 200)
        self.client.post(reverse('ausencia_disable', args=[ausencia.pk]))
        self.assertEqual(self.meta.meta_ajustada, 10)

    def test_ausencia_en_feriado_no_reduce_meta(self):
        periodo = Periodo.objects.create(nombre='Feriado del trabajo', fecha_inicio=date(2026, 4, 30), fecha_termino=date(2026, 5, 4))
        meta = MetaFuncionario.objects.create(funcionario=self.func, item=self.item, periodo=periodo, valor_objetivo=10, definida_por=self.coord)
        Ausencia.objects.create(funcionario=self.func, tipo='LIB', fecha_inicio=date(2026, 5, 1), fecha_termino=date(2026, 5, 3),
            motivo='Permiso sin días laborables', registrada_por=self.delegado)
        self.assertEqual(meta.meta_ajustada, 10)

    def test_editar_actividad_revoca_felicitacion(self):
        f = self.felicitacion()
        f.validar(self.delegado)
        a = f.actividad
        a.accion = 'Descripción de ejecución modificada'
        a.save()
        f.refresh_from_db()
        self.assertIsNone(f.validada_por)

    def test_validar_felicitacion_otra_delegacion_no_permitido(self):
        f = self.felicitacion()
        self.delegado.delegacion = self.otra_delegacion
        self.delegado.save()
        self.client.force_login(self.delegado)
        self.assertEqual(self.client.post(reverse('felicitacion_validar', args=[f.pk])).status_code, 404)

    def test_desactivar_vecino_no_borra_actividad_historica(self):
        a = self.actividad(vecino=self.vecino)
        self.client.post(reverse('vecino_disable', args=[self.vecino.pk]))
        a.refresh_from_db()
        self.assertEqual(a.vecino_id, self.vecino.pk)
        self.assertEqual(a.contacto_nombre, 'Vecina de prueba')

    def test_anonimo_no_accede_a_nuevos_modulos(self):
        self.client.logout()
        for ruta in ('vecino_list', 'organizacion_list', 'hito_list', 'ausencia_list'):
            self.assertEqual(self.client.get(reverse(ruta)).status_code, 302)

    def test_completar_solicitud_no_elude_cupo_y_revoca_evidencia(self):
        tipo = TipoAtencion.objects.create(codigo='SOC', nombre='Social')
        sub = SubAtencion.objects.create(codigo='TAL', nombre='Taller', tipo=tipo)
        solicitud = AtencionCiudadana.objects.create(solicitante='Vecina', telefono='', tipo=tipo, subatencion=sub,
            descripcion='Solicitud de un taller', responsable=self.func, delegacion=self.delegacion)
        AtencionCiudadana.objects.filter(pk=solicitud.pk).update(fecha_registro=timezone.make_aware(datetime.combine(date(2026, 5, 11), time(10))))
        a = self.actividad(atencion=solicitud, aprobada=True)
        for _ in range(7):
            self.actividad()
        datos = dict(solicitante='Vecina', telefono='912345678', tipo=tipo.pk, subatencion=sub.pk, descripcion='Solicitud de un taller')
        response = self.client.post(reverse('atencion_update', args=[solicitud.pk]), datos)
        self.assertContains(response, 'siete actividades')
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.telefono, '')
        Actividad.objects.exclude(pk=a.pk).first().delete()
        response = self.client.post(reverse('atencion_update', args=[solicitud.pk]), datos)
        self.assertEqual(response.status_code, 302)
        a.refresh_from_db()
        self.assertEqual(a.contacto_nombre, 'Vecina')
        self.assertEqual(a.evidencias.get().estado, Evidencia.PENDIENTE)

    def test_solicitud_cerrada_no_se_modifica(self):
        tipo = TipoAtencion.objects.create(codigo='SOC', nombre='Social')
        sub = SubAtencion.objects.create(codigo='TAL', nombre='Taller', tipo=tipo)
        solicitud = AtencionCiudadana.objects.create(solicitante='Vecina', tipo=tipo, subatencion=sub,
            descripcion='Solicitud de un taller', responsable=self.func, delegacion=self.delegacion)
        AtencionCiudadana.objects.filter(pk=solicitud.pk).update(fecha_registro=timezone.make_aware(datetime.combine(date(2026, 5, 1), time(10))))
        response = self.client.post(reverse('atencion_update', args=[solicitud.pk]), dict(solicitante='Vecina',
            telefono='912345678', tipo=tipo.pk, subatencion=sub.pk, descripcion='Solicitud de un taller'))
        self.assertContains(response, 'cerrada')
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.telefono, '')
