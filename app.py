import streamlit as st
import os
import subprocess
import json
import uuid
import requests
import re
from pathlib import Path
from datetime import datetime
import hashlib

# ============ CONFIGURACIÓN INICIAL ============
st.set_page_config(
    page_title="VideoAI Studio Pro",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============ SISTEMA DE ARCHIVOS ============
BASE_PATH = Path("/tmp/videoai-studio")
UPLOADS = BASE_PATH / "uploads"
OUTPUTS = BASE_PATH / "outputs"
DATABASE = BASE_PATH / "database"
PLANTILLAS = BASE_PATH / "plantillas"
IMAGENES_GENERADAS = BASE_PATH / "imagenes"

for carpeta in [BASE_PATH, UPLOADS, OUTPUTS, DATABASE, PLANTILLAS, IMAGENES_GENERADAS]:
    carpeta.mkdir(parents=True, exist_ok=True)

DB_FILE = DATABASE / "sistema.json"

# ============ BASE DE DATOS ============
def cargar_db():
    if DB_FILE.exists():
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "usuarios": [],
        "plantillas": [],
        "membresias": [
            {"id": "gratis", "nombre": "Gratis", "precio": 0, "tokens": 3,
             "features": ["3 videos/mes", "Plantillas básicas", "Marca de agua"]},
            {"id": "pro", "nombre": "Pro", "precio": 19.99, "tokens": 50,
             "features": ["50 videos/mes", "Todas las plantillas", "Sin marca de agua", "Soporte prioritario"]},
            {"id": "business", "nombre": "Business", "precio": 49.99, "tokens": 200,
             "features": ["200 videos/mes", "Plantillas personalizadas", "API", "Multi-usuario"]}
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

# ============ IA GROQ ============
class GroqAI:
    def __init__(self, api_key, model="llama-3.1-70b-versatile"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.groq.com/openai/v1"
        self.headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    def listar_modelos(self):
        try:
            r = requests.get(f"{self.base_url}/models", headers=self.headers, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if "data" in data:
                    return [m["id"] for m in data["data"]]
                return list(data.keys())
            return {"error": f"Error {r.status_code}: {r.text}"}
        except Exception as e:
            return {"error": str(e)}

    def _limpiar_json(self, texto):
        texto = re.sub(r'```json\s*|\s*```', '', texto)
        texto = re.sub(r'<think>.*?</think>', '', texto, flags=re.DOTALL)
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

    def _consultar(self, prompt):
        try:
            data = {"model": self.model, "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7, "max_tokens": 3000}
            r = requests.post(f"{self.base_url}/chat/completions", headers=self.headers, json=data, timeout=30)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            return {"error": f"Error {r.status_code}: {r.text}"}
        except Exception as e:
            return {"error": str(e)}

    def generar_guion(self, texto_objetivo, tipo_contenido, duracion_objetivo, material_descripcion):
        prompt = f"""
        Eres un director de producción audiovisual profesional.
        Crea un guion técnico completo para un video de {duracion_objetivo} minutos, tipo {tipo_contenido}.
        
        Objetivo/mensaje: {texto_objetivo}
        Material disponible: {material_descripcion}
        
        Devuelve JSON con:
        {{
            "titulo": "...",
            "introduccion": "texto de introducción",
            "escenas": [
                {{"numero": 1, "descripcion": "...", "texto_en_pantalla": "...", "imagen_sugerida": "", "duracion_seg": 5}}
            ],
            "cta_final": "..."
        }}
        Responde SOLO con JSON válido.
        """
        resultado = self._consultar(prompt)
        limpio = self._limpiar_json(resultado)
        try:
            return json.loads(limpio)
        except:
            return {"error": "No se pudo parsear JSON", "raw": resultado}

    def generar_plantilla(self, tipo_video, descripcion, estilo):
        prompt = f"""
        Crea una plantilla de edición de video en JSON.
        Tipo: {tipo_video}, Descripción: {descripcion}, Estilo: {estilo}
        Incluye: estructura, colores hex, tipografía, transiciones, subtítulos, timing.
        Responde SOLO con JSON válido.
        """
        resultado = self._consultar(prompt)
        limpio = self._limpiar_json(resultado)
        try:
            return json.loads(limpio)
        except:
            return {"error": "No se pudo parsear JSON", "raw": resultado}

# ============ AUTENTICACIÓN ============
def crear_hash(p):
    return hashlib.sha256(p.encode()).hexdigest()

def registrar_usuario(nombre, email, password, plan="gratis"):
    db = cargar_db()
    for u in db["usuarios"]:
        if u["email"] == email:
            return None, "El email ya está registrado"
    usuario = {"id": str(uuid.uuid4()), "nombre": nombre, "email": email,
               "password_hash": crear_hash(password), "plan": plan,
               "tokens": db["membresias"][0]["tokens"] if plan == "gratis" else 50,
               "proyectos": [], "fecha_registro": datetime.now().isoformat(), "activo": True}
    db["usuarios"].append(usuario)
    guardar_db(db)
    return usuario, "Usuario creado exitosamente"

def login_usuario(email, password):
    db = cargar_db()
    hash_p = crear_hash(password)
    for u in db["usuarios"]:
        if u["email"] == email and u["password_hash"] == hash_p:
            return u, "Login exitoso"
    return None, "Credenciales incorrectas"

def verificar_tokens(uid):
    db = cargar_db()
    for u in db["usuarios"]:
        if u["id"] == uid:
            return u["tokens"] > 0
    return False

def usar_token(uid):
    db = cargar_db()
    for u in db["usuarios"]:
        if u["id"] == uid:
            u["tokens"] -= 1
            guardar_db(db)
            return True
    return False

# ============ DETECCIÓN DE SILENCIOS CON FFMPEG ============
def detectar_silencios_ffmpeg(ruta_video, umbral_db=-45, duracion_min=1.0):
    comando = ["ffmpeg", "-i", ruta_video, "-af", f"silencedetect=noise={umbral_db}dB:d={duracion_min}", "-f", "null", "-"]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    salida = resultado.stderr
    silencios = []
    inicio = None
    for linea in salida.splitlines():
        if "silence_start" in linea:
            try:
                inicio = float(linea.split("silence_start:")[1].strip())
            except:
                pass
        elif "silence_end" in linea and inicio is not None:
            try:
                fin = float(linea.split("silence_end:")[1].split("|")[0].strip())
                silencios.append((inicio, fin))
                inicio = None
            except:
                pass
    return silencios

# ============ FUNCIÓN PARA CREAR INTRO ============
def crear_intro(titulo, plantilla, duracion=4, resolucion="1920x1080"):
    color = plantilla.get("color_primario", "#3B82F6")
    color_texto = "white"
    # Crear un clip de color de fondo con texto
    intro_path = OUTPUTS / f"intro_{uuid.uuid4()}.mp4"
    # Usar drawtext para poner el título centrado
    # Crear un video de color sólido con FFmpeg
    cmd = [
        "ffmpeg",
        "-f", "lavfi",
        "-i", f"color=c={color}:s={resolucion}:d={duracion}",
        "-vf", f"drawtext=text='{titulo}':fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:fontsize=60:fontcolor={color_texto}:x=(w-text_w)/2:y=(h-text_h)/2",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-ar", "44100", "-ac", "2",
        str(intro_path)
    ]
    subprocess.run(cmd, capture_output=True)
    return str(intro_path)

# ============ FUNCIÓN PARA CREAR DIAPOSITIVA DE IMAGEN ============
def crear_diapositiva_imagen(ruta_imagen, duracion=3, resolucion="1920x1080"):
    slide_path = OUTPUTS / f"slide_{uuid.uuid4()}.mp4"
    cmd = [
        "ffmpeg", "-loop", "1", "-i", ruta_imagen,
        "-t", str(duracion),
        "-vf", f"scale={resolucion}:force_original_aspect_ratio=decrease,pad={resolucion}:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-ar", "44100", "-ac", "2",
        str(slide_path)
    ]
    subprocess.run(cmd, capture_output=True)
    return str(slide_path)

# ============ PROCESAMIENTO PRINCIPAL ============
def procesar_video_pro(ruta_video, guion, plantilla, config, archivos_extra):
    """
    Procesa video(s) según guion y plantilla, usando todo el material disponible.
    """
    try:
        import whisper
        modelo = whisper.load_model(config.get("whisper_model", "base"))
        transcripcion = modelo.transcribe(ruta_video, fp16=False)

        # Guardar videos extra
        videos_extra = archivos_extra.get("videos", [])
        imagenes = archivos_extra.get("imagenes", [])
        audio_musica = archivos_extra.get("audio", None)

        # Detectar silencios en video principal
        silencios = detectar_silencios_ffmpeg(ruta_video)

        # Cortar segmentos útiles del video principal
        temp_dir = OUTPUTS / str(uuid.uuid4())
        temp_dir.mkdir(parents=True, exist_ok=True)
        segmentos_principales = []
        inicio = 0.0
        for i, (s_ini, s_fin) in enumerate(silencios):
            if s_ini - inicio >= 2:
                seg = temp_dir / f"seg_{i:03d}.mp4"
                subprocess.run(["ffmpeg", "-ss", str(inicio), "-i", ruta_video,
                                "-t", str(s_ini - inicio), "-c:v", "libx264",
                                "-c:a", "aac", "-preset", "fast", "-crf", "23", str(seg)], capture_output=True)
                segmentos_principales.append(str(seg))
            inicio = s_fin
        seg = temp_dir / "seg_final.mp4"
        subprocess.run(["ffmpeg", "-ss", str(inicio), "-i", ruta_video,
                        "-c:v", "libx264", "-c:a", "aac", "-preset", "fast",
                        "-crf", "23", str(seg)], capture_output=True)
        segmentos_principales.append(str(seg))

        # Crear lista de clips finales
        clips_finales = []

        # 1. Intro con título
        if guion and "titulo" in guion:
            intro = crear_intro(guion["titulo"], plantilla, duracion=4)
            clips_finales.append(intro)

        # 2. Insertar imágenes/diapositivas según guion
        if imagenes:
            for idx, img_path in enumerate(imagenes):
                slide = crear_diapositiva_imagen(img_path, duracion=3)
                clips_finales.append(slide)

        # 3. Agregar segmentos del video principal
        clips_finales.extend(segmentos_principales)

        # 4. Agregar videos extra al final (o intercalarlos)
        if videos_extra:
            for v_path in videos_extra:
                clips_finales.append(v_path)

        # Aplicar transiciones entre clips usando xfade
        if len(clips_finales) > 1:
            # Construir comando con xfade
            inputs = []
            for clip in clips_finales:
                inputs.extend(["-i", clip])
            filter_parts = []
            prev_label = "[0:v]"
            for i in range(1, len(clips_finales)):
                out_label = f"[v{i}]"
                # Duración de transición 0.5s, offset se maneja automáticamente con xfade
                filter_parts.append(f"{prev_label}[{i}:v]xfade=transition=fade:duration=0.5:offset=2{out_label}")
                prev_label = out_label
            # Para el audio, usamos el audio del primer clip (simplificado)
            filter_complex = ";".join(filter_parts)
            # Mapear video final y audio del primer clip
            cmd = ["ffmpeg"]
            for s in clips_finales:
                cmd.extend(["-i", s])
            cmd.extend([
                "-filter_complex", filter_complex,
                "-map", prev_label,
                "-map", "0:a",  # audio del primer clip (mejorable)
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "192k",
                str(temp_dir / "video_transiciones.mp4")
            ])
            subprocess.run(cmd, capture_output=True)
            video_base = str(temp_dir / "video_transiciones.mp4")
        else:
            # Solo un clip
            video_base = clips_finales[0]

        # Mezclar audio de música si se proporciona
        if audio_musica:
            video_con_musica = temp_dir / "video_con_musica.mp4"
            cmd = [
                "ffmpeg", "-i", video_base, "-i", audio_musica,
                "-filter_complex", "[1:a]volume=0.2[musica];[0:a][musica]amix=inputs=2:duration=first[aout]",
                "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                str(video_con_musica)
            ]
            subprocess.run(cmd, capture_output=True)
            video_base = str(video_con_musica)

        # Generar subtítulos quemados
        if transcripcion and "segments" in transcripcion:
            srt_content = ""
            for i, segm in enumerate(transcripcion["segments"], 1):
                def f_t(s):
                    h = int(s // 3600); m = int((s % 3600) // 60); sec = int(s % 60); ms = int((s - int(s)) * 1000)
                    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"
                srt_content += f"{i}\n{f_t(segm['start'])} --> {f_t(segm['end'])}\n{segm['text'].strip()}\n\n"
            ruta_srt = OUTPUTS / f"subtitulos_{uuid.uuid4()}.srt"
            with open(ruta_srt, 'w', encoding='utf-8') as f:
                f.write(srt_content)

            # Quemar subtítulos usando drawtext con estilo de plantilla
            color_sub = plantilla.get("color_secundario", "white")
            # Construir filtro de subtítulos aproximado (simplificado)
            video_con_sub = temp_dir / "video_con_sub.mp4"
            # Usar el archivo SRT con ffmpeg subtitles
            cmd = [
                "ffmpeg", "-i", video_base,
                "-vf", f"subtitles={ruta_srt}:force_style='FontName=DejaVu Sans,FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1'",
                "-c:a", "copy",
                str(video_con_sub)
            ]
            subprocess.run(cmd, capture_output=True)
            video_base = str(video_con_sub)

        # Exportar versiones para plataformas
        formatos = {}
        # YouTube 16:9
        yt = OUTPUTS / f"youtube_{uuid.uuid4()}.mp4"
        subprocess.run(["ffmpeg", "-i", video_base, "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2", "-c:a", "copy", str(yt)], capture_output=True)
        formatos["youtube"] = str(yt)
        # TikTok 9:16
        tk = OUTPUTS / f"tiktok_{uuid.uuid4()}.mp4"
        subprocess.run(["ffmpeg", "-i", video_base, "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2", "-c:a", "copy", str(tk)], capture_output=True)
        formatos["tiktok"] = str(tk)
        # Instagram 1:1
        ig = OUTPUTS / f"instagram_{uuid.uuid4()}.mp4"
        subprocess.run(["ffmpeg", "-i", video_base, "-vf", "scale=1080:1080:force_original_aspect_ratio=decrease,pad=1080:1080:(ow-iw)/2:(oh-ih)/2", "-c:a", "copy", str(ig)], capture_output=True)
        formatos["instagram"] = str(ig)

        return {
            "video_final": video_base,
            "formatos": formatos,
            "subtitulos": str(ruta_srt),
            "transcripcion": transcripcion["text"],
            "segmentos": len(segmentos_principales)
        }
    except Exception as e:
        return {"error": str(e)}

# ============ PLANTILLAS PROFESIONALES MEJORADAS ============
PLANTILLAS_PREDEF = [
    {"id": "moderno", "nombre": "Moderno", "color_primario": "#3B82F6", "color_secundario": "#1E293B",
     "fuente": "Inter", "estilo": "minimalista", "transicion": "fade", "descripcion": "Limpio, tecnológico, ideal para tutoriales y tech.",
     "fondo_intro": "#3B82F6", "color_texto": "#FFFFFF", "color_sub": "#1E293B"},
    {"id": "corporativo", "nombre": "Corporativo", "color_primario": "#0F172A", "color_secundario": "#F59E0B",
     "fuente": "Montserrat", "estilo": "elegante", "transicion": "slide", "descripcion": "Serio, profesional, para empresas.",
     "fondo_intro": "#0F172A", "color_texto": "#FFFFFF", "color_sub": "#F59E0B"},
    {"id": "publicitario", "nombre": "Publicitario", "color_primario": "#EF4444", "color_secundario": "#FACC15",
     "fuente": "Poppins", "estilo": "impactante", "transicion": "zoom", "descripcion": "Atrevido, llamativo, para anuncios.",
     "fondo_intro": "#EF4444", "color_texto": "#FFFFFF", "color_sub": "#FACC15"},
    {"id": "institucional", "nombre": "Institucional", "color_primario": "#0369A1", "color_secundario": "#B45309",
     "fuente": "Lato", "estilo": "formal", "transicion": "fade", "descripcion": "Sobrio, informativo, para organizaciones.",
     "fondo_intro": "#0369A1", "color_texto": "#FFFFFF", "color_sub": "#B45309"}
]

# ============ INTERFAZ PRINCIPAL (CON CSS MODERNO) ============
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        color: white;
    }
    .stButton>button {
        background-color: #3B82F6;
        color: white;
        border-radius: 10px;
        padding: 10px 20px;
        font-weight: bold;
        border: none;
        transition: all 0.3s;
    }
    .stButton>button:hover {
        background-color: #2563EB;
        transform: translateY(-2px);
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .stFileUploader>div>div>div>div {
        background-color: #1e293b;
        border: 2px dashed #3B82F6;
        border-radius: 15px;
    }
    .plantilla-card {
        background-color: #1e293b;
        border-radius: 15px;
        padding: 20px;
        margin: 10px 0;
        border: 1px solid #334155;
        transition: all 0.3s;
    }
    .plantilla-card:hover {
        border-color: #3B82F6;
        box-shadow: 0 8px 16px rgba(0,0,0,0.5);
        transform: translateY(-5px);
    }
    h1, h2, h3, h4, h5, h6 {
        color: #F8FAFC;
    }
    .stMarkdown p, .stMarkdown li {
        color: #CBD5E1;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #1e293b;
        border-radius: 10px 10px 0 0;
        padding: 10px 20px;
        color: #CBD5E1;
    }
    .stTabs [aria-selected="true"] {
        background-color: #3B82F6 !important;
        color: white !important;
    }
    .metric-card {
        background-color: #1e293b;
        border-radius: 10px;
        padding: 15px;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

def main():
    if 'usuario' not in st.session_state:
        st.session_state.usuario = None
    if 'vista' not in st.session_state:
        st.session_state.vista = "login"

    with st.sidebar:
        st.title("🎬 VideoAI Studio Pro")
        st.markdown("---")
        if st.session_state.usuario:
            st.write(f"👤 **{st.session_state.usuario['nombre']}**")
            st.write(f"📧 {st.session_state.usuario['email']}")
            st.write(f"🎯 Plan: {st.session_state.usuario['plan'].upper()}")
            st.write(f"🪙 Tokens: {st.session_state.usuario['tokens']}")
            st.markdown("---")
            vista = st.radio("Navegación", ["📤 Procesar Video", "🎨 Plantillas", "📊 Mis Proyectos", "⚙️ Configuración"])
            if st.button("🚪 Cerrar Sesión"):
                st.session_state.usuario = None
                st.rerun()
        else:
            st.info("Inicia sesión para continuar")

    if not st.session_state.usuario:
        tab1, tab2 = st.tabs(["🔐 Iniciar Sesión", "📝 Registrarse"])
        with tab1:
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            if st.button("Entrar", type="primary"):
                usuario, msg = login_usuario(email, password)
                if usuario:
                    st.session_state.usuario = usuario
                    st.rerun()
                else:
                    st.error(msg)
        with tab2:
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
                        st.rerun()
                    else:
                        st.error(msg)
    else:
        if vista == "📤 Procesar Video":
            st.title("📤 Producción Automática de Video")
            if st.session_state.usuario['tokens'] <= 0:
                st.warning("⚠️ No tienes tokens disponibles. Actualiza tu plan.")
            else:
                # Paso 1: Subir material
                st.subheader("1. Sube tu material")
                video_principal = st.file_uploader("Video principal", type=['mp4','mov','avi','mkv'], key="video_main")
                videos_extra = st.file_uploader("Videos adicionales (B-roll)", type=['mp4','mov','avi','mkv'], accept_multiple_files=True, key="videos_extra")
                imagenes = st.file_uploader("Imágenes de apoyo", type=['png','jpg','jpeg','webp'], accept_multiple_files=True, key="imgs_extra")
                audio_musica = st.file_uploader("Música o audio", type=['mp3','wav'], key="audio_extra")

                # Paso 2: Información del proyecto
                st.subheader("2. Describe tu proyecto")
                texto_objetivo = st.text_area("¿Qué mensaje quieres transmitir? (objetivo, marca, público)", height=150, placeholder="Ej: Quiero promocionar mi curso online de marketing digital...")
                tipo_contenido = st.selectbox("Tipo de contenido", ["Publicitario", "Institucional", "Educativo", "Entretenimiento", "Tutorial", "Vlog"])
                duracion_objetivo = st.slider("Duración aproximada (minutos)", 1, 15, 3)

                # Paso 3: Plantilla con vista previa
                st.subheader("3. Elige una plantilla profesional")
                cols = st.columns(2)
                for i, plant in enumerate(PLANTILLAS_PREDEF):
                    with cols[i % 2]:
                        st.markdown(f"""
                        <div class="plantilla-card">
                            <h3 style="color:{plant['color_primario']};">{plant['nombre']}</h3>
                            <p>Color primario: {plant['color_primario']} | Secundario: {plant['color_secundario']}</p>
                            <p>Fuente: {plant['fuente']} | Estilo: {plant['estilo']}</p>
                            <p>{plant['descripcion']}</p>
                            <div style="background-color:{plant['color_primario']}; padding:10px; border-radius:5px; color:{plant['color_texto']}; font-family:{plant['fuente']};">
                                Vista previa de texto
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        if st.button(f"Usar {plant['nombre']}", key=f"plant_{plant['id']}"):
                            st.session_state.plantilla_elegida = plant
                            st.success(f"Plantilla {plant['nombre']} seleccionada")
                if 'plantilla_elegida' not in st.session_state:
                    st.session_state.plantilla_elegida = PLANTILLAS_PREDEF[0]

                # Paso 4: Formatos
                st.subheader("4. Formatos de publicación")
                formatos_salida = st.multiselect("Selecciona formatos", ["YouTube (16:9)", "TikTok (9:16)", "Instagram (1:1)"], default=["YouTube (16:9)"])

                # Paso 5: Generar guion
                if st.button("🧠 Generar Guion con IA", type="primary"):
                    if not texto_objetivo:
                        st.warning("Escribe una descripción del proyecto")
                    else:
                        with st.spinner("Generando guion profesional..."):
                            db = cargar_db()
                            groq = GroqAI(db["config"]["groq_api_key"], model=db["config"].get("groq_model", "llama-3.1-70b-versatile"))
                            material_desc = f"Videos: {video_principal.name if video_principal else 'no'}, Videos extra: {len(videos_extra) if videos_extra else 0}, Imágenes: {len(imagenes) if imagenes else 0}, Audio: {'sí' if audio_musica else 'no'}"
                            guion = groq.generar_guion(texto_objetivo, tipo_contenido, duracion_objetivo, material_desc)
                            if "error" in guion:
                                st.error(f"Error al generar guion: {guion['error']}")
                            else:
                                st.session_state.guion = guion
                                st.success("Guion generado")
                                st.json(guion)

                # Mostrar guion editable
                if 'guion' in st.session_state:
                    st.subheader("Guion generado (editable)")
                    guion_editable = st.text_area("Edita el guion si es necesario", value=json.dumps(st.session_state.guion, indent=2), height=200)
                    try:
                        st.session_state.guion = json.loads(guion_editable)
                    except:
                        st.warning("El JSON no es válido, se usará el último válido")

                # Procesar video
                if st.button("🚀 Producir Video", type="primary"):
                    if not video_principal:
                        st.error("Debes subir al menos un video principal")
                    else:
                        with st.spinner("Procesando video... esto puede tomar varios minutos"):
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            ruta_video = UPLOADS / f"{timestamp}_{video_principal.name}"
                            with open(ruta_video, 'wb') as f:
                                f.write(video_principal.getbuffer())

                            # Guardar archivos extra
                            archivos_extra = {"videos": [], "imagenes": [], "audio": None}
                            if videos_extra:
                                for v in videos_extra:
                                    ruta_v = UPLOADS / f"{timestamp}_{v.name}"
                                    with open(ruta_v, 'wb') as f:
                                        f.write(v.getbuffer())
                                    archivos_extra["videos"].append(str(ruta_v))
                            if imagenes:
                                for img in imagenes:
                                    ruta_img = UPLOADS / f"{timestamp}_{img.name}"
                                    with open(ruta_img, 'wb') as f:
                                        f.write(img.getbuffer())
                                    archivos_extra["imagenes"].append(str(ruta_img))
                            if audio_musica:
                                ruta_audio = UPLOADS / f"{timestamp}_{audio_musica.name}"
                                with open(ruta_audio, 'wb') as f:
                                    f.write(audio_musica.getbuffer())
                                archivos_extra["audio"] = str(ruta_audio)

                            config = {"whisper_model": "base"}
                            resultado = procesar_video_pro(str(ruta_video), st.session_state.guion if 'guion' in st.session_state else None,
                                                           st.session_state.plantilla_elegida, config, archivos_extra)
                            if "error" not in resultado:
                                usar_token(st.session_state.usuario['id'])
                                db = cargar_db()
                                for u in db["usuarios"]:
                                    if u["id"] == st.session_state.usuario['id']:
                                        u["proyectos"].append({
                                            "fecha": timestamp,
                                            "video_original": video_principal.name,
                                            "video_final": resultado["video_final"],
                                            "subtitulos": resultado["subtitulos"],
                                            "formatos": resultado["formatos"],
                                            "transcripcion": resultado["transcripcion"][:500]
                                        })
                                        u["tokens"] -= 1
                                        st.session_state.usuario = u
                                guardar_db(db)
                                st.success("✅ Video producido exitosamente!")
                                st.video(resultado["video_final"])
                                for nombre_fmt, ruta_fmt in resultado["formatos"].items():
                                    with open(ruta_fmt, 'rb') as f:
                                        st.download_button(f"⬇️ Descargar {nombre_fmt}", f, file_name=f"{nombre_fmt}_{timestamp}.mp4", mime="video/mp4")
                                with open(resultado["subtitulos"], 'rb') as f:
                                    st.download_button("⬇️ Descargar Subtítulos", f, file_name=f"subtitulos_{timestamp}.srt")
                                with st.expander("📝 Transcripción"):
                                    st.write(resultado["transcripcion"])
                            else:
                                st.error(f"Error: {resultado['error']}")
        elif vista == "🎨 Plantillas":
            st.title("🎨 Plantillas Profesionales")
            for plant in PLANTILLAS_PREDEF:
                st.markdown(f"### {plant['nombre']}")
                st.markdown(f"Color primario: {plant['color_primario']} | Secundario: {plant['color_secundario']}")
                st.markdown(f"Fuente: {plant['fuente']} | Estilo: {plant['estilo']} | Transición: {plant['transicion']}")
                st.markdown(plant['descripcion'])
                # Vista previa visual mejorada
                st.markdown(f"""
                <div style="background-color:{plant['fondo_intro']}; padding:20px; border-radius:15px; color:{plant['color_texto']}; margin:10px 0; box-shadow:0 4px 6px rgba(0,0,0,0.5);">
                    <h2 style="font-family:{plant['fuente']};">{plant['nombre']}</h2>
                    <p style="font-family:{plant['fuente']};">Ejemplo de cómo se vería el texto con esta plantilla.</p>
                    <span style="background-color:{plant['color_secundario']}; padding:5px 15px; border-radius:20px; color:white;">Botón de ejemplo</span>
                </div>
                """, unsafe_allow_html=True)
                st.markdown("---")
        elif vista == "📊 Mis Proyectos":
            st.title("📊 Mis Proyectos")
            if st.session_state.usuario['proyectos']:
                for proy in reversed(st.session_state.usuario['proyectos']):
                    with st.expander(f"Proyecto {proy['fecha']}"):
                        st.write(f"**Original:** {proy['video_original']}")
                        st.write(f"**Transcripción:** {proy.get('transcripcion', '')}...")
            else:
                st.info("No tienes proyectos aún.")
        elif vista == "⚙️ Configuración":
            st.title("⚙️ Configuración")
            st.json(st.session_state.usuario)
            st.markdown("---")
            st.subheader("💳 Actualizar Membresía")
            if st.button("Actualizar a Pro (19.99/mes)"):
                st.markdown("[Haz clic aquí para pagar con PayPal](https://www.paypal.com/paypalme/tu-cuenta)")

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
        if st.button("Listar modelos"):
            if db["config"]["groq_api_key"]:
                groq = GroqAI(db["config"]["groq_api_key"])
                modelos = groq.listar_modelos()
                if isinstance(modelos, list):
                    st.session_state.modelos_groq = modelos
                    st.success(f"{len(modelos)} modelos")
                else:
                    st.error(modelos.get("error"))
            else:
                st.warning("Guarda API key")
        if "modelos_groq" in st.session_state:
            mod = st.selectbox("Modelo", st.session_state.modelos_groq)
            if st.button("Guardar modelo"):
                db["config"]["groq_model"] = mod
                guardar_db(db)
                st.success("Modelo guardado")
    admin_vista = st.sidebar.radio("Admin", ["📊 Dashboard", "👥 Usuarios", "🎨 Plantillas", "💰 Membresías"])
    if admin_vista == "📊 Dashboard":
        st.title("📊 Dashboard")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Usuarios", len(db["usuarios"]))
        col2.metric("Plantillas", len(PLANTILLAS_PREDEF))
        col3.metric("Membresías", len(db["membresias"]))
        col4.metric("Tokens activos", sum(u["tokens"] for u in db["usuarios"]))
    elif admin_vista == "👥 Usuarios":
        st.title("👥 Usuarios")
        for u in db["usuarios"]:
            with st.expander(f"👤 {u['nombre']}"):
                st.write(f"Plan: {u['plan']}, Tokens: {u['tokens']}")
                col1, col2 = st.columns(2)
                with col1:
                    add = st.number_input(f"Tokens {u['id']}", 1, 100, 10, key=f"tok_{u['id']}")
                    if st.button(f"Añadir {u['id']}"):
                        u["tokens"] += add
                        guardar_db(db)
                        st.rerun()
                with col2:
                    if st.button(f"Suspender {u['id']}"):
                        u["activo"] = False
                        guardar_db(db)
                        st.rerun()
    elif admin_vista == "🎨 Plantillas":
        st.title("🎨 Plantillas del sistema")
        for p in PLANTILLAS_PREDEF:
            st.json(p)
    elif admin_vista == "💰 Membresías":
        st.title("💰 Planes")
        st.json(db["membresias"])

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
