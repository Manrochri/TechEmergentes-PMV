"""Extracción determinista de los campos con formato validable.

Esta capa existe porque depender solo del modelo de lenguaje para campos que ya tienen
una forma reconocible (un DNI son 8 dígitos, un correo tiene ``@``) es fragil: si Ollama
no está disponible, tarda, o devuelve un JSON mal formado, esos campos jamás se
completarían y la conversación quedaría pidiendo lo mismo para siempre.

Aquí no se usa ningún modelo: son expresiones regulares sobre el mensaje del estudiante.
Cubre tanto segmentos explícitamente etiquetados ("Apellidos y nombres: ...") como datos
sueltos con forma reconocible (DNI, celular, correo, RUC). El texto verdaderamente libre
sin ninguna etiqueta (una dirección mencionada de pasada, sin la palabra "dirección"
delante) sigue dependiendo del modelo o de la asignación directa de último recurso en
``agente_fut.py``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .validaciones import (
    esCorreoValido,
    esDniValido,
    esRucValido,
    limpiarTexto,
    normalizarClave,
    quitarTildes,
    soloDigitos,
)

if TYPE_CHECKING:
    from .modelos import SolicitudFut

_PATRON_CORREO = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PATRON_NUMERO = re.compile(r"(?<!\d)\d[\d\-.\s]{4,}\d(?!\d)")

_VENTANA_CONTEXTO = 24

_PALABRAS_FIJO = ("fijo",)
_PALABRAS_CODIGO = ("codigo", "código", "code")
_PALABRAS_EMPRESA = (
    "empresa", "institucion", "institución", "practica", "práctica",
    "centro de practicas", "centro de prácticas", "trabajo",
)

#: Etiquetas explícitas que el estudiante puede escribir ("Apellidos y nombres: ...").
#: Las claves ya están sin tildes y en minúsculas porque se comparan contra texto
#: normalizado con :func:`quitarTildes`; las más largas van primero para que, por
#: ejemplo, "escuela profesional" no quede opacada por "escuela".
_ETIQUETAS_A_CAMPO: dict[str, str] = {
    "apellidos y nombres": "apellidosNombres",
    "apellidos y nombre": "apellidosNombres",
    "nombres y apellidos": "apellidosNombres",
    "nombre completo": "apellidosNombres",
    "escuela profesional": "escuelaProfesional",
    "escuela": "escuelaProfesional",
    "codigo de estudiante": "codigoEstudiante",
    "codigo estudiante": "codigoEstudiante",
    "codigo": "codigoEstudiante",
    "documento de identidad": "documentoIdentidad",
    "dni": "documentoIdentidad",
    "pasaporte": "documentoIdentidad",
    "carne de extranjeria": "documentoIdentidad",
    "direccion domiciliaria": "direccion",
    "direccion": "direccion",
    "domicilio": "direccion",
    "distrito": "distrito",
    "telefono fijo": "telefonoFijo",
    "celular": "celular",
    "correo electronico": "correoElectronico",
    "correo": "correoElectronico",
    "email": "correoElectronico",
    "dependencia": "dependencia",
    "nombre de la institucion o empresa": "empresa.nombreInstitucion",
    "nombre de la empresa": "empresa.nombreInstitucion",
    "institucion o empresa": "empresa.nombreInstitucion",
    "empresa": "empresa.nombreInstitucion",
    "ruc de la empresa": "empresa.ruc",
    "ruc": "empresa.ruc",
    "telefono de la empresa": "empresa.telefono",
    "direccion de la institucion o empresa": "empresa.direccion",
    "direccion de la empresa": "empresa.direccion",
    "nombre, apellidos y cargo a quien va dirigido": "empresa.destinatario",
    "destinatario": "empresa.destinatario",
}

#: Patrón que reconoce cualquiera de las etiquetas de arriba seguida de ":" o "-".
_PATRON_ETIQUETA = re.compile(
    r"(" + "|".join(re.escape(e) for e in sorted(_ETIQUETAS_A_CAMPO, key=len, reverse=True)) + r")\s*[:\-]\s*",
    re.IGNORECASE,
)


def _contexto(texto: str, inicio: int) -> str:
    """Fragmento normalizado justo antes de una coincidencia, para desambiguar por palabras clave."""
    return normalizarClave(texto[max(0, inicio - _VENTANA_CONTEXTO) : inicio])


def _contienePalabra(contexto: str, palabras: tuple[str, ...]) -> bool:
    return any(palabra in contexto for palabra in palabras)


def extraerSegmentosEtiquetados(mensaje: str) -> dict[str, object]:
    """Reconoce pares "Etiqueta: valor" como los que arma la propia pregunta del asistente.

    Es la señal más confiable de todas: si el estudiante escribió literalmente
    "Apellidos y nombres: Pérez, Juan Escuela: Ingeniería Industrial", no hace falta
    ningún modelo para saber qué va en cada campo. Se compara sobre una copia sin
    tildes y en minúsculas (misma longitud que el original, así que los índices
    siguen siendo válidos) para no depender de que el estudiante haya tildado bien.
    """
    normalizado = quitarTildes(mensaje).lower()
    coincidencias = list(_PATRON_ETIQUETA.finditer(normalizado))
    if not coincidencias:
        return {}

    cambios: dict[str, object] = {}
    empresa: dict[str, str] = {}

    for indice, coincidencia in enumerate(coincidencias):
        campo = _ETIQUETAS_A_CAMPO.get(coincidencia.group(1).lower())
        if not campo:
            continue
        inicioValor = coincidencia.end()
        finValor = coincidencias[indice + 1].start() if indice + 1 < len(coincidencias) else len(mensaje)
        valor = limpiarTexto(mensaje[inicioValor:finValor]).strip(" .,-")
        if not valor:
            continue
        if campo.startswith("empresa."):
            empresa[campo.split(".", 1)[1]] = valor
        else:
            cambios[campo] = valor

    if empresa:
        cambios["empresa"] = empresa
    return cambios


def extraerCorreos(mensaje: str) -> list[tuple[str, str]]:
    """Todos los correos válidos del mensaje, con su contexto previo."""
    correos = []
    for coincidencia in _PATRON_CORREO.finditer(mensaje):
        correo = coincidencia.group(0)
        if esCorreoValido(correo):
            correos.append((correo, _contexto(mensaje, coincidencia.start())))
    return correos


def extraerNumeros(mensaje: str) -> list[tuple[str, str]]:
    """Todas las secuencias numéricas del mensaje (limpias de separadores), con contexto."""
    numeros = []
    for coincidencia in _PATRON_NUMERO.finditer(mensaje):
        digitos = soloDigitos(coincidencia.group(0))
        if digitos:
            numeros.append((digitos, _contexto(mensaje, coincidencia.start())))
    return numeros


def extraerCamposDeterministas(mensaje: str, solicitud: "SolicitudFut") -> dict[str, object]:
    """Detecta datos con forma reconocible en texto libre, sin usar ningún modelo.

    Combina dos señales, de mayor a menor confianza:
    1. Segmentos explícitamente etiquetados ("Apellidos y nombres: ...").
    2. Correos, números de documento/celular/RUC sueltos, desambiguados por contexto.

    Solo propone un valor para un campo si ese campo todavía está vacío en la solicitud,
    de modo que nunca sobrescribe un dato ya confirmado por el estudiante en un turno
    anterior. Las correcciones explícitas ("en realidad mi celular es...") las sigue
    resolviendo el modelo de lenguaje, que sí tiene el contexto conversacional completo.
    """
    cambios: dict[str, object] = {}
    empresa: dict[str, str] = {}

    # --- 1) segmentos etiquetados: la señal más confiable ---------------------------
    etiquetados = extraerSegmentosEtiquetados(mensaje)
    empresaEtiquetada = etiquetados.pop("empresa", {})
    for campo, valor in etiquetados.items():
        if not getattr(solicitud, campo, None):
            cambios[campo] = valor
    for campo, valor in empresaEtiquetada.items():
        if not getattr(solicitud.empresa, campo, None):
            empresa[campo] = valor

    # --- 2) correos electrónicos sueltos, para lo que el paso 1 no haya cubierto ----
    correos = extraerCorreos(mensaje)
    if correos:
        primerCorreo, primerContexto = correos[0]
        primeroEsEmpresa = _contienePalabra(primerContexto, _PALABRAS_EMPRESA)

        if solicitud.esCartaPresentacion and primeroEsEmpresa and not solicitud.empresa.correo and not empresa.get("correo"):
            empresa["correo"] = primerCorreo
        elif not solicitud.correoElectronico and not cambios.get("correoElectronico"):
            cambios["correoElectronico"] = primerCorreo
        elif solicitud.esCartaPresentacion and not solicitud.empresa.correo and not empresa.get("correo"):
            empresa["correo"] = primerCorreo

        if len(correos) > 1:
            segundoCorreo, _ = correos[1]
            if solicitud.esCartaPresentacion and not empresa.get("correo") and not solicitud.empresa.correo:
                empresa["correo"] = segundoCorreo
            elif not cambios.get("correoElectronico") and not solicitud.correoElectronico:
                cambios["correoElectronico"] = segundoCorreo

    # --- 3) secuencias numéricas sueltas, para lo que siga sin cubrirse -------------
    for digitos, contexto in extraerNumeros(mensaje):
        longitud = len(digitos)
        esEmpresa = _contienePalabra(contexto, _PALABRAS_EMPRESA)

        if longitud == 11 and solicitud.esCartaPresentacion and esRucValido(digitos):
            if not solicitud.empresa.ruc and not empresa.get("ruc"):
                empresa["ruc"] = digitos
            continue

        if longitud == 9:
            if esEmpresa and solicitud.esCartaPresentacion and not solicitud.empresa.telefono and not empresa.get("telefono"):
                empresa["telefono"] = digitos
            elif _contienePalabra(contexto, _PALABRAS_FIJO) and not solicitud.telefonoFijo and not cambios.get("telefonoFijo"):
                cambios["telefonoFijo"] = digitos
            elif not solicitud.celular and not cambios.get("celular"):
                cambios["celular"] = digitos
            continue

        if longitud == 8:
            if _contienePalabra(contexto, _PALABRAS_CODIGO) and not solicitud.codigoEstudiante and not cambios.get("codigoEstudiante"):
                cambios["codigoEstudiante"] = digitos
            elif esDniValido(digitos) and not solicitud.documentoIdentidad and not cambios.get("documentoIdentidad"):
                cambios["documentoIdentidad"] = digitos
            continue

        if 6 <= longitud <= 7 and _contienePalabra(contexto, _PALABRAS_FIJO) and not solicitud.telefonoFijo and not cambios.get("telefonoFijo"):
            cambios["telefonoFijo"] = digitos
            continue

        if 6 <= longitud <= 12 and _contienePalabra(contexto, _PALABRAS_CODIGO) and not solicitud.codigoEstudiante and not cambios.get("codigoEstudiante"):
            cambios["codigoEstudiante"] = digitos
            continue

    if empresa:
        cambios["empresa"] = empresa
    return cambios


__all__ = ["extraerCamposDeterministas", "extraerSegmentosEtiquetados", "extraerCorreos", "extraerNumeros"]
