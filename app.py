"""
Cousinade Planner — Flask Backend
API endpoints for gîtes search, participant management, and cost simulation.
"""

import json
import os
import math
import requests as http_requests
from urllib.parse import unquote, urlparse
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
from scraper import search_gites

# ─── Configuration ───────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PARTICIPANTS_FILE = os.path.join(DATA_DIR, "participants.json")
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

app = Flask(__name__, static_folder=STATIC_DIR, template_folder=TEMPLATES_DIR)
CORS(app)


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
        departement = request.args.get("departement", "").strip() or None
        budget_max_str = request.args.get("budget_max", "").strip()
        budget_max = int(budget_max_str) if budget_max_str else None
        animaux_str = request.args.get("animaux", "").strip().lower()
        animaux = True if animaux_str == "true" else None

        gites = search_gites(
            capacite_min=capacite_min,
            departement=departement,
            budget_max=budget_max,
            animaux=animaux,
        )
        return jsonify({"success": True, "gites": gites, "count": len(gites)})

    except Exception as e:
        return jsonify({"success": False, "error": str(e), "gites": []}), 500


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


# ─── Run ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)
