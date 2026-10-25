"""
Formularios del SGR.

Cada ModelForm hereda las validaciones del modelo (clean) y agrega las que
dependen del usuario que está usando el sistema o de la vista.
"""

from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import (Actividad, Cargo, Compromiso, Delegacion, Evidencia, Funcionario, Item,
                     MetaFuncionario, Periodo, ReclamoFelicitacion, Validacion)


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
        fields = ["codigo", "nombre", "direccion", "comuna", "sector", "activa"]


class CargoForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Cargo
        fields = ["nombre", "descripcion", "vigente"]


class ItemForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Item
        fields = ["codigo", "cargo", "nombre", "descripcion", "unidad", "ponderador", "vigente", "puntuable", "tipo_resultado"]


class PeriodoForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Periodo
        fields = ["nombre", "fecha_inicio", "fecha_termino", "umbral_verde", "umbral_ambar", "abierto"]
        widgets = {
            "fecha_inicio": forms.DateInput(attrs={"type": "date"}),
            "fecha_termino": forms.DateInput(attrs={"type": "date"}),
        }


class FuncionarioForm(BootstrapMixin, UserCreationForm):
    """Alta de funcionarios: usa el formulario de Django para la contraseña."""

    class Meta:
        model = Funcionario
        fields = ["username", "first_name", "last_name", "email", "telefono", "territorio", "delegacion", "delegaciones_autorizadas", "cargo", "rol"]

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            raise forms.ValidationError("El correo institucional es obligatorio.")
        existe = Funcionario.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists()
        if existe:
            raise forms.ValidationError("Ya existe un funcionario registrado con ese correo.")
        return email


class FuncionarioEditForm(BootstrapMixin, forms.ModelForm):
    """Edición: no toca la contraseña."""

    class Meta:
        model = Funcionario
        fields = ["username", "first_name", "last_name", "email", "telefono", "territorio",
                  "delegacion", "delegaciones_autorizadas", "cargo", "rol", "is_active"]

    clean_email = FuncionarioForm.clean_email


class MetaForm(BootstrapMixin, forms.ModelForm):
    """Las metas solo las define coordinación; 'definida_por' se toma del usuario en sesión."""

    class Meta:
        model = MetaFuncionario
        fields = ["funcionario", "item", "periodo", "valor_objetivo"]

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        self.fields["periodo"].queryset = Periodo.objects.filter(abierto=True)

    def clean(self):
        datos = super().clean()
        if self.usuario and not self.usuario.es_coordinacion:
            raise forms.ValidationError("Tu perfil no puede definir metas. Solicítalo a coordinación.")
        return datos

    def save(self, commit=True):
        meta = super().save(commit=False)
        if self.usuario:
            meta.definida_por = self.usuario
        if commit:
            meta.save()
        return meta


class ActividadForm(BootstrapMixin, forms.ModelForm):
    """Registro de actividad. El funcionario se toma de la sesión, no se elige."""

    class Meta:
        model = Actividad
        fields = ["fecha", "item", "tipo_atencion", "solicitud", "accion",
                  "clasificacion", "origen", "vecino", "beneficiario_funcionario", "hito", "tarea_hito", "atencion",
                  "contacto_nombre", "contacto_telefono", "ingresa_agenda"]
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}),
            "solicitud": forms.Textarea(attrs={"rows": 3}),
            "accion": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        autor = self.instance.funcionario if self.instance.funcionario_id else usuario
        if autor:
            from .models import Vecino, Hito, AtencionCiudadana
            self.fields['vecino'].queryset = Vecino.objects.filter(delegacion_id=autor.delegacion_id, activo=True)
            self.fields['beneficiario_funcionario'].queryset = Funcionario.objects.filter(delegacion_id=autor.delegacion_id, is_active=True)
            self.fields['hito'].queryset = Hito.objects.filter(delegacion_id=autor.delegacion_id, responsables=autor)
            self.fields['tarea_hito'].queryset = Compromiso.objects.filter(hito__isnull=False, responsable=autor)
            self.fields['atencion'].queryset = AtencionCiudadana.objects.filter(responsable=autor, delegacion_id=autor.delegacion_id)
        # Solo se ofrecen los ítems del cargo del funcionario (evita el error antes de que ocurra).
        if autor is not None and autor.cargo_id:
            self.fields["item"].queryset = Item.objects.filter(cargo=autor.cargo, vigente=True)
        else:
            self.fields["item"].queryset = Item.objects.filter(vigente=True)

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
            raise forms.ValidationError("La fotografía no puede pesar más de 10 MB.")
        return archivo


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
                  "area_apoyo", "fecha_comprometida", "estado", "observacion", "hito"]
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
    class Meta:
        model = ReclamoFelicitacion
        fields = ["tipo", "canal", "delegacion", "funcionario", "vecino", "telefono", "descripcion", "estado",
                  "proviene_de_vecino", "dirigida_a", "respaldo", "actividad"]
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
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


from .models import TipoAtencion, SubAtencion, AtencionCiudadana, Rol
class TipoAtencionForm(BootstrapMixin, forms.ModelForm):
    class Meta: model = TipoAtencion; fields = ['codigo','nombre','descripcion','activo']
class SubAtencionForm(BootstrapMixin, forms.ModelForm):
    class Meta: model = SubAtencion; fields = ['codigo','nombre','tipo','activo']
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['tipo'].queryset = TipoAtencion.objects.filter(activo=True) | TipoAtencion.objects.filter(pk=getattr(self.instance,'tipo_id',None))
class RolForm(BootstrapMixin, forms.ModelForm):
    class Meta: model = Rol; fields = ['codigo','descripcion','activo','permisos_descripcion']
class AtencionCiudadanaForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = AtencionCiudadana
        fields = ['solicitante','telefono','contacto','vecino','tipo','subatencion','descripcion']
        widgets = {'descripcion':forms.Textarea(attrs={'rows':4})}
    def __init__(self,*args,usuario=None,delegacion_id=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['tipo'].queryset = TipoAtencion.objects.filter(activo=True)
        self.fields['subatencion'].queryset = SubAtencion.objects.filter(activo=True)
        from .models import Vecino
        self.fields['vecino'].queryset = Vecino.objects.filter(activo=True, delegacion_id=delegacion_id or getattr(usuario, 'delegacion_id', None))
    def clean(self):
        d=super().clean();tipo=d.get('tipo');sub=d.get('subatencion')
        if tipo and sub and sub.tipo_id != tipo.pk:
            self.add_error('subatencion','La subatención no corresponde al tipo elegido.')
        return d
