"""
Vistas del SGR.

Se usan vistas basadas en clases (CBV): ListView, CreateView, UpdateView y
DeleteView para los CRUD. Cada grupo comparte un mixin que exige sesión
iniciada y, cuando corresponde, un rol determinado (RNF-05).
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Count, Q
from django.db import transaction
from django.core.exceptions import ValidationError, PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from .forms import (ActividadForm, CambioEstadoForm, CargoForm, CompromisoForm, DelegacionForm,
                    EvidenciaForm, FuncionarioEditForm, FuncionarioForm, ItemForm, MetaForm,
                    PeriodoForm, ReclamoFelicitacionForm, ValidacionForm)
from .models import (Actividad, Auditoria, Cargo, Compromiso, Delegacion, Evidencia, Funcionario,
                     HistorialCompromiso, Item, MetaFuncionario, Notificacion, Periodo,
                     ReclamoFelicitacion, Rol)


# ---------------------------------------------------------------------- mixins
class RolRequeridoMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Permite el acceso solo a los roles indicados en `roles_permitidos`."""

    roles_permitidos = ()

    def test_func(self):
        if self.request.user.is_superuser:
            return True
        if not self.roles_permitidos:
            return True
        return self.request.user.tiene_rol(*self.roles_permitidos)

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.error(self.request, "Tu perfil no tiene acceso a esa sección.")
            return redirect("inicio")
        return super().handle_no_permission()


class MensajeMixin:
    """Muestra un mensaje al guardar y deja el evento en auditoría (RNF-08)."""

    mensaje_exito = "Registro guardado correctamente."

    def form_valid(self, form):
        try:
            with transaction.atomic():
                respuesta = super().form_valid(form)
        except ValidationError as exc:
            form.add_error(None, ' '.join(exc.messages))
            return self.form_invalid(form)
        messages.success(self.request, self.mensaje_exito)
        Auditoria.objects.create(
            funcionario=self.request.user,
            evento="CREAR" if isinstance(self, CreateView) else "EDITAR",
            entidad=self.model._meta.verbose_name,
            registro_id=str(self.object.pk),
            detalle=str(self.object),
        )
        return respuesta


class AdminCRUD(RolRequeridoMixin, MensajeMixin):
    """Base para los mantenedores: solo administración y coordinación."""

    roles_permitidos = (Rol.ADMINISTRADOR, Rol.COORDINADOR)
    template_name = "core/form.html"


# ------------------------------------------------------------------- dashboard
class InicioView(LoginRequiredMixin, TemplateView):
    template_name = "core/inicio.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        usuario = self.request.user
        periodo = Periodo.objects.filter(abierto=True).first()
        metas = MetaFuncionario.objects.filter(funcionario=usuario, periodo=periodo) if periodo else []
        ctx["periodo"] = periodo
        ctx["metas"] = metas
        from .indicadores import resumen_funcionario
        resumen = resumen_funcionario(usuario, list(metas))
        ctx["cumplimiento_total"] = resumen['cumplimiento']
        ctx['avance_esperado_personal'] = resumen['esperado']
        ctx["actividades"] = Actividad.objects.filter(funcionario=usuario)[:5]
        ctx["pendientes"] = Evidencia.objects.filter(estado=Evidencia.PENDIENTE).count()
        ctx["compromisos"] = Compromiso.objects.exclude(estado=Compromiso.REALIZADO).count()
        return ctx


# ----------------------------------------------------------------- delegaciones
class DelegacionList(RolRequeridoMixin, ListView):
    roles_permitidos = (Rol.ADMINISTRADOR, Rol.COORDINADOR)
    model = Delegacion
    template_name = "core/delegacion_list.html"
    context_object_name = "delegaciones"
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().annotate(total=Count("funcionarios")).order_by("nombre")
        buscar = self.request.GET.get("q")
        return qs.filter(nombre__icontains=buscar) if buscar else qs


class DelegacionCreate(AdminCRUD, CreateView):
    model = Delegacion
    form_class = DelegacionForm
    success_url = reverse_lazy("delegacion_list")
    mensaje_exito = "Delegación creada correctamente."


class DelegacionUpdate(AdminCRUD, UpdateView):
    model = Delegacion
    form_class = DelegacionForm
    success_url = reverse_lazy("delegacion_list")
    mensaje_exito = "Delegación actualizada."


