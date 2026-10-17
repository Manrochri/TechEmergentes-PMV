"""Prompts y esquemas usados por el agente.

Se mantienen fuera de la lógica para poder ajustarlos sin tocar el flujo, y para que
queden versionados junto al código.
"""

from __future__ import annotations

from typing import Any

from .catalogo_tramites import (
    ESCUELAS_PROFESIONALES,
    TRAMITES_POR_CLAVE,
    listarCamposAdicionales,
    listarCamposPorCurso,
    obtenerCampoAdicional,
    obtenerCampoPorCurso,
    resumirCatalogoParaModelo,
)
from .coordenadas_fut import ETIQUETAS

# ---------------------------------------------------------------------------
# Esquema de extracción
# ---------------------------------------------------------------------------
_CAMPOS_TEXTO_SIMPLES: tuple[str, ...] = (
    "apellidosNombres",
    "escuelaProfesional",
    "codigoEstudiante",
    "documentoIdentidad",
    "direccion",
    "numeroDepartamento",
    "distrito",
    "telefonoFijo",
    "celular",
    "correoElectronico",
    "correoNotificacion",
    "dependencia",
    "ciudad",
)

_CAMPOS_EMPRESA: tuple[str, ...] = (
    "nombreInstitucion",
    "ruc",
    "correo",
    "telefono",
    "direccion",
    "destinatario",
)


# ---------------------------------------------------------------------------
# Plantilla para copiar y rellenar en el chat
# ---------------------------------------------------------------------------
#: Orden en que aparecen los datos en la plantilla (mismo orden que el FUT impreso).
#: Los datos propios del trámite (``tramite.<clave>``, p. ej. curso y secciones) se
#: insertan antes de los de la empresa; ver ``AgenteFut.camposParaPlantilla``.
ORDEN_PLANTILLA: tuple[str, ...] = (
    "apellidosNombres",
    "escuelaProfesional",
    "codigoEstudiante",
    "documentoIdentidad",
    "direccion",
    "numeroDepartamento",
    "distrito",
    "telefonoFijo",
    "celular",
    "correoElectronico",
    "empresa.nombreInstitucion",
    "empresa.ruc",
    "empresa.correo",
    "empresa.telefono",
    "empresa.direccion",
    "empresa.destinatario",
)

#: Datos que no son obligatorios pero sí tienen casilla en el FUT: se muestran en la
#: plantilla marcados como "(opcional)" para que el estudiante sepa que existen.
CAMPOS_OPCIONALES_PLANTILLA: frozenset[str] = frozenset({"numeroDepartamento", "telefonoFijo"})

#: Etiqueta de cada renglón de la plantilla. IMPORTANTE: cada etiqueta debe estar
#: reconocida en ``_ETIQUETAS_A_CAMPO`` de ``extractor_determinista.py`` (sin tildes y en
#: minúsculas); así la plantilla rellenada se lee sin depender del modelo de lenguaje.
#: ``tests/test_plantilla_datos.py`` comprueba que ambas listas sigan sincronizadas.
ETIQUETAS_PLANTILLA: dict[str, str] = {
    "apellidosNombres": "Apellidos y nombres",
    "escuelaProfesional": "Escuela profesional",
    "codigoEstudiante": "Código de estudiante",
    "documentoIdentidad": "DNI o pasaporte",
    "direccion": "Dirección domiciliaria",
    "numeroDepartamento": "N° y/o Dpto.",
    "distrito": "Distrito",
    "telefonoFijo": "Teléfono fijo",
    "celular": "Celular",
    "correoElectronico": "Correo electrónico",
    "empresa.nombreInstitucion": "Nombre de la institución o empresa",
    "empresa.ruc": "RUC de la empresa",
    "empresa.correo": "Correo de la empresa",
    "empresa.telefono": "Teléfono de la empresa",
    "empresa.direccion": "Dirección de la institución o empresa",
    "empresa.destinatario": "Nombre, apellidos y cargo a quien va dirigido",
}

