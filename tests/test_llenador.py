"""Pruebas del llenado del FUT sobre la plantilla oficial."""

from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader

from src.catalogo_tramites import buscarTramitePorTexto
from src.llenador_fut import (
    ErrorLlenadoFut,
    ajustarTextoAlCampo,
    generarNombreArchivo,
    partirEnLineas,
    rellenarFut,
)
from src.coordenadas_fut import CAMPOS_TEXTO
from src.modelos import DatosEmpresa, SolicitudFut

RUTA_PLANTILLA = Path(__file__).resolve().parent.parent / "assets" / "FUT_SG-FORMULARIO.pdf"


@pytest.fixture
def solicitudCompleta() -> SolicitudFut:
    solicitud = SolicitudFut(
        tramiteClave="carta_presentacion",
        apellidosNombres="Quispe Ramírez, Christian",
        escuelaProfesional="Ingeniería de Sistemas",
        codigoEstudiante="2021015432",
        documentoIdentidad="74125896",
        direccion="Av. Los Próceres 1450",
        distrito="San Isidro",
        celular="987654321",
        correoElectronico="christian.quispe@unfv.edu.pe",
        empresa=DatosEmpresa(
            nombreInstitucion="Consultora Andina S.A.C.",
            ruc="20512345671",
            correo="rrhh@andina.com.pe",
            telefono="014567890",
            direccion="Av. Javier Prado Este 2050",
            destinatario="Ing. María Torres - Jefa de RR. HH.",
        ),
    )
    solicitud.aplicarValoresDelTramite()
    return solicitud


def testSolicitudCompletaNoTieneFaltantes(solicitudCompleta: SolicitudFut) -> None:
    assert solicitudCompleta.estaCompleta()
    assert solicitudCompleta.erroresDeFormato() == {}


def testFaltanDatosDeEmpresaEnCartaDePresentacion() -> None:
    solicitud = SolicitudFut(
        tramiteClave="carta_presentacion",
        apellidosNombres="Pérez López, Ana",
        escuelaProfesional="Ingeniería Industrial",
        codigoEstudiante="2020123456",
        documentoIdentidad="74125896",
        direccion="Jr. Las Begonias 120",
        distrito="Lince",
        celular="987654321",
        correoElectronico="ana.perez@unfv.edu.pe",
    )
    faltantes = solicitud.camposFaltantes()
    assert "empresa.ruc" in faltantes
    assert "empresa.destinatario" in faltantes


def testFundamentacionIncluyeBloqueDeEmpresa(solicitudCompleta: SolicitudFut) -> None:
    texto = solicitudCompleta.construirFundamentacion()
    for etiqueta in (
        "Nombre de la Institución o Empresa:",
        "RUC de la Empresa:",
        "Correo:",
        "Teléfono de la empresa:",
        "Dirección de la Institución o Empresa:",
        "Nombre, Apellidos y cargo a quien va dirigido:",
    ):
        assert etiqueta in texto


def testElPdfConservaLasDosPaginasDeLaPlantilla(solicitudCompleta: SolicitudFut) -> None:
    contenido = rellenarFut(solicitudCompleta, RUTA_PLANTILLA)
    lector = PdfReader.__new__(PdfReader)  # evita escribir en disco
    import io

    lector = PdfReader(io.BytesIO(contenido))
    assert len(lector.pages) == 2


def testElPdfContieneLosDatosDelEstudiante(solicitudCompleta: SolicitudFut) -> None:
    import io

    contenido = rellenarFut(solicitudCompleta, RUTA_PLANTILLA)
    texto = PdfReader(io.BytesIO(contenido)).pages[0].extract_text()
    assert "2021015432" in texto
    assert "74125896" in texto
    assert "20512345671" in texto


def testPlantillaInexistenteLanzaError(solicitudCompleta: SolicitudFut) -> None:
    with pytest.raises(ErrorLlenadoFut):
        rellenarFut(solicitudCompleta, "no/existe/plantilla.pdf")


def testElTextoLargoSeAjustaAlCampo() -> None:
    campo = CAMPOS_TEXTO["fundamentacion"]
    texto = "Palabra " * 300
    lineas, tamano = ajustarTextoAlCampo(texto, campo)
    assert len(lineas) <= campo.limiteLineas
    assert tamano >= campo.tamanoMinimo


def testPartirEnLineasRespetaSaltosExistentes() -> None:
    lineas = partirEnLineas("uno\ndos\ntres", ancho=200, fuente="Helvetica", tamano=9)
    assert lineas == ["uno", "dos", "tres"]


def testNombreArchivoIncluyeCodigoYTramite(solicitudCompleta: SolicitudFut) -> None:
    nombre = generarNombreArchivo(solicitudCompleta)
    assert nombre.startswith("FUT_carta_presentacion_2021015432_")
    assert nombre.endswith(".pdf")


def testBusquedaDeTramitePorTextoLibre() -> None:
    tramite = buscarTramitePorTexto("necesito una carta de presentación para mis prácticas")
    assert tramite is not None
    assert tramite.clave == "carta_presentacion"
