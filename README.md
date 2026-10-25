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

El incremento de vecinos, organizaciones, hitos, puntuación y ausencias está
documentado en [Requerimientos territoriales](docs/requerimientos_territoriales.md),
incluyendo comparación con lo anterior, reglas, casos de uso, modelo y pruebas.
Al actualizar el proyecto, instala las dependencias y aplica las migraciones:

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
```

El calendario de metas excluye fines de semana y feriados públicos de Chile
(Coquimbo). En Administración → Ítems se configura si cada acción puntúa y si
admite una ejecución final o una felicitación validada. Los módulos nuevos se
acceden desde Vecinos y organizaciones, Hitos y festividades y Ausencias.

```bash
python manage.py test core
```

## Comprobaciones de desarrollo y produccion

Para el entorno local (HTTP y `DEBUG=True`), ejecuta:

```powershell
python manage.py check
```

`check --deploy` revisa la configuracion de produccion. Es normal que muestre
advertencias de HTTPS y DEBUG si se ejecuta con la configuracion local.
Para comprobar el modo de produccion desde PowerShell:

```powershell
$env:DJANGO_DEBUG = '0'
python manage.py check --deploy
```

Con `DJANGO_DEBUG=0` se desactiva DEBUG, se redirige HTTP a HTTPS, se usan
cookies de sesion y CSRF seguras y se habilita HSTS durante una hora.
Usa este modo en un servidor con HTTPS configurado. HSTS no se extiende a
subdominios ni solicita inclusion en listas de precarga.
Por eso pueden aparecer `security.W005` y `security.W021`: esas opciones
requieren comprobar primero HTTPS en todos los subdominios y decidir si se
quiere solicitar la precarga del dominio en los navegadores. No se habilitan
automaticamente para eliminar advertencias.

Antes de publicar, configura `DJANGO_ALLOWED_HOSTS` con los dominios reales
(separados por comas) y `DJANGO_SECRET_KEY` con una clave aleatoria privada,
distinta de la clave de desarrollo incluida en el proyecto. Conserva esa clave
en las variables del servidor, fuera del repositorio. Si usas un proxy que
termina HTTPS, configura el reconocimiento de HTTPS segun tu infraestructura
antes de activar las redirecciones.

Para volver al desarrollo local en la misma terminal:

```powershell
$env:DJANGO_DEBUG = '1'
python manage.py runserver
```

## Cambiar de SQLite a MySQL

En `config/settings.py` está comentada la configuración de MySQL. Al activarla:

```bash
pip install mysqlclient
python manage.py migrate
```