#: Aclaración breve entre paréntesis para los datos con un formato concreto.
PISTAS_PLANTILLA: dict[str, str] = {
    "escuelaProfesional": " / ".join(
        e.replace("Ingeniería de ", "").replace("Ingeniería ", "") for e in ESCUELAS_PROFESIONALES
    ),
    "documentoIdentidad": "8 dígitos si es DNI",
    "celular": "9 dígitos",
    "empresa.ruc": "11 dígitos",
}


def _separarCampoCurso(campo: str) -> tuple[int, str] | None:
    """``"curso.2.seccionOrigen"`` -> ``(2, "seccionOrigen")``; ``None`` si no es de curso."""
    partes = campo.split(".")
    if len(partes) == 3 and partes[0] == "curso" and partes[1].isdigit():
        return int(partes[1]), partes[2]
    return None


def construirPlantillaDeDatos(campos: list[str], opcionales: frozenset[str] | set[str] = frozenset()) -> str:
    """Renglones "Etiqueta: " listos para rellenar, uno por dato, en el orden recibido.

    Los datos por curso llevan su número ("Curso 2 (nombre o código): "), que es lo que
    permite al extractor saber a qué curso pertenece cada sección. ``opcionales`` marca
    renglones extra que se pueden dejar en blanco (p. ej. el bloque para otro curso).
    """
    renglones: list[str] = []
    for campo in campos:
        datoCurso = _separarCampoCurso(campo)
        if datoCurso is not None:
            numero, clave = datoCurso
            definicion = obtenerCampoPorCurso(clave)
            etiqueta = f"{definicion.etiqueta if definicion else clave} {numero}"
            if campo in opcionales:
                pista = "opcional, si rectificas otro curso" if clave == "curso" else "opcional"
            else:
                pista = definicion.pista if definicion else ""
            renglones.append(f"{etiqueta} ({pista}): " if pista else f"{etiqueta}: ")
            continue
        etiqueta = ETIQUETAS_PLANTILLA.get(campo, describirCampo(campo))
        if campo in CAMPOS_OPCIONALES_PLANTILLA or campo in opcionales:
            pista = "opcional"
        elif campo.startswith("tramite."):
            adicional = obtenerCampoAdicional(campo.split(".", 1)[1])
            pista = adicional.pista if adicional else ""
        else:
            pista = PISTAS_PLANTILLA.get(campo)
        if pista:
            etiqueta = f"{etiqueta} ({pista})"
        renglones.append(f"{etiqueta}: ")
    return "\n".join(renglones)


def construirEsquemaExtraccion() -> dict[str, Any]:
    """JSON Schema que Ollama impone a la respuesta del modelo al extraer datos.

    Deliberadamente NO se usa ``enum`` para ``tramiteClave``: un enum con las claves de
    los 22 trámites, sumado al objeto anidado de la empresa, es una carga considerable
    para un modelo de 7B y en la práctica reduce la fiabilidad del JSON devuelto. En su
    lugar se deja como texto libre y :func:`AgenteFut.identificarTramiteSiFalta`
    valida (o descarta) el valor contra el catálogo real en Python.
    """
    propiedades: dict[str, Any] = {
        campo: {"type": "string"} for campo in _CAMPOS_TEXTO_SIMPLES
    }
    propiedades["tramiteClave"] = {"type": "string"}
    propiedades["empresa"] = {
        "type": "object",
        "properties": {campo: {"type": "string"} for campo in _CAMPOS_EMPRESA},
    }
    camposCurso = listarCamposPorCurso()
    if camposCurso:
        propiedades["cursos"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {campo.clave: {"type": "string"} for campo in camposCurso},
            },
        }
    adicionales = listarCamposAdicionales()
    if adicionales:
        propiedades["datosTramite"] = {
            "type": "object",
            "properties": {campo.clave: {"type": "string"} for campo in adicionales},
        }
    return {"type": "object", "properties": propiedades}


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
PROMPT_EXTRACCION = """Eres un extractor de datos para el Formulario Único de Trámite (FUT) \
de la Facultad de Ingeniería Industrial y de Sistemas de la UNFV.

Tu única tarea es leer la conversación y devolver un JSON con los datos que el ESTUDIANTE \
haya proporcionado de forma explícita.

Reglas estrictas:
1. No inventes ningún dato. Si un dato no aparece textualmente, omite esa clave.
2. Devuelve solo los datos nuevos o corregidos del último mensaje del estudiante.
3. `tramiteClave` solo puede ser una de las claves del catálogo. Si el estudiante no \
identificó un trámite, omítela.
4. `apellidosNombres` va en el formato "APELLIDOS, NOMBRES" tal como lo dicte el estudiante.
5. `documentoIdentidad` son solo los dígitos o caracteres del DNI/pasaporte, sin etiquetas.
6. El bloque `empresa` solo aplica cuando el trámite es la carta de presentación para \
prácticas: son los datos del centro de prácticas, NO los del estudiante.
7. No confundas el correo del estudiante con el correo de la empresa.
8. El bloque `datosTramite` guarda datos propios de algunos trámites: {datosTramite}. \
Inclúyelos solo si el estudiante los dio de forma explícita.
9. `cursos` es una lista con un elemento por cada curso que el estudiante quiere tramitar \
(p. ej. en la rectificación de matrícula: `curso`, `seccionOrigen` y `seccionDestino`), en el \
orden en que los mencionó. Inclúyela solo si dio esos datos de forma explícita.

Catálogo de trámites disponibles:
{catalogo}

Escuelas profesionales válidas: {escuelas}
"""

