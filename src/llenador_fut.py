"""Llenado del FUT sobre la plantilla oficial.

Estrategia
----------
No se reconstruye el formulario. Se dibuja una capa transparente con ReportLab que
contiene únicamente el texto del estudiante y se fusiona con la **primera página del PDF
original**; la segunda página (el reverso con la lista de trámites) se copia intacta.
Así el documento resultante conserva el diseño, los sellos y el código ``SG-UNFV-001``
de la Secretaría General.
"""

from __future__ import annotations

import io
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from .coordenadas_fut import (
    CAMPOS_TEXTO,
    CASILLAS_TIPO_SOLICITANTE,
    FUENTE_MARCA,
    MARCA_CASILLA,
    PAGINA_FORMULARIO,
    TAMANO_MARCA,
    CampoFut,
)
from .modelos import SolicitudFut

PASO_REDUCCION_FUENTE: float = 0.25


class ErrorLlenadoFut(RuntimeError):
    """Se lanza cuando la plantilla no existe o no tiene el formato esperado."""


# ---------------------------------------------------------------------------
# Utilidades de texto
# ---------------------------------------------------------------------------
def medirTexto(texto: str, fuente: str, tamano: float) -> float:
    """Ancho en puntos que ocupa ``texto`` con la fuente indicada."""
    return pdfmetrics.stringWidth(texto, fuente, tamano)


def partirEnLineas(texto: str, ancho: float, fuente: str, tamano: float) -> list[str]:
    """Divide el texto en líneas que caben en ``ancho``, respetando los saltos existentes."""
    lineas: list[str] = []
    for parrafo in str(texto).split("\n"):
        palabras = parrafo.split()
        if not palabras:
            lineas.append("")
            continue
        actual = palabras[0]
        for palabra in palabras[1:]:
            tentativa = f"{actual} {palabra}"
            if medirTexto(tentativa, fuente, tamano) <= ancho:
                actual = tentativa
            else:
                lineas.append(actual)
                actual = palabra
        lineas.append(actual)
    return lineas


def ajustarTextoAlCampo(texto: str, campo: CampoFut) -> tuple[list[str], float]:
    """Busca el mayor tamaño de fuente con el que el texto entra en el campo.

    Devuelve las líneas ya divididas y el tamaño de fuente elegido. Si ni con el tamaño
    mínimo entra todo, se recorta la última línea con puntos suspensivos para no invadir
    las celdas vecinas del formulario.
    """
    tamano = campo.tamanoFuente
    while tamano >= campo.tamanoMinimo:
        lineas = partirEnLineas(texto, campo.ancho, campo.fuente, tamano)
        if len(lineas) <= campo.limiteLineas:
            return lineas, tamano
        tamano -= PASO_REDUCCION_FUENTE

    tamano = campo.tamanoMinimo
    lineas = partirEnLineas(texto, campo.ancho, campo.fuente, tamano)[: campo.limiteLineas]
    if lineas:
        lineas[-1] = _recortarConElipsis(lineas[-1], campo.ancho, campo.fuente, tamano)
    return lineas, tamano


def _recortarConElipsis(texto: str, ancho: float, fuente: str, tamano: float) -> str:
    if medirTexto(texto, fuente, tamano) <= ancho:
        return texto
    recortado = texto
    while recortado and medirTexto(f"{recortado}...", fuente, tamano) > ancho:
        recortado = recortado[:-1]
    return f"{recortado}..."


def normalizarParaPdf(texto: str) -> str:
    """Sustituye caracteres que las fuentes base (WinAnsi) no pueden representar."""
    reemplazos = {"\u2013": "-", "\u2014": "-", "\u2018": "'", "\u2019": "'",
                  "\u201c": '"', "\u201d": '"', "\u2026": "...", "\u00a0": " "}
    for origen, destino in reemplazos.items():
        texto = texto.replace(origen, destino)
    return "".join(c for c in texto if unicodedata.category(c) != "Cc" or c == "\n")


# ---------------------------------------------------------------------------
# Dibujo
# ---------------------------------------------------------------------------
def dibujarCampo(lienzo: canvas.Canvas, campo: CampoFut, texto: str, altoPagina: float) -> None:
    """Escribe el valor de un campo respetando su caja y su alineación."""
    contenido = normalizarParaPdf(str(texto)).strip()
    if not contenido:
        return

    lineas, tamano = ajustarTextoAlCampo(contenido, campo)
    lienzo.setFont(campo.fuente, tamano)

    for indice, linea in enumerate(lineas):
        if not linea:
            continue
        lineaBase = campo.y + indice * campo.interlineado
        y = altoPagina - lineaBase
        if campo.centrado:
            x = campo.x + (campo.ancho - medirTexto(linea, campo.fuente, tamano)) / 2
        else:
            x = campo.x
        lienzo.drawString(x, y, linea)


