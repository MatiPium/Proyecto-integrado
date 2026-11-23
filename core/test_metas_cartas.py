from datetime import date

from django.test import TestCase
from django.urls import reverse

from .models import (
    Cargo, Delegacion, Funcionario, Item, MetaFuncionario, Periodo,
    ReclamoFelicitacion, Rol,
)


class MetasCartasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.delegacion = Delegacion.objects.create(nombre='Centro')
        cls.cargo = Cargo.objects.create(nombre='Gestión')
        rol = Rol.objects.create(codigo=Rol.COORDINADOR)
        cls.coord = Funcionario.objects.create_user('coord_metas', rol=rol)
        cls.func = Funcionario.objects.create_user(
            'func_metas', cargo=cls.cargo, delegacion=cls.delegacion,
        )
        cls.periodo = Periodo.objects.create(
            nombre='T1 2027', fecha_inicio=date(2027, 1, 1), fecha_termino=date(2027, 3, 31),
        )
        cls.item = Item.objects.create(nombre='Visitas', cargo=cls.cargo, ponderador=60)
        cls.otro = Item.objects.create(nombre='Gestiones', cargo=cls.cargo, ponderador=40)

    def setUp(self):
        self.client.force_login(self.coord)

    def datos_meta(self, **cambios):
        return dict(funcionario=self.func.pk, item=self.item.pk, periodo=self.periodo.pk,
                    valor_objetivo=10, **cambios)

    def test_limite_y_edicion_sin_duplicar_peso(self):
        url = reverse('meta_create')
        self.assertEqual(self.client.post(url, self.datos_meta()).status_code, 302)
        datos = self.datos_meta()
        datos['item'] = self.otro.pk
        self.assertEqual(self.client.post(url, datos).status_code, 302)
        meta = MetaFuncionario.objects.get(item=self.item)
        respuesta = self.client.post(reverse('meta_update', args=[meta.pk]), self.datos_meta())
        self.assertEqual(respuesta.status_code, 302)
        exceso = Item.objects.create(nombre='Histórico adicional', cargo=self.cargo, ponderador=5)
        datos['item'] = exceso.pk
        self.assertContains(self.client.post(url, datos), 'máximo por funcionario y trimestre')
        self.assertEqual(MetaFuncionario.objects.count(), 2)
        siguiente = Periodo.objects.create(
            nombre='T2 2027', fecha_inicio=date(2027, 4, 1), fecha_termino=date(2027, 6, 30),
        )
        datos['periodo'] = siguiente.pk
        self.assertEqual(self.client.post(url, datos).status_code, 302)

    def test_cantidad_y_trimestre(self):
        datos = self.datos_meta()
        for cantidad in ('', 0, -1, '1.5'):
            datos['valor_objetivo'] = cantidad
            self.assertEqual(self.client.post(reverse('meta_create'), datos).status_code, 200)
        self.assertFalse(MetaFuncionario.objects.exists())
        datos['valor_objetivo'] = 10
        self.periodo.abierto = False
        self.periodo.save()
        self.assertEqual(self.client.post(reverse('meta_create'), datos).status_code, 200)
        self.periodo.abierto = True
        self.periodo.fecha_termino = date(2027, 4, 1)
        self.periodo.save()
        self.assertContains(self.client.post(reverse('meta_create'), datos), 'trimestre calendario completo')
        self.assertFalse(MetaFuncionario.objects.exists())

    def test_periodos_calendario_y_anio_bisiesto(self):
        for inicio, fin in [(date(2028, 1, 1), date(2028, 3, 31)),
                            (date(2027, 10, 1), date(2027, 12, 31))]:
            periodo = Periodo(nombre=str(inicio), fecha_inicio=inicio, fecha_termino=fin)
            periodo.full_clean()
        respuesta = self.client.post(reverse('periodo_create'), {
            'nombre': 'Inválido', 'fecha_inicio': '2027-02-01', 'fecha_termino': '2027-04-30',
            'umbral_verde': 100, 'umbral_ambar': 60, 'abierto': 'on',
        })
        self.assertContains(respuesta, 'trimestre calendario completo')

    def test_carta_cambia_estado_con_historial_y_observacion(self):
        datos = {
            'tipo': 'FEL', 'canal': 'PRES', 'delegacion': self.delegacion.pk,
            'funcionario': self.func.pk, 'vecino': 'Vecino de prueba', 'telefono': '912345678',
            'descripcion': 'Felicitación por el trabajo realizado', 'estado': 'ING',
            'dirigida_a': 'DEL', 'proviene_de_vecino': 'on',
        }
        self.assertEqual(self.client.post(reverse('reclamo_create'), datos).status_code, 302)
        carta = ReclamoFelicitacion.objects.get()
        url = reverse('reclamo_update', args=[carta.pk])
        self.assertEqual(carta.historial.count(), 1)
        datos['estado'] = 'PRO'
        self.assertContains(self.client.post(url, datos), 'al menos 5 caracteres')
        carta.refresh_from_db()
        self.assertEqual(carta.estado, 'ING')
        datos['observacion_estado'] = 'Se revisa el documento recibido'
        for estado in ('PRO', 'CER'):
            datos['estado'] = estado
            self.assertEqual(self.client.post(url, datos).status_code, 302)
        carta.refresh_from_db()
        self.assertEqual(carta.estado, 'CER')
        self.assertEqual(carta.historial.count(), 3)
        self.assertIsNone(carta.validada_por_id)
        self.assertContains(self.client.get(url), 'Se revisa el documento recibido')
        otra = Delegacion.objects.create(nombre='Rural')
        externo = Funcionario.objects.create_user('externo', delegacion=otra)
        self.client.force_login(externo)
        self.assertEqual(self.client.post(url, datos).status_code, 404)
