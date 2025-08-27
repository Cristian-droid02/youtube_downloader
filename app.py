from flask import Flask, render_template_string, request, send_file, jsonify
import yt_dlp
import os
import re

app = Flask(__name__)

DOWNLOAD_FOLDER = "downloads"
COOKIES_FILE = "cookies.txt"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

if os.path.exists(COOKIES_FILE):
    print("✓ Cookies encontradas. Se usará autenticación.")
else:
    print("⚠️ No se encontró archivo de cookies. Continuando sin autenticación.")

progress_data = {"status": "idle", "progress": 0, "filename": None}

def progress_hook(d):
    if d['status'] == 'downloading':
        downloaded = d.get("downloaded_bytes", 0)
        total = d.get("total_bytes", 0) or d.get("total_bytes_estimate", 1)
        progress_data["status"] = "downloading"
        progress_data["progress"] = int(downloaded / total * 100) if total > 0 else 0
    elif d['status'] == 'finished':
        progress_data["status"] = "finished"
        progress_data["progress"] = 100
        progress_data["filename"] = d["filename"]

def get_ydl_opts_base():
    """Obtener opciones base que incluyen cookies si están disponibles"""
    base_opts = {
        "quiet": True,
        "no_warnings": False,
    }
    
    if os.path.exists(COOKIES_FILE):
        base_opts["cookiefile"] = COOKIES_FILE
    
    return base_opts

def get_available_resolutions(info):
    """Obtener las resoluciones disponibles para el video"""
    resolutions = {}
    
    for f in info.get("formats", []):
        try:
            # Solo considerar formatos con video
            if f.get('vcodec') == 'none':
                continue
                
            # Obtener la resolución
            height = f.get('height')
            if not height:
                continue
                
            # Determinar el tipo de formato (video solo o combinado)
            has_audio = f.get('acodec') != 'none'
            format_type = "combinado" if has_audio else "video"
            
            # Calcular tamaño aproximado
            filesize = f.get('filesize', 0) or f.get('filesize_approx', 0)
            filesize_mb = f"{filesize / (1024*1024):.1f} MB" if filesize else "N/A"
            
            # Obtener FPS si está disponible
            fps = f.get('fps', 0)
            fps_text = f" {fps}fps" if fps > 30 else ""
            
            # Crear clave única para esta resolución y tipo
            resolution_key = f"{height}p{'_combinado' if has_audio else ''}"
            
            # Solo mantener el mejor formato para cada resolución
            if resolution_key not in resolutions:
                resolutions[resolution_key] = {
                    "height": height,
                    "format_id": f["format_id"],
                    "ext": f.get("ext", "mp4"),
                    "has_audio": has_audio,
                    "filesize": filesize_mb,
                    "fps": fps,
                    "quality": f.get('quality', 0),
                }
            else:
                # Si encontramos un formato mejor para esta resolución, actualizar
                current = resolutions[resolution_key]
                if f.get('quality', 0) > current['quality']:
                    resolutions[resolution_key] = {
                        "height": height,
                        "format_id": f["format_id"],
                        "ext": f.get("ext", "mp4"),
                        "has_audio": has_audio,
                        "filesize": filesize_mb,
                        "fps": fps,
                        "quality": f.get('quality', 0),
                    }
                    
        except (KeyError, TypeError):
            continue
    
    # Convertir a lista y ordenar por resolución
    resolutions_list = []
    for key, res in resolutions.items():
        # Crear texto descriptivo
        fps_text = f" {res['fps']}fps" if res['fps'] > 30 else ""
        audio_text = " (con audio)" if res['has_audio'] else " (solo video)"
        
        resolutions_list.append({
            "format_id": res["format_id"],
            "resolution": f"{res['height']}p{fps_text}{audio_text}",
            "height": res["height"],
            "filesize": res["filesize"],
            "has_audio": res["has_audio"],
            "ext": res["ext"]
        })
    
    # Ordenar por resolución (mayor primero)
    resolutions_list.sort(key=lambda x: x["height"], reverse=True)
    
    return resolutions_list

