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
from django.db import models
from django.utils import timezone


# ------------------------------------------------------------------ catálogos
class Delegacion(models.Model):
    """Las 6 delegaciones municipales de La Serena."""

    nombre = models.CharField("nombre", max_length=80, unique=True)
    sector = models.CharField("sector", max_length=120, blank=True)
    codigo = models.CharField(max_length=20, blank=True, default="")
    direccion = models.CharField(max_length=180, blank=True, default="")
    comuna = models.CharField(max_length=100, blank=True, default="La Serena")
    activa = models.BooleanField("activa", default=True)

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


class Cargo(models.Model):
    """Función del funcionario: Gestor Social, Territorial OO.CC., etc."""

    nombre = models.CharField("nombre", max_length=100, unique=True)
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


class Item(models.Model):
    """Unidad medible de trabajo de un cargo, con su peso en el cumplimiento."""

    cargo = models.ForeignKey(Cargo, on_delete=models.PROTECT, related_name="items", verbose_name="cargo")
    nombre = models.CharField("nombre", max_length=120)
    unidad = models.CharField("unidad de medida", max_length=40, default="gestión")
    ponderador = models.DecimalField(
        "ponderador (%)", max_digits=5, decimal_places=2,
        validators=[MinValueValidator(0.01), MaxValueValidator(100)],
    )
    vigente = models.BooleanField("vigente", default=True)
    codigo = models.CharField(max_length=20, blank=True, default="")
    descripcion = models.CharField(max_length=250, blank=True, default="")

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
            raise ValidationError({
                "ponderador": f"La suma de ponderadores del cargo llegaría a {usado + self.ponderador}%. "
                              f"El máximo es 100% (disponible: {100 - usado}%)."
            })


class Periodo(models.Model):
    """Trimestre de medición, con los umbrales que definen el semáforo."""

    nombre = models.CharField("nombre", max_length=60, unique=True)
    fecha_inicio = models.DateField("fecha de inicio")
    fecha_termino = models.DateField("fecha de término")
    umbral_verde = models.DecimalField("umbral verde (%)", max_digits=5, decimal_places=2, default=100)
    umbral_ambar = models.DecimalField("umbral ámbar (%)", max_digits=5, decimal_places=2, default=60)
    abierto = models.BooleanField("abierto", default=True)

    class Meta:
        verbose_name = "período"
        verbose_name_plural = "períodos"
        ordering = ["-fecha_inicio"]

    def __str__(self):
        return self.nombre

    def clean(self):
        if self.fecha_inicio and self.fecha_termino and self.fecha_termino <= self.fecha_inicio:
            raise ValidationError({"fecha_termino": "La fecha de término debe ser posterior a la de inicio."})
        if self.umbral_verde is not None and self.umbral_ambar is not None:
            if self.umbral_ambar >= self.umbral_verde:
                raise ValidationError({"umbral_ambar": "El umbral ámbar debe ser menor que el verde."})

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
    delegaciones_autorizadas = models.ManyToManyField(Delegacion, blank=True, related_name="usuarios_autorizados")

    class Meta:
        verbose_name = "funcionario"
        verbose_name_plural = "funcionarios"
        ordering = ["first_name", "last_name"]

    def __str__(self):
        return self.get_full_name() or self.username

    def tiene_rol(self, *codigos):
        return bool(self.rol and self.rol.codigo in codigos)

    @property
    def es_coordinacion(self):
        return self.tiene_rol(Rol.COORDINADOR, Rol.ADMINISTRADOR)

    def clean(self):
        super().clean()
        if self.rol and self.rol.codigo in (Rol.FUNCIONARIO, Rol.DELEGADO, Rol.VERIFICADOR) and not self.delegacion_id:
            raise ValidationError({"delegacion": "Los perfiles operativos deben tener una delegación asignada."})


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
        if self.definida_por_id and not self.definida_por.es_coordinacion:
            raise ValidationError({"definida_por": "Solo un usuario con rol Coordinador o Administrador "
                                                   "puede definir metas."})
        if self.funcionario_id and self.item_id and self.funcionario.cargo_id != self.item.cargo_id:
            raise ValidationError({"item": "El ítem no pertenece al cargo del funcionario."})
        if self.periodo_id and not self.periodo.abierto:
            raise ValidationError({"periodo": "No se pueden definir metas en un período cerrado."})

    @property
    def avance(self):
        """Cuenta las actividades del período que tienen evidencia aprobada."""
        return Actividad.objects.filter(
            funcionario=self.funcionario, item=self.item,
            fecha__range=(self.periodo.fecha_inicio, self.periodo.fecha_termino),
            evidencias__estado=Evidencia.APROBADA,
        ).distinct().count()

    @property
    def cumplimiento(self):
        if not self.valor_objetivo:
            return 0
        return round(self.avance / self.valor_objetivo * 100, 1)

    @property
    def resultado_ponderado(self):
        return round(float(self.item.ponderador) * min(self.cumplimiento, 150) / 100, 1)

    @property
    def semaforo(self):
        """verde / ambar / rojo comparando con el avance esperado al día de hoy (RF-12)."""
        esperado = self.periodo.avance_esperado
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
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="actividades", verbose_name="ítem")
    fecha = models.DateField("fecha de la actividad")
    tipo_atencion = models.CharField("tipo de atención", max_length=80, blank=True)
    solicitud = models.TextField("solicitud o problema atendido")
    accion = models.TextField("acción ejecutada")
    contacto_nombre = models.CharField("nombre del contacto", max_length=120, blank=True)
    contacto_telefono = models.CharField("teléfono del contacto", max_length=20, blank=True)
    ingresa_agenda = models.BooleanField("ingresar a la agenda colectiva", default=False)
    creada_en = models.DateTimeField("creada en", auto_now_add=True)

    class Meta:
        verbose_name = "actividad"
        verbose_name_plural = "actividades"
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"{self.fecha} · {self.item} · {self.funcionario}"

    def clean(self):
        if self.fecha and self.fecha > timezone.localdate():
            raise ValidationError({"fecha": "No se pueden registrar actividades con fecha futura."})
        if self.funcionario_id and self.item_id and self.funcionario.cargo_id != self.item.cargo_id:
            raise ValidationError({"item": "El ítem seleccionado no corresponde al cargo del funcionario."})
        if self.solicitud and len(self.solicitud.strip()) < 10:
            raise ValidationError({"solicitud": "Describe la solicitud con al menos 10 caracteres."})
        if self.accion and len(self.accion.strip()) < 10:
            raise ValidationError({"accion": "Indica la acción ejecutada con al menos 10 caracteres."})

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
    archivo = models.ImageField("fotografía", upload_to="evidencias/%Y/%m/")
    momento = models.CharField("momento", max_length=10, choices=MOMENTOS, default="ANTES")
    estado = models.CharField("estado", max_length=3, choices=ESTADOS, default=PENDIENTE)
    cargada_en = models.DateTimeField("cargada en", auto_now_add=True)

    class Meta:
        verbose_name = "evidencia"
        verbose_name_plural = "evidencias"
        ordering = ["-cargada_en"]

    def __str__(self):
        return self.codigo

    def save(self, *args, **kwargs):
        if not self.codigo:
            prefijo = (self.actividad.item.cargo.nombre[:3] or "SGR").upper()
            correlativo = Evidencia.objects.filter(codigo__startswith=prefijo).count() + 1
            self.codigo = f"{prefijo}{correlativo:04d}"
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


