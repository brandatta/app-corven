# app.py
import streamlit as st
import pandas as pd
import mysql.connector
from mysql.connector import ClientFlag
import tempfile
import os
from PIL import Image
import base64
import io
import string

st.set_page_config(page_title="Subida CSV/XLSX → modelo_ap", layout="centered")

# ------------ Utilidades ------------
def get_base64_logo(path="logorelleno.png"):
    try:
        img = Image.open(path).resize((40, 40))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode()
    except Exception:
        return None

def open_connection():
    return mysql.connector.connect(
        host=st.secrets["DB_HOST"],
        user=st.secrets["DB_USER"],
        password=st.secrets["DB_PASSWORD"],
        database=st.secrets["DB_NAME"],
        charset="utf8mb4",
        use_unicode=True,
        allow_local_infile=True,
        client_flags=[ClientFlag.LOCAL_FILES]
    )

def excel_letter_to_index(letter: str) -> int:
    """
    Convierte una letra de columna estilo Excel (A, B, ... Z, AA, AB, ...) a índice 0-based.
    """
    letter = letter.strip().upper()
    val = 0
    for ch in letter:
        if not ('A' <= ch <= 'Z'):
            raise ValueError("Solo letras A-Z")
        val = val * 26 + (ord(ch) - ord('A') + 1)
    return val - 1  # 0-based

def make_excel_headers(n_cols: int):
    """
    Genera nombres tipo Excel A, B, ..., Z, AA, AB ... según cantidad de columnas.
    """
    headers = []
    i = 1
    while len(headers) < n_cols:
        s, x = "", i
        while x:
            x, r = divmod(x - 1, 26)
            s = chr(65 + r) + s
        headers.append(s)
        i += 1
    return headers

logo_b64 = get_base64_logo()

# ------------ Estilos ------------
st.markdown("""
    <style>
    .main { background-color: #d4fdb7 !important; }
    .main > div:first-child { padding-top: 0rem; }
    .header-container {
        display:flex; justify-content:space-between; align-items:center;
        padding:2px 0 10px 0; border-bottom:2px solid #d4fdb7; margin-bottom:20px;
    }
    .header-title {
        font-size:24px; font-weight:bold; color:#d4fdb7;
        text-shadow:-1px -1px 0 #64352c, 1px -1px 0 #64352c, -1px 1px 0 #64352c, 1px 1px 0 #64352c;
    }
    .header-logo img { height:40px; }
    button[kind="primary"] { background-color:#64352c !important; border-color:#64352c !important; color:white !important; }
    button[kind="primary"]:hover { background-color:#4f2923 !important; border-color:#4f2923 !important; }
    .stAlert[data-baseweb="alert"] { background-color:#f6fff0; color:#64352c !important; font-weight:bold; }
    label, .stSelectbox label, .stFileUploader label { color:#64352c !important; }
    </style>
""", unsafe_allow_html=True)

# ------------ Header ------------
if logo_b64:
    st.markdown(f"""
    <div class="header-container">
        <div class="header-title">Subida de CSV/XLSX → <strong>app_marco_new.modelo_ap</strong></div>
        <div class="header-logo"><img src="data:image/png;base64,{logo_b64}" /></div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div class="header-container">
        <div class="header-title">Subida de CSV/XLSX → <strong>app_marco_new.modelo_ap</strong></div>
    </div>
    """, unsafe_allow_html=True)

st.info("Al confirmar, se **reemplazan** los datos de `app_marco_new.modelo_ap` por los del archivo subido (TRUNCATE + LOAD). "
        "Esta versión asume **archivos sin encabezados** (columnas tipo A, B, C...).")

# ------------ Lógica principal ------------
uploaded_file = st.file_uploader("Subí tu archivo CSV o XLSX (sin encabezados)", type=["csv", "xlsx"])

if uploaded_file:
    # Leer SIN encabezados → columnas 0..n-1
    if uploaded_file.name.lower().endswith(".csv"):
        df = pd.read_csv(uploaded_file, header=None)
    else:
        df = pd.read_excel(uploaded_file, header=None)  # requiere openpyxl

    # Renombrar columnas SOLO para visualización como letras Excel
    excel_cols = make_excel_headers(df.shape[1])
    df_display = df.copy()
    df_display.columns = excel_cols

    # --- Métricas inmediatas ---
    st.write(f"**Filas detectadas:** {df.shape[0]}")
    # Selector de columna (letra). Default 'N' si existe, sino primera.
    default_letter = "N" if "N" in excel_cols else excel_cols[0]
    col_letter = st.selectbox("Columna para sumar (letra estilo Excel)", options=excel_cols, index=excel_cols.index(default_letter))
    try:
        idx = excel_letter_to_index(col_letter)
        suma_col = pd.to_numeric(df.iloc[:, idx], errors="coerce").sum()
        st.write(f"**Suma de columna {col_letter}:** {suma_col:,.2f}")
    except Exception as e:
        st.warning(f"No pude calcular la suma de la columna {col_letter}: {e}")

    # Vista previa
    st.write("Vista previa del archivo:")
    st.dataframe(df_display.head(100), use_container_width=True)

    # Confirmación
    if st.button("Cargar y reemplazar tabla", type="primary"):
        try:
            if df.empty:
                st.warning("El archivo no tiene filas.")
            else:
                # Guardar a CSV temporal SIN encabezados (porque la tabla se carga por posición)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", encoding="utf-8", newline="\n") as tmp:
                    # header=False: no escribimos encabezado
                    df.to_csv(tmp.name, index=False, header=False)
                    temp_path = tmp.name

                # Conectar a MySQL
                conn = open_connection()
                cur = conn.cursor()

                # 1) TRUNCATE
                cur.execute("TRUNCATE TABLE `app_marco_new`.`modelo_ap`;")

                # 2) LOAD DATA LOCAL INFILE por posición (sin lista de columnas)
                csv_path = temp_path.replace("\\", "\\\\")  # por si Windows
                load_sql = f"""
                LOAD DATA LOCAL INFILE '{csv_path}'
                INTO TABLE `app_marco_new`.`modelo_ap`
                CHARACTER SET utf8mb4
                FIELDS TERMINATED BY ',' ENCLOSED BY '"' ESCAPED BY '"'
                LINES TERMINATED BY '\\n';
                """  # No usamos IGNORE 1 ROWS porque nuestro CSV NO tiene encabezados
                cur.execute(load_sql)
                conn.commit()

                # Contar filas cargadas
                cur.execute("SELECT COUNT(*) FROM `app_marco_new`.`modelo_ap`;")
                total = cur.fetchone()[0]

                cur.close()
                conn.close()

                # Limpiar archivo temporal
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

                st.success(f"Carga completada. Filas actuales en `modelo_ap`: {total}.")

        except Exception as e:
            st.error(f"Error durante la carga: {e}")
