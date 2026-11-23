"""
Modelos del Sistema de Gestión de Resultados (SGR)
Delegaciones Municipales de La Serena.

Cada modelo corresponde a una entidad del Modelo Entidad-Relación del informe.
Las validaciones de negocio van en el método clean(), así se aplican tanto en
los formularios del sitio como en el panel de administración de Django.
"""

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models, router, transaction
from datetime import timedelta
from calendar import monthrange
from django.utils import timezone


# ------------------------------------------------------------------ catálogos
class SecuenciaCatalogo(models.Model):
    prefijo = models.CharField(max_length=12, primary_key=True)
    ultimo = models.PositiveBigIntegerField(default=0)


class CatalogoConCodigo(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding or self.codigo:
            return super().save(*args, **kwargs)

        using = kwargs.get('using') or router.db_for_write(type(self), instance=self)
        secuencias = SecuenciaCatalogo.objects.using(using)
        secuencia = secuencias.filter(pk=self.prefijo_codigo)
        catalogo = type(self).objects.using(using)
        with transaction.atomic(using=using):
            # La primera operación es una escritura para serializar altas también en SQLite.
            if not secuencia.update(ultimo=models.F('ultimo')):
                secuencias.get_or_create(pk=self.prefijo_codigo)
            numero = secuencia.values_list('ultimo', flat=True).get() + 1
            codigo = f'{self.prefijo_codigo}{numero:02d}'
            # También respeta códigos incorporados por importación después de la migración.
            while catalogo.filter(codigo__iexact=codigo).exists():
                numero += 1
                codigo = f'{self.prefijo_codigo}{numero:02d}'
            secuencia.update(ultimo=numero)
            self.codigo = codigo
            try:
                return super().save(*args, **kwargs)
            except Exception:
                self.codigo = ''
                raise


class Delegacion(CatalogoConCodigo):
    """Las 6 delegaciones municipales de La Serena."""

    nombre = models.CharField("nombre", max_length=80, unique=True)
    sector = models.CharField("sector", max_length=120, blank=True)
    prefijo_codigo = 'D'
    codigo = models.CharField(max_length=20, blank=True, default="", editable=False)
    direccion = models.CharField(max_length=180, blank=True, default="")
    comuna = models.CharField(max_length=100, blank=True, default="La Serena")
    activa = models.BooleanField("activa", default=True)
    delegado = models.ForeignKey('Funcionario', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='delegaciones_dirigidas')

    class Meta:
        verbose_name = "delegación"
        verbose_name_plural = "delegaciones"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    def clean(self):
        if self.nombre:
            self.nombre = self.nombre.strip()
        if self.nombre and len(self.nombre) < 3:
            raise ValidationError({"nombre": "El nombre debe tener al menos 3 caracteres."})


class Territorio(CatalogoConCodigo):
    prefijo_codigo = 'TER'
    codigo = models.CharField(max_length=20, blank=True, default='', editable=False, unique=True)
    nombre = models.CharField(max_length=100)
    descripcion = models.CharField(max_length=250, blank=True)
    delegacion = models.ForeignKey(Delegacion, on_delete=models.PROTECT, related_name='territorios')
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ['delegacion', 'nombre']
        constraints = [models.UniqueConstraint(fields=['delegacion', 'nombre'], name='territorio_unico_delegacion')]

    def __str__(self):
        return f'{self.nombre} · {self.delegacion}'


class Rol(models.Model):
    """Perfil de acceso: define qué puede hacer cada funcionario."""

    ADMINISTRADOR = "ADMIN"
    COORDINADOR = "COORD"
    DELEGADO = "DELEG"
    FUNCIONARIO = "FUNC"
    VERIFICADOR = "VERIF"
    CONSULTA = "CONS"
    OPCIONES = [
        (ADMINISTRADOR, "Administrador"),
        (COORDINADOR, "Coordinador"),
        (DELEGADO, "Delegado / jefatura"),
        (FUNCIONARIO, "Funcionario"),
        (VERIFICADOR, "Verificador"),
        (CONSULTA, "Usuario de consulta"),
    ]

    codigo = models.CharField("código", max_length=5, choices=OPCIONES, unique=True)
    descripcion = models.CharField("descripción", max_length=200, blank=True)
    activo = models.BooleanField(default=True)
    permisos_descripcion = models.TextField(blank=True, help_text="Resumen informativo; autorización según perfil en servidor.")

    class Meta:
        verbose_name = "rol"
        verbose_name_plural = "roles"
        ordering = ["codigo"]

    def __str__(self):
        return self.get_codigo_display()


class Cargo(CatalogoConCodigo):
    """Función del funcionario: Gestor Social, Territorial OO.CC., etc."""

    nombre = models.CharField("nombre", max_length=100, unique=True)
    prefijo_codigo = 'CAR'
    codigo = models.CharField(max_length=20, blank=True, default='', editable=False, unique=True)
    descripcion = models.CharField("descripción", max_length=200, blank=True)
    vigente = models.BooleanField("vigente", default=True)

    class Meta:
        verbose_name = "cargo"
        verbose_name_plural = "cargos"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    @property
    def total_ponderadores(self):
        """Suma de los ponderadores de sus ítems vigentes (debe llegar a 100%)."""
        return sum(i.ponderador for i in self.items.filter(vigente=True))


class Item(CatalogoConCodigo):
    """Unidad medible de trabajo de un cargo, con su peso en el cumplimiento."""

    cargo = models.ForeignKey(Cargo, on_delete=models.PROTECT, related_name="items", verbose_name="cargo")
    nombre = models.CharField("nombre", max_length=120)
    unidad = models.CharField("unidad de medida", max_length=40, default="gestión")
    ponderador = models.DecimalField(
        "ponderador (%)", max_digits=5, decimal_places=2,
        validators=[MinValueValidator(0.01), MaxValueValidator(100)],
    )
    vigente = models.BooleanField("vigente", default=True)
    puntuable = models.BooleanField("acción válida para puntuación", default=True)
    tipo_resultado = models.CharField('resultado admitido', max_length=3, default='EJE',
        choices=[('EJE', 'Ejecución final'), ('FEL', 'Felicitación validada')])
    prefijo_codigo = 'I'
    codigo = models.CharField(max_length=20, blank=True, default="", editable=False)
    descripcion = models.CharField(max_length=250, blank=True, default="")
    tipo = models.CharField(max_length=20, default='CANTIDAD', choices=[
        ('CANTIDAD', 'Cantidad'), ('PORCENTAJE', 'Porcentaje'), ('HITO', 'Hito'),
    ])
    requiere_evidencia = models.BooleanField(default=True)

    class Meta:
        verbose_name = "ítem"
        verbose_name_plural = "ítems"
        ordering = ["cargo__nombre", "nombre"]
        constraints = [
            models.UniqueConstraint(fields=["cargo", "nombre"], name="item_unico_por_cargo"),
        ]

    def __str__(self):
        return f"{self.nombre} ({self.cargo})"

    def clean(self):
        """La suma de ponderadores vigentes de un cargo no puede pasar de 100%."""
        if not self.cargo_id or self.ponderador is None:
            return
        otros = Item.objects.filter(cargo=self.cargo, vigente=True).exclude(pk=self.pk)
        usado = sum(i.ponderador for i in otros)
        if usado + self.ponderador > 100:
            raise ValidationError(
                f"La suma de ponderadores del cargo llegaría a {usado + self.ponderador}%. "
                f"El máximo es 100% (disponible: {100 - usado}%)."
            )


class Periodo(CatalogoConCodigo):
    """Trimestre de medición, con los umbrales que definen el semáforo."""

    nombre = models.CharField("nombre", max_length=60, unique=True)
    prefijo_codigo = 'TRI'
    codigo = models.CharField(max_length=20, blank=True, default='', editable=False, unique=True)
    anio = models.PositiveSmallIntegerField(null=True, blank=True, editable=False)
    numero = models.PositiveSmallIntegerField(null=True, blank=True, editable=False)
    fecha_inicio = models.DateField("fecha de inicio")
    fecha_termino = models.DateField("fecha de término")
    umbral_verde = models.DecimalField("umbral verde (%)", max_digits=5, decimal_places=2, default=100)
    umbral_ambar = models.DecimalField("umbral ámbar (%)", max_digits=5, decimal_places=2, default=60)
    abierto = models.BooleanField("abierto", default=True)
    cerrado_en = models.DateTimeField(null=True, blank=True, editable=False)
    cerrado_por = models.ForeignKey('Funcionario', on_delete=models.PROTECT, null=True, blank=True,
                                    related_name='trimestres_cerrados', editable=False)

    class Meta:
        verbose_name = "período"
        verbose_name_plural = "períodos"
        ordering = ["-fecha_inicio"]

    def __str__(self):
        return self.nombre

    def clean(self):
        if self.fecha_inicio and self.fecha_termino and not self.es_trimestre_calendario:
            raise ValidationError('El período debe abarcar un trimestre calendario completo.')
        if self.fecha_inicio and self.fecha_termino and self.fecha_termino <= self.fecha_inicio:
            raise ValidationError({"fecha_termino": "La fecha de término debe ser posterior a la de inicio."})
        if self.umbral_verde is not None and self.umbral_ambar is not None:
            if self.umbral_ambar >= self.umbral_verde:
                raise ValidationError({"umbral_ambar": "El umbral ámbar debe ser menor que el verde."})

    def save(self, *args, **kwargs):
        if self.fecha_inicio:
            self.anio = self.fecha_inicio.year
            self.numero = (self.fecha_inicio.month - 1) // 3 + 1
        super().save(*args, **kwargs)

    def cerrar(self, usuario):
        with transaction.atomic():
            for meta in self.metas.select_related('item', 'funcionario'):
                meta.avance_congelado = meta.avance
                meta.cumplimiento_congelado = meta.cumplimiento
                meta.resultado_congelado = meta.resultado_ponderado
                meta.save(update_fields=['avance_congelado', 'cumplimiento_congelado', 'resultado_congelado'])
            self.abierto = False
            self.cerrado_en = timezone.now()
            self.cerrado_por = usuario
            self.save(update_fields=['abierto', 'cerrado_en', 'cerrado_por', 'anio', 'numero'])
            Auditoria.objects.create(funcionario=usuario, evento='CERRAR', entidad='trimestre',
                                     registro_id=str(self.pk), detalle=str(self))

    def reabrir(self, usuario, motivo):
        if len((motivo or '').strip()) < 5:
            raise ValidationError('Indica el motivo de reapertura.')
        with transaction.atomic():
            self.metas.update(avance_congelado=None, cumplimiento_congelado=None, resultado_congelado=None)
            self.abierto = True
            self.cerrado_en = None
            self.cerrado_por = None
            self.save(update_fields=['abierto', 'cerrado_en', 'cerrado_por'])
            Auditoria.objects.create(funcionario=usuario, evento='REABRIR', entidad='trimestre',
                                     registro_id=str(self.pk), detalle=motivo.strip())

    @property
    def es_trimestre_calendario(self):
        inicio, fin = self.fecha_inicio, self.fecha_termino
        return bool(inicio and fin and inicio.day == 1 and inicio.month in (1, 4, 7, 10)
                    and fin.year == inicio.year and fin.month == inicio.month + 2
                    and fin.day == monthrange(fin.year, fin.month)[1])

    @property
    def dias_totales(self):
        return (self.fecha_termino - self.fecha_inicio).days + 1

    @property
    def dias_transcurridos(self):
        hoy = timezone.localdate()
        if hoy < self.fecha_inicio:
            return 0
        return min((hoy - self.fecha_inicio).days + 1, self.dias_totales)

    @property
    def avance_esperado(self):
        """Porcentaje que se debería llevar al día de hoy."""
        if not self.dias_totales:
            return 0
        return round(self.dias_transcurridos / self.dias_totales * 100, 1)


# -------------------------------------------------------------------- usuario
class Funcionario(AbstractUser):
    """
    Usuario del sistema. Hereda de AbstractUser para reutilizar el login,
    el cifrado de contraseñas y los permisos de Django (RNF-04, RNF-05).
    """

    delegacion = models.ForeignKey(Delegacion, on_delete=models.PROTECT, null=True, blank=True,
                                   related_name="funcionarios", verbose_name="delegación")
    cargo = models.ForeignKey(Cargo, on_delete=models.PROTECT, null=True, blank=True,
                              related_name="funcionarios", verbose_name="cargo")
    rol = models.ForeignKey(Rol, on_delete=models.PROTECT, null=True, blank=True,
                            related_name="funcionarios", verbose_name="rol")
    telefono = models.CharField("teléfono", max_length=20, blank=True)
    rut = models.CharField(max_length=12, unique=True, null=True, blank=True)
    territorio = models.CharField('territorio de trabajo', max_length=100, blank=True)
    territorio_asignado = models.ForeignKey(Territorio, on_delete=models.SET_NULL, null=True, blank=True,
                                            related_name='funcionarios')
    delegaciones_autorizadas = models.ManyToManyField(Delegacion, blank=True, related_name="usuarios_autorizados")
    roles = models.ManyToManyField(Rol, blank=True, related_name='usuarios')
    debe_cambiar_clave = models.BooleanField(default=False)
    intentos_fallidos = models.PositiveSmallIntegerField(default=0)
    bloqueado_hasta = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "funcionario"
        verbose_name_plural = "funcionarios"
        ordering = ["first_name", "last_name"]

    def __str__(self):
        return self.get_full_name() or self.username

    def tiene_rol(self, *codigos):
        return bool((self.rol and self.rol.codigo in codigos) or self.roles.filter(codigo__in=codigos).exists())

    @property
    def es_coordinacion(self):
        return self.tiene_rol(Rol.COORDINADOR, Rol.ADMINISTRADOR)

    def clean(self):
        super().clean()
        if self.rut:
            self.rut = normalizar_rut(self.rut)
            if not rut_valido(self.rut):
                raise ValidationError({'rut': 'El RUT no es válido.'})
        if self.rol and self.rol.codigo in (Rol.FUNCIONARIO, Rol.DELEGADO, Rol.VERIFICADOR) and not self.delegacion_id:
            raise ValidationError({"delegacion": "Los perfiles operativos deben tener una delegación asignada."})


def normalizar_rut(valor):
    limpio = ''.join(c for c in (valor or '').upper() if c.isdigit() or c == 'K')
    return f'{limpio[:-1]}-{limpio[-1:]}' if len(limpio) > 1 else limpio


def rut_valido(valor):
    limpio = ''.join(c for c in (valor or '').upper() if c.isdigit() or c == 'K')
    if len(limpio) < 2 or not limpio[:-1].isdigit():
        return False
    suma, factor = 0, 2
    for digito in reversed(limpio[:-1]):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - suma % 11
    esperado = '0' if resto == 11 else 'K' if resto == 10 else str(resto)
    return limpio[-1] == esperado


# ------------------------------------------------------------------- medición
class MetaFuncionario(models.Model):
    """
    Objetivo por funcionario, ítem y período.
    Regla confirmada en la reunión: las metas las define la coordinación según
    el presupuesto; el funcionario no puede autoasignárselas (RF-14).
    """

    funcionario = models.ForeignKey(Funcionario, on_delete=models.CASCADE, related_name="metas",
                                    verbose_name="funcionario")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="metas", verbose_name="ítem")
    periodo = models.ForeignKey(Periodo, on_delete=models.PROTECT, related_name="metas", verbose_name="período")
    valor_objetivo = models.PositiveIntegerField("meta del período", validators=[MinValueValidator(1)])
    codigo = models.CharField(max_length=24, unique=True, blank=True, editable=False)
    ponderacion = models.DecimalField(max_digits=5, decimal_places=2,
                                      validators=[MinValueValidator(0.01), MaxValueValidator(100)], null=True)
    observacion = models.TextField(blank=True)
    activa = models.BooleanField(default=True)
    modificada_en = models.DateTimeField(auto_now=True, null=True)
    avance_congelado = models.PositiveIntegerField(null=True, blank=True, editable=False)
    cumplimiento_congelado = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, editable=False)
    resultado_congelado = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, editable=False)
    definida_por = models.ForeignKey(Funcionario, on_delete=models.PROTECT, related_name="metas_definidas",
                                     verbose_name="definida por")
    fecha_definicion = models.DateField("fecha de definición", auto_now_add=True)

    class Meta:
        verbose_name = "meta"
        verbose_name_plural = "metas"
        ordering = ["funcionario", "item"]
        constraints = [
            models.UniqueConstraint(fields=["funcionario", "item", "periodo"], name="meta_unica_por_periodo"),
        ]

    def __str__(self):
        return f"{self.funcionario} · {self.item} · {self.valor_objetivo}"

    def clean(self):
        if self.ponderacion is None and self.item_id:
            self.ponderacion = self.item.ponderador
        if self.definida_por_id and not self.definida_por.es_coordinacion:
            raise ValidationError({"definida_por": "Solo un usuario con rol Coordinador o Administrador "
                                                   "puede definir metas."})
        if self.funcionario_id and self.item_id and self.funcionario.cargo_id != self.item.cargo_id:
            raise ValidationError({"item": "El ítem no pertenece al cargo del funcionario."})
        if self.periodo_id and not self.periodo.abierto:
            raise ValidationError({"periodo": "No se pueden definir metas en un período cerrado."})
        if self.periodo_id and not self.periodo.es_trimestre_calendario:
            raise ValidationError({'periodo': 'Selecciona un trimestre calendario completo.'})
        if self.funcionario_id and self.item_id and self.periodo_id:
            otras = type(self).objects.filter(
                funcionario_id=self.funcionario_id,
                periodo__fecha_inicio=self.periodo.fecha_inicio,
                periodo__fecha_termino=self.periodo.fecha_termino,
            ).exclude(pk=self.pk)
            total = sum(otras.filter(activa=True).values_list('ponderacion', flat=True)) + (
                (self.ponderacion or 0) if self.activa else 0)
            if total > 100:
                raise ValidationError({'item': f'Las metas sumarían {total} %. El máximo por funcionario y trimestre es 100 %.'})
            if otras.filter(item_id=self.item_id).exists():
                raise ValidationError({'item': 'El ítem ya tiene una meta para este funcionario y trimestre.'})

    def guardar_validada(self):
        with transaction.atomic():
            creada = self.pk is None
            Funcionario.objects.select_for_update().get(pk=self.funcionario_id)
            self.full_clean()
            self.save()
            Auditoria.objects.create(funcionario=self.definida_por, evento='CREAR' if creada else 'EDITAR',
                                     entidad='meta asignada', registro_id=str(self.pk), detalle=str(self))

    def save(self, *args, **kwargs):
        if self.ponderacion is None and self.item_id:
            self.ponderacion = self.item.ponderador
        if not self.codigo and self.funcionario_id and self.periodo_id:
            with transaction.atomic():
                SecuenciaCatalogo.objects.get_or_create(prefijo='META')
                SecuenciaCatalogo.objects.filter(pk='META').update(ultimo=models.F('ultimo') + 1)
                numero = SecuenciaCatalogo.objects.values_list('ultimo', flat=True).get(pk='META')
                self.codigo = f'META{numero:05d}'
        super().save(*args, **kwargs)

    @property
    def avance(self):
        """Una ejecución válida cuenta una vez, aunque tenga varias evidencias."""
        if not self.periodo.abierto and self.avance_congelado is not None:
            return self.avance_congelado
        actividades = Actividad.objects.filter(
            funcionario=self.funcionario, item=self.item,
            fecha__range=(self.periodo.fecha_inicio, self.periodo.fecha_termino),
        ).filter(models.Q(meta_asignada=self) | models.Q(meta_asignada__isnull=True)).select_related(
            'item', 'beneficiario_funcionario', 'felicitacion').prefetch_related('evidencias')
        return sum(a.genera_puntaje for a in actividades)

    def dias_laborables(self, hasta=None):
        from .calendario import dias_habiles
        fin = min(hasta or self.periodo.fecha_termino, self.periodo.fecha_termino)
        inicio = self.periodo.fecha_inicio
        dias = dias_habiles(inicio, fin)
        ausencias = self.funcionario.ausencias.filter(
            activa=True, fecha_inicio__lte=fin, fecha_termino__gte=inicio)
        for ausencia in ausencias:
            desde, hasta_ausencia = max(inicio, ausencia.fecha_inicio), min(fin, ausencia.fecha_termino)
            dias.difference_update(desde + timedelta(days=n) for n in range((hasta_ausencia - desde).days + 1))
        return len(dias)

    @property
    def meta_ajustada(self):
        from .calendario import dias_habiles
        inicio, fin = self.periodo.fecha_inicio, self.periodo.fecha_termino
        base = len(dias_habiles(inicio, fin))
        return self.valor_objetivo * self.dias_laborables() / base if base else 0

    @property
    def avance_esperado(self):
        total = self.dias_laborables()
        return self.dias_laborables(timezone.localdate()) / total * 100 if total else 0

    @property
    def cumplimiento(self):
        if not self.periodo.abierto and self.cumplimiento_congelado is not None:
            return float(self.cumplimiento_congelado)
        if not self.meta_ajustada:
            return 0
        return round(min(self.avance / self.meta_ajustada * 100, 120), 1)

    @property
    def resultado_ponderado(self):
        if not self.periodo.abierto and self.resultado_congelado is not None:
            return float(self.resultado_congelado)
        return round(float(self.ponderacion or 0) * self.cumplimiento / 100, 1)

    @property
    def semaforo(self):
        """verde / ambar / rojo comparando con el avance esperado al día de hoy (RF-12)."""
        if not self.meta_ajustada:
            return 'sin_meta'
        esperado = self.avance_esperado
        if self.cumplimiento >= esperado:
            return "verde"
        if self.cumplimiento >= esperado * float(self.periodo.umbral_ambar) / 100:
            return "ambar"
        return "rojo"


