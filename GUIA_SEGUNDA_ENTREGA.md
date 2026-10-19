# SGR – Segunda evaluación: instalación y pruebas

Esta es una copia extendida de tu proyecto. No se incluyó la base de datos del ZIP ni carpetas privadas.

## Windows PowerShell (en la carpeta que contiene manage.py)

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py check
python manage.py makemigrations core
python manage.py migrate
python manage.py test core
python manage.py runserver
```

**Haz copia de seguridad de tu `db.sqlite3` antes de migrar** si tienes registros importantes. Los modelos conservan los campos existentes y añaden otros; no borres migraciones anteriores.

Visita `http://127.0.0.1:8000/acceso/`. Si recuperas contraseña, el código se imprime **solo en la terminal de desarrollo** hasta configurar SMTP. Para correo real proporciona variables EMAIL_BACKEND (`django.core.mail.backends.smtp.EmailBackend`), EMAIL_HOST, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD, DEFAULT_FROM_EMAIL y EMAIL_PORT.

Mantenedores nuevos: `/mantenedores/delegaciones/`, `/mantenedores/roles/`, `/mantenedores/items/`, `/mantenedores/tipos/`, `/mantenedores/subatenciones/`. Usuarios: `/funcionarios/` (existente). Atención: `/atenciones/nueva/`.

**Seguridad:** no publiques en AWS con DEBUG=1, secreto por defecto, SQLite sin respaldo ni HTTP. Configura DJANGO_SECRET_KEY, DJANGO_DEBUG=0, DJANGO_ALLOWED_HOSTS y base MySQL, HTTPS, archivos estáticos y correo real antes de desplegar. El código de esta copia no constituye un despliegue AWS ni pruebas de estrés ejecutadas.

**Pendientes de validar en tu equipo:** comprobar migraciones con tu BD local, ejecución de pruebas, filtros en todos los CRUD antiguos, selector de delegación y autorizaciones de todos los módulos heredados, plantillas institucionales según norma gráfica municipal. Las nuevas pantallas son un incremento, no una certificación de cumplimiento completo.
