# Asistente de trámites FIIS — UNFV

Aplicación web con agente de IA que acompaña a los estudiantes de la **Facultad de Ingeniería
Industrial y de Sistemas** de la **Universidad Nacional Federico Villarreal** en sus trámites:
conversa con el estudiante, reconoce el trámite, pide solo los datos que faltan y devuelve el
**Formulario Único de Trámite (FUT) ya rellenado, en PDF, listo para imprimir y firmar**.

El PDF que se entrega **es la plantilla oficial** `SG-UNFV-001`: no se reconstruye ni se imita
el formulario, se escribe encima de él. El reverso con la lista de trámites se conserva intacto.

---

## Qué hace

- **Chat con el estudiante.** El agente identifica el trámite entre los 22 del tarifario vigente
  de la FIIS y le indica el monto y el código de pago del Banco de la Nación.
- **Completa el FUT automáticamente.** Dependencia de destino, tipo de solicitante, datos
  personales, domicilio, contacto, fundamentación, documentos adjuntos, folios, lugar y fecha.
- **Descarga e impresión desde el propio chat.** Cuando el formulario queda completo, el mensaje
  del asistente trae dos botones: **Descargar PDF** y **Abrir e imprimir** (abre el FUT en una
  pestaña nueva del navegador, desde donde se imprime con Ctrl+P o el ícono del visor).
- **Robusto ante fallos del modelo.** La extracción de datos combina tres capas: segmentos
  explícitamente etiquetados y expresiones regulares para los campos con formato validable (DNI,
  celular, correo, RUC, y también "Apellidos y nombres: ...", "Escuela: ..."), el modelo de
  lenguaje para el resto, y como último recurso, si el asistente pidió un solo dato y nada más lo
  interpretó, se asigna la respuesta completa a ese campo. Además, el asistente nunca puede decir
  que el trámite está listo o que ya se puede imprimir mientras de verdad falten datos: esa
  afirmación se filtra y se reemplaza por un recordatorio exacto de lo que falta, sin importar lo
  que "opine" el modelo.
- **Caso especial: carta de presentación para prácticas.** Además del resto de campos, escribe
  dentro de *Fundamentación de lo Solicitado* el bloque exigido por la facultad:

  ```
  Nombre de la Institución o Empresa:
  RUC de la Empresa:
  Correo:
  Teléfono de la empresa:
  Dirección de la Institución o Empresa:
  Nombre, Apellidos y cargo a quien va dirigido:
  ```

- **Panel de revisión.** Barra lateral con el avance, los datos ya capturados y un formulario
  para corregir cualquier campo a mano y regenerar el PDF sin pasar por el chat. Si el chat no
  avanza en dos turnos seguidos, el propio asistente lo sugiere.
- **Sin firma digital, a propósito.** El FUT se entrega sin firmar: el estudiante firma a mano
  sobre el PDF impreso. Ver la sección *"Por qué no se puede adjuntar una firma"* más abajo.

---

## Requisitos