class DelegacionDelete(RolRequeridoMixin, DeleteView):
    model = Delegacion
    roles_permitidos = (Rol.ADMINISTRADOR,)
    template_name = "core/confirmar_eliminar.html"
    success_url = reverse_lazy("delegacion_list")

    def form_valid(self, form):
        if self.get_object().funcionarios.exists():
            messages.error(self.request, "No se puede eliminar: la delegación tiene funcionarios asignados.")
            return redirect("delegacion_list")
        messages.success(self.request, "Delegación eliminada.")
        return super().form_valid(form)


# ----------------------------------------------------------------------- cargos
class CargoList(LoginRequiredMixin, ListView):
    model = Cargo
    template_name = "core/cargo_list.html"
    context_object_name = "cargos"


class CargoCreate(AdminCRUD, CreateView):
    model = Cargo
    form_class = CargoForm
    success_url = reverse_lazy("cargo_list")
    mensaje_exito = "Cargo creado correctamente."


class CargoUpdate(AdminCRUD, UpdateView):
    model = Cargo
    form_class = CargoForm
    success_url = reverse_lazy("cargo_list")
    mensaje_exito = "Cargo actualizado."


class CargoDelete(RolRequeridoMixin, DeleteView):
    model = Cargo
    roles_permitidos = (Rol.ADMINISTRADOR,)
    template_name = "core/confirmar_eliminar.html"
    success_url = reverse_lazy("cargo_list")


# ------------------------------------------------------------------------ ítems
class ItemList(RolRequeridoMixin, ListView):
    roles_permitidos = (Rol.ADMINISTRADOR, Rol.COORDINADOR)
    model = Item
    template_name = "core/item_list.html"
    context_object_name = "items"

    def get_queryset(self):
        qs = super().get_queryset().select_related("cargo")
        cargo = self.request.GET.get("cargo")
        return qs.filter(cargo_id=cargo) if cargo else qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["cargos"] = Cargo.objects.all()
        return ctx


class ItemCreate(AdminCRUD, CreateView):
    model = Item
    form_class = ItemForm
    success_url = reverse_lazy("item_list")
    mensaje_exito = "Ítem creado correctamente."


class ItemUpdate(AdminCRUD, UpdateView):
    model = Item
    form_class = ItemForm
    success_url = reverse_lazy("item_list")
    mensaje_exito = "Ítem actualizado."


class ItemDelete(RolRequeridoMixin, DeleteView):
    model = Item
    roles_permitidos = (Rol.ADMINISTRADOR,)
    template_name = "core/confirmar_eliminar.html"
    success_url = reverse_lazy("item_list")


# --------------------------------------------------------------------- períodos
class PeriodoList(LoginRequiredMixin, ListView):
    model = Periodo
    template_name = "core/periodo_list.html"
    context_object_name = "periodos"


class PeriodoCreate(AdminCRUD, CreateView):
    model = Periodo
    form_class = PeriodoForm
    success_url = reverse_lazy("periodo_list")
    mensaje_exito = "Período creado correctamente."


class PeriodoUpdate(AdminCRUD, UpdateView):
    model = Periodo
    form_class = PeriodoForm
    success_url = reverse_lazy("periodo_list")
    mensaje_exito = "Período actualizado."


class PeriodoDelete(RolRequeridoMixin, DeleteView):
    model = Periodo
    roles_permitidos = (Rol.ADMINISTRADOR,)
    template_name = "core/confirmar_eliminar.html"
    success_url = reverse_lazy("periodo_list")


# ----------------------------------------------------------------- funcionarios
class FuncionarioList(RolRequeridoMixin, ListView):
    model = Funcionario
    roles_permitidos = (Rol.ADMINISTRADOR, Rol.COORDINADOR, Rol.DELEGADO)
    template_name = "core/funcionario_list.html"
    context_object_name = "funcionarios"
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().select_related("delegacion", "cargo", "rol")
        buscar = self.request.GET.get("q")
        if buscar:
            qs = qs.filter(Q(first_name__icontains=buscar) | Q(last_name__icontains=buscar) |
                           Q(username__icontains=buscar))
        return qs


class FuncionarioCreate(AdminCRUD, CreateView):
    model = Funcionario
    form_class = FuncionarioForm
    success_url = reverse_lazy("funcionario_list")
    mensaje_exito = "Funcionario creado correctamente."


class FuncionarioUpdate(AdminCRUD, UpdateView):
    model = Funcionario
    form_class = FuncionarioEditForm
    success_url = reverse_lazy("funcionario_list")
    mensaje_exito = "Funcionario actualizado."


