import streamlit as st
import os
import subprocess
import json
import uuid
import requests
import re
from pathlib import Path
from datetime import datetime, timedelta
import hashlib

# ============ CONFIGURACIÓN INICIAL ============
st.set_page_config(
    page_title="VideoAI Studio Pro",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============ SISTEMA DE ARCHIVOS EN LA NUBE ============
BASE_PATH = Path("/tmp/videoai-studio")
UPLOADS = BASE_PATH / "uploads"
OUTPUTS = BASE_PATH / "outputs"
DATABASE = BASE_PATH / "database"
PLANTILLAS = BASE_PATH / "plantillas"

for carpeta in [BASE_PATH, UPLOADS, OUTPUTS, DATABASE, PLANTILLAS]:
    carpeta.mkdir(parents=True, exist_ok=True)

# ============ BASE DE DATOS SIMPLE (JSON) ============
DB_FILE = DATABASE / "sistema.json"

def cargar_db():
    if DB_FILE.exists():
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "usuarios": [],
        "plantillas": [],
        "membresias": [
            {
                "id": "gratis",
                "nombre": "Gratis",
                "precio": 0,
                "tokens": 3,
                "features": ["3 videos/mes", "Plantillas básicas", "Marca de agua"]
            },
            {
                "id": "pro",
                "nombre": "Pro",
                "precio": 19.99,
                "tokens": 50,
                "features": ["50 videos/mes", "Todas las plantillas", "Sin marca de agua", "Soporte prioritario"]
            },
            {
                "id": "business",
                "nombre": "Business",
                "precio": 49.99,
                "tokens": 200,
                "features": ["200 videos/mes", "Plantillas personalizadas", "API", "Multi-usuario"]
            }
        ],
        "config": {
            "groq_api_key": "",
            "groq_model": "llama-3.1-70b-versatile",
            "whisper_model": "base",
            "admin_password": "admin123"
        }
    }

def guardar_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ============ CLASE DE IA (GROQ) ============
class GroqAI:
    def __init__(self, api_key, model="llama-3.1-70b-versatile"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.groq.com/openai/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def listar_modelos(self):
        try:
            response = requests.get(f"{self.base_url}/models", headers=self.headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                if "data" in data:
                    return [m["id"] for m in data["data"]]
                else:
                    return list(data.keys())
            else:
                return {"error": f"Error {response.status_code}: {response.text}"}
        except Exception as e:
            return {"error": str(e)}

    def _limpiar_json(self, texto):
        # Eliminar bloques de código markdown
        texto = re.sub(r'```json\s*|\s*```', '', texto)
        # Eliminar etiquetas <think> ... </think>
        texto = re.sub(r'<think>.*?</think>', '', texto, flags=re.DOTALL)
        # Buscar el primer { o [ y extraer JSON completo
        start = min([i for i in (texto.find('{'), texto.find('[')) if i != -1] or [-1])
        if start != -1:
            stack = []
            for i, ch in enumerate(texto[start:], start):
                if ch in '{[':
                    stack.append(ch)
                elif ch in '}]':
                    if stack and ((ch == '}' and stack[-1] == '{') or (ch == ']' and stack[-1] == '[')):
                        stack.pop()
                        if not stack:
                            return texto[start:i+1]
        return texto

    def generar_plantilla(self, tipo_video, descripcion, estilo):
        prompt = f"""
        Crea una plantilla de edición de video en JSON.
        
        Tipo de video: {tipo_video}
        Descripción: {descripcion}
        Estilo deseado: {estilo}
        
        La plantilla debe incluir:
        - Estructura (intro, desarrollo, cierre)
        - Colores de marca (hexadecimal)
        - Tipografía sugerida
        - Estilo de transiciones
        - Configuración de subtítulos
        - Timing sugerido para cada sección
        
        Responde SOLO con JSON válido.
        """
        resultado = self._consultar(prompt)
        resultado_limpio = self._limpiar_json(resultado)
        try:
            return json.loads(resultado_limpio)
        except:
            return {"error": "No se pudo parsear JSON", "raw": resultado}

    def analizar_video(self, transcripcion, tipo_contenido):
        prompt = f"""
        Analiza este video de tipo "{tipo_contenido}" y genera:
        1. Título atractivo para YouTube (máx 60 caracteres)
        2. Descripción optimizada para SEO (100-150 palabras)
        3. 10 hashtags relevantes
        4. 3 momentos más importantes (con timestamps aproximados)
        5. Resumen de 2 oraciones
        6. Sugerencia de miniaturas (3 ideas)
        
        Transcripción:
        {transcripcion[:4000]}
        
        Responde SOLO con JSON válido.
        """
        resultado = self._consultar(prompt)
        resultado_limpio = self._limpiar_json(resultado)
        try:
            return json.loads(resultado_limpio)
        except:
            return {"error": "No se pudo parsear JSON", "raw": resultado}

    def _consultar(self, prompt):
        try:
            data = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 2000
            }
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=data,
                timeout=30
            )
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            else:
                return {"error": f"Error {response.status_code}: {response.text}"}
        except Exception as e:
            return {"error": str(e)}

