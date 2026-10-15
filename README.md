# SGR — Sistema de Gestión de Resultados
Delegaciones Municipales de La Serena · Proyecto Integrado (Django + Python)

## Cómo levantarlo en Visual Studio Code

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate         # macOS / Linux

pip install -r requirements.txt
python manage.py migrate
python manage.py datos_demo       # carga datos de prueba
python manage.py runserver
```

Luego abre http://127.0.0.1:8000/

### Usuarios de prueba (contraseña `sgr12345`)

| Usuario | Rol | Para probar |
|---|---|---|
| `coordinacion` | Coordinador | Metas, administración, indicadores |
| `camila` | Funcionaria | Registrar actividades y evidencias |
| `pedro` | Verificador | Aprobar o rechazar evidencias |
| `jorge` | Delegado | Agenda colectiva |

Para entrar al panel de administración de Django:
```bash
python manage.py createsuperuser
```

## Estructura

```
sgr/
├── config/              # configuración del proyecto
│   ├── settings.py      # apps, idioma, AUTH_USER_MODEL, media
│   └── urls.py          # rutas raíz + login/logout
├── core/                # aplicación principal
│   ├── models.py        # 16 modelos con validaciones (clean)
│   ├── forms.py         # ModelForms con validaciones adicionales
│   ├── views.py         # CRUD con vistas basadas en clases
│   ├── urls.py          # rutas de la aplicación
│   ├── admin.py         # panel de administración
│   ├── tests.py         # 13 pruebas de CRUD y validaciones
│   └── management/commands/datos_demo.py
├── templates/           # plantillas HTML (Bootstrap 5)
├── media/               # evidencias fotográficas subidas
└── manage.py
```

## CRUD implementados

Delegaciones · Cargos · Ítems · Períodos · Funcionarios · Metas · Actividades (con evidencias) ·
Compromisos de la agenda colectiva · Reclamos y felicitaciones.

Además: bandeja de verificación de evidencias (CU-08), indicadores por delegación y registro de auditoría.

## Validaciones incluidas

| Validación | Dónde | Requisito |
|---|---|---|
| La suma de ponderadores de un cargo no supera 100% | `Item.clean()` | RF-02 |
| No se registran actividades con fecha futura | `Actividad.clean()` | RF-01 |
| El ítem debe corresponder al cargo del funcionario | `Actividad.clean()` | RF-01 |
| Solicitud y acción con mínimo 10 caracteres | `Actividad.clean()` | RNF-07 |
| Código de evidencia generado automáticamente | `Evidencia.save()` | RF-03 |
| Foto de máximo 10 MB | `EvidenciaForm.clean_archivo()` | RF-04 |
| El rechazo de evidencia exige observación | `Validacion.clean()` | RF-05 |
| Nadie valida su propia evidencia | `Validacion.clean()` | RN-3 |
| Solo coordinación define metas | `MetaFuncionario.clean()` + `MetaForm` | RF-14 |
| Una meta por funcionario, ítem y período | `UniqueConstraint` | RF-10 |
| Compromiso sin responsable o fecha no se guarda | campos obligatorios + `clean()` | RF-08 |
| El responsable debe ser de la misma delegación | `Compromiso.clean()` | RNF-05 |
| Cambio de estado con observación e historial | `CambioEstadoForm` + `HistorialCompromiso` | RF-09 |
| Fecha de término posterior al inicio | `Periodo.clean()` | RF-12 |
| Correo institucional único | `FuncionarioForm.clean_email()` | RNF-07 |
| Felicitación debe indicar funcionario | `ReclamoFelicitacion.clean()` | RF-13 |

## Pruebas

```bash
python manage.py test core
```

## Cambiar de SQLite a MySQL

En `config/settings.py` está comentada la configuración de MySQL. Al activarla:

```bash
pip install mysqlclient
python manage.py migrate
```