# ------------------------------------------------------------------ operación
class Actividad(models.Model):
    """Registro de una gestión realizada por un funcionario (RF-01)."""

    funcionario = models.ForeignKey(Funcionario, on_delete=models.PROTECT, related_name="actividades",
                                    verbose_name="funcionario")
    codigo = models.CharField(max_length=24, unique=True, blank=True, editable=False)
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="actividades", verbose_name="ítem")
    meta_asignada = models.ForeignKey(MetaFuncionario, on_delete=models.PROTECT, null=True, blank=True,
                                      related_name='actividades', verbose_name='meta asignada')
    fecha = models.DateField("fecha de la actividad")
    tipo_atencion = models.CharField("tipo de atención", max_length=80, blank=True)
    solicitud = models.TextField("solicitud o problema atendido")
    accion = models.TextField("acción ejecutada")
    contacto_nombre = models.CharField("nombre del contacto", max_length=120, blank=True)
    contacto_telefono = models.CharField("teléfono del contacto", max_length=20, blank=True)
    ingresa_agenda = models.BooleanField("ingresar a la agenda colectiva", default=False)
    creada_en = models.DateTimeField("creada en", auto_now_add=True, null=True)
    modificada_en = models.DateTimeField(auto_now=True, null=True)
    territorio_asignado = models.ForeignKey(Territorio, on_delete=models.SET_NULL, null=True, blank=True)
    fecha_compromiso = models.DateField(null=True, blank=True)
    area_apoyo = models.CharField(max_length=120, blank=True)
    avance_tubo = models.TextField(blank=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True, editable=False)
    VER_PENDIENTE, VER_PONDERA, VER_NO_PONDERA = 'PEN', 'APP', 'APN'
    VER_ANTECEDENTES, VER_RECHAZADA, VER_ANULADA = 'ANT', 'REC', 'ANU'
    ESTADOS_VERIFICACION = [
        ('', 'Sin revisión (registro histórico)'), (VER_PENDIENTE, 'Pendiente'),
        (VER_PONDERA, 'Aprobada y pondera'), (VER_NO_PONDERA, 'Aprobada y no pondera'),
        (VER_ANTECEDENTES, 'Solicitud de antecedentes'), (VER_RECHAZADA, 'Rechazada'),
        (VER_ANULADA, 'Anulada'),
    ]
    estado_verificacion = models.CharField(max_length=3, choices=ESTADOS_VERIFICACION, blank=True, default='')
    sin_puntaje_por_tope = models.BooleanField(default=False, editable=False)
    EJECUCION, COORDINACION, OTRA, FELICITACION = 'EJE', 'COO', 'OTR', 'FEL'
    clasificacion = models.CharField(max_length=3, default=EJECUCION, choices=[
        (EJECUCION, 'Ejecución final'), (COORDINACION, 'Coordinación'),
        (OTRA, 'Otra gestión'), (FELICITACION, 'Felicitación')])
    origen = models.CharField(max_length=3, default='EXT', choices=[('EXT', 'Solicitud externa'), ('INT', 'Actividad interna')])
    vecino = models.ForeignKey('Vecino', on_delete=models.PROTECT, null=True, blank=True)
    beneficiario_funcionario = models.ForeignKey(Funcionario, on_delete=models.PROTECT, null=True,
        blank=True, related_name='actividades_como_beneficiario', verbose_name='beneficiario municipal')
    hito = models.ForeignKey('Hito', on_delete=models.PROTECT, null=True, blank=True, related_name='actividades')
    tarea_hito = models.OneToOneField('Compromiso', on_delete=models.PROTECT, null=True, blank=True,
        related_name='ejecucion', verbose_name='tarea del hito ejecutada')
    atencion = models.OneToOneField('AtencionCiudadana', on_delete=models.PROTECT, null=True, blank=True,
        related_name='ejecucion', verbose_name='solicitud ciudadana de origen')

    class Meta:
        verbose_name = "actividad"
        verbose_name_plural = "actividades"
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"{self.fecha} · {self.item} · {self.funcionario}"

    def clean(self):
        self.normalizar()
        self.validar_semana()
        if self.fecha and self.fecha > timezone.localdate():
            raise ValidationError({"fecha": "No se pueden registrar actividades con fecha futura."})
        if self.funcionario_id and self.item_id and self.funcionario.cargo_id != self.item.cargo_id:
            raise ValidationError({"item": "El ítem seleccionado no corresponde al cargo del funcionario."})
        if self.meta_asignada_id:
            if self.meta_asignada.funcionario_id != self.funcionario_id:
                raise ValidationError({'meta_asignada': 'La meta no pertenece al funcionario.'})
            if self.meta_asignada.item_id != self.item_id:
                raise ValidationError({'meta_asignada': 'La meta seleccionada no corresponde al ítem.'})
            if self.fecha and not (self.meta_asignada.periodo.fecha_inicio <= self.fecha <= self.meta_asignada.periodo.fecha_termino):
                raise ValidationError({'meta_asignada': 'La fecha de la actividad está fuera del trimestre de la meta.'})
        if self.ingresa_agenda and not self.fecha_compromiso:
            raise ValidationError({'fecha_compromiso': 'Indica la fecha de compromiso para ingresar al Tubo.'})
        if self.fecha_compromiso and self.fecha and self.fecha_compromiso < self.fecha:
            raise ValidationError({'fecha_compromiso': 'La fecha de compromiso no puede ser anterior a la actividad.'})
        if self.solicitud and len(self.solicitud.strip()) < 10:
            raise ValidationError({"solicitud": "Describe la solicitud con al menos 10 caracteres."})
        if self.accion and len(self.accion.strip()) < 10:
            raise ValidationError({"accion": "Indica la acción ejecutada con al menos 10 caracteres."})
        if self.vecino_id and self.funcionario_id and self.vecino.delegacion_id != self.funcionario.delegacion_id:
            raise ValidationError({'vecino': 'El vecino debe pertenecer a la delegación del funcionario.'})
        if self.hito_id and self.funcionario_id:
            if self.hito.delegacion_id != self.funcionario.delegacion_id or not self.hito.responsables.filter(pk=self.funcionario_id).exists():
                raise ValidationError({'hito': 'El funcionario debe ser responsable del hito en su delegación.'})
        if self.tarea_hito_id and (not self.tarea_hito.hito_id or self.tarea_hito.hito_id != self.hito_id
                                  or self.tarea_hito.responsable_id != self.funcionario_id):
            raise ValidationError({'tarea_hito': 'La tarea debe corresponder al hito y al funcionario responsable.'})
        if self.atencion_id and (self.atencion.delegacion_id != self.funcionario.delegacion_id
                                or self.atencion.responsable_id != self.funcionario_id):
            raise ValidationError({'atencion': 'La atención debe corresponder al funcionario y su delegación.'})
        if self.es_candidata and self.fecha and self.funcionario_id:
            otras = Actividad.objects.filter(funcionario_id=self.funcionario_id, fecha=self.fecha).exclude(pk=self.pk).select_related('item', 'beneficiario_funcionario')
            if sum(a.es_candidata for a in otras) >= 7:
                raise ValidationError('Máximo de siete actividades puntuables por funcionario y día. No se puede registrar otra actividad puntuable en esta fecha.')

    def normalizar(self):
        if self.atencion_id:
            self.contacto_nombre = self.contacto_nombre.strip() or self.atencion.solicitante
            self.contacto_telefono = self.contacto_telefono.strip() or self.atencion.telefono
        if self.tarea_hito_id:
            self.hito = self.tarea_hito.hito
        if self.hito_id:
            self.origen = 'INT'
        if self.beneficiario_funcionario_id and self.beneficiario_funcionario.tiene_rol(Rol.DELEGADO):
            self.clasificacion = self.OTRA
        if self.vecino_id:
            self.contacto_nombre = self.contacto_nombre.strip() or self.vecino.nombre
            self.contacto_telefono = self.contacto_telefono.strip() or self.vecino.telefono
        if not self.pk and self.funcionario_id and self.item_id and self.fecha:
            metas = list(MetaFuncionario.objects.filter(funcionario_id=self.funcionario_id, item_id=self.item_id,
                periodo__fecha_inicio__lte=self.fecha, periodo__fecha_termino__gte=self.fecha))
            # Un registro nuevo posterior al tope se conserva, pero no ocupa cupo puntuable.
            self.sin_puntaje_por_tope = bool(metas and all(m.cumplimiento >= 120 for m in metas))

    @staticmethod
    def semana_cerrada(fecha):
        # El lunes siguiente está incluido; el cierre comienza el martes a las 00:00 locales.
        return bool(fecha and timezone.localdate() > fecha - timedelta(days=fecha.weekday()) + timedelta(days=7))

    def validar_semana(self):
        original = type(self).objects.filter(pk=self.pk).values_list('fecha', flat=True).first() if self.pk else None
        if self.semana_cerrada(self.fecha) or self.semana_cerrada(original):
            raise ValidationError('La semana de esta actividad está cerrada desde el martes siguiente. No se permite ingresar ni modificar el registro.')

    @property
    def motivo_no_puntuable(self):
        if self.sin_puntaje_por_tope:
            return 'El ítem ya había alcanzado el tope de 120 % al registrar esta actividad.'
        if self.atencion_id and (not self.atencion.solicitante.strip() or not self.atencion.telefono.strip()):
            return 'La solicitud de origen no tiene nombre y teléfono completos.'
        if self.beneficiario_funcionario_id and self.beneficiario_funcionario.tiene_rol(Rol.DELEGADO):
            return 'El beneficiario es el delegado: Otra gestión.'
        if self.clasificacion not in (self.EJECUCION, self.FELICITACION):
            return 'Las coordinaciones y otras gestiones no generan puntaje.'
        if not self.contacto_nombre.strip() or not self.contacto_telefono.strip():
            return 'Falta el nombre o el teléfono del vecino o usuario.'
        if not self.item_id or not self.item.puntuable or not self.item.vigente:
            return 'El ítem no está habilitado en el catálogo de puntuación.'
        if self.item.tipo_resultado != self.clasificacion:
            return 'La clasificación no corresponde al resultado admitido por el ítem del catálogo.'
        return ''

    @property
    def es_candidata(self):
        return not self.motivo_no_puntuable

    @property
    def genera_puntaje(self):
        if not self.es_candidata or not self.pk:
            return False
        if self.estado_verificacion:
            return self.estado_verificacion == self.VER_PONDERA
        if self.clasificacion == self.FELICITACION:
            felicitacion = getattr(self, 'felicitacion', None)
            return bool(felicitacion and felicitacion.es_valida_para_puntuar)
        return any(e.estado == Evidencia.APROBADA for e in self.evidencias.all())

    def save(self, *args, **kwargs):
        # Serializa las escrituras del funcionario también en SQLite, donde
        # select_for_update no toma bloqueos de fila. Evita dos octavas actividades.
        with transaction.atomic():
            if self.funcionario_id:
                Funcionario.objects.filter(pk=self.funcionario_id).update(last_login=models.F('last_login'))
            if not self.codigo:
                SecuenciaCatalogo.objects.get_or_create(prefijo='ACT')
                SecuenciaCatalogo.objects.filter(pk='ACT').update(ultimo=models.F('ultimo') + 1)
                self.codigo = f'ACT{SecuenciaCatalogo.objects.values_list("ultimo", flat=True).get(pk="ACT"):06d}'
            self.clean()
            anterior = type(self).objects.filter(pk=self.pk).first() if self.pk else None
            if anterior and anterior.estado_verificacion in (self.VER_PONDERA, self.VER_NO_PONDERA) and not kwargs.pop('permitir_revision', False):
                raise ValidationError('Una actividad aprobada está bloqueada y no admite modificaciones.')
            campos = ('item_id', 'fecha', 'solicitud', 'accion', 'contacto_nombre', 'contacto_telefono',
                      'clasificacion', 'beneficiario_funcionario_id', 'atencion_id', 'hito_id', 'vecino_id')
            cambiado = anterior and any(getattr(anterior, c) != getattr(self, c) for c in campos)
            resultado = super().save(*args, **kwargs)
            if cambiado:
                self.evidencias.filter(estado=Evidencia.APROBADA).update(estado=Evidencia.PENDIENTE)
                ReclamoFelicitacion.objects.filter(actividad=self).update(validada_por=None, validada_en=None)
            return resultado

    @property
    def estado_evidencia(self):
        evidencia = self.evidencias.order_by("-id").first()
        return evidencia.get_estado_display() if evidencia else "Sin evidencia"


