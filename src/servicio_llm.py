"""Selección del proveedor de modelo de lenguaje.

Regla por defecto (modo automático): se comprueba primero si Qwen3 está disponible en
Ollama; si no lo está (servidor apagado, modelo no descargado, etc.), se usa
automáticamente la API de Gemini como respaldo.

``PROVEEDOR_LLM_MANUAL`` es un switch pensado **solo para pruebas**: fuerza un
proveedor concreto sin comprobar primero si Qwen3 está disponible. Déjalo vacío (su
valor por defecto) para el comportamiento automático descrito arriba.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from .configuracion import Configuracion, obtenerConfiguracion
from .servicio_gemini import ServicioGemini
from .servicio_ollama import ServicioOllama

registrador = logging.getLogger(__name__)

#: Nombres legibles del proveedor activo, usados también en la interfaz (app.py).
NOMBRE_QWEN: str = "Qwen3 (Ollama, local)"
NOMBRE_GEMINI: str = "Gemini 3.6 Flash (API de Google, respaldo)"

_VALORES_VALIDOS_SWITCH: frozenset[str] = frozenset({"", "qwen", "gemini"})


class ServicioLlm(Protocol):
    """Interfaz común que implementan ``ServicioOllama`` y ``ServicioGemini``.

    ``AgenteFut`` solo depende de esta interfaz, nunca de una implementación concreta,
    así que puede recibir cualquiera de los dos servicios indistintamente.
    """

    def verificarDisponibilidad(self) -> tuple[bool, str]: ...

    def conversar(
        self, mensajes: list[dict[str, str]], temperatura: float | None = None
    ) -> str: ...

    def extraerEstructurado(
        self,
        mensajes: list[dict[str, str]],
        esquema: dict[str, Any],
        temperatura: float = 0.0,
    ) -> dict[str, Any]: ...


def seleccionarServicioLlm(
    configuracion: Configuracion | None = None,
) -> tuple[ServicioLlm, str, str]:
    """Elige y construye el servicio de LLM que debe usar el agente.

    Devuelve ``(servicio, nombreProveedor, detalleEstado)``. ``nombreProveedor`` es el
    texto que la interfaz debe mostrar (ver ``NOMBRE_QWEN`` / ``NOMBRE_GEMINI``);
    ``detalleEstado`` es la explicación legible de por qué se eligió ese proveedor,
    igual en espíritu al mensaje que ya devolvía ``ServicioOllama.verificarDisponibilidad``.
    """
    configuracion = configuracion or obtenerConfiguracion()
    switch = configuracion.proveedorLlmManual.strip().lower()
    if switch not in _VALORES_VALIDOS_SWITCH:
        registrador.warning(
            "PROVEEDOR_LLM_MANUAL='%s' no es válido (usa 'qwen', 'gemini' o vacío); "
            "se ignora y se usa selección automática.", switch,
        )
        switch = ""

    if switch == "qwen":
        registrador.info("Switch manual: forzando Qwen3 (Ollama) sin comprobar disponibilidad real.")
        servicio = ServicioOllama(configuracion)
        _, detalle = servicio.verificarDisponibilidad()
        return servicio, NOMBRE_QWEN, f"[Switch manual] {detalle}"

    if switch == "gemini":
        registrador.info("Switch manual: forzando Gemini sin comprobar antes Qwen3.")
        servicio = ServicioGemini(configuracion)
        _, detalle = servicio.verificarDisponibilidad()
        return servicio, NOMBRE_GEMINI, f"[Switch manual] {detalle}"

    # Modo automático (por defecto): Qwen3 primero, Gemini solo si Qwen3 no responde.
    servicioOllama = ServicioOllama(configuracion)
    disponibleQwen, detalleQwen = servicioOllama.verificarDisponibilidad()
    if disponibleQwen:
        return servicioOllama, NOMBRE_QWEN, detalleQwen

    registrador.warning("Qwen3 no disponible (%s); usando Gemini como respaldo.", detalleQwen)
    servicioGemini = ServicioGemini(configuracion)
    disponibleGemini, detalleGemini = servicioGemini.verificarDisponibilidad()
    prefijo = "Qwen3 no disponible" if disponibleGemini else "Qwen3 y Gemini no disponibles"
    detalle = f"{prefijo}. Qwen3: {detalleQwen} · Gemini: {detalleGemini}"
    return servicioGemini, NOMBRE_GEMINI, detalle


__all__ = ["seleccionarServicioLlm", "ServicioLlm", "NOMBRE_QWEN", "NOMBRE_GEMINI"]