class FuncionarioDelete(RolRequeridoMixin, DeleteView):
    model = Funcionario
    roles_permitidos = (Rol.ADMINISTRADOR,)
    template_name = "core/confirmar_eliminar.html"
    success_url = reverse_lazy("funcionario_list")


# ------------------------------------------------------------------------ metas
class MetaList(RolRequeridoMixin, ListView):
    model = MetaFuncionario
    roles_permitidos = (Rol.ADMINISTRADOR, Rol.COORDINADOR, Rol.DELEGADO)
    template_name = "core/meta_list.html"
    context_object_name = "metas"

    def get_queryset(self):
        return super().get_queryset().select_related("funcionario", "item", "periodo")


class MetaCreate(AdminCRUD, CreateView):
    model = MetaFuncionario
    form_class = MetaForm
    success_url = reverse_lazy("meta_list")
    mensaje_exito = "Meta definida correctamente."

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["usuario"] = self.request.user
        return kwargs


class MetaUpdate(AdminCRUD, UpdateView):
    model = MetaFuncionario
    form_class = MetaForm
    success_url = reverse_lazy("meta_list")
    mensaje_exito = "Meta actualizada."

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["usuario"] = self.request.user
        return kwargs


class MetaDelete(RolRequeridoMixin, DeleteView):
    model = MetaFuncionario
    roles_permitidos = (Rol.ADMINISTRADOR, Rol.COORDINADOR)
    template_name = "core/confirmar_eliminar.html"
    success_url = reverse_lazy("meta_list")


# ------------------------------------------------------------------ actividades
class ActividadList(LoginRequiredMixin, ListView):
    model = Actividad
    template_name = "core/actividad_list.html"
    context_object_name = "actividades"
    paginate_by = 20

    def get_queryset(self):
        qs = Actividad.objects.select_related("item", "funcionario").prefetch_related("evidencias")
        usuario = self.request.user
        # Cada funcionario ve lo suyo; jefatura y verificador, su delegación (RNF-05).
        if usuario.tiene_rol(Rol.FUNCIONARIO):
            qs = qs.filter(funcionario=usuario)
        elif usuario.tiene_rol(Rol.DELEGADO, Rol.VERIFICADOR) and usuario.delegacion_id:
            qs = qs.filter(funcionario__delegacion_id=usuario.delegacion_id)
        return qs


class ActividadCreate(LoginRequiredMixin, MensajeMixin, CreateView):
    model = Actividad
    form_class = ActividadForm
    template_name = "core/actividad_form.html"
    mensaje_exito = "Actividad registrada. Ahora puedes adjuntar la evidencia."

    def get_initial(self):
        datos = super().get_initial()
        tarea = Compromiso.objects.filter(pk=self.request.GET.get('tarea'), responsable=self.request.user,
                                         hito__isnull=False).first() if self.request.GET.get('tarea', '').isdigit() else None
        if tarea:
            datos.update(tarea_hito=tarea.pk, hito=tarea.hito_id, origen='INT', solicitud=tarea.descripcion)
        from .models import AtencionCiudadana
        atencion = AtencionCiudadana.objects.filter(pk=self.request.GET.get('atencion'), responsable=self.request.user).first() if self.request.GET.get('atencion', '').isdigit() else None
        if atencion:
            datos.update(atencion=atencion.pk, vecino=atencion.vecino_id, contacto_nombre=atencion.solicitante,
                         contacto_telefono=atencion.telefono, solicitud=atencion.descripcion)
        return datos

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["usuario"] = self.request.user
        return kwargs

    def get_success_url(self):
        return reverse_lazy("actividad_detalle", kwargs={"pk": self.object.pk})


class ActividadUpdate(LoginRequiredMixin, MensajeMixin, UpdateView):
    model = Actividad
    form_class = ActividadForm
    template_name = "core/actividad_form.html"
    mensaje_exito = "Actividad actualizada."

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["usuario"] = self.request.user
        return kwargs

    def get_queryset(self):
        # Solo se edita lo propio, salvo coordinación.
        if self.request.user.es_coordinacion:
            return Actividad.objects.all()
        return Actividad.objects.filter(funcionario=self.request.user)

    def get_success_url(self):
        return reverse_lazy("actividad_detalle", kwargs={"pk": self.object.pk})