class Evidencia(models.Model):
    """Fotografía que respalda una actividad. El código se genera solo (RF-03, RF-04)."""

    PENDIENTE, APROBADA, RECHAZADA = "PEN", "APR", "REC"
    ESTADOS = [(PENDIENTE, "Pendiente"), (APROBADA, "Aprobada"), (RECHAZADA, "Rechazada")]
    MOMENTOS = [("ANTES", "Antes"), ("DESPUES", "Después")]

    actividad = models.ForeignKey(Actividad, on_delete=models.CASCADE, related_name="evidencias",
                                  verbose_name="actividad")
    codigo = models.CharField("código", max_length=20, unique=True, editable=False)
    archivo = models.FileField("archivo", upload_to="evidencias/%Y/%m/")
    momento = models.CharField("momento", max_length=10, choices=MOMENTOS, default="ANTES")
    estado = models.CharField("estado", max_length=3, choices=ESTADOS, default=PENDIENTE)
    cargada_en = models.DateTimeField("cargada en", auto_now_add=True)
    autor = models.ForeignKey(Funcionario, on_delete=models.PROTECT, null=True, blank=True,
                              related_name='evidencias_cargadas')
    observacion = models.TextField(blank=True)
    verificador = models.ForeignKey(Funcionario, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name='evidencias_verificadas')
    revisada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "evidencia"
        verbose_name_plural = "evidencias"
        ordering = ["-cargada_en"]

    def __str__(self):
        return self.codigo

    def save(self, *args, **kwargs):
        if not self.codigo:
            with transaction.atomic():
                SecuenciaCatalogo.objects.get_or_create(prefijo='GES')
                SecuenciaCatalogo.objects.filter(pk='GES').update(ultimo=models.F('ultimo') + 1)
                self.codigo = f'GES{SecuenciaCatalogo.objects.values_list("ultimo", flat=True).get(pk="GES"):06d}'
        super().save(*args, **kwargs)