| Componente | Versión | Nota |
|---|---|---|
| Windows | 10 u 11 | También funciona en Linux y macOS |
| Python | 3.11 o superior | [python.org/downloads](https://www.python.org/downloads/) — marca *Add python.exe to PATH* |
| Ollama | 0.5 o superior | [ollama.com/download](https://ollama.com/download) |
| Modelo | `qwen2.5:7b` | ~4.7 GB de descarga, ~8 GB de RAM libre |

---

## Instalación en Windows

### 1. Instalar Ollama y descargar el modelo

Instala Ollama desde su página oficial y, en **PowerShell**, descarga el modelo:

```powershell
ollama pull qwen2.5:7b
```

Comprueba que el servicio responde:

```powershell
ollama list
```

Ollama se inicia solo al arrancar Windows. Si no está activo, ejecuta `ollama serve` en una
terminal aparte y déjala abierta.

### 2. Preparar el proyecto

```powershell
cd C:\ruta\donde\guardaste\agente-fut-fiis

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt
```

> Si PowerShell bloquea el script de activación, ejecuta una sola vez:
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`
> Con el *Símbolo del sistema* (cmd) el comando de activación es `.\.venv\Scripts\activate.bat`.

### 3. Configurar el archivo `.env`

El proyecto ya trae un `.env` funcional. Si quieres partir de cero:

```powershell
Copy-Item .env.example .env
```

Variables disponibles:

| Variable | Valor por defecto | Para qué sirve |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | Dirección del servidor de Ollama |
| `OLLAMA_MODELO` | `qwen2.5:7b` | Modelo de lenguaje |
| `OLLAMA_TEMPERATURA` | `0.2` | Creatividad de la redacción |
| `OLLAMA_TIEMPO_ESPERA` | `120` | Segundos máximos de espera |
| `OLLAMA_NUM_CTX` | `8192` | Ventana de contexto |
| `OLLAMA_MAX_TOKENS` | `1024` | Máximo de tokens de salida (bajo esto, el JSON de extracción puede truncarse) |
| `RUTA_PLANTILLA_FUT` | `assets/FUT_SG-FORMULARIO.pdf` | Plantilla oficial del FUT |
| `RUTA_LOGO` | `assets/Logo_fiis_nuevo.png` | Logo de la FIIS |
| `DIRECTORIO_SALIDAS` | `salidas` | Dónde se guardan los FUT generados |
| `CIUDAD_PREDETERMINADA` | `Lima` | Ciudad del campo *Lugar y Fecha* |
| `GUARDAR_COPIA_LOCAL` | `true` | Guardar copia en disco de cada FUT |
| `MENSAJES_EN_HISTORIAL` | `12` | Turnos que se envían al modelo |
| `COLOR_PRINCIPAL` | `#792D2F` | Color institucional de la interfaz |

### 4. Verificar el entorno

```powershell
python scripts\verificar_entorno.py
```

Debe mostrar cuatro líneas `[OK]`. Si alguna sale `[ERROR]`, el propio mensaje indica cómo
corregirla.

### 5. Levantar la aplicación

```powershell
streamlit run app.py
```

Se abre en `http://localhost:8501`. Para detenerla, `Ctrl + C` en la terminal.

---

## Cómo se usa

1. Escribe lo que necesitas, en lenguaje natural:
   *"Necesito una carta de presentación para mis prácticas en una consultora"*.
2. El asistente reconoce el trámite, muestra el monto y el código de pago en la barra lateral,
   y empieza a pedir los datos de dos en dos.
3. Cuando el expediente está completo, el mensaje trae dos botones: **Descargar PDF** y
   **Abrir e imprimir** (abre el FUT en una pestaña nueva; se imprime con el ícono del visor
   del navegador o Ctrl+P).
4. Firma a mano sobre "Firma y Post Firma del Solicitante" y preséntalo en la Oficina de
   Trámite Documentario con los documentos adjuntos.

Si prefieres no conversar, abre **Revisar y corregir datos** en la barra lateral, completa el
formulario y pulsa **Guardar y generar FUT**. El propio asistente sugiere este atajo si el chat
lleva dos turnos seguidos sin avanzar.

---

## Por qué no se puede adjuntar una firma

El asistente no ofrece subir una imagen de firma, y es una decisión deliberada, no una
limitación pendiente de resolver:

- **La Secretaría General exige firma manuscrita** al presentar el FUT impreso. Una imagen
  pegada en el PDF no tiene ese valor: la oficina igual pediría firmar en el momento, así que
  la función no ahorraría ningún paso real.
- **Es fácil de falsificar y difícil de verificar.** Cualquiera podría adjuntar la firma de
  otra persona a partir de una foto; un campo de "firma digital" así no aporta ninguna garantía
  y podría dar a entender, equivocadamente, que el trámite quedó validado.
- **Genera una falsa sensación de trámite terminado.** Es preferible que el estudiante vea con
  claridad que falta un paso manual, a que crea que un PDF con una imagen pegada ya es un
  documento firmado y listo para presentar.

Por eso el formulario se entrega **sin firmar a propósito** (el recuadro de firma queda en
blanco; solo se imprime el nombre en el "Post firma", justo debajo de donde el estudiante
firmará a mano) y el asistente lo indica en tres lugares: la nota fija en la barra lateral, el
texto junto a los botones de descarga/impresión, y el mensaje de cierre de la conversación.

---

## Estructura del proyecto

```
agente-fut-fiis/
├── app.py                      Interfaz Streamlit (chat, panel lateral, descarga e impresión)
├── requirements.txt
├── .env / .env.example         Configuración
├── .streamlit/config.toml      Tema institucional
├── assets/
│   ├── FUT_SG-FORMULARIO.pdf   Plantilla oficial (no modificar)
│   ├── Logo_fiis_nuevo.png
│   ├── Nuevos-codigos-pago-1.pdf
│   └── estilos.css             Paleta granate #792D2F
├── src/
│   ├── configuracion.py            Lectura y validación del .env
│   ├── modelos.py                  SolicitudFut y DatosEmpresa (Pydantic)
│   ├── validaciones.py             DNI, RUC, correo, teléfono, fechas
│   ├── catalogo_tramites.py        22 trámites con montos y códigos de pago
│   ├── coordenadas_fut.py          Mapa de coordenadas del formulario
│   ├── llenador_fut.py             Superposición de datos sobre la plantilla
│   ├── servicio_ollama.py          Cliente de Ollama con salidas estructuradas
│   ├── extractor_determinista.py   Respaldo por regex (DNI, celular, correo, RUC)
│   ├── plantillas_prompt.py        Prompts y esquema JSON de extracción
│   └── agente_fut.py               Orquestación de la conversación
├── scripts/
│   ├── verificar_entorno.py    Diagnóstico previo
│   └── prueba_llenado.py       FUT de ejemplo sin usar el modelo
├── tests/                      Pruebas con pytest
└── salidas/                    FUT generados
```

---

## Cómo está construido

**El modelo de lenguaje no decide nada crítico.** Extrae datos del diálogo (con un JSON
Schema impuesto vía el parámetro `format` de Ollama) y redacta la siguiente pregunta. Qué
falta, si el formulario está completo y cuándo generar el PDF son decisiones deterministas
escritas en Python. Una alucinación del modelo no puede producir un FUT incorrecto: como
mucho, provoca que se vuelva a preguntar un dato.

**La extracción de datos tiene tres capas de resiliencia**, de más a menos confiable:
1. `extractor_determinista.py` — expresiones regulares y segmentos etiquetados ("Apellidos y
   nombres: ...", "Escuela: ...") para los campos con formato validable o explícitamente
   nombrado. No depende de Ollama en absoluto.
2. El modelo de lenguaje — para texto libre sin ninguna etiqueta. Su salida se recorta al primer
   `{`/último `}` antes de parsear, para tolerar el texto de más que algunos modelos agregan pese
   a recibir un `format` estructurado.
3. Asignación directa como último recurso — si el asistente pidió un solo dato y ni la regex ni
   el modelo interpretaron nada, se asume que el mensaje completo es la respuesta a ese dato
   (con salvaguardas para no confundir preguntas o saludos con datos reales).

**El texto del modelo nunca es la última palabra sobre si el trámite terminó.** Un modelo de 7B
puede (y en la práctica lo hace) decir "ya tengo todos tus datos" o "ya puedes imprimir el FUT"
aunque la mayoría de campos siga vacía — ignora la lista de pendientes que se le da en el
prompt. `agente_fut.py` filtra esas afirmaciones (`_afirmaFalsaCompletitud`) mientras
`camposFaltantes()` no esté vacío, y agrega siempre un pie exacto ("_Aún falta: ..._") calculado
en Python, nunca por el modelo. El botón de descarga solo aparece cuando el estado real —no lo
que diga el chat— confirma que no falta nada.

Esto es lo que evita el problema de fondo que motivó este rediseño: si solo se depende del
modelo para todo, un JSON truncado o mal formado en un campo de texto libre dejaba la
conversación pidiendo el mismo dato para siempre y el FUT nunca se generaba. Con las tres capas,
el flujo llega al PDF incluso si Ollama no está disponible en absoluto (cubierto por
`tests/test_resiliencia_agente.py`).

**El llenado no reconstruye el formulario.** `llenador_fut.py` dibuja con ReportLab una capa
transparente que contiene solo el texto del estudiante y la fusiona con la primera página del
PDF original mediante `pypdf`. Las coordenadas de `coordenadas_fut.py` se obtuvieron leyendo la
estructura vectorial real de la plantilla (celdas de las tablas y posiciones de las etiquetas),
no estimándolas a ojo. Si un texto no cabe en su celda, la fuente se reduce automáticamente
hasta un mínimo antes de recortar, para no invadir las casillas vecinas.

**Convenciones de código.** Funciones y variables en `camelCase` en español; clases en
`PascalCase`; módulos en `snake_case`. Todo el acceso a configuración pasa por
`obtenerConfiguracion()`; ningún módulo lee `os.environ` por su cuenta.

---

## Pruebas

```powershell
python -m pytest tests -v
```

Cubren las validaciones peruanas (DNI, RUC con dígito verificador, correo), la detección de
campos faltantes, el bloque obligatorio de la carta de presentación, el ajuste de texto largo,
la integridad del PDF generado, el extractor determinista y —lo más importante para el problema
reportado— que el flujo completo llega al PDF incluso simulando un Ollama que nunca devuelve
nada útil (`test_resiliencia_agente.py`).

Para revisar visualmente el resultado del llenado sin levantar la app:

```powershell
python scripts\prueba_llenado.py
```

Genera un FUT de ejemplo en `salidas/`.

---

## Ajustes frecuentes

**Cambiar montos o añadir un trámite.** Edita `src/catalogo_tramites.py`: cada trámite es una
entrada de `CATALOGO` con su concepto, monto, código de pago, dependencia de destino, sumilla y
documentos sugeridos. Las `palabrasClave` alimentan el reconocimiento por texto libre.

**Verificar las dependencias de destino.** Los valores de `DEP_DECANATO`, `DEP_REGISTROS`,
`DEP_ESCUELA`, `DEP_GRADOS` y `DEP_BIBLIOTECA` son valores por defecto razonables; conviene
confirmarlos con la Oficina de Trámite Documentario y ajustarlos. Lo mismo aplica a
`ESCUELAS_PROFESIONALES`.

**Si la Secretaría General publica una nueva plantilla.** Reemplaza el PDF en `assets/` y ajusta
`src/coordenadas_fut.py`; es el único archivo con coordenadas. Cada campo declara su esquina
superior izquierda, el ancho de la celda, la línea base de la primera línea y el tamaño de
fuente. Después ejecuta `python scripts\prueba_llenado.py` y revisa el resultado.

---

## Problemas conocidos

| Síntoma | Causa y solución |
|---|---|
| *No se pudo conectar con Ollama* | El servicio no está corriendo. Ejecuta `ollama serve` en otra terminal. |
| *El modelo 'qwen2.5:7b' no está descargado* | `ollama pull qwen2.5:7b` |
| El asistente tarda mucho en responder | Es normal en la primera consulta: el modelo se carga en memoria. Sube `OLLAMA_TIEMPO_ESPERA` si hace falta. |
| El asistente no entiende bien los datos | Escribe un dato por línea (*"DNI: 74125896"*). Como alternativa, usa el formulario manual del panel lateral. |
| `streamlit` no se reconoce como comando | El entorno virtual no está activo. Ejecuta `.\.venv\Scripts\Activate.ps1`. |
| El PDF se descarga en blanco | Falta la plantilla en `assets/`. Ejecuta `python scripts\verificar_entorno.py`. |
| El chat pide el mismo dato una y otra vez | Activa `MODO_DEPURACION=true` en `.env` y revisa la consola: si ves "JSON inválido" repetido, el modelo está teniendo problemas para seguir el esquema. El asistente ya sugiere el panel manual tras dos turnos sin avance; úsalo como salida garantizada. |
| El chat dice "ya está listo" o "ya puedes imprimir" pero no aparece el botón | Es el modelo alucinando; ya se filtra automáticamente (busca en la consola la advertencia "Se descartó una respuesta del modelo..."). Confía siempre en el pie "_Aún falta: ..._" del propio mensaje y en la lista de la barra lateral, no en lo que diga la primera frase. |
| Quiero adjuntar una firma escaneada | No está disponible a propósito: ver *"Por qué no se puede adjuntar una firma"* más arriba. |

---

## Nota sobre los datos

La aplicación corre íntegramente en la máquina del usuario: el modelo se ejecuta en local con
Ollama y ningún dato personal sale del equipo. Los FUT generados se guardan en `salidas/`, que
está excluida del control de versiones junto con el archivo `.env`.
