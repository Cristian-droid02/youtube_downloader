from flask import Flask, render_template_string, request, send_file, jsonify
import yt_dlp
import os
import re
import tempfile

app = Flask(__name__)

# Usar directorio temporal para descargas
DOWNLOAD_FOLDER = tempfile.mkdtemp()
print(f"📁 Directorio de descargas: {DOWNLOAD_FOLDER}")

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

def get_available_video_formats(info):
    """Obtener solo formatos de video con audio"""
    video_formats = []
    
    for f in info.get("formats", []):
        try:
            # Solo considerar formatos con video Y audio
            if f.get('vcodec') == 'none' or f.get('acodec') == 'none':
                continue
                
            # Obtener la resolución
            height = f.get('height')
            if not height:
                continue
            
            # Calcular tamaño aproximado
            filesize = f.get('filesize', 0) or f.get('filesize_approx', 0)
            filesize_mb = f"{filesize / (1024*1024):.1f} MB" if filesize else "N/A"
            
            # Obtener FPS si está disponible
            fps = f.get('fps', 0)
            fps_text = f" {fps}fps" if fps > 30 else ""
            
            video_formats.append({
                "format_id": f["format_id"],
                "resolution": f"{height}p{fps_text}",
                "height": height,
                "filesize": filesize_mb,
                "ext": f.get("ext", "mp4"),
                "quality": f.get('quality', 0),
            })
                    
        except (KeyError, TypeError):
            continue
    
    # Ordenar por resolución (mayor primero)
    video_formats.sort(key=lambda x: x["height"], reverse=True)
    
    return video_formats

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
                    
                    # Obtener formatos de video disponibles (con audio)
                    video_formats = get_available_video_formats(info)
                    
                    if not video_formats:
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
                    video_formats=video_formats,
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
    
    # Usar directorio temporal para evitar problemas de permisos
    ydl_opts["outtmpl"] = os.path.join(DOWNLOAD_FOLDER, "%(title)s.%(ext)s")
    ydl_opts["progress_hooks"] = [progress_hook]

    # Configurar formato seleccionado
    if format_id == "mp3":
        # Para audio, convertir a MP3 de alta calidad (320kbps)
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "320"
        }]
    else:
        # Para video, usar el formato seleccionado
        ydl_opts["format"] = format_id
        ydl_opts["merge_output_format"] = "mp4"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

            # Asegurar extensión correcta
            if format_id == "mp3":
                filename = os.path.splitext(filename)[0] + ".mp3"
            elif not filename.endswith('.mp4'):
                filename = os.path.splitext(filename)[0] + ".mp4"

            # Verificar que el archivo existe antes de enviarlo
            if not os.path.exists(filename):
                # Buscar el archivo en el directorio de descargas
                download_dir = os.path.dirname(filename)
                actual_files = [f for f in os.listdir(download_dir) if os.path.isfile(os.path.join(download_dir, f))]
                
                if actual_files:
                    # Usar el primer archivo encontrado
                    filename = os.path.join(download_dir, actual_files[0])
                else:
                    raise FileNotFoundError(f"No se encontró ningún archivo descargado en {download_dir}")

        # Enviar el archivo como descarga
        response = send_file(
            filename, 
            as_attachment=True,
            download_name=os.path.basename(filename)
        )
        
        return response
    
    except Exception as e:
        error_message = f"Error al descargar: {str(e)}"
        return render_template_string(error_template, error=error_message)

@app.route("/progress")
def progress():
    return jsonify(progress_data)

# Templates actualizados
error_template = """
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Error - YouTube Downloader</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body {
      background: linear-gradient(135deg, #0f0f0f 0%, #1a1a1a 100%);
      min-height: 100vh;
    }
  </style>
</head>
<body class="text-gray-100 font-sans antialiased">
  <div class="min-h-screen flex items-center justify-center px-4 py-8">
    <div class="bg-gray-800 p-6 rounded-xl shadow-xl w-full max-w-md border border-gray-700">
      <div class="text-center">
        <div class="mx-auto w-16 h-16 flex items-center justify-center bg-gray-700 rounded-full mb-4">
          <svg class="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
          </svg>
        </div>
        <h2 class="text-xl font-semibold text-gray-200 mb-2">Error</h2>
        <p class="text-gray-400 mb-6">{{ error }}</p>
        <a href="/" class="inline-block bg-gray-700 hover:bg-gray-600 text-gray-200 px-4 py-2 rounded-lg transition-colors duration-200">
          Volver al inicio
        </a>
      </div>
    </div>
  </div>
</body>
</html>
"""

