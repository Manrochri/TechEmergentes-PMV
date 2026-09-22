"""Pruebas del análisis tolerante de JSON en las respuestas de Ollama.

No requieren un servidor de Ollama real: prueban directamente el método privado que
recorta y parsea el contenido de la respuesta, incluidos los casos ruidosos que en la
práctica hacían que la extracción de datos fallara en silencio.
"""

from __future__ import annotations

from unittest.mock import patch

from src.servicio_ollama import ServicioOllama


def _servicio() -> ServicioOllama:
    with patch("src.servicio_ollama.Client"):
        return ServicioOllama()


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
