"""
Cousinade Planner — Flask Backend
API endpoints for gîtes search, participant management, and cost simulation.
"""

import json
import os
import math
import secrets
import threading
from datetime import datetime, timezone
from functools import wraps
import requests as http_requests
from urllib.parse import unquote, urlparse
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
from scraper import search_gites, run_deep_scan

# ─── Configuration ───────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PARTICIPANTS_FILE = os.path.join(DATA_DIR, "participants.json")
MANUAL_GITES_FILE = os.path.join(DATA_DIR, "manual_gites.json")
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

app = Flask(__name__, static_folder=STATIC_DIR, template_folder=TEMPLATES_DIR)
CORS(app)

# ─── API Key for manual gîtes endpoint ───────────────────────────────────────
_MANUAL_API_KEY = os.environ.get("MANUAL_API_KEY", "")
if not _MANUAL_API_KEY:
    _MANUAL_API_KEY = secrets.token_urlsafe(32)
    print(f"\n{'='*60}")
    print("⚠️  MANUAL_API_KEY non définie dans l'environnement.")
    print("Clé temporaire générée pour cette session :")
    print(f"  {_MANUAL_API_KEY}")
    print("Ajoutez cette clé dans les options de votre extension Chrome.")
    print("Pour la rendre permanente : set MANUAL_API_KEY=<clé> avant de lancer Flask.")
    print(f"{'='*60}\n")


# ─── Helpers ─────────────────────────────────────────────────────────────────
def load_participants() -> list[dict]:
    """Load participants from JSON file."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(PARTICIPANTS_FILE):
        save_participants([])
    try:
        with open(PARTICIPANTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def save_participants(participants: list[dict]) -> None:
    """Save participants to JSON file."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PARTICIPANTS_FILE, "w", encoding="utf-8") as f:
        json.dump(participants, f, ensure_ascii=False, indent=2)


def require_api_key(f):
    """Decorator: require valid X-API-Key header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key", "")
        if not key or key != _MANUAL_API_KEY:
            return jsonify({"success": False, "error": "Clé API invalide ou manquante"}), 401
        return f(*args, **kwargs)
    return decorated


def load_manual_gites() -> list[dict]:
    """Load manually-added gîtes from JSON file."""
    if not os.path.exists(MANUAL_GITES_FILE):
        return []
    try:
        with open(MANUAL_GITES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def save_manual_gites(gites: list[dict]) -> None:
    """Persist manually-added gîtes to JSON file."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(MANUAL_GITES_FILE, "w", encoding="utf-8") as f:
        json.dump(gites, f, ensure_ascii=False, indent=2)


def compute_totals(participants: list[dict]) -> dict:
    """Compute total adults, children, babies, and total people."""
    total_adultes = sum(p.get("adultes", 0) for p in participants)
    total_enfants = sum(p.get("enfants", 0) for p in participants)
    total_bebes = sum(p.get("bebes", 0) for p in participants)
    total_personnes = total_adultes + total_enfants + total_bebes
    return {
        "total_adultes": total_adultes,
        "total_enfants": total_enfants,
        "total_bebes": total_bebes,
        "total_personnes": total_personnes,
        "nb_foyers": len(participants),
    }


# ─── Frontend Serving ────────────────────────────────────────────────────────
@app.route("/")
def index():
    """Serve the main HTML page."""
    return send_from_directory(TEMPLATES_DIR, "index.html")


@app.route("/static/<path:filename>")
def serve_static(filename):
    """Serve static files (CSS, JS, images)."""
    return send_from_directory(STATIC_DIR, filename)


