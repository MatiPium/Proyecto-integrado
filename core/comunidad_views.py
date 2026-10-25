"""Vecinos, organizaciones, hitos y ausencias; permisos en cada petición."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from .comunidad_forms import alcance, VecinoForm, OrganizacionForm, MembresiaForm, HitoForm, AusenciaForm
from .models import Vecino, Organizacion, Membresia, Hito, Ausencia, Rol, Auditoria, ReclamoFelicitacion


MODULOS = {
    'vecino': (Vecino, VecinoForm, 'Vecinos', 'delegacion_id', 'activo'),
    'organizacion': (Organizacion, OrganizacionForm, 'Organizaciones comunitarias', 'delegacion_id', 'activa'),
    'membresia': (Membresia, MembresiaForm, 'Pertenencias y dirigentes', 'vecino__delegacion_id', 'activa'),
    'hito': (Hito, HitoForm, 'Hitos y festividades', 'delegacion_id', None),
    'ausencia': (Ausencia, AusenciaForm, 'Ausencias justificadas', 'funcionario__delegacion_id', 'activa'),
}


def puede_gestionar(usuario, clave):
    if clave == 'ausencia':
        return usuario.tiene_rol(Rol.DELEGADO)
    if clave == 'hito':
        return usuario.is_superuser or usuario.tiene_rol(Rol.ADMINISTRADOR, Rol.DELEGADO)
    return usuario.is_superuser or usuario.tiene_rol(Rol.ADMINISTRADOR, Rol.COORDINADOR, Rol.DELEGADO, Rol.FUNCIONARIO)


class TerritorialMixin(LoginRequiredMixin):
    clave = ''
    escritura = False

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and self.escritura and not puede_gestionar(request.user, self.clave):
            raise PermissionDenied('Tu perfil no puede gestionar este módulo.')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        modelo, _, _, campo, _ = MODULOS[self.clave]
        qs = alcance(self.request.user, modelo.objects.all(), campo)
        if self.clave == 'ausencia' and not (self.request.user.is_superuser or self.request.user.es_coordinacion or self.request.user.tiene_rol(Rol.DELEGADO)):
            qs = qs.filter(funcionario=self.request.user)
        return qs.order_by('-pk')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(clave=self.clave, nombre=MODULOS[self.clave][2],
                   puede_gestionar=puede_gestionar(self.request.user, self.clave),
                   permite_desactivar=bool(MODULOS[self.clave][4]))
        return ctx


class TerritorialList(TerritorialMixin, ListView):
    template_name = 'core/comunidad_list.html'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get('q', '').strip()
        if q:
            campo = {'membresia': 'vecino__nombre', 'ausencia': 'funcionario__username'}.get(self.clave, 'nombre')
            qs = qs.filter(**{campo + '__icontains': q})
        return qs


class TerritorialGuardar(TerritorialMixin):
    escritura = True
    template_name = 'core/form.html'

    def get_form_kwargs(self):
        return dict(super().get_form_kwargs(), usuario=self.request.user)

    def get_success_url(self):
        return reverse(self.clave + '_detalle', args=[self.object.pk])

    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)
            Auditoria.objects.create(funcionario=self.request.user, evento='GUARDAR', entidad=self.clave,
                                     registro_id=str(self.object.pk), detalle=str(self.object))
        messages.success(self.request, 'Registro guardado correctamente.')
        return response


class TerritorialCreate(TerritorialGuardar, CreateView):
    pass


class TerritorialUpdate(TerritorialGuardar, UpdateView):
    pass


class TerritorialDetalle(TerritorialMixin, DetailView):
    template_name = 'core/comunidad_detalle.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['campos'] = [(f.verbose_name, getattr(self.object, 'get_' + f.name + '_display')()
                         if f.choices else getattr(self.object, f.name))
                        for f in self.object._meta.fields if f.name != 'id']
        if self.clave == 'vecino':
            ctx['membresias'] = self.object.membresias.select_related('organizacion')
        if self.clave == 'organizacion':
            ctx['membresias'] = self.object.membresias.select_related('vecino')
        return ctx


@login_required
@require_POST
def desactivar(request, clave, pk):
    if not puede_gestionar(request.user, clave):
        raise PermissionDenied
    modelo, _, _, campo, atributo = MODULOS[clave]
    if not atributo:
        raise PermissionDenied
    obj = get_object_or_404(alcance(request.user, modelo.objects.all(), campo), pk=pk)
    with transaction.atomic():
        setattr(obj, atributo, False)
        obj.save(update_fields=[atributo])
        Auditoria.objects.create(funcionario=request.user, evento='DESACTIVAR', entidad=clave,
                                 registro_id=str(obj.pk), detalle=str(obj))
    messages.success(request, 'Registro desactivado. Se conserva su historial.')
    return redirect(clave + '_list')


@login_required
@require_POST
def validar_felicitacion(request, pk):
    if not request.user.tiene_rol(Rol.DELEGADO):
        raise PermissionDenied
    with transaction.atomic():
        registro = get_object_or_404(ReclamoFelicitacion.objects.select_for_update(), pk=pk,
                                     delegacion_id=request.user.delegacion_id)
        try:
            registro.validar(request.user)
        except ValidationError as exc:
            messages.error(request, ' '.join(exc.messages))
        else:
            Auditoria.objects.create(funcionario=request.user, evento='VALIDAR', entidad='felicitacion',
                                     registro_id=str(registro.pk), detalle='Respaldo formal validado por el delegado.')
            messages.success(request, 'Felicitación validada formalmente.')
    return redirect('reclamo_list')