class ActividadDelete(LoginRequiredMixin, DeleteView):
    model = Actividad
    template_name = "core/confirmar_eliminar.html"
    success_url = reverse_lazy("actividad_list")

    def get_queryset(self):
        if self.request.user.es_coordinacion:
            return Actividad.objects.all()
        return Actividad.objects.filter(funcionario=self.request.user)

    def form_valid(self, form):
        try:
            self.get_object().validar_semana()
        except ValidationError as exc:
            messages.error(self.request, ' '.join(exc.messages))
            return redirect('actividad_list')
        if self.get_object().evidencias.filter(estado=Evidencia.APROBADA).exists():
            messages.error(self.request, "No se puede eliminar: la actividad ya tiene evidencia aprobada.")
            return redirect("actividad_list")
        if ReclamoFelicitacion.objects.filter(actividad=self.get_object()).exists():
            messages.error(self.request, 'La actividad respalda un registro ciudadano y debe conservarse.')
            return redirect('actividad_list')
        messages.success(self.request, "Actividad eliminada.")
        return super().form_valid(form)


class ActividadDetalle(LoginRequiredMixin, DetailView):
    model = Actividad
    template_name = "core/actividad_detalle.html"
    context_object_name = "actividad"

    def get_queryset(self):
        from .comunidad_forms import alcance
        qs = alcance(self.request.user, Actividad.objects.all(), 'funcionario__delegacion_id')
        if self.request.user.tiene_rol(Rol.FUNCIONARIO):
            qs = qs.filter(funcionario=self.request.user)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault("form_evidencia", EvidenciaForm())
        return ctx

    def post(self, request, *args, **kwargs):
        """Carga de la evidencia desde el detalle de la actividad (RF-04)."""
        self.object = self.get_object()
        if self.object.funcionario_id != request.user.pk and not (request.user.es_coordinacion or request.user.is_superuser):
            raise PermissionDenied
        try:
            self.object.validar_semana()
        except ValidationError as exc:
            messages.error(request, ' '.join(exc.messages))
            return redirect('actividad_detalle', pk=self.object.pk)
        form = EvidenciaForm(request.POST, request.FILES)
        if form.is_valid():
            evidencia = form.save(commit=False)
            evidencia.actividad = self.object
            evidencia.save()
            messages.success(request, f"Evidencia {evidencia.codigo} cargada. Queda pendiente de verificación.")
            return redirect("actividad_detalle", pk=self.object.pk)
        return self.render_to_response(self.get_context_data(form_evidencia=form))


# ------------------------------------------------------------------- evidencias
class BandejaVerificacion(RolRequeridoMixin, ListView):
    """Cola de evidencias pendientes (CU-08)."""

    model = Evidencia
    roles_permitidos = (Rol.VERIFICADOR, Rol.COORDINADOR, Rol.ADMINISTRADOR)
    template_name = "core/verificacion_list.html"
    context_object_name = "evidencias"

    def get_queryset(self):
        qs = Evidencia.objects.filter(estado=Evidencia.PENDIENTE).select_related(
            "actividad", "actividad__funcionario", "actividad__item")
        usuario = self.request.user
        if usuario.tiene_rol(Rol.VERIFICADOR) and usuario.delegacion_id:
            qs = qs.filter(actividad__funcionario__delegacion_id=usuario.delegacion_id)
        return qs


class VerificarEvidencia(RolRequeridoMixin, DetailView):
    model = Evidencia
    roles_permitidos = (Rol.VERIFICADOR, Rol.COORDINADOR, Rol.ADMINISTRADOR)
    template_name = "core/verificacion_detalle.html"
    context_object_name = "evidencia"

    def get_queryset(self):
        from .comunidad_forms import alcance
        return alcance(self.request.user, super().get_queryset(), 'actividad__funcionario__delegacion_id')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault("form", ValidacionForm())
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = ValidacionForm(request.POST, evidencia=self.object, usuario=request.user)
        if form.is_valid():
            validacion = form.save()
            Auditoria.objects.create(
                funcionario=request.user, evento="VALIDAR", entidad="evidencia",
                registro_id=self.object.codigo, detalle=validacion.get_decision_display(),
            )
            if validacion.decision == Evidencia.RECHAZADA:
                Notificacion.objects.create(
                    destinatario=self.object.actividad.funcionario,
                    mensaje=f"Tu evidencia {self.object.codigo} fue rechazada: {validacion.observacion[:120]}",
                )
            messages.success(request, f"Evidencia {self.object.codigo}: {validacion.get_decision_display()}.")
            return redirect("verificacion_list")
        return self.render_to_response(self.get_context_data(form=form))