class Validacion(models.Model):
    """Decisión del verificador sobre una evidencia (RF-05, RF-06 · CU-08)."""

    evidencia = models.ForeignKey(Evidencia, on_delete=models.CASCADE, related_name="validaciones",
                                  verbose_name="evidencia")
    verificador = models.ForeignKey(Funcionario, on_delete=models.PROTECT, related_name="validaciones",
                                    verbose_name="verificador")
    decision = models.CharField("decisión", max_length=3,
                                choices=[(Evidencia.APROBADA, "Aprobar"), (Evidencia.RECHAZADA, "Rechazar")])
    observacion = models.TextField("observación", blank=True)
    fecha = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        verbose_name = "validación"
        verbose_name_plural = "validaciones"
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.evidencia} · {self.get_decision_display()}"

    def clean(self):
        if self.decision == Evidencia.RECHAZADA and not (self.observacion or "").strip():
            raise ValidationError({"observacion": "Para rechazar una evidencia debes indicar el motivo."})
        if self.evidencia_id and self.verificador_id == self.evidencia.actividad.funcionario_id:
            raise ValidationError("Un funcionario no puede validar sus propias evidencias.")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # La evidencia toma el estado de la decisión; el avance se recalcula solo,
        # porque MetaFuncionario.avance cuenta las evidencias aprobadas.
        self.evidencia.estado = self.decision
        self.evidencia.save(update_fields=["estado"])


