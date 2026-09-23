"""Pruebas del cliente de Gemini.

No requieren red ni una clave de API real: prueban directamente los métodos que
traducen mensajes al formato de Gemini, extraen el texto de una respuesta y analizan el
JSON devuelto, incluidos los casos ruidosos que ya se cubren para Ollama.
"""

from __future__ import annotations

from src.configuracion import Configuracion
from src.servicio_gemini import ServicioGemini


def _servicio(**overrides: object) -> ServicioGemini:
    return ServicioGemini(Configuracion(_env_file=None, **overrides))


def testAnalizaJsonLimpio() -> None:
    servicio = _servicio()
    assert servicio._analizarJson('{"celular": "987654321"}') == {"celular": "987654321"}


def testAnalizaJsonDentroDeCercaMarkdown() -> None:
    servicio = _servicio()
    contenido = '```json\n{"celular": "987654321"}\n```'
    assert servicio._analizarJson(contenido) == {"celular": "987654321"}


def testAnalizaJsonConTextoAlrededor() -> None:
    servicio = _servicio()
    contenido = 'Aquí tienes los datos: {"celular": "987654321"} espero que ayude.'
    assert servicio._analizarJson(contenido) == {"celular": "987654321"}


def testDevuelveDiccionarioVacioSiNoHayJson() -> None:
    servicio = _servicio()
    assert servicio._analizarJson("no encontré ningún dato nuevo") == {}


def testDevuelveDiccionarioVacioSiElJsonEsInvalido() -> None:
    servicio = _servicio()
    assert servicio._analizarJson("{celular: 987654321}") == {}


def testDevuelveDiccionarioVacioParaCadenaVacia() -> None:
    servicio = _servicio()
    assert servicio._analizarJson("") == {}


def testExtraerTextoConcatenaLasPartesDelPrimerCandidato() -> None:
    datos = {
        "candidates": [
            {"content": {"parts": [{"text": "Hola, "}, {"text": "mundo."}], "role": "model"}}
        ]
    }
    assert ServicioGemini._extraerTexto(datos) == "Hola, mundo."


def testExtraerTextoDevuelveVacioSiNoHayCandidatos() -> None:
    assert ServicioGemini._extraerTexto({"candidates": []}) == ""
    assert ServicioGemini._extraerTexto({}) == ""


def testConstruirCuerpoSeparaElSistemaYTraduceRoles() -> None:
    servicio = _servicio()
    mensajes = [
        {"role": "system", "content": "Eres un asistente."},
        {"role": "user", "content": "Hola"},
        {"role": "assistant", "content": "¿En qué te ayudo?"},
    ]
    cuerpo = servicio._construirCuerpo(mensajes, temperatura=None)

    assert cuerpo["systemInstruction"] == {"parts": [{"text": "Eres un asistente."}]}
    assert cuerpo["contents"] == [
        {"role": "user", "parts": [{"text": "Hola"}]},
        {"role": "model", "parts": [{"text": "¿En qué te ayudo?"}]},
    ]
    # Sin temperatura explícita, usa la de la configuración (por defecto 0.2).
    assert cuerpo["generationConfig"]["temperature"] == 0.2


def testConstruirCuerpoRespetaLaTemperaturaExplicita() -> None:
    servicio = _servicio()
    cuerpo = servicio._construirCuerpo([{"role": "user", "content": "Hola"}], temperatura=0.9)
    assert cuerpo["generationConfig"]["temperature"] == 0.9


def testVerificarDisponibilidadEsFalsoSinClave() -> None:
    servicio = _servicio(GEMINI_API_KEY="")
    disponible, detalle = servicio.verificarDisponibilidad()
    assert disponible is False
    assert "GEMINI_API_KEY" in detalle