class Compromiso(models.Model):
    """Tarea futura de la agenda colectiva, el 'tubo de trabajo' (RF-07, RF-08)."""

    INGRESADO, PENDIENTE, EN_PROCESO, REALIZADO = "ING", "PEN", "PRO", "REA"
    ESTADOS = [(INGRESADO, "Ingresado"), (PENDIENTE, "Pendiente"),
               (EN_PROCESO, "En proceso"), (REALIZADO, "Realizado")]

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
    creado_en = models.DateTimeField("creado en", auto_now_add=True)

    class Meta:
        verbose_name = "compromiso"
        verbose_name_plural = "compromisos"
        ordering = ["fecha_comprometida"]

    def __str__(self):
        return self.descripcion

    def clean(self):
        if self.fecha_comprometida and not self.pk and self.fecha_comprometida < timezone.localdate():
            raise ValidationError({"fecha_comprometida": "La fecha comprometida no puede estar en el pasado."})
        if self.responsable_id and self.delegacion_id and self.responsable.delegacion_id != self.delegacion_id:
            raise ValidationError({"responsable": "El responsable debe pertenecer a la delegación indicada."})
        if self.estado == self.REALIZADO and not (self.observacion or "").strip():
            raise ValidationError({"observacion": "Para marcar un compromiso como realizado, describe el avance."})

    @property
    def vencido(self):
        return self.estado != self.REALIZADO and self.fecha_comprometida < timezone.localdate()


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
class TipoAtencion(models.Model):
    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.CharField(max_length=250, blank=True)
    activo = models.BooleanField(default=True)
    def __str__(self): return self.nombre
    class Meta: ordering = ['nombre']; verbose_name = 'tipo de atención'

class SubAtencion(models.Model):
    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=100)
    tipo = models.ForeignKey(TipoAtencion, on_delete=models.PROTECT, related_name='subatenciones')
    activo = models.BooleanField(default=True)
    def __str__(self): return f'{self.tipo} · {self.nombre}'
    class Meta: ordering = ['nombre']; verbose_name = 'subatención'

class AtencionCiudadana(models.Model):
    solicitante = models.CharField(max_length=160)
    contacto = models.CharField(max_length=100, blank=True)
    tipo = models.ForeignKey(TipoAtencion, on_delete=models.PROTECT)
    subatencion = models.ForeignKey(SubAtencion, on_delete=models.PROTECT)
    descripcion = models.TextField()
    delegacion = models.ForeignKey(Delegacion, on_delete=models.PROTECT)
    responsable = models.ForeignKey(Funcionario, on_delete=models.PROTECT)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f'AT-{self.pk or "nuevo"} · {self.solicitante}'
    def clean(self):
        super().clean()
        if self.tipo_id and self.subatencion_id and self.subatencion.tipo_id != self.tipo_id:
            raise ValidationError({'subatencion':'No corresponde al tipo de atención elegido.'})
        if self.tipo_id and not self.tipo.activo:
            raise ValidationError({'tipo':'Tipo de atención inactivo.'})
        if self.subatencion_id and not self.subatencion.activo:
            raise ValidationError({'subatencion':'Subatención inactiva.'})
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
