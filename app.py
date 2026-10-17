"""Asistente de trámites FIIS - UNFV.

Interfaz web del agente que conversa con el estudiante, completa el Formulario Único
de Trámite sobre la plantilla oficial y lo entrega listo para descargar.

Ejecución:
    streamlit run app.py
"""

from __future__ import annotations

import base64
import html
import logging
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as componentes

from src.agente_fut import AgenteFut, RespuestaAgente
from src.catalogo_tramites import ESCUELAS_PROFESIONALES, listarTramites, obtenerTramite
from src.configuracion import Configuracion, obtenerConfiguracion
from src.llenador_fut import ErrorLlenadoFut, generarNombreArchivo, rellenarFut
from src.modelos import CAMPOS_OBLIGATORIOS, PREFIJO_DATOS_TRAMITE, SolicitudFut
from src.plantillas_prompt import MENSAJE_BIENVENIDA, describirCampo
from src.puente_secretos import sincronizarSecretosDeStreamlit

# Debe ejecutarse antes de la primera llamada a obtenerConfiguracion(): en Streamlit
# Community Cloud no hay .env, los secretos viven en st.secrets.
sincronizarSecretosDeStreamlit()

_configuracionLog = obtenerConfiguracion()
logging.basicConfig(
    level=logging.DEBUG if _configuracionLog.modoDepuracion else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

#: Turnos consecutivos sin avance a partir de los cuales se sugiere el panel manual.
TURNOS_SIN_AVANCE_PARA_SUGERIR: int = 2

#: Clave de ``st.chat_input``. Asignar texto a ``st.session_state[CLAVE_ENTRADA_CHAT]``
#: ANTES de dibujar el widget lo deja escrito en el cuadro de mensaje (Streamlit 1.47+).
CLAVE_ENTRADA_CHAT: str = "entrada_chat"


# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------
def configurarPagina(configuracion: Configuracion) -> None:
    """Define título, icono y disposición general de la página."""
    icono = str(configuracion.rutaLogo) if configuracion.rutaLogo.is_file() else "📄"
    st.set_page_config(
        page_title=configuracion.nombreAplicacion,
        page_icon=icono,
        layout="centered",
        initial_sidebar_state="expanded",
    )


def cargarEstilos(rutaEstilos: Path) -> None:
    """Inyecta la hoja de estilos de la aplicación."""
    if not rutaEstilos.is_file():
        return
    st.markdown(f"<style>{rutaEstilos.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def codificarImagen(ruta: str) -> str:
    """Devuelve una imagen local como data URI para incrustarla en el encabezado."""
    return base64.b64encode(Path(ruta).read_bytes()).decode("ascii")


@st.cache_resource(show_spinner=False)
def obtenerAgente() -> AgenteFut:
    """Instancia única del agente (se reutiliza entre recargas de la interfaz)."""
    return AgenteFut()





def inicializarEstado(configuracion: Configuracion) -> None:
    """Crea las claves de ``st.session_state`` la primera vez que se abre la app."""
    if "solicitud" not in st.session_state:
        st.session_state.solicitud = SolicitudFut(ciudad=configuracion.ciudadPredeterminada)
    if "mensajes" not in st.session_state:
        st.session_state.mensajes = [{"role": "assistant", "content": MENSAJE_BIENVENIDA}]
    if "documentos" not in st.session_state:
        # indice del mensaje -> {"pdf": bytes, "nombre": str}
        st.session_state.documentos = {}
    if "advertencias" not in st.session_state:
        st.session_state.advertencias = []
    if "turnosSinAvance" not in st.session_state:
        st.session_state.turnosSinAvance = 0
    if "camposEsperados" not in st.session_state:
        st.session_state.camposEsperados = []
    if "plantillas" not in st.session_state:
        # indice del mensaje -> plantilla "Etiqueta: " que se dejó en el cuadro de mensaje
        st.session_state.plantillas = {}
    if "plantillaPendiente" not in st.session_state:
        # texto a escribir en el cuadro de mensaje en la próxima ejecución
        st.session_state.plantillaPendiente = None


def reiniciarConversacion(configuracion: Configuracion) -> None:
    """Vuelve al estado inicial conservando la configuración cargada."""
    st.session_state.solicitud = SolicitudFut(ciudad=configuracion.ciudadPredeterminada)
    st.session_state.mensajes = [{"role": "assistant", "content": MENSAJE_BIENVENIDA}]
    st.session_state.documentos = {}
    st.session_state.advertencias = []
    st.session_state.turnosSinAvance = 0
    st.session_state.camposEsperados = []
    st.session_state.plantillas = {}
    st.session_state.plantillaPendiente = None


# ---------------------------------------------------------------------------
# Encabezado
# ---------------------------------------------------------------------------
def renderizarEncabezado(configuracion: Configuracion) -> None:
    """Cabecera con el logo de la FIIS y el nombre de la aplicación."""
    logo = ""
    if configuracion.rutaLogo.is_file():
        logo = f'<img src="data:image/png;base64,{codificarImagen(str(configuracion.rutaLogo))}" alt="Logo FIIS UNFV" />'

    st.markdown(
        f"""
        <div class="encabezado-fiis">
          {logo}
          <div class="encabezado-textos">
            <p class="encabezado-titulo">Trámites FIIS</p>
            <p class="encabezado-subtitulo">Llena tu Formulario Único de Trámite conversando. Universidad Nacional Federico Villarreal.</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Panel lateral: expediente en construcción
# ---------------------------------------------------------------------------
def renderizarPanelLateral(configuracion: Configuracion) -> None:
    """Muestra el trámite elegido, el avance del formulario y las acciones manuales."""
    solicitud: SolicitudFut = st.session_state.solicitud

    with st.sidebar:
        st.markdown('<p class="panel-titulo">TRÁMITE</p>', unsafe_allow_html=True)
        renderizarTarjetaTramite(solicitud)
        st.caption(
            "Este asistente no pide ni adjunta una firma digital: el FUT se entrega sin "
            "firmar y la firmas a mano sobre el PDF impreso."
        )

        st.markdown('<p class="panel-titulo">AVANCE DEL FORMULARIO</p>', unsafe_allow_html=True)
        renderizarAvance(solicitud)

        with st.expander("Revisar y corregir datos"):
            renderizarFormularioManual(solicitud, configuracion)

        st.markdown('<p class="panel-titulo">SESIÓN</p>', unsafe_allow_html=True)
        if st.button("Empezar un trámite nuevo", use_container_width=True, type="secondary"):
            reiniciarConversacion(configuracion)
            st.rerun()

        renderizarEstadoDelSistema(configuracion)


def renderizarTarjetaTramite(solicitud: SolicitudFut) -> None:
    """Tarjeta con el nombre, el costo y el código de pago del trámite en curso."""
    tramite = solicitud.tramite
    if tramite is None:
        st.markdown(
            '<div class="tarjeta-vacia">Cuéntale al asistente qué necesitas y aquí '
            "aparecerá el trámite con su costo.</div>",
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f"""
        <div class="tarjeta-tramite">
          <div class="nombre">{tramite.nombre}</div>
          <div class="detalle">
            {tramite.montoFormateado} · código {tramite.codigoPago}<br />
            {solicitud.dependencia or tramite.dependencia}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def renderizarAvance(solicitud: SolicitudFut) -> None:
    """Barra de progreso y lista de verificación de los campos obligatorios."""
    faltantes = set(solicitud.camposFaltantes())
    obligatorios = list(CAMPOS_OBLIGATORIOS)
    if solicitud.tramite is not None:
        obligatorios += [
            f"{PREFIJO_DATOS_TRAMITE}{c.clave}" for c in solicitud.tramite.camposAdicionales
        ]
    if solicitud.esCartaPresentacion:
        obligatorios += [
            "empresa.nombreInstitucion",
            "empresa.ruc",
            "empresa.correo",
            "empresa.telefono",
            "empresa.direccion",
            "empresa.destinatario",
        ]

    completos = [c for c in obligatorios if c not in faltantes]
    total = len(obligatorios) or 1
    st.progress(len(completos) / total)
    st.markdown(
        f'<p class="progreso-texto">{len(completos)} de {total} datos completos</p>',
        unsafe_allow_html=True,
    )

    elementos = []
    for campo in obligatorios:
        completo = campo not in faltantes
        clase = "completo" if completo else "pendiente"
        marca = "●" if completo else "○"
        valor = obtenerValorLegible(solicitud, campo) if completo else ""
        detalle = f'<span class="valor">{valor}</span>' if valor else ""
        elementos.append(
            f'<li class="{clase}"><span class="marca">{marca}</span>'
            f"<span>{describirCampo(campo)} {detalle}</span></li>"
        )
    st.markdown(f'<ul class="lista-campos">{"".join(elementos)}</ul>', unsafe_allow_html=True)


def obtenerValorLegible(solicitud: SolicitudFut, campo: str) -> str:
    """Valor corto del campo para mostrarlo junto a la marca de completado."""
    if campo == "tramiteClave":
        return ""
    if campo.startswith("empresa."):
        valor = str(getattr(solicitud.empresa, campo.split(".", 1)[1], ""))
    elif campo.startswith(PREFIJO_DATOS_TRAMITE):
        valor = str(solicitud.datosTramite.get(campo[len(PREFIJO_DATOS_TRAMITE):], ""))
    else:
        valor = str(getattr(solicitud, campo, ""))
    return valor if len(valor) <= 28 else f"{valor[:27]}…"


def renderizarFormularioManual(solicitud: SolicitudFut, configuracion: Configuracion) -> None:
    """Permite corregir a mano cualquier dato y regenerar el FUT sin pasar por el chat."""
    tramites = listarTramites()
    claves = [t.clave for t in tramites]
    indiceTramite = claves.index(solicitud.tramiteClave) if solicitud.tramiteClave in claves else 0

    with st.form("formulario_manual"):
        claveElegida = st.selectbox(
            "Trámite",
            options=claves,
            index=indiceTramite,
            format_func=lambda c: obtenerTramite(c).nombre,
        )
        apellidosNombres = st.text_input("Apellidos y nombres", value=solicitud.apellidosNombres)
        escuela = st.selectbox(
            "Escuela profesional",
            options=list(ESCUELAS_PROFESIONALES),
            index=(
                list(ESCUELAS_PROFESIONALES).index(solicitud.escuelaProfesional)
                if solicitud.escuelaProfesional in ESCUELAS_PROFESIONALES
                else 0
            ),
        )
        codigo = st.text_input("Código de estudiante", value=solicitud.codigoEstudiante)
        documento = st.text_input("DNI / Pasaporte / C. Extranjería", value=solicitud.documentoIdentidad)
        direccion = st.text_input("Dirección domiciliaria", value=solicitud.direccion)
        numeroDepartamento = st.text_input("N° y/o Dpto.", value=solicitud.numeroDepartamento)
        distrito = st.text_input("Distrito", value=solicitud.distrito)
        telefonoFijo = st.text_input("Teléfono fijo", value=solicitud.telefonoFijo)
        celular = st.text_input("Celular", value=solicitud.celular)
        correo = st.text_input("Correo electrónico", value=solicitud.correoElectronico)
        dependencia = st.text_input("Dependencia a quien se dirige", value=solicitud.dependencia)

        # Datos propios del trámite (p. ej. curso y secciones en la rectificación de matrícula).
        # Como en el bloque de la empresa, aparecen al guardar con el trámite ya elegido.
        datosTramite: dict[str, str] = {}
        tramiteElegido = obtenerTramite(claveElegida)
        if tramiteElegido is not None and tramiteElegido.camposAdicionales:
            st.markdown(f"**Datos de {tramiteElegido.nombre.lower()}**")
            for adicional in tramiteElegido.camposAdicionales:
                etiqueta = f"{adicional.etiqueta} ({adicional.pista})" if adicional.pista else adicional.etiqueta
                datosTramite[adicional.clave] = st.text_input(
                    etiqueta, value=solicitud.datosTramite.get(adicional.clave, "")
                )

        datosEmpresa: dict[str, str] = {}
        if claveElegida == "carta_presentacion":
            st.markdown("**Centro de prácticas**")
            datosEmpresa = {
                "nombreInstitucion": st.text_input(
                    "Nombre de la institución o empresa", value=solicitud.empresa.nombreInstitucion
                ),
                "ruc": st.text_input("RUC de la empresa", value=solicitud.empresa.ruc),
                "correo": st.text_input("Correo de la empresa", value=solicitud.empresa.correo),
                "telefono": st.text_input("Teléfono de la empresa", value=solicitud.empresa.telefono),
                "direccion": st.text_input(
                    "Dirección de la institución o empresa", value=solicitud.empresa.direccion
                ),
                "destinatario": st.text_input(
                    "Nombre, apellidos y cargo a quien va dirigido",
                    value=solicitud.empresa.destinatario,
                ),
            }

        enviado = st.form_submit_button("Guardar y generar FUT", use_container_width=True)

    if not enviado:
        return

    cambios: dict[str, object] = {
        "tramiteClave": claveElegida,
        "apellidosNombres": apellidosNombres,
        "escuelaProfesional": escuela,
        "codigoEstudiante": codigo,
        "documentoIdentidad": documento,
        "direccion": direccion,
        "numeroDepartamento": numeroDepartamento,
        "distrito": distrito,
        "telefonoFijo": telefonoFijo,
        "celular": celular,
        "correoElectronico": correo,
        "dependencia": dependencia,
    }
    if datosEmpresa:
        cambios["empresa"] = datosEmpresa
    if datosTramite:
        cambios["datosTramite"] = datosTramite

    solicitud.fusionar(cambios)
    solicitud.aplicarValoresDelTramite()
    generarDesdeFormulario(solicitud, configuracion)


def generarDesdeFormulario(solicitud: SolicitudFut, configuracion: Configuracion) -> None:
    """Genera el FUT desde el panel manual y lo publica como mensaje del asistente."""
    errores = solicitud.erroresDeFormato()
    if errores:
        st.error(" ".join(errores.values()))
        return

    faltantes = solicitud.camposFaltantes()
    if faltantes:
        etiquetas = ", ".join(describirCampo(c).lower() for c in faltantes[:4])
        st.warning(f"Todavía faltan datos: {etiquetas}.")
        return

    agente = obtenerAgente()
    if not solicitud.fundamentacion:
        solicitud.fundamentacion = agente.redactarFundamentacion(solicitud)

    try:
        pdf = rellenarFut(solicitud, configuracion.rutaPlantillaFut)
    except ErrorLlenadoFut as error:
        st.error(str(error))
        return
    except Exception as error:  # salvaguarda: un fallo inesperado nunca debe quedar en silencio
        st.error(f"Ocurrió un error inesperado al generar el PDF: {error}")
        return

    nombreArchivo = generarNombreArchivo(solicitud)
    st.session_state.turnosSinAvance = 0
    st.session_state.camposEsperados = []
    st.session_state.plantillaPendiente = None
    registrarMensajeConDocumento(
        "Actualicé tus datos y volví a generar el FUT.",
        pdf,
        nombreArchivo,
        solicitud=solicitud,
        titulo="Tu FUT se actualizó",
    )
    st.rerun()


def renderizarEstadoDelSistema(configuracion: Configuracion) -> None:
    """Indica la plantilla del FUT y qué proveedor de LLM está usando el agente.

    El proveedor (Qwen3 o Gemini) se decide una sola vez, al crear el agente cacheado
    (ver ``seleccionarServicioLlm`` en ``src/servicio_llm.py``): primero se comprueba si
    Qwen3 responde en Ollama y, si no, se usa automáticamente la API de Gemini. Aquí se
    muestra siempre el proveedor que el agente realmente está usando en esta sesión, no
    una comprobación aparte, para que la interfaz nunca diga algo distinto de lo que en
    verdad está respondiendo.
    """
    problemas = configuracion.verificarRutas()
    if problemas:
        st.markdown(
            f'<p class="aviso-estado error">{"<br />".join(problemas)}</p>',
            unsafe_allow_html=True,
        )

    agente = obtenerAgente()
    st.markdown(
        f'<p class="aviso-estado">Modelo en uso: <strong>{agente.nombreProveedor}</strong></p>',
        unsafe_allow_html=True,
    )
    st.caption(agente.detalleProveedor)


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------
def registrarMensajeConDocumento(
    texto: str,
    pdf: bytes | None,
    nombreArchivo: str | None,
    solicitud: SolicitudFut | None = None,
    titulo: str = "Tu FUT está listo",
) -> None:
    """Agrega un mensaje del asistente y, si corresponde, adjunta el PDF generado.

    Junto al PDF se guarda una foto de lo que necesita la tarjeta de cierre (trámite y
    documentos adjuntos), para que un mensaje antiguo no cambie si luego se edita la
    solicitud desde el panel lateral.
    """
    st.session_state.mensajes.append({"role": "assistant", "content": texto})
    if pdf and nombreArchivo:
        indice = len(st.session_state.mensajes) - 1
        st.session_state.documentos[indice] = {
            "pdf": pdf,
            "nombre": nombreArchivo,
            "titulo": titulo,
            "tramiteClave": solicitud.tramiteClave if solicitud else None,
            "adjuntos": list(solicitud.documentosAdjuntos) if solicitud else [],
        }


def renderizarHistorial() -> None:
    """Dibuja toda la conversación, con el botón de descarga en su mensaje original."""
    plantillas: dict[int, str] = st.session_state.plantillas
    ultimaPlantilla = max(plantillas) if plantillas else None
    for indice, mensaje in enumerate(st.session_state.mensajes):
        with st.chat_message(mensaje["role"]):
            documento = st.session_state.documentos.get(indice)
            if documento:
                # La tarjeta reemplaza al texto del mensaje: ya contiene el estado, el
                # pago y los pasos, y repetirlos en un párrafo solo añade ruido.
                renderizarTarjetaFutListo(documento, indice)
            else:
                st.markdown(mensaje["content"])
            if indice == ultimaPlantilla:
                renderizarRespaldoPlantilla(plantillas[indice], indice)


def renderizarRespaldoPlantilla(plantilla: str, indice: int) -> None:
    """Respaldo por si el estudiante borró la plantilla del cuadro de mensaje.

    Solo se muestra en el último mensaje que trajo plantilla (las anteriores ya no
    reflejan lo que falta).
    """
    with st.expander("Ver la plantilla de datos"):
        st.code(plantilla, language=None)
        if st.button("Volver a escribirla en el cuadro de mensaje", key=f"replantilla_{indice}"):
            st.session_state.plantillaPendiente = plantilla
            st.rerun()


def renderizarTarjetaFutListo(documento: dict[str, object], indice: int) -> None:
    """Tarjeta de cierre: estado, pago, acciones y pasos, en ese orden de importancia.

    Jerarquía pensada para leerse de un vistazo:
    1. Estado: "Tu FUT está listo" y el nombre del trámite.
    2. Pago: monto y código como datos grandes, que es lo que el estudiante copia en el
       banco (antes estaban enterrados a mitad de un párrafo).
    3. Acciones: descargar (principal) e imprimir (secundaria).
    4. Pasos siguientes: lista numerada corta, cada uno empezando por su verbo.

    La firma se deja siempre en blanco a propósito: es una firma manuscrita la que la
    Secretaría General exige al presentar el trámite en físico, y una imagen adjunta no
    tiene ese valor ni evita que la oficina pida firmar de todos modos. Por eso el
    formulario solo imprime el nombre bajo la línea de firma (el "Post firma") y el paso
    2 recuerda firmarlo a mano, en vez de ofrecer una opción de "adjuntar firma" que
    daría una falsa sensación de trámite terminado.
    """
    tramite = obtenerTramite(documento.get("tramiteClave"))  # type: ignore[arg-type]
    titulo = html.escape(str(documento.get("titulo") or "Tu FUT está listo"))
    nombreTramite = html.escape(tramite.nombre) if tramite else ""

    st.markdown(
        f"""
        <div class="fut-listo">
          <div class="fut-estado">
            <span class="fut-icono" aria-hidden="true">✓</span>
            <div>
              <p class="fut-titulo">{titulo}</p>
              <p class="fut-subtitulo">{nombreTramite}</p>
            </div>
          </div>
          {construirBloquePago(tramite)}
        </div>
        """,
        unsafe_allow_html=True,
    )

    renderizarAcciones(documento, indice)

    st.markdown(construirPasosSiguientes(tramite, documento.get("adjuntos") or []), unsafe_allow_html=True)


def construirBloquePago(tramite) -> str:
    """Monto y código de pago como datos destacados (o un aviso si no aplica)."""
    if tramite is None:
        return ""
    if tramite.llevaCodigoPago:
        codigo = (
            '<span class="fut-dato-etiqueta">Código de pago</span>'
            f'<span class="fut-dato-valor fut-mono">{html.escape(tramite.codigoPago)}</span>'
        )
    else:
        codigo = (
            '<span class="fut-dato-etiqueta">Código de pago</span>'
            '<span class="fut-dato-valor fut-apagado">No requiere</span>'
        )
    return f"""
          <div class="fut-pago">
            <div class="fut-dato">
              <span class="fut-dato-etiqueta">Monto a pagar</span>
              <span class="fut-dato-valor">{html.escape(tramite.montoFormateado)}</span>
            </div>
            <div class="fut-dato">{codigo}</div>
          </div>"""


def construirPasosSiguientes(tramite, adjuntos: list[str]) -> str:
    """Lista numerada y breve de lo que el estudiante tiene que hacer después."""
    pasos: list[str] = []
    if tramite is not None and tramite.monto is not None:
        # El monto y el código ya están destacados arriba: aquí solo va la acción.
        if tramite.llevaCodigoPago:
            pasos.append("<strong>Paga</strong> en el Banco de la Nación con el código de pago.")
        else:
            pasos.append("<strong>Paga</strong> el monto indicado (no lleva código de pago).")
    pasos.append(
        "<strong>Imprime y firma a mano</strong> en «Firma y Post Firma del Solicitante» "
        "(no se acepta firma digital)."
    )
    documentos = ""
    if adjuntos:
        documentos = '<span class="fut-adjuntos">' + " · ".join(html.escape(d) for d in adjuntos) + "</span>"
    pasos.append(
        f"<strong>Preséntalo</strong> en la Oficina de Trámite Documentario con:{documentos}"
        if adjuntos
        else "<strong>Preséntalo</strong> en la Oficina de Trámite Documentario."
    )
    elementos = "".join(f"<li>{paso}</li>" for paso in pasos)
    return f"""
        <div class="fut-siguientes">
          <p class="fut-seccion">Siguientes pasos</p>
          <ol class="fut-pasos">{elementos}</ol>
        </div>
        """


def renderizarAcciones(documento: dict[str, object], indice: int) -> None:
    """Descargar (acción principal) e imprimir (secundaria), con el nombre del archivo."""
    nombre = str(documento["nombre"])
    pdfBytes = documento["pdf"]
    pdfBase64 = base64.b64encode(pdfBytes).decode("ascii")

    columnaDescarga, columnaImprimir = st.columns(2)
    with columnaDescarga:
        st.download_button(
            label="Descargar PDF",
            icon=":material/download:",
            data=pdfBytes,
            file_name=nombre,
            mime="application/pdf",
            key=f"descarga_{indice}",
            use_container_width=True,
        )
    with columnaImprimir:
        renderizarBotonImprimir(pdfBase64, indice)

    st.markdown(
        f'<p class="fut-archivo">{html.escape(nombre)} · "Imprimir" abre el PDF en una '
        "pestaña nueva</p>",
        unsafe_allow_html=True,
    )


def renderizarBotonImprimir(pdfBase64: str, indice: int) -> None:
    """Botón que abre el PDF en una pestaña nueva para imprimirlo.

    Antes este botón era un `<a href="data:application/pdf;base64,...">` con
    `target="_blank"`. Desde hace varias versiones, Chrome y otros navegadores basados
    en Chromium bloquean la NAVEGACIÓN de nivel superior (abrir una pestaña o cambiar de
    página) hacia un `data:` URI por motivos de seguridad (ver
    https://developer.chrome.com/blog/deprecating-web-based-data-uris): la pestaña se
    abre en blanco y el PDF nunca carga. Eso no afectaba a "Descargar PDF" porque el
    atributo `download` de `st.download_button` dispara una descarga directa, que el
    navegador no trata como una navegación.

    La solución es reconstruir el PDF como un `Blob` dentro del navegador y abrir un
    `blob:` URL, que sí se puede navegar/abrir en una pestaña nueva. `st.markdown` no
    ejecuta las etiquetas `<script>` que inserta, así que este botón se renderiza con
    `st.components.v1.html`, que sí lo hace (corre en su propio iframe).
    """
    idBoton = f"boton-imprimir-{indice}"
    colorPrincipal = obtenerConfiguracion().colorPrincipal
    html = f"""
    <style>
      html, body {{ margin: 0; padding: 0; }}
      #{idBoton} {{
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.45rem;
        width: 100%;
        height: 2.5rem;
        background: transparent;
        color: {colorPrincipal};
        border: 1px solid {colorPrincipal};
        border-radius: 8px;
        font-weight: 560;
        font-size: 0.88rem;
        font-family: "Inter", "Segoe UI", system-ui, -apple-system, sans-serif;
        cursor: pointer;
        box-sizing: border-box;
        transition: background 120ms ease, color 120ms ease;
      }}
      #{idBoton}:hover {{ background: {colorPrincipal}; color: #fff; }}
      #{idBoton}:focus-visible {{ outline: 2px solid {colorPrincipal}; outline-offset: 2px; }}
    </style>
    <button id="{idBoton}" type="button">
      <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" fill="currentColor">
        <path d="M19 8H5c-1.66 0-3 1.34-3 3v6h4v4h12v-4h4v-6c0-1.66-1.34-3-3-3zm-3 11H8v-5h8v5zm3-7c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1zm-1-9H6v4h12V3z"/>
      </svg>
      Imprimir
    </button>
    <script>
      document.getElementById("{idBoton}").addEventListener("click", function () {{
        const base64 = "{pdfBase64}";
        const binario = atob(base64);
        const bytes = new Uint8Array(binario.length);
        for (let i = 0; i < binario.length; i++) {{
          bytes[i] = binario.charCodeAt(i);
        }}
        const blob = new Blob([bytes], {{ type: "application/pdf" }});
        const url = URL.createObjectURL(blob);
        window.open(url, "_blank");
      }});
    </script>
    """
    componentes.html(html, height=46)


def procesarEntrada(texto: str) -> None:
    """Envía el mensaje del estudiante al agente y publica la respuesta."""
    st.session_state.mensajes.append({"role": "user", "content": texto})

    with st.chat_message("user"):
        st.markdown(texto)

    with st.chat_message("assistant"):
        with st.spinner("Revisando tus datos…"):
            agente = obtenerAgente()
            historial = st.session_state.mensajes[:-1]
            respuesta: RespuestaAgente = agente.procesarMensaje(
                texto,
                st.session_state.solicitud,
                historial,
                camposEsperados=st.session_state.camposEsperados,
            )

    st.session_state.solicitud = respuesta.solicitud
    st.session_state.advertencias = respuesta.advertencias
    st.session_state.camposEsperados = respuesta.camposPreguntados

    if respuesta.formularioListo or respuesta.camposActualizados:
        st.session_state.turnosSinAvance = 0
    else:
        st.session_state.turnosSinAvance += 1

    mensaje = respuesta.mensaje
    if not respuesta.formularioListo and st.session_state.turnosSinAvance >= TURNOS_SIN_AVANCE_PARA_SUGERIR:
        mensaje += (
            "\n\nSi prefieres no seguir conversando, abre \"Revisar y corregir datos\" en el "
            "panel lateral: ahí puedes escribir todos los datos directamente y generar el FUT "
            "sin depender del chat."
        )

    registrarMensajeConDocumento(
        mensaje, respuesta.pdf, respuesta.nombreArchivo, solicitud=respuesta.solicitud
    )
    if respuesta.plantilla:
        indice = len(st.session_state.mensajes) - 1
        st.session_state.plantillas[indice] = respuesta.plantilla
    # No se puede escribir en el cuadro de mensaje desde aquí: el widget ya se dibujó en
    # esta ejecución. Se deja pendiente y ``principal`` lo aplica antes de dibujarlo.
    st.session_state.plantillaPendiente = respuesta.plantilla or None
    st.rerun()


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------
def principal() -> None:
    """Arranca la aplicación."""
    configuracion = obtenerConfiguracion()
    configurarPagina(configuracion)
    cargarEstilos(configuracion.rutaEstilos)
    inicializarEstado(configuracion)

    renderizarEncabezado(configuracion)
    renderizarPanelLateral(configuracion)
    renderizarHistorial()

    for advertencia in st.session_state.advertencias:
        st.warning(advertencia)

    # Deja la plantilla de datos escrita en el cuadro de mensaje para que el estudiante
    # solo la rellene. Debe asignarse antes de crear el widget.
    if st.session_state.plantillaPendiente:
        st.session_state[CLAVE_ENTRADA_CHAT] = st.session_state.plantillaPendiente
        st.session_state.plantillaPendiente = None

    entrada = st.chat_input("Escribe tu consulta o tus datos…", key=CLAVE_ENTRADA_CHAT)
    if entrada:
        procesarEntrada(entrada)


if __name__ == "__main__":
    principal()