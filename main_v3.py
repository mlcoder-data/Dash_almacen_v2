# --- IMPORTS ---
import streamlit as st
import pandas as pd
from datetime import datetime
 # si no lo tienes importado
from streamlit_option_menu import option_menu  # menú con iconos
from auth import login  # maneja sesión y roles en st.session_state
# BD y helpers tuyos

# importa funciones de la BD
from database import (
    ensure_db,                   # crea tablas base (llaves, inventario)
    asegurar_esquema_inventario, # crea rooms + índices extra (opcional, al entrar a Inventario)
    registrar_evento, obtener_historial, eliminar_registro, llave_activa_por_salon,
    obtener_inventario, agregar_equipo, actualizar_equipo, eliminar_equipo,
    obtener_salones, registrar_salon, insertar_inventario_masivo,
)

ensure_db()

CATEGORIAS_VALIDAS = [
    "Computador","Portátil","Cargador","Osciloscopio","Multímetro","Fuente","Router",
    "Switch","Herramienta","Televisor","Proyector","Otro"
]
ESTADOS_VALIDOS = ["Disponible","En uso","Dañado","Extraviado"]



# --- Cargar estilos globales ---
def load_styles():
    try:
        with open("styles.css", "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        pass

st.set_page_config(page_title="Almacén-TICS", layout="wide")
load_styles()


# ---------------------- Autenticación ----------------------
#if not login():
#    st.stop()

#usuario = st.session_state.usuario
#is_admin = bool(st.session_state.get("is_admin", False))
#--------------------------------------------------------------


# --------------------- Utilidades ----------------------------
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def procesar_fechas(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    if "fecha_hora" in df.columns:
        df["fecha_hora"] = pd.to_datetime(df["fecha_hora"], errors="coerce")
        df["fecha"] = df["fecha_hora"].dt.date
        df["hora"] = df["fecha_hora"].dt.strftime("%H:%M")
        df["día_semana"] = df["fecha_hora"].dt.day_name()
    return df

def filtros_comunes(df: pd.DataFrame, key_prefix="flt") -> pd.DataFrame:
    if df is None or df.empty:
        return df
    df = procesar_fechas(df.copy())
    profesores = ["Todos"] + sorted(df["nombre"].dropna().unique().tolist())
    salones = ["Todos"] + sorted(df["salon"].dropna().unique().tolist())
    areas = ["Todos"] + sorted(df["area"].dropna().unique().tolist())
    dias = ["Todos"] + sorted(df["día_semana"].dropna().unique().tolist())

    c1, c2, c3 = st.columns(3)
    with c1: f_prof = st.selectbox("Profesor", profesores, key=f"{key_prefix}_prof")
    with c2: f_salon = st.selectbox("Salón", salones, key=f"{key_prefix}_salon")
    with c3: f_area = st.selectbox("Área", areas, key=f"{key_prefix}_area")
    c4, c5 = st.columns(2)
    with c4: f_dia = st.selectbox("Día de la semana", dias, key=f"{key_prefix}_dia")
    with c5: f_rango = st.date_input("Rango de fechas", [], key=f"{key_prefix}_rango")

    if f_prof != "Todos": df = df[df["nombre"] == f_prof]
    if f_salon != "Todos": df = df[df["salon"] == f_salon]
    if f_area != "Todos": df = df[df["area"] == f_area]
    if f_dia != "Todos": df = df[df["día_semana"] == f_dia]
    if isinstance(f_rango, list) and len(f_rango) == 2:
        ini, fin = f_rango
        df = df[(df["fecha"] >= ini) & (df["fecha"] <= fin)]
    return df

# Bloques visuales
def badge(text, kind="ok"):
    return f'<span class="badge {kind}">{text}</span>'

def card(title, body_md):
    st.markdown(f"""
    <div class="card">
        <h4>{title}</h4>
        <div>{body_md}</div>
    </div>
    """, unsafe_allow_html=True)


# ===== SIDEBAR: menú bonito con iconos =====
with st.sidebar:
    st.markdown("### 💬 Menú\n**Principal**")
    st.divider()
    menu_label = option_menu(
        menu_title=None,
        options=["Dashboard", "Registrar llave", "Llaves activas", "Historial", "Estadísticas", "Inventario", "Inventario por salón","Movimientos de equipos"],
        icons=["speedometer", "pencil-square", "key", "clock-history", "bar-chart", "boxes", "diagram-3","arrows-move"],
        default_index=0,
        styles={
            "container": {"padding": "0"},
            "icon": {"font-size": "16px"},
            "nav-link": {"font-weight": "600", "border-radius": "12px"},
            "nav-link-selected": {"background-color": "#ff5a5f"},
        },
    )
    st.markdown("---")
    st.markdown(f"**Usuario:** {st.session_state.get('usuario','Mateo')}")
    st.caption("Rol: Administrador")

# Router robusto por clave (no por texto con tildes)
label_to_key = {
    "Dashboard": "dashboard",
    "Registrar llave": "registrar",
    "Llaves activas": "activas",
    "Historial": "historial",
    "Estadísticas": "stats",
    "Inventario": "inventario",
    "Inventario por salón": "inv_salon",
    "Movimientos de equipos": "mov_equipos",
}
menu_key = label_to_key.get(menu_label, "dashboard")

if menu_key == "dashboard":
    st.header("📊 Dashboard")

    # --- Datos base ---
    hist = obtener_historial()
    inv = obtener_inventario()

    total_registros = 0 if hist is None or hist.empty else len(hist)
    total_inventario = 0 if inv is None or inv.empty else len(inv)
    activas = 0
    if hist is not None and not hist.empty:
        h2 = procesar_fechas(hist)
        ultimas = h2.sort_values("fecha_hora").groupby("salon").tail(1)
        activas = int((ultimas["accion"] == "Entregada").sum())

    # --- KPIs (solo una fila, sin resumen duplicado) ---
    c1, c2, c3 = st.columns(3)
    c1.metric("🔑 Registros (llaves)", total_registros)
    c2.metric("🟢 Llaves activas", activas)
    c3.metric("💼 Activos en inventario", total_inventario)

    st.divider()

    # --- Dos columnas: Recordatorios  |  Últimos movimientos ---
    col_left, col_right = st.columns([1, 1])

    # 1) Recordatorios (izquierda)
    with col_left:
        st.markdown("### 🔔 Recordatorios")
        alertas = []
        if hist is not None and not hist.empty:
            df = procesar_fechas(hist)
            ult = df.sort_values("fecha_hora").groupby("salon").tail(1)
            vencidas = ult[
                (ult["accion"] == "Entregada")
                & ((pd.Timestamp.now() - ult["fecha_hora"]) > pd.Timedelta(hours=2))
            ]
            if not vencidas.empty:
                for _, r in vencidas.iterrows():
                    card(
                        "Devolución pendiente",
                        f"⚠️ **{r['salon']}** entregada a **{r['nombre']}** · {r['area']}  \n"
                        f"🕒 {r['fecha_hora'].strftime('%Y-%m-%d %H:%M')}"
                    )
            else:
                card("Estado", badge("No hay recordatorios por ahora", "ok"))
        else:
            card("Estado", badge("Aún no hay movimientos", "warn"))

    # 2) Últimos movimientos (derecha)
    with col_right:
        st.markdown("### 🕓 Últimos movimientos")
        if hist is not None and not hist.empty:
            df_last = procesar_fechas(hist).sort_values("fecha_hora", ascending=False).head(6)
            for _, r in df_last.iterrows():
                icon = "🔑" if r["accion"] == "Entregada" else "✅"
                color = "warn" if r["accion"] == "Entregada" else "ok"
                card(
                    f"{icon} {r['accion']} — {r['salon']}",
                    f"👤 **{r['nombre']}** · 🏫 {r['area']}  \n"
                    f"{badge(r['accion'], color)} · 🕒 {r['fecha_hora'].strftime('%Y-%m-%d %H:%M')}"
                )
        else:
            card("Últimos movimientos", badge("Sin registros", "ok"))

    st.divider()

    # --- Actividad (7 días) ---
    st.markdown("### 📅 Actividad (últimos 7 días)")
    if hist is not None and not hist.empty:
        df_g = procesar_fechas(hist)
        ult7 = df_g[df_g["fecha_hora"] > (pd.Timestamp.now() - pd.Timedelta(days=7))]
        if not ult7.empty:
            by_day = (
                ult7.groupby(["fecha"])["id"].count()
                .reset_index()
                .rename(columns={"id": "movimientos"})
            )
            import altair as alt
            chart = (
                alt.Chart(by_day)
                .mark_bar()
                .encode(
                    x=alt.X("fecha:T", title="Fecha"),
                    y=alt.Y("movimientos:Q", title="Movimientos"),
                    tooltip=["fecha", "movimientos"],
                )
                .properties(height=240)
            )
            st.altair_chart(chart, use_container_width=True)
        else:
            card("Actividad", badge("No hay datos en los últimos 7 días", "warn"))
    else:
        card("Actividad", badge("Sin datos para graficar", "warn"))

    # (Opcional) Top salones de la semana — descomenta si quieres este mini-chart
    # st.markdown("#### 🏫 Top salones (7 días)")
    # if hist is not None and not hist.empty:
    #     df_g = procesar_fechas(hist)
    #     ult7 = df_g[df_g["fecha_hora"] > (pd.Timestamp.now() - pd.Timedelta(days=7))]
    #     if not ult7.empty:
    #         top_salones = (
    #             ult7.groupby("salon")["id"].count()
    #             .sort_values(ascending=False).head(8).reset_index()
    #             .rename(columns={"id": "movimientos"})
    #         )
    #         chart2 = (
    #             alt.Chart(top_salones)
    #             .mark_bar()
    #             .encode(
    #                 x=alt.X("movimientos:Q", title="Mov."),
    #                 y=alt.Y("salon:N", sort="-x", title="Salón"),
    #                 tooltip=["salon", "movimientos"],
    #             )
    #             .properties(height=220)
    #         )
    #         st.altair_chart(chart2, use_container_width=True)


elif menu_key == "registrar":
    st.header("📝 Registrar movimiento de llave")
    card("Instrucciones", "Completa los campos y registra **Entregada** o **Devuelta**.  \n"
                          + badge("Una llave no puede entregarse dos veces seguidas", "warn"))
    with st.form("form_llave", clear_on_submit=True):
        c1,c2 = st.columns(2)
        with c1:
            nombre = st.text_input("Instructor *")
            area = st.text_input("Programa *")
        with c2:
            salon = st.text_input("Salón *", placeholder="Ej: C3-204")
            accion = st.selectbox("Acción *", ["Entregada", "Devuelta"])
        if st.form_submit_button("Registrar", type="primary"):
            if not nombre or not area or not salon or not accion:
                st.error("Completa los campos obligatorios (*)")
            else:
                if accion == "Entregada" and llave_activa_por_salon(salon):
                    st.error(f"La llave del salón {salon} ya está prestada. Primero debe devolverse.")
                else:
                    registrar_evento(nombre, area, salon, accion, now_str())
                    b = badge("OK", "ok") if accion=="Devuelta" else badge("Entregada","warn")
                    card("Registro exitoso", f"{b}  \n**{accion}** para **{salon}** — **{nombre}** ({area})  \n🕒 {now_str()}")
                    st.rerun()

elif menu_key == "activas":
    st.header("🔐 Llaves actualmente entregadas")
    data = obtener_historial()
    if data is None or data.empty:
        card("Estado", badge("No hay llaves prestadas", "ok"))
    else:
        df = procesar_fechas(data)
        ult = df.sort_values("fecha_hora").groupby("salon").tail(1)
        activas = ult[ult["accion"] == "Entregada"].copy()

        if activas.empty:
            card("Estado", badge("No hay llaves prestadas", "ok"))
        else:
            colf1, colf2, colf3 = st.columns(3)
            with colf1:
                f_prof = st.selectbox("Profesor", ["Todos"] + sorted(activas["nombre"].unique().tolist()))
            with colf2:
                f_area = st.selectbox("Área", ["Todos"] + sorted(activas["area"].unique().tolist()))
            with colf3:
                f_salon = st.selectbox("Salón", ["Todos"] + sorted(activas["salon"].unique().tolist()))

            if f_prof != "Todos":  activas = activas[activas["nombre"] == f_prof]
            if f_area != "Todos":  activas = activas[activas["area"] == f_area]
            if f_salon != "Todos": activas = activas[activas["salon"] == f_salon]

            for idx, row in activas.iterrows():
                estado = badge("Entregada", "warn")
                card(
                    f"Salón {row['salon']} — {estado}",
                    f"👤 **{row['nombre']}** · 🏫 {row['area']}  \n🕒 {row['fecha_hora'].strftime('%Y-%m-%d %H:%M')}"
                )
                if st.button(f"Devolver {row['salon']}", key=f"dev_{idx}"):
                    registrar_evento(row["nombre"], row["area"], row["salon"], "Devuelta", now_str())
                    st.success(f"Llave de {row['salon']} devuelta.")
                    st.rerun()


elif menu_key == "historial":
    st.header("🕒 Historial de movimientos")
    data = obtener_historial()
    if data is None or data.empty:
        card("Historial", badge("Sin registros aún", "ok"))
    else:
        df = filtros_comunes(data, key_prefix="hist")
        st.dataframe(df[["id","fecha_hora","nombre","area","salon","accion"]],
                     use_container_width=True, hide_index=True)
        entregas = int((df["accion"]=="Entregada").sum())
        devols   = int((df["accion"]=="Devuelta").sum())
        c1,c2 = st.columns(2)
        with c1: card("Resumen", f"{badge('Entregadas','warn')} **{entregas}**  \n{badge('Devueltas','ok')} **{devols}**")
        with c2:
            st.download_button("Descargar CSV", data=df.to_csv(index=False).encode("utf-8"),
                               file_name="historial_llaves.csv", mime="text/csv")
        # (opcional) eliminar por ID si usas rol admin


elif menu_key == "inventario":
    # Crear tablas extra de inventario/rooms si faltan
    asegurar_esquema_inventario()
    from database import asegurar_campo_placa, existe_placa
    asegurar_campo_placa()

    st.header("🧰 Inventario de equipos")

    # Diagnóstico rápido
    from database import RUTA_BD
    st.caption(f"BD usada: **{RUTA_BD}**")
    inv_now = obtener_inventario()
    st.caption(f"Registros actuales: **{0 if inv_now is None else len(inv_now)}**")

    tab_add, tab_upload, tab_view, tab_tpl = st.tabs(
        ["➕ Agregar equipo", "⤴️ Cargar archivo", "📋 Ver / Editar / Exportar", "📑 Plantillas"]
    )

    # ---------- TAB: AGREGAR ----------
    with tab_add:
        with st.form("form_inv_add", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                nombre = st.text_input("Nombre del equipo *", placeholder="Osciloscopio, Multímetro…", key="inv_add_nombre")
                tipo = st.selectbox("Tipo/Categoría *", options=CATEGORIAS_VALIDAS,
                                    index=CATEGORIAS_VALIDAS.index("Otro"), key="inv_add_tipo")
            with c2:
                estado = st.selectbox("Estado *", options=ESTADOS_VALIDOS, key="inv_add_estado")
                salon  = st.text_input("Salón (código)", placeholder="C3-204 (o BODEGA)", key="inv_add_salon")
            with c3:
                responsable = st.text_input("Responsable (opcional)", key="inv_add_resp")
                placa = st.text_input("Placa (opcional, única para activos de alto valor)", key="inv_add_placa").strip().upper()
                fecha_registro = now_str()

            if st.form_submit_button("Guardar", type="primary", key="inv_add_submit"):
                if not nombre.strip():
                    st.error("El nombre es obligatorio.")
                else:
                    tipo_n   = tipo.strip().title()
                    estado_n = estado.strip()
                    salon_n  = (salon or "").strip().upper()
                    placa_n  = placa or None

                    # Validación de placa (si viene)
                    if placa_n and existe_placa(placa_n):
                        st.error(f"La placa {placa_n} ya existe en el inventario.")
                    else:
                        if salon_n not in ("", "BODEGA"):
                            registrar_salon(salon_n)
                        agregar_equipo(
                            nombre.strip(), tipo_n, estado_n, salon_n,
                            (responsable or "").strip(), fecha_registro, placa_n
                        )
                        st.success("Equipo agregado.")
                        st.rerun()

    # ---------- TAB: CARGAR ARCHIVO ----------
    with tab_upload:
        st.markdown("Sube un **XLSX** o **CSV** con el inventario.")
        file = st.file_uploader("Archivo", type=["xlsx", "csv"], key="inv_up_file")
        sep = st.selectbox("Separador (para CSV)", [",", ";", "|"], index=0, key="inv_up_sep")

        if file is not None:
            try:
                if file.name.lower().endswith(".xlsx"):
                    df_raw = pd.read_excel(file)
                else:
                    df_raw = pd.read_csv(file, sep=sep)
            except Exception as e:
                st.error(f"Error leyendo el archivo: {e}")
                df_raw = None

            if df_raw is not None:
                # (1) NORMALIZAR ENCABEZADOS (acepta variantes)
                df_raw.columns = df_raw.columns.str.strip().str.lower()
                alias = {"nombre equipo": "nombre", "equipo": "nombre", "ubicación": "salon", "salón": "salon"}
                df_raw = df_raw.rename(columns=alias)

                st.subheader("Previsualización")
                st.dataframe(df_raw.head(20), use_container_width=True)

                st.subheader("Validación")
                REQUIRED = ["nombre", "tipo", "estado", "salon", "responsable", "fecha_registro"]
                faltantes = [c for c in REQUIRED if c not in df_raw.columns]
                if faltantes:
                    st.error(f"Faltan columnas obligatorias: {faltantes}")
                else:
                    df = df_raw.copy()

                    # Normalización básica
                    for c in df.columns:
                        if df[c].dtype == object:
                            df[c] = df[c].astype(str).str.strip()
                    df["tipo"]   = df["tipo"].str.title()
                    df["estado"] = df["estado"].str.title()
                    df["salon"]  = df["salon"].str.upper().fillna("")

                    errores = []
                    if (~df["tipo"].isin(CATEGORIAS_VALIDAS)).any():
                        errores.append(f"Tipos inválidos: {sorted(df.loc[~df['tipo'].isin(CATEGORIAS_VALIDAS),'tipo'].unique().tolist())}")
                    if (~df["estado"].isin(ESTADOS_VALIDOS)).any():
                        errores.append(f"Estados inválidos: {sorted(df.loc[~df['estado'].isin(ESTADOS_VALIDOS),'estado'].unique().tolist())}")

                    # (2) VALIDAR Y FORMATEAR FECHA
                    try:
                        fecha_ok = pd.to_datetime(df["fecha_registro"], errors="raise")
                        df["fecha_registro"] = fecha_ok.dt.strftime("%Y-%m-%d")  # ISO limpio
                    except Exception:
                        errores.append("fecha_registro debe estar en formato YYYY-MM-DD o fecha válida.")

                    # (3) PLACA (opcional, única)
                    if "placa" not in df.columns:
                        df["placa"] = None
                    else:
                        df["placa"] = df["placa"].fillna("").astype(str).str.strip().str.upper().replace({"": None})

                    # Duplicados en archivo (ignorando vacíos)
                    placas_no_nulas = df["placa"].dropna()
                    if placas_no_nulas.duplicated().any():
                        dups = sorted(placas_no_nulas[placas_no_nulas.duplicated()].unique().tolist())
                        errores.append(f"Placas duplicadas en el archivo: {dups}")

                    # Duplicados con la BD
                    if df["placa"].notna().any():
                        inv_existente = obtener_inventario()
                        if inv_existente is not None and not inv_existente.empty and "placa" in inv_existente.columns:
                            existentes = set(inv_existente["placa"].dropna().unique().tolist())
                            conflictivas = sorted([p for p in df["placa"].dropna().unique().tolist() if p in existentes])
                            if conflictivas:
                                errores.append(f"Placas ya existentes en BD: {conflictivas}")

                    if errores:
                        for e in errores: st.error(e)
                    else:
                        st.success("Validación OK ✅")
                        if st.checkbox("Registrar salones inexistentes automáticamente", key="inv_up_autoroom"):
                            for code in sorted(df["salon"].dropna().unique().tolist()):
                                if code and code != "BODEGA":
                                    registrar_salon(code)

                        if st.button("Guardar en inventario", type="primary", key="inv_up_save"):
                            try:
                                insertar_inventario_masivo(df)  # incluye 'placa'
                                st.success(f"{len(df)} filas importadas.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error guardando: {e}")

    # ---------- TAB: VER / EDITAR / EXPORTAR ----------
    with tab_view:
        inv = obtener_inventario()
        if inv is None or inv.empty:
            st.info("No hay equipos.")
        else:
            df = inv.copy()
            if "placa" not in df.columns:
                df["placa"] = None

            # Filtros
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                f_tipo = st.selectbox("Tipo", ["Todos"] + sorted(df["tipo"].dropna().unique().tolist()), key="inv_view_tipo")
            with c2:
                f_estado = st.selectbox("Estado", ["Todos"] + ESTADOS_VALIDOS, key="inv_view_estado")
            with c3:
                f_salon = st.selectbox("Salón", ["Todos"] + sorted(df["salon"].fillna("").unique().tolist()), key="inv_view_salon")
            with c4:
                q = st.text_input("Buscar (placa/nombre/tipo/salón)", key="inv_view_q")

            if f_tipo != "Todos":   df = df[df["tipo"] == f_tipo]
            if f_estado != "Todos": df = df[df["estado"] == f_estado]
            if f_salon != "Todos":  df = df[df["salon"].fillna("") == f_salon]
            if q:
                ql = q.lower()
                df = df[
                    df["placa"].fillna("").str.lower().str.contains(ql)
                    | df["nombre"].str.lower().str.contains(ql)
                    | df["tipo"].str.lower().str.contains(ql)
                    | df["salon"].fillna("").str.lower().str.contains(ql)
                ]

            # Tabla + Export
            cols_tabla = ["id", "placa", "nombre", "tipo", "estado", "salon", "responsable", "fecha_registro"]
            st.dataframe(df[cols_tabla], use_container_width=True, hide_index=True)
            st.download_button(
                "Exportar CSV",
                df[cols_tabla].to_csv(index=False).encode("utf-8"),
                file_name="inventario_filtrado.csv",
                mime="text/csv",
                key="inv_view_export"
            )

            colA, colB, colC, colD = st.columns(4)
            with colB:
                row_id = st.number_input("ID para editar", min_value=0, step=1, key="inv_view_row")
            with colC:
                nuevo_estado = st.selectbox("Nuevo estado", ESTADOS_VALIDOS, key="inv_view_new_estado")
            with colD:
                nuevo_salon = st.text_input("Nuevo salón (código)", placeholder="C3-204 / BODEGA",
                                            key="inv_view_new_salon").strip().upper()

            nueva_placa = st.text_input("Nueva placa (opcional, única)", key="inv_view_new_placa").strip().upper()

            if st.button("Aplicar cambios", key="inv_view_apply"):
                inv_full = obtener_inventario()
                if inv_full is None or inv_full.empty or row_id not in inv_full["id"].values:
                    st.warning("ID no existente.")
                else:
                    updates = {"estado": nuevo_estado}

                    if nuevo_salon:
                        updates["salon"] = nuevo_salon
                        if nuevo_salon != "BODEGA":
                            registrar_salon(nuevo_salon)

                    if nueva_placa:
                        # validar unicidad excepto si es la misma del registro editado
                        reg_actual = inv_full[inv_full["id"] == int(row_id)].iloc[0]
                        placa_actual = str(reg_actual.get("placa") or "").upper()
                        if nueva_placa != placa_actual and existe_placa(nueva_placa):
                            st.error(f"La placa {nueva_placa} ya existe.")
                            st.stop()
                        updates["placa"] = nueva_placa

                    actualizar_equipo(int(row_id), **updates)
                    st.success("Actualizado.")
                    st.rerun()

            st.divider()

            # Eliminar
            del_id = st.number_input("Eliminar registro ID", min_value=0, step=1, key="inv_view_del_id")
            if st.button("Eliminar", type="secondary", key="inv_view_delete"):
                inv_full = obtener_inventario()
                if inv_full is not None and not inv_full.empty and del_id in inv_full["id"].values:
                    eliminar_equipo(int(del_id))
                    st.success("Eliminado.")
                    st.rerun()
                else:
                    st.warning("ID no encontrado.")

    # ---------- TAB: PLANTILLAS ----------
    with tab_tpl:
        st.markdown("### Plantillas de carga (estandarizadas)")
        # Usamos encabezados estándar y añadimos 'placa' (opcional)
        cols = ["nombre","tipo","estado","salon","responsable","fecha_registro","placa"]
        ejemplo = pd.DataFrame([
            ["Osciloscopio 100MHz","Osciloscopio","Disponible","C3-204","Mateo","2025-10-17","EQ-OSC-0001"],
            ["Multímetro TRMS","Multímetro","En uso","C3-204","Mateo","2025-10-17",""]  # consumible sin placa
        ], columns=cols)
        st.dataframe(ejemplo, use_container_width=True)

        # CSV
        st.download_button(
            "Descargar plantilla CSV",
            ejemplo.to_csv(index=False).encode("utf-8"),
            file_name="plantilla_inventario.csv",
            mime="text/csv",
            key="inv_tpl_csv"
        )

        # XLSX
        import io
        bio = io.BytesIO()
        with pd.ExcelWriter(bio, engine="xlsxwriter") as writer:
            ejemplo.to_excel(writer, index=False, sheet_name="inventario_template")
            pd.DataFrame({"CATEGORIAS_VALIDAS": CATEGORIAS_VALIDAS}).to_excel(writer, index=False, sheet_name="listas")
            pd.DataFrame({"ESTADOS_VALIDOS": ESTADOS_VALIDOS}).to_excel(writer, index=False, sheet_name="listas", startcol=2)
        st.download_button(
            "Descargar plantilla XLSX",
            data=bio.getvalue(),
            file_name="plantilla_inventario.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="inv_tpl_xlsx"
        )


elif menu_key == "stats":
    st.header("📈 Estadísticas")

    # ----- Datos base -----
    hist = obtener_historial()
    inv  = obtener_inventario()

    if (hist is None or hist.empty) and (inv is None or inv.empty):
        card("Sin datos", badge("Aún no hay información para graficar", "warn"))
    else:
        # ---------- KPIs ----------
        total_mov = 0 if hist is None or hist.empty else len(hist)
        total_ent = 0 if hist is None or hist.empty else int((hist["accion"] == "Entregada").sum())
        total_dev = 0 if hist is None or hist.empty else int((hist["accion"] == "Devuelta").sum())
        total_inv = 0 if inv is None or inv.empty else len(inv)

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("📝 Movimientos", total_mov)
        k2.metric("🔑 Entregas", total_ent)
        k3.metric("✅ Devoluciones", total_dev)
        k4.metric("🧰 Equipos inventario", total_inv)

        st.divider()

        # ---------- Filtros ----------
        if hist is not None and not hist.empty:
            dfh = procesar_fechas(hist.copy())
            hoy = pd.Timestamp.now().normalize()
            fecha_ini = hoy - pd.Timedelta(days=30)
            c1, c2, c3 = st.columns(3)
            with c1:
                rango = st.date_input("Rango (llaves)", [fecha_ini.date(), hoy.date()], key="flt_stats_rango")
            with c2:
                f_salon = st.selectbox("Salón", ["Todos"] + sorted(dfh["salon"].dropna().unique().tolist()), key="flt_stats_salon")
            with c3:
                f_area = st.selectbox("Área", ["Todos"] + sorted(dfh["area"].dropna().unique().tolist()), key="flt_stats_area")

            # aplica filtros
            if isinstance(rango, list) and len(rango) == 2:
                ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1]) + pd.Timedelta(days=1)
                dfh = dfh[(dfh["fecha_hora"] >= ini) & (dfh["fecha_hora"] < fin)]
            if f_salon != "Todos":
                dfh = dfh[dfh["salon"] == f_salon]
            if f_area != "Todos":
                dfh = dfh[dfh["area"] == f_area]
        else:
            dfh = None

        # ============ Gráfico 1: Movimientos diarios (últimos 30 días / filtrado) ============
        st.subheader("🗓️ Movimientos por día")
        if dfh is None or dfh.empty:
            card("Movimientos por día", badge("Sin datos de llaves en el rango", "warn"))
        else:
            g1 = (dfh.groupby(dfh["fecha_hora"].dt.date)["id"]
                  .count().reset_index().rename(columns={"fecha_hora":"fecha","id":"movimientos"}))
            import altair as alt
            chart1 = (
                alt.Chart(g1)
                .mark_bar()
                .encode(
                    x=alt.X("fecha:T", title="Fecha"),
                    y=alt.Y("movimientos:Q", title="Movimientos"),
                    tooltip=["fecha:T", "movimientos:Q"],
                )
                .properties(height=240)
            )
            st.altair_chart(chart1, use_container_width=True)

        st.divider()

        # ============ Gráfico 2: Top salones e instructores ============
        colA, colB = st.columns(2)
        with colA:
            st.subheader("🏫 Top salones")
            if dfh is None or dfh.empty:
                card("Top salones", badge("Sin datos", "warn"))
            else:
                top_salones = (dfh.groupby("salon")["id"].count()
                               .sort_values(ascending=False).head(8).reset_index()
                               .rename(columns={"id":"mov"}))
                import altair as alt
                chart3 = (
                    alt.Chart(top_salones)
                    .mark_bar()
                    .encode(
                        x=alt.X("mov:Q", title="Movimientos"),
                        y=alt.Y("salon:N", sort="-x", title="Salón"),
                        tooltip=["salon","mov"]
                    )
                    .properties(height=240)
                )
                st.altair_chart(chart3, use_container_width=True)

        with colB:
            st.subheader("👤 Top instructores")
            if dfh is None or dfh.empty:
                card("Top instructores", badge("Sin datos", "warn"))
            else:
                top_prof = (dfh.groupby("nombre")["id"].count()
                            .sort_values(ascending=False).head(8).reset_index()
                            .rename(columns={"id":"mov"}))
                import altair as alt
                chart4 = (
                    alt.Chart(top_prof)
                    .mark_bar()
                    .encode(
                        x=alt.X("mov:Q", title="Movimientos"),
                        y=alt.Y("nombre:N", sort="-x", title="Instructor"),
                        tooltip=["nombre","mov"]
                    )
                    .properties(height=240)
                )
                st.altair_chart(chart4, use_container_width=True)

        st.divider()

        # ============ Gráfico 3: Estado del inventario ============
        st.subheader("🧰 Estado del inventario")
        if inv is None or inv.empty:
            card("Inventario", badge("No hay equipos registrados", "warn"))
        else:
            g5 = inv.groupby("estado")["id"].count().reset_index().rename(columns={"id":"cantidad"})
            # donut sencillo
            import altair as alt
            chart5 = (
                alt.Chart(g5)
                .mark_arc(innerRadius=60)
                .encode(
                    theta="cantidad:Q",
                    color=alt.Color("estado:N", legend=None),
                    tooltip=["estado","cantidad"]
                )
                .properties(height=280)
            )
            st.altair_chart(chart5, use_container_width=False)


# ========== Inventario por salón ============
elif menu_key == "inv_salon":
    st.header("🏫 Inventario por salón")
    from database import mover_equipo

    # --- Datos base ---
    inv = obtener_inventario()
    if inv is None or inv.empty:
        card("Inventario", badge("No hay equipos registrados", "warn"))
        st.stop()

    # Normalización
    df_all = inv.copy()
    df_all["salon"] = df_all["salon"].fillna("").replace("", "BODEGA").str.upper()
    if "placa" not in df_all.columns:
        df_all["placa"] = None

    # Salones existentes (rooms + inventario)
    try:
        rooms_df = obtener_salones()
        rooms = rooms_df["codigo"].str.upper().tolist() if not rooms_df.empty else []
    except Exception:
        rooms = []
    salones_disponibles = sorted(set(rooms) | set(df_all["salon"].unique().tolist()))

    # Selector salón + creación rápida
    cA, cB = st.columns([3, 2])
    with cA:
        salon_sel = st.selectbox("Selecciona un salón", salones_disponibles, index=0, key="inv_room_sel")
    with cB:
        st.caption("Crear salón")
        nuevo_salon = st.text_input("Código nuevo (ej: C3-204)", key="inv_room_new").strip().upper()
        if st.button("➕ Registrar salón", key="inv_room_add"):
            if not nuevo_salon:
                st.warning("Escribe un código.")
            else:
                registrar_salon(nuevo_salon)
                st.success(f"Salón {nuevo_salon} registrado.")
                st.rerun()

    # Subconjunto del salón seleccionado
    df = df_all[df_all["salon"] == salon_sel].copy()
    if df.empty:
        card(f"Salón {salon_sel}", badge("Sin equipos en este salón", "warn"))
        st.stop()

    # KPIs
    total = len(df)
    disp = int((df["estado"] == "Disponible").sum())
    uso  = int((df["estado"] == "En uso").sum())
    dan  = int((df["estado"] == "Dañado").sum())
    ext  = int((df["estado"] == "Extraviado").sum())
    sin_placa = int(df["placa"].isna().sum())
    k1,k2,k3,k4,k5 = st.columns(5)
    k1.metric("Total", total)
    k2.metric("Disponibles", disp)
    k3.metric("En uso", uso)
    k4.metric("Dañados", dan)
    k5.metric("Extraviados", ext)
    st.caption(f"🔘 Equipos sin placa (consumibles): **{sin_placa}**")

    st.divider()

    # Filtros y búsqueda (incluye placa)
    c1,c2,c3 = st.columns(3)
    with c1:
        f_tipo = st.selectbox("Tipo", ["Todos"] + sorted(df["tipo"].dropna().unique().tolist()), key="inv_room_tipo")
    with c2:
        f_estado = st.selectbox("Estado", ["Todos","Disponible","En uso","Dañado","Extraviado"], key="inv_room_estado")
    with c3:
        q = st.text_input("Buscar (placa / nombre / tipo / responsable)", key="inv_room_q")

    df_f = df.copy()
    if f_tipo != "Todos":   df_f = df_f[df_f["tipo"] == f_tipo]
    if f_estado != "Todos": df_f = df_f[df_f["estado"] == f_estado]
    if q:
        ql = q.lower()
        df_f = df_f[
            df_f["placa"].fillna("").str.lower().str.contains(ql)
            | df_f["nombre"].str.lower().str.contains(ql)
            | df_f["tipo"].str.lower().str.contains(ql)
            | df_f["responsable"].fillna("").str.lower().str.contains(ql)
        ]

    # Tabla + export
    st.markdown(f"### 📋 Equipos en **{salon_sel}**")
    cols_show = ["id","placa","nombre","tipo","estado","responsable","fecha_registro"]
    st.dataframe(df_f[cols_show], use_container_width=True, hide_index=True)

    st.download_button(
        "⬇️ Exportar CSV del salón",
        df_f[cols_show].to_csv(index=False).encode("utf-8"),
        file_name=f"inventario_{salon_sel}.csv",
        mime="text/csv",
        key="inv_room_export_csv"
    )

    # Export XLSX
    import io
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="xlsxwriter") as writer:
        df_f[cols_show].to_excel(writer, index=False, sheet_name=f"{salon_sel}_inventario")
    st.download_button(
        "⬇️ Exportar XLSX del salón",
        data=bio.getvalue(),
        file_name=f"inventario_{salon_sel}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="inv_room_export_xlsx"
    )

    st.divider()

    # Acciones en lote
    st.markdown("### ⚙️ Acciones en lote")
    ids_disponibles = df_f["id"].tolist()
    ids_sel = st.multiselect("Selecciona IDs", ids_disponibles, key="inv_room_ids")

    cA1, cA2, cA3 = st.columns(3)
    with cA1:
        nuevo_estado = st.selectbox("Cambiar a estado", ["Disponible","En uso","Dañado","Extraviado"], key="inv_room_state")
        if st.button("Cambiar estado", key="inv_room_change"):
            if not ids_sel:
                st.warning("Selecciona al menos un ID.")
            else:
                for _id in ids_sel:
                    actualizar_equipo(int(_id), estado=nuevo_estado)
                st.success(f"Estado actualizado en {len(ids_sel)} equipo(s).")
                st.rerun()

    with cA2:
        target = st.text_input("Mover al salón", placeholder="Ej: C3-205", key="inv_room_target").strip().upper()
        motivo = st.selectbox("Motivo", ["Traslado", "Préstamo", "Mantenimiento", "Auditoría", "Otro"], key="inv_room_motivo")
        resp_mv = st.text_input("Responsable del movimiento", key="inv_room_resp")
        notas_mv = st.text_area("Notas (opcional)", key="inv_room_notas", height=70)

        if st.button("Mover equipo(s)", key="inv_room_move"):
            if not ids_sel:
                st.warning("Selecciona al menos un ID.")
            elif not target:
                st.warning("Indica el salón destino.")
            else:
                registrar_salon(target)  # asegura existencia
                ok, fail = 0, 0
                for _id in ids_sel:
                    try:
                        mover_equipo(
                            int(_id), target, motivo, resp_mv or "N/A",
                            fecha_hora=now_str(), notas=notas_mv or None
                        )
                        ok += 1
                    except Exception as e:
                        fail += 1
                st.success(f"Movidos {ok} equipo(s) a {target}. {f'Fallidos: {fail}' if fail else ''}")
                st.rerun()

    with cA3:
        if st.button("Eliminar seleccionados", type="secondary", key="inv_room_delete"):
            if not ids_sel:
                st.warning("Selecciona al menos un ID.")
            else:
                for _id in ids_sel:
                    eliminar_equipo(int(_id))
                st.success(f"Eliminados {len(ids_sel)} equipo(s).")
                st.rerun()

    st.divider()

    # Resumen por tipo (tarjetas)
    st.markdown("### 🧩 Resumen por tipo")
    g_tipo = (df.groupby("tipo")["id"].count().reset_index().rename(columns={"id":"cantidad"}))
    for _, r in g_tipo.iterrows():
        card(f"{r['tipo']}", f"**{int(r['cantidad'])}** equipo(s) en {salon_sel}")

    # Distribución por tipo (gráfico)
    import altair as alt
    st.markdown("### 📊 Distribución por tipo")
    chart = (
        alt.Chart(g_tipo)
        .mark_bar()
        .encode(
            x=alt.X("tipo:N", title="Tipo de equipo", sort="-y"),
            y=alt.Y("cantidad:Q", title="Cantidad"),
            tooltip=["tipo","cantidad"]
        )
        .properties(height=280)
    )
    st.altair_chart(chart, use_container_width=True)

