"""Pruebas de resiliencia del agente ante un modelo de lenguaje poco fiable.

Estas pruebas reproducen el problema reportado: si Ollama nunca devuelve un JSON útil
(el peor caso posible), la conversación no debe quedar atascada pidiendo el mismo dato
para siempre. El extractor determinista y la asignación directa de respuestas son las
dos redes de seguridad que lo evitan.
"""

from __future__ import annotations

from src.agente_fut import AgenteFut
from src.modelos import DatosEmpresa, SolicitudFut


class _OllamaSiempreRoto:
    """Simula un servidor de Ollama que jamás devuelve JSON ni texto útil."""

    def extraerEstructurado(self, mensajes, esquema, temperatura: float = 0.0) -> dict:
        return {}

    def conversar(self, mensajes, temperatura: float | None = None) -> str:
        return ""


def _agente() -> AgenteFut:
    return AgenteFut(servicio=_OllamaSiempreRoto())


def testElFlujoCompletaUnDatoPorTurnoSinModelo() -> None:
    """Reproduce el reporte: cada respuesta es la contestación directa a lo preguntado."""
    agente = _agente()
    solicitud = SolicitudFut()
    historial: list[dict[str, str]] = []
    camposEsperados: list[str] = []

    turnos = [
        "necesito una carta de presentacion para mis practicas",
        "Quispe Ramírez, Christian",
        "Ingeniería de Sistemas",
        "2021015432",
        "74125896",
        "Av. Los Próceres 1450",
        "San Isidro",
        "987654321",
        "christian.quispe@unfv.edu.pe",
        "Consultora Andina S.A.C.",
        "20512345671",
        "rrhh@andina.com.pe",
        "014567890",
        "Av. Javier Prado Este 2050",
        "Ing. María Torres - Jefa de RR. HH.",
    ]

    respuesta = None
    for texto in turnos:
        respuesta = agente.procesarMensaje(texto, solicitud, historial, camposEsperados)
        solicitud = respuesta.solicitud
        camposEsperados = respuesta.camposPreguntados
        historial.append({"role": "user", "content": texto})
        historial.append({"role": "assistant", "content": respuesta.mensaje})

    assert respuesta is not None
    assert respuesta.formularioListo
    assert respuesta.pdf


def testUnaPreguntaDelEstudianteNoSeAsignaComoDato() -> None:
    agente = _agente()
    solicitud = SolicitudFut(tramiteClave="boleta_notas")
    respuesta = agente.procesarMensaje(
        "¿cuánto cuesta este trámite?", solicitud, [], camposEsperados=["apellidosNombres"]
    )
    assert respuesta.solicitud.apellidosNombres == ""


def testUnSaludoNoSeAsignaComoDato() -> None:
    agente = _agente()
    solicitud = SolicitudFut(tramiteClave="boleta_notas")
    respuesta = agente.procesarMensaje(
        "hola, gracias", solicitud, [], camposEsperados=["apellidosNombres"]
    )
    assert respuesta.solicitud.apellidosNombres == ""


def testUnValorConFormatoInvalidoSePideCorregir() -> None:
    """La asignación directa no valida el contenido: erroresDeFormato lo hace después."""
    agente = _agente()
    solicitud = SolicitudFut(tramiteClave="boleta_notas")
    respuesta = agente.procesarMensaje(
        "no tengo DNI todavía", solicitud, [], camposEsperados=["documentoIdentidad"]
    )
    # Se asignó el texto tal cual, pero al no pasar el formato se pide confirmarlo de nuevo
    # en vez de aceptarlo silenciosamente.
    assert respuesta.solicitud.documentoIdentidad
    assert "documento" in respuesta.mensaje.lower() or "DNI" in respuesta.mensaje


def testUnFalloDeGeneracionInesperadoNoRompeLaConversacion(monkeypatch) -> None:
    """Si rellenarFut lanza algo que no es ErrorLlenadoFut, el agente igual responde."""
    import src.agente_fut as modulo

    def _rellenarRoto(solicitud, ruta):
        raise ValueError("fallo inesperado simulado")

    monkeypatch.setattr(modulo, "rellenarFut", _rellenarRoto)

    agente = _agente()
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
        empresa=DatosEmpresa(
            nombreInstitucion="Consultora Andina S.A.C.",
            ruc="20512345671",
            correo="rrhh@andina.com.pe",
            telefono="014567890",
            direccion="Av. Javier Prado Este 2050",
            destinatario="Ing. María Torres - Jefa de RR. HH.",
        ),
    )

    respuesta = agente.completarYGenerar(solicitud, [], [])
    assert respuesta.pdf is None
    assert respuesta.mensaje  # el estudiante recibe un mensaje, no una excepción sin manejar


class _OllamaQueAlucinaCompletitud:
    """Reproduce el bug reportado: no extrae nada, pero el chat afirma que ya terminó."""

    def extraerEstructurado(self, mensajes, esquema, temperatura: float = 0.0) -> dict:
        return {}

    def conversar(self, mensajes, temperatura: float | None = None) -> str:
        return "Ya tengo todos los datos necesarios. Tu trámite está listo, ya puedes imprimir el FUT."


def testSeDescartaUnaAfirmacionFalsaDeCompletitud() -> None:
    """Reproduce el reporte: el modelo dice 'ya está listo' aunque falten casi todos los datos."""
    agente = AgenteFut(servicio=_OllamaQueAlucinaCompletitud())
    solicitud = SolicitudFut(tramiteClave="rectificacion_matricula")

    respuesta = agente.procesarMensaje(
        "Apellidos y nombres: Perez, Juan Escuela: Ingeniería industrial",
        solicitud, [], camposEsperados=[],
    )

    assert "listo" not in respuesta.mensaje.lower()
    assert "imprimir" not in respuesta.mensaje.lower()
    assert not respuesta.formularioListo
    assert respuesta.pdf is None
    # Pero los datos con etiqueta explícita sí deben haberse capturado.
    assert respuesta.solicitud.apellidosNombres == "PEREZ, JUAN"
    assert respuesta.solicitud.escuelaProfesional == "Ingeniería industrial"


def testElMensajeSiempreIncluyeLoQueRealmenteFalta() -> None:
    """El pie '_Aún falta: ...' refleja el estado real, no lo que diga el modelo."""
    agente = AgenteFut(servicio=_OllamaQueAlucinaCompletitud())
    solicitud = SolicitudFut(tramiteClave="boleta_notas")

    respuesta = agente.procesarMensaje("hola", solicitud, [], camposEsperados=[])
    assert "Aún falta" in respuesta.mensaje