class RevisionActividad(models.Model):
    actividad = models.ForeignKey(Actividad, on_delete=models.PROTECT, related_name='revisiones')
    verificador = models.ForeignKey(Funcionario, on_delete=models.PROTECT, related_name='revisiones_actividad')
    decision = models.CharField(max_length=3, choices=[c for c in Actividad.ESTADOS_VERIFICACION if c[0]])
    observacion = models.TextField()
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha', '-pk']

    def clean(self):
        if self.actividad_id and self.verificador_id == self.actividad.funcionario_id:
            raise ValidationError('Un funcionario no puede revisar su propia actividad.')
        if len((self.observacion or '').strip()) < 5:
            raise ValidationError({'observacion': 'Registra una observación de al menos 5 caracteres.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        with transaction.atomic():
            super().save(*args, **kwargs)
            Actividad.objects.filter(pk=self.actividad_id).update(estado_verificacion=self.decision)
            if self.decision in (Actividad.VER_PONDERA, Actividad.VER_NO_PONDERA,
                                 Actividad.VER_RECHAZADA, Actividad.VER_ANULADA):
                Actividad.objects.filter(pk=self.actividad_id).update(fecha_cierre=timezone.now())
            else:
                Actividad.objects.filter(pk=self.actividad_id).update(fecha_cierre=None)
            Auditoria.objects.create(funcionario=self.verificador, evento='REVISAR', entidad='actividad',
                                     registro_id=str(self.actividad_id),
                                     detalle=f'{self.get_decision_display()}: {self.observacion}')


class Compromiso(models.Model):
    """Tarea futura de la agenda colectiva, el 'tubo de trabajo' (RF-07, RF-08)."""

    INGRESADO, PENDIENTE, EN_PROCESO, REALIZADO = "ING", "PEN", "PRO", "REA"
    CERRADO, NO_APLICA = 'CER', 'NAP'
    ESTADOS = [(INGRESADO, "Ingresado"), (PENDIENTE, "Pendiente"),
               (EN_PROCESO, "En proceso"), (REALIZADO, "Realizado"),
               (CERRADO, 'Cerrado'), (NO_APLICA, 'No aplica')]

    codigo = models.CharField(max_length=24, unique=True, blank=True, editable=False)

    delegacion = models.ForeignKey(Delegacion, on_delete=models.PROTECT, related_name="compromisos",
                                   verbose_name="delegación")
    responsable = models.ForeignKey(Funcionario, on_delete=models.PROTECT, related_name="compromisos",
                                    verbose_name="responsable")
    actividad = models.ForeignKey(Actividad, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name="compromisos", verbose_name="actividad de origen")
    descripcion = models.CharField("actividad, solicitud o problema", max_length=250)
    solicitante = models.CharField("solicitante", max_length=120, blank=True)
    territorio = models.CharField("territorio", max_length=80, blank=True)
    area_apoyo = models.CharField("área o persona de apoyo", max_length=120, blank=True)
    fecha_comprometida = models.DateField("fecha comprometida")
    estado = models.CharField("estado", max_length=3, choices=ESTADOS, default=INGRESADO)
    observacion = models.TextField("avance u observaciones", blank=True)
    creado_en = models.DateTimeField("creado en", auto_now_add=True, null=True)
    modificado_en = models.DateTimeField(auto_now=True, null=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True, editable=False)
    motivo_reasignacion = models.CharField(max_length=250, blank=True)
    hito = models.ForeignKey('Hito', on_delete=models.PROTECT, null=True, blank=True, related_name='tareas')

    class Meta:
        verbose_name = "compromiso"
        verbose_name_plural = "compromisos"
        ordering = ["fecha_comprometida"]

    def __str__(self):
        return self.descripcion

    def clean(self):
        anterior = type(self).objects.filter(pk=self.pk).values_list('estado', flat=True).first()
        if anterior and anterior != self.estado and len((self.observacion or '').strip()) < 5:
            raise ValidationError({'observacion': 'Describe el avance con al menos 5 caracteres.'})
        if self.hito_id:
            if self.delegacion_id != self.hito.delegacion_id:
                raise ValidationError({'hito': 'El hito debe pertenecer a la misma delegación.'})
            if self.responsable_id and not self.hito.responsables.filter(pk=self.responsable_id).exists():
                raise ValidationError({'responsable': 'El responsable debe estar asignado al hito.'})
        if self.fecha_comprometida and not self.pk and self.fecha_comprometida < timezone.localdate():
            raise ValidationError({"fecha_comprometida": "La fecha comprometida no puede estar en el pasado."})
        if self.responsable_id and self.delegacion_id and self.responsable.delegacion_id != self.delegacion_id:
            raise ValidationError({"responsable": "El responsable debe pertenecer a la delegación indicada."})
        if self.estado == self.REALIZADO and not (self.observacion or "").strip():
            raise ValidationError({"observacion": "Para marcar un compromiso como realizado, describe el avance."})

    def save(self, *args, **kwargs):
        if not self.codigo:
            with transaction.atomic():
                SecuenciaCatalogo.objects.get_or_create(prefijo='TUBO')
                SecuenciaCatalogo.objects.filter(pk='TUBO').update(ultimo=models.F('ultimo') + 1)
                self.codigo = f'TUBO{SecuenciaCatalogo.objects.values_list("ultimo", flat=True).get(pk="TUBO"):06d}'
        if self.estado in (self.CERRADO, self.NO_APLICA) and not self.fecha_cierre:
            self.fecha_cierre = timezone.now()
        if self.estado not in (self.CERRADO, self.NO_APLICA):
            self.fecha_cierre = None
        super().save(*args, **kwargs)

    @property
    def vencido(self):
        return self.estado not in (self.REALIZADO, self.CERRADO, self.NO_APLICA) and self.fecha_comprometida < timezone.localdate()

    def guardar_con_historial(self, usuario):
        with transaction.atomic():
            # Una escritura previa serializa cambios concurrentes también en SQLite.
            type(self).objects.filter(pk=self.pk).update(estado=models.F('estado'))
            previo = type(self).objects.filter(pk=self.pk).values('estado', 'responsable_id').first()
            anterior = previo['estado'] if previo else None
            self.full_clean()
            self.save()
            if anterior != self.estado:
                HistorialCompromiso.objects.create(
                    compromiso=self, estado_anterior=anterior or '', estado_nuevo=self.estado,
                    autor=usuario, observacion=self.observacion or 'Creación del compromiso.',
                )
            responsable_anterior = previo['responsable_id'] if previo else None
            if responsable_anterior != self.responsable_id:
                if previo and len((self.motivo_reasignacion or '').strip()) < 5:
                    raise ValidationError('Indica el motivo de la reasignación.')
                HistorialResponsable.objects.create(
                    compromiso=self, responsable_anterior_id=responsable_anterior,
                    responsable_nuevo=self.responsable, autor=usuario,
                    motivo=self.motivo_reasignacion or 'Asignación inicial.',
                )
            Auditoria.objects.create(
                funcionario=usuario, evento='EDITAR' if anterior else 'CREAR',
                entidad='compromiso', registro_id=str(self.pk), detalle=str(self),
            )


class HistorialCompromiso(models.Model):
    """Trazabilidad de los cambios de estado de un compromiso (RF-09)."""

    compromiso = models.ForeignKey(Compromiso, on_delete=models.CASCADE, related_name="historial",
                                   verbose_name="compromiso")
    estado_anterior = models.CharField("estado anterior", max_length=3, choices=Compromiso.ESTADOS, blank=True)
    estado_nuevo = models.CharField("estado nuevo", max_length=3, choices=Compromiso.ESTADOS)
    autor = models.ForeignKey(Funcionario, on_delete=models.PROTECT, related_name="cambios_compromiso",
                              verbose_name="autor")
    observacion = models.TextField("observación", blank=True)
    fecha = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        verbose_name = "cambio de estado"
        verbose_name_plural = "historial de compromisos"
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.compromiso} · {self.get_estado_nuevo_display()}"


class HistorialResponsable(models.Model):
    compromiso = models.ForeignKey(Compromiso, on_delete=models.CASCADE, related_name='historial_responsables')
    responsable_anterior = models.ForeignKey(Funcionario, on_delete=models.PROTECT, null=True, blank=True,
                                              related_name='reasignaciones_salida')
    responsable_nuevo = models.ForeignKey(Funcionario, on_delete=models.PROTECT,
                                          related_name='reasignaciones_entrada')
    autor = models.ForeignKey(Funcionario, on_delete=models.PROTECT, related_name='reasignaciones_realizadas')
    motivo = models.TextField()
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha', '-pk']


class ReclamoFelicitacion(models.Model):
    """Canal unificado de reclamos y felicitaciones (RF-13)."""

    RECLAMO, FELICITACION = "REC", "FEL"
    TIPOS = [(RECLAMO, "Reclamo"), (FELICITACION, "Felicitación")]
    CANALES = [("WSP", "WhatsApp"), ("MAIL", "Correo"), ("PRES", "Presencial"), ("MOV", "Formulario móvil")]
    ESTADOS = [("ING", "Ingresado"), ("PRO", "En proceso"), ("CER", "Cerrado")]

    tipo = models.CharField("tipo", max_length=3, choices=TIPOS)
    canal = models.CharField("canal de origen", max_length=4, choices=CANALES)
    delegacion = models.ForeignKey(Delegacion, on_delete=models.PROTECT, related_name="reclamos",
                                   verbose_name="delegación")
    funcionario = models.ForeignKey(Funcionario, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="reclamos", verbose_name="funcionario involucrado")
    vecino = models.CharField("nombre del vecino", max_length=120, blank=True)
    descripcion = models.TextField("descripción")
    estado = models.CharField("estado", max_length=3, choices=ESTADOS, default="ING")
    fecha = models.DateTimeField("fecha de registro", auto_now_add=True)
    telefono = models.CharField('teléfono del vecino', max_length=20, blank=True)
    proviene_de_vecino = models.BooleanField('proviene directamente de un vecino o usuario', default=False)
    dirigida_a = models.CharField(max_length=5, default='PERS', choices=[
        ('DELEG', 'Delegado'), ('DEL', 'Delegación'), ('PERS', 'Funcionario / mensaje personal')])
    respaldo = models.FileField('respaldo formal', upload_to='felicitaciones/%Y/%m/', blank=True)
    actividad = models.OneToOneField(Actividad, on_delete=models.PROTECT, null=True, blank=True, related_name='felicitacion')
    validada_por = models.ForeignKey(Funcionario, on_delete=models.PROTECT, null=True, blank=True,
        related_name='felicitaciones_validadas', editable=False)
    validada_en = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "reclamo o felicitación"
        verbose_name_plural = "reclamos y felicitaciones"
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.delegacion}"

    def clean(self):
        if self.descripcion and len(self.descripcion.strip()) < 10:
            raise ValidationError({"descripcion": "Describe el reclamo o la felicitación con al menos 10 caracteres."})
        if self.tipo == self.FELICITACION and not self.funcionario_id:
            raise ValidationError({"funcionario": "Indica a qué funcionario corresponde la felicitación."})
        if self.funcionario_id and self.delegacion_id and self.funcionario.delegacion_id != self.delegacion_id:
            raise ValidationError({"funcionario": "El funcionario no pertenece a la delegación indicada."})
        if self.actividad_id and (self.actividad.funcionario_id != self.funcionario_id or
                                   self.actividad.clasificacion != Actividad.FELICITACION):
            raise ValidationError({'actividad': 'Selecciona una actividad de tipo Felicitación del funcionario involucrado.'})

    @property
    def es_valida_para_puntuar(self):
        return bool(self.tipo == self.FELICITACION and self.proviene_de_vecino and
                    self.dirigida_a in ('DELEG', 'DEL') and self.respaldo and self.vecino.strip() and
                    self.telefono.strip() and self.validada_por_id and self.validada_en and self.actividad_id)

    def validar(self, usuario):
        if not usuario.tiene_rol(Rol.DELEGADO) or usuario.delegacion_id != self.delegacion_id:
            raise ValidationError('Solo el delegado de esta delegación puede validar la felicitación.')
        if not (self.tipo == self.FELICITACION and self.proviene_de_vecino and self.dirigida_a in ('DELEG', 'DEL')
                and self.respaldo and self.vecino.strip() and self.telefono.strip() and self.actividad_id):
            raise ValidationError('Para validar se requiere origen vecinal, destinatario delegado/delegación, nombre, teléfono, respaldo formal y actividad de felicitación.')
        self.clean()
        if not self.actividad.es_candidata:
            raise ValidationError(self.actividad.motivo_no_puntuable)
        self.validada_por, self.validada_en = usuario, timezone.now()
        self.save(update_fields=['validada_por', 'validada_en'])

    def save(self, *args, **kwargs):
        if self.pk:
            anterior = type(self).objects.get(pk=self.pk)
            campos = ('tipo', 'funcionario_id', 'delegacion_id', 'vecino', 'telefono', 'descripcion',
                      'proviene_de_vecino', 'dirigida_a', 'respaldo', 'actividad_id')
            if any(getattr(anterior, c) != getattr(self, c) for c in campos):
                self.validada_por = self.validada_en = None
                if kwargs.get('update_fields'):
                    kwargs['update_fields'] = set(kwargs['update_fields']) | {'validada_por', 'validada_en'}
        return super().save(*args, **kwargs)


