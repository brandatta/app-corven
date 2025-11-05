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

st.set_page_config(page_title="Subida CSV/XLSX", layout="centered")

# ---- Logo a base64 (opcional) ----
def get_base64_logo(path="logorelleno.png"):
    try:
        img = Image.open(path).resize((40, 40))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode()
    except Exception:
        return None

logo_b64 = get_base64_logo()

# ---- Estilos ----
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

# ---- Header ----
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

st.info("Al confirmar, se **reemplazan** los datos de `app_marco_new.modelo_ap` por los del archivo subido (TRUNCATE + LOAD).")

# -------------------- LÓGICA PRINCIPAL --------------------
uploaded_file = st.file_uploader("Subí tu archivo CSV o XLSX", type=["csv", "xlsx"])

def open_connection():
    # Asegurate de tener estos valores en .streamlit/secrets.toml
    # [general]
    # [connections.mysql]
    # DB_HOST="..."
    # DB_USER="..."
    # DB_PASSWORD="..."
    # DB_NAME="..."
    # O bien en st.secrets directamente como abajo:
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

if uploaded_file:
    # Leer archivo a DataFrame
    if uploaded_file.name.lower().endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    # Vista previa
    st.write("Vista previa del archivo:")
    st.dataframe(df.head(100), use_container_width=True)

    # Confirmación
    if st.button("Cargar y reemplazar tabla", type="primary"):
        try:
            if df.empty:
                st.warning("El archivo no tiene filas.")
            else:
                # Guardar a CSV temporal (con encabezados) para usar LOAD DATA
                with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", encoding="utf-8", newline="\n") as tmp:
                    df.to_csv(tmp.name, index=False)
                    temp_path = tmp.name

                # Conectar a MySQL
                conn = open_connection()
                cur = conn.cursor()

                # 1) TRUNCATE
                cur.execute("TRUNCATE TABLE `app_marco_new`.`modelo_ap`;")

                # 2) LOAD DATA LOCAL INFILE con mapeo de columnas por nombre
                #    IMPORTANTE: los nombres de columna del archivo deben coincidir con los de la tabla.
                cols = ", ".join(f"`{c}`" for c in df.columns.tolist())

                # Fix path para Windows si aplica
                csv_path = temp_path.replace("\\", "\\\\")

                load_sql = f"""
                LOAD DATA LOCAL INFILE '{csv_path}'
                INTO TABLE `app_marco_new`.`modelo_ap`
                CHARACTER SET utf8mb4
                FIELDS TERMINATED BY ',' ENCLOSED BY '"' ESCAPED BY '"'
                LINES TERMINATED BY '\\n'
                IGNORE 1 ROWS
                ({cols});
                """
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
