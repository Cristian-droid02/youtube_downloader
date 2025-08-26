from flask import Flask, render_template_string, request, send_file, jsonify
import yt_dlp
import os

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
        total = d.get("total_bytes", 1)
        progress_data["status"] = "downloading"
        progress_data["progress"] = int(downloaded / total * 100)
    elif d['status'] == 'finished':
        progress_data["status"] = "finished"
        progress_data["progress"] = 100
        progress_data["filename"] = d["filename"]

def get_ydl_opts_base():
    """Obtener opciones base que incluyen cookies si están disponibles"""
    base_opts = {
        "quiet": True,
        "no_warnings": False,
        "verbose": True,  # Para debugging
    }
    
    if os.path.exists(COOKIES_FILE):
        base_opts["cookiefile"] = COOKIES_FILE
        base_opts["extractor_args"] = {
            "youtube": {
                "skip": ["dash", "hls"],
                "player_client": ["android", "web"]
            }
        }
        base_opts["http_headers"] = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    
    return base_opts

def get_best_format(formats):
    """Seleccionar el mejor formato disponible"""
    best_video = None
    best_audio = None
    
    for f in formats:
        # Buscar el mejor video (sin audio)
        if (f.get('vcodec') != 'none' and f.get('acodec') == 'none' and
            f.get('height') is not None and f.get('width') is not None):
            if (best_video is None or 
                (f.get('height', 0) > best_video.get('height', 0) and
                 f.get('fps', 0) >= best_video.get('fps', 0))):
                best_video = f
        
        # Buscar el mejor audio
        if (f.get('acodec') != 'none' and f.get('vcodec') == 'none' and
            f.get('audio_ext') != 'none'):
            if (best_audio is None or 
                (f.get('abr', 0) or 0) > (best_audio.get('abr', 0) or 0)):
                best_audio = f
    
    # Si encontramos ambos, crear formato combinado
    if best_video and best_audio:
        return f"{best_video['format_id']}+{best_audio['format_id']}"
    
    # Si no, usar el formato por defecto de mejor calidad
    return "bestvideo+bestaudio/best"

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url")
        if url:
            ydl_opts = get_ydl_opts_base()
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    
                    # Obtener todos los formatos disponibles
                    formats = []
                    for f in info["formats"]:
                        if (f.get('ext') in ['mp4', 'webm', 'm4a'] and 
                            not f.get('format_note', '').startswith('DASH')):  # Excluir formatos DASH
                            
                            resolution = ""
                            if f.get('vcodec') != 'none':
                                height = f.get('height', 0)
                                fps = f.get('fps', 0)
                                resolution = f"{height}p"
                                if fps and fps > 30:
                                    resolution += f"{int(fps)}"
                            else:
                                abr = f.get('abr', 0)
                                resolution = f"Audio {abr}kbps" if abr else "Audio"
                            
                            format_note = f.get('format_note', '')
                            if format_note and format_note != 'unknown':
                                resolution = f"{resolution} ({format_note})" if resolution else format_note
                            
                            formats.append({
                                "format_id": f["format_id"],
                                "ext": f["ext"],
                                "resolution": resolution or f.get('format', ''),
                                "vcodec": f.get('vcodec', 'none'),
                                "acodec": f.get('acodec', 'none'),
                                "filesize": f.get('filesize', 0),
                                "quality": f.get('quality', 0)
                            })
                    
                    # Ordenar formatos por calidad (mayor primero)
                    formats.sort(key=lambda x: (
                        x.get('height', 0) if x.get('height') else 0,
                        x.get('fps', 0) if x.get('fps') else 0,
                        x.get('abr', 0) if x.get('abr') else 0
                    ), reverse=True)
                    
                    # Obtener el mejor formato automáticamente
                    best_format = get_best_format(info["formats"])
                    
                return render_template_string(quality_template, url=url, formats=formats, best_format=best_format)
            except Exception as e:
                error_message = f"Error: {str(e)}"
                return render_template_string(error_template, error=error_message)

    return render_template_string(index_template)