class HistorialReclamo(models.Model):
    carta = models.ForeignKey(ReclamoFelicitacion, on_delete=models.CASCADE, related_name='historial')
    estado_anterior = models.CharField(max_length=3, choices=ReclamoFelicitacion.ESTADOS, blank=True)
    estado_nuevo = models.CharField(max_length=3, choices=ReclamoFelicitacion.ESTADOS)
    autor = models.ForeignKey(Funcionario, on_delete=models.PROTECT)
    observacion = models.TextField()
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha', '-pk']


class Carta(models.Model):
    INGRESADA, DERIVADA, EN_PROCESO = 'ING', 'DER', 'PRO'
    APROBADA, FINALIZADA, NO_APLICA = 'APR', 'FIN', 'NAP'
    ESTADOS = [
        (INGRESADA, 'Ingresada'), (DERIVADA, 'Derivada'), (EN_PROCESO, 'En proceso'),
        (APROBADA, 'Aprobada'), (FINALIZADA, 'Finalizada'), (NO_APLICA, 'No aplica'),
    ]
    numero = models.CharField(max_length=24, unique=True, blank=True, editable=False)
    fecha = models.DateField(default=timezone.localdate)
    remitente = models.CharField(max_length=160)
    destinatario = models.CharField(max_length=160)
    telefono = models.CharField(max_length=20, blank=True)
    materia = models.CharField(max_length=250)
    fecha_actividad_respuesta = models.DateField(null=True, blank=True)
    responsable = models.ForeignKey(Funcionario, on_delete=models.PROTECT, related_name='cartas')
    delegacion = models.ForeignKey(Delegacion, on_delete=models.PROTECT, related_name='cartas')
    area_derivada = models.CharField(max_length=160, blank=True)
    estado = models.CharField(max_length=3, choices=ESTADOS, default=INGRESADA)
    pronunciamiento = models.TextField(blank=True)
    observaciones = models.TextField(blank=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True, editable=False)
    creada_en = models.DateTimeField(auto_now_add=True)
    modificada_en = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        ordering = ['-fecha', '-pk']

    def __str__(self):
        return f'{self.numero} · {self.materia}'

    def clean(self):
        if self.responsable_id and self.delegacion_id and self.responsable.delegacion_id != self.delegacion_id:
            raise ValidationError({'responsable': 'El responsable debe pertenecer a la delegación.'})
        if self.estado in (self.APROBADA, self.FINALIZADA) and len((self.pronunciamiento or '').strip()) < 5:
            raise ValidationError({'pronunciamiento': 'Registra el pronunciamiento antes de aprobar o finalizar.'})

    def save(self, *args, **kwargs):
        if not self.numero:
            with transaction.atomic():
                SecuenciaCatalogo.objects.get_or_create(prefijo='CARTA')
                SecuenciaCatalogo.objects.filter(pk='CARTA').update(ultimo=models.F('ultimo') + 1)
                self.numero = f'CAR{SecuenciaCatalogo.objects.values_list("ultimo", flat=True).get(pk="CARTA"):06d}'
        if self.estado in (self.FINALIZADA, self.NO_APLICA) and not self.fecha_cierre:
            self.fecha_cierre = timezone.now()
        if self.estado not in (self.FINALIZADA, self.NO_APLICA):
            self.fecha_cierre = None
        super().save(*args, **kwargs)


