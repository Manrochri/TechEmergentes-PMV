"""Puente entre ``st.secrets`` (Streamlit Community Cloud) y las variables de entorno.

``Configuracion`` (pydantic-settings) solo sabe leer variables de entorno y el archivo
``.env``. Streamlit Community Cloud no despliega ``.env`` (no debería: ahí viven las
claves) — en su lugar, los secretos se pegan en el panel de la app y quedan disponibles
solo dentro del proceso, en ``st.secrets``. Esta función copia lo que encuentre ahí a
``os.environ`` para que ``Configuracion`` los lea exactamente igual que en local, sin que
el resto del código necesite saber dónde está corriendo.

Debe llamarse una sola vez, al principio de ``app.py``, antes de la primera llamada a
``obtenerConfiguracion()``.
"""

from __future__ import annotations

import os

import streamlit as st


def sincronizarSecretosDeStreamlit() -> None:
    """Copia ``st.secrets`` a ``os.environ`` sin pisar variables ya definidas.

    Una variable de entorno real (exportada en el sistema, o ya cargada desde un
    ``.env`` local por ``pydantic-settings``) tiene prioridad sobre ``st.secrets``, así
    que el flujo local con ``.env`` sigue funcionando exactamente igual que antes. Esto
    solo entra en juego cuando no hay ``.env`` local, como en Streamlit Community Cloud.
    """
    try:
        secretos = st.secrets
    except Exception:
        return  # sin secrets.toml configurado: nada que sincronizar

    try:
        claves = list(secretos.keys())
    except Exception:
        return

    for clave in claves:
        valor = secretos[clave]
        if isinstance(valor, str) and clave.isupper() and clave not in os.environ:
            os.environ[clave] = valor


__all__ = ["sincronizarSecretosDeStreamlit"]