# ============ AUTENTICACIÓN ============
def crear_hash(password):
    return hashlib.sha256(password.encode()).hexdigest()

def registrar_usuario(nombre, email, password, plan="gratis"):
    db = cargar_db()
    for u in db["usuarios"]:
        if u["email"] == email:
            return None, "El email ya está registrado"
    usuario = {
        "id": str(uuid.uuid4()),
        "nombre": nombre,
        "email": email,
        "password_hash": crear_hash(password),
        "plan": plan,
        "tokens": db["membresias"][0]["tokens"] if plan == "gratis" else 50,
        "proyectos": [],
        "fecha_registro": datetime.now().isoformat(),
        "activo": True
    }
    db["usuarios"].append(usuario)
    guardar_db(db)
    return usuario, "Usuario creado exitosamente"

def login_usuario(email, password):
    db = cargar_db()
    hash_password = crear_hash(password)
    for u in db["usuarios"]:
        if u["email"] == email and u["password_hash"] == hash_password:
            return u, "Login exitoso"
    return None, "Credenciales incorrectas"

def verificar_tokens(usuario_id):
    db = cargar_db()
    for u in db["usuarios"]:
        if u["id"] == usuario_id:
            return u["tokens"] > 0
    return False

def usar_token(usuario_id):
    db = cargar_db()
    for u in db["usuarios"]:
        if u["id"] == usuario_id:
            u["tokens"] -= 1
            guardar_db(db)
            return True
    return False