quality_template = """
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Seleccionar Calidad - YouTube Downloader</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body {
      background: linear-gradient(135deg, #0f0f0f 0%, #1a1a1a 100%);
      min-height: 100vh;
    }
    .quality-option {
      transition: all 0.2s ease;
    }
    .quality-option:hover {
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    }
    progress {
      border-radius: 4px;
      background: #2d2d2d;
    }
    progress::-webkit-progress-bar {
      background: #2d2d2d;
      border-radius: 4px;
    }
    progress::-webkit-progress-value {
      background: #4a4a4a;
      border-radius: 4px;
    }
  </style>
</head>
<body class="text-gray-100 font-sans antialiased">
  <div class="min-h-screen flex items-center justify-center px-4 py-8">
    <div class="bg-gray-800 p-6 rounded-xl shadow-xl w-full max-w-2xl border border-gray-700">
      {% if video_info.thumbnail %}
      <div class="text-center mb-6">
        <img src="{{ video_info.thumbnail }}" alt="Miniatura" class="w-full max-w-xs h-auto rounded-lg mx-auto mb-4 border border-gray-600">
        <h3 class="text-lg font-semibold text-gray-200 mb-2">{{ video_info.title|truncate(60) }}</h3>
        <div class="flex justify-center items-center space-x-4 text-sm text-gray-400">
          {% if video_info.duration %}
          <span>⏱️ {{ (video_info.duration // 60)|int }}:{{ '%02d' % (video_info.duration % 60) }}</span>
          {% endif %}
          {% if video_info.view_count %}
          <span>👁️ {{ "{:,}".format(video_info.view_count) }} vistas</span>
          {% endif %}
        </div>
      </div>
      {% endif %}
      
      <h2 class="text-xl font-semibold text-gray-200 mb-6 text-center border-b border-gray-700 pb-3">Seleccionar Formato de Descarga</h2>
      
      <form method="POST" action="/download" onsubmit="startProgress()">
        <input type="hidden" name="url" value="{{ url }}">
        
        <div class="mb-6">
          <h3 class="text-lg font-medium text-gray-300 mb-3 flex items-center">
            <svg class="w-5 h-5 mr-2 text-gray-400" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
              <path fill-rule="evenodd" d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm12 12H4l4-8 3 6 2-4 3 6z" clip-rule="evenodd"></path>
            </svg>
            Formatos de Video
          </h3>
          <div class="space-y-3">
            {% for video in video_formats %}
            <label class="quality-option block bg-gray-700 p-4 rounded-lg border border-gray-600 hover:bg-gray-650 cursor-pointer">
              <div class="flex items-center">
                <input type="radio" name="format_id" value="{{ video.format_id }}" 
                       class="h-4 w-4 text-gray-400 border-gray-500 focus:ring-gray-400" {{ 'checked' if loop.first }}>
                <div class="ml-3 flex-1">
                  <div class="flex justify-between items-center">
                    <span class="text-gray-200 font-medium">{{ video.resolution }}</span>
                    <span class="text-sm text-gray-400">{{ video.filesize }}</span>
                  </div>
                  <span class="text-xs text-gray-500 block mt-1">Formato: MP4 con audio</span>
                </div>
              </div>
            </label>
            {% endfor %}
          </div>
        </div>
        
        <div class="mb-6">
          <h3 class="text-lg font-medium text-gray-300 mb-3 flex items-center">
            <svg class="w-5 h-5 mr-2 text-gray-400" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
              <path fill-rule="evenodd" d="M9.383 3.076A1 1 0 0110 4v12a1 1 0 01-1.707.707L4.586 13H2a1 1 0 01-1-1V8a1 1 0 011-1h2.586l3.707-3.707a1 1 0 011.09-.217zM14.657 2.929a1 1 0 011.414 0A9.972 9.972 0 0119 10a9.972 9.972 0 01-2.929 7.071 1 1 0 01-1.414-1.414A7.971 7.971 0 0017 10c0-2.21-.894-4.208-2.343-5.657a1 1 0 010-1.414zm-2.829 2.828a1 1 0 011.415 0A5.983 5.983 0 0115 10a5.984 5.984 0 01-1.757 4.243 1 1 0 01-1.415-1.415A3.984 3.984 0 0013 10a3.983 3.983 0 00-1.172-2.828 1 1 0 010-1.415z" clip-rule="evenodd"></path>
            </svg>
            Formato de Audio
          </h3>
          <div class="space-y-3">
            <label class="quality-option block bg-gray-700 p-4 rounded-lg border border-gray-600 hover:bg-gray-650 cursor-pointer">
              <div class="flex items-center">
                <input type="radio" name="format_id" value="mp3" 
                       class="h-4 w-4 text-gray-400 border-gray-500 focus:ring-gray-400">
                <div class="ml-3 flex-1">
                  <div class="flex justify-between items-center">
                    <span class="text-gray-200 font-medium">MP3 - Alta Calidad (320kbps)</span>
                    <span class="text-sm text-gray-400">Tamaño variable</span>
                  </div>
                  <span class="text-xs text-gray-500 block mt-1">Audio extraído y convertido a MP3</span>
                </div>
              </div>
            </label>
          </div>
        </div>
        
        <button type="submit" class="w-full bg-gray-700 hover:bg-gray-600 text-gray-200 py-3 px-4 rounded-lg font-medium transition-colors duration-200 flex items-center justify-center">
          <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path>
          </svg>
          Descargar
        </button>
      </form>
      
      <div id="progress-container" class="hidden mt-6 p-4 bg-gray-700 rounded-lg border border-gray-600">
        <p id="status" class="text-gray-300 text-center mb-2">Preparando descarga...</p>
        <progress id="bar" value="0" max="100" class="w-full h-2"></progress>
        <p id="percent" class="text-gray-400 text-center text-sm mt-2">0%</p>
      </div>
    </div>
  </div>

  <script>
    async function checkProgress() {
      try {
        const res = await fetch('/progress');
        const data = await res.json();
        document.getElementById("status").innerText = data.status;
        document.getElementById("bar").value = data.progress;
        document.getElementById("percent").innerText = data.progress + "%";
        
        if(data.status !== "finished"){
          setTimeout(checkProgress, 1000);
        }
      } catch (error) {
        console.error('Error checking progress:', error);
      }
    }
    
    function startProgress(){
      document.getElementById("progress-container").classList.remove("hidden");
      setTimeout(checkProgress, 1000);
    }
  </script>
</body>
</html>
"""