PROMPT_CONVERSACION = """Eres el asistente de trámites de la Facultad de Ingeniería Industrial \
y de Sistemas (FIIS) de la Universidad Nacional Federico Villarreal. Ayudas a estudiantes a \
preparar su Formulario Único de Trámite (FUT).

Cómo respondes:
- En español peruano, cercano pero formal. Tuteas al estudiante.
- Respuestas breves: una o dos frases como máximo, sin listas.
- Si todavía no se sabe qué trámite necesita el estudiante, pregúntale cuál es.
- Si el trámite ya se conoce, el sistema escribirá en el cuadro de mensaje del estudiante una \
plantilla con TODOS los datos que faltan, para que solo la rellene y la envíe. Tú NO enumeres \
los datos, NO copies la plantilla y NO pidas datos sueltos: solo responde brevemente a lo que \
dijo el estudiante (si hizo una pregunta, contéstala) e invítalo a completar la plantilla que \
ya tiene en su cuadro de mensaje.
- Si entre los datos que faltan figura "Cursos a rectificar", el sistema mostrará debajo de tu \
respuesta una tabla para que el estudiante agregue sus cursos. Responde en una sola frase breve \
y NO pidas cursos, secciones ni datos personales: las instrucciones de la tabla ya las da el \
sistema.
- Nunca inventas requisitos, montos ni plazos: usa solo lo que aparece en el contexto.
- No repites datos que el estudiante ya confirmó, salvo que él pida revisarlos.
- No uses markdown pesado ni encabezados; escribe en prosa corta.

Reglas que NO puedes romper bajo ninguna circunstancia:
- Si la lista "Datos que todavía faltan" no está vacía, el trámite NO está completo. Nunca \
digas ni des a entender que "ya tienes todos los datos", que el trámite "está listo", o que \
el estudiante "ya puede imprimir o descargar el FUT". Eso solo lo anuncia el sistema, de forma \
automática, cuando de verdad generó el PDF.
- No preguntes "¿necesitas algo más?" ni des la conversación por terminada mientras la lista \
de datos faltantes no esté vacía: tu única tarea en ese caso es pedir los datos que faltan.
- Si no tienes claro si un dato ya fue confirmado, trátalo como pendiente en vez de asumir que \
ya lo tienes.

Contexto del trámite en curso:
{contextoTramite}

Datos ya registrados:
{datosRegistrados}

Datos que todavía faltan (solo como referencia; la plantilla ya los nombra todos):
{datosFaltantes}
"""

