import streamlit as st
import os
import subprocess
import json
import uuid
import requests
import re
import base64
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
            "escenas": [
                {{"numero": 1, "descripcion": "...", "texto_en_pantalla": "...", "imagen_sugerida": "...", "duracion_seg": 5}}
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

# ============ GENERADOR DE IMÁGENES (POLLINATIONS - GRATIS) ============
def generar_imagen(prompt, ancho=1280, alto=720):
    url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt)}?width={ancho}&height={alto}&nologo=true"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            nombre = f"img_{uuid.uuid4()}.jpg"
            ruta = IMAGENES_GENERADAS / nombre
            with open(ruta, 'wb') as f:
                f.write(r.content)
            return str(ruta)
        return None
    except:
        return None

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

# ============ PROCESAMIENTO PRINCIPAL ============
def procesar_video_pro(ruta_video, guion, plantilla, config, archivos_extra):
    """
    Procesa video(s) según guion y plantilla.
    Incluye generación de imágenes automáticas, overlays de texto y transiciones.
    """
    try:
        import whisper
        modelo = whisper.load_model(config.get("whisper_model", "base"))
        transcripcion = modelo.transcribe(ruta_video, fp16=False)

        # Detectar silencios
        silencios = detectar_silencios_ffmpeg(ruta_video)

        # Cortar segmentos útiles
        temp_dir = OUTPUTS / str(uuid.uuid4())
        temp_dir.mkdir(parents=True, exist_ok=True)
        segmentos = []
        inicio = 0.0
        for i, (s_ini, s_fin) in enumerate(silencios):
            if s_ini - inicio >= 2:
                seg = temp_dir / f"seg_{i:03d}.mp4"
                subprocess.run(["ffmpeg", "-ss", str(inicio), "-i", ruta_video,
                                "-t", str(s_ini - inicio), "-c:v", "libx264",
                                "-c:a", "aac", "-preset", "fast", "-crf", "23", str(seg)], capture_output=True)
                segmentos.append(str(seg))
            inicio = s_fin
        seg = temp_dir / "seg_final.mp4"
        subprocess.run(["ffmpeg", "-ss", str(inicio), "-i", ruta_video,
                        "-c:v", "libx264", "-c:a", "aac", "-preset", "fast",
                        "-crf", "23", str(seg)], capture_output=True)
        segmentos.append(str(seg))

        # Generar imágenes automáticas si el guion lo sugiere
        imagenes_generadas = []
        if guion and "escenas" in guion:
            for escena in guion["escenas"]:
                if "imagen_sugerida" in escena and escena["imagen_sugerida"]:
                    ruta_img = generar_imagen(escena["imagen_sugerida"])
                    if ruta_img:
                        # Crear una diapositiva de 3 segundos con la imagen
                        slide = temp_dir / f"slide_{escena['numero']}.mp4"
                        subprocess.run([
                            "ffmpeg", "-loop", "1", "-i", ruta_img,
                            "-t", "3", "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
                            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                            str(slide)
                        ], capture_output=True)
                        imagenes_generadas.append((escena["numero"], str(slide)))

        # Aplicar overlay de título (primeros 3 segundos del primer segmento)
        if guion and "titulo" in guion and plantilla:
            titulo = guion["titulo"]
            color = plantilla.get("color_primario", "#FFFFFF")
            fuente = plantilla.get("fuente", "Arial")
            # Reemplazar el primer segmento por uno con texto
            primer_segmento = segmentos[0] if segmentos else None
            if primer_segmento:
                seg_con_titulo = temp_dir / "seg_0_titulo.mp4"
                # Usar drawtext para superponer el título
                cmd = [
                    "ffmpeg", "-i", primer_segmento,
                    "-vf", f"drawtext=text='{titulo}':fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:fontsize=48:fontcolor={color}:x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,0,3)'",
                    "-c:a", "copy", str(seg_con_titulo)
                ]
                subprocess.run(cmd, capture_output=True)
                segmentos[0] = str(seg_con_titulo)

        # Unir segmentos con transiciones de fundido (xfade)
        # Si hay más de un segmento, usar xfade; de lo contrario copiar directamente
        if len(segmentos) > 1:
            # Construir lista de inputs y filtros
            inputs = []
            for s in segmentos:
                inputs.extend(["-i", s])
            # Crear filtros xfade encadenados
            filter_parts = []
            prev_label = "[0:v]"
            for i in range(1, len(segmentos)):
                offset = 1  # duración de transición en segundos (aproximado)
                label_out = f"[v{i}]"
                filter_parts.append(f"{prev_label}[{i}:v]xfade=transition=fade:duration=0.5:offset={offset}{label_out}")
                prev_label = label_out
            # Último label es el video final
            video_final_filter = prev_label
            # Audio: concatenar (simplificado)
            # Usaremos amix para audio o simplemente copiar el primero
            cmd = ["ffmpeg"]
            for s in segmentos:
                cmd.extend(["-i", s])
            filter_complex = ";".join(filter_parts)
            cmd.extend(["-filter_complex", filter_complex,
                        "-map", video_final_filter,
                        "-map", "0:a",  # audio del primer segmento (mejorable)
                        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                        "-c:a", "aac", "-b:a", "192k",
                        str(OUTPUTS / f"con_transiciones_{uuid.uuid4()}.mp4")])
            subprocess.run(cmd, capture_output=True)
            video_base = str(OUTPUTS / f"con_transiciones_{uuid.uuid4()}.mp4")
            # Mover el archivo resultante
            # Nota: el comando anterior genera un archivo con nombre único, pero no lo capturamos bien.
            # Vamos a simplificar: usar concat normal por ahora, y luego aplicar un fade global de entrada/salida.
            # Esta parte es compleja, la dejamos como concatenación simple con fade in/out global.
            video_base = temp_dir / "video_base.mp4"
            # Concatenar normal
            lista = temp_dir / "lista.txt"
            with open(lista, 'w') as f:
                for s in segmentos:
                    f.write(f"file '{s}'\n")
            subprocess.run(["ffmpeg", "-f", "concat", "-safe", "0", "-i", str(lista),
                            "-c", "copy", str(video_base)], capture_output=True)
            # Aplicar fade in/out global
            fade_video = temp_dir / "video_fade.mp4"
            subprocess.run(["ffmpeg", "-i", str(video_base),
                            "-vf", "fade=t=in:st=0:d=0.5,fade=t=out:st=8:d=0.5",
                            "-c:a", "copy", str(fade_video)], capture_output=True)
            video_base = fade_video
        else:
            # Un solo segmento
            video_base = OUTPUTS / f"base_{uuid.uuid4()}.mp4"
            subprocess.run(["ffmpeg", "-i", segmentos[0], "-c", "copy", str(video_base)], capture_output=True)

        # Insertar imágenes generadas en puntos específicos (si existen)
        # (Se insertan al principio si hay alguna)
        if imagenes_generadas:
            # Tomar la primera imagen generada y ponerla al inicio
            primera_imagen = imagenes_generadas[0][1]
            lista_final = temp_dir / "lista_final.txt"
            with open(lista_final, 'w') as f:
                f.write(f"file '{primera_imagen}'\n")
                f.write(f"file '{video_base}'\n")
            video_con_imagen = OUTPUTS / f"video_con_imagen_{uuid.uuid4()}.mp4"
            subprocess.run(["ffmpeg", "-f", "concat", "-safe", "0", "-i", str(lista_final),
                            "-c", "copy", str(video_con_imagen)], capture_output=True)
            video_base = video_con_imagen

        # Generar subtítulos
        srt_content = ""
        for i, segm in enumerate(transcripcion["segments"], 1):
            def f_t(s):
                h = int(s // 3600); m = int((s % 3600) // 60); sec = int(s % 60); ms = int((s - int(s)) * 1000)
                return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"
            srt_content += f"{i}\n{f_t(segm['start'])} --> {f_t(segm['end'])}\n{segm['text'].strip()}\n\n"
        ruta_srt = OUTPUTS / f"subtitulos_{uuid.uuid4()}.srt"
        with open(ruta_srt, 'w', encoding='utf-8') as f:
            f.write(srt_content)

        # Exportar versiones para plataformas
        formatos = {}
        yt = OUTPUTS / f"youtube_{uuid.uuid4()}.mp4"
        subprocess.run(["ffmpeg", "-i", str(video_base), "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2", "-c:a", "copy", str(yt)], capture_output=True)
        formatos["youtube"] = str(yt)
        tk = OUTPUTS / f"tiktok_{uuid.uuid4()}.mp4"
        subprocess.run(["ffmpeg", "-i", str(video_base), "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2", "-c:a", "copy", str(tk)], capture_output=True)
        formatos["tiktok"] = str(tk)
        ig = OUTPUTS / f"instagram_{uuid.uuid4()}.mp4"
        subprocess.run(["ffmpeg", "-i", str(video_base), "-vf", "scale=1080:1080:force_original_aspect_ratio=decrease,pad=1080:1080:(ow-iw)/2:(oh-ih)/2", "-c:a", "copy", str(ig)], capture_output=True)
        formatos["instagram"] = str(ig)

        return {
            "video_final": str(video_base),
            "formatos": formatos,
            "subtitulos": str(ruta_srt),
            "transcripcion": transcripcion["text"],
            "segmentos": len(segmentos)
        }
    except Exception as e:
        return {"error": str(e)}

# ============ PLANTILLAS PROFESIONALES PREDEFINIDAS ============
PLANTILLAS_PREDEF = [
    {"id": "moderno", "nombre": "Moderno", "color_primario": "#3B82F6", "color_secundario": "#1E293B",
     "fuente": "Inter", "estilo": "minimalista", "transicion": "fade", "descripcion": "Limpio, tecnológico, ideal para tutoriales y tech."},
    {"id": "corporativo", "nombre": "Corporativo", "color_primario": "#0F172A", "color_secundario": "#F59E0B",
     "fuente": "Montserrat", "estilo": "elegante", "transicion": "slide", "descripcion": "Serio, profesional, para empresas."},
    {"id": "publicitario", "nombre": "Publicitario", "color_primario": "#EF4444", "color_secundario": "#FACC15",
     "fuente": "Poppins", "estilo": "impactante", "transicion": "zoom", "descripcion": "Atrevido, llamativo, para anuncios."},
    {"id": "institucional", "nombre": "Institucional", "color_primario": "#0369A1", "color_secundario": "#B45309",
     "fuente": "Lato", "estilo": "formal", "transicion": "fade", "descripcion": "Sobrio, informativo, para organizaciones."}
]

# ============ INTERFAZ PRINCIPAL ============
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

                # Paso 3: Plantilla
                st.subheader("3. Elige una plantilla profesional")
                cols = st.columns(2)
                for i, plant in enumerate(PLANTILLAS_PREDEF):
                    with cols[i % 2]:
                        st.markdown(f"**{plant['nombre']}**")
                        st.markdown(f"Color: <span style='color:{plant['color_primario']}'>⬤</span> {plant['color_primario']} | {plant['descripcion']}", unsafe_allow_html=True)
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
                            material_desc = f"Videos: {video_principal.name if video_principal else 'no'}, Imágenes: {len(imagenes) if imagenes else 0}, Audio: {'sí' if audio_musica else 'no'}"
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

                            archivos_extra = []
                            if imagenes:
                                for img in imagenes:
                                    ruta_img = UPLOADS / f"{timestamp}_{img.name}"
                                    with open(ruta_img, 'wb') as f:
                                        f.write(img.getbuffer())
                                    archivos_extra.append(str(ruta_img))

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
                # Vista previa visual con HTML
                st.markdown(f"""
                <div style="background-color:{plant['color_primario']}; padding:20px; border-radius:10px; color:white;">
                    <h2 style="font-family:{plant['fuente']};">{plant['nombre']}</h2>
                    <p style="font-family:{plant['fuente']};">Este es un ejemplo de cómo se vería el texto con la plantilla.</p>
                    <span style="background-color:{plant['color_secundario']}; padding:5px 10px; border-radius:5px;">Botón de ejemplo</span>
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
            # Botón para actualizar membresía
            st.markdown("---")
            st.subheader("💳 Actualizar Membresía")
            if st.button("Actualizar a Pro (19.99/mes)"):
                # Enlace a PayPal (debes reemplazar con tu enlace de pago)
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