def marcarCasilla(lienzo: canvas.Canvas, tipoSolicitante: str, altoPagina: float) -> None:
    """Coloca la ``X`` dentro del paréntesis del tipo de solicitante."""
    posicion = CASILLAS_TIPO_SOLICITANTE.get(tipoSolicitante)
    if posicion is None:
        return
    centroX, lineaBase = posicion
    lienzo.setFont(FUENTE_MARCA, TAMANO_MARCA)
    ancho = medirTexto(MARCA_CASILLA, FUENTE_MARCA, TAMANO_MARCA)
    lienzo.drawString(centroX - ancho / 2, altoPagina - lineaBase, MARCA_CASILLA)


def construirCapaDeDatos(
    solicitud: SolicitudFut, anchoPagina: float, altoPagina: float
) -> io.BytesIO:
    """Genera en memoria un PDF de una página con solo el texto a superponer."""
    memoria = io.BytesIO()
    lienzo = canvas.Canvas(memoria, pagesize=(anchoPagina, altoPagina))
    lienzo.setTitle("Capa de datos FUT")

    valores = solicitud.aCamposDelFormulario()
    for clave, campo in CAMPOS_TEXTO.items():
        dibujarCampo(lienzo, campo, valores.get(clave, ""), altoPagina)

    marcarCasilla(lienzo, solicitud.tipoSolicitante, altoPagina)

    lienzo.showPage()
    lienzo.save()
    memoria.seek(0)
    return memoria


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------
def rellenarFut(solicitud: SolicitudFut, rutaPlantilla: str | Path) -> bytes:
    """Devuelve los bytes del FUT original con los datos del estudiante impresos.

    Args:
        solicitud: estado validado de la solicitud.
        rutaPlantilla: ruta al PDF oficial ``FUT_SG-FORMULARIO.pdf``.

    Raises:
        ErrorLlenadoFut: si la plantilla no existe o no se puede leer.
    """
    ruta = Path(rutaPlantilla)
    if not ruta.is_file():
        raise ErrorLlenadoFut(f"No se encontró la plantilla del FUT en: {ruta}")

    try:
        lector = PdfReader(str(ruta))
    except Exception as error:  # pragma: no cover - depende del archivo del usuario
        raise ErrorLlenadoFut(f"No se pudo leer la plantilla del FUT: {error}") from error

    if not lector.pages:
        raise ErrorLlenadoFut("La plantilla del FUT no contiene páginas.")

    solicitud.aplicarValoresDelTramite()

    paginaFormulario = lector.pages[PAGINA_FORMULARIO]
    caja = paginaFormulario.mediabox
    capa = construirCapaDeDatos(solicitud, float(caja.width), float(caja.height))
    paginaCapa = PdfReader(capa).pages[0]

    escritor = PdfWriter()
    for indice, pagina in enumerate(lector.pages):
        if indice == PAGINA_FORMULARIO:
            pagina.merge_page(paginaCapa)
        escritor.add_page(pagina)

    escritor.add_metadata(
        {
            "/Title": "Formulario Único de Trámite - FIIS UNFV",
            "/Subject": solicitud.sumilla or "Solicitud FUT",
            "/Creator": "Asistente de trámites FIIS",
        }
    )

    salida = io.BytesIO()
    escritor.write(salida)
    return salida.getvalue()


def generarNombreArchivo(solicitud: SolicitudFut) -> str:
    """Nombre de archivo sugerido: ``FUT_<tramite>_<codigo>_<fecha>.pdf``."""
    tramite = solicitud.tramite
    etiqueta = tramite.clave if tramite else "tramite"
    codigo = re.sub(r"\W+", "", solicitud.codigoEstudiante) or "sincodigo"
    marca = datetime.now().strftime("%Y%m%d-%H%M")
    return f"FUT_{etiqueta}_{codigo}_{marca}.pdf"


def guardarFut(contenido: bytes, directorio: str | Path, nombreArchivo: str) -> Path:
    """Guarda una copia local del FUT generado y devuelve su ruta."""
    carpeta = Path(directorio)
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / nombreArchivo
    destino.write_bytes(contenido)
    return destino


__all__ = [
    "ErrorLlenadoFut",
    "rellenarFut",
    "generarNombreArchivo",
    "guardarFut",
    "partirEnLineas",
    "ajustarTextoAlCampo",
]
