# Mi Jarvis — asistente personal de escritorio

Asistente para **Windows 10/11** con interfaz gráfica **PySide6**, conversación por **voz continua** y control por **texto**. Lee documentos de Word (`.docx`) y libros de Excel (`.xlsx`/`.xlsm`), responde preguntas sobre su contenido con **Google Gemini**, calcula los datos de Excel en local y en **solo lectura**, habla y transcribe con **ElevenLabs**, puede **abrir archivos que estén en tu carpeta real de Descargas** cuando se lo pides por voz y consulta tu **correo de Gmail y tu Google Calendar en modo de solo lectura** con las API oficiales de Google.

> **Estado:** versión funcional de escritorio. La ventana gráfica es la forma normal de uso; la consola se conserva con `--console`. La integración de **Gmail y Google Calendar (correo y agenda) está implementada y cubierta por pruebas con respuestas simuladas**, pero la conexión con una cuenta real requiere crear una aplicación de escritorio en Google Cloud y **no se ha verificado todavía con una cuenta autenticada**. Los asistentes de Tareas y Reportes **no** están implementados.

---

## Índice

1. [Qué hace](#qué-hace)
2. [Requisitos](#requisitos)
3. [Instalación en Windows PowerShell](#instalación-en-windows-powershell)
4. [Primer arranque y privacidad](#primer-arranque-y-privacidad)
5. [Configuración `.env`](#configuración-env)
6. [Cómo obtener las claves](#cómo-obtener-las-claves)
7. [Formas de inicio](#formas-de-inicio)
8. [La ventana de Jarvis](#la-ventana-de-jarvis)
9. [Micrófono: selección, prueba y permisos](#micrófono-selección-prueba-y-permisos)
10. [Conversación por voz](#conversación-por-voz)
11. [Abrir documentos de Descargas por voz](#abrir-documentos-de-descargas-por-voz)
12. [Documento activo y preguntas](#documento-activo-y-preguntas)
13. [Análisis de Excel en modo solo lectura](#análisis-de-excel-en-modo-solo-lectura)
14. [Correo y agenda de Google en solo lectura](#correo-y-agenda-de-google-en-solo-lectura)
15. [Cómo conectar Gmail y Google Calendar con Jarvis](#cómo-conectar-gmail-y-google-calendar-con-jarvis)
16. [Privacidad: qué datos salen del equipo](#privacidad-qué-datos-salen-del-equipo)
17. [Cómo funciona por dentro](#cómo-funciona-por-dentro)
18. [Pruebas automatizadas](#pruebas-automatizadas)
19. [Qué está verificado y qué no](#qué-está-verificado-y-qué-no)
20. [Errores frecuentes y soluciones](#errores-frecuentes-y-soluciones)
21. [Limitaciones conocidas](#limitaciones-conocidas)
22. [Estructura del proyecto](#estructura-del-proyecto)
23. [Hoja de ruta](#hoja-de-ruta)

---

## Qué hace

- Abre una **ventana de escritorio** con estética oscura (azul marino, cian, azul eléctrico y violeta), un orbe animado y visualizadores conectados a **señales reales** de audio.
- **Escucha de forma continua** después del consentimiento: detecta el inicio y el final de cada frase en local (VAD por energía) y no necesita pulsar un botón para hablar.
- Distingue con honestidad **dispositivo detectado**, **flujo de captura abierto** y **voz detectada**. La cabecera y los estados nunca muestran «ESCUCHANDO» si el micrófono está cerrado.
- **Conversa con voz**: transcripción en vivo, respuesta de Gemini y lectura en voz alta con ElevenLabs. El micrófono se suspende mientras Jarvis habla para no escucharse a sí mismo.
- Transcribe con **Scribe Realtime v2** y cae automáticamente al **modo por lotes** si la conexión en tiempo real no está disponible. Cada intervención produce **una sola** transcripción final.
- **Abre un `.docx` de Descargas por voz**: «abre el documento informe de Descargas». La búsqueda ignora acentos y mayúsculas, y **pregunta cuál abrir** si hay varios parecidos; nunca elige en silencio.
- **Abre y analiza libros de Excel por voz**: «abre el Excel de tareas de Descargas». Admite `.xlsx` y `.xlsm`, localiza encabezados y tablas, y responde con conteos, sumas, filtros, agrupaciones, fechas, fórmulas y calidad de datos **calculados en Python**.
- Trata Word y Excel como **un único recurso activo**: al abrir uno, el otro se descarga y el contexto de las preguntas se reinicia para no mezclar datos.
- **Consulta tu correo de Gmail y tu Google Calendar en solo lectura** con las API oficiales: lista los 20 correos más recientes de la bandeja, abre únicamente el que pides y muestra la agenda de hoy, mañana, la semana laboral o los próximos siete días en tu zona horaria.
- **Nunca envía, responde, marca, mueve ni borra correos, ni crea o modifica eventos.** Solo solicita `gmail.readonly` y `calendar.events.readonly`, y no descarga adjuntos.
- Carga el documento para **resumir, explicar y responder preguntas**, con fuentes por párrafo/tabla y sin inventar datos.
- Mantiene una **conversación libre breve** cuando no hay documento abierto, con historial acotado.
- Permite **escribir** en cualquier momento: si el micrófono falla, no hay claves o rechazas permisos, el modo texto sigue funcionando.
- Guarda tus preferencias (micrófono, escucha automática, lectura en voz alta y permisos) entre sesiones.
- Limpia el audio al cerrar: no quedan micrófonos ni reproducciones activas.

## Requisitos

- **Windows 10 u 11**.
- **Python 3.11 o superior** (probado con 3.12.2).
- Conexión a Internet para Gemini, ElevenLabs y, si lo conectas, las API de Google (Gmail y Calendar).
- Micrófono y altavoces/auriculares para la conversación por voz (opcionales).
- Cuenta gratuita de **Google AI Studio** (Gemini) y, opcionalmente, de **ElevenLabs**.
- Para Gmail y Calendar: una cuenta de Google y un proyecto gratuito en **Google Cloud** con una credencial OAuth de tipo **Aplicación de escritorio**.

Dependencias principales: `google-genai`, `elevenlabs`, `python-docx`, `openpyxl`, `sounddevice`, `python-dotenv`, **`PySide6-Essentials`**, `google-api-python-client`, `google-auth`, `google-auth-httplib2`, `google-auth-oauthlib`, `tzdata` y `pytest`. No se usa NumPy ni `webrtcvad`: el audio se procesa como PCM entero de 16 bits con la biblioteca estándar, y `openpyxl` lee Excel sin automatizar Excel ni ejecutar macros.

## Instalación en Windows PowerShell

```powershell
# 1. Entra en la carpeta del proyecto
cd "C:\Users\sgall\OneDrive\Escritorio\Proyectos\Jarvis"

# 2. Crea el entorno virtual
python -m venv .venv

# 3. Actívalo
.\.venv\Scripts\Activate.ps1

# Si PowerShell bloquea la activación, ejecuta una vez:
# Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# 4. Instala las dependencias
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# 5. Comprueba el entorno (no gasta cuota ni envía datos)
python main.py --check

# 6. Abre la ventana
python main.py
```

> **Ruta demasiado larga (MAX_PATH).** Si `pip` falla al instalar `elevenlabs` con un error `No such file or directory` dentro de `.venv\Lib\site-packages\elevenlabs\...`, es el límite de 260 caracteres de Windows combinado con una ruta larga (por ejemplo, OneDrive). Solución: crea el entorno en una ruta corta y úsalo desde ahí:
>
> ```powershell
> python -m venv C:\venvs\jarvis
> C:\venvs\jarvis\Scripts\Activate.ps1
> python -m pip install -r requirements.txt
> ```
>
> En este equipo `.venv` apunta a una ruta corta y los comandos de arriba funcionan tal cual. No copies `.venv` a otro equipo: créalo de nuevo.

## Primer arranque y privacidad

La primera vez que abres la ventana, Jarvis muestra un diálogo de **consentimiento explícito** antes de crear el controlador:

- Seis casillas, **todas desmarcadas al empezar**:
  1. **Micrófono:** enviar tu voz a ElevenLabs para transcribirla.
  2. **Voz:** enviar el texto de las respuestas a ElevenLabs para leerlo.
  3. **Documentos:** enviar fragmentos del documento a Google Gemini.
  4. **Excel:** enviar tu pregunta y un resumen acotado del libro a Google Gemini para interpretarla o redactar la respuesta.
  5. **Conversación:** enviar tus mensajes a Google Gemini cuando no hay documento.
  6. **Google:** enviar únicamente el correo o los eventos **que ya has seleccionado** a Google Gemini para resumirlos. La consulta del buzón y la agenda con las API de Google no usa Gemini.
- Puedes marcar solo lo que quieras y pulsar **Empezar**.
- **Solo modo texto** deniega todos los permisos, guarda la aceptación, desactiva la escucha automática y la lectura en voz alta, y arranca sin micrófono ni voz.

Después del consentimiento:

1. Jarvis detecta el micrófono y muestra su estado real.
2. Muestra el saludo inicial en la conversación. Si la voz está configurada y autorizada, también lo lee en voz alta.
3. Si **Escucha automática** está activa, abre el micrófono y queda **ESCUCHANDO**.
4. Si está desactivada, solo detecta el dispositivo (estado **EN PAUSA** y micrófono **DETECTADO**) y **no abre el flujo de audio** hasta que pulsas **Activar micrófono**.

Los permisos y preferencias se guardan con `QSettings` en el registro de Windows:

```text
HKEY_CURRENT_USER\Software\MiJarvis\MiJarvis
```

Solo se guardan permisos, dispositivo elegido, geometría de la ventana y preferencias de comportamiento; **nunca claves ni contenido**. Puedes cambiar los permisos desde **Ajustes**. Para repetir el asistente de primer arranque puedes borrar esa clave del registro (opcional):

```powershell
# Solo si quieres que Jarvis vuelva a pedir todos los permisos
Remove-Item -Path "HKCU:\Software\MiJarvis" -Recurse -Force
```

## Configuración `.env`

1. Copia el archivo de ejemplo:

```powershell
Copy-Item .env.example .env
```

2. Abre `.env` y rellena solo lo que tengas:

```dotenv
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.6-flash

ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
ELEVENLABS_STT_MODEL_ID=scribe_v2
ELEVENLABS_REALTIME_MODEL_ID=scribe_v2_realtime
ELEVENLABS_TTS_MODEL_ID=eleven_multilingual_v2
ELEVENLABS_LANGUAGE_CODE=es

JARVIS_SPEAK_RESPONSES=true
JARVIS_STT_MODE=realtime
JARVIS_AUTO_LISTEN=true
JARVIS_INPUT_DEVICE=
JARVIS_LOG_LEVEL=INFO

# Gmail y Google Calendar de solo lectura (opcional)
GOOGLE_OAUTH_CLIENT_FILE=credentials.json
GOOGLE_TIMEZONE=America/Santiago
```

Reglas importantes:

- `.env` está incluido en `.gitignore`: **nunca** se sube al repositorio.
- El código no contiene claves. El identificador de voz tampoco está escrito en el código: se lee de `ELEVENLABS_VOICE_ID`.
- Los valores del entorno del sistema tienen prioridad sobre `.env`.
- Si dejas una clave vacía, esa función queda desactivada y Jarvis lo explica al arrancar; **no se bloquea el modo texto**.
- Si un valor numérico o booleano es inválido, se usa el valor por defecto y se muestra un aviso.
- Una vez guardas preferencias en la ventana, estas tienen prioridad sobre `.env` en ese equipo: micrófono elegido, escucha automática, lectura en voz alta y permisos. Los permisos nuevos se guardan al aceptarlos.

### Variables

| Variable | Obligatoria | Descripción |
|---|---|---|
| `GEMINI_API_KEY` | Sí, para preguntas y resúmenes | Clave de Google AI Studio. |
| `GEMINI_MODEL` | No | Modelo de Gemini. Por defecto `gemini-3.6-flash`. |
| `ELEVENLABS_API_KEY` | Solo para voz | Clave de ElevenLabs. |
| `ELEVENLABS_VOICE_ID` | Solo para leer respuestas | Identificador de la voz. Sin él se transcribe, pero no se habla. |
| `ELEVENLABS_STT_MODEL_ID` | No | Transcripción por lotes. Por defecto `scribe_v2`. |
| `ELEVENLABS_REALTIME_MODEL_ID` | No | Transcripción en tiempo real. Por defecto `scribe_v2_realtime`. |
| `ELEVENLABS_TTS_MODEL_ID` | No | Modelo de voz. Por defecto `eleven_multilingual_v2`. |
| `ELEVENLABS_LANGUAGE_CODE` | No | Idioma de transcripción. Por defecto `es`. |
| `JARVIS_MAX_CONTEXT_CHARS` | No | Máximo de caracteres de documento enviados a Gemini por consulta. |
| `JARVIS_MAX_CHUNK_BATCH_CHARS` | No | Tamaño de cada lote al resumir documentos largos. |
| `JARVIS_CHUNK_SIZE_CHARS` | No | Tamaño objetivo de cada fragmento. |
| `JARVIS_MAX_RECORD_SECONDS` | No | Límite de duración de una grabación (consola). |
| `JARVIS_SAMPLE_RATE` | No | Frecuencia de trabajo de la captura (16 kHz por defecto). |
| `JARVIS_SPEAK_RESPONSES` | No | `true`/`false`: leer las respuestas en voz alta. |
| `JARVIS_STT_MODE` | No | `realtime` (con respaldo automático) o `batch`. |
| `JARVIS_AUTO_LISTEN` | No | `true`/`false`: abrir el micrófono al arrancar. |
| `JARVIS_INPUT_DEVICE` | No | Micrófono recordado: `Host API\|Nombre\|índice` o vacío para el predeterminado. |
| `JARVIS_VAD_MARGIN_DB` | No | Margen de voz sobre el ruido de fondo (por defecto `9`). |
| `JARVIS_VAD_MIN_RMS` | No | Nivel mínimo de voz (por defecto `120`). |
| `JARVIS_SILENCE_MS` | No | Silencio que cierra una frase (por defecto `850`). |
| `JARVIS_PREROLL_MS` | No | Audio previo que se conserva (por defecto `300`). |
| `JARVIS_MIN_SPEECH_MS` | No | Duración mínima de una frase (por defecto `250`). |
| `JARVIS_GREETING` | No | Saludo inicial; se muestra siempre y se habla si hay voz. |
| `JARVIS_DOWNLOADS_MAX_DEPTH` | No | Subcarpetas que se revisan en Descargas (por defecto `3`). |
| `JARVIS_DOWNLOADS_MAX_FILES` | No | Archivos máximos revisados por búsqueda (por defecto `2000`). |
| `JARVIS_SPREADSHEET_MAX_FILE_MB` | No | Tamaño máximo de un libro `.xlsx`/`.xlsm` (por defecto `25` MB). |
| `JARVIS_SPREADSHEET_MAX_ROWS` | No | Filas máximas por hoja (por defecto `10000`). |
| `JARVIS_SPREADSHEET_MAX_COLUMNS` | No | Columnas máximas por hoja (por defecto `60`). |
| `JARVIS_SPREADSHEET_MAX_CELLS` | No | Celdas máximas procesadas por hoja (por defecto `300000`). |
| `JARVIS_SPREADSHEET_MAX_QUERY_ROWS` | No | Filas máximas devueltas por una consulta (por defecto `10000`). |
| `JARVIS_SPREADSHEET_MAX_CONTEXT_CHARS` | No | Contexto máximo de Excel enviado a Gemini (por defecto `6000`). |
| `JARVIS_SPREADSHEET_HEADER_SCAN_ROWS` | No | Filas iniciales examinadas para localizar el encabezado (por defecto `12`). |
| `JARVIS_SPREADSHEET_TIMEOUT_S` | No | Tiempo máximo de una consulta de Excel en segundos (por defecto `20`). |
| `GOOGLE_OAUTH_CLIENT_FILE` | Solo para Gmail y Calendar | Ruta del JSON de la aplicación OAuth de escritorio. Por defecto `credentials.json`. Sin archivo válido, GOOGLE CONNECT queda desactivado. |
| `GOOGLE_TIMEZONE` | No | Zona horaria para mostrar eventos. Por defecto `America/Santiago`; si no es válida, se usa esa y se avisa. |
| `JARVIS_LOG_LEVEL` | No | `DEBUG`, `INFO`, `WARNING`, `ERROR`. |

## Cómo obtener las claves

### Google Gemini

1. Entra en <https://aistudio.google.com/apikey> con tu cuenta de Google.
2. Crea una **API key** y cópiala en `GEMINI_API_KEY`.
3. El modelo inicial es `gemini-3.6-flash`. Si tu cuenta no lo tiene disponible o devuelve **503 por alta demanda**, cambia `GEMINI_MODEL` por otro modelo con **nivel gratuito**.
4. **No** actives facturación: Jarvis no la necesita y no la configura. Si aparece un error 429, es cuota agotada: espera o revisa tu plan en AI Studio.

> Aviso: en el nivel gratuito, Google puede usar el contenido enviado para mejorar sus productos. No uses documentos laborales confidenciales con esta configuración.

### ElevenLabs

1. Crea una cuenta en <https://elevenlabs.io>.
2. Copia tu **API key** desde el panel de la cuenta en `ELEVENLABS_API_KEY`.
3. Copia en `ELEVENLABS_VOICE_ID` el **Voice ID** de una voz de tu cuenta. En el **plan gratuito** deben ser voces **premade**: las voces de biblioteca o de categoría *professional* devuelven el error 402 `paid_plan_required` al usarlas por API.
4. Los modelos iniciales son `scribe_v2` / `scribe_v2_realtime` (transcripción) y `eleven_multilingual_v2` (voz). Se pueden cambiar por `.env`.

Sin clave de ElevenLabs, Jarvis arranca y funciona por texto; el micrófono y la voz quedan desactivados.

## Formas de inicio

```powershell
# Inicio normal: abre la ventana gráfica
python main.py

# Abrir directamente un documento al arrancar la ventana
python main.py --document "C:\ruta\al\manual.docx"

# Abrir directamente un libro de Excel al arrancar la ventana
python main.py --document "C:\ruta\al\libro.xlsx"

# Consola clásica (sin Qt)
python main.py --console

# Consola con un documento concreto
python main.py --console --document "C:\ruta\al\manual.docx"

# Forzar respuestas solo en pantalla (sin lectura en voz alta)
python main.py --no-voice

# Comprobar dependencias, claves, ventana y micrófono sin iniciar sesión
python main.py --check

# Ver la versión
python main.py --version
```

`--no-voice` desactiva la **lectura en voz alta** de las respuestas, pero no impide usar el micrófono para hablar si hay claves y permiso. Si lo que quieres es no abrir el micrófono, usa `--console` en modo texto, desactiva la escucha automática en Ajustes o pausa el micrófono al arrancar.

> La consola clásica (`--console`) sigue centrada en documentos de Word. El análisis de Excel está disponible en la ventana gráfica.

## La ventana de Jarvis

La ventana tiene seis zonas:

1. **Cabecera**
   - Título y estado real del asistente.
   - Indicadores honestos: `GEMINI`, `VOZ`, `MIC` y `STT`. Muestran «SIN CLAVE», «PAUSA», «ERROR», «DETECTADO», «ESCUCHANDO» o el modo de transcripción real (`REALTIME`/`BATCH`).
   - Botones **Ayuda** y **Ajustes**.
2. **Orbe central**
   - Cambia de color según el estado y late con el nivel real del micrófono o de la voz.
   - Gira un arco mientras procesa.
3. **TU VOZ**
   - Barras de nivel del micrófono y **transcripción parcial en vivo**.
4. **JARVIS**
   - Barras del audio que se está reproduciendo y subtítulo del estado de la voz.
5. **Conversación y recurso activo**
   - Mensajes con hora, autor y fuentes (`P#`/`T#`).
   - Tarjeta del **documento activo** con párrafos, tablas, encabezados y caracteres, o tarjeta del **libro activo** con hojas, filas, columnas, fórmulas y tablas.
   - Panel de **resultado del análisis** con métricas, tabla, fuentes y avisos de calidad.
   - Sección **GOOGLE CONNECT** con el estado de Gmail y Google Calendar, cuenta conectada y última consulta.
   - Lista de candidatos cuando hay ambigüedad.
6. **Controles**
   - Pausar/reanudar micrófono, detener voz, probar micrófono.
   - Selector de dispositivo y botón de actualización.
   - Cuadro de texto y botón **Enviar**.
   - Avisos y pista de estado.

### Estados

| Estado | Significado |
|---|---|
| `INICIANDO` | Comprobando configuración, consentimiento y micrófono. |
| `PREPARADO` | Listo para texto o para activar el micrófono. |
| `ESCUCHANDO` | Flujo de captura abierto y sin voz detectada. |
| `TE ESCUCHO` | Voz detectada ahora mismo. |
| `PROCESANDO` | Transcribiendo o consultando a Gemini. |
| `HABLANDO` | Reproduciendo una respuesta de voz. |
| `EN PAUSA` | El usuario pausó la escucha o desactivó el micrófono. |
| `ERROR` | Fallo de audio, red o proveedor; se muestra el motivo. |

Las transiciones se validan contra una tabla. La interfaz nunca muestra «ESCUCHANDO» mientras el micrófono está en pausa, cerrado o en error.

### Atajos

| Atajo | Acción |
|---|---|
| `Ctrl+M` | Pausar o reanudar la escucha. |
| `Ctrl+.` | Detener la voz de Jarvis. |
| `Ctrl+T` | Probar el micrófono dos segundos. |
| `Ctrl+O` | Elegir un documento de Word o un libro de Excel manualmente. |
| `Ctrl+,` | Abrir Ajustes. |
| `F1` | Ayuda y atajos. |
| `Esc` | Detener la voz. |

### Controles y comportamiento

- **Pausar escucha** cierra la captura y descarta lo pendiente; **Reanudar** vuelve a abrir el micrófono y pide permiso si aún no lo tenías.
- **Detener voz** corta la reproducción de inmediato y devuelve el estado a escucha.
- **Probar micrófono** graba dos segundos y mide el nivel real. El resultado distingue «se recibió audio» de «no se detectó voz».
- **Detente**, **pausa**, **reanuda** y **cancela** funcionan también por voz o texto.
- Los turnos se procesan **en serie**: una frase nueva espera a que termine la anterior y nunca se solapan dos respuestas.
- Las órdenes duplicadas se descartan en una ventana corta, y una respuesta pendiente se invalida si pausas, cancelas o cierras.
- Al cerrar la ventana se cierra el micrófono, se detiene la voz y no queda ningún hilo de audio activo.

## Micrófono: selección, prueba y permisos

### Selección

- Jarvis enumera los dispositivos de entrada reales de Windows (MME, WASAPI, DirectSound, etc.).
- El selector muestra el nombre y la API de host. **Predeterminado del sistema** usa el dispositivo configurado en Windows.
- El dispositivo elegido se guarda en `QSettings` y se aplica **inmediatamente**, sin reiniciar.
- La captura usa la **frecuencia nativa** del dispositivo y remuestrea a 16 kHz con DSP propio si es necesario. No se fuerza una frecuencia que el dispositivo no admita.

### Prueba

1. Pulsa **Probar micrófono** (o `Ctrl+T`).
2. Habla durante dos segundos.
3. Si el nivel máximo llega al umbral, verás «El micrófono funciona» con el nivel medido.
4. Si no, verás «No se detectó voz» y una sugerencia de revisar el dispositivo o los permisos.

La prueba usa el mismo flujo de captura que la conversación: si la transcripción está activa, el audio también puede enviarse a ElevenLabs como en cualquier turno. El **resultado** de la prueba se calcula localmente midiendo el nivel.

### Permisos de Windows

Si el micrófono no aparece, aparece pero no entrega audio, o Windows lo bloquea:

1. Abre **Configuración**.
2. Entra en **Privacidad y seguridad → Micrófono**.
3. Activa **Acceso al micrófono**.
4. Activa **Permitir que las aplicaciones de escritorio accedan al micrófono**.
5. Comprueba que la aplicación de terminal o Python no esté bloqueada en la lista.
6. Vuelve a Jarvis y pulsa **↻** para actualizar la lista o **Probar micrófono**.

También ayuda:

- Cerrar otras aplicaciones que estén usando el micrófono (Teams, Zoom, OBS…).
- Elegir explícitamente el micrófono correcto en el selector.
- Revisar el silenciador físico del micrófono o de los auriculares.
- En portátiles, comprobar que el micrófono interno no esté desactivado en el panel de sonido.

### Si el micrófono falla

Jarvis muestra el error, deja el estado en **PREPARADO** o **ERROR** de forma coherente y mantiene el **modo texto**. Nunca simula que está escuchando. Puedes cambiar de dispositivo, probar de nuevo o escribir la orden.

## Conversación por voz

1. Con el micrófono activo, verás **ESCUCHANDO**.
2. Al empezar a hablar, el estado pasa a **TE ESCUCHO** y la transcripción parcial aparece en **TU VOZ**.
3. Cuando haces una pausa (850 ms por defecto), la frase se cierra y pasa a **PROCESANDO**.
4. La transcripción final se envía a Gemini (o al asistente del documento) y la respuesta aparece en la conversación.
5. Si la voz está configurada y autorizada, Jarvis habla con ElevenLabs; mientras habla, el micrófono se suspende para evitar eco.
6. Al terminar, vuelve a **ESCUCHANDO** automáticamente.

La detección de voz es **local** y se basa en energía con adaptación al ruido de fondo. El audio solo se envía a ElevenLabs mientras la escucha está activa: en tiempo real, por fragmentos continuos; en modo por lotes, al cerrarse la frase. No se envía si el micrófono está en pausa, cerrado o si Jarvis está hablando.

### Ejemplos

```text
Hola Jarvis
¿Cómo estás?
Abre el documento informe de Descargas
Abre el manual
Resume el documento
Resume la sección 2
Explícame el objetivo principal
Extrae las fechas y plazos
Lista las acciones pendientes
Enumera las responsabilidades
Muéstrame las conclusiones
Pausa
Reanuda
Detente
Cancela
Ayuda
```

### Transcripción en tiempo real y respaldo

- Con `JARVIS_STT_MODE=realtime`, Jarvis intenta **Scribe Realtime v2**.
- Si la conexión no se establece, se pierde o el servidor no responde a tiempo, usa automáticamente el **modo por lotes** (`scribe_v2`) y lo avisa.
- Cada intervención entrega **una sola transcripción final**, aunque lleguen resultados parciales o tardíos.
- El indicador `STT` de la cabecera muestra el modo que se está usando de verdad.

### Voz de las respuestas

- La síntesis usa `eleven_multilingual_v2` y reproduce PCM a 16 kHz por los altavoces.
- El botón **Detener voz**, la orden «detente» y `Ctrl+.` cortan la reproducción.
- Si no hay voz configurada, la respuesta queda solo en pantalla.
- Si el plan de ElevenLabs no permite la voz elegida (402), Jarvis lo explica y sugiere una voz **premade**.

## Abrir documentos de Descargas por voz

Jarvis localiza la carpeta **real** de Descargas de Windows (`FOLDERID_Downloads`), no una ruta escrita a mano en el código.

Puedes decir, por ejemplo:

```text
Abre el documento informe de Descargas
Abre el manual
Abre el archivo presupuesto
Abre el documento de recursos humanos
Abre el Excel de tareas de Descargas
Abre el libro seguimiento mensual
```

Reglas de seguridad y precisión:

- Solo considera archivos **`.docx`, `.xlsx` y `.xlsm`**. No abre PDF, `.doc`, imágenes ni ejecutables.
- Busca en Descargas y subcarpetas con límites (profundidad 3 y 2000 archivos por defecto).
- La coincidencia **ignora acentos, mayúsculas y signos**: «presupuesto», «PRESUPUESTO» y «presupueto» pueden acercarse al mismo archivo.
- Si hay una coincidencia clara, abre el archivo con la aplicación predeterminada de Windows y lo carga para consultas.
- Si hay **varios candidatos parecidos**, muestra la lista y pregunta cuál abrir. Puedes responder con el número («el segundo»), con el nombre o pulsar el botón correspondiente.
- **Nunca** elige uno en silencio ni inventa una ruta.
- **Nunca** ejecuta comandos del sistema ni acepta rutas generadas por el modelo.
- Si el archivo no se puede abrir en Word (por ejemplo, Word no está instalado), Jarvis puede cargarlo igualmente para leerlo y lo indica.

También puedes elegir un archivo manualmente con **Elegir Word o Excel** o `Ctrl+O`. El selector empieza en tu carpeta de Descargas.

## Documento activo y preguntas

Con un documento cargado puedes pedir:

| Acción | Cómo pedirla |
|---|---|
| Preguntar | Cualquier pregunta sobre el documento |
| Resumen general | `resumen`, `resume el documento` |
| Resumen de sección | `resume la sección 2`, `resumen del apartado de responsabilidades` |
| Explicación breve | `explícame el objetivo`, `explícame el segundo apartado` |
| Fechas y plazos | `extrae las fechas`, `fechas` |
| Acciones | `lista las acciones`, `acciones` |
| Responsabilidades | `enumera las responsabilidades` |
| Conclusiones | `muéstrame las conclusiones` |
| Cambiar documento | `documento`, `cambiar documento`, `quiero otro documento` |

- Las respuestas se basan **solo en fragmentos del documento** seleccionados localmente por relevancia (TF-IDF).
- Cada respuesta indica sus fuentes por párrafo/tabla y encabezado; no se inventan números de página.
- Si el documento no contiene el dato, Jarvis lo dice explícitamente en lugar de inventarlo.
- El texto del documento se trata como **material no confiable**: si contiene instrucciones ocultas, no se obedecen.
- Cuando no hay documento, una pregunta libre se responde con Gemini usando un historial breve y acotado (últimos turnos, máximo ~3500 caracteres).
- El asistente documental y el chat usan **Gemini**; sin clave o sin consentimiento, Jarvis explica qué falta y mantiene las funciones locales.

## Análisis de Excel en modo solo lectura

Jarvis puede analizar libros **`.xlsx`** y **`.xlsm`** (Excel 2007 o posterior) sin modificarlos. Excel y Word comparten un **único recurso activo**: al abrir un libro, el documento de Word se descarga; al abrir un Word, el libro se cierra. Así las preguntas siempre se refieren a un solo recurso.

### Abrir un libro

```text
Abre el Excel de tareas de Descargas
Abre el libro seguimiento mensual
Busca la planilla de gastos.xlsx
```

La búsqueda funciona igual que con Word: carpeta real de Descargas y subcarpetas, sin distinguir acentos, mayúsculas ni extensión. Si hay varios libros parecidos, muestra las alternativas y **pregunta cuál abrir**. También puedes elegir el archivo con **Elegir Word o Excel** o `Ctrl+O`.

Al abrirlo, Jarvis:

1. Valida que sea un libro `.xlsx`/`.xlsm` legible.
2. Localiza encabezados (no necesariamente en la fila 1), tablas formales y rangos de datos.
3. Identifica hojas visibles y ocultas, columnas, tipos y fórmulas.
4. Lo abre con la aplicación predeterminada de Windows.
5. Actualiza la tarjeta **LIBRO ACTIVO** y responde «He abierto y cargado el libro…».

### Seguridad y solo lectura

- Nunca guarda, edita ni borra celdas o archivos.
- Nunca ejecuta macros: un `.xlsm` se lee como datos, no como código.
- Nunca evalúa fórmulas ni ejecuta código incrustado en celdas.
- No recalcula el libro: lee las fórmulas y, si existe, el último resultado guardado por Excel.
- No sigue enlaces externos ni descarga nada.
- Trata el contenido del libro como **material no confiable**: si una celda contiene instrucciones, se ignoran.
- Las hojas ocultas se listan, pero **no se mezclan** en los análisis salvo que las pidas expresamente.

### Preguntas que entiende

Los cálculos se hacen siempre en **Python**, de forma determinista:

| Tipo | Ejemplos |
|---|---|
| Conteo y totales | «¿Cuántas tareas hay?», «Suma el importe», «Promedio de avance» |
| Mínimos y máximos | «¿Cuál es el importe máximo?» |
| Porcentajes y distintos | «¿Qué porcentaje está pendiente?», «¿Cuántas áreas distintas hay?» |
| Filtros | «Tareas de Gestión», «Pendientes de Ana», «Importe mayor que 1000» |
| Filtros combinados y fechas | «Pendientes de Gestión en octubre», «Entre el 1 y el 30 de noviembre» |
| Agrupaciones | «Agrupa por área», «Cuenta por estado», «Suma por responsable», «Por mes» |
| Comparaciones | «Compara Gestión con Operaciones» |
| Vencimientos | «¿Cuántas están vencidas?», «¿Qué vence en los próximos 7 días?» |
| Fechas ausentes | «¿Qué registros no tienen fecha límite?» |
| Duplicados y listados | «Busca duplicados», «Lista las tareas de Ventas» |
| Calidad de datos | «Revisa la calidad de los datos» |
| Fórmulas | «Explícame la fórmula de la columna Cálculo», «¿Qué fórmulas hay?» |
| Resumen y prioridades | «Resume la hoja Tareas», «¿Qué debería revisar primero?» |

Cada respuesta indica su origen, por ejemplo `Fuente: hoja Tareas, rango A3:M31`. Si la respuesta combina varias hojas, se citan todas. Cuando el dato no existe o falta un resultado, Jarvis lo dice con honestidad en lugar de inventarlo. Si la pregunta no nombra una hoja y hay varias con datos, muestra las alternativas en lugar de elegir una.

### Fórmulas y resultados cacheados

- Se leen las fórmulas reales (`data_only=False`) y, por separado, los valores que Excel guardó al calcular (`data_only=True`).
- Se reconocen y explican funciones localizadas en español: `SI`, `Y`, `O`, `BUSCARV`, `BUSCARX`, `SUMA`, `PROMEDIO`, `CONTAR`, `CONTARA`, `CONTAR.SI`, `SUMAR.SI`, `SI.ERROR`, `CONCATENAR`, funciones de fecha y combinaciones.
- Si el archivo no tiene resultado cacheado para una celda (por ejemplo, lo generó una herramienta que no lo calculó), Jarvis explica la fórmula y avisa de que debe abrirse y guardarse en Excel para actualizar los resultados. **No inventa el resultado ni recalcula.**

### Calidad de datos

El diagnóstico señala, entre otros:

- celdas vacías en columnas clave,
- registros duplicados,
- fechas guardadas como texto o con formatos inconsistentes,
- números guardados como texto,
- encabezados repetidos o sin nombre,
- filas completamente vacías dentro de los datos,
- columnas con tipos mezclados o posible error de captura.

### Contexto de seguimiento

Mientras el mismo libro siga activo, puedes encadenar preguntas: «¿Cuántas tareas están vencidas?» y después «¿Y cuántas corresponden a Gestión?». Jarvis conserva las últimas consultas y la hoja activa. Al cambiar de libro (o al abrir un Word), el contexto se reinicia para no mezclar datos.

### Límites y rendimiento

Los valores por defecto protegen la memoria y el tiempo de respuesta:

| Variable | Por defecto | Efecto |
|---|---|---|
| `JARVIS_SPREADSHEET_MAX_FILE_MB` | `25` | Tamaño máximo del archivo. |
| `JARVIS_SPREADSHEET_MAX_ROWS` | `10000` | Filas leídas por hoja. |
| `JARVIS_SPREADSHEET_MAX_COLUMNS` | `60` | Columnas leídas por hoja. |
| `JARVIS_SPREADSHEET_MAX_CELLS` | `300000` | Celdas procesadas por hoja. |
| `JARVIS_SPREADSHEET_MAX_QUERY_ROWS` | `10000` | Filas devueltas por una consulta. |
| `JARVIS_SPREADSHEET_MAX_CONTEXT_CHARS` | `6000` | Contexto máximo enviado a Gemini. |
| `JARVIS_SPREADSHEET_HEADER_SCAN_ROWS` | `12` | Filas iniciales examinadas para el encabezado. |
| `JARVIS_SPREADSHEET_TIMEOUT_S` | `20` | Tiempo máximo de una consulta. |

Si el libro supera un límite, Jarvis avisa de que el **análisis es parcial** y no pretende haber leído todo.

### Formatos no admitidos

Solo se admiten `.xlsx` y `.xlsm`. Los formatos antiguos `.xls` y binarios `.xlsb` necesitan una dependencia opcional que no está verificada en este proyecto: Jarvis te pedirá que abras el libro en Excel y lo guardes como `.xlsx`.

### Gemini en Excel

Gemini actúa solo como **intérprete del lenguaje** (elegir hoja, columna u operación) y como **redactor** de la explicación a partir de hechos ya calculados. Nunca calcula, nunca genera código y nunca ve el libro completo. La primera vez pide un consentimiento específico (**Excel**) distinto del de Word; si lo rechazas, las consultas deterministas y los cálculos locales siguen funcionando.

## Correo y agenda de Google en solo lectura

Jarvis se conecta **directamente a las API de Gmail y Google Calendar** con las bibliotecas oficiales `google-api-python-client` y `google-auth`. No usa navegador automatizado, Selenium, Playwright, scraping de HTML, IMAP/SMTP, contraseñas ni servicios intermediarios. La autenticación es **OAuth 2.0 de escritorio con PKCE**: al conectar se abre el navegador predeterminado, autorizas la cuenta y Google redirige a un servidor local efímero. Jarvis no pide ni guarda tu contraseña. El token se guarda cifrado con **DPAPI** de Windows o, si el cifrado no está disponible, solo en memoria.

### Qué puede hacer

| Servicio | Consulta | Límites |
|---|---|---|
| **Correo** | Lista los **20 correos más recientes** de la bandeja de entrada (`INBOX`), ordenados del más nuevo al más antiguo, con remitente, asunto, fecha, fragmento, estado de lectura, importancia y adjuntos. | Los metadatos se piden con `users.messages.get(format="metadata")`; solo se descarga el cuerpo del correo que eliges, con `format="full"`. |
| **Correo** | Dice cuántos hay, cuántos están sin leer, cuántos son de importancia alta y cuántos tienen adjuntos. | No descarga adjuntos, no marca como leído, no mueve ni borra. |
| **Agenda** | Hoy, mañana, la semana laboral (lunes a viernes), los **próximos siete días** o un día concreto de la semana. | Usa `events.list` con `calendarId="primary"`, `singleEvents=True` y `orderBy="startTime"`, que resuelve las ocurrencias de eventos recurrentes. |

- Gmail procesa mensajes **multipart**, **HTML** y **Base64 URL-safe**; el HTML se convierte a **texto legible** y la ventana nunca muestra etiquetas HTML.
- Los eventos se solicitan en la zona `GOOGLE_TIMEZONE` y se convierten con `zoneinfo`. **Nunca se presenta una hora UTC como si fuera local**, y los eventos de día completo se muestran como «todo el día».
- El correo y la agenda tienen **contextos separados**. Un seguimiento como «¿quién lo envió?» se aplica al correo mostrado; «¿dónde es la reunión?» se aplica a la agenda. Al cambiar de servicio, el contexto anterior se descarta.
- **No se carga el buzón al arrancar** ni se sincroniza en segundo plano. Cada consulta nace de una orden, un botón o una pregunta de seguimiento.
- La lista usa paginación (`nextPageToken`) hasta completar el límite de 20 correos o de eventos, sin bucles infinitos.

### Órdenes que entiende

```text
Revisa mis correos
¿Cuántos correos tengo sin leer?
Lee el último correo
Lee el correo de Ana
Busca el correo con asunto presupuesto
¿Quién lo envió?
¿Qué dice el correo?
¿Cuándo lo recibí?
¿Tiene adjuntos?
Resume el correo

Consulta mi agenda de hoy
¿Qué tengo mañana?
Muéstrame las reuniones de esta semana
¿Qué tengo en los próximos siete días?
¿Qué tengo el lunes?
¿Cuál es mi próxima reunión?
¿Dónde es la reunión?
¿Quiénes participan?
Resume la agenda
Estado de Google
Conecta Google
Desconecta Google
```

### Botones de la ventana

La sección **GOOGLE CONNECT** muestra dos tarjetas:

- **CORREO · SOLO LECTURA:** estado real, cuenta conectada, última consulta, cantidad de correos y no leídos.
- **CALENDARIO · SOLO LECTURA:** estado, última consulta, cantidad de eventos y próximo evento.

Incluye **CONECTAR GOOGLE**, **Consultar correos**, **Abrir Gmail**, **Consultar agenda**, **Abrir Google Calendar** y **Desconectar**. Los botones Abrir llevan a <https://mail.google.com/> y <https://calendar.google.com/calendar/>. La autenticación y las consultas se ejecutan **fuera del hilo de Qt**; la ventana solo dibuja el resultado.

Estados del panel: **SIN CONFIGURAR**, **CONFIGURADO · SIN AUTORIZAR**, **CONECTANDO…** y **CONECTADO**. Si falta el archivo de credenciales, el panel explica qué hacer sin bloquear el resto de Jarvis.

### Seguridad y privacidad

- Solo se solicitan los permisos exactos de lectura `https://www.googleapis.com/auth/gmail.readonly` y `https://www.googleapis.com/auth/calendar.events.readonly`. No se piden permisos de envío, escritura, etiquetado ni administración, y el código no descarga adjuntos.
- El cliente de solo lectura expone únicamente cuatro operaciones: perfil de Gmail, lista de mensajes, detalle de un mensaje y lista de eventos. No hay ninguna ruta pública para enviar, modificar, archivar o borrar.
- No se descargan adjuntos ni se marcan correos como leídos: leer un correo no cambia su estado en Gmail.
- El contenido de correos y eventos se trata como **información no confiable**: si un mensaje contiene instrucciones, Jarvis no las obedece.
- No se guardan correos, cuerpos ni eventos en disco. El token se guarda cifrado con DPAPI en `%LOCALAPPDATA%\MiJarvis\google_token_cache.bin`; la desconexión lo borra.
- Al leer con ElevenLabs, Jarvis avisa de que **el texto de la respuesta se transmite al proveedor de voz**, igual que con las respuestas del documento.
- Gemini solo recibe el **correo seleccionado** o los **eventos de la agenda consultada** para resumirlos, nunca el buzón o el calendario completos, y solo si concediste el permiso **Google**.

## Cómo conectar Gmail y Google Calendar con Jarvis

Esta guía crea una aplicación propia de **Google Cloud** para que Jarvis pueda pedir permiso a tu cuenta. Es gratis y no necesitas cuenta de servicio ni contraseña. La conexión real no se puede probar sin completar estos pasos con tu cuenta de Google.

### 1. Crear el proyecto en Google Cloud

1. Entra en <https://console.cloud.google.com/> con la cuenta de Google que quieres conectar.
2. En el selector de proyectos, pulsa **Nuevo proyecto**.
3. Escribe un nombre, por ejemplo `Mi Jarvis`, y pulsa **Crear**.
4. Selecciona ese proyecto antes de continuar.

### 2. Habilitar Gmail API y Google Calendar API

1. Abre **APIs y servicios → Biblioteca**.
2. Busca **Gmail API**, ábrela y pulsa **Habilitar**.
3. Vuelve a la biblioteca, busca **Google Calendar API**, ábrela y pulsa **Habilitar**.
4. Sin estas dos API habilitadas, la conexión puede autorizar la cuenta pero las consultas fallarán con un error 403.

### 3. Configurar la pantalla de consentimiento OAuth

1. Abre **APIs y servicios → Pantalla de consentimiento de OAuth**.
2. Elige **Externo** para una cuenta personal de Gmail, o **Interno** si es una cuenta de Google Workspace de tu organización.
3. Rellena el nombre de la aplicación (`Mi Jarvis`), el correo de asistencia y el correo de contacto del desarrollador. Guarda.
4. En **Permisos o alcances**, añade exactamente:
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/calendar.events.readonly`
5. **No añadas** permisos de envío, modificación, borrado ni acceso completo al calendario.
6. Si la aplicación queda en estado **Prueba** (Testing), abre **Usuarios de prueba** y añade la cuenta de Google que vas a conectar. Sin eso, Google mostrará «Acceso bloqueado».
7. Para uso personal no hace falta publicar la aplicación; si la publicas, Google puede pedir una revisión de los permisos. Jarvis funciona igual en modo Prueba para las cuentas de prueba.

### 4. Crear la credencial OAuth de escritorio

1. Abre **APIs y servicios → Credenciales**.
2. Pulsa **Crear credenciales → ID de cliente de OAuth**.
3. En **Tipo de aplicación** elige **Aplicación de escritorio**.
4. Escribe un nombre, por ejemplo `Jarvis escritorio`, y pulsa **Crear**.
5. Descarga el **JSON** con el botón de descarga.
6. Guarda el archivo como `credentials.json` en la raíz del proyecto o en otra ruta y anótala.
7. Comprueba que el JSON contiene un bloque `"installed"`. Si contiene `"web"`, creaste un cliente web por error: repite el paso con **Aplicación de escritorio**.

> `credentials.json` está excluido en `.gitignore`. **Nunca** lo subas al repositorio: identifica a tu aplicación de Google Cloud.

### 5. Configurar `.env`

```dotenv
GOOGLE_OAUTH_CLIENT_FILE=credentials.json
GOOGLE_TIMEZONE=America/Santiago
```

- Si guardaste el JSON fuera del proyecto, usa una ruta absoluta, por ejemplo `C:\Users\tu_usuario\Documentos\credentials.json`.
- `GOOGLE_TIMEZONE` acepta cualquier zona IANA. Si el valor no es válido, Jarvis usa `America/Santiago` y muestra un aviso.
- Reinicia Jarvis después de guardar `.env`.

### 6. Conectar la cuenta

1. Abre Jarvis y busca **GOOGLE CONNECT**.
2. Pulsa **CONECTAR GOOGLE** (o di «conecta Google»).
3. Se abrirá tu **navegador predeterminado** con la página de autorización de Google.
4. Elige la cuenta que añadiste como usuario de prueba.
5. Si aparece «Google no ha verificado esta aplicación», entra en **Configuración avanzada** y continúa con tu propia aplicación. Es normal mientras está en modo Prueba.
6. Revisa que los permisos sean **solo lectura de Gmail** y **solo lectura de eventos de Calendar** y acepta.
7. Cuando el navegador muestre «Autorización completada», cierra esa pestaña y vuelve a Jarvis.
8. Jarvis verifica el acceso con el perfil de Gmail y una consulta mínima de un día al calendario, **sin descargar correos ni eventos**.
9. La tarjeta mostrará **CONECTADO** con la cuenta autorizada. Prueba **Consultar correos** y **Consultar agenda**.

### 7. Token, desconexión y revocación

- El token se guarda cifrado con **DPAPI** en `%LOCALAPPDATA%\MiJarvis\google_token_cache.bin`, ligado a tu usuario de Windows. Si DPAPI no está disponible, la sesión vive **solo en memoria**.
- En aplicaciones con estado **Prueba**, Google puede hacer caducar el token de actualización a los 7 días. Si ocurre, vuelve a pulsar **CONECTAR GOOGLE**.
- Pulsa **Desconectar** o di «desconecta Google». Jarvis borra **su** token y el contexto, pero **no cierra la sesión de tu cuenta en el navegador**.
- Para retirar el consentimiento de la aplicación, entra en <https://myaccount.google.com/permissions>, selecciona la aplicación y pulsa **Quitar acceso**.
- Para empezar de cero, desconecta en Jarvis y borra `%LOCALAPPDATA%\MiJarvis\google_token_cache.bin`.

### 8. Solución de problemas de permisos

| Síntoma | Causa probable | Solución |
|---|---|---|
| «Google no está configurado» | Falta `credentials.json` o la ruta de `GOOGLE_OAUTH_CLIENT_FILE` no existe | Descarga el JSON de la aplicación de escritorio y revisa la ruta en `.env`. |
| «El archivo de credenciales no corresponde a una aplicación de escritorio» | Se creó un cliente OAuth de tipo web | Crea un cliente **Aplicación de escritorio** y descarga su JSON. |
| «Google bloqueó el acceso de la aplicación» | La app está en Prueba y la cuenta no es usuario de prueba, o Workspace lo impide | Añade la cuenta en **Usuarios de prueba** o pide aprobación al administrador. |
| «No se concedieron los permisos de Google» | Rechazaste el consentimiento | Repite la conexión y acepta los dos permisos de lectura. |
| Error 403 | Alguna API está deshabilitada o faltan permisos | Habilita **Gmail API** y **Google Calendar API** y vuelve a conectar. |
| «La sesión de Google venció» | Token caducado, revocado o contraseña cambiada | Pulsa **CONECTAR GOOGLE** otra vez. |
| Error 429 | Límite temporal de las API de Google | Jarvis respeta `Retry-After` y reintenta de forma acotada; espera unos segundos. |
| «No se pudo conectar con Google» | Sin Internet, proxy o firewall | El resto de Jarvis sigue funcionando; recupera la conexión y reintenta. |
| El navegador no se abre | Navegador predeterminado mal configurado | Configura un navegador predeterminado y vuelve a pulsar **CONECTAR GOOGLE**; el flujo local no usa un código manual. |

Enlaces oficiales:

- Consola de Google Cloud: <https://console.cloud.google.com/>
- Gmail API: <https://developers.google.com/gmail/api>
- Google Calendar API: <https://developers.google.com/calendar/api>
- OAuth 2.0 para aplicaciones de escritorio: <https://developers.google.com/identity/protocols/oauth2/native-app>
- Permisos de Gmail: <https://developers.google.com/gmail/api/auth/scopes>
- Permisos de Calendar: <https://developers.google.com/calendar/api/auth>
- Guía rápida de Gmail en Python: <https://developers.google.com/gmail/api/quickstart/python>
- Guía rápida de Calendar en Python: <https://developers.google.com/calendar/api/quickstart/python>
- Revocar acceso: <https://myaccount.google.com/permissions>

## Privacidad: qué datos salen del equipo

Jarvis pide permiso **por proveedor y por finalidad**. Los permisos se conceden en el primer arranque y se pueden retirar en **Ajustes**.

1. **ElevenLabs — transcripción**
   - Se envía el **audio del micrófono** mientras la escucha está activa (en tiempo real por fragmentos o la frase completa en modo lote).
   - No se envía audio si el micrófono está en pausa, cerrado o si Jarvis está hablando.
2. **ElevenLabs — voz**
   - Se envía el **texto de la respuesta** (sin citas `[P#]`, sin enlaces ni marcas) para sintetizarlo.
3. **Google Gemini — documentos**
   - Se envían **solo los fragmentos seleccionados** del documento y tu pregunta.
   - No se envían el archivo completo, la ruta local ni el nombre completo como comando.
4. **Google Gemini — Excel**
   - Se envían tu pregunta y un **resumen acotado de la estructura del libro** (hojas, columnas, tipos y algunos valores), nunca el archivo completo ni rutas locales.
   - Los cálculos se hacen en tu equipo; Gemini solo interpreta la pregunta o redacta la explicación sobre resultados ya calculados.
5. **Google Gemini — conversación**
   - Se envían tu mensaje y un **historial breve y acotado** de la charla.
6. **Google — Gmail, Calendar y voz**
   - La consulta del buzón y de la agenda va **directamente a las API de Google** con un token OAuth; Gemini no participa en esa consulta.
   - Si pides un resumen, se envía a Google Gemini **solo el correo seleccionado** o **los eventos de la agenda consultada**, nunca el buzón o el calendario completos, y solo con el permiso **Google**.
   - Si la respuesta se lee en voz alta, el texto se transmite a ElevenLabs como cualquier otra respuesta. Jarvis lo avisa al activar la voz.
   - No se guardan correos, cuerpos, eventos ni tokens en texto plano. El token usa el cifrado de Windows (DPAPI) o queda solo en memoria.
7. **Aviso del nivel gratuito**
   - Google puede usar el contenido enviado para mejorar sus productos en el nivel gratuito. No uses documentos, libros, correos ni agendas confidenciales con esta configuración.

Además:

- Las claves viven en `.env`, nunca en el código ni en los registros.
- `logs/jarvis.log` guarda eventos técnicos (estado, tipo de error, nombre del recurso y número de fragmentos), **nunca** claves, tokens de Google, contenido del documento o del libro, correos, eventos ni transcripciones.
- El historial de conversación vive solo en memoria; no se guarda entre sesiones.
- Al cerrar, se cierran los flujos de audio, se detiene cualquier reproducción y se liberan los asistentes de Google.
- Jarvis no ejecuta comandos, **no envía, borra ni modifica correos**, no crea ni cambia eventos, no modifica archivos y no activa facturación ni planes de pago.

## Cómo funciona por dentro

La interfaz es delgada y **no llama a proveedores**. Todo pasa por un controlador sin Qt:

1. **`jarvis/core/controller.py`** coordina el arranque, los turnos, el micrófono, la voz, los documentos y el cierre. Todo el trabajo pesado ocurre en un hilo propio con una cola serial.
2. **`jarvis/ui/bridge.py`** convierte los callbacks del controlador en señales Qt en cola. Ningún widget se toca desde el hilo de audio o de red.
3. **`jarvis/audio/capture.py`** abre `sounddevice.RawInputStream`, copia bloques PCM a una cola y procesa remuestreo, VAD y niveles fuera del hilo de Qt.
4. **`jarvis/audio/vad.py`** detecta inicio y fin de frase con energía, búfer previo y adaptación al ruido.
5. **`jarvis/voice/stt.py`** implementa Scribe Realtime v2, el modo por lotes y el híbrido que garantiza una única transcripción final por intervención.
6. **`jarvis/voice/speech.py`** reproduce la síntesis por streaming en subbloques de 20 ms, publica el nivel real y permite detenerla.
7. **`jarvis/core/states.py`** valida las transiciones y etiqueta los estados.
8. **`jarvis/documents/downloads.py`** busca y abre `.docx`, `.xlsx` y `.xlsm` en la carpeta real de Descargas con coincidencia difusa y ambigüedad explícita.
9. **`jarvis/documents/`** extrae párrafos, tablas y secciones; fragmenta; recupera contexto local; el asistente construye el prompt con fuentes.
10. **`jarvis/spreadsheets/`** carga libros con `openpyxl` en dos pasadas (fórmulas y valores), detecta encabezados y tablas, ejecuta consultas y diagnósticos permitidos en Python y deja a Gemini solo la interpretación y la redacción.
11. **`jarvis/integrations/`** implementa Gmail y Google Calendar con OAuth 2.0 de escritorio, caché cifrada con DPAPI, un cliente de solo lectura con reintentos y paginación, y los servicios de correo y calendario con formato en español. El controlador decide cuándo consultar; la UI solo muestra el estado.
12. **`jarvis/ui/`** dibuja el orbe, los visualizadores, la conversación, las tarjetas de Word/Excel, la sección GOOGLE CONNECT y los controles; guarda solo preferencias.

Los errores de los SDK se traducen a mensajes en español (`ProviderRateLimitError`, `ProviderNetworkError`, `ProviderAuthError`, `ProviderModelError`, `DocumentError`, `AudioError`…). La ventana nunca muestra una traza técnica.

## Pruebas automatizadas

```powershell
# Suite completa (local, sin claves ni llamadas reales)
& .\.venv\Scripts\python.exe -m pytest -q

# Un archivo concreto
& .\.venv\Scripts\python.exe -m pytest tests/test_controller.py -v

# Pruebas de integración reales (requieren claves y consumen cuota)
& .\.venv\Scripts\python.exe -m pytest -m integration -v
```

La suite:

- Genera documentos `.docx` temporales con párrafos, encabezados y tablas.
- Genera libros `.xlsx` temporales con `openpyxl` (título, encabezado en la fila 3, tabla, fórmulas y hoja oculta) y comprueba carga, límites, consultas, filtros, agrupaciones, fechas, fórmulas/valores cacheados, calidad, contexto y ambigüedad.
- Bloquea conexiones de red externas; los proveedores se sustituyen por dobles locales.
- Cubre estados y transiciones, saludo, turnos de voz y texto, micrófono ausente o roto, pausa/reanudación, detención de voz, supresión de eco, duplicados, apertura de Descargas, ambigüedad y resolución por número, preguntas sobre el documento, historial acotado, consentimiento denegado, prueba de micrófono, cambio de dispositivo, cierre ordenado y ausencia de secretos en los registros.
- Incluye pruebas de **humo de la ventana** con `QT_QPA_PLATFORM=offscreen`: construcción sin claves, actualización de estado y mensajes, tarjetas de Word/Excel, panel de análisis, cierre limpio y persistencia de consentimiento/preferencias.
- Cubre **Gmail y Google Calendar** con respuestas simuladas: OAuth 2.0 de escritorio con PKCE, caché cifrada con DPAPI, validación de `credentials.json`, cliente de solo lectura sin métodos de escritura, paginación, Gmail (lista, no leídos, multipart, HTML a texto, Base64 URL-safe, detalle solo del correo elegido y sin adjuntos), Calendar (hoy, mañana, semana laboral, próximos siete días, día concreto, eventos de día completo y zona `America/Santiago`), errores 401/403/429/red, consentimiento, seguimientos y separación de contextos.
- Las pruebas marcadas `integration` están **excluidas por defecto** (`pytest.ini`).

### Resultado de la última ejecución

| Prueba | Comando | Resultado |
|---|---|---|
| Suite local completa | `& .\.venv\Scripts\python.exe -m pytest -q` | **460 pasadas**, 4 deseleccionadas |

## Qué está verificado y qué no

Verificado en este equipo:

- **Suite local:** 460 pruebas pasadas, 4 deseleccionadas.
- **Ventana PySide6:** construcción, señales, tarjetas de Word/Excel, sección GOOGLE CONNECT, panel de análisis, cierre y persistencia con plataforma `offscreen`.
- **Excel:** carga de `.xlsx` temporales con encabezado en la fila 3, tabla, fórmulas y hoja oculta; consultas, filtros, agrupaciones, fechas, calidad y lectura de valores cacheados, todo en local con `openpyxl`.
- **Gmail y Google Calendar:** OAuth 2.0 con PKCE, caché cifrada con DPAPI, validación de credenciales, cliente de solo lectura, paginación, correo y calendario con **respuestas simuladas de las API de Google**, errores y contextos. No se ha ejecutado ninguna llamada real a las API de Google en las pruebas.
- **Captura real de micrófono:** MME a 16 kHz y WASAPI a 48 kHz con remuestreo a 16 kHz. `python main.py --check` detecta el micrófono.
- **Carpeta real de Descargas:** resuelta mediante `SHGetKnownFolderPath` como `C:\Users\sgall\Downloads`.
- **Gemini real:** llamadas y asistente documental con un `.docx` temporal.
- **ElevenLabs TTS real:** síntesis PCM a 16 kHz con voz premade.
- **ElevenLabs STT por lotes real:** ida y vuelta síntesis → WAV → `scribe_v2`, con la frase reconocida en español.
- **Proveedores y SDK:** `elevenlabs` 2.74.1, `google-genai` 2.33.0, `openpyxl` 3.1.5, `PySide6-Essentials` 6.12.0, `google-api-python-client` 2.202.0, `google-auth` 2.62.0, `google-auth-httplib2` 0.4.4, `google-auth-oauthlib` 1.5.0, `tzdata` 2026.6, Python 3.12.2.

No verificado todavía de extremo a extremo en hardware real:

- **Conexión real con Google.** La integración está implementada y probada con respuestas simuladas, pero **no se ha autenticado una cuenta real** en este equipo: falta crear la aplicación de escritorio en Google Cloud, colocar `credentials.json` y autorizar la cuenta en el navegador. No se afirma que Gmail ni Calendar funcionen sin esa prueba.
- **Sesión continua de Scribe Realtime v2 en vivo.** La ruta está implementada y probada con dobles; si falla, el respaldo por lotes está probado. El indicador `STT` muestra el modo efectivo.
- **Reproducción por altavoces del flujo TTS.** La síntesis real está verificada; la salida física se cubre con pruebas simuladas.
- **Flujo completo voz → abrir documento → pregunta → respuesta hablada** en una sola sesión con micrófono y altavoces físicos. Cada componente está probado por separado.
- **Flujo completo con un libro real de Descargas desde la interfaz**: apertura, tarjeta de libro, panel de análisis, seguimiento y cambio Word ↔ Excel. La lógica está cubierta con libros temporales y pruebas de humo; falta la comprobación manual en pantalla y con voz real.
- **Revisión visual manual** de la ventana en una pantalla real. Las pruebas gráficas se ejecutaron sin pantalla (`offscreen`).
- **Libros `.xls` o `.xlsb`:** no se admiten; la dependencia opcional no se ha verificado. Se pide guardar como `.xlsx`.
- **Voces profesionales o de biblioteca en plan gratuito:** no funcionan por API (402); se usa una voz premade.

## Errores frecuentes y soluciones

| Mensaje / síntoma | Causa probable | Solución |
|---|---|---|
| `No se pudo cargar la interfaz gráfica (PySide6)` | Falta la dependencia | `python -m pip install -r requirements.txt`. |
| La ventana no aparece y no hay error | Sesión sin escritorio o Qt sin plataforma | Ejecuta desde una sesión de escritorio de Windows; comprueba que `PySide6-Essentials` esté instalado. |
| `Falta GEMINI_API_KEY` | `.env` sin clave o mal ubicado | Crea `.env` en la raíz del proyecto y rellena `GEMINI_API_KEY`. |
| `Se alcanzó el límite de uso… (429)` | Cuota gratuita agotada | Espera a que se restablezca o revisa la cuota en AI Studio. Jarvis no activa pagos. |
| `El servicio informó de un problema interno (503)` | Alta demanda temporal del modelo | Jarvis reintenta; si persiste, cambia `GEMINI_MODEL` por otro modelo gratuito. |
| `El plan actual del servicio no permite usar esta función` | ElevenLabs: voz de biblioteca o *professional* en plan gratuito (402) | Elige una voz **premade** y copia su ID en `ELEVENLABS_VOICE_ID`. |
| `La clave de API fue rechazada` | Clave incorrecta, revocada o de otro proyecto | Genera una nueva clave y actualiza `.env`. |
| `El modelo configurado no está disponible` | El modelo no existe o no está en tu plan | Cambia `GEMINI_MODEL` por uno disponible. |
| `No se pudo conectar con…` | Sin Internet, proxy o firewall | Comprueba la conexión; el modo texto sigue disponible. |
| `No se detectó un micrófono` | Sin micrófono o en uso por otra app | Conecta uno, ciérralo en otras apps, actualiza la lista y usa el modo texto mientras tanto. |
| El micrófono aparece pero no se oye nada | Permiso de Windows, silenciador o dispositivo equivocado | Revisa Privacidad → Micrófono, elige otro dispositivo y usa **Probar micrófono**. |
| La prueba dice «No se detectó voz» | Hablaste demasiado bajo o el flujo no entrega audio | Acércate al micrófono, sube la ganancia o prueba otro dispositivo. |
| `Se perdió la conexión de transcripción; se usará el modo por lotes` | Realtime no disponible | Es el respaldo esperado; el indicador `STT` cambia a `BATCH`. |
| `No diste permiso para enviar audio a ElevenLabs` | Permiso de micrófono retirado | Actívalo en **Ajustes** o reinicia y acepta el diálogo. |
| `No diste permiso para enviar la conversación a Google Gemini` | Permiso de conversación retirado | Actívalo en **Ajustes**; el resto de funciones locales sigue disponible. |
| `El documento parece estar protegido` | Archivo abierto en Word o sin permisos | Ciérralo en Word o copia el archivo a otra carpeta. |
| `El archivo no es un documento .docx válido` | `.doc` antiguo, PDF o archivo dañado | Ábrelo en Word y guárdalo como `.docx`. |
| `El documento no contiene texto legible` | Documento vacío o solo con imágenes | Esta versión no hace OCR. |
| `No pude revisar la carpeta de Descargas` | Carpeta movida, permisos o OneDrive | Comprueba que Descargas exista y que Windows permita leerla. |
| «Encontré varios documentos parecidos» | Ambigüedad real | Responde con el número o elige en la lista; no se abre nada hasta que decidas. |
| `no es un libro .xlsx o .xlsm` | Archivo `.xls`/`.xlsb` antiguo o formato no admitido | Ábrelo en Excel y guárdalo como `.xlsx`. |
| `El libro supera los límites…` / «análisis parcial» | Libro grande para los límites configurados | Sube `JARVIS_SPREADSHEET_MAX_FILE_MB`, `MAX_ROWS` o `MAX_CELLS`, o divide el libro. |
| `el archivo no contiene un resultado calculado` | Celda con fórmula sin valor cacheado | Abre y guarda el libro en Excel para actualizar los resultados; Jarvis no recalcula. |
| `No encontré la columna…` | El nombre no coincide con el encabezado real | Usa el nombre exacto de la columna o escribe la pregunta con la hoja delante. |
| `Hay varias hojas… ¿Cuál quieres consultar?` | La pregunta no indica hoja y hay varias con datos | Nombra la hoja: «en la hoja Tareas». |
| `El archivo no es un libro .xlsx válido` | Archivo dañado, protegido o renombrado | Ábrelo en Excel, comprueba que no esté dañado y guárdalo de nuevo como `.xlsx`. |
| `No se pudo leer ese documento` | `.docx` corrupto o abierto en Word | Ciérralo y vuelve a intentarlo. |
| `Google no está configurado` | Falta `credentials.json` o la ruta de `GOOGLE_OAUTH_CLIENT_FILE` no existe | Descarga el JSON de la aplicación de escritorio y revisa la ruta en `.env`; consulta la guía de Google. |
| `Google no está conectado` | Aún no autorizaste la cuenta | Pulsa **CONECTAR GOOGLE** y completa la autorización en el navegador. |
| `No se concedieron los permisos de Google` | Rechazaste el consentimiento | Repite la conexión y acepta `gmail.readonly` y `calendar.events.readonly`. |
| `Google bloqueó el acceso de la aplicación` | La app está en Prueba y la cuenta no es usuario de prueba, o una política de Workspace lo impide | Añade la cuenta en **Usuarios de prueba** o pide aprobación al administrador. |
| `La sesión de Google venció` | Token caducado (en modo Prueba puede durar 7 días), revocado o contraseña cambiada | Vuelve a conectar la cuenta con **CONECTAR GOOGLE**. |
| `Google rechazó la consulta (error 403)` | Permisos insuficientes, revocados o API deshabilitada | Habilita **Gmail API** y **Google Calendar API** y revisa los dos permisos concedidos. |
| `Google limitó temporalmente las solicitudes (error 429)` | Límite temporal de las API | Jarvis respeta `Retry-After` y reintenta de forma acotada; espera unos segundos. |
| «No hay correos disponibles» / «No hay eventos» | Bandeja o agenda vacías en ese período | Es un resultado válido; prueba otro período o revisa Gmail o Google Calendar. |
| `No se pudo conectar con Google` | Sin Internet, proxy o firewall | Recupera la conexión; Word, Excel, voz y el resto de funciones siguen disponibles. |
| Acentos raros en la consola | Código de página de Windows | Usa Windows Terminal o `chcp 65001`; Jarvis reconfigura la salida a UTF-8. |
| `pip` falla con rutas largas | Límite MAX_PATH + OneDrive | Crea el venv en una ruta corta (ver instalación). |
| La voz no se oye pero la transcripción funciona | Falta `ELEVENLABS_VOICE_ID`, permiso de voz o plan | Configura la voz, acepta el permiso de voz o revisa el plan. |
| El saludo aparece en pantalla pero no se oye | Voz no configurada o permiso de voz denegado | Configura `ELEVENLABS_VOICE_ID` y activa el permiso en Ajustes. |

## Limitaciones conocidas

- No lee **imágenes, escaneos, manuscritos ni texto dentro de imágenes** (haría falta OCR).
- No ofrece **paginación fiable**: las referencias son por encabezado, párrafo y tabla.
- **No hay palabra de activación.** La escucha es continua solo mientras está activa y autorizada; puedes pausarla o cerrarla explícitamente.
- Solo abre archivos **`.docx`, `.xlsx` y `.xlsm`** de Descargas; no controla el sistema operativo, no ejecuta comandos y no modifica archivos.
- **Gmail y Google Calendar:** solo lectura. No envía, responde, reenvía, marca, mueve ni borra correos; no descarga adjuntos; no crea, modifica, cancela ni acepta eventos.
- **Gmail y Google Calendar:** solo se consultan la bandeja de entrada (20 correos recientes), el calendario `primary` y los detalles del correo elegido. No hay búsqueda global, calendarios compartidos, buzones delegados ni sincronización continua.
- **Gmail y Google Calendar:** requieren crear una aplicación propia de escritorio en Google Cloud y autorizar la cuenta en el navegador. Si la app está en modo Prueba, solo funcionan las cuentas añadidas como usuarios de prueba y el token puede caducar a los 7 días; la publicación puede exigir una revisión de Google.
- **Gmail y Google Calendar:** la ventana muestra los eventos en `GOOGLE_TIMEZONE`; no convierte automáticamente a otra zona si viajas.
- **Excel:** solo se admiten `.xlsx`/`.xlsm`; los `.xls`/`.xlsb` requieren guardarse como `.xlsx`.
- **Excel:** no recalcula fórmulas ni ejecuta macros. Si el archivo no trae resultados cacheados, solo puede explicar la fórmula.
- **Excel:** las hojas ocultas se listan pero no se mezclan automáticamente; los libros que superan los límites se analizan de forma **parcial** y se avisa de ello.
- **Excel:** la detección de encabezados y tipos es heurística; una hoja con formato muy irregular puede necesitar que nombres la columna o la hoja.
- La búsqueda local es por palabras clave + TF-IDF; puede no encontrar paráfrasis muy alejadas del vocabulario del documento.
- No hay memoria entre sesiones: solo se guardan preferencias y permisos, no la conversación ni el documento.
- Los turnos se procesan de uno en uno; una respuesta puede tardar si el proveedor está lento.
- El nivel gratuito de Gemini puede usar el contenido para mejorar sus productos; no uses documentos confidenciales.
- El plan gratuito de ElevenLabs puede limitar voces y cuota; Jarvis no activa pagos.
- La calidad de la transcripción depende del micrófono, del ruido ambiente y del idioma configurado.
- La interfaz necesita una sesión de escritorio de Windows; no está pensada para servidores sin pantalla.
- El modo realtime depende de la disponibilidad del modelo; el respaldo por lotes puede añadir latencia.

## Estructura del proyecto

```text
Jarvis/
├─ main.py                         # Entrada: ventana por defecto, consola opcional
├─ jarvis/
│  ├─ config.py                    # .env, validación y valores por defecto
│  ├─ core/
│  │  ├─ controller.py             # Orquestador sin Qt: turnos, audio, documentos
│  │  ├─ states.py                 # Estados y transiciones validadas
│  │  ├─ consent.py                # Permisos por proveedor y finalidad
│  │  ├─ intents.py                # Órdenes en lenguaje natural (reglas locales)
│  │  ├─ errors.py                 # Errores con mensajes en español
│  │  └─ logging_setup.py          # Registro técnico sin datos privados
│  ├─ audio/
│  │  ├─ capture.py                # Captura continua y VAD fuera del hilo de Qt
│  │  ├─ devices.py                # Enumeración y selección de micrófonos
│  │  ├─ dsp.py                    # PCM, niveles y remuestreo sin NumPy
│  │  ├─ vad.py                    # Detección local de voz por energía
│  │  └─ recorder.py               # Grabación explícita de la consola
│  ├─ voice/
│  │  ├─ stt.py                    # Scribe Realtime v2 + lotes + híbrido
│  │  └─ speech.py                 # Síntesis en streaming y reproducción PCM
│  ├─ documents/
│  │  ├─ downloads.py              # Búsqueda y apertura segura en Descargas
│  │  ├─ docx_loader.py            # Lectura de .docx con python-docx
│  │  ├─ chunker.py                # Fragmentación y lotes para resúmenes
│  │  ├─ retriever.py              # Búsqueda local TF-IDF
│  │  └─ models.py                 # Párrafos, tablas, secciones y documento
│  ├─ assistants/
│  │  └─ document_assistant.py     # Preguntas, resúmenes, explicaciones y extracción
│  ├─ spreadsheets/
│  │  ├─ workbook_loader.py        # Carga .xlsx/.xlsm en dos pasadas y aplica límites
│  │  ├─ sheet_profiler.py         # Encabezados, tablas, tipos y estadísticas
│  │  ├─ query_engine.py           # Consultas, filtros, fechas, grupos y fuentes
│  │  ├─ query_planner.py          # Plan local en español + validación del plan de Gemini
│  │  ├─ data_quality.py           # Diagnóstico de calidad de datos
│  │  ├─ formula_explainer.py      # Fórmulas localizadas y valores cacheados
│  │  ├─ workbook_analyzer.py      # Resumen del libro
│  │  ├─ spreadsheet_assistant.py  # Orquestación, contexto y respuestas
│  │  └─ models.py                 # Libro, hoja, columna, rango y resultado
│  ├─ providers/
│  │  ├─ base.py                   # Interfaz LLMProvider
│  │  ├─ gemini_provider.py        # google-genai
│  │  └─ elevenlabs_provider.py    # STT y TTS oficiales
│  ├─ integrations/
│  │  ├─ __init__.py               # Permisos, zona y URL oficiales de Google
│  │  ├─ google_auth.py            # OAuth 2.0 con PKCE, DPAPI y caché cifrada
│  │  ├─ google_client.py          # Cliente GET de solo lectura y reintentos
│  │  ├─ google_mail.py            # Gmail, multipart, HTML a texto y no leídos
│  │  ├─ google_calendar.py        # events.list, zonas horarias y períodos
│  │  ├─ google_format.py          # Formato de fechas, horas y etiquetas
│  │  └─ google_session.py         # Conexión, verificación y servicios de Google
│  └─ ui/
│     ├─ gui.py                    # Ventana, diálogos y preferencias
│     ├─ bridge.py                 # Callbacks del controlador → señales Qt
│     ├─ theme.py                  # Paleta y hoja de estilos
│     ├─ widgets.py                # Orbe, barras, paneles, tarjetas y Google
│     └─ console.py                # Consola clásica (--console)
├─ tests/
│  ├─ test_controller.py           # Turnos, micrófono, documentos, Excel y cierre
│  ├─ test_gui.py                  # Humo de la ventana, paneles y preferencias
│  ├─ test_spreadsheets.py         # Carga, consultas, fórmulas, calidad y contexto
│  ├─ test_google_auth.py          # OAuth, PKCE, DPAPI y caché cifrada
│  ├─ test_google_client.py        # Cliente de solo lectura, reintentos y paginación
│  ├─ test_google_mail.py          # Gmail, multipart, HTML y correo elegido
│  ├─ test_google_calendar.py      # Agenda, períodos y zona horaria
│  ├─ test_google_controller.py    # Comandos, contextos y conexión simulada
│  ├─ google_helpers.py            # Dobles de Gmail y Calendar compartidos
│  ├─ spreadsheet_helpers.py       # Libros .xlsx temporales compartidos
│  └─ ...                          # Audio, voz, documentos, proveedores, estados
├─ .env.example                    # Variables vacías documentadas
├─ .gitignore                      # Protege .env, credentials.json, tokens y temporales
├─ requirements.txt
├─ pytest.ini
└─ README.md
```

## Hoja de ruta

La primera versión implementa la **capacidad documental**, el **análisis de Excel en solo lectura**, la **conversación por voz** y la **consulta de correo de Gmail y agenda de Google Calendar en solo lectura**. La arquitectura permite añadir los roles previstos sin reescribir lo existente.

| Rol | Estado | Piezas que ya existen |
|---|---|---|
| Asistente de Correo | **Solo lectura implementada** (bandeja, conteo y lectura del correo elegido) | `Controller`, `integrations/google_mail.py`, `ConsentManager` |
| Asistente de Agenda | **Solo lectura implementada** (hoy, mañana, semana laboral y próximos siete días) | `integrations/google_calendar.py`, `zoneinfo`, referencias de período |
| Asistente de Tareas | Pendiente | Extracción de acciones y responsabilidades |
| Asistente de Reportes | Pendiente | Resumen map-reduce, salida con fuentes |

Evolución prevista:

1. Añadir nuevos asistentes con la misma interfaz de respuesta (`AssistantAnswer`).
2. Ampliar **Excel**: la lectura y el análisis local ya están; una futura escritura controlada exigirá confirmación explícita.
3. Ampliar **Gmail y Google Calendar** solo si se mantiene el principio de mínimo privilegio: cualquier escritura exigirá permisos nuevos, confirmación explícita y una revisión de seguridad.
4. Añadir un **dashboard** que reutilice el controlador y los asistentes.
5. Mantener un único punto de consentimiento y registro para cada proveedor externo.
6. Verificar en hardware real la conexión con una cuenta de Google, la sesión continua de Scribe Realtime v2 y la reproducción por altavoces.

Los asistentes futuros deberán pedir **confirmación explícita** antes de cualquier acción que modifique información (enviar, crear o borrar). Esta versión solo realiza consultas y aperturas locales autorizadas.

---

**Mi Jarvis 0.1.0** — asistente de escritorio con voz, Word, Excel, Descargas, Gmail y Google Calendar de solo lectura. Hecho para crecer semana a semana.