elif menu_key == "mov_equipos":
    from database import asegurar_esquema_movimientos, obtener_movimientos, movimientos_por_placa
    asegurar_esquema_movimientos()

    st.header("🔀 Movimientos de equipos (trazabilidad)")
    st.caption("Filtra, revisa y exporta el historial de traslados/ajustes de equipos.")

    # Filtros
    c1, c2, c3 = st.columns(3)
    with c1:
        f_placa = st.text_input("Placa (exacta)", key="mov_f_placa").strip().upper()
    with c2:
        f_origen = st.text_input("Salón origen", key="mov_f_origen").strip().upper()
    with c3:
        f_dest   = st.text_input("Salón destino", key="mov_f_dest").strip().upper()

    c4, c5, c6 = st.columns(3)
    with c4:
        f_resp = st.text_input("Responsable (contiene)", key="mov_f_resp")
    with c5:
        f_ini  = st.date_input("Desde (fecha)", value=None, key="mov_f_ini")
    with c6:
        f_fin  = st.date_input("Hasta (fecha)", value=None, key="mov_f_fin")

    fecha_ini = f_ini.strftime("%Y-%m-%d") if f_ini else None
    fecha_fin = f_fin.strftime("%Y-%m-%d") if f_fin else None

    dfm = obtener_movimientos(
        fecha_ini=fecha_ini, fecha_fin=fecha_fin,
        placa=f_placa or None,
        salon_origen=f_origen or None,
        salon_destino=f_dest or None,
        responsable=f_resp or None
    )

    st.markdown("### 📋 Resultados")
    if dfm is None or dfm.empty:
        card("Movimientos", badge("Sin movimientos con los filtros actuales", "warn"))
    else:
        # Orden visual y columnas
        dfm = dfm[["id","fecha_hora","placa","inventario_id","salon_origen","salon_destino","motivo","responsable","notas"]]
        st.dataframe(dfm, use_container_width=True, hide_index=True)

        # Export
        st.download_button(
            "⬇️ Exportar CSV",
            dfm.to_csv(index=False).encode("utf-8"),
            file_name="movimientos_equipos.csv",
            mime="text/csv",
            key="mov_export_csv"
        )

    st.divider()

    # Recorrido por placa (timeline simple)
    st.markdown("### 🧭 Recorrido por placa")
    placa_q = st.text_input("Consultar recorrido de la placa", key="mov_rec_placa").strip().upper()
    if placa_q:
        line = movimientos_por_placa(placa_q)
        if line is None or line.empty:
            card("Recorrido", badge("Sin movimientos registrados para esta placa", "warn"))
        else:
            # Orden cronológico
            line = line.sort_values("fecha_hora")
            # Mostrar tipo “timeline” textual
            for _, r in line.iterrows():
                card(
                    f"🕒 {r['fecha_hora']} — {r['motivo'] or 'Movimiento'}",
                    f"🔖 Placa: **{placa_q}**  \n"
                    f"📦 {r['salon_origen'] or '—'} → **{r['salon_destino']}**  \n"
                    f"👤 Responsable: {r['responsable'] or 'N/A'}  \n"
                    f"📝 {r['notas'] or ''}"
                )
