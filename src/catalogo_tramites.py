"""Catálogo de trámites de la FIIS y numerales del reverso del FUT.

Fuentes
-------
* ``assets/Nuevos-codigos-pago-1.pdf`` — códigos de pago y montos vigentes de la FIIS.
* Reverso de ``assets/FUT_SG-FORMULARIO.pdf`` — lista oficial de numerales de trámite.

Las dependencias de destino son valores por defecto razonables y **editables**: el
estudiante siempre puede corregirlas desde el panel de revisión antes de generar el PDF.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .validaciones import normalizarClave

# ---------------------------------------------------------------------------
# Numeral 34 del reverso del FUT: "Otros". La mayoría de trámites de facultad
# no figuran en la lista de Secretaría General, así que se declaran como "Otros"
# y el detalle se precisa en la sumilla.
# ---------------------------------------------------------------------------
NUMERAL_OTROS: str = "34"

#: Lista literal del reverso del FUT (numeral -> descripción).
NUMERALES_FUT: dict[str, str] = {
    "1": "Revalidación de grado o título otorgado en el extranjero",
    "2": "Año Sabático",
    "3": "Recurso de reconsideración (1ra instancia)",
    "4": "Recurso de apelación (2da instancia)",
    "5": "Anulación de ingreso y devolución de documentos",
    "6": "Fraccionamiento de deuda",
    "7": "Exoneración de pago",
    "8": "Exoneración del 50% de tasa académica para estudios de maestría o doctorado",
    "9": "Exoneración de tasa académica para optar grado de maestro o doctor",
    "10": "Documentos de sobre membretado",
    "11": "Acumulación de cuatro años de formación profesional",
    "12": "Acumulación de tiempo de servicios en otra entidad estatal",
    "13": "Reconocimiento del primer quinquenio",
    "14": "Reconocimiento del segundo al sexto quinquenio",
    "15": "Reconocimiento de tiempo de servicios",
    "16": "Subsidio familiar",
    "17": "Subsidio por luto",
    "18": "Subsidio por sepelio",
    "19": "Pensión por viudez",
    "20": "Pensión por orfandad",
    "21": "Retención de haberes por mandato judicial",
    "22": "Cese, compensación y/o pensión",
    "23": "Exoneración de tasa para adoptar grado o título",
    "24": "Declaración jurada del empleador para la AFP",
    "25": "Certificado de retención de quinta categoría",
    "26": "Certificado de retención de cuarta categoría",
    "27": "Devolución de dinero",
    "28": "Giro de nuevo cheque",
    "29": "Constancia de recibo de pago",
    "30": "Rectificación o adición de nombre y/o apellido",
    "31": "Constancia de grado o título",
    "32": "Auspicio académico",
    "33": "Anulación de primer ingreso",
    "34": "Otros",
}

FACULTAD_PREDETERMINADA: str = "Ingeniería Industrial y de Sistemas"

#: Escuelas profesionales de la FIIS. Ajustar si la facultad actualiza su oferta.
ESCUELAS_PROFESIONALES: tuple[str, ...] = (
    "Ingeniería Industrial",
    "Ingeniería de Sistemas",
    "Ingeniería Agroindustrial",
    "Ingeniería Mecatrónica",
    "Ingeniería de Transportes",
)

# Dependencias de destino más usadas dentro de la FIIS.
DEP_DECANATO = "Decanato de la Facultad de Ingeniería Industrial y de Sistemas"
DEP_REGISTROS = "Unidad de Registros Académicos - FIIS"
DEP_ESCUELA = "Escuela Profesional - FIIS"
DEP_GRADOS = "Unidad de Grados y Títulos - FIIS"
DEP_BIBLIOTECA = "Biblioteca Especializada - FIIS"


@dataclass(frozen=True)
class Tramite:
    """Un trámite ofrecido por la FIIS, con su costo y sus requisitos."""

    clave: str
    nombre: str
    concepto: str
    monto: float | None
    codigoPago: str
    numeralFut: str = NUMERAL_OTROS
    dependencia: str = DEP_DECANATO
    sumilla: str = ""
    requiereDatosEmpresa: bool = False
    documentosSugeridos: tuple[str, ...] = ()
    palabrasClave: tuple[str, ...] = ()

    @property
    def montoFormateado(self) -> str:
        if self.monto is None:
            return "Sin costo registrado"
        return f"S/ {self.monto:.2f}"

    @property
    def llevaCodigoPago(self) -> bool:
        return self.codigoPago.upper() != "NO LLEVA"

    def resumirCosto(self) -> str:
        """Frase corta con el costo y el código de pago del Banco de la Nación."""
        if not self.llevaCodigoPago:
            return f"{self.montoFormateado} (este concepto no lleva código de pago)"
        return f"{self.montoFormateado} — código de pago {self.codigoPago}"


def _tramite(**datos) -> Tramite:
    return Tramite(**datos)


CATALOGO: tuple[Tramite, ...] = (
    _tramite(
        clave="matricula_regular",
        nombre="Matrícula Regular u Ordinaria - Pregrado",
        concepto="MATRICULA REGULAR",
        monto=72.80,
        codigoPago="NO LLEVA",
        dependencia=DEP_REGISTROS,
        sumilla="Solicito matrícula regular de pregrado",
        documentosSugeridos=("Comprobante de pago de matrícula regular",),
        palabrasClave=("matricula regular", "matricula ordinaria", "matricularme"),
    ),
    _tramite(
        clave="rectificacion_matricula",
        nombre="Rectificación de Matrícula - Por Asignatura",
        concepto="RECTIFI.MAT-POR ASIG",
        monto=8.40,
        codigoPago="83138",
        dependencia=DEP_REGISTROS,
        sumilla="Solicito rectificación de matrícula por asignatura",
        documentosSugeridos=(
            "Comprobante de pago por rectificación de matrícula",
            "Ficha de matrícula vigente",
        ),
        palabrasClave=("rectificacion de matricula", "rectificar matricula", "cambiar curso"),
    ),
    _tramite(
        clave="retiro_matricula",
        nombre="Retiro de Matrícula - Por Asignatura",
        concepto="RETIRO.MAT-POR ASIG",
        monto=36.00,
        codigoPago="83139",
        dependencia=DEP_REGISTROS,
        sumilla="Solicito retiro de matrícula por asignatura",
        documentosSugeridos=(
            "Comprobante de pago por retiro de matrícula",
            "Ficha de matrícula vigente",
        ),
        palabrasClave=("retiro de matricula", "retirar curso", "retirarme de un curso"),
    ),
    _tramite(
        clave="reserva_matricula",
        nombre="Reserva de Matrícula",
        concepto="RESERV-MAT",
        monto=39.20,
        codigoPago="83140",
        dependencia=DEP_REGISTROS,
        sumilla="Solicito reserva de matrícula",
        documentosSugeridos=("Comprobante de pago por reserva de matrícula",),
        palabrasClave=("reserva de matricula", "reservar matricula", "congelar ciclo"),
    ),
    _tramite(
        clave="reactualizacion_matricula",
        nombre="Reactualización de Matrícula",
        concepto="REACT-MAT",
        monto=58.00,
        codigoPago="83141",
        dependencia=DEP_REGISTROS,
        sumilla="Solicito reactualización de matrícula",
        documentosSugeridos=("Comprobante de pago por reactualización de matrícula",),
        palabrasClave=("reactualizacion", "reactualizar matricula", "reincorporacion"),
    ),
    _tramite(
        clave="convalidacion_asignatura",
        nombre="Convalidación de Asignatura - Por Asignatura",
        concepto="CON.ASIG-POR ASIGN",
        monto=29.70,
        codigoPago="83142",
        dependencia=DEP_ESCUELA,
        sumilla="Solicito convalidación de asignatura",
        documentosSugeridos=(
            "Comprobante de pago por convalidación",
            "Certificado de estudios original",
            "Sílabo del curso a convalidar",
        ),
        palabrasClave=("convalidacion", "convalidar curso", "convalidar asignatura"),
    ),
    _tramite(
        clave="examen_aplazado",
        nombre="Examen de Aplazado - Por Asignatura",
        concepto="EXAM.APLA-POR ASIG",
        monto=30.80,
        codigoPago="83143",
        dependencia=DEP_ESCUELA,
        sumilla="Solicito rendir examen de aplazado",
        documentosSugeridos=("Comprobante de pago por examen de aplazado",),
        palabrasClave=("examen de aplazado", "aplazados", "rendir aplazado"),
    ),
    _tramite(
        clave="reprocesamiento_acta",
        nombre="Reprocesamiento de Acta Definitiva - Por Hoja",
        concepto="REPROC.ACTA.DEFIN-POR HOJA",
        monto=20.20,
        codigoPago="83144",
        dependencia=DEP_REGISTROS,
        sumilla="Solicito reprocesamiento de acta definitiva",
        documentosSugeridos=("Comprobante de pago por reprocesamiento de acta",),
        palabrasClave=("reprocesamiento de acta", "acta definitiva", "corregir acta"),
    ),
    _tramite(
        clave="boleta_notas",
        nombre="Boleta de Notas",
        concepto="BOLETA NOTAS",
        monto=7.00,
        codigoPago="83145",
        dependencia=DEP_REGISTROS,
        sumilla="Solicito emisión de boleta de notas",
        documentosSugeridos=("Comprobante de pago por boleta de notas",),
        palabrasClave=("boleta de notas", "boleta", "mis notas"),
    ),
    _tramite(
        clave="regularizacion_academica",
        nombre="Regularización Académica",
        concepto="REG.ACADEMICA",
        monto=51.60,
        codigoPago="83146",
        dependencia=DEP_REGISTROS,
        sumilla="Solicito regularización académica",
        documentosSugeridos=("Comprobante de pago por regularización académica",),
        palabrasClave=("regularizacion academica", "regularizar"),
    ),
    _tramite(
        clave="matricula_extemporanea",
        nombre="Matrícula Extemporánea",
        concepto="MATRICULA EXTEMPORANEA",
        monto=34.70,
        codigoPago="NO LLEVA",
        dependencia=DEP_REGISTROS,
        sumilla="Solicito matrícula extemporánea",
        documentosSugeridos=("Comprobante de pago de matrícula extemporánea",),
        palabrasClave=("matricula extemporanea", "matricula fuera de fecha"),
    ),
    _tramite(
        clave="constancia_estudios",
        nombre="Constancia de Estudio - Pregrado",
        concepto="CONST.ESTUDIO-PREGRADO",
        monto=12.20,
        codigoPago="83147",
        dependencia=DEP_REGISTROS,
        sumilla="Solicito constancia de estudios de pregrado",
        documentosSugeridos=("Comprobante de pago por constancia de estudios",),
        palabrasClave=("constancia de estudio", "constancia de estudios"),
    ),
    _tramite(
        clave="constancia_matricula",
        nombre="Constancia de Matrícula",
        concepto="CONST.MATRICULA",
        monto=5.50,
        codigoPago="83148",
        dependencia=DEP_REGISTROS,
        sumilla="Solicito constancia de matrícula",
        documentosSugeridos=("Comprobante de pago por constancia de matrícula",),
        palabrasClave=("constancia de matricula",),
    ),
    _tramite(
        clave="constancia_egresado",
        nombre="Constancia de Egresado - Pregrado",
        concepto="CONST.EGRESADO-PREGRADO",
        monto=35.20,
        codigoPago="83149",
        dependencia=DEP_REGISTROS,
        sumilla="Solicito constancia de egresado de pregrado",
        documentosSugeridos=("Comprobante de pago por constancia de egresado",),
        palabrasClave=("constancia de egresado", "soy egresado"),
    ),
    _tramite(
        clave="constancia_orden_merito",
        nombre="Constancia de Orden de Mérito",
        concepto="CONST.ORD.MERITO",
        monto=35.00,
        codigoPago="83150",
        dependencia=DEP_REGISTROS,
        sumilla="Solicito constancia de orden de mérito",
        documentosSugeridos=("Comprobante de pago por constancia de orden de mérito",),
        palabrasClave=("orden de merito", "tercio superior", "quinto superior"),
    ),
    _tramite(
        clave="subsanacion_asignatura",
        nombre="Subsanación de Asignatura",
        concepto="SUBSA.ASIINATURA",
        monto=59.10,
        codigoPago="83151",
        dependencia=DEP_ESCUELA,
        sumilla="Solicito subsanación de asignatura",
        documentosSugeridos=("Comprobante de pago por subsanación de asignatura",),
        palabrasClave=("subsanacion", "subsanar curso"),
    ),
    _tramite(
        clave="carnet_biblioteca",
        nombre="Carnet de Biblioteca Especializada",
        concepto="CARNET.BIBLIO.ESPECIALIZADA",
        monto=4.60,
        codigoPago="83152",
        dependencia=DEP_BIBLIOTECA,
        sumilla="Solicito carnet de biblioteca especializada",
        documentosSugeridos=(
            "Comprobante de pago por carnet de biblioteca",
            "Fotografía tamaño carnet",
        ),
        palabrasClave=("carnet de biblioteca", "biblioteca"),
    ),
    _tramite(
        clave="carta_presentacion",
        nombre="Carta de Presentación - Práctica Pre Profesional o Profesional",
        concepto="CARTA PRESENTACION",
        monto=16.90,
        codigoPago="83153",
        dependencia=DEP_DECANATO,
        sumilla="Solicito carta de presentación para prácticas pre profesionales",
        requiereDatosEmpresa=True,
        documentosSugeridos=(
            "Comprobante de pago por carta de presentación",
            "Constancia de matrícula o ficha de matrícula vigente",
        ),
        palabrasClave=(
            "carta de presentacion",
            "carta de presentacion para practicas",
            "practicas pre profesionales",
            "practicas preprofesionales",
            "practicas profesionales",
        ),
    ),
    _tramite(
        clave="constancia_notas_actualizacion",
        nombre="Constancia de Notas - Curso de Actualización",
        concepto="CONST.NOTAS-CURSO DE ACTUAL.",
        monto=5.10,
        codigoPago="83154",
        dependencia=DEP_REGISTROS,
        sumilla="Solicito constancia de notas del curso de actualización",
        documentosSugeridos=("Comprobante de pago por constancia de notas",),
        palabrasClave=("constancia de notas", "curso de actualizacion"),
    ),
    _tramite(
        clave="grado_bachiller",
        nombre="Obtención del Grado de Bachiller",
        concepto="OBTEN.GRA.BLCHILLER",
        monto=351.10,
        codigoPago="83155",
        dependencia=DEP_GRADOS,
        sumilla="Solicito obtención del grado académico de bachiller",
        documentosSugeridos=(
            "Comprobante de pago por grado de bachiller",
            "Certificado de estudios originales",
            "Constancia de egresado",
            "Copia del DNI",
            "Fotografías tamaño pasaporte",
        ),
        palabrasClave=("grado de bachiller", "bachiller", "bachillerato"),
    ),
    _tramite(
        clave="titulo_tesis",
        nombre="Obtención del Título Profesional - Modalidad Tesis",
        concepto="OBTEN.TÍT.PROFES-MOD-TESIS",
        monto=400.90,
        codigoPago="83156",
        dependencia=DEP_GRADOS,
        sumilla="Solicito obtención del título profesional en la modalidad de tesis",
        documentosSugeridos=(
            "Comprobante de pago por título profesional",
            "Diploma de bachiller (copia fedateada)",
            "Ejemplares de la tesis",
            "Copia del DNI",
        ),
        palabrasClave=("titulo profesional tesis", "titularme con tesis", "sustentacion de tesis"),
    ),
    _tramite(
        clave="titulo_suficiencia",
        nombre="Obtención del Título Profesional - Modalidad Trabajo de Suficiencia Profesional",
        concepto="OBTEN.TIT.PROF.MOD.TRAB.SUF.PROF.",
        monto=408.80,
        codigoPago="83157",
        dependencia=DEP_GRADOS,
        sumilla="Solicito obtención del título profesional por trabajo de suficiencia profesional",
        documentosSugeridos=(
            "Comprobante de pago por título profesional",
            "Diploma de bachiller (copia fedateada)",
            "Trabajo de suficiencia profesional",
            "Certificado de trabajo que acredite la experiencia",
        ),
        palabrasClave=(
            "trabajo de suficiencia profesional",
            "suficiencia profesional",
            "titulo por experiencia",
        ),
    ),
)

#: Índice rápido por clave.
TRAMITES_POR_CLAVE: dict[str, Tramite] = {t.clave: t for t in CATALOGO}

#: Clave del trámite que exige el bloque de datos de la empresa.
CLAVE_CARTA_PRESENTACION: str = "carta_presentacion"


def listarTramites() -> tuple[Tramite, ...]:
    """Devuelve el catálogo completo, en el orden del tarifario oficial."""
    return CATALOGO


def obtenerTramite(clave: str | None) -> Tramite | None:
    """Busca un trámite por su clave interna."""
    if not clave:
        return None
    return TRAMITES_POR_CLAVE.get(clave)


def buscarTramitePorTexto(texto: str) -> Tramite | None:
    """Identifica un trámite a partir de texto libre del estudiante.

    Es un respaldo determinista al reconocimiento que hace el modelo de lenguaje:
    compara contra el nombre del trámite y contra sus palabras clave.
    """
    consulta = normalizarClave(texto)
    if not consulta:
        return None

    mejorTramite: Tramite | None = None
    mejorPuntaje = 0

    for tramite in CATALOGO:
        candidatos = (tramite.nombre, *tramite.palabrasClave)
        for candidato in candidatos:
            clave = normalizarClave(candidato)
            if clave and clave in consulta and len(clave) > mejorPuntaje:
                mejorPuntaje = len(clave)
                mejorTramite = tramite
    return mejorTramite


def describirNumeralFut(numeral: str) -> str:
    """Devuelve la descripción oficial de un numeral del reverso del FUT."""
    return NUMERALES_FUT.get(str(numeral).strip(), NUMERALES_FUT[NUMERAL_OTROS])


def resumirCatalogoParaModelo() -> str:
    """Catálogo compacto que se inyecta en el prompt del modelo de lenguaje."""
    lineas = [
        f"- {t.clave}: {t.nombre} | {t.montoFormateado} | código {t.codigoPago}"
        for t in CATALOGO
    ]
    return "\n".join(lineas)


__all__ = [
    "Tramite",
    "CATALOGO",
    "TRAMITES_POR_CLAVE",
    "CLAVE_CARTA_PRESENTACION",
    "NUMERAL_OTROS",
    "NUMERALES_FUT",
    "ESCUELAS_PROFESIONALES",
    "FACULTAD_PREDETERMINADA",
    "listarTramites",
    "obtenerTramite",
    "buscarTramitePorTexto",
    "describirNumeralFut",
    "resumirCatalogoParaModelo",
]
