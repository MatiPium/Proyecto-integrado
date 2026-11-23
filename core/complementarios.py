"""Flujos complementarios: territorios, cartas, revisión, seguridad y reportes."""
import secrets
from datetime import timedelta
from io import BytesIO
from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView
from openpyxl import Workbook

from .forms import BootstrapMixin, RevisionActividadForm
from .models import (Actividad, Auditoria, Carta, Compromiso, CredencialActivacion,
                     Delegacion, DocumentoCarta, Evidencia, Funcionario, HistorialCarta,
                     MetaFuncionario, Periodo, RevisionActividad, Rol, Territorio)
from .segunda_views import AdminRequired


class TerritorioForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Territorio
        fields = ['nombre', 'descripcion', 'delegacion', 'activo']


class TerritorioList(AdminRequired, ListView):
    model = Territorio
    template_name = 'core/territorio_list.html'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().select_related('delegacion')
        q = self.request.GET.get('q', '').strip()
        return qs.filter(Q(codigo__icontains=q) | Q(nombre__icontains=q) |
                         Q(delegacion__nombre__icontains=q)) if q else qs


class TerritorioGuardar(AdminRequired):
    model = Territorio
    form_class = TerritorioForm
    template_name = 'core/form.html'
    success_url = reverse_lazy('territorio_list')

    def form_valid(self, form):
        creado = form.instance.pk is None
        respuesta = super().form_valid(form)
        Auditoria.objects.create(funcionario=self.request.user,
                                 evento='CREAR' if creado else 'EDITAR',
                                 entidad='territorio', registro_id=str(self.object.pk), detalle=str(self.object))
        messages.success(self.request, 'Territorio guardado.')
        return respuesta


class TerritorioCreate(TerritorioGuardar, CreateView):
    pass


class TerritorioUpdate(TerritorioGuardar, UpdateView):
    pass


@require_POST
def territorio_desactivar(request, pk):
    if not request.user.is_authenticated or not (request.user.is_superuser or request.user.es_coordinacion):
        raise PermissionDenied
    territorio = get_object_or_404(Territorio, pk=pk)
    territorio.activo = False
    territorio.save(update_fields=['activo'])
    Auditoria.objects.create(funcionario=request.user, evento='DESACTIVAR', entidad='territorio',
                             registro_id=str(pk), detalle=str(territorio))
    return redirect('territorio_list')