# ============ PROCESAMIENTO DE VIDEO ============
def procesar_video_automatico(ruta_video, plantilla_json, config):
    try:
        import whisper
        modelo = whisper.load_model(config.get("whisper_model", "base"))
        transcripcion = modelo.transcribe(ruta_video, fp16=False)

        from pydub import AudioSegment
        from pydub.silence import detect_silence
        audio = AudioSegment.from_file(ruta_video)
        silencios = detect_silence(audio, min_silence_len=1000, silence_thresh=-45)

        temp_dir = OUTPUTS / str(uuid.uuid4())
        temp_dir.mkdir(parents=True, exist_ok=True)

        segmentos = []
        inicio = 0.0
        for i, (s_inicio, s_fin) in enumerate(silencios):
            s_inicio = s_inicio / 1000
            s_fin = s_fin / 1000
            if s_inicio - inicio >= 2:
                seg = temp_dir / f"seg_{i:03d}.mp4"
                subprocess.run([
                    "ffmpeg", "-ss", str(inicio), "-i", ruta_video,
                    "-t", str(s_inicio - inicio), "-c:v", "libx264",
                    "-c:a", "aac", "-preset", "fast", "-crf", "23",
                    str(seg)
                ], capture_output=True)
                segmentos.append(str(seg))
            inicio = s_fin

        seg = temp_dir / "seg_final.mp4"
        subprocess.run([
            "ffmpeg", "-ss", str(inicio), "-i", ruta_video,
            "-c:v", "libx264", "-c:a", "aac", "-preset", "fast",
            "-crf", "23", str(seg)
        ], capture_output=True)
        segmentos.append(str(seg))

        lista = temp_dir / "lista.txt"
        with open(lista, 'w') as f:
            for s in segmentos:
                f.write(f"file '{s}'\n")

        video_final = OUTPUTS / f"final_{uuid.uuid4()}.mp4"
        subprocess.run([
            "ffmpeg", "-f", "concat", "-safe", "0", "-i", str(lista),
            "-c", "copy", str(video_final)
        ], capture_output=True)

        srt_content = ""
        for i, segm in enumerate(transcripcion["segments"], 1):
            def f_t(s):
                h = int(s // 3600)
                m = int((s % 3600) // 60)
                sec = int(s % 60)
                ms = int((s - int(s)) * 1000)
                return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"
            srt_content += f"{i}\n{f_t(segm['start'])} --> {f_t(segm['end'])}\n{segm['text'].strip()}\n\n"

        ruta_srt = OUTPUTS / f"subtitulos_{uuid.uuid4()}.srt"
        with open(ruta_srt, 'w', encoding='utf-8') as f:
            f.write(srt_content)

        return {
            "video_final": str(video_final),
            "subtitulos": str(ruta_srt),
            "transcripcion": transcripcion["text"],
            "segmentos": len(segmentos)
        }
    except Exception as e:
        return {"error": str(e)}

# ============ INTERFAZ PRINCIPAL ============
def main():
    if 'usuario' not in st.session_state:
        st.session_state.usuario = None
    if 'vista' not in st.session_state:
        st.session_state.vista = "login"

    with st.sidebar:
        st.title("🎬 VideoAI Studio")
        st.markdown("---")
        if st.session_state.usuario:
            st.write(f"👤 **{st.session_state.usuario['nombre']}**")
            st.write(f"📧 {st.session_state.usuario['email']}")
            st.write(f"🎯 Plan: {st.session_state.usuario['plan'].upper()}")
            st.write(f"🪙 Tokens: {st.session_state.usuario['tokens']}")
            st.markdown("---")
            vista = st.radio(
                "Navegación",
                ["📤 Procesar Video", "🎨 Plantillas", "📊 Mis Proyectos", "⚙️ Configuración"]
            )
            if st.button("🚪 Cerrar Sesión"):
                st.session_state.usuario = None
                st.rerun()
        else:
            st.info("Inicia sesión para continuar")

    if not st.session_state.usuario:
        tab1, tab2 = st.tabs(["🔐 Iniciar Sesión", "📝 Registrarse"])
        with tab1:
            st.header("Iniciar Sesión")
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            if st.button("Entrar", type="primary"):
                usuario, msg = login_usuario(email, password)
                if usuario:
                    st.session_state.usuario = usuario
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
        with tab2:
            st.header("Crear Cuenta")
            nombre = st.text_input("Nombre", key="reg_nombre")
            email = st.text_input("Email", key="reg_email")
            password = st.text_input("Password", type="password", key="reg_password")
            password2 = st.text_input("Confirmar Password", type="password", key="reg_password2")
            if st.button("Registrarse", type="primary"):
                if password != password2:
                    st.error("Las contraseñas no coinciden")
                else:
                    usuario, msg = registrar_usuario(nombre, email, password)
                    if usuario:
                        st.session_state.usuario = usuario
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
    else:
        if vista == "📤 Procesar Video":
            st.title("📤 Procesar Video Automáticamente")
            if st.session_state.usuario['tokens'] <= 0:
                st.warning("⚠️ No tienes tokens disponibles. Actualiza tu plan.")
            else:
                video_subido = st.file_uploader("Sube tu video", type=['mp4','mov','avi','mkv'])
                if video_subido:
                    st.video(video_subido)
                    col1, col2, col3 = st.columns(3)
                    col1.info(f"**Archivo:** {video_subido.name}")
                    col2.info(f"**Tamaño:** {video_subido.size/1024/1024:.1f} MB")
                    col3.info(f"**Tokens:** 1")
                    db = cargar_db()
                    plantillas = db["plantillas"]
                    if plantillas:
                        plantilla_sel = st.selectbox("Elige una plantilla", [p["nombre"] for p in plantillas])
                    else:
                        st.info("No hay plantillas disponibles. El admin debe crearlas.")
                        plantilla_sel = None
                    with st.expander("⚙️ Configuración avanzada"):
                        eliminar_silencios = st.checkbox("Eliminar silencios", True)
                        generar_subs = st.checkbox("Generar subtítulos", True)
                        calidad = st.selectbox("Calidad", ["720p", "1080p"])
                    if st.button("🚀 Procesar Video", type="primary"):
                        if verificar_tokens(st.session_state.usuario['id']):
                            with st.spinner("Procesando video... Esto puede tardar unos minutos"):
                                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                ruta_video = UPLOADS / f"{timestamp}_{video_subido.name}"
                                with open(ruta_video, 'wb') as f:
                                    f.write(video_subido.getbuffer())
                                config = {"whisper_model": "base"}
                                resultado = procesar_video_automatico(str(ruta_video), plantilla_sel, config)
                                if "error" not in resultado:
                                    usar_token(st.session_state.usuario['id'])
                                    db = cargar_db()
                                    for u in db["usuarios"]:
                                        if u["id"] == st.session_state.usuario['id']:
                                            u["proyectos"].append({
                                                "fecha": timestamp,
                                                "video_original": video_subido.name,
                                                "video_final": resultado["video_final"],
                                                "subtitulos": resultado["subtitulos"],
                                                "transcripcion": resultado["transcripcion"][:500]
                                            })
                                            u["tokens"] -= 1
                                            st.session_state.usuario = u
                                    guardar_db(db)
                                    st.success("✅ Video procesado exitosamente!")
                                    st.video(resultado["video_final"])
                                    col1, col2 = st.columns(2)
                                    with col1:
                                        with open(resultado["video_final"], 'rb') as f:
                                            st.download_button("⬇️ Descargar Video", f, file_name=f"editado_{timestamp}.mp4", mime="video/mp4")
                                    with col2:
                                        if generar_subs:
                                            with open(resultado["subtitulos"], 'rb') as f:
                                                st.download_button("⬇️ Descargar Subtítulos", f, file_name=f"subtitulos_{timestamp}.srt")
                                    with st.expander("📝 Ver transcripción"):
                                        st.write(resultado["transcripcion"])
                                else:
                                    st.error(f"Error: {resultado['error']}")
                        else:
                            st.error("No tienes tokens suficientes")
        elif vista == "🎨 Plantillas":
            st.title("🎨 Plantillas Disponibles")
            db = cargar_db()
            plantillas = db["plantillas"]
            if not plantillas:
                st.info("El administrador aún no ha creado plantillas.")
            else:
                for p in plantillas:
                    with st.expander(f"📁 {p['nombre']}"):
                        st.json(p)
        elif vista == "📊 Mis Proyectos":
            st.title("📊 Mis Proyectos")
            if st.session_state.usuario['proyectos']:
                for proyecto in reversed(st.session_state.usuario['proyectos']):
                    with st.expander(f"Proyecto {proyecto['fecha']}"):
                        st.write(f"**Original:** {proyecto['video_original']}")
                        if "transcripcion" in proyecto:
                            st.write(f"**Transcripción:** {proyecto['transcripcion']}...")
            else:
                st.info("Aún no tienes proyectos procesados.")
        elif vista == "⚙️ Configuración":
            st.title("⚙️ Configuración")
            st.json(st.session_state.usuario)

# ============ ADMINISTRADOR ============
def panel_admin():
    st.sidebar.title("🔑 Panel Admin")
    db = cargar_db()

    with st.sidebar.expander("🔑 API de Groq"):
        api_key = st.text_input("API Key", value=db["config"].get("groq_api_key", ""), type="password")
        if st.button("Guardar API"):
            db["config"]["groq_api_key"] = api_key
            guardar_db(db)
            st.success("API guardada")

        if st.button("Listar modelos disponibles"):
            if db["config"]["groq_api_key"]:
                groq = GroqAI(db["config"]["groq_api_key"])
                modelos = groq.listar_modelos()
                if isinstance(modelos, list):
                    st.session_state["modelos_groq"] = modelos
                    st.success(f"Se encontraron {len(modelos)} modelos")
                else:
                    st.error(modelos.get("error", "Error al listar modelos"))
            else:
                st.warning("Primero guarda tu API key")

        if "modelos_groq" in st.session_state:
            st.write("Modelos disponibles:")
            modelo_seleccionado = st.selectbox("Selecciona modelo", st.session_state["modelos_groq"])
            if st.button("Guardar modelo"):
                db["config"]["groq_model"] = modelo_seleccionado
                guardar_db(db)
                st.success("Modelo guardado")

    admin_vista = st.sidebar.radio(
        "Admin",
        ["📊 Dashboard", "👥 Usuarios", "🎨 Plantillas", "💰 Membresías"]
    )

    if admin_vista == "📊 Dashboard":
        st.title("📊 Dashboard")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Usuarios", len(db["usuarios"]))
        col2.metric("Plantillas", len(db["plantillas"]))
        col3.metric("Membresías", len(db["membresias"]))
        col4.metric("Tokens activos", sum(u["tokens"] for u in db["usuarios"]))

    elif admin_vista == "👥 Usuarios":
        st.title("👥 Gestión de Usuarios")
        for u in db["usuarios"]:
            with st.expander(f"👤 {u['nombre']} - {u['email']}"):
                st.write(f"**Plan:** {u['plan']}")
                st.write(f"**Tokens:** {u['tokens']}")
                st.write(f"**Proyectos:** {len(u['proyectos'])}")
                st.write(f"**Registro:** {u['fecha_registro']}")
                col1, col2 = st.columns(2)
                with col1:
                    tokens_add = st.number_input(f"Tokens a añadir {u['id']}", 1, 100, 10, key=f"tokens_{u['id']}")
                    if st.button(f"➕ Añadir tokens {u['id']}"):
                        u["tokens"] += tokens_add
                        guardar_db(db)
                        st.rerun()
                with col2:
                    if st.button(f"🔒 Suspender {u['id']}"):
                        u["activo"] = False
                        guardar_db(db)
                        st.rerun()

    elif admin_vista == "🎨 Plantillas":
        st.title("🎨 Gestión de Plantillas")

        def eliminar_plantilla(plantilla_id):
            db = cargar_db()
            db["plantillas"] = [p for p in db["plantillas"] if p["id"] != plantilla_id]
            guardar_db(db)
            st.success("Plantilla eliminada")
            st.rerun()

        with st.expander("➕ Nueva Plantilla"):
            nombre = st.text_input("Nombre de plantilla")
            tipo = st.selectbox("Tipo", ["Tutorial", "Vlog", "Shorts", "Corporativo"])
            descripcion = st.text_area("Descripción")
            estilo = st.selectbox("Estilo", ["Moderno", "Minimalista", "Corporativo", "Creativo"])
            if st.button("Generar Plantilla con IA"):
                if db["config"]["groq_api_key"]:
                    groq = GroqAI(db["config"]["groq_api_key"], model=db["config"].get("groq_model", "llama-3.1-70b-versatile"))
                    resultado = groq.generar_plantilla(tipo, descripcion, estilo)
                    if "error" in resultado:
                        st.error(f"Error al generar: {resultado['error']}")
                    else:
                        plantilla = {
                            "id": str(uuid.uuid4()),
                            "nombre": nombre,
                            "tipo": tipo,
                            "descripcion": descripcion,
                            "json": resultado,
                            "fecha_creacion": datetime.now().isoformat()
                        }
                        db["plantillas"].append(plantilla)
                        guardar_db(db)
                        st.success("Plantilla creada!")
                        st.rerun()
                else:
                    st.error("Configura primero la API de Groq")

        st.subheader("Plantillas existentes")
        if not db["plantillas"]:
            st.info("No hay plantillas aún.")
        for p in db["plantillas"]:
            with st.expander(f"📁 {p['nombre']}"):
                st.write(f"**Tipo:** {p['tipo']}")
                st.write(f"**Descripción:** {p['descripcion']}")
                st.json(p['json'])
                if st.button(f"🗑️ Eliminar {p['nombre']}", key=f"eliminar_{p['id']}"):
                    eliminar_plantilla(p["id"])

if __name__ == "__main__":
    if 'admin_mode' not in st.session_state:
        st.session_state.admin_mode = False

    with st.sidebar:
        if not st.session_state.admin_mode:
            with st.expander("🔐 Modo Admin"):
                admin_pass = st.text_input("Contraseña admin", type="password")
                if st.button("Ingresar como Admin"):
                    db = cargar_db()
                    if admin_pass == db["config"].get("admin_password", "admin123"):
                        st.session_state.admin_mode = True
                        st.success("Modo admin activado")
                        st.rerun()
                    else:
                        st.error("Contraseña incorrecta")
        else:
            if st.button("Salir de modo admin"):
                st.session_state.admin_mode = False
                st.rerun()

    if st.session_state.admin_mode:
        panel_admin()
    else:
        main()
