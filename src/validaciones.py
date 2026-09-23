"""Validaciones y normalizaciones de datos peruanos usados en el FUT.

Todas las funciones son puras: no dependen de Streamlit ni de Ollama, por lo que se
pueden probar de forma aislada (ver ``tests/test_validaciones.py``).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

_MESES_ES: tuple[str, ...] = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "setiembre", "octubre", "noviembre", "diciembre",
)

_PATRON_CORREO = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_PATRON_ESPACIOS = re.compile(r"\s+")


def limpiarTexto(valor: str | None) -> str:
    """Normaliza espacios en blanco y recorta los extremos."""
    if not valor:
        return ""
    return _PATRON_ESPACIOS.sub(" ", str(valor)).strip()


def soloDigitos(valor: str | None) -> str:
    """Devuelve únicamente los dígitos presentes en el valor."""
    if not valor:
        return ""
    return re.sub(r"\D", "", str(valor))


def aMayusculas(valor: str | None) -> str:
    """Pasa a mayúsculas conservando las tildes (se usa en apellidos y nombres)."""
    return limpiarTexto(valor).upper()


def quitarTildes(valor: str) -> str:
    """Versión sin diacríticos, útil para comparar texto escrito por el usuario."""
    descompuesto = unicodedata.normalize("NFD", valor)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def normalizarClave(valor: str) -> str:
    """Convierte un texto libre en una clave comparable (minúsculas, sin tildes)."""
    return _PATRON_ESPACIOS.sub(" ", quitarTildes(limpiarTexto(valor)).lower()).strip()


def esDniValido(valor: str | None) -> bool:
    """El DNI peruano tiene exactamente 8 dígitos."""
    return len(soloDigitos(valor)) == 8


def esDocumentoIdentidadValido(valor: str | None) -> bool:
    """Acepta DNI (8 dígitos), pasaporte o carné de extranjería (6 a 12 alfanuméricos)."""
    texto = limpiarTexto(valor).replace(" ", "")
    if not texto:
        return False
    if esDniValido(texto):
        return True
    return bool(re.fullmatch(r"[A-Za-z0-9]{6,12}", texto))


def esRucValido(valor: str | None) -> bool:
    """Verifica que el RUC tenga exactamente 11 dígitos."""
    
    digitos = soloDigitos(valor)

    return len(digitos) == 11


def esCorreoValido(valor: str | None) -> bool:
    """Validación pragmática de correo electrónico."""
    return bool(_PATRON_CORREO.fullmatch(limpiarTexto(valor)))


def esTelefonoValido(valor: str | None, minimo: int = 6, maximo: int = 15) -> bool:
    """Valida longitud de un teléfono fijo o celular una vez extraídos los dígitos."""
    return minimo <= len(soloDigitos(valor)) <= maximo


def esCodigoEstudianteValido(valor: str | None) -> bool:
    """El código de la UNFV suele tener entre 7 y 12 caracteres alfanuméricos."""
    texto = limpiarTexto(valor).replace(" ", "")
    return bool(re.fullmatch(r"[A-Za-z0-9\-]{6,12}", texto))


def normalizarCelular(valor: str | None) -> str:
    """Devuelve el celular en formato de 9 dígitos cuando es posible."""
    digitos = soloDigitos(valor)
    if digitos.startswith("51") and len(digitos) == 11:
        digitos = digitos[2:]
    return digitos


def formatearFechaLarga(fecha: date | None = None) -> str:
    """Devuelve una fecha en el formato usado en los trámites: ``12 de marzo de 2026``."""
    fecha = fecha or date.today()
    return f"{fecha.day} de {_MESES_ES[fecha.month - 1]} de {fecha.year}"


def construirLugarYFecha(ciudad: str, fecha: date | None = None) -> str:
    """Arma la cadena del campo ``Lugar y Fecha`` del FUT."""
    return f"{limpiarTexto(ciudad) or 'Lima'}, {formatearFechaLarga(fecha)}"


__all__ = [
    "limpiarTexto",
    "soloDigitos",
    "aMayusculas",
    "quitarTildes",
    "normalizarClave",
    "esDniValido",
    "esDocumentoIdentidadValido",
    "esRucValido",
    "esCorreoValido",
    "esTelefonoValido",
    "esCodigoEstudianteValido",
    "normalizarCelular",
    "formatearFechaLarga",
    "construirLugarYFecha",
]