class CartaForm(BootstrapMixin, forms.ModelForm):
    observacion_cambio = forms.CharField(required=False, label='Motivo o avance del cambio',
                                        widget=forms.Textarea(attrs={'rows': 2}))
    documento = forms.FileField(required=False)

    class Meta:
        model = Carta
        fields = ['fecha', 'remitente', 'destinatario', 'telefono', 'materia',
                  'fecha_actividad_respuesta', 'responsable', 'delegacion', 'area_derivada',
                  'estado', 'pronunciamiento', 'observaciones']
        widgets = {'fecha': forms.DateInput(attrs={'type': 'date'}),
                   'fecha_actividad_respuesta': forms.DateInput(attrs={'type': 'date'}),
                   'pronunciamiento': forms.Textarea(attrs={'rows': 3}),
                   'observaciones': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        if usuario and not (usuario.is_superuser or usuario.es_coordinacion):
            self.fields['delegacion'].queryset = Delegacion.objects.filter(pk=usuario.delegacion_id)
            self.fields['responsable'].queryset = Funcionario.objects.filter(delegacion_id=usuario.delegacion_id,
                                                                              is_active=True)

    def clean_documento(self):
        archivo = self.cleaned_data.get('documento')
        if archivo and archivo.size > 10 * 1024 * 1024:
            raise forms.ValidationError('El documento no puede superar 10 MB.')
        return archivo

    def clean(self):
        datos = super().clean()
        if self.instance.pk:
            anterior = Carta.objects.get(pk=self.instance.pk)
            cambio = anterior.estado != datos.get('estado') or anterior.responsable_id != getattr(datos.get('responsable'), 'pk', None)
            if cambio and len((datos.get('observacion_cambio') or '').strip()) < 5:
                self.add_error('observacion_cambio', 'Explica el cambio con al menos 5 caracteres.')
        return datos

    def guardar(self):
        with transaction.atomic():
            anterior = Carta.objects.filter(pk=self.instance.pk).values('estado', 'responsable_id').first()
            carta = super().save()
            observacion = self.cleaned_data.get('observacion_cambio', '').strip() or 'Ingreso de la carta.'
            if not anterior or anterior['estado'] != carta.estado or anterior['responsable_id'] != carta.responsable_id:
                HistorialCarta.objects.create(
                    carta=carta, estado_anterior=anterior['estado'] if anterior else '', estado_nuevo=carta.estado,
                    responsable_anterior_id=anterior['responsable_id'] if anterior else None,
                    responsable_nuevo=carta.responsable, autor=self.usuario, observacion=observacion,
                )
            archivo = self.cleaned_data.get('documento')
            if archivo:
                DocumentoCarta.objects.create(carta=carta, archivo=archivo, autor=self.usuario)
            Auditoria.objects.create(funcionario=self.usuario, evento='EDITAR' if anterior else 'CREAR',
                                     entidad='carta', registro_id=str(carta.pk), detalle=observacion)
            return carta


class CartaAlcanceMixin(LoginRequiredMixin):
    def get_queryset(self):
        qs = Carta.objects.select_related('delegacion', 'responsable')
        if self.request.user.is_superuser or self.request.user.es_coordinacion:
            return qs
        return qs.filter(delegacion_id=self.request.user.delegacion_id)


class CartaList(CartaAlcanceMixin, ListView):
    template_name = 'core/carta_list.html'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()
        q, estado = self.request.GET.get('q', '').strip(), self.request.GET.get('estado', '')
        if q:
            qs = qs.filter(Q(numero__icontains=q) | Q(remitente__icontains=q) |
                           Q(destinatario__icontains=q) | Q(materia__icontains=q))
        if estado:
            qs = qs.filter(estado=estado)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['estados'] = Carta.ESTADOS
        return ctx


class CartaCreate(LoginRequiredMixin, CreateView):
    model = Carta
    form_class = CartaForm
    template_name = 'core/form.html'
    success_url = reverse_lazy('carta_list')

    def get_form_kwargs(self):
        return dict(super().get_form_kwargs(), usuario=self.request.user)

    def form_valid(self, form):
        self.object = form.guardar()
        messages.success(self.request, f'Carta {self.object.numero} registrada.')
        return redirect(self.get_success_url())


class CartaUpdate(CartaAlcanceMixin, UpdateView):
    form_class = CartaForm
    template_name = 'core/form.html'

    def dispatch(self, request, *args, **kwargs):
        carta = self.get_object()
        permitido = request.user.is_superuser or request.user.es_coordinacion or request.user.tiene_rol(Rol.DELEGADO) or carta.responsable_id == request.user.pk
        if not permitido:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return dict(super().get_form_kwargs(), usuario=self.request.user)

    def form_valid(self, form):
        self.object = form.guardar()
        messages.success(self.request, 'Carta actualizada con trazabilidad.')
        return redirect('carta_detail', pk=self.object.pk)


class CartaDetail(CartaAlcanceMixin, DetailView):
    template_name = 'core/carta_detail.html'


class RevisionActividadList(LoginRequiredMixin, ListView):
    model = Actividad
    template_name = 'core/revision_actividad_list.html'
    paginate_by = 20

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not (request.user.is_superuser or request.user.tiene_rol(Rol.VERIFICADOR, Rol.COORDINADOR, Rol.ADMINISTRADOR)):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = Actividad.objects.select_related('funcionario', 'item', 'meta_asignada').prefetch_related('evidencias')
        if self.request.user.tiene_rol(Rol.VERIFICADOR) and self.request.user.delegacion_id:
            qs = qs.filter(funcionario__delegacion_id=self.request.user.delegacion_id)
        estado = self.request.GET.get('estado', Actividad.VER_PENDIENTE)
        return qs.filter(estado_verificacion=estado) if estado else qs.exclude(estado_verificacion='')


class RevisionActividadDetail(LoginRequiredMixin, DetailView):
    model = Actividad
    template_name = 'core/revision_actividad_detail.html'

    def get_queryset(self):
        qs = Actividad.objects.select_related('funcionario', 'item', 'meta_asignada').prefetch_related('evidencias', 'revisiones')
        if self.request.user.tiene_rol(Rol.VERIFICADOR) and self.request.user.delegacion_id:
            qs = qs.filter(funcionario__delegacion_id=self.request.user.delegacion_id)
        return qs

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not (request.user.is_superuser or request.user.tiene_rol(Rol.VERIFICADOR, Rol.COORDINADOR, Rol.ADMINISTRADOR)):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form'] = RevisionActividadForm(actividad=self.object, usuario=self.request.user)
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = RevisionActividadForm(request.POST, actividad=self.object, usuario=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Decisión de verificación registrada.')
            return redirect('revision_actividad_list')
        return self.render_to_response(self.get_context_data(form=form))


@require_POST
def cambiar_estado_trimestre(request, pk):
    if not request.user.is_authenticated or not (request.user.is_superuser or request.user.es_coordinacion):
        raise PermissionDenied
    periodo = get_object_or_404(Periodo, pk=pk)
    try:
        if periodo.abierto:
            periodo.cerrar(request.user)
            messages.success(request, 'Trimestre cerrado y resultados congelados.')
        else:
            periodo.reabrir(request.user, request.POST.get('motivo', ''))
            messages.success(request, 'Trimestre reabierto con registro en bitácora.')
    except ValidationError as exc:
        messages.error(request, ' '.join(exc.messages))
    return redirect('periodo_list')


def enviar_credencial_activacion(usuario):
    codigo = f'{secrets.randbelow(1000000):06d}'
    with transaction.atomic():
        CredencialActivacion.objects.filter(usuario=usuario, utilizada=False).update(utilizada=True)
        CredencialActivacion.objects.create(usuario=usuario, hash_codigo=make_password(codigo),
                                             vence=timezone.now() + timedelta(hours=24))
    send_mail('Activa tu cuenta SGR', f'Tu código temporal es {codigo}. Vence en 24 horas.',
              None, [usuario.email], fail_silently=False)


def activar_cuenta(request):
    if request.method == 'POST':
        identidad = request.POST.get('identidad', '').strip()
        usuario = Funcionario.objects.filter(Q(email__iexact=identidad) | Q(username__iexact=identidad)).first()
        credencial = CredencialActivacion.objects.filter(usuario=usuario, utilizada=False).first() if usuario else None
        codigo = request.POST.get('codigo', '').strip()
        clave = request.POST.get('password1', '')
        if credencial and credencial.vence > timezone.now() and credencial.intentos < 5:
            credencial.intentos += 1
            credencial.save(update_fields=['intentos'])
            if check_password(codigo, credencial.hash_codigo):
                try:
                    validate_password(clave, usuario)
                except ValidationError as exc:
                    messages.error(request, ' '.join(exc.messages))
                else:
                    usuario.set_password(clave)
                    usuario.is_active = True
                    usuario.debe_cambiar_clave = False
                    usuario.save(update_fields=['password', 'is_active', 'debe_cambiar_clave'])
                    credencial.utilizada = True
                    credencial.save(update_fields=['utilizada'])
                    messages.success(request, 'Cuenta activada. Ya puedes iniciar sesión.')
                    return redirect('login')
        messages.error(request, 'Código incorrecto, vencido o bloqueado.')
    return render(request, 'registration/activar.html')


class SGRLoginView(auth_views.LoginView):
    template_name = 'registration/login.html'

    def form_invalid(self, form):
        identidad = self.request.POST.get('username', '')
        usuario = Funcionario.objects.filter(username__iexact=identidad).first()
        if usuario:
            usuario.intentos_fallidos += 1
            if usuario.intentos_fallidos >= 5:
                usuario.bloqueado_hasta = timezone.now() + timedelta(minutes=15)
                usuario.intentos_fallidos = 0
            usuario.save(update_fields=['intentos_fallidos', 'bloqueado_hasta'])
        return super().form_invalid(form)

    def form_valid(self, form):
        usuario = form.get_user()
        if usuario.bloqueado_hasta and usuario.bloqueado_hasta > timezone.now():
            form.add_error(None, 'Cuenta bloqueada temporalmente. Intenta más tarde.')
            return auth_views.LoginView.form_invalid(self, form)
        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None
        usuario.save(update_fields=['intentos_fallidos', 'bloqueado_hasta'])
        return super().form_valid(form)


def secure_media(request, path):
    if not request.user.is_authenticated:
        return redirect(f'{reverse("login")}?next={request.path}')
    raiz = Path(settings.MEDIA_ROOT).resolve()
    archivo = (raiz / path).resolve()
    if raiz not in archivo.parents or not archivo.is_file():
        raise Http404
    permitido = request.user.is_superuser or request.user.es_coordinacion
    if not permitido:
        if path.startswith('evidencias/'):
            permitido = Evidencia.objects.filter(archivo=path, actividad__funcionario__delegacion_id=request.user.delegacion_id).exists()
        elif path.startswith('cartas/'):
            permitido = DocumentoCarta.objects.filter(archivo=path, carta__delegacion_id=request.user.delegacion_id).exists()
        elif path.startswith('felicitaciones/'):
            from .models import ReclamoFelicitacion
            permitido = ReclamoFelicitacion.objects.filter(
                respaldo=path, delegacion_id=request.user.delegacion_id).exists()
    if not permitido:
        raise PermissionDenied
    return FileResponse(open(archivo, 'rb'), as_attachment=False, filename=archivo.name)


REPORTES = {
    'actividades': (Actividad, [('Código', 'codigo'), ('Fecha', 'fecha'), ('Funcionario', 'funcionario'),
                                ('Meta', 'meta_asignada'), ('Estado', 'get_estado_verificacion_display')]),
    'metas': (MetaFuncionario, [('Código', 'codigo'), ('Funcionario', 'funcionario'), ('Meta', 'item'),
                                ('Trimestre', 'periodo'), ('Objetivo', 'valor_objetivo'), ('Ponderación', 'ponderacion')]),
    'tubo': (Compromiso, [('Código', 'codigo'), ('Descripción', 'descripcion'), ('Responsable', 'responsable'),
                          ('Estado', 'get_estado_display'), ('Fecha compromiso', 'fecha_comprometida')]),
    'evidencias': (Evidencia, [('Código', 'codigo'), ('Actividad', 'actividad'), ('Estado', 'get_estado_display'),
                               ('Fecha', 'cargada_en')]),
    'cartas': (Carta, [('Número', 'numero'), ('Materia', 'materia'), ('Responsable', 'responsable'),
                       ('Estado', 'get_estado_display'), ('Fecha', 'fecha')]),
}


def exportar_reporte(request, tipo):
    if not request.user.is_authenticated or tipo not in REPORTES:
        raise PermissionDenied
    modelo, columnas = REPORTES[tipo]
    qs = modelo.objects.all()
    if not (request.user.is_superuser or request.user.es_coordinacion):
        campo = {'actividades': 'funcionario__delegacion_id', 'metas': 'funcionario__delegacion_id',
                 'tubo': 'delegacion_id', 'evidencias': 'actividad__funcionario__delegacion_id',
                 'cartas': 'delegacion_id'}[tipo]
        qs = qs.filter(**{campo: request.user.delegacion_id})
    wb, ws = Workbook(), None
    ws = wb.active
    ws.title = tipo[:31]
    ws.append([titulo for titulo, _ in columnas])
    for obj in qs.iterator():
        fila = []
        for _, atributo in columnas:
            valor = getattr(obj, atributo)
            fila.append(str(valor() if callable(valor) else valor or ''))
        ws.append(fila)
    ws.append([])
    ws.append(['Generado', timezone.localtime().strftime('%d/%m/%Y %H:%M')])
    salida = BytesIO()
    wb.save(salida)
    respuesta = HttpResponse(salida.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    respuesta['Content-Disposition'] = f'attachment; filename="sgr_{tipo}.xlsx"'
    return respuesta
