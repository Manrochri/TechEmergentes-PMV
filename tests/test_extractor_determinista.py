"""Pruebas del extractor determinista de campos con formato validable."""

from __future__ import annotations

from src.extractor_determinista import extraerCamposDeterministas
from src.modelos import SolicitudFut


def testExtraeDniCelularYCorreoDeUnMensajeLibre() -> None:
    solicitud = SolicitudFut()
    mensaje = "Mi DNI es 74125896, mi celular 987654321 y mi correo christian@unfv.edu.pe"
    cambios = extraerCamposDeterministas(mensaje, solicitud)

    assert cambios["documentoIdentidad"] == "74125896"
    assert cambios["celular"] == "987654321"
    assert cambios["correoElectronico"] == "christian@unfv.edu.pe"


def testNoSobrescribeUnCampoYaConfirmado() -> None:
    solicitud = SolicitudFut(documentoIdentidad="11111111")
    cambios = extraerCamposDeterministas("mi dni es 74125896", solicitud)
    assert "documentoIdentidad" not in cambios


def testDistingueCorreoDeEmpresaPorContexto() -> None:
    solicitud = SolicitudFut(tramiteClave="carta_presentacion", correoElectronico="alumno@unfv.edu.pe")
    mensaje = "el correo de la empresa es rrhh@andina.com.pe"
    cambios = extraerCamposDeterministas(mensaje, solicitud)

    assert cambios.get("empresa", {}).get("correo") == "rrhh@andina.com.pe"
    assert "correoElectronico" not in cambios


def testRucSoloSeAsignaEnCartaDePresentacion() -> None:
    solicitud = SolicitudFut(tramiteClave="carta_presentacion")
    cambios = extraerCamposDeterministas("el RUC de la empresa es 20512345671", solicitud)
    assert cambios["empresa"]["ruc"] == "20512345671"


def testRucNoSeAsignaFueraDeCartaDePresentacion() -> None:
    solicitud = SolicitudFut(tramiteClave="boleta_notas")
    cambios = extraerCamposDeterministas("mi numero es 20512345671", solicitud)
    assert "empresa" not in cambios


def testTelefonoFijoRequiereLaPalabraFijo() -> None:
    solicitud = SolicitudFut()
    cambios = extraerCamposDeterministas("mi telefono fijo es 016543210", solicitud)
    assert cambios["telefonoFijo"] == "016543210"
    assert "celular" not in cambios


def testCodigoDeEstudianteRequiereLaPalabraCodigo() -> None:
    solicitud = SolicitudFut()
    cambios = extraerCamposDeterministas("mi codigo es 2021015432", solicitud)
    assert cambios["codigoEstudiante"] == "2021015432"


def testMensajeSinDatosNoProduceCambios() -> None:
    solicitud = SolicitudFut()
    assert extraerCamposDeterministas("hola, buenas tardes", solicitud) == {}
