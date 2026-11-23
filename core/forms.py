"""
Formularios del SGR.

Cada ModelForm hereda las validaciones del modelo (clean) y agrega las que
dependen del usuario que está usando el sistema o de la vista.
"""

from django import forms
from django.utils import timezone

from .models import (Actividad, Cargo, Compromiso, Delegacion, Evidencia, Funcionario, Item,
                     MetaFuncionario, Periodo, ReclamoFelicitacion, RevisionActividad, Validacion)


class BootstrapMixin:
    """Aplica las clases de Bootstrap a todos los campos, sin repetir widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            widget = campo.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")
            if isinstance(widget, forms.DateInput):
                widget.input_type = "date"


class DelegacionForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Delegacion
        fields = ["nombre", "direccion", "comuna", "sector", "activa"]


class CargoForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Cargo
        fields = ["nombre", "descripcion", "vigente"]


class ItemForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Item
        fields = ["cargo", "nombre", "descripcion", "vigente", "puntuable", "tipo_resultado"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance._state.adding:
            self.instance.ponderador = 5


class PeriodoForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Periodo
        fields = ["nombre", "fecha_inicio", "fecha_termino", "umbral_verde", "umbral_ambar", "abierto"]
        help_texts = {
            'fecha_inicio': 'Inicio del trimestre: 1 de enero, abril, julio u octubre.',
            'fecha_termino': 'Fin del trimestre: 31 de marzo, 30 de junio, 30 de septiembre o 31 de diciembre.',
        }
        widgets = {
            "fecha_inicio": forms.DateInput(attrs={"type": "date"}),
            "fecha_termino": forms.DateInput(attrs={"type": "date"}),
        }


class FuncionarioForm(BootstrapMixin, forms.ModelForm):
    """Alta de funcionarios pendiente de activación por correo."""

    class Meta:
        model = Funcionario
        fields = ["username", "first_name", "last_name", "rut", "email", "telefono", "territorio_asignado",
                  "delegacion", "delegaciones_autorizadas", "cargo", "rol", "roles"]

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            raise forms.ValidationError("El correo institucional es obligatorio.")
        existe = Funcionario.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists()
        if existe:
            raise forms.ValidationError("Ya existe un funcionario registrado con ese correo.")
        return email

    def save(self, commit=True):
        usuario = super().save(commit=False)
        if usuario._state.adding:
            usuario.set_unusable_password()
            usuario.is_active = False
            usuario.debe_cambiar_clave = True
        if commit:
            usuario.save()
            self.save_m2m()
        return usuario


class FuncionarioEditForm(BootstrapMixin, forms.ModelForm):
    """Edición: no toca la contraseña."""

    class Meta:
        model = Funcionario
        fields = ["username", "first_name", "last_name", "rut", "email", "telefono", "territorio_asignado",
                  "delegacion", "delegaciones_autorizadas", "cargo", "rol", "roles", "is_active"]

    clean_email = FuncionarioForm.clean_email


class MetaForm(BootstrapMixin, forms.ModelForm):
    """Las metas solo las define coordinación; 'definida_por' se toma del usuario en sesión."""

    class Meta:
        model = MetaFuncionario
        fields = ["funcionario", "item", "periodo", "valor_objetivo", "ponderacion", "observacion"]

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        self.fields["periodo"].queryset = Periodo.objects.filter(abierto=True)
        self.fields['valor_objetivo'].label = 'Meta cuantitativa'
        self.fields['ponderacion'].required = False
        self.fields['periodo'].help_text = 'Selecciona un trimestre calendario completo y abierto.'
        self.fields['ponderacion'].help_text = 'Peso para este funcionario y trimestre. Si se omite, se usa el peso vigente del ítem.'
        if usuario:
            self.instance.definida_por = usuario

    def clean(self):
        datos = super().clean()
        if self.usuario and not self.usuario.es_coordinacion:
            raise forms.ValidationError("Tu perfil no puede definir metas. Solicítalo a coordinación.")
        return datos

    @property
    def datos_funcionarios(self):
        return {
            str(f.pk): {'cargo': f.cargo_id, 'delegacion': f.delegacion_id}
            for f in self.fields['funcionario'].queryset.only('id', 'cargo_id', 'delegacion_id')
        }

    @property
    def datos_items(self):
        return {str(i.pk): {'cargo': i.cargo_id} for i in self.fields['item'].queryset.only('id', 'cargo_id')}

    def save(self, commit=True):
        meta = super().save(commit=False)
        if self.usuario:
            meta.definida_por = self.usuario
        if commit:
            meta.guardar_validada()
        return meta


class ActividadForm(BootstrapMixin, forms.ModelForm):
    """Registro de actividad. El funcionario se toma de la sesión, no se elige."""

    class Meta:
        model = Actividad
        fields = ["fecha", "meta_asignada", "item", "tipo_atencion", "solicitud", "accion",
                  "clasificacion", "origen", "vecino", "beneficiario_funcionario", "hito", "tarea_hito", "atencion",
                  "contacto_nombre", "contacto_telefono", "territorio_asignado", "ingresa_agenda",
                  "fecha_compromiso", "area_apoyo", "avance_tubo"]
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}),
            "solicitud": forms.Textarea(attrs={"rows": 3}),
            "accion": forms.Textarea(attrs={"rows": 3}),
            "fecha_compromiso": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        autor = self.instance.funcionario if self.instance.funcionario_id else usuario
        from .comunidad_forms import VecinoForm
        from .comunidad_views import puede_gestionar
        self.vecino_form = None
        if usuario and autor and autor.delegacion_id and puede_gestionar(usuario, 'vecino'):
            self.vecino_form = VecinoForm(usuario=usuario, prefix='nuevo_vecino')
            self.vecino_form.fields.pop('delegacion')
            self.vecino_form.fields.pop('activo')
        if autor:
            from .models import Vecino, Hito, AtencionCiudadana
            self.fields['vecino'].queryset = Vecino.objects.filter(delegacion_id=autor.delegacion_id, activo=True)
            self.fields['beneficiario_funcionario'].queryset = Funcionario.objects.filter(delegacion_id=autor.delegacion_id, is_active=True)
            self.fields['hito'].queryset = Hito.objects.filter(delegacion_id=autor.delegacion_id, responsables=autor)
            self.fields['tarea_hito'].queryset = Compromiso.objects.filter(hito__isnull=False, responsable=autor)
            self.fields['atencion'].queryset = AtencionCiudadana.objects.filter(responsable=autor, delegacion_id=autor.delegacion_id)
            self.fields['meta_asignada'].queryset = MetaFuncionario.objects.filter(
                funcionario=autor, activa=True, periodo__abierto=True).select_related('item', 'periodo')
            self.fields['territorio_asignado'].queryset = (autor.delegacion.territorios.filter(activo=True)
                                                           if autor.delegacion_id else self.fields['territorio_asignado'].queryset.none())
        # Solo se ofrecen los ítems del cargo del funcionario (evita el error antes de que ocurra).
        if autor is not None and autor.cargo_id:
            self.fields["item"].queryset = Item.objects.filter(cargo=autor.cargo, vigente=True)
        else:
            self.fields["item"].queryset = Item.objects.filter(vigente=True)

    @property
    def contactos_vecinos(self):
        return {
            str(vecino.pk): {'nombre': vecino.nombre, 'telefono': vecino.telefono}
            for vecino in self.fields['vecino'].queryset.only('id', 'nombre', 'telefono')
        }

    @property
    def datos_metas(self):
        return {
            str(meta.pk): {
                'item': meta.item_id,
                'item_nombre': meta.item.nombre,
                'trimestre': str(meta.periodo),
                'objetivo': meta.valor_objetivo,
                'ponderacion': str(meta.ponderacion),
            }
            for meta in self.fields['meta_asignada'].queryset
        }

    @property
    def datos_hitos(self):
        return {
            str(h.pk): {'territorio': h.territorio_asignado_id, 'delegacion': h.delegacion_id}
            for h in self.fields['hito'].queryset.only('id', 'territorio_asignado_id', 'delegacion_id')
        }

    def save(self, commit=True):
        actividad = super().save(commit=False)
        if self.usuario and not actividad.funcionario_id:
            actividad.funcionario = self.usuario
        if commit:
            actividad.save()
        return actividad

    def _post_clean(self):
        # Asigna el funcionario antes de que el modelo ejecute su clean().
        if self.usuario and self.instance.funcionario_id is None:
            self.instance.funcionario = self.usuario
        super()._post_clean()


class EvidenciaForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Evidencia
        fields = ["archivo", "momento"]

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        if archivo.size > 10 * 1024 * 1024:
            raise forms.ValidationError("El archivo no puede pesar más de 10 MB.")
        extension = archivo.name.rsplit('.', 1)[-1].lower() if '.' in archivo.name else ''
        if extension not in {'jpg', 'jpeg', 'png', 'webp', 'pdf', 'doc', 'docx', 'xls', 'xlsx'}:
            raise forms.ValidationError('Formato no permitido. Usa imagen, PDF, Word o Excel.')
        return archivo


class RevisionActividadForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = RevisionActividad
        fields = ['decision', 'observacion']
        widgets = {'observacion': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, actividad=None, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.actividad = actividad
        self.instance.verificador = usuario


class ValidacionForm(BootstrapMixin, forms.ModelForm):
    """Aprobar o rechazar una evidencia (CU-08)."""

    class Meta:
        model = Validacion
        fields = ["decision", "observacion"]
        widgets = {"observacion": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, evidencia=None, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.evidencia = evidencia
        self.usuario = usuario

    def _post_clean(self):
        if self.evidencia and self.instance.evidencia_id is None:
            self.instance.evidencia = self.evidencia
        if self.usuario and self.instance.verificador_id is None:
            self.instance.verificador = self.usuario
        super()._post_clean()


class CompromisoForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Compromiso
        fields = ["delegacion", "descripcion", "solicitante", "territorio", "responsable",
                  "area_apoyo", "fecha_comprometida", "estado", "observacion", "motivo_reasignacion", "hito"]
        widgets = {
            "fecha_comprometida": forms.DateInput(attrs={"type": "date"}),
            "observacion": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        from .models import Hito
        self.fields['hito'].queryset = Hito.objects.all()
        if usuario and not (usuario.es_coordinacion or usuario.is_superuser):
            self.fields['hito'].queryset = Hito.objects.filter(delegacion_id=usuario.delegacion_id)
        self.fields["responsable"].queryset = Funcionario.objects.filter(is_active=True)
        if usuario is not None and usuario.delegacion_id and not usuario.es_coordinacion:
            # Un funcionario solo trabaja compromisos de su propia delegación (RNF-05).
            self.fields["delegacion"].queryset = Delegacion.objects.filter(pk=usuario.delegacion_id)
            self.fields["delegacion"].initial = usuario.delegacion_id
            self.fields["responsable"].queryset = Funcionario.objects.filter(
                delegacion_id=usuario.delegacion_id, is_active=True)
            if not usuario.tiene_rol(Rol.DELEGADO):
                self.fields['responsable'].queryset = Funcionario.objects.filter(pk=usuario.pk)
                self.fields['responsable'].initial = usuario.pk

    @property
    def datos_hitos(self):
        return {
            str(h.pk): {'delegacion': h.delegacion_id, 'territorio': h.territorio}
            for h in self.fields['hito'].queryset.only('id', 'delegacion_id', 'territorio')
        }


class CambioEstadoForm(BootstrapMixin, forms.Form):
    """Cambia el estado de un compromiso dejando historial (RF-09)."""

    estado = forms.ChoiceField(label="Nuevo estado", choices=Compromiso.ESTADOS)
    observacion = forms.CharField(label="Observación", widget=forms.Textarea(attrs={"rows": 3}))

    def clean_observacion(self):
        obs = (self.cleaned_data.get("observacion") or "").strip()
        if len(obs) < 5:
            raise forms.ValidationError("Describe el avance con al menos 5 caracteres.")
        return obs


class ReclamoFelicitacionForm(BootstrapMixin, forms.ModelForm):
    observacion_estado = forms.CharField(
        label='Observación del cambio de estado', required=False,
        widget=forms.Textarea(attrs={'rows': 2}),
        help_text='Obligatoria al cambiar el estado.',
    )
    class Meta:
        model = ReclamoFelicitacion
        fields = ["tipo", "canal", "delegacion", "funcionario", "vecino", "telefono", "descripcion", "estado",
                  "proviene_de_vecino", "dirigida_a", "respaldo", "actividad"]
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        self.fields['actividad'].queryset = Actividad.objects.filter(clasificacion=Actividad.FELICITACION)
        if usuario and not (usuario.es_coordinacion or usuario.is_superuser):
            self.fields['delegacion'].queryset = Delegacion.objects.filter(pk=usuario.delegacion_id)
            self.fields['funcionario'].queryset = Funcionario.objects.filter(delegacion_id=usuario.delegacion_id)
            self.fields['actividad'].queryset = self.fields['actividad'].queryset.filter(funcionario__delegacion_id=usuario.delegacion_id)

    def clean_respaldo(self):
        archivo = self.cleaned_data.get('respaldo')
        if archivo and archivo.size > 10 * 1024 * 1024:
            raise forms.ValidationError('El respaldo no puede pesar más de 10 MB.')
        return archivo

    def clean(self):
        datos = super().clean()
        if self.instance.pk:
            anterior = ReclamoFelicitacion.objects.get(pk=self.instance.pk).estado
            if datos.get('estado') != anterior and len(datos.get('observacion_estado', '').strip()) < 5:
                self.add_error('observacion_estado', 'Describe el cambio con al menos 5 caracteres.')
        return datos

    def save(self, commit=True):
        from django.db import transaction
        from django.db.models import F
        from .models import HistorialReclamo
        if not commit:
            return super().save(commit=False)
        with transaction.atomic():
            ReclamoFelicitacion.objects.filter(pk=self.instance.pk).update(estado=F('estado'))
            anterior = ReclamoFelicitacion.objects.filter(pk=self.instance.pk).values_list('estado', flat=True).first()
            observacion = self.cleaned_data.get('observacion_estado', '').strip()
            if anterior and anterior != self.instance.estado and len(observacion) < 5:
                raise forms.ValidationError('Describe el cambio de estado con al menos 5 caracteres.')
            carta = super().save()
            if anterior != carta.estado:
                HistorialReclamo.objects.create(
                    carta=carta, estado_anterior=anterior or '', estado_nuevo=carta.estado,
                    autor=self.usuario, observacion=observacion or 'Registro de la carta.',
                )
            return carta


from .models import TipoAtencion, SubAtencion, AtencionCiudadana, Rol
class TipoAtencionForm(BootstrapMixin, forms.ModelForm):
    class Meta: model = TipoAtencion; fields = ['nombre','descripcion','activo']
class SubAtencionForm(BootstrapMixin, forms.ModelForm):
    class Meta: model = SubAtencion; fields = ['nombre','tipo','activo']
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['tipo'].queryset = TipoAtencion.objects.filter(activo=True) | TipoAtencion.objects.filter(pk=getattr(self.instance,'tipo_id',None))
class RolForm(BootstrapMixin, forms.ModelForm):
    class Meta: model = Rol; fields = ['codigo','descripcion','activo','permisos_descripcion']
class AtencionCiudadanaForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = AtencionCiudadana
        fields = ['solicitante','telefono','contacto','vecino','tipo','subatencion','descripcion',
                  'fecha_atencion','meta_asignada','visita','ingresa_tubo','primera_gestion',
                  'fecha_visita_programada','segunda_gestion','fecha_visita','fecha_informe',
                  'tercera_gestion','fecha_beneficio','derivacion','resultado','observaciones','estado']
        widgets = {'descripcion':forms.Textarea(attrs={'rows':4}), 'primera_gestion': forms.Textarea(attrs={'rows': 2}),
                   'segunda_gestion': forms.Textarea(attrs={'rows': 2}), 'tercera_gestion': forms.Textarea(attrs={'rows': 2}),
                   **{campo: forms.DateInput(attrs={'type': 'date'}) for campo in
                      ('fecha_atencion','fecha_visita_programada','fecha_visita','fecha_informe','fecha_beneficio')}}
    def __init__(self,*args,usuario=None,delegacion_id=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['fecha_atencion'].required = False
        self.fields['fecha_atencion'].initial = timezone.localdate()
        self.fields['estado'].required = False
        self.fields['estado'].initial = AtencionCiudadana.INGRESADA if hasattr(AtencionCiudadana, 'INGRESADA') else 'ING'
        self.fields['tipo'].queryset = TipoAtencion.objects.filter(activo=True)
        self.fields['subatencion'].queryset = SubAtencion.objects.filter(activo=True)
        from .models import Vecino
        self.fields['vecino'].queryset = Vecino.objects.filter(activo=True, delegacion_id=delegacion_id or getattr(usuario, 'delegacion_id', None))
        responsable = self.instance.responsable if self.instance.pk else usuario
        self.fields['meta_asignada'].queryset = MetaFuncionario.objects.filter(
            funcionario=responsable, activa=True, periodo__abierto=True) if responsable else MetaFuncionario.objects.none()
    def clean(self):
        d=super().clean();tipo=d.get('tipo');sub=d.get('subatencion')
        d['fecha_atencion'] = d.get('fecha_atencion') or timezone.localdate()
        d['estado'] = d.get('estado') or 'ING'
        if tipo and sub and sub.tipo_id != tipo.pk:
            self.add_error('subatencion','La subatención no corresponde al tipo elegido.')
        return d
