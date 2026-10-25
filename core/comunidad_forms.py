"""Formularios de gestión territorial con selección limitada por delegación."""
from django import forms
from .forms import BootstrapMixin
from .models import Ausencia, Delegacion, Funcionario, Hito, Membresia, Organizacion, Vecino


def alcance(usuario, queryset, campo='delegacion_id'):
    if usuario.is_superuser or usuario.es_coordinacion:
        return queryset
    if not usuario.delegacion_id:
        return queryset.none()
    return queryset.filter(**{campo: usuario.delegacion_id})


class TerritorialForm(BootstrapMixin, forms.ModelForm):
    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        if 'delegacion' in self.fields:
            self.fields['delegacion'].queryset = alcance(usuario, Delegacion.objects.filter(activa=True), 'pk')
            self.fields['delegacion'].initial = usuario.delegacion_id


class VecinoForm(TerritorialForm):
    class Meta:
        model = Vecino
        fields = ['nombre', 'telefono', 'direccion', 'territorio', 'delegacion', 'activo']


class OrganizacionForm(TerritorialForm):
    class Meta:
        model = Organizacion
        fields = ['nombre', 'tipo', 'domicilio_legal', 'territorio', 'delegacion', 'socios_activos',
                  'fecha_constitucion', 'registro_personalidad', 'fecha_inscripcion', 'numero_registro', 'activa']


class MembresiaForm(TerritorialForm):
    class Meta:
        model = Membresia
        fields = ['vecino', 'organizacion', 'rol', 'cargo', 'activa']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['vecino'].queryset = alcance(self.usuario, Vecino.objects.filter(activo=True))
        self.fields['organizacion'].queryset = alcance(self.usuario, Organizacion.objects.filter(activa=True))


class HitoForm(TerritorialForm):
    class Meta:
        model = Hito
        fields = ['nombre', 'descripcion', 'fecha_inicio', 'fecha_termino', 'territorio', 'delegacion',
                  'recursos', 'responsables', 'estado', 'recurrente', 'periodicidad']
        widgets = {'descripcion': forms.Textarea(attrs={'rows': 3}), 'recursos': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['responsables'].queryset = alcance(self.usuario, Funcionario.objects.filter(is_active=True))
        if not self.instance.pk:
            self.instance.creado_por = self.usuario

    def clean(self):
        datos = super().clean()
        delegacion, responsables = datos.get('delegacion'), datos.get('responsables')
        if delegacion and responsables is not None and responsables.exclude(delegacion=delegacion).exists():
            self.add_error('responsables', 'Todos los responsables deben pertenecer a la delegación del hito.')
        if self.instance.pk and responsables is not None:
            usados = set(self.instance.tareas.values_list('responsable_id', flat=True))
            usados.update(self.instance.actividades.values_list('funcionario_id', flat=True))
            if not usados.issubset(set(responsables.values_list('pk', flat=True))):
                self.add_error('responsables', 'Conserva los responsables que ya tienen tareas o actividades en este hito.')
            if delegacion and delegacion.pk != Hito.objects.get(pk=self.instance.pk).delegacion_id:
                if self.instance.tareas.exists() or self.instance.actividades.exists():
                    self.add_error('delegacion', 'No se puede cambiar la delegación de un hito con tareas o actividades.')
        return datos


class AusenciaForm(TerritorialForm):
    class Meta:
        model = Ausencia
        fields = ['funcionario', 'tipo', 'fecha_inicio', 'fecha_termino', 'motivo', 'activa']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['funcionario'].queryset = Funcionario.objects.filter(delegacion_id=self.usuario.delegacion_id, is_active=True)
        self.instance.registrada_por = self.usuario
