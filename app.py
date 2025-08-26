from flask import Flask, render_template_string, request, send_file, jsonify
import yt_dlp
import os

app = Flask(__name__)

DOWNLOAD_FOLDER = "downloads"
COOKIES_FILE = "cookies.txt"  # Nombre del archivo de cookies
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Verificar si el archivo de cookies existe
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
    base_opts = {"quiet": True}
    
    # Agregar cookies si el archivo existe
    if os.path.exists(COOKIES_FILE):
        base_opts["cookiefile"] = COOKIES_FILE
        # También agregar estas opciones para evitar bloqueos
        base_opts["extractor_args"] = {
            "youtube": {
                "skip": ["dash", "hls"],
                "player_client": ["android", "web"]
            }
        }
        base_opts["http_headers"] = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-us,en;q=0.5",
            "Accept-Encoding": "gzip,deflate",
            "Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7",
            "Connection": "keep-alive"
        }
    
    return base_opts

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url")
        if url:
            ydl_opts = get_ydl_opts_base()
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    formats = [
                        {"format_id": f["format_id"], "ext": f["ext"], "resolution": f.get("resolution") or "audio"}
                        for f in info["formats"]
                        if f["ext"] in ["mp4", "m4a"]
                    ]
                return render_template_string(quality_template, url=url, formats=formats)
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
        ydl_opts.update({
            "format": format_id,
            "merge_output_format": "mp4"
        })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

            if format_id == "mp3":
                filename = os.path.splitext(filename)[0] + ".mp3"

        return send_file(filename, as_attachment=True)
    
    except Exception as e:
        error_message = f"Error al descargar: {str(e)}"
        return render_template_string(error_template, error=error_message)

@app.route("/progress")
def progress():
    return jsonify(progress_data)

# Template de error
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

# Los templates index_template y quality_template permanecen igual como en tu código original

index_template = """
<!DOCTYPE html>
<html>
<head>
  <title>Descargar videos de YouTube</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 text-white flex items-center justify-center min-h-screen">
  <div class="bg-gray-800 p-8 rounded-2xl shadow-xl w-full max-w-lg text-center">
    <h2 class="text-2xl font-bold mb-4">Descargar Video de YouTube</h2>
    <form method="POST">
      <input type="text" name="url" placeholder="Pega el enlace de YouTube aquí"
        class="w-full p-2 rounded-lg text-black" required>
      <br><br>
      <button type="submit" class="bg-blue-500 hover:bg-blue-600 px-4 py-2 rounded-lg shadow-md">
        Continuar
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
  <div class="bg-gray-800 p-8 rounded-2xl shadow-xl w-full max-w-lg text-center">
    <h2 class="text-2xl font-bold mb-4">Elige calidad (Video MP4 o Audio MP3)</h2>
    <form method="POST" action="/download" onsubmit="startProgress()">
      <input type="hidden" name="url" value="{{ url }}">
      <select name="format_id" required class="w-full p-2 rounded-lg text-black">
        {% for f in formats %}
          <option value="{{ f.format_id }}">
            {{ f.resolution }} ({{ f.ext }})
          </option>
        {% endfor %}
        <option value="mp3">Solo Audio (MP3 320kbps)</option>
      </select>
      <br><br>
      <button type="submit" class="bg-green-500 hover:bg-green-600 px-4 py-2 rounded-lg shadow-md">
        Descargar
      </button>
    </form>
    <div id="progress-container" class="hidden mt-6">
      <p id="status" class="mb-2">Preparando...</p>
      <progress id="bar" value="0" max="100" class="w-full"></progress>
      <p id="percent" class="mt-2">0%</p>
    </div>
  </div>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
