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

from .catalogo_tramites import listarCamposAdicionales
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
    "dni o pasaporte": "documentoIdentidad",
    "dni": "documentoIdentidad",
    "pasaporte": "documentoIdentidad",
    "carne de extranjeria": "documentoIdentidad",
    "direccion domiciliaria": "direccion",
    "direccion": "direccion",
    "domicilio": "direccion",
    "n° y/o dpto.": "numeroDepartamento",
    "n° y/o dpto": "numeroDepartamento",
    "numero y/o dpto": "numeroDepartamento",
    "dpto": "numeroDepartamento",
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
    "correo de la empresa": "empresa.correo",
    "correo de la institucion": "empresa.correo",
    "ruc de la empresa": "empresa.ruc",
    "ruc": "empresa.ruc",
    "telefono de la empresa": "empresa.telefono",
    "direccion de la institucion o empresa": "empresa.direccion",
    "direccion de la empresa": "empresa.direccion",
    "nombre, apellidos y cargo a quien va dirigido": "empresa.destinatario",
    "destinatario": "empresa.destinatario",
}

# Etiquetas de los datos propios de cada trámite (``Tramite.camposAdicionales``), p. ej.
# "Curso", "Sección de origen" y "Sección de destino" en la rectificación de matrícula.
# Se generan desde el catálogo para que añadir un dato nuevo no exija tocar este módulo.
for _campoAdicional in listarCamposAdicionales():
    _ETIQUETAS_A_CAMPO.setdefault(
        normalizarClave(_campoAdicional.etiqueta), f"tramite.{_campoAdicional.clave}"
    )

#: Patrón que reconoce cualquiera de las etiquetas de arriba seguida de ":" o "-".
#: Entre la etiqueta y los dos puntos admite una aclaración entre paréntesis, tal como
#: la muestra la plantilla del chat: "Celular (9 dígitos): ..." o "Teléfono fijo
#: (opcional): ...". ``(?<!\w)`` evita reconocer una etiqueta en medio de otra palabra.
_PATRON_ETIQUETA = re.compile(
    r"(?<!\w)("
    + "|".join(re.escape(e) for e in sorted(_ETIQUETAS_A_CAMPO, key=len, reverse=True))
    + r")\s*(?:\([^)\n]*\))?\s*[:\-][ \t]*",
    re.IGNORECASE,
)


def contieneEtiquetas(mensaje: str) -> bool:
    """Indica si el mensaje trae alguna etiqueta de la plantilla ("Celular: ...")."""
    return bool(_PATRON_ETIQUETA.search(quitarTildes(mensaje).lower()))


def _contexto(texto: str, inicio: int) -> str:
    """Fragmento normalizado justo antes de una coincidencia, para desambiguar por palabras clave."""
    return normalizarClave(texto[max(0, inicio - _VENTANA_CONTEXTO) : inicio])


def _contienePalabra(contexto: str, palabras: tuple[str, ...]) -> bool:
    return any(palabra in contexto for palabra in palabras)


def _segmentosEtiquetados(mensaje: str) -> list[tuple[str, int, int]]:
    """Lista de ``(campo, inicioValor, finValor)`` de cada "Etiqueta: valor" del mensaje."""
    normalizado = quitarTildes(mensaje).lower()
    coincidencias = list(_PATRON_ETIQUETA.finditer(normalizado))
    segmentos: list[tuple[str, int, int]] = []
    for indice, coincidencia in enumerate(coincidencias):
        campo = _ETIQUETAS_A_CAMPO.get(coincidencia.group(1).lower())
        if not campo:
            continue
        finValor = coincidencias[indice + 1].start() if indice + 1 < len(coincidencias) else len(mensaje)
        segmentos.append((campo, coincidencia.end(), finValor))
    return segmentos


def _ocultarValoresEtiquetados(mensaje: str) -> str:
    """Copia del mensaje con los valores ya etiquetados reemplazados por espacios.

    Evita que un dato leído por su etiqueta se vuelva a asignar en la búsqueda de datos
    sueltos (por ejemplo, que el "Teléfono de la empresa: 014567890" de la plantilla
    termine también como celular del estudiante, o que el correo del estudiante se copie
    como correo de la empresa). Conserva la longitud para que el contexto siga alineado.
    """
    caracteres = list(mensaje)
    for _, inicio, fin in _segmentosEtiquetados(mensaje):
        for posicion in range(inicio, fin):
            if not caracteres[posicion].isspace():
                caracteres[posicion] = " "
    return "".join(caracteres)


def extraerSegmentosEtiquetados(mensaje: str) -> dict[str, object]:
    """Reconoce pares "Etiqueta: valor" como los que arma la propia pregunta del asistente.

    Es la señal más confiable de todas: si el estudiante escribió literalmente
    "Apellidos y nombres: Pérez, Juan Escuela: Ingeniería Industrial", no hace falta
    ningún modelo para saber qué va en cada campo. Se compara sobre una copia sin
    tildes y en minúsculas (misma longitud que el original, así que los índices
    siguen siendo válidos) para no depender de que el estudiante haya tildado bien.
    """
    cambios: dict[str, object] = {}
    empresa: dict[str, str] = {}
    datosTramite: dict[str, str] = {}

    for campo, inicioValor, finValor in _segmentosEtiquetados(mensaje):
        valor = limpiarTexto(mensaje[inicioValor:finValor]).strip(" .,-")
        if not valor:
            continue
        if campo.startswith("empresa."):
            empresa[campo.split(".", 1)[1]] = valor
        elif campo.startswith("tramite."):
            datosTramite[campo.split(".", 1)[1]] = valor
        else:
            cambios[campo] = valor

    if empresa:
        cambios["empresa"] = empresa
    if datosTramite:
        cambios["datosTramite"] = datosTramite
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
    tramiteEtiquetado = {
        campo: valor
        for campo, valor in etiquetados.pop("datosTramite", {}).items()
        if not solicitud.datosTramite.get(campo)
    }
    if tramiteEtiquetado:
        cambios["datosTramite"] = tramiteEtiquetado
    for campo, valor in etiquetados.items():
        if not getattr(solicitud, campo, None):
            cambios[campo] = valor
    for campo, valor in empresaEtiquetada.items():
        if not getattr(solicitud.empresa, campo, None):
            empresa[campo] = valor

    # Los pasos 2 y 3 solo miran el texto que no estaba ya etiquetado.
    mensajeLibre = _ocultarValoresEtiquetados(mensaje)

    # --- 2) correos electrónicos sueltos, para lo que el paso 1 no haya cubierto ----
    correos = extraerCorreos(mensajeLibre)
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
    for digitos, contexto in extraerNumeros(mensajeLibre):
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


__all__ = ["contieneEtiquetas", "extraerCamposDeterministas", "extraerSegmentosEtiquetados", "extraerCorreos", "extraerNumeros"]