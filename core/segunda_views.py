"""Incremento de segunda evaluación: mantenedores, atención y recuperación."""
import secrets
from datetime import timedelta
from io import BytesIO
from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView
from openpyxl import Workbook
from .models import Delegacion, Rol, Item, TipoAtencion, SubAtencion, AtencionCiudadana, CodigoRecuperacion, Auditoria, Funcionario
from .forms import DelegacionForm, ItemForm, TipoAtencionForm, SubAtencionForm, RolForm, AtencionCiudadanaForm

ADMIN_ROLES = (Rol.ADMINISTRADOR, Rol.COORDINADOR)
class AdminRequired(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser or self.request.user.tiene_rol(*ADMIN_ROLES)
    def handle_no_permission(self):
        if self.request.user.is_authenticated: return HttpResponseForbidden('Acceso restringido a administración.')
        return super().handle_no_permission()


class CatalogList(AdminRequired, ListView):
    template_name = 'core/catalogo.html'
    paginate_by = 10
    nombre = 'Mantenedor'
    columnas = ()
    clave = ''

    def get_queryset(self):
        qs = self.model.objects.all().order_by('pk')
        q = self.request.GET.get('q', '').strip()

        if q:
            conditions = Q()

            for col in self.columnas:
                conditions |= Q(**{f'{col}__icontains': q})

            # Permite buscar roles por su nombre visible.
            if self.model == Rol:
                for codigo, nombre in Rol.OPCIONES:
                    if q.casefold() in nombre.casefold():
                        conditions |= Q(codigo=codigo)

            qs = qs.filter(conditions).distinct()

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['nombre'] = self.nombre
        context['clave'] = self.clave
        context['q'] = self.request.GET.get('q', '')
        context['total'] = self.get_queryset().count()

        return context



class CatalogCreate(AdminRequired,CreateView):
    template_name='core/form.html'
    def get_success_url(self): return reverse_lazy(self.clave+'_list')
    def form_valid(self,form):
        response=super().form_valid(form);messages.success(self.request,'Registro creado correctamente.');return response
class CatalogEdit(AdminRequired,UpdateView):
    template_name='core/form.html'
    def get_success_url(self): return reverse_lazy(self.clave+'_list')
    def form_valid(self,form):
        response=super().form_valid(form);messages.success(self.request,'Cambios guardados.');return response

CATALOGOS={
'delegaciones':(Delegacion,DelegacionForm,('nombre','sector','codigo','direccion','comuna')),
'roles':(Rol,RolForm,('codigo','descripcion')),
'items':(Item,ItemForm,('nombre','codigo','descripcion','unidad')),
'tipos':(TipoAtencion,TipoAtencionForm,('codigo','nombre','descripcion')),
'subatenciones':(SubAtencion,SubAtencionForm,('codigo','nombre')),
}

def catalogo_clases(clave):
    model,form,cols=CATALOGOS[clave]
    # Vistas distintas por catálogo; clase construida al iniciar servidor.
    return (
      type(f'{clave}Lista',(CatalogList,),{'model':model,'columnas':cols,'nombre':clave.title(),'clave':clave}),
      type(f'{clave}Crear',(CatalogCreate,),{'model':model,'form_class':form,'clave':clave}),
      type(f'{clave}Editar',(CatalogEdit,),{'model':model,'form_class':form,'clave':clave}),
    )

def catalogo_desactivar(request,clave,pk):
    from django.contrib.auth.decorators import login_required
    if not request.user.is_authenticated: return redirect('login')
    if not (request.user.is_superuser or request.user.tiene_rol(*ADMIN_ROLES)): return HttpResponseForbidden('No autorizado')
    if request.method!='POST': return HttpResponse(status=405)
    obj=get_object_or_404(CATALOGOS[clave][0],pk=pk)
    campo={'delegaciones':'activa','roles':'activo','items':'vigente','tipos':'activo','subatenciones':'activo'}[clave]
    setattr(obj,campo,False);obj.save(update_fields=[campo])
    messages.success(request,'Registro desactivado; se conserva su historial.')
    return redirect(clave+'_list')

def exportar_catalogo(request,clave):
    if not request.user.is_authenticated: return redirect('login')
    if not (request.user.is_superuser or request.user.tiene_rol(*ADMIN_ROLES)): return HttpResponseForbidden('No autorizado')
    modelo,_,columnas=CATALOGOS[clave]
    qs=modelo.objects.all().order_by('pk');q=request.GET.get('q','').strip()

    if q:
        filtro = Q()

        for col in columnas:
            filtro |= Q(**{f'{col}__icontains': q})

        if clave == 'roles':
            for codigo, nombre in Rol.OPCIONES:
                if q.casefold() in nombre.casefold():
                    filtro |= Q(codigo=codigo)

        qs = qs.filter(filtro).distinct()

    wb=Workbook();ws=wb.active;ws.title=clave[:31];ws.append(['ID',*columnas,'Estado'])
    campo={'delegaciones':'activa','roles':'activo','items':'vigente','tipos':'activo','subatenciones':'activo'}[clave]
    for obj in qs.iterator(): ws.append([obj.pk,*[str(getattr(obj,col) or '') for col in columnas], 'Activo' if getattr(obj,campo) else 'Inactivo'])
    out=BytesIO();wb.save(out)
    res=HttpResponse(out.getvalue(),content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    res['Content-Disposition']=f'attachment; filename="sgr_{clave}.xlsx"'
    return res

class AtencionCreate(LoginRequiredMixin,CreateView):
    model=AtencionCiudadana;form_class=AtencionCiudadanaForm;template_name='core/atencion_form.html'
    def get_form_kwargs(self):
        return dict(super().get_form_kwargs(), usuario=self.request.user,
                    delegacion_id=self.request.session.get('delegacion_activa_id') or self.request.user.delegacion_id)
    def form_valid(self,form):
        usuario=self.request.user
        delegacion_id=self.request.session.get('delegacion_activa_id') or usuario.delegacion_id
        if not delegacion_id:
            form.add_error(None,'Tu usuario no tiene delegación asignada. Contacta a administración.');return self.form_invalid(form)
        autorizadas=set(usuario.delegaciones_autorizadas.values_list('pk',flat=True))
        if usuario.delegacion_id: autorizadas.add(usuario.delegacion_id)
        if not usuario.is_superuser and int(delegacion_id) not in autorizadas:
            return HttpResponseForbidden('Delegación no autorizada')
        with transaction.atomic():
            form.instance.responsable=usuario;form.instance.delegacion_id=delegacion_id
            result=super().form_valid(form)
            Auditoria.objects.create(funcionario=usuario,evento='CREAR',entidad='AtencionCiudadana',registro_id=str(self.object.pk),detalle='Atención registrada')
        messages.success(self.request,f'Atención AT-{self.object.pk} registrada correctamente.')
        return result
    def get_success_url(self): return reverse_lazy('atencion_create')

class AtencionList(LoginRequiredMixin,ListView):
    model=AtencionCiudadana;template_name='core/atencion_list.html';paginate_by=10
    def get_queryset(self):
        u=self.request.user
        ids=set(u.delegaciones_autorizadas.values_list('id',flat=True))
        if u.delegacion_id: ids.add(u.delegacion_id)
        qs=AtencionCiudadana.objects.select_related('tipo','subatencion','delegacion','responsable')
        if not u.is_superuser: qs=qs.filter(delegacion_id__in=ids)
        q=self.request.GET.get('q','').strip()
        if q: qs=qs.filter(Q(solicitante__icontains=q)|Q(descripcion__icontains=q))
        return qs


class AtencionUpdate(LoginRequiredMixin, UpdateView):
    model = AtencionCiudadana
    form_class = AtencionCiudadanaForm
    template_name = 'core/atencion_form.html'
    success_url = reverse_lazy('atencion_list')

    def get_queryset(self):
        from .comunidad_forms import alcance
        qs = alcance(self.request.user, AtencionCiudadana.objects.all())
        if not (self.request.user.es_coordinacion or self.request.user.is_superuser):
            qs = qs.filter(responsable=self.request.user)
        return qs

    def get_form_kwargs(self):
        return dict(super().get_form_kwargs(), usuario=self.request.user, delegacion_id=self.object.delegacion_id)

    def form_valid(self, form):
        # Completar el contacto de una solicitud puede volver puntuable su ejecución.
        # Se revalida el límite diario dentro de la misma transacción.
        from .models import Actividad
        try:
            with transaction.atomic():
                response = super().form_valid(form)
                actividad = Actividad.objects.filter(atencion=self.object).first()
                if actividad:
                    actividad.contacto_nombre = self.object.solicitante
                    actividad.contacto_telefono = self.object.telefono
                    actividad.save()
                Auditoria.objects.create(funcionario=self.request.user, evento='EDITAR', entidad='AtencionCiudadana',
                    registro_id=str(self.object.pk), detalle='Datos de la solicitud actualizados')
        except ValidationError as exc:
            form.add_error(None, ' '.join(exc.messages))
            return self.form_invalid(form)
        messages.success(self.request, 'Atención actualizada.')
        return response

def subatenciones_json(request):
    if not request.user.is_authenticated: return JsonResponse({'error':'No autorizado'},status=403)
    return JsonResponse({'opciones':list(SubAtencion.objects.filter(activo=True,tipo_id=request.GET.get('tipo')).values('id','nombre'))})

def cambiar_delegacion(request):
    if not request.user.is_authenticated: return redirect('login')
    if request.method!='POST': return HttpResponse(status=405)
    destino=request.POST.get('delegacion')
    permitidas=set(request.user.delegaciones_autorizadas.values_list('id',flat=True))
    if request.user.delegacion_id: permitidas.add(request.user.delegacion_id)
    if not destino or not destino.isdigit() or int(destino) not in permitidas: return HttpResponseForbidden('Delegación no autorizada')
    request.session['delegacion_activa_id']=int(destino)
    messages.info(request,'Delegación activa actualizada.')
    return redirect('inicio')

# Recuperación con código de seis dígitos, vigencia y bloqueo por intentos.
GENERIC='Si el correo está registrado, recibirás instrucciones para recuperar el acceso.'
def recuperar_solicitar(request):
    if request.method=='POST':
        correo=request.POST.get('email','').strip()
        user=Funcionario.objects.filter(email__iexact=correo,is_active=True).first()
        if user:
            anterior=CodigoRecuperacion.objects.filter(usuario=user).first()
            if not anterior or timezone.now()-anterior.creado>=timedelta(seconds=45):
                codigo=f'{secrets.randbelow(1000000):06d}'
                with transaction.atomic():
                    CodigoRecuperacion.objects.filter(usuario=user,utilizado=False).update(utilizado=True)
                    CodigoRecuperacion.objects.create(usuario=user,hash_codigo=make_password(codigo),vence=timezone.now()+timedelta(minutes=10))
                try: send_mail('Código de recuperación SGR',f'Tu código es {codigo}. Vence en 10 minutos. Si no lo solicitaste, ignora este correo.',None,[user.email],fail_silently=False)
                except Exception:
                    # No revelar existencia de cuenta ni exponer el código en pantalla.
                    import logging;logging.getLogger(__name__).exception('Fallo al enviar correo de recuperación')
        messages.info(request,GENERIC)
        return redirect('recuperar_validar')
    return render(request,'registration/recuperar_solicitar.html')

def recuperar_validar(request):
    if request.method=='POST':
        correo=request.POST.get('email','').strip();codigo=request.POST.get('codigo','').strip()
        user=Funcionario.objects.filter(email__iexact=correo,is_active=True).first()
        intento=CodigoRecuperacion.objects.filter(usuario=user,utilizado=False).first() if user else None
        if intento and timezone.now()<intento.vence and intento.intentos<5:
            intento.intentos+=1
            if check_password(codigo,intento.hash_codigo):
                intento.verificado=True;intento.save(update_fields=['intentos','verificado'])
                request.session['recuperacion_id']=intento.pk
                return redirect('recuperar_nueva')
            intento.save(update_fields=['intentos'])
        messages.error(request,'Código incorrecto, vencido o bloqueado.')
    return render(request,'registration/recuperar_validar.html')

def recuperar_nueva(request):
    intento=CodigoRecuperacion.objects.select_related('usuario').filter(pk=request.session.get('recuperacion_id'),verificado=True,utilizado=False,vence__gt=timezone.now()).first()
    if not intento: return redirect('recuperar_solicitar')
    if request.method=='POST':
        clave=request.POST.get('password1','');confirmacion=request.POST.get('password2','')
        if clave!=confirmacion: messages.error(request,'Las contraseñas no coinciden.')
        else:
            try: validate_password(clave,intento.usuario)
            except ValidationError as exc: messages.error(request,' '.join(exc.messages))
            else:
                with transaction.atomic():
                    intento.usuario.set_password(clave);intento.usuario.save(update_fields=['password'])
                    intento.utilizado=True;intento.save(update_fields=['utilizado'])
                    CodigoRecuperacion.objects.filter(usuario=intento.usuario,utilizado=False).update(utilizado=True)
                request.session.pop('recuperacion_id',None)
                messages.success(request,'Contraseña actualizada. Ya puedes iniciar sesión.')
                return redirect('login')
    return render(request,'registration/recuperar_nueva.html')


def exportar_usuarios(request):
    if not request.user.is_authenticated: return redirect('login')
    if not (request.user.is_superuser or request.user.tiene_rol(*ADMIN_ROLES)): return HttpResponseForbidden('No autorizado')
    qs=Funcionario.objects.select_related('delegacion','rol').order_by('pk')
    q=request.GET.get('q','').strip()
    if q: qs=qs.filter(Q(username__icontains=q)|Q(first_name__icontains=q)|Q(last_name__icontains=q)|Q(email__icontains=q))
    wb=Workbook();ws=wb.active;ws.title='Usuarios';ws.append(['ID','Usuario','Nombre','Correo','Rol','Delegación','Estado'])
    for u in qs.iterator():ws.append([u.pk,u.username,u.get_full_name(),u.email,str(u.rol or ''),str(u.delegacion or ''),'Activo' if u.is_active else 'Inactivo'])
    out=BytesIO();wb.save(out)
    res=HttpResponse(out.getvalue(),content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');res['Content-Disposition']='attachment; filename="sgr_usuarios.xlsx"';return res