class HistorialCarta(models.Model):
    # Sin índices automáticos: SQLite conserva los nombres de índice del historial
    # de reclamos al renombrar esa tabla durante la migración 0008.
    carta = models.ForeignKey(Carta, on_delete=models.CASCADE, related_name='historial', db_index=False)
    estado_anterior = models.CharField(max_length=3, choices=Carta.ESTADOS, blank=True)
    estado_nuevo = models.CharField(max_length=3, choices=Carta.ESTADOS)
    responsable_anterior = models.ForeignKey(Funcionario, on_delete=models.PROTECT, null=True, blank=True,
                                              related_name='cartas_reasignadas_salida')
    responsable_nuevo = models.ForeignKey(Funcionario, on_delete=models.PROTECT,
                                          related_name='cartas_reasignadas_entrada')
    autor = models.ForeignKey(Funcionario, on_delete=models.PROTECT, related_name='cambios_cartas', db_index=False)
    observacion = models.TextField()
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha', '-pk']


class DocumentoCarta(models.Model):
    carta = models.ForeignKey(Carta, on_delete=models.CASCADE, related_name='documentos')
    archivo = models.FileField(upload_to='cartas/%Y/%m/')
    autor = models.ForeignKey(Funcionario, on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True)


class Notificacion(models.Model):
    """Aviso automático, por ejemplo al registrarse una felicitación (RF-15)."""

    destinatario = models.ForeignKey(Funcionario, on_delete=models.CASCADE, related_name="notificaciones",
                                     verbose_name="destinatario")
    registro = models.ForeignKey(ReclamoFelicitacion, on_delete=models.CASCADE, null=True, blank=True,
                                 related_name="notificaciones", verbose_name="registro asociado")
    mensaje = models.CharField("mensaje", max_length=250)
    leida = models.BooleanField("leída", default=False)
    enviada_en = models.DateTimeField("enviada en", auto_now_add=True)

    class Meta:
        verbose_name = "notificación"
        verbose_name_plural = "notificaciones"
        ordering = ["-enviada_en"]

    def __str__(self):
        return self.mensaje


class Auditoria(models.Model):
    """Registro de operaciones críticas: quién, qué y cuándo (RNF-08)."""

    funcionario = models.ForeignKey(Funcionario, on_delete=models.SET_NULL, null=True,
                                    related_name="eventos", verbose_name="usuario")
    evento = models.CharField("evento", max_length=20)
    entidad = models.CharField("entidad", max_length=60)
    registro_id = models.CharField("id del registro", max_length=20, blank=True)
    detalle = models.TextField("detalle", blank=True)
    fecha = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        verbose_name = "evento de auditoría"
        verbose_name_plural = "auditoría"
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.fecha:%d/%m/%Y %H:%M} · {self.evento} · {self.entidad}"


# --- Módulos de segunda evaluación ---
class TipoAtencion(CatalogoConCodigo):
    prefijo_codigo = 'T'
    codigo = models.CharField(max_length=20, unique=True, editable=False)
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.CharField(max_length=250, blank=True)
    activo = models.BooleanField(default=True)
    def __str__(self): return self.nombre
    class Meta: ordering = ['nombre']; verbose_name = 'tipo de atención'

class SubAtencion(CatalogoConCodigo):
    prefijo_codigo = 'S'
    codigo = models.CharField(max_length=20, unique=True, editable=False)
    nombre = models.CharField(max_length=100)
    tipo = models.ForeignKey(TipoAtencion, on_delete=models.PROTECT, related_name='subatenciones')
    activo = models.BooleanField(default=True)
    def __str__(self): return f'{self.tipo} · {self.nombre}'
    class Meta: ordering = ['nombre']; verbose_name = 'subatención'

class AtencionCiudadana(models.Model):
    codigo = models.CharField(max_length=24, unique=True, blank=True, editable=False)
    solicitante = models.CharField(max_length=160, blank=True)
    contacto = models.CharField(max_length=100, blank=True)
    telefono = models.CharField('teléfono del solicitante', max_length=20, blank=True)
    vecino = models.ForeignKey('Vecino', on_delete=models.PROTECT, null=True, blank=True)
    tipo = models.ForeignKey(TipoAtencion, on_delete=models.PROTECT)
    subatencion = models.ForeignKey(SubAtencion, on_delete=models.PROTECT)
    descripcion = models.TextField()
    delegacion = models.ForeignKey(Delegacion, on_delete=models.PROTECT)
    responsable = models.ForeignKey(Funcionario, on_delete=models.PROTECT)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_atencion = models.DateField(default=timezone.localdate)
    meta_asignada = models.ForeignKey(MetaFuncionario, on_delete=models.PROTECT, null=True, blank=True,
                                      related_name='gestiones_sociales')
    visita = models.BooleanField(default=False)
    ingresa_tubo = models.BooleanField(default=False)
    primera_gestion = models.TextField(blank=True)
    fecha_visita_programada = models.DateField(null=True, blank=True)
    segunda_gestion = models.TextField(blank=True)
    fecha_visita = models.DateField(null=True, blank=True)
    fecha_informe = models.DateField(null=True, blank=True)
    tercera_gestion = models.TextField(blank=True)
    fecha_beneficio = models.DateField(null=True, blank=True)
    derivacion = models.CharField(max_length=200, blank=True)
    resultado = models.TextField(blank=True)
    observaciones = models.TextField(blank=True)
    estado = models.CharField(max_length=3, default='ING', choices=[
        ('ING', 'Ingresada'), ('PRO', 'En proceso'), ('CER', 'Cerrada'), ('NAP', 'No aplica')])
    fecha_cierre = models.DateTimeField(null=True, blank=True, editable=False)
    modificada_en = models.DateTimeField(auto_now=True)
    def __str__(self): return f'{self.codigo or "AT-nueva"} · {self.solicitante}'
    def clean(self):
        super().clean()
        if self.vecino_id:
            self.solicitante = self.solicitante.strip() or self.vecino.nombre
            self.telefono = self.telefono.strip() or self.vecino.telefono
            if self.delegacion_id and self.vecino.delegacion_id != self.delegacion_id:
                raise ValidationError({'vecino': 'El vecino debe pertenecer a la delegación de la atención.'})
        if self.fecha_registro and Actividad.semana_cerrada(timezone.localtime(self.fecha_registro).date()):
            raise ValidationError('La semana de esta solicitud está cerrada. No se permite modificarla.')
        if self.tipo_id and self.subatencion_id and self.subatencion.tipo_id != self.tipo_id:
            raise ValidationError({'subatencion':'No corresponde al tipo de atención elegido.'})
        if self.tipo_id and not self.tipo.activo:
            raise ValidationError({'tipo':'Tipo de atención inactivo.'})
        if self.subatencion_id and not self.subatencion.activo:
            raise ValidationError({'subatencion':'Subatención inactiva.'})
        if self.meta_asignada_id:
            if self.meta_asignada.funcionario_id != self.responsable_id:
                raise ValidationError({'meta_asignada': 'La meta no pertenece al responsable.'})
            if not (self.meta_asignada.periodo.fecha_inicio <= self.fecha_atencion <= self.meta_asignada.periodo.fecha_termino):
                raise ValidationError({'meta_asignada': 'La atención queda fuera del trimestre de la meta.'})
        fechas = [self.fecha_atencion, self.fecha_visita_programada, self.fecha_visita,
                  self.fecha_informe, self.fecha_beneficio]
        anteriores = [fecha for fecha in fechas if fecha]
        if anteriores != sorted(anteriores):
            raise ValidationError('Las fechas de la gestión social deben conservar su orden cronológico.')
    def save(self, *args, **kwargs):
        if not self.codigo:
            with transaction.atomic():
                SecuenciaCatalogo.objects.get_or_create(prefijo='SOC')
                SecuenciaCatalogo.objects.filter(pk='SOC').update(ultimo=models.F('ultimo') + 1)
                self.codigo = f'SOC{SecuenciaCatalogo.objects.values_list("ultimo", flat=True).get(pk="SOC"):06d}'
        if self.estado in ('CER', 'NAP') and not self.fecha_cierre:
            self.fecha_cierre = timezone.now()
        super().save(*args, **kwargs)
    @property
    def dias_hasta_primera_gestion(self):
        return (self.fecha_visita_programada - self.fecha_atencion).days if self.fecha_visita_programada else None
    @property
    def dias_programacion_visita(self):
        return (self.fecha_visita - self.fecha_visita_programada).days if self.fecha_visita and self.fecha_visita_programada else None
    @property
    def dias_visita_informe(self):
        return (self.fecha_informe - self.fecha_visita).days if self.fecha_informe and self.fecha_visita else None
    @property
    def dias_atencion_beneficio(self):
        return (self.fecha_beneficio - self.fecha_atencion).days if self.fecha_beneficio else None
    class Meta: ordering = ['-fecha_registro']

