"""Pruebas de la plantilla "Etiqueta: " que el asistente muestra en el chat.

El asistente ya no pide los datos de dos en dos: en cuanto conoce el trámite, arma una
plantilla con TODOS los datos que faltan, que la interfaz deja escrita en el cuadro de
mensaje para que el estudiante la rellene y la envíe en un solo mensaje. Estas pruebas comprueban que la plantilla nombre todos los datos
y que, una vez rellenada, se lea completa sin depender del modelo de lenguaje.
"""

from __future__ import annotations

from src.agente_fut import AgenteFut
from src.catalogo_tramites import normalizarEscuela
from src.extractor_determinista import extraerSegmentosEtiquetados
from src.modelos import SolicitudFut
from src.plantillas_prompt import (
    ETIQUETAS_PLANTILLA,
    ORDEN_PLANTILLA,
    construirPlantillaDeDatos,
)


class _ModeloMudo:
    """Simula un modelo que no extrae ni redacta nada (peor caso)."""

    def extraerEstructurado(self, mensajes, esquema, temperatura: float = 0.0) -> dict:
        return {}

    def conversar(self, mensajes, temperatura: float | None = None) -> str:
        return ""


def _agente() -> AgenteFut:
    return AgenteFut(servicio=_ModeloMudo())


def _rellenar(plantilla: str, valores: dict[str, str]) -> str:
    """Simula al estudiante escribiendo cada valor después de los dos puntos."""
    renglones = []
    for renglon in plantilla.splitlines():
        campo = next(
            (c for c in valores if construirPlantillaDeDatos([c]) == renglon), None
        )
        renglones.append(renglon + (valores[campo] if campo else ""))
    return "\n".join(renglones)


def testCadaEtiquetaDeLaPlantillaLaReconoceElExtractor() -> None:
    """Si alguien cambia una etiqueta de la plantilla, esta prueba avisa que falta en el extractor."""
    for campo in ORDEN_PLANTILLA:
        renglon = construirPlantillaDeDatos([campo]) + "valor de prueba 123"
        cambios = extraerSegmentosEtiquetados(renglon)
        if campo.startswith("empresa."):
            leido = cambios.get("empresa", {}).get(campo.split(".", 1)[1])
        else:
            leido = cambios.get(campo)
        assert leido == "valor de prueba 123", f"La etiqueta de '{campo}' no se reconoce: {renglon!r}"


def testTodasLasEtiquetasTienenTextoEnLaPlantilla() -> None:
    assert set(ORDEN_PLANTILLA) == set(ETIQUETAS_PLANTILLA)


def testAlIdentificarElTramiteSeNombranTodosLosDatos() -> None:
    agente = _agente()
    respuesta = agente.procesarMensaje(
        "necesito una carta de presentacion para mis practicas", SolicitudFut(), [], []
    )
    for campo in ORDEN_PLANTILLA:
        assert ETIQUETAS_PLANTILLA[campo] in respuesta.plantilla, campo
    assert "(opcional)" in respuesta.plantilla
    # La plantilla va al cuadro de mensaje, no dentro del texto del chat.
    assert "```" not in respuesta.mensaje
    assert "cuadro de mensaje" in respuesta.mensaje


def testSinTramiteSePreguntaPrimeroElTramite() -> None:
    respuesta = _agente().procesarMensaje("hola", SolicitudFut(), [], [])
    assert respuesta.plantilla == ""
    assert "trámite" in respuesta.mensaje.lower()


def testLaPlantillaRellenadaCompletaElFutEnUnSoloMensaje() -> None:
    agente = _agente()
    solicitud = SolicitudFut()
    primera = agente.procesarMensaje(
        "necesito una carta de presentacion para mis practicas", solicitud, [], []
    )
    plantilla = primera.plantilla

    relleno = _rellenar(plantilla, {
        "apellidosNombres": "Quispe Ramírez, Christian",
        "escuelaProfesional": "sistemas",
        "codigoEstudiante": "2021015432",
        "documentoIdentidad": "74125896",
        "direccion": "Av. Los Próceres 1450",
        "distrito": "San Isidro",
        "celular": "987654321",
        "correoElectronico": "christian.quispe@unfv.edu.pe",
        "empresa.nombreInstitucion": "Consultora Andina S.A.C.",
        "empresa.ruc": "20512345671",
        "empresa.correo": "rrhh@andina.com.pe",
        "empresa.telefono": "014567890",
        "empresa.direccion": "Av. Javier Prado Este 2050",
        "empresa.destinatario": "Ing. María Torres - Jefa de RR. HH.",
    })

    respuesta = agente.procesarMensaje(relleno, primera.solicitud, [], primera.camposPreguntados)
    assert respuesta.formularioListo, respuesta.mensaje
    assert respuesta.pdf
    s = respuesta.solicitud
    assert s.escuelaProfesional == "Ingeniería de Sistemas"
    assert s.empresa.correo == "rrhh@andina.com.pe"
    assert s.correoElectronico == "christian.quispe@unfv.edu.pe"
    assert s.telefonoFijo == "" and s.numeroDepartamento == ""


