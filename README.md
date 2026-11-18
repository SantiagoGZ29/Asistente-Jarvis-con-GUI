# Mi Jarvis — asistente personal de escritorio

Asistente para **Windows 10/11** con interfaz gráfica **PySide6**, conversación por **voz continua** y control por **texto**. Lee documentos de Word (`.docx`) y libros de Excel (`.xlsx`/`.xlsm`), responde preguntas sobre su contenido con **Google Gemini**, calcula los datos de Excel en local y en **solo lectura**, habla y transcribe con **ElevenLabs** y puede **abrir archivos que estén en tu carpeta real de Descargas** cuando se lo pides por voz.

> **Estado:** versión funcional de escritorio. La ventana gráfica es la forma normal de uso; la consola se conserva con `--console`. Los asistentes de Correo, Agenda, Tareas y Reportes **no** están implementados.

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
14. [Privacidad: qué datos salen del equipo](#privacidad-qué-datos-salen-del-equipo)
15. [Cómo funciona por dentro](#cómo-funciona-por-dentro)
16. [Pruebas automatizadas](#pruebas-automatizadas)
17. [Qué está verificado y qué no](#qué-está-verificado-y-qué-no)
18. [Errores frecuentes y soluciones](#errores-frecuentes-y-soluciones)
19. [Limitaciones conocidas](#limitaciones-conocidas)
20. [Estructura del proyecto](#estructura-del-proyecto)
21. [Hoja de ruta](#hoja-de-ruta)

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
- Carga el documento para **resumir, explicar y responder preguntas**, con fuentes por párrafo/tabla y sin inventar datos.
- Mantiene una **conversación libre breve** cuando no hay documento abierto, con historial acotado.
- Permite **escribir** en cualquier momento: si el micrófono falla, no hay claves o rechazas permisos, el modo texto sigue funcionando.
- Guarda tus preferencias (micrófono, escucha automática, lectura en voz alta y permisos) entre sesiones.
- Limpia el audio al cerrar: no quedan micrófonos ni reproducciones activas.

## Requisitos

- **Windows 10 u 11**.
- **Python 3.11 o superior** (probado con 3.12.2).
- Conexión a Internet para Gemini y ElevenLabs.
- Micrófono y altavoces/auriculares para la conversación por voz (opcionales).
- Cuenta gratuita de **Google AI Studio** (Gemini) y, opcionalmente, de **ElevenLabs**.

Dependencias principales: `google-genai`, `elevenlabs`, `python-docx`, `openpyxl`, `sounddevice`, `python-dotenv`, **`PySide6-Essentials`** y `pytest`. No se usa NumPy ni `webrtcvad`: el audio se procesa como PCM entero de 16 bits con la biblioteca estándar, y `openpyxl` lee Excel sin automatizar Excel ni ejecutar macros.

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

- Cinco casillas, **todas desmarcadas al empezar**:
  1. **Micrófono:** enviar tu voz a ElevenLabs para transcribirla.
  2. **Voz:** enviar el texto de las respuestas a ElevenLabs para leerlo.
  3. **Documentos:** enviar fragmentos del documento a Google Gemini.
  4. **Excel:** enviar tu pregunta y un resumen acotado del libro a Google Gemini para interpretarla o redactar la respuesta.
  5. **Conversación:** enviar tus mensajes a Google Gemini cuando no hay documento.
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
6. **Aviso del nivel gratuito**
   - Google puede usar el contenido enviado para mejorar sus productos en el nivel gratuito. No uses documentos ni libros laborales confidenciales con esta configuración.

Además:

- Las claves viven en `.env`, nunca en el código ni en los registros.
- `logs/jarvis.log` guarda eventos técnicos (estado, tipo de error, nombre del recurso y número de fragmentos), **nunca** claves, contenido del documento o del libro ni transcripciones.
- El historial de conversación vive solo en memoria; no se guarda entre sesiones.
- Al cerrar, se cierran los flujos de audio y se detiene cualquier reproducción.
- Jarvis no ejecuta comandos, no envía correos, no modifica archivos y no activa facturación ni planes de pago.

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
11. **`jarvis/ui/`** dibuja el orbe, los visualizadores, la conversación, las tarjetas de Word/Excel y los controles; guarda solo preferencias.

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
- Las pruebas marcadas `integration` están **excluidas por defecto** (`pytest.ini`).

### Resultado de la última ejecución

| Prueba | Comando | Resultado |
|---|---|---|
| Suite local completa | `& .\.venv\Scripts\python.exe -m pytest -q` | **341 pasadas**, 4 deseleccionadas |

## Qué está verificado y qué no

Verificado en este equipo:

- **Suite local:** 341 pruebas pasadas, 4 deseleccionadas.
- **Ventana PySide6:** construcción, señales, tarjetas de Word/Excel, panel de análisis, cierre y persistencia con plataforma `offscreen`.
- **Excel:** carga de `.xlsx` temporales con encabezado en la fila 3, tabla, fórmulas y hoja oculta; consultas, filtros, agrupaciones, fechas, calidad y lectura de valores cacheados, todo en local con `openpyxl`.
- **Captura real de micrófono:** MME a 16 kHz y WASAPI a 48 kHz con remuestreo a 16 kHz. `python main.py --check` detecta el micrófono.
- **Carpeta real de Descargas:** resuelta mediante `SHGetKnownFolderPath` como `C:\Users\sgall\Downloads`.
- **Gemini real:** llamadas y asistente documental con un `.docx` temporal.
- **ElevenLabs TTS real:** síntesis PCM a 16 kHz con voz premade.
- **ElevenLabs STT por lotes real:** ida y vuelta síntesis → WAV → `scribe_v2`, con la frase reconocida en español.
- **Proveedores y SDK:** `elevenlabs` 2.74.1, `google-genai` 2.33.0, `openpyxl` 3.1.5, `PySide6-Essentials` 6.12.0, Python 3.12.2.

No verificado todavía de extremo a extremo en hardware real:

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
| Acentos raros en la consola | Código de página de Windows | Usa Windows Terminal o `chcp 65001`; Jarvis reconfigura la salida a UTF-8. |
| `pip` falla con rutas largas | Límite MAX_PATH + OneDrive | Crea el venv en una ruta corta (ver instalación). |
| La voz no se oye pero la transcripción funciona | Falta `ELEVENLABS_VOICE_ID`, permiso de voz o plan | Configura la voz, acepta el permiso de voz o revisa el plan. |
| El saludo aparece en pantalla pero no se oye | Voz no configurada o permiso de voz denegado | Configura `ELEVENLABS_VOICE_ID` y activa el permiso en Ajustes. |

## Limitaciones conocidas

- No lee **imágenes, escaneos, manuscritos ni texto dentro de imágenes** (haría falta OCR).
- No ofrece **paginación fiable**: las referencias son por encabezado, párrafo y tabla.
- **No hay palabra de activación.** La escucha es continua solo mientras está activa y autorizada; puedes pausarla o cerrarla explícitamente.
- Solo abre archivos **`.docx`, `.xlsx` y `.xlsm`** de Descargas; no controla el sistema operativo, no ejecuta comandos y no modifica archivos.
- No se conecta a **correo, Outlook, Google Calendar ni WhatsApp**.
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
│  └─ ui/
│     ├─ gui.py                    # Ventana, diálogos y preferencias
│     ├─ bridge.py                 # Callbacks del controlador → señales Qt
│     ├─ theme.py                  # Paleta y hoja de estilos
│     ├─ widgets.py                # Orbe, barras, paneles y tarjetas
│     └─ console.py                # Consola clásica (--console)
├─ tests/
│  ├─ test_controller.py           # Turnos, micrófono, documentos, Excel y cierre
│  ├─ test_gui.py                  # Humo de la ventana, tarjetas y preferencias
│  ├─ test_spreadsheets.py         # Carga, consultas, fórmulas, calidad y contexto
│  ├─ spreadsheet_helpers.py       # Libros .xlsx temporales compartidos
│  └─ ...                          # Audio, voz, documentos, proveedores, estados
├─ .env.example                    # Variables vacías documentadas
├─ .gitignore                      # Protege .env, .venv, logs y temporales
├─ requirements.txt
├─ pytest.ini
└─ README.md
```

## Hoja de ruta

La primera versión implementa la **capacidad documental**, el **análisis de Excel en solo lectura** y la **conversación por voz**. La arquitectura permite añadir los cuatro roles previstos sin reescribir lo existente. Esos cuatro roles **siguen sin estar conectados** a cuentas, calendarios ni correos; el análisis de Excel ya está disponible.

| Rol | Qué hará | Piezas que ya existen |
|---|---|---|
| Asistente de Correo | Clasificar comunicaciones e identificar compromisos | `Controller`, `DocumentAssistant` como patrón, `ConsentManager` |
| Asistente de Agenda | Reuniones, fechas y vencimientos | Extracción de fechas/plazos, referencias a fuentes |
| Asistente de Tareas | Registros, estados y prioridades | Extracción de acciones y responsabilidades |
| Asistente de Reportes | Resúmenes e indicadores | Resumen map-reduce, salida con fuentes |

Evolución prevista:

1. Añadir nuevos asistentes con la misma interfaz de respuesta (`AssistantAnswer`).
2. Ampliar **Excel**: la lectura y el análisis local ya están; una futura escritura controlada exigirá confirmación explícita.
3. Añadir un **dashboard** que reutilice el controlador y los asistentes.
4. Mantener un único punto de consentimiento y registro para cada proveedor externo.
5. Verificar en hardware real la sesión continua de Scribe Realtime v2 y la reproducción por altavoces.

Los asistentes futuros deberán pedir **confirmación explícita** antes de cualquier acción que modifique información (enviar, crear o borrar). Esta versión solo realiza consultas y aperturas locales autorizadas.

---

**Mi Jarvis 0.1.0** — asistente de escritorio con voz, Word, Excel y Descargas. Hecho para crecer semana a semana.