class CodigoRecuperacion(models.Model):
    usuario = models.ForeignKey(Funcionario, on_delete=models.CASCADE)
    hash_codigo = models.CharField(max_length=128)
    creado = models.DateTimeField(default=timezone.now)
    vence = models.DateTimeField()
    intentos = models.PositiveSmallIntegerField(default=0)
    verificado = models.BooleanField(default=False)
    utilizado = models.BooleanField(default=False)
    class Meta: ordering = ['-creado']


class CredencialActivacion(models.Model):
    usuario = models.ForeignKey(Funcionario, on_delete=models.CASCADE, related_name='credenciales_activacion')
    hash_codigo = models.CharField(max_length=128)
    creado = models.DateTimeField(default=timezone.now)
    vence = models.DateTimeField()
    utilizada = models.BooleanField(default=False)
    intentos = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['-creado']


class Organizacion(CatalogoConCodigo):
    prefijo_codigo = 'ORG'
    codigo = models.CharField(max_length=20, unique=True, blank=True, editable=False)
    nombre = models.CharField(max_length=160)
    tipo = models.CharField(max_length=2, choices=[('JV', 'Junta de vecinos'), ('OC', 'Organización comunitaria')])
    domicilio_legal = models.CharField(max_length=200)
    territorio = models.CharField(max_length=100)
    territorio_asignado = models.ForeignKey(Territorio, on_delete=models.SET_NULL, null=True, blank=True)
    delegacion = models.ForeignKey(Delegacion, on_delete=models.PROTECT, related_name='organizaciones')
    socios_activos = models.PositiveIntegerField(null=True, blank=True)
    fecha_constitucion = models.DateField('fecha de constitución')
    registro_personalidad = models.CharField('número de personalidad jurídica', max_length=80)
    fecha_inscripcion = models.DateField('fecha de inscripción')
    numero_registro = models.CharField('número de registro', max_length=80)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = 'organización'
        verbose_name_plural = 'organizaciones'

    def __str__(self):
        return self.nombre

    def clean(self):
        if self.fecha_constitucion and self.fecha_inscripcion and self.fecha_inscripcion < self.fecha_constitucion:
            raise ValidationError({'fecha_inscripcion': 'La inscripción no puede ser anterior a la constitución.'})


class Vecino(models.Model):
    rut = models.CharField(max_length=12, unique=True, null=True, blank=True)
    nombre = models.CharField(max_length=160)
    apellidos = models.CharField(max_length=160, blank=True)
    telefono = models.CharField('teléfono', max_length=20)
    email = models.EmailField(blank=True)
    direccion = models.CharField('dirección', max_length=200, blank=True)
    territorio = models.CharField(max_length=100)
    territorio_asignado = models.ForeignKey(Territorio, on_delete=models.SET_NULL, null=True, blank=True)
    delegacion = models.ForeignKey(Delegacion, on_delete=models.PROTECT, related_name='vecinos')
    activo = models.BooleanField(default=True)
    organizaciones = models.ManyToManyField(Organizacion, through='Membresia', related_name='vecinos')

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return f'{self.nombre} {self.apellidos}'.strip()

    def clean(self):
        if self.rut:
            self.rut = normalizar_rut(self.rut)
            if not rut_valido(self.rut):
                raise ValidationError({'rut': 'El RUT no es válido.'})
        if self.territorio_asignado_id and self.territorio_asignado.delegacion_id != self.delegacion_id:
            raise ValidationError({'territorio_asignado': 'El territorio debe pertenecer a la delegación.'})

    @property
    def pertenece_junta(self):
        return self.membresias.filter(activa=True, organizacion__tipo='JV', organizacion__activa=True).exists()


class Membresia(models.Model):
    vecino = models.ForeignKey(Vecino, on_delete=models.PROTECT, related_name='membresias')
    organizacion = models.ForeignKey(Organizacion, on_delete=models.PROTECT, related_name='membresias')
    rol = models.CharField(max_length=3, choices=[('SOC', 'Socio/a'), ('DIR', 'Dirigente')], default='SOC')
    cargo = models.CharField('cargo en la organización', max_length=100, blank=True)
    activa = models.BooleanField(default=True)
    fecha_incorporacion = models.DateField(default=timezone.localdate)

    class Meta:
        verbose_name = 'pertenencia a organización'
        constraints = [models.UniqueConstraint(fields=['vecino', 'organizacion'], name='membresia_vecino_organizacion_unica')]

    def __str__(self):
        return f'{self.vecino} · {self.organizacion} · {self.get_rol_display()}'

    def clean(self):
        if self.vecino_id and self.organizacion_id and self.vecino.delegacion_id != self.organizacion.delegacion_id:
            raise ValidationError({'organizacion': 'El vecino y la organización deben pertenecer a la misma delegación.'})


class Hito(CatalogoConCodigo):
    prefijo_codigo = 'HIT'
    codigo = models.CharField(max_length=20, unique=True, blank=True, editable=False)
    nombre = models.CharField(max_length=160)
    descripcion = models.TextField('descripción')
    fecha_inicio = models.DateField()
    fecha_termino = models.DateField('fecha de término', null=True, blank=True)
    territorio = models.CharField(max_length=100)
    territorio_asignado = models.ForeignKey(Territorio, on_delete=models.SET_NULL, null=True, blank=True)
    delegacion = models.ForeignKey(Delegacion, on_delete=models.PROTECT, related_name='hitos')
    recursos = models.TextField('recursos asociados', blank=True)
    responsables = models.ManyToManyField(Funcionario, related_name='hitos_responsables')
    estado = models.CharField(max_length=3, default='PLA', choices=[
        ('PLA', 'Planificado'), ('PRO', 'En ejecución'), ('FIN', 'Finalizado'), ('CAN', 'Cancelado')])
    recurrente = models.BooleanField(default=False)
    periodicidad = models.CharField(max_length=80, blank=True, help_text='Ejemplo: anual, cada diciembre.')
    creado_por = models.ForeignKey(Funcionario, on_delete=models.PROTECT, related_name='hitos_creados', editable=False)
    creado_en = models.DateTimeField(auto_now_add=True, null=True)
    modificado_en = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        ordering = ['fecha_inicio', 'nombre']

    def __str__(self):
        return self.nombre

    def clean(self):
        if self.fecha_inicio and self.fecha_termino and self.fecha_termino < self.fecha_inicio:
            raise ValidationError({'fecha_termino': 'El término no puede ser anterior al inicio.'})
        if self.recurrente and not self.periodicidad.strip():
            raise ValidationError({'periodicidad': 'Indica la periodicidad del evento recurrente.'})
        if not self.recurrente:
            self.periodicidad = ''
        if self.creado_por_id and not (self.creado_por.is_superuser or self.creado_por.tiene_rol(Rol.ADMINISTRADOR, Rol.DELEGADO)):
            raise ValidationError('Solo un delegado o administrador puede crear hitos.')

    @property
    def situacion(self):
        hoy = timezone.localdate()
        if self.estado in ('FIN', 'CAN'):
            return self.get_estado_display()
        if self.fecha_termino and self.fecha_termino < hoy:
            return 'Vencido'
        if self.fecha_inicio <= hoy + timedelta(days=30):
            return 'Próximo'
        return self.get_estado_display()


class Ausencia(models.Model):
    funcionario = models.ForeignKey(Funcionario, on_delete=models.PROTECT, related_name='ausencias')
    tipo = models.CharField(max_length=3, choices=[('LIB', 'Día libre'), ('VAC', 'Vacaciones'),
        ('ADM', 'Día administrativo'), ('LIC', 'Licencia'), ('OTR', 'Otra ausencia justificada')])
    fecha_inicio = models.DateField()
    fecha_termino = models.DateField('fecha de término')
    motivo = models.CharField('justificación', max_length=250)
    activa = models.BooleanField(default=True)
    registrada_por = models.ForeignKey(Funcionario, on_delete=models.PROTECT, related_name='ausencias_registradas', editable=False)

    class Meta:
        ordering = ['-fecha_inicio']

    def __str__(self):
        return f'{self.funcionario} · {self.get_tipo_display()} · {self.fecha_inicio} / {self.fecha_termino}'

    def clean(self):
        if self.fecha_inicio and self.fecha_termino and self.fecha_termino < self.fecha_inicio:
            raise ValidationError({'fecha_termino': 'El término no puede ser anterior al inicio.'})
        if self.registrada_por_id and self.funcionario_id:
            if not self.registrada_por.tiene_rol(Rol.DELEGADO) or self.registrada_por.delegacion_id != self.funcionario.delegacion_id:
                raise ValidationError('Solo el delegado de la delegación puede registrar ausencias.')
