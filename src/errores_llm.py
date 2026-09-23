"""Excepción base compartida por todos los proveedores de LLM.

Vive en su propio módulo (en vez de en ``servicio_ollama.py`` o ``servicio_gemini.py``)
para que ninguno de los dos clientes concretos dependa del otro ni de ``servicio_llm``:
los tres solo dependen de esta base. ``agente_fut.py`` captura ``ErrorServicioLlm`` en
vez de la excepción concreta de cada proveedor, así que el resto del código no necesita
saber si en ese turno se usó Qwen3 o Gemini.
"""

from __future__ import annotations


class ErrorServicioLlm(RuntimeError):
    """Error de comunicación o de configuración con un proveedor de LLM."""


__all__ = ["ErrorServicioLlm"]