def testUnDatoInvalidoReapareceEnLaPlantillaYSePuedeCorregir() -> None:
    agente = _agente()
    solicitud = SolicitudFut(tramiteClave="boleta_notas")
    respuesta = agente.procesarMensaje("DNI o pasaporte: 123", solicitud, [], [])
    assert respuesta.solicitud.documentoIdentidad == ""
    assert "DNI o pasaporte (8 dígitos si es DNI):" in respuesta.plantilla

    corregida = agente.procesarMensaje(
        "DNI o pasaporte: 74125896", respuesta.solicitud, [], respuesta.camposPreguntados
    )
    assert corregida.solicitud.documentoIdentidad == "74125896"


def testNormalizarEscuelaAceptaAbreviaturas() -> None:
    assert normalizarEscuela("sistemas") == "Ingeniería de Sistemas"
    assert normalizarEscuela("Ing. Industrial") == "Ingeniería Industrial"
    assert normalizarEscuela("agroindustrial") == "Ingeniería Agroindustrial"
    assert normalizarEscuela("mecatronica") == "Ingeniería Mecatrónica"
    assert normalizarEscuela("Transporte") == "Ingeniería de Transportes"
    assert normalizarEscuela("Arquitectura") == "Arquitectura"


def testUnDatoEtiquetadoNoSeReasignaComoDatoSuelto() -> None:
    """El correo del estudiante no debe copiarse como correo de la empresa, ni el teléfono
    de la empresa como celular del estudiante."""
    from src.extractor_determinista import extraerCamposDeterministas

    solicitud = SolicitudFut(tramiteClave="carta_presentacion")
    cambios = extraerCamposDeterministas(
        "Correo electrónico: ana@unfv.edu.pe\nTeléfono de la empresa: 014567890", solicitud
    )
    assert cambios["correoElectronico"] == "ana@unfv.edu.pe"
    assert cambios["empresa"] == {"telefono": "014567890"}
    assert "celular" not in cambios


def testRectificacionPideCursoYSecciones() -> None:
    respuesta = _agente().procesarMensaje(
        "quiero hacer una rectificacion de matricula", SolicitudFut(), [], []
    )
    assert respuesta.solicitud.tramiteClave == "rectificacion_matricula"
    plantilla = respuesta.plantilla
    assert "Curso (nombre o código del curso):" in plantilla
    assert "Sección de origen (en la que estás matriculado):" in plantilla
    assert "Sección de destino (a la que deseas cambiarte):" in plantilla
    # Van después de los datos del estudiante.
    assert plantilla.index("Correo electrónico") < plantilla.index("Curso")


def testOtrosTramitesNoPidenCursoNiSecciones() -> None:
    respuesta = _agente().procesarMensaje("necesito mi boleta de notas", SolicitudFut(), [], [])
    assert "Curso" not in respuesta.plantilla
    assert "Sección" not in respuesta.plantilla


def testRectificacionCompletaImprimeCursoYSeccionesEnLaFundamentacion() -> None:
    agente = _agente()
    primera = agente.procesarMensaje(
        "quiero hacer una rectificacion de matricula", SolicitudFut(), [], []
    )
    relleno = _rellenar(primera.plantilla, {
        "apellidosNombres": "Pérez López, Ana",
        "escuelaProfesional": "Industrial",
        "codigoEstudiante": "2020123456",
        "documentoIdentidad": "74125896",
        "direccion": "Jr. Las Begonias 120",
        "distrito": "Lince",
        "celular": "987654321",
        "correoElectronico": "ana.perez@unfv.edu.pe",
        "tramite.curso": "Investigación de Operaciones I",
        "tramite.seccionOrigen": "01",
        "tramite.seccionDestino": "03",
    })
    respuesta = agente.procesarMensaje(relleno, primera.solicitud, [], primera.camposPreguntados)

    assert respuesta.formularioListo, respuesta.mensaje
    fundamentacion = respuesta.solicitud.fundamentacion
    assert "Curso: Investigación de Operaciones I" in fundamentacion
    assert "Sección de origen: 01" in fundamentacion
    assert "Sección de destino: 03" in fundamentacion


def testUnaRespuestaSueltaSeAsignaAlDatoDelTramitePendiente() -> None:
    """Si solo falta la sección de destino y el estudiante responde "03", se asigna ahí."""
    solicitud = SolicitudFut(
        tramiteClave="rectificacion_matricula",
        datosTramite={"curso": "Física I", "seccionOrigen": "01"},
    )
    respuesta = _agente().procesarMensaje(
        "03", solicitud, [], camposEsperados=["tramite.seccionDestino"]
    )
    assert respuesta.solicitud.datosTramite["seccionDestino"] == "03"


def testUnaPlantillaEnviadaSinRellenarNoSeTomaComoDato() -> None:
    solicitud = SolicitudFut(tramiteClave="boleta_notas")
    respuesta = _agente().procesarMensaje(
        "Celular (9 dígitos): ", solicitud, [], camposEsperados=["celular"]
    )
    assert respuesta.solicitud.celular == ""
    assert "Revisemos" not in respuesta.mensaje