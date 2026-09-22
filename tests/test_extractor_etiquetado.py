"""Pruebas de la extracción por segmentos etiquetados.

Reproducen el patrón exacto que motivó esta capa: un estudiante que responde en el
mismo formato en que el propio asistente nombra los campos ("Apellidos y nombres: ...").
"""

from __future__ import annotations

from src.extractor_determinista import extraerCamposDeterministas, extraerSegmentosEtiquetados
from src.modelos import SolicitudFut


def testCapturaApellidosYEscuelaEnUnSoloMensaje() -> None:
    mensaje = "Apellidos y nombres: Perez, Juan Escuela: Ingeniería industrial"
    cambios = extraerSegmentosEtiquetados(mensaje)
    assert cambios["apellidosNombres"] == "Perez, Juan"
    assert cambios["escuelaProfesional"] == "Ingeniería industrial"


def testFuncionaSinTildesNiMayusculasEnLaEtiqueta() -> None:
    cambios = extraerSegmentosEtiquetados("direccion: Av. Los Proceres 1450 distrito: San Isidro")
    assert cambios["direccion"] == "Av. Los Proceres 1450"
    assert cambios["distrito"] == "San Isidro"


def testEtiquetasDeEmpresaVanAlSubobjeto() -> None:
    mensaje = "Nombre de la empresa: Consultora Andina RUC de la empresa: 20512345671"
    cambios = extraerSegmentosEtiquetados(mensaje)
    assert cambios["empresa"]["nombreInstitucion"] == "Consultora Andina"
    assert cambios["empresa"]["ruc"] == "20512345671"


def testSinEtiquetasNoDevuelveNada() -> None:
    assert extraerSegmentosEtiquetados("hola, buenas tardes") == {}


def testIntegradoEnElExtractorCompletoNoSobrescribeDatosYaConfirmados() -> None:
    solicitud = SolicitudFut(apellidosNombres="GARCIA, LUIS")
    cambios = extraerCamposDeterministas("Apellidos y nombres: Perez, Juan", solicitud)
    assert "apellidosNombres" not in cambios
