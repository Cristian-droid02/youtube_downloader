from flask import Flask, render_template_string, request, send_file, jsonify
import yt_dlp
import os

app = Flask(__name__)

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

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

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url")
        if url:
            ydl_opts = {"quiet": True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                formats = [
                    {"format_id": f["format_id"], "ext": f["ext"], "resolution": f.get("resolution") or "audio"}
                    for f in info["formats"]
                    if f["ext"] in ["mp4", "m4a"]
                ]
            return render_template_string(quality_template, url=url, formats=formats)

    return render_template_string(index_template)

@app.route("/download", methods=["POST"])
def download():
    url = request.form.get("url")
    format_id = request.form.get("format_id")

    progress_data.update({"status": "starting", "progress": 0, "filename": None})

    if format_id == "mp3":
        ydl_opts = {
    "format": "bestaudio/best",
    "postprocessors": [{
        "key": "FFmpegExtractAudio",
        "preferredcodec": "mp3",
        "preferredquality": "320",
    }],
    "cookiefile": "cookies.txt"  # <--- aquí
}
    else:
        ydl_opts = {
            "format": format_id,
            "outtmpl": os.path.join(DOWNLOAD_FOLDER, "%(title)s.%(ext)s"),
            "merge_output_format": "mp4",
            "progress_hooks": [progress_hook]
        }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)

        if format_id == "mp3":
            filename = os.path.splitext(filename)[0] + ".mp3"

    return send_file(filename, as_attachment=True)

@app.route("/progress")
def progress():
    return jsonify(progress_data)

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
        <option value="mp3">🎵 Solo Audio (MP3 320kbps)</option>
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
