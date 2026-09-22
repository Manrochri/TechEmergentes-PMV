"""Comprueba que el entorno está listo antes de levantar la aplicación.

Uso:
    python scripts/verificar_entorno.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.configuracion import obtenerConfiguracion  # noqa: E402
from src.servicio_ollama import ServicioOllama  # noqa: E402

MARCA_OK = "[OK]   "
MARCA_ERROR = "[ERROR]"


def verificarVersionPython() -> bool:
    """Requiere Python 3.11 o superior."""
    correcto = sys.version_info >= (3, 11)
    marca = MARCA_OK if correcto else MARCA_ERROR
    print(f"{marca} Python {sys.version.split()[0]} (se requiere 3.11+)")
    return correcto


def verificarDependencias() -> bool:
    """Confirma que las librerías principales están instaladas."""
    modulos = ("streamlit", "ollama", "pydantic", "pydantic_settings", "pypdf", "reportlab")
    faltantes: list[str] = []
    for modulo in modulos:
        try:
            __import__(modulo)
        except ImportError:
            faltantes.append(modulo)
    if faltantes:
        print(f"{MARCA_ERROR} Faltan dependencias: {', '.join(faltantes)}")
        print("        Ejecuta: pip install -r requirements.txt")
        return False
    print(f"{MARCA_OK} Dependencias instaladas")
    return True


def verificarArchivos() -> bool:
    """Confirma que la plantilla del FUT y el logo están en su sitio."""
    configuracion = obtenerConfiguracion()
    problemas = configuracion.verificarRutas()
    for problema in problemas:
        print(f"{MARCA_ERROR} {problema}")
    if not problemas:
        print(f"{MARCA_OK} Plantilla del FUT y logo encontrados")
    return not problemas


def verificarOllama() -> bool:
    """Confirma que el servidor responde y que el modelo está descargado."""
    disponible, detalle = ServicioOllama().verificarDisponibilidad()
    print(f"{MARCA_OK if disponible else MARCA_ERROR} {detalle}")
    return disponible


def principal() -> int:
    print("Verificación del entorno - Asistente de trámites FIIS")
    print("-" * 58)
    resultados = [
        verificarVersionPython(),
        verificarDependencias(),
        verificarArchivos(),
        verificarOllama(),
    ]
    print("-" * 58)
    if all(resultados):
        print("Todo listo. Ejecuta:  streamlit run app.py")
        return 0
    print("Corrige los puntos marcados con [ERROR] y vuelve a ejecutar este script.")
    return 1


if __name__ == "__main__":
    raise SystemExit(principal())