def get_audio_formats(info):
    """Obtener formatos de audio disponibles"""
    audio_formats = []
    
    for f in info.get("formats", []):
        try:
            # Solo considerar formatos de audio
            if f.get('vcodec') != 'none' or f.get('acodec') == 'none':
                continue
                
            # Obtener bitrate
            abr = f.get('abr', 0)
            bitrate = f"{abr}kbps" if abr else "N/A"
            
            # Calcular tamaño aproximado
            filesize = f.get('filesize', 0) or f.get('filesize_approx', 0)
            filesize_mb = f"{filesize / (1024*1024):.1f} MB" if filesize else "N/A"
            
            audio_formats.append({
                "format_id": f["format_id"],
                "resolution": f"Solo audio ({bitrate})",
                "ext": f.get("ext", "m4a"),
                "filesize": filesize_mb,
                "quality": f.get('quality', 0),
            })
                    
        except (KeyError, TypeError):
            continue
    
    # Ordenar por calidad (mayor primero)
    audio_formats.sort(key=lambda x: x["quality"], reverse=True)
    
    return audio_formats

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url")
        if url:
            # Validar URL de YouTube
            if not re.match(r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/', url):
                return render_template_string(error_template, error="URL de YouTube no válida")
            
            ydl_opts = get_ydl_opts_base()
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    
                    # Obtener resoluciones disponibles
                    resolutions = get_available_resolutions(info)
                    audio_formats = get_audio_formats(info)
                    
                    if not resolutions and not audio_formats:
                        return render_template_string(error_template, error="No se encontraron formatos disponibles para este video")
                    
                    # Información del video para mostrar
                    video_info = {
                        "title": info.get('title', 'Video sin título'),
                        "duration": info.get('duration', 0),
                        "thumbnail": info.get('thumbnail', ''),
                        "view_count": info.get('view_count', 0)
                    }
                    
                return render_template_string(
                    quality_template, 
                    url=url, 
                    resolutions=resolutions,
                    audio_formats=audio_formats,
                    video_info=video_info
                )
            except Exception as e:
                error_message = f"Error al obtener información: {str(e)}"
                return render_template_string(error_template, error=error_message)

    return render_template_string(index_template)

@app.route("/download", methods=["POST"])
def download():
    url = request.form.get("url")
    format_id = request.form.get("format_id")

    if not url:
        return render_template_string(error_template, error="URL no proporcionada")

    progress_data.update({"status": "starting", "progress": 0, "filename": None})

    # Obtener opciones base con cookies
    ydl_opts = get_ydl_opts_base()
    ydl_opts["outtmpl"] = os.path.join(DOWNLOAD_FOLDER, "%(title)s.%(ext)s")
    ydl_opts["progress_hooks"] = [progress_hook]

    # Configurar formato seleccionado
    ydl_opts["format"] = format_id
    
    # Para formatos de video, asegurar que se fusionen correctamente
    if format_id != "mp3" and not format_id.startswith("bestaudio"):
        ydl_opts["merge_output_format"] = "mp4"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

            # Asegurar extensión correcta
            if format_id == "mp3" or format_id.startswith("bestaudio"):
                filename = os.path.splitext(filename)[0] + ".mp3"
            elif not filename.endswith('.mp4'):
                filename = os.path.splitext(filename)[0] + ".mp4"

        return send_file(filename, as_attachment=True)
    
    except Exception as e:
        error_message = f"Error al descargar: {str(e)}"
        return render_template_string(error_template, error=error_message)

@app.route("/progress")
def progress():
    return jsonify(progress_data)

# Templates actualizados
error_template = """
<!DOCTYPE html>
<html>
<head>
  <title>Error</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 text-white flex items-center justify-center min-h-screen">
  <div class="bg-gray-800 p-8 rounded-2xl shadow-xl w-full max-w-lg text-center">
    <h2 class="text-2xl font-bold mb-4 text-red-500">Error</h2>
    <p class="mb-4">{{ error }}</p>
    <a href="/" class="bg-blue-500 hover:bg-blue-600 px-4 py-2 rounded-lg shadow-md">
      Volver al inicio
    </a>
  </div>
</body>
</html>
"""

quality_template = """
<!DOCTYPE html>
<html>
<head>
  <title>Elige calidad</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    async function checkProgress() {
      const res = await fetch('/progress');
      const data = await res.json();
      document.getElementById("status").innerText = data.status;
      document.getElementById("bar").value = data.progress;
      document.getElementById("percent").innerText = data.progress + "%";
      if(data.status !== "finished"){
        setTimeout(checkProgress, 1000);
      }
    }
    function startProgress(){
      document.getElementById("progress-container").classList.remove("hidden");
      setTimeout(checkProgress, 1000);
    }
  </script>
</head>
<body class="bg-gray-900 text-white flex items-center justify-center min-h-screen">
  <div class="bg-gray-800 p-8 rounded-2xl shadow-xl w-full max-w-2xl">
    {% if video_info.thumbnail %}
    <div class="text-center mb-6">
      <img src="{{ video_info.thumbnail }}" alt="Miniatura" class="w-64 h-36 object-cover rounded-lg mx-auto mb-3">
      <h3 class="text-lg font-semibold">{{ video_info.title|truncate(50) }}</h3>
      <p class="text-sm text-gray-400">
        {% if video_info.duration %}
          Duración: {{ (video_info.duration // 60)|int }}:{{ '%02d' % (video_info.duration % 60) }}
        {% endif %}
        {% if video_info.view_count %}
          • {{ "{:,}".format(video_info.view_count) }} vistas
        {% endif %}
      </p>
    </div>
    {% endif %}
    
    <h2 class="text-2xl font-bold mb-6 text-center">Selecciona la calidad de descarga</h2>
    
    <form method="POST" action="/download" onsubmit="startProgress()">
      <input type="hidden" name="url" value="{{ url }}">
      
      <div class="mb-6">
        <label class="block text-sm font-medium mb-3 text-blue-400">🎥 Formatos de video disponibles:</label>
        <div class="space-y-2">
          {% for res in resolutions %}
          <div class="flex items-center p-3 bg-gray-700 rounded-lg hover:bg-gray-600 transition">
            <input type="radio" name="format_id" value="{{ res.format_id }}" id="format-{{ loop.index }}" 
                   class="mr-3 h-4 w-4 text-blue-500" {{ 'checked' if loop.first }}>
            <label for="format-{{ loop.index }}" class="flex-1 cursor-pointer">
              <span class="font-medium">{{ res.resolution }}</span>
              <span class="text-sm text-gray-400 ml-2">({{ res.ext|upper }}, {{ res.filesize }})</span>
            </label>
          </div>
          {% endfor %}
        </div>
      </div>
      
      {% if audio_formats %}
      <div class="mb-6">
        <label class="block text-sm font-medium mb-3 text-green-400">🔊 Formatos de audio:</label>
        <div class="space-y-2">
          {% for audio in audio_formats %}
          <div class="flex items-center p-3 bg-gray-700 rounded-lg hover:bg-gray-600 transition">
            <input type="radio" name="format_id" value="{{ audio.format_id }}" id="audio-{{ loop.index }}" 
                   class="mr-3 h-4 w-4 text-green-500">
            <label for="audio-{{ loop.index }}" class="flex-1 cursor-pointer">
              <span class="font-medium">{{ audio.resolution }}</span>
              <span class="text-sm text-gray-400 ml-2">({{ audio.ext|upper }}, {{ audio.filesize }})</span>
            </label>
          </div>
          {% endfor %}
        </div>
      </div>
      {% endif %}
      
      <button type="submit" class="w-full bg-green-600 hover:bg-green-700 px-4 py-3 rounded-lg shadow-md font-semibold text-lg">
        ⬇️ Descargar
      </button>
    </form>
    
    <div id="progress-container" class="hidden mt-6 p-4 bg-gray-700 rounded-lg">
      <p id="status" class="mb-2 text-center">Preparando descarga...</p>
      <progress id="bar" value="0" max="100" class="w-full h-3 rounded-full"></progress>
      <p id="percent" class="mt-2 text-center text-sm">0%</p>
    </div>
  </div>
</body>
</html>
"""

index_template = """
<!DOCTYPE html>
<html>
<head>
  <title>Descargar videos de YouTube</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 text-white flex items-center justify-center min-h-screen">
  <div class="bg-gray-800 p-8 rounded-2xl shadow-xl w-full max-w-lg text-center">
    <h2 class="text-2xl font-bold mb-4">🎬 Descargar Video de YouTube</h2>
    <form method="POST">
      <input type="text" name="url" placeholder="https://www.youtube.com/watch?v=..." 
        class="w-full p-3 rounded-lg bg-gray-700 text-white border border-gray-600 placeholder-gray-400" 
        required>
      <br><br>
      <button type="submit" class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg shadow-md font-semibold">
        ➡️ Continuar
      </button>
    </form>
    {% if cookies_available %}
    <p class="mt-4 text-green-400">✓ Autenticación con cookies disponible</p>
    {% else %}
    <p class="mt-4 text-yellow-400">⚠️ Descargando sin autenticación (puede haber limitaciones)</p>
    {% endif %}
  </div>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