# ------------------------------------------------------------------ compromisos
class CompromisoList(LoginRequiredMixin, ListView):
    model = Compromiso
    template_name = "core/compromiso_list.html"
    context_object_name = "compromisos"

    def get_queryset(self):
        qs = Compromiso.objects.select_related("delegacion", "responsable")
        usuario = self.request.user
        if not usuario.es_coordinacion and usuario.delegacion_id:
            qs = qs.filter(delegacion_id=usuario.delegacion_id)
        estado = self.request.GET.get("estado")
        return qs.filter(estado=estado) if estado else qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Agrupa por estado para el tablero: Ingresado, Pendiente, En proceso, Realizado.
        ctx["columnas"] = [
            (etiqueta, [c for c in ctx["compromisos"] if c.estado == codigo])
            for codigo, etiqueta in Compromiso.ESTADOS
        ]
        return ctx


class CompromisoCreate(LoginRequiredMixin, MensajeMixin, CreateView):
    model = Compromiso
    form_class = CompromisoForm
    template_name = "core/form.html"
    success_url = reverse_lazy("compromiso_list")
    mensaje_exito = "Compromiso registrado en la agenda colectiva."

    def get_initial(self):
        from .models import Hito
        from .comunidad_forms import alcance
        datos = super().get_initial()
        hito = alcance(self.request.user, Hito.objects.all()).filter(pk=self.request.GET.get('hito')).first() if self.request.GET.get('hito', '').isdigit() else None
        if hito:
            datos.update(hito=hito.pk, delegacion=hito.delegacion_id, territorio=hito.territorio, solicitante='Actividad interna municipal')
        return datos

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["usuario"] = self.request.user
        return kwargs

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        HistorialCompromiso.objects.create(
            compromiso=self.object, estado_anterior="", estado_nuevo=self.object.estado,
            autor=self.request.user, observacion="Creación del compromiso.",
        )
        return respuesta


class CompromisoAlcanceMixin:
    def get_queryset(self):
        from .comunidad_forms import alcance
        return alcance(self.request.user, super().get_queryset())


class CompromisoUpdate(CompromisoAlcanceMixin, LoginRequiredMixin, MensajeMixin, UpdateView):
    model = Compromiso
    form_class = CompromisoForm
    template_name = "core/form.html"
    success_url = reverse_lazy("compromiso_list")
    mensaje_exito = "Compromiso actualizado."

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["usuario"] = self.request.user
        return kwargs


class CompromisoDelete(CompromisoAlcanceMixin, RolRequeridoMixin, DeleteView):
    model = Compromiso
    roles_permitidos = (Rol.ADMINISTRADOR, Rol.COORDINADOR, Rol.DELEGADO)
    template_name = "core/confirmar_eliminar.html"
    success_url = reverse_lazy("compromiso_list")

    def form_valid(self, form):
        if Actividad.objects.filter(tarea_hito=self.get_object()).exists():
            messages.error(self.request, 'La tarea tiene una ejecución registrada y debe conservarse.')
            return redirect('compromiso_list')
        return super().form_valid(form)


class CompromisoDetalle(CompromisoAlcanceMixin, LoginRequiredMixin, DetailView):
    model = Compromiso
    template_name = "core/compromiso_detalle.html"
    context_object_name = "compromiso"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault("form", CambioEstadoForm(initial={"estado": self.object.estado}))
        ctx["historial"] = self.object.historial.select_related("autor")
        return ctx

    def post(self, request, *args, **kwargs):
        """Cambio de estado con historial (RF-09)."""
        self.object = self.get_object()
        form = CambioEstadoForm(request.POST)
        if form.is_valid():
            anterior = self.object.estado
            nuevo = form.cleaned_data["estado"]
            if anterior == nuevo:
                messages.info(request, "El compromiso ya se encuentra en ese estado.")
                return redirect("compromiso_detalle", pk=self.object.pk)
            self.object.estado = nuevo
            self.object.observacion = form.cleaned_data["observacion"]
            self.object.save()
            HistorialCompromiso.objects.create(
                compromiso=self.object, estado_anterior=anterior, estado_nuevo=nuevo,
                autor=request.user, observacion=form.cleaned_data["observacion"],
            )
            messages.success(request, "Estado actualizado y registrado en el historial.")
            return redirect("compromiso_detalle", pk=self.object.pk)
        return self.render_to_response(self.get_context_data(form=form))