@app.route("/download", methods=["POST"])
def download():
    url = request.form.get("url")
    format_id = request.form.get("format_id")

    progress_data.update({"status": "starting", "progress": 0, "filename": None})

    # Obtener opciones base con cookies
    ydl_opts = get_ydl_opts_base()
    ydl_opts["outtmpl"] = os.path.join(DOWNLOAD_FOLDER, "%(title)s.%(ext)s")
    ydl_opts["progress_hooks"] = [progress_hook]

    if format_id == "mp3":
        ydl_opts.update({
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "320"
                },
                {"key": "FFmpegMetadata"},
                {"key": "EmbedThumbnail"}  
            ],
            "writethumbnail": True,
        })
    else:
        # Para video, usar el formato seleccionado y fusionar
        ydl_opts.update({
            "format": format_id,
            "merge_output_format": "mp4",  # Siempre convertir a MP4
            "postprocessors": [
                {
                    "key": "FFmpegVideoConvertor",
                    "preferedformat": "mp4"  # Asegurar formato MP4
                }
            ]
        })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

            if format_id == "mp3":
                filename = os.path.splitext(filename)[0] + ".mp3"
            else:
                # Asegurar extensión .mp4
                base_name = os.path.splitext(filename)[0]
                filename = base_name + ".mp4"

        return send_file(filename, as_attachment=True)
    
    except Exception as e:
        error_message = f"Error al descargar: {str(e)}"
        return render_template_string(error_template, error=error_message)

@app.route("/progress")
def progress():
    return jsonify(progress_data)

# Template de error (igual que antes)
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

# Template de calidad mejorado
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
    
    // Seleccionar automáticamente el mejor formato
    window.onload = function() {
      document.querySelector('option[value="{{ best_format }}"]').selected = true;
    }
  </script>
</head>
<body class="bg-gray-900 text-white flex items-center justify-center min-h-screen">
  <div class="bg-gray-800 p-8 rounded-2xl shadow-xl w-full max-w-lg">
    <h2 class="text-2xl font-bold mb-4 text-center">Selecciona la calidad</h2>
    <p class="text-sm text-gray-400 mb-4 text-center">El formato recomendado está seleccionado automáticamente</p>
    
    <form method="POST" action="/download" onsubmit="startProgress()">
      <input type="hidden" name="url" value="{{ url }}">
      
      <div class="mb-4">
        <label class="block text-sm font-medium mb-2">Formatos de video:</label>
        <select name="format_id" required class="w-full p-3 rounded-lg bg-gray-700 text-white border border-gray-600">
          <optgroup label="Formatos combinados (recomendados)">
            <option value="best">Mejor calidad automática</option>
            <option value="bestvideo+bestaudio">Mejor video + mejor audio (combinado)</option>
          </optgroup>
          
          <optgroup label="Formatos específicos">
            {% for f in formats %}
              {% if f.vcodec != 'none' and f.acodec != 'none' %}
              <option value="{{ f.format_id }}">
                {{ f.resolution }} - {{ f.ext|upper }} (completo)
              </option>
              {% endif %}
            {% endfor %}
          </optgroup>
          
          <optgroup label="Solo audio">
            <option value="mp3">MP3 - Alta calidad (320kbps)</option>
            {% for f in formats %}
              {% if f.vcodec == 'none' and f.acodec != 'none' %}
              <option value="{{ f.format_id }}">
                {{ f.resolution }} - {{ f.ext|upper }} (solo audio)
              </option>
              {% endif %}
            {% endfor %}
          </optgroup>
        </select>
      </div>
      
      <button type="submit" class="w-full bg-green-600 hover:bg-green-700 px-4 py-3 rounded-lg shadow-md font-semibold">
        🎬 Descargar
      </button>
    </form>
    
    <div id="progress-container" class="hidden mt-6">
      <p id="status" class="mb-2 text-center">Preparando...</p>
      <progress id="bar" value="0" max="100" class="w-full h-3 rounded-full"></progress>
      <p id="percent" class="mt-2 text-center text-sm">0%</p>
    </div>
    
    <div class="mt-6 p-4 bg-gray-700 rounded-lg">
      <h3 class="font-semibold mb-2">💡 Recomendación:</h3>
      <p class="text-sm text-gray-300">Selecciona "Mejor video + mejor audio" para la máxima calidad. Los formatos se fusionarán automáticamente.</p>
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
