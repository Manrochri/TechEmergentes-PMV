"""Prompts y esquemas usados por el agente.

Se mantienen fuera de la lógica para poder ajustarlos sin tocar el flujo, y para que
queden versionados junto al código.
"""

from __future__ import annotations

from typing import Any

from .catalogo_tramites import (
    ESCUELAS_PROFESIONALES,
    TRAMITES_POR_CLAVE,
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

Catálogo de trámites disponibles:
{catalogo}

Escuelas profesionales válidas: {escuelas}
"""

PROMPT_CONVERSACION = """Eres el asistente de trámites de la Facultad de Ingeniería Industrial \
y de Sistemas (FIIS) de la Universidad Nacional Federico Villarreal. Ayudas a estudiantes a \
preparar su Formulario Único de Trámite (FUT).

Cómo respondes:
- En español peruano, cercano pero formal. Tuteas al estudiante.
- Respuestas breves: dos o tres frases como máximo, sin listas largas.
- Pides como mucho DOS datos por turno, y los nombras por separado y con claridad (por \
ejemplo: "tu código de estudiante y tu DNI"). Nunca fusiones dos datos distintos en una sola \
pregunta ambigua.
- Explicas para qué sirve un dato solo si no es evidente.
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

Datos que todavía faltan (pregunta por los primeros de esta lista):
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
    "de Trámite y te lo entrego listo para imprimir y firmar. ¿Qué trámite necesitas hacer?"
)


def construirPromptExtraccion() -> str:
    """Prompt del sistema para la fase de extracción."""
    return PROMPT_EXTRACCION.format(
        catalogo=resumirCatalogoParaModelo(),
        escuelas=", ".join(ESCUELAS_PROFESIONALES),
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
    if clave == "tramiteClave":
        return "Trámite a realizar"
    return ETIQUETAS.get(clave, clave)


__all__ = [
    "construirEsquemaExtraccion",
    "construirPromptExtraccion",
    "construirPromptConversacion",
    "construirPromptFundamentacion",
    "describirCampo",
    "MENSAJE_BIENVENIDA",
]
