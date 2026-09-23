"""Pruebas de :func:`seleccionarServicioLlm`.

Sustituyen ``ServicioOllama`` y ``ServicioGemini`` por dobles de prueba: lo que se
verifica es la lógica de selección (automática y con el switch manual), no los clientes
reales de cada proveedor, que ya se prueban por su cuenta.
"""

from __future__ import annotations

from unittest.mock import patch

from src.configuracion import Configuracion
from src.servicio_llm import NOMBRE_GEMINI, NOMBRE_QWEN, seleccionarServicioLlm


class _ProveedorFalso:
    """Doble de prueba con la interfaz mínima de un servicio de LLM."""

    def __init__(self, disponible: bool, detalle: str) -> None:
        self._disponible = disponible
        self._detalle = detalle

    def verificarDisponibilidad(self) -> tuple[bool, str]:
        return self._disponible, self._detalle


def _configuracion(proveedorLlmManual: str = "") -> Configuracion:
    return Configuracion(_env_file=None, PROVEEDOR_LLM_MANUAL=proveedorLlmManual)


def testModoAutomaticoUsaQwenCuandoEstaDisponible() -> None:
    with (
        patch("src.servicio_llm.ServicioOllama", return_value=_ProveedorFalso(True, "Qwen3 ok")),
        patch("src.servicio_llm.ServicioGemini") as gemini,
    ):
        servicio, nombre, detalle = seleccionarServicioLlm(_configuracion())

    assert nombre == NOMBRE_QWEN
    assert detalle == "Qwen3 ok"
    gemini.assert_not_called()  # no debe ni instanciarse si Qwen3 ya respondió


def testModoAutomaticoCaeAGeminiCuandoQwenNoEstaDisponible() -> None:
    with (
        patch(
            "src.servicio_llm.ServicioOllama",
            return_value=_ProveedorFalso(False, "Ollama apagado"),
        ),
        patch(
            "src.servicio_llm.ServicioGemini",
            return_value=_ProveedorFalso(True, "Gemini ok"),
        ),
    ):
        servicio, nombre, detalle = seleccionarServicioLlm(_configuracion())

    assert nombre == NOMBRE_GEMINI
    assert "Ollama apagado" in detalle
    assert "Gemini ok" in detalle


def testSwitchManualFuerzaQwenSinImportarDisponibilidad() -> None:
    with (
        patch(
            "src.servicio_llm.ServicioOllama",
            return_value=_ProveedorFalso(False, "Ollama apagado"),
        ) as ollama,
        patch("src.servicio_llm.ServicioGemini") as gemini,
    ):
        servicio, nombre, detalle = seleccionarServicioLlm(_configuracion("qwen"))

    assert nombre == NOMBRE_QWEN
    assert "[Switch manual]" in detalle
    ollama.assert_called_once()
    gemini.assert_not_called()


def testSwitchManualFuerzaGeminiSinComprobarQwenPrimero() -> None:
    with (
        patch("src.servicio_llm.ServicioOllama") as ollama,
        patch(
            "src.servicio_llm.ServicioGemini",
            return_value=_ProveedorFalso(True, "Gemini ok"),
        ),
    ):
        servicio, nombre, detalle = seleccionarServicioLlm(_configuracion("gemini"))

    assert nombre == NOMBRE_GEMINI
    assert "[Switch manual]" in detalle
    ollama.assert_not_called()  # el switch manual se salta la comprobación de Qwen3


def testValorInvalidoDelSwitchCaeAModoAutomatico() -> None:
    with (
        patch("src.servicio_llm.ServicioOllama", return_value=_ProveedorFalso(True, "Qwen3 ok")),
        patch("src.servicio_llm.ServicioGemini") as gemini,
    ):
        servicio, nombre, detalle = seleccionarServicioLlm(_configuracion("algo-invalido"))

    assert nombre == NOMBRE_QWEN
    gemini.assert_not_called()