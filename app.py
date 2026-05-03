import os
import sqlite3
import uuid
import base64
import json as json_mod
import traceback
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify, render_template, send_from_directory

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "plantes.db"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Load .env file if present
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

GUIDE_SECTIONS = [
    ("lumiere", "Lumiere"),
    ("arrosage", "Arrosage"),
    ("temperature", "Temperature"),
    ("humidite", "Humidite"),
    ("substrat", "Substrat"),
    ("engrais", "Engrais"),
    ("rempotage", "Rempotage"),
    ("problemes", "Problemes courants"),
    ("symbolique", "Symbolique"),
]


# ── Database ────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS plants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                species TEXT DEFAULT '',
                care_guide TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plant_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                uploaded_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (plant_id) REFERENCES plants(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS waterings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plant_id INTEGER NOT NULL,
                watered_at TEXT DEFAULT (datetime('now','localtime')),
                notes TEXT DEFAULT '',
                FOREIGN KEY (plant_id) REFERENCES plants(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plant_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                answer TEXT DEFAULT '',
                photo_filename TEXT,
                asked_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (plant_id) REFERENCES plants(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS repottings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plant_id INTEGER NOT NULL,
                repotted_at TEXT DEFAULT (datetime('now','localtime')),
                notes TEXT DEFAULT '',
                FOREIGN KEY (plant_id) REFERENCES plants(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS checkups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plant_id INTEGER NOT NULL,
                photo_filename TEXT NOT NULL,
                status TEXT DEFAULT 'unknown',
                summary TEXT DEFAULT '',
                details TEXT DEFAULT '',
                comparison TEXT DEFAULT '',
                recommendations TEXT DEFAULT '',
                checked_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (plant_id) REFERENCES plants(id) ON DELETE CASCADE
            );
        """)


# ── Helpers ─────────────────────────────────────────────────────────────────

def row_to_dict(row):
    return dict(row) if row else None


def rows_to_list(rows):
    return [dict(r) for r in rows]


def save_upload(file_storage):
    ext = Path(file_storage.filename).suffix.lower() or ".jpg"
    name = f"{uuid.uuid4().hex}{ext}"
    file_storage.save(str(UPLOAD_DIR / name))
    return name


def save_base64_image(data_url):
    header, b64data = data_url.split(",", 1)
    ext = ".jpg"
    if "png" in header:
        ext = ".png"
    elif "webp" in header:
        ext = ".webp"
    name = f"{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / name).write_bytes(base64.b64decode(b64data))
    return name


def extract_b64_parts(data_url):
    header, b64data = data_url.split(",", 1)
    media_type = header.split(":")[1].split(";")[0]
    return media_type, b64data


def get_claude_client():
    import anthropic
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, base_url="https://api.anthropic.com")


GUIDE_PROMPT = """Tu es un expert botaniste. Identifie la plante sur la photo et fournis un guide d'entretien structure.
Reponds UNIQUEMENT avec un objet JSON valide (sans markdown, sans backticks), avec EXACTEMENT ces champs :
{
  "name": "Nom commun en francais",
  "species": "Nom scientifique latin",
  "guide": {
    "lumiere": "Description des besoins en lumiere (2-3 phrases max)",
    "arrosage": "Frequence et methode d'arrosage (2-3 phrases max)",
    "temperature": "Plage de temperature ideale (2-3 phrases max)",
    "humidite": "Besoins en humidite (2-3 phrases max)",
    "substrat": "Type de sol/substrat recommande (2-3 phrases max)",
    "engrais": "Type et frequence de fertilisation (2-3 phrases max)",
    "rempotage": "Quand et comment rempoter (2-3 phrases max)",
    "problemes": "Problemes courants et solutions (2-4 phrases max)",
    "symbolique": "Symbolique et signification de la plante dans differentes cultures, langage des fleurs, feng shui, etc. (2-4 phrases)"
  }
}"""


# ── Page ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(str(UPLOAD_DIR), filename)


# ── Plants CRUD ─────────────────────────────────────────────────────────────

@app.route("/api/plants", methods=["GET"])
def list_plants():
    with get_db() as db:
        plants = rows_to_list(db.execute("""
            SELECT p.*,
                   (SELECT filename FROM photos WHERE plant_id = p.id
                    ORDER BY uploaded_at DESC LIMIT 1) AS last_photo,
                   (SELECT watered_at FROM waterings WHERE plant_id = p.id
                    ORDER BY watered_at DESC LIMIT 1) AS last_watered
            FROM plants p ORDER BY p.name
        """).fetchall())
    return jsonify(plants)


@app.route("/api/plants", methods=["POST"])
def create_plant():
    data = request.get_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Le nom est requis"}), 400
    species = data.get("species", "").strip()
    care_guide = data.get("care_guide", "").strip()
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO plants (name, species, care_guide) VALUES (?, ?, ?)",
            (name, species, care_guide),
        )
        plant = row_to_dict(
            db.execute("SELECT * FROM plants WHERE id = ?", (cur.lastrowid,)).fetchone()
        )
    return jsonify(plant), 201


@app.route("/api/plants/<int:pid>", methods=["GET"])
def get_plant(pid):
    with get_db() as db:
        plant = row_to_dict(db.execute("SELECT * FROM plants WHERE id = ?", (pid,)).fetchone())
        if not plant:
            return jsonify({"error": "Plante introuvable"}), 404
    return jsonify(plant)


@app.route("/api/plants/<int:pid>", methods=["PUT"])
def update_plant(pid):
    data = request.get_json()
    with get_db() as db:
        plant = row_to_dict(db.execute("SELECT * FROM plants WHERE id = ?", (pid,)).fetchone())
        if not plant:
            return jsonify({"error": "Plante introuvable"}), 404
        db.execute(
            "UPDATE plants SET name=?, species=?, care_guide=? WHERE id=?",
            (
                data.get("name", plant["name"]),
                data.get("species", plant["species"]),
                data.get("care_guide", plant["care_guide"]),
                pid,
            ),
        )
        plant = row_to_dict(db.execute("SELECT * FROM plants WHERE id = ?", (pid,)).fetchone())
    return jsonify(plant)


@app.route("/api/plants/<int:pid>", methods=["DELETE"])
def delete_plant(pid):
    with get_db() as db:
        db.execute("DELETE FROM plants WHERE id = ?", (pid,))
    return "", 204


# ── Photos ──────────────────────────────────────────────────────────────────

@app.route("/api/plants/<int:pid>/photos", methods=["GET"])
def list_photos(pid):
    with get_db() as db:
        photos = rows_to_list(
            db.execute(
                "SELECT * FROM photos WHERE plant_id = ? ORDER BY uploaded_at DESC", (pid,)
            ).fetchall()
        )
    return jsonify(photos)


@app.route("/api/plants/<int:pid>/photos", methods=["POST"])
def upload_photo(pid):
    if "photo" in request.files:
        filename = save_upload(request.files["photo"])
    elif request.is_json and request.json.get("photo_base64"):
        filename = save_base64_image(request.json["photo_base64"])
    else:
        return jsonify({"error": "Aucune photo fournie"}), 400
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO photos (plant_id, filename) VALUES (?, ?)", (pid, filename)
        )
        photo = row_to_dict(
            db.execute("SELECT * FROM photos WHERE id = ?", (cur.lastrowid,)).fetchone()
        )
    return jsonify(photo), 201


@app.route("/api/plants/<int:pid>/photos/<int:photo_id>", methods=["DELETE"])
def delete_photo(pid, photo_id):
    with get_db() as db:
        photo = row_to_dict(
            db.execute(
                "SELECT * FROM photos WHERE id = ? AND plant_id = ?", (photo_id, pid)
            ).fetchone()
        )
        if photo:
            filepath = UPLOAD_DIR / photo["filename"]
            if filepath.exists():
                filepath.unlink()
            db.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
    return "", 204


# ── Waterings ───────────────────────────────────────────────────────────────

@app.route("/api/plants/<int:pid>/waterings", methods=["GET"])
def list_waterings(pid):
    with get_db() as db:
        waterings = rows_to_list(
            db.execute(
                "SELECT * FROM waterings WHERE plant_id = ? ORDER BY watered_at DESC LIMIT 30",
                (pid,),
            ).fetchall()
        )
    return jsonify(waterings)


@app.route("/api/plants/<int:pid>/waterings", methods=["POST"])
def add_watering(pid):
    data = request.get_json() or {}
    notes = data.get("notes", "")
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO waterings (plant_id, notes) VALUES (?, ?)", (pid, notes)
        )
        w = row_to_dict(
            db.execute("SELECT * FROM waterings WHERE id = ?", (cur.lastrowid,)).fetchone()
        )
    return jsonify(w), 201


# ── Repottings ──────────────────────────────────────────────────────────────

@app.route("/api/plants/<int:pid>/repottings", methods=["GET"])
def list_repottings(pid):
    with get_db() as db:
        repottings = rows_to_list(
            db.execute(
                "SELECT * FROM repottings WHERE plant_id = ? ORDER BY repotted_at DESC LIMIT 30",
                (pid,),
            ).fetchall()
        )
    return jsonify(repottings)


@app.route("/api/plants/<int:pid>/repottings", methods=["POST"])
def add_repotting(pid):
    data = request.get_json() or {}
    notes = data.get("notes", "")
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO repottings (plant_id, notes) VALUES (?, ?)", (pid, notes)
        )
        r = row_to_dict(
            db.execute("SELECT * FROM repottings WHERE id = ?", (cur.lastrowid,)).fetchone()
        )
    return jsonify(r), 201


# ── Ask Claude about a plant ────────────────────────────────────────────────

@app.route("/api/plants/<int:pid>/ask", methods=["POST"])
def ask_about_plant(pid):
    if not ANTHROPIC_API_KEY:
        return jsonify({"error": "Cle API non configuree"}), 503

    try:
        data = request.get_json()
        question = data.get("question", "").strip()
        photo_b64 = data.get("photo_base64")

        if not question:
            return jsonify({"error": "Question requise"}), 400

        with get_db() as db:
            plant = row_to_dict(db.execute("SELECT * FROM plants WHERE id = ?", (pid,)).fetchone())
            if not plant:
                return jsonify({"error": "Plante introuvable"}), 404
            last_watering = row_to_dict(
                db.execute(
                    "SELECT * FROM waterings WHERE plant_id = ? ORDER BY watered_at DESC LIMIT 1",
                    (pid,),
                ).fetchone()
            )

        context = f"""Tu es un expert en botanique et entretien de plantes.
L'utilisateur te pose une question sur sa plante.

Informations sur la plante :
- Nom : {plant['name']}
- Espece : {plant['species'] or 'Non renseignee'}
- Guide d'entretien : {plant['care_guide'] or 'Non renseigne'}
- Dernier arrosage : {last_watering['watered_at'] if last_watering else 'Jamais enregistre'}

Reponds en francais, de maniere claire et pratique."""

        content = []
        photo_filename = None

        if photo_b64:
            photo_filename = save_base64_image(photo_b64)
            media_type, b64data = extract_b64_parts(photo_b64)
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": b64data},
            })

        content.append({"type": "text", "text": question})

        client = get_claude_client()
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=context,
            messages=[{"role": "user", "content": content}],
        )

        answer = response.content[0].text

        with get_db() as db:
            cur = db.execute(
                "INSERT INTO conversations (plant_id, question, answer, photo_filename) VALUES (?, ?, ?, ?)",
                (pid, question, answer, photo_filename),
            )
            conv = row_to_dict(
                db.execute("SELECT * FROM conversations WHERE id = ?", (cur.lastrowid,)).fetchone()
            )

        return jsonify(conv), 201

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/plants/<int:pid>/conversations", methods=["GET"])
def list_conversations(pid):
    with get_db() as db:
        convs = rows_to_list(
            db.execute(
                "SELECT * FROM conversations WHERE plant_id = ? ORDER BY asked_at DESC",
                (pid,),
            ).fetchall()
        )
    return jsonify(convs)


# ── Checkups (plant health assessment) ──────────────────────────────────────

@app.route("/api/plants/<int:pid>/checkups", methods=["GET"])
def list_checkups(pid):
    with get_db() as db:
        checkups = rows_to_list(
            db.execute(
                "SELECT * FROM checkups WHERE plant_id = ? ORDER BY checked_at DESC",
                (pid,),
            ).fetchall()
        )
    return jsonify(checkups)


@app.route("/api/plants/<int:pid>/checkup", methods=["POST"])
def create_checkup(pid):
    if not ANTHROPIC_API_KEY:
        return jsonify({"error": "Cle API non configuree"}), 503

    try:
        data = request.get_json()
        photo_b64 = data.get("photo_base64")
        if not photo_b64:
            return jsonify({"error": "Photo requise"}), 400

        with get_db() as db:
            plant = row_to_dict(db.execute("SELECT * FROM plants WHERE id = ?", (pid,)).fetchone())
            if not plant:
                return jsonify({"error": "Plante introuvable"}), 404
            last_checkup = row_to_dict(
                db.execute(
                    "SELECT * FROM checkups WHERE plant_id = ? ORDER BY checked_at DESC LIMIT 1",
                    (pid,),
                ).fetchone()
            )
            last_watering = row_to_dict(
                db.execute(
                    "SELECT * FROM waterings WHERE plant_id = ? ORDER BY watered_at DESC LIMIT 1",
                    (pid,),
                ).fetchone()
            )

        photo_filename = save_base64_image(photo_b64)
        media_type, b64data = extract_b64_parts(photo_b64)

        has_previous = last_checkup and last_checkup["photo_filename"]
        comparison_instruction = ""
        if has_previous:
            comparison_instruction = (
                "\nUne photo precedente du dernier bilan est aussi fournie. "
                "Compare l'etat actuel avec le precedent et indique si la plante "
                "s'est amelioree, degradee, ou est restee stable."
            )

        system_prompt = f"""Tu es un expert botaniste qui realise un bilan de sante d'une plante.

Informations sur la plante :
- Nom : {plant['name']}
- Espece : {plant['species'] or 'Non renseignee'}
- Dernier arrosage : {last_watering['watered_at'] if last_watering else 'Jamais enregistre'}
{comparison_instruction}

Reponds UNIQUEMENT avec un objet JSON valide (sans markdown, sans backticks) :
{{
  "status": "good" ou "warning" ou "bad",
  "summary": "Resume en une phrase de l'etat general",
  "details": "Description detaillee de ce que tu observes (feuilles, tiges, couleur, etc.)",
  "comparison": "Comparaison avec la photo precedente si disponible, sinon chaine vide",
  "recommendations": "Conseils pratiques pour ameliorer ou maintenir la sante de la plante"
}}"""

        # Build message content
        content = []

        # Add previous checkup photo if available
        if has_previous:
            prev_photo_path = UPLOAD_DIR / last_checkup["photo_filename"]
            if prev_photo_path.exists():
                prev_bytes = prev_photo_path.read_bytes()
                prev_ext = prev_photo_path.suffix.lower()
                prev_mime = "image/jpeg" if prev_ext in (".jpg", ".jpeg") else f"image/{prev_ext.lstrip('.')}"
                content.append({
                    "type": "text",
                    "text": f"Photo du bilan precedent ({last_checkup['checked_at']}) :"
                })
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": prev_mime,
                        "data": base64.b64encode(prev_bytes).decode(),
                    },
                })

        content.append({"type": "text", "text": "Photo actuelle :"})
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": b64data},
        })
        content.append({"type": "text", "text": "Fais le bilan de sante de cette plante."})

        client = get_claude_client()
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=system_prompt,
            messages=[{"role": "user", "content": content}],
        )

        raw_text = response.content[0].text.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        try:
            result = json_mod.loads(raw_text)
        except json_mod.JSONDecodeError:
            result = {
                "status": "unknown",
                "summary": raw_text[:200],
                "details": raw_text,
                "comparison": "",
                "recommendations": "",
            }

        with get_db() as db:
            cur = db.execute(
                """INSERT INTO checkups
                   (plant_id, photo_filename, status, summary, details, comparison, recommendations)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    pid,
                    photo_filename,
                    result.get("status", "unknown"),
                    result.get("summary", ""),
                    result.get("details", ""),
                    result.get("comparison", ""),
                    result.get("recommendations", ""),
                ),
            )
            checkup = row_to_dict(
                db.execute("SELECT * FROM checkups WHERE id = ?", (cur.lastrowid,)).fetchone()
            )

        return jsonify(checkup), 201

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ── Identify plant from photo ───────────────────────────────────────────────

@app.route("/api/plants/identify", methods=["POST"])
def identify_plant():
    if not ANTHROPIC_API_KEY:
        return jsonify({"error": "Cle API non configuree"}), 503

    try:
        photo_b64 = None
        if "photo" in request.files:
            f = request.files["photo"]
            raw = f.read()
            ext = Path(f.filename).suffix.lower() or ".jpg"
            mime = "image/jpeg" if ext in (".jpg", ".jpeg") else f"image/{ext.lstrip('.')}"
            photo_b64 = f"data:{mime};base64," + base64.b64encode(raw).decode()
        elif request.is_json and request.json.get("photo_base64"):
            photo_b64 = request.json["photo_base64"]

        if not photo_b64:
            return jsonify({"error": "Photo requise"}), 400

        photo_filename = save_base64_image(photo_b64)
        media_type, b64data = extract_b64_parts(photo_b64)

        client = get_claude_client()
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=GUIDE_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64data}},
                    {"type": "text", "text": "Identifie cette plante et donne-moi son guide d'entretien structure."},
                ],
            }],
        )

        raw_text = response.content[0].text.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        try:
            info = json_mod.loads(raw_text)
        except json_mod.JSONDecodeError:
            info = {"name": "Plante inconnue", "species": "", "guide": {}}

        name = info.get("name", "Plante inconnue")
        species = info.get("species", "")
        guide = info.get("guide", {})

        # Store guide as JSON string
        care_guide_json = json_mod.dumps(guide, ensure_ascii=False)

        with get_db() as db:
            cur = db.execute(
                "INSERT INTO plants (name, species, care_guide) VALUES (?, ?, ?)",
                (name, species, care_guide_json),
            )
            plant_id = cur.lastrowid
            db.execute(
                "INSERT INTO photos (plant_id, filename) VALUES (?, ?)",
                (plant_id, photo_filename),
            )
            plant = row_to_dict(
                db.execute("SELECT * FROM plants WHERE id = ?", (plant_id,)).fetchone()
            )

        plant["photo"] = photo_filename
        return jsonify(plant), 201

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ── AI status ──────────────────────────────────────────────────────────────

@app.route("/api/ai-status")
def ai_status():
    return jsonify({"available": bool(ANTHROPIC_API_KEY)})


# ── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    import socket
    local_ip = "?"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass
    print(f"\n  Mes Plantes est accessible sur :")
    print(f"    - http://localhost:5000")
    print(f"    - http://{local_ip}:5000  (depuis ton telephone)\n")
    app.run(host="0.0.0.0", port=5000, debug=True)
