"""
Carga datos de prueba para trabajar el avance:
    python manage.py datos_demo
Crea las 6 delegaciones, roles, cargos, ítems, un período y usuarios de ejemplo.
"""

from datetime import date, timedelta

from django.core.management.base import BaseCommand

from core.models import (Actividad, Cargo, Compromiso, Delegacion, Funcionario, Item,
                         MetaFuncionario, Periodo, Rol)

DELEGACIONES = ["Las Compañías", "La Antena", "La Pampa", "Avenida del Mar", "Centro", "Rural"]

ITEMS_GESTOR_SOCIAL = [
    ("Atención social a usuario presencial", 20, 90),
    ("Visita a terreno", 20, 12),
    ("Entrega de informe", 25, 40),
    ("Entrega de beneficio", 20, 8),
    ("Emergencia", 5, 4),
    ("Soluciones de ingresos al tubo", 10, 20),
]


class Command(BaseCommand):
    help = "Carga datos de prueba del SGR."

    def handle(self, *args, **opciones):
        for nombre in DELEGACIONES:
            Delegacion.objects.get_or_create(nombre=nombre)
        for codigo, _ in Rol.OPCIONES:
            Rol.objects.get_or_create(codigo=codigo)

        cargo, _ = Cargo.objects.get_or_create(nombre="Gestor Social")
        Cargo.objects.get_or_create(nombre="Territorial OO.CC.")
        for nombre, ponderador, _meta in ITEMS_GESTOR_SOCIAL:
            Item.objects.get_or_create(cargo=cargo, nombre=nombre, defaults={"ponderador": ponderador})

        hoy = date.today()
        periodo, _ = Periodo.objects.get_or_create(
            nombre=f"Trimestre {hoy.year}",
            defaults={"fecha_inicio": hoy - timedelta(days=60), "fecha_termino": hoy + timedelta(days=30)},
        )

        companias = Delegacion.objects.get(nombre="Las Compañías")
        usuarios = [
            ("coordinacion", "Coordinación", "Delegaciones", Rol.COORDINADOR, None, None),
            ("camila", "Camila", "Rojas", Rol.FUNCIONARIO, companias, cargo),
            ("pedro", "Pedro", "Tapia", Rol.VERIFICADOR, companias, None),
            ("jorge", "Jorge", "Díaz", Rol.DELEGADO, companias, None),
        ]
        creados = {}
        for username, nombre, apellido, rol_codigo, delegacion, cargo_usuario in usuarios:
            usuario, nuevo = Funcionario.objects.get_or_create(
                username=username,
                defaults={"first_name": nombre, "last_name": apellido,
                          "email": f"{username}@laserena.cl",
                          "rol": Rol.objects.get(codigo=rol_codigo),
                          "delegacion": delegacion, "cargo": cargo_usuario},
            )
            if nuevo:
                usuario.set_password("sgr12345")
                usuario.save()
            creados[username] = usuario

        # Metas de la funcionaria de ejemplo, definidas por coordinación (RF-14).
        for nombre, _pond, valor in ITEMS_GESTOR_SOCIAL:
            MetaFuncionario.objects.get_or_create(
                funcionario=creados["camila"], item=Item.objects.get(cargo=cargo, nombre=nombre),
                periodo=periodo, defaults={"valor_objetivo": valor, "definida_por": creados["coordinacion"]},
            )

        Actividad.objects.get_or_create(
            funcionario=creados["camila"], item=Item.objects.get(cargo=cargo, nombre="Visita a terreno"),
            fecha=hoy - timedelta(days=2),
            defaults={"solicitud": "Vecina solicita retiro de escombros en su vivienda.",
                      "accion": "Se realiza visita en terreno y se deriva a DISERCO.",
                      "tipo_atencion": "Derivaciones"},
        )
        Compromiso.objects.get_or_create(
            delegacion=companias, responsable=creados["camila"],
            descripcion="Retiro de escombros en calle Balmaceda",
            defaults={"territorio": "Latorre", "solicitante": "Junta de vecinos",
                      "fecha_comprometida": hoy + timedelta(days=15), "estado": Compromiso.EN_PROCESO},
        )

        self.stdout.write(self.style.SUCCESS(
            "Datos de prueba cargados. Usuarios: coordinacion, camila, pedro, jorge (contraseña: sgr12345)."))