# ─── API: Image Proxy ───────────────────────────────────────────────────────
@app.route("/api/proxy-image")
def proxy_image():
    """
    Proxy external gîte images to bypass hotlink protection.
    Usage: /api/proxy-image?url=https://www.grandsgites.com/images/...
    """
    image_url = request.args.get("url", "")
    if not image_url:
        return "", 400

    image_url = unquote(image_url)
    parsed = urlparse(image_url)

    # Only allow proxying from known gîte sites
    allowed_domains = [
        "grandsgites.com", "www.grandsgites.com",
        "toploc.com", "www.toploc.com",
        "greengo.voyage", "www.greengo.voyage",
        "gites-de-france.com", "www.gites-de-france.com",
        "abritel.fr", "www.abritel.fr",
        "clevacances.com", "www.clevacances.com",
        "giga-location.com", "www.giga-location.com",
        "gitesxxl.fr", "www.gitesxxl.fr",
        # CDNs for manually-added gîtes (Airbnb, Abritel/VRBO, etc.)
        "muscache.com",
        "trvl-media.com",
        "expediagroup.com",
    ]
    # Also allow departmental GdF subdomains (gites-de-france-drome.com, etc.)
    is_gdf_dept = parsed.hostname and "gites-de-france-" in parsed.hostname
    if parsed.hostname and not is_gdf_dept and not any(parsed.hostname.endswith(d) for d in allowed_domains):
        return "", 403

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Referer": f"{parsed.scheme}://{parsed.hostname}/",
            "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
        }
        resp = http_requests.get(image_url, headers=headers, timeout=10, stream=True)
        if resp.status_code != 200:
            return "", resp.status_code

        content_type = resp.headers.get("Content-Type", "image/jpeg")
        return Response(
            resp.content,
            content_type=content_type,
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except Exception:
        return "", 502


# ─── API: Gîtes Search ──────────────────────────────────────────────────────
@app.route("/api/gites", methods=["GET"])
def api_search_gites():
    """
    Search for gîtes with optional filters.
    Query params: capacite_min, departement, budget_max, animaux
    Always scrapes live data (cached for 1 hour).
    """
    try:
        capacite_min = int(request.args.get("capacite_min", 10))
        departement_str = request.args.get("departement", "").strip() or None
        departements = [d.strip() for d in departement_str.split(",")] if departement_str else None
        budget_max_str = request.args.get("budget_max", "").strip()
        budget_max = int(budget_max_str) if budget_max_str else None
        animaux_str = request.args.get("animaux", "").strip().lower()
        animaux = True if animaux_str == "true" else None
        
        sources_str = request.args.get("sources", "")
        sources_list = [s.strip() for s in sources_str.split(",") if s.strip()] if sources_str else None

        # Separate "manuel" from scraper sources so the scraper never receives it
        include_manual = sources_list is None or "manuel" in sources_list
        scraper_sources = [s for s in (sources_list or []) if s != "manuel"] or None

        gites = search_gites(
            capacite_min=capacite_min,
            departements=departements,
            budget_max=budget_max,
            animaux=animaux,
            sources=scraper_sources,
        )

        # Merge manually-added gîtes (apply same basic filters)
        if include_manual:
            for g in load_manual_gites():
                cap = int(g.get("capacite") or 0)
                if cap < capacite_min:
                    continue
                if departements and g.get("departement") not in departements:
                    continue
                if budget_max and g.get("prix_semaine") and g["prix_semaine"] > budget_max:
                    continue
                if animaux and not g.get("animaux"):
                    continue
                gites.append(g)

        return jsonify({"success": True, "gites": gites, "count": len(gites)})

    except Exception as e:
        return jsonify({"success": False, "error": str(e), "gites": []}), 500


@app.route("/api/deep-scan", methods=["POST"])
def api_deep_scan():
    """
    Trigger a deep scan in the background.
    """
    try:
        capacite_min = int(request.json.get("capacite_min", 10)) if request.is_json else 10
        sources = request.json.get("sources", None) if request.is_json else None
        
        # Start in background so it doesn't block the request
        thread = threading.Thread(target=run_deep_scan, args=(capacite_min, sources))
        thread.daemon = True
        thread.start()
        
        return jsonify({"success": True, "message": "Scan approfondi démarré. Cela peut prendre plusieurs minutes."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/clear-cache", methods=["POST"])
def api_clear_cache():
    """
    Clear all cached scraper JSON files and deep scan results.
    """
    try:
        import glob
        deleted = 0
        cache_files = glob.glob(os.path.join(DATA_DIR, "cache_*.json"))
        deep_file = os.path.join(DATA_DIR, "deep_gites.json")
        if os.path.exists(deep_file):
            cache_files.append(deep_file)

        for filepath in cache_files:
            try:
                os.remove(filepath)
                deleted += 1
            except Exception as e:
                pass
                
        return jsonify({"success": True, "message": f"{deleted} fichiers de cache supprimés."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── API: Participants ───────────────────────────────────────────────────────
@app.route("/api/participants", methods=["GET"])
def api_get_participants():
    """Get all registered participant families."""
    participants = load_participants()
    totals = compute_totals(participants)
    return jsonify({
        "success": True,
        "participants": participants,
        "totals": totals,
    })


@app.route("/api/participants", methods=["POST"])
def api_add_participant():
    """
    Add a new family (foyer).
    Body JSON: { nom_foyer, adultes, enfants, bebes }
    """
    try:
        data = request.get_json()
        if not data or not data.get("nom_foyer"):
            return jsonify({"success": False, "error": "Nom du foyer requis"}), 400

        participants = load_participants()

        # Generate unique ID
        max_id = max((p.get("id", 0) for p in participants), default=0)
        new_participant = {
            "id": max_id + 1,
            "nom_foyer": data["nom_foyer"].strip(),
            "adultes": max(0, int(data.get("adultes", 1))),
            "enfants": max(0, int(data.get("enfants", 0))),
            "bebes": max(0, int(data.get("bebes", 0))),
        }

        participants.append(new_participant)
        save_participants(participants)

        totals = compute_totals(participants)
        return jsonify({
            "success": True,
            "participant": new_participant,
            "totals": totals,
        }), 201

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/participants/<int:participant_id>", methods=["PUT"])
def api_update_participant(participant_id: int):
    """Update an existing participant family."""
    try:
        data = request.get_json()
        participants = load_participants()

        for p in participants:
            if p["id"] == participant_id:
                if data.get("nom_foyer"):
                    p["nom_foyer"] = data["nom_foyer"].strip()
                if "adultes" in data:
                    p["adultes"] = max(0, int(data["adultes"]))
                if "enfants" in data:
                    p["enfants"] = max(0, int(data["enfants"]))
                if "bebes" in data:
                    p["bebes"] = max(0, int(data["bebes"]))

                save_participants(participants)
                totals = compute_totals(participants)
                return jsonify({"success": True, "participant": p, "totals": totals})

        return jsonify({"success": False, "error": "Participant non trouvé"}), 404

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/participants/<int:participant_id>", methods=["DELETE"])
def api_delete_participant(participant_id: int):
    """Remove a participant family."""
    try:
        participants = load_participants()
        original_len = len(participants)
        participants = [p for p in participants if p["id"] != participant_id]

        if len(participants) == original_len:
            return jsonify({"success": False, "error": "Participant non trouvé"}), 404

        save_participants(participants)
        totals = compute_totals(participants)
        return jsonify({"success": True, "totals": totals})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── API: Cost Simulation ───────────────────────────────────────────────────
@app.route("/api/simulation", methods=["POST"])
def api_simulate_costs():
    """
    Simulate costs for a given gîte and current participants.
    Body JSON: {
        gite_id: int (optional, for reference),
        prix_semaine: float,
        frais_adulte: float (daily food/logistics per adult),
        frais_enfant: float (daily food/logistics per child),
        nb_jours: int (number of days, default 7)
    }
    """
    try:
        data = request.get_json()
        prix_semaine = float(data.get("prix_semaine", 0))
        frais_adulte = float(data.get("frais_adulte", 15))
        frais_enfant = float(data.get("frais_enfant", 8))
        nb_jours = int(data.get("nb_jours", 7))

        participants = load_participants()
        totals = compute_totals(participants)

        if totals["total_personnes"] == 0:
            return jsonify({
                "success": False,
                "error": "Aucun participant inscrit. Ajoutez des foyers d'abord.",
            }), 400

        # Total food/logistics cost
        total_frais_bouche = (
            totals["total_adultes"] * frais_adulte * nb_jours
            + totals["total_enfants"] * frais_enfant * nb_jours
            # Babies don't pay food costs
        )

        # Total cost = lodging + food/logistics
        cout_total = prix_semaine + total_frais_bouche

        # Per-person cost (proportional: adults = 1 share, children = 0.5 share, babies = 0)
        total_parts = totals["total_adultes"] + (totals["total_enfants"] * 0.5)
        if total_parts == 0:
            total_parts = 1  # Safety fallback

        prix_par_part = cout_total / total_parts

        # Calculate per-family breakdown
        repartition = []
        for p in participants:
            parts_foyer = p["adultes"] + (p["enfants"] * 0.5)
            cout_foyer = round(parts_foyer * prix_par_part, 2)

            # Detail: lodging share + food share
            lodging_share = round(parts_foyer * (prix_semaine / total_parts), 2)
            food_share = round(
                (p["adultes"] * frais_adulte * nb_jours)
                + (p["enfants"] * frais_enfant * nb_jours),
                2,
            )

            repartition.append({
                "id": p["id"],
                "nom_foyer": p["nom_foyer"],
                "adultes": p["adultes"],
                "enfants": p["enfants"],
                "bebes": p["bebes"],
                "parts": parts_foyer,
                "cout_hebergement": lodging_share,
                "cout_bouche": food_share,
                "cout_total": round(lodging_share + food_share, 2),
            })

        return jsonify({
            "success": True,
            "simulation": {
                "prix_gite": prix_semaine,
                "frais_adulte_jour": frais_adulte,
                "frais_enfant_jour": frais_enfant,
                "nb_jours": nb_jours,
                "total_frais_bouche": round(total_frais_bouche, 2),
                "cout_total": round(cout_total, 2),
                "total_parts": total_parts,
                "prix_par_part": round(prix_par_part, 2),
                "totals": totals,
            },
            "repartition": repartition,
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── API: Manual Gîtes (Browser Extension Gateway) ──────────────────────────
@app.route("/api/manual-gites", methods=["GET"])
def api_get_manual_gites():
    """Return all manually-added gîtes (read-only, no auth required)."""
    gites = load_manual_gites()
    return jsonify({"success": True, "gites": gites, "count": len(gites)})


@app.route("/api/manual-gites", methods=["POST"])
@require_api_key
def api_add_manual_gite():
    """
    Add a gîte manually (e.g. via browser extension).
    Requires X-API-Key header.
    Body JSON: { nom, url, capacite, prix_semaine, localisation, departement,
                 description, equipements, photo, note, animaux }
    """
    try:
        data = request.get_json()
        if not data or not data.get("nom"):
            return jsonify({"success": False, "error": "Nom du gîte requis"}), 400

        gites = load_manual_gites()

        # Generate next manual ID
        max_num = 0
        for g in gites:
            try:
                max_num = max(max_num, int(str(g.get("id", "manual_0")).replace("manual_", "")))
            except (ValueError, TypeError):
                pass

        prix = data.get("prix_semaine")
        note = data.get("note")

        new_gite = {
            "id": f"manual_{max_num + 1}",
            "nom": data.get("nom", "").strip(),
            "url": data.get("url", "").strip(),
            "capacite": int(data.get("capacite") or 0),
            "prix_semaine": float(prix) if prix not in (None, "", 0) else None,
            "localisation": data.get("localisation", "").strip(),
            "departement": data.get("departement", "").strip(),
            "description": data.get("description", "").strip(),
            "equipements": data.get("equipements") or [],
            "photo": data.get("photo", "").strip(),
            "note": float(note) if note not in (None, "", 0) else None,
            "animaux": bool(data.get("animaux", False)),
            "source": "manuel",
            "added_at": datetime.now(timezone.utc).isoformat(),
        }

        gites.append(new_gite)
        save_manual_gites(gites)
        return jsonify({"success": True, "gite": new_gite}), 201

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/manual-gites/<gite_id>", methods=["DELETE"])
@require_api_key
def api_delete_manual_gite(gite_id: str):
    """Remove a manually-added gîte. Requires X-API-Key header."""
    try:
        gites = load_manual_gites()
        original_len = len(gites)
        gites = [g for g in gites if str(g.get("id")) != gite_id]

        if len(gites) == original_len:
            return jsonify({"success": False, "error": "Gîte non trouvé"}), 404

        save_manual_gites(gites)
        return jsonify({"success": True})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── Run ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)