index_template = """
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>YouTube Downloader</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body {
      background: linear-gradient(135deg, #0f0f0f 0%, #1a1a1a 100%);
      min-height: 100vh;
    }
    .card {
      backdrop-filter: blur(10px);
      background: rgba(26, 26, 26, 0.8);
      border: 1px solid rgba(255, 255, 255, 0.1);
    }
  </style>
</head>
<body class="text-gray-100 font-sans antialiased">
  <div class="min-h-screen flex items-center justify-center px-4 py-8">
    <div class="card rounded-2xl shadow-2xl p-6 md:p-8 w-full max-w-md">
      <div class="text-center mb-6">
        <div class="inline-flex items-center justify-center w-16 h-16 bg-gray-700 rounded-full mb-4">
          <svg class="w-8 h-8 text-gray-300" fill="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path d="M19.615 3.184c-3.604-.246-11.631-.245-15.23 0-3.897.266-4.356 2.62-4.385 8.816.029 6.185.484 8.549 4.385 8.816 3.6.245 11.626.246 15.23 0 3.897-.266 4.356-2.62 4.385-8.816-.029-6.185-.484-8.549-4.385-8.816zm-10.615 12.816v-8l8 3.993-8 4.007z"/>
          </svg>
        </div>
        <h1 class="text-2xl md:text-3xl font-bold text-gray-100 mb-2">YouTube Downloader</h1>
        <p class="text-gray-400 text-sm md:text-base">Descarga videos y audio de YouTube</p>
      </div>
      
      <form method="POST">
        <div class="mb-4">
          <label for="url" class="block text-sm font-medium text-gray-300 mb-2">URL de YouTube</label>
          <input type="url" name="url" placeholder="https://www.youtube.com/watch?v=..." 
                 class="w-full px-4 py-3 bg-gray-700 border border-gray-600 rounded-lg text-gray-100 placeholder-gray-400 focus:outline-none focus:border-gray-500 focus:ring-1 focus:ring-gray-500 transition-colors duration-200"
                 required>
        </div>
        
        <button type="submit" class="w-full bg-gray-700 hover:bg-gray-600 text-gray-200 py-3 px-4 rounded-lg font-medium transition-colors duration-200 flex items-center justify-center">
          <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
          </svg>
          Ver formatos disponibles
        </button>
      </form>
      
      <div class="mt-6 pt-6 border-t border-gray-700">
        <div class="text-center">
          {% if cookies_available %}
          <p class="text-green-400 text-sm flex items-center justify-center">
            <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>
            Autenticación disponible
          </p>
          {% else %}
          <p class="text-yellow-400 text-sm flex items-center justify-center">
            <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
            </svg>
            Descarga básica (puede haber limitaciones)
          </p>
          {% endif %}
        </div>
      </div>
    </div>
  </div>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