# ---------------------------------------------------- reclamos y felicitaciones
class ReclamoAlcanceMixin:
    def get_queryset(self):
        from .comunidad_forms import alcance
        return alcance(self.request.user, super().get_queryset())

    def get_form_kwargs(self):
        return dict(super().get_form_kwargs(), usuario=self.request.user)


class ReclamoList(ReclamoAlcanceMixin, LoginRequiredMixin, ListView):
    model = ReclamoFelicitacion
    template_name = "core/reclamo_list.html"
    context_object_name = "registros"
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().select_related("delegacion", "funcionario")
        tipo = self.request.GET.get("tipo")
        return qs.filter(tipo=tipo) if tipo else qs


class ReclamoCreate(ReclamoAlcanceMixin, LoginRequiredMixin, MensajeMixin, CreateView):
    model = ReclamoFelicitacion
    form_class = ReclamoFelicitacionForm
    template_name = "core/form.html"
    success_url = reverse_lazy("reclamo_list")
    mensaje_exito = "Registro guardado en el canal unificado."

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        # RF-15: al registrar una felicitación se avisa a coordinación.
        if self.object.tipo == ReclamoFelicitacion.FELICITACION:
            for coordinador in Funcionario.objects.filter(rol__codigo=Rol.COORDINADOR, is_active=True):
                Notificacion.objects.create(
                    destinatario=coordinador, registro=self.object,
                    mensaje=f"Nueva felicitación para {self.object.funcionario} ({self.object.delegacion}).",
                )
        return respuesta


class ReclamoUpdate(ReclamoAlcanceMixin, LoginRequiredMixin, MensajeMixin, UpdateView):
    model = ReclamoFelicitacion
    form_class = ReclamoFelicitacionForm
    template_name = "core/form.html"
    success_url = reverse_lazy("reclamo_list")
    mensaje_exito = "Registro actualizado."


class ReclamoDelete(ReclamoAlcanceMixin, RolRequeridoMixin, DeleteView):
    model = ReclamoFelicitacion
    roles_permitidos = (Rol.ADMINISTRADOR, Rol.COORDINADOR)
    template_name = "core/confirmar_eliminar.html"
    success_url = reverse_lazy("reclamo_list")


# ------------------------------------------------------------------ indicadores
class IndicadoresView(RolRequeridoMixin, TemplateView):
    """Resumen por delegación para coordinación y jefaturas (RF-16)."""

    roles_permitidos = (Rol.COORDINADOR, Rol.ADMINISTRADOR, Rol.DELEGADO, Rol.CONSULTA)
    template_name = "core/indicadores.html"

    def get_context_data(self, **kwargs):
        from .comunidad_forms import alcance
        from .indicadores import tablero
        ctx = super().get_context_data(**kwargs)
        periodo_id = self.request.GET.get('periodo', '')
        periodo = Periodo.objects.filter(pk=periodo_id).first() if periodo_id.isdigit() else Periodo.objects.filter(abierto=True).first()
        delegaciones = alcance(self.request.user, Delegacion.objects.filter(activa=True), 'pk')
        datos = tablero(periodo, delegaciones)
        ctx.update(datos, periodo=periodo, periodos=Periodo.objects.all())
        ctx['bajos'] = [p for p in datos['individuales'] if p['semaforo'] in ('rojo', 'ambar')]
        ctx['items_bajos'] = [dict(d, funcionario=p['funcionario']) for p in datos['individuales']
                              for d in p['items'] if d['semaforo'] in ('rojo', 'ambar')]
        ctx['colectivos'] = [('Delegaciones', datos['delegaciones']), ('Equipos por cargo', datos['equipos']),
                             ('Territorios', datos['territorios'])]
        # Conserva los contadores operativos del tablero anterior.
        ctx['operaciones'] = [dict(delegacion=d,
            compromisos=d.compromisos.count(), realizados=d.compromisos.filter(estado=Compromiso.REALIZADO).count(),
            reclamos=d.reclamos.filter(tipo=ReclamoFelicitacion.RECLAMO).count(),
            felicitaciones=d.reclamos.filter(tipo=ReclamoFelicitacion.FELICITACION).count()) for d in delegaciones]
        return ctx


class AuditoriaList(RolRequeridoMixin, ListView):
    model = Auditoria
    roles_permitidos = (Rol.ADMINISTRADOR, Rol.COORDINADOR)
    template_name = "core/auditoria_list.html"
    context_object_name = "eventos"
    paginate_by = 30