PROMPT_FUNDAMENTACION = """Redacta la "Fundamentación de lo Solicitado" de un FUT de la FIIS-UNFV.

Requisitos:
- Un solo párrafo, entre 30 y 55 palabras.
- Redacción formal en primera persona, dirigida a la autoridad de la dependencia.
- Menciona el trámite solicitado y que se adjuntan los documentos requeridos.
- No incluyas saludos, despedidas, firmas ni datos personales.
- Devuelve únicamente el párrafo, sin comillas ni encabezados.

Trámite: {nombreTramite}
Dependencia: {dependencia}
Motivo indicado por el estudiante: {motivo}
"""

MENSAJE_BIENVENIDA = (
    "Hola, soy el asistente de trámites de la FIIS. Te ayudo a llenar tu Formulario Único "
    "de Trámite y te lo entrego listo para imprimir y firmar. ¿Qué trámite necesitas hacer? "
    "En cuanto me lo digas, te dejaré escrita en el cuadro de mensaje una plantilla con todos "
    "los datos que necesito, para que solo la completes y la envíes."
)


def construirPromptExtraccion() -> str:
    """Prompt del sistema para la fase de extracción."""
    adicionales = listarCamposAdicionales()
    return PROMPT_EXTRACCION.format(
        catalogo=resumirCatalogoParaModelo(),
        escuelas=", ".join(ESCUELAS_PROFESIONALES),
        datosTramite=(
            "; ".join(f"`{c.clave}` = {c.etiqueta.lower()} ({c.pista})" for c in adicionales)
            or "ninguno"
        ),
    )


def construirPromptConversacion(
    contextoTramite: str, datosRegistrados: str, datosFaltantes: str
) -> str:
    """Prompt del sistema para la fase de redacción de la respuesta."""
    return PROMPT_CONVERSACION.format(
        contextoTramite=contextoTramite or "Aún no se ha identificado el trámite.",
        datosRegistrados=datosRegistrados or "Ninguno todavía.",
        datosFaltantes=datosFaltantes or "Ninguno: el formulario está completo.",
    )


def construirPromptFundamentacion(nombreTramite: str, dependencia: str, motivo: str) -> str:
    return PROMPT_FUNDAMENTACION.format(
        nombreTramite=nombreTramite,
        dependencia=dependencia,
        motivo=motivo or "No indicó un motivo particular.",
    )


def describirCampo(clave: str) -> str:
    """Etiqueta legible de un campo, incluidos los del bloque de empresa."""
    if clave.startswith("empresa."):
        etiquetasEmpresa = {
            "nombreInstitucion": "Nombre de la institución o empresa",
            "ruc": "RUC de la empresa",
            "correo": "Correo de la empresa",
            "telefono": "Teléfono de la empresa",
            "direccion": "Dirección de la institución o empresa",
            "destinatario": "Nombre, apellidos y cargo a quien va dirigido",
        }
        return etiquetasEmpresa.get(clave.split(".", 1)[1], clave)
    if clave.startswith("tramite."):
        adicional = obtenerCampoAdicional(clave.split(".", 1)[1])
        return adicional.etiqueta if adicional else clave
    datoCurso = _separarCampoCurso(clave)
    if datoCurso is not None:
        numero, nombre = datoCurso
        definicion = obtenerCampoPorCurso(nombre)
        etiqueta = definicion.etiqueta if definicion else nombre
        return f"{etiqueta} {numero}" if nombre == "curso" else f"{etiqueta} (curso {numero})"
    if clave == "tramiteClave":
        return "Trámite a realizar"
    if clave == "cursos":
        return "Cursos a rectificar"
    return ETIQUETAS.get(clave, clave)


__all__ = [
    "construirEsquemaExtraccion",
    "construirPromptExtraccion",
    "construirPromptConversacion",
    "construirPromptFundamentacion",
    "construirPlantillaDeDatos",
    "describirCampo",
    "MENSAJE_BIENVENIDA",
    "ORDEN_PLANTILLA",
    "CAMPOS_OPCIONALES_PLANTILLA",
    "ETIQUETAS_PLANTILLA",
]