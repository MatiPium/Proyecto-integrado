from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Actividad, Auditoria, Cargo, Carta, Compromiso, Delegacion, Funcionario,
    Item, MetaFuncionario, Periodo, RevisionActividad, Rol, Territorio,
)


class RequerimientosComplementariosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.delegacion = Delegacion.objects.create(nombre='Centro complementarios')
        cls.cargo = Cargo.objects.create(nombre='Gestor complementarios')
        cls.rol_coord = Rol.objects.create(codigo=Rol.COORDINADOR, descripcion='Coordinación')
        cls.rol_verificador = Rol.objects.create(codigo=Rol.VERIFICADOR, descripcion='Verificador')
        cls.coord = Funcionario.objects.create_user('coord_complementarios', rol=cls.rol_coord)
        cls.funcionario = Funcionario.objects.create_user(
            'func_complementarios', delegacion=cls.delegacion, cargo=cls.cargo,
        )
        cls.verificador = Funcionario.objects.create_user(
            'verificador_complementarios', delegacion=cls.delegacion, rol=cls.rol_verificador,
        )
        cls.item = Item.objects.create(
            nombre='Visitas complementarias', cargo=cls.cargo, ponderador=35,
            tipo_resultado=Actividad.EJECUCION,
        )
        cls.periodo = Periodo.objects.create(
            nombre='T4 complementarios', fecha_inicio=date(2026, 10, 1),
            fecha_termino=date(2026, 12, 31),
        )
        cls.meta = MetaFuncionario.objects.create(
            funcionario=cls.funcionario, item=cls.item, periodo=cls.periodo,
            valor_objetivo=10, ponderacion=35, definida_por=cls.coord,
        )

    def setUp(self):
        self.client.force_login(self.coord)

    def test_territorio_genera_codigo_y_respeta_delegacion(self):
        territorio = Territorio.objects.create(nombre='Sector Norte', delegacion=self.delegacion)
        self.assertTrue(territorio.codigo.startswith('TER'))
        self.assertIn('Sector Norte', str(territorio))

    def test_carta_tiene_tubo_documentado_y_trazable(self):
        datos = {
            'fecha': timezone.localdate(), 'remitente': 'Junta vecinal',
            'destinatario': 'Municipalidad', 'materia': 'Solicitud de luminarias',
            'responsable': self.funcionario.pk, 'delegacion': self.delegacion.pk,
            'estado': Carta.INGRESADA,
        }
        self.assertEqual(self.client.post(reverse('carta_create'), datos).status_code, 302)
        carta = Carta.objects.get()
        self.assertTrue(carta.numero.startswith('CAR'))
        self.assertEqual(carta.historial.count(), 1)
        datos['estado'] = Carta.DERIVADA
        respuesta = self.client.post(reverse('carta_update', args=[carta.pk]), datos)
        self.assertContains(respuesta, 'al menos 5 caracteres')
        datos['observacion_cambio'] = 'Derivación a operaciones municipales'
        self.assertEqual(self.client.post(reverse('carta_update', args=[carta.pk]), datos).status_code, 302)
        self.assertEqual(carta.historial.count(), 2)

    def test_verificador_decide_y_deja_auditoria(self):
        actividad = Actividad.objects.create(
            funcionario=self.funcionario, item=self.item, meta_asignada=self.meta,
            fecha=timezone.localdate(), solicitud='Solicitud ciudadana completa',
            accion='Visita territorial ejecutada', contacto_nombre='Vecina',
            contacto_telefono='912345678', estado_verificacion=Actividad.VER_PENDIENTE,
        )
        revision = RevisionActividad.objects.create(
            actividad=actividad, verificador=self.verificador,
            decision=Actividad.VER_PONDERA, observacion='Antecedentes completos y consistentes.',
        )
        actividad.refresh_from_db()
        self.assertEqual(actividad.estado_verificacion, Actividad.VER_PONDERA)
        self.assertTrue(actividad.genera_puntaje)
        self.assertTrue(Auditoria.objects.filter(entidad='actividad', registro_id=str(actividad.pk)).exists())
        self.assertEqual(revision.verificador, self.verificador)

    def test_cierre_congela_y_reapertura_habilita_recalculo(self):
        self.periodo.cerrar(self.coord)
        self.meta.refresh_from_db()
        self.periodo.refresh_from_db()
        self.assertFalse(self.periodo.abierto)
        self.assertIsNotNone(self.meta.resultado_congelado)
        with self.assertRaises(ValidationError):
            self.periodo.reabrir(self.coord, 'no')
        self.periodo.reabrir(self.coord, 'Corrección autorizada por coordinación')
        self.meta.refresh_from_db()
        self.periodo.refresh_from_db()
        self.assertTrue(self.periodo.abierto)
        self.assertIsNone(self.meta.resultado_congelado)
        self.assertIsNone(self.periodo.cerrado_por)

    def test_reasignacion_de_tubo_exige_motivo_y_guarda_historial(self):
        otro = Funcionario.objects.create_user(
            'otro_complementarios', delegacion=self.delegacion, cargo=self.cargo,
        )
        compromiso = Compromiso(
            delegacion=self.delegacion, responsable=self.funcionario,
            descripcion='Coordinar respuesta territorial', fecha_comprometida=timezone.localdate(),
        )
        compromiso.guardar_con_historial(self.coord)
        compromiso.responsable = otro
        with self.assertRaises(ValidationError):
            compromiso.guardar_con_historial(self.coord)
        compromiso.motivo_reasignacion = 'Cambio de cobertura territorial'
        compromiso.guardar_con_historial(self.coord)
        self.assertEqual(compromiso.historial_responsables.count(), 2)
