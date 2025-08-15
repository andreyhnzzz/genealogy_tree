from flask import Flask, render_template, request, jsonify, Response, make_response
import time, threading, json, random, string, math

app = Flask(__name__)

# ----------------------------
# In-memory data store
# ----------------------------
class Store:
    def __init__(self):
        self.lock = threading.RLock()
        self.reset()

    def reset(self):
        with self.lock:
            self.year = 1990
            self.ticks = 0
            self.families = {}
            self.people = {}
            self.unions = set()
            self.version = 0

    def bump_version(self):
        self.version += 1

store = Store()
change_event = threading.Event()

def notify_change():
    with store.lock:
        store.bump_version()
    change_event.set()

def rand_id(n=9):
    return ''.join(random.choice(string.digits) for _ in range(n))

# ----------------------------
# Relationship inference utils
# ----------------------------
def is_alive(p):
    return p.get("vivo", True) and p.get("fecha_def") is None

def age_of(p):
    return p.get("edad", 0)

def interests_match(p1, p2):
    s1 = set(p1.get("intereses", [])); s2 = set(p2.get("intereses", []))
    return len(s1.intersection(s2))

def genome_distance(g1, g2):
    n = min(len(g1), len(g2))
    return sum(1 for i in range(n) if g1[i] != g2[i]) + abs(len(g1)-len(g2))

def compatibility_score(p1, p2):
    k = min(interests_match(p1, p2), 5)
    interests_part = k / 5 * 50
    age_diff = abs(age_of(p1) - age_of(p2))
    age_part = max(0, 25 - min(age_diff, 25))
    gd = genome_distance(p1.get("genome",""), p2.get("genome",""))
    genome_part = min(gd, 25)
    return interests_part + age_part + genome_part

def are_siblings(a, b):
    return bool(set(a.get("padres", [])) & set(b.get("padres", [])))

def set_union(a_id, b_id):
    pair = tuple(sorted([a_id, b_id]))
    store.unions.add(pair)
    pa, pb = store.people.get(a_id), store.people.get(b_id)
    if pa: pa["pareja"] = b_id
    if pb: pb["pareja"] = a_id

# ----------------------------
# Simulation: every 10s == +1 year
# ----------------------------
def simulate_year():
    with store.lock:
        store.year += 1
        # birthdays
        for p in store.people.values():
            if is_alive(p):
                p["edad"] = p.get("edad", 0) + 1
        # deaths
        for p in store.people.values():
            if is_alive(p):
                base = 0.002 + p["edad"] * 0.0005
                if random.random() < base:
                    p["vivo"] = False
                    p["fecha_def"] = store.year
                    spouse = p.get("pareja")
                    if spouse and spouse in store.people and is_alive(store.people[spouse]):
                        store.people[spouse]["estado_civil"] = "viudo"
                        store.people[spouse]["viudo"] = True
        # unions
        alive_ids = [cid for cid, p in store.people.items() if is_alive(p) and p.get("edad",0) >= 18 and not p.get("pareja")]
        random.shuffle(alive_ids)
        for i in range(len(alive_ids)):
            a_id = alive_ids[i]; a = store.people[a_id]
            candidates = [b_id for b_id in alive_ids if b_id != a_id]
            random.shuffle(candidates)
            for b_id in candidates[:6]:
                b = store.people[b_id]
                if b.get("pareja"): continue
                if abs(a["edad"] - b["edad"]) > 15: continue
                if are_siblings(a, b): continue
                score = compatibility_score(a, b)
                if a.get("viudo"): score -= 10
                if b.get("viudo"): score -= 10
                if score >= 70:
                    set_union(a_id, b_id)
                    break
        # births
        for (a_id, b_id) in list(store.unions):
            a = store.people.get(a_id); b = store.people.get(b_id)
            if not a or not b: continue
            if not (is_alive(a) and is_alive(b)): continue
            if not (18 <= a["edad"] <= 45 and 18 <= b["edad"] <= 45): continue
            p_birth = min(0.10, 0.02 + compatibility_score(a, b) / 1000.0)
            if random.random() < p_birth:
                child_id = rand_id(9)
                child = {
                    "cedula": child_id, "nombre": f"Bebe{child_id[-3:]}", "edad": 0,
                    "fecha_nac": store.year, "fecha_def": None, "vivo": True,
                    "genero": random.choice(["M","F"]), "provincia": random.choice(["SJ","AL","CA","HE","LI","PU","GU"]),
                    "estado_civil": "soltero", "padres": [a_id, b_id], "hijos": [], "pareja": None,
                    "intereses": random.sample(["música","deporte","cine","lectura","cocina","viajes","arte","jardinería","tecnología"], k=3),
                    "genome": ''.join(random.choice("ACGT") for _ in range(20)), "historial": [(store.year, "nacimiento")],
                    "familia_id": None
                }
                store.people[child_id] = child
                a.setdefault("hijos", []).append(child_id)
                b.setdefault("hijos", []).append(child_id)
    notify_change()

def sim_loop():
    while True:
        time.sleep(10)
        with store.lock: store.ticks += 1
        simulate_year()

threading.Thread(target=sim_loop, daemon=True).start()

# ----------------------------
# Routes
# ----------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.get("/state")
def get_state():
    with store.lock:
        data = {
            "year": store.year,
            "counts": {
                "families": len(store.families),
                "people": len(store.people),
                "unions": len(store.unions),
                "living": sum(1 for p in store.people.values() if is_alive(p)),
            },
            "people": list(store.people.values())[:120],
            "version": store.version,
        }
    return jsonify(data)

@app.post("/families")
def create_family():
    body = request.get_json(force=True)
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Nombre requerido"}), 400
    fid = rand_id(6)
    with store.lock:
        store.families[fid] = {"id": fid, "name": name, "members": set()}
    notify_change()
    return jsonify({"ok": True, "family": {"id": fid, "name": name}})

@app.post("/people")
def create_person():
    body = request.get_json(force=True)
    p = {
        "cedula": body.get("cedula") or rand_id(9),
        "nombre": body.get("nombre","SinNombre"),
        "edad": int(body.get("edad", 0)),
        "fecha_nac": body.get("fecha_nac"),
        "fecha_def": None,
        "vivo": True,
        "genero": body.get("genero","M"),
        "provincia": body.get("provincia","SJ"),
        "estado_civil": body.get("estado_civil","soltero"),
        "padres": [x for x in body.get("padres", []) if x],
        "hijos": [],
        "pareja": None,
        "intereses": body.get("intereses", []),
        "genome": body.get("genome") or ''.join(random.choice("ACGT") for _ in range(20)),
        "historial": [],
        "familia_id": body.get("familia_id"),
    }
    with store.lock:
        store.people[p["cedula"]] = p
        fid = p.get("familia_id")
        if fid and fid in store.families:
            store.families[fid]["members"].add(p["cedula"])
        # If parents provided, infer child links
        for pid in p["padres"]:
            if pid in store.people:
                store.people[pid].setdefault("hijos", []).append(p["cedula"])
    notify_change()
    return jsonify({"ok": True, "person": p})

@app.get("/stream")
def stream():
    def event_stream(last_version=[-1]):
        while True:
            change_event.wait()
            with store.lock:
                v = store.version
                payload = {
                    "version": v,
                    "year": store.year,
                    "counts": {
                        "families": len(store.families),
                        "people": len(store.people),
                        "unions": len(store.unions),
                        "living": sum(1 for p in store.people.values() if is_alive(p)),
                    },
                }
                if v == last_version[0]:
                    change_event.clear()
                    continue
                last_version[0] = v
                data = f"data: {json.dumps(payload)}\\n\\n"
            change_event.clear()
            yield data
    return Response(event_stream(), mimetype="text/event-stream")

# ----------------------------
# SVG Tree (quick layered layout by generations)
# ----------------------------
def compute_levels():
    # Assign level 0 to roots (no parents), then BFS by children.
    with store.lock:
        people = store.people
        roots = [pid for pid, p in people.items() if not p.get("padres")]
        level = {}
        frontier = roots[:]
        for r in roots:
            level[r] = 0
        i = 0
        while frontier and i < 50:  # safety depth
            nxt = []
            for u in frontier:
                for v in people.get(u, {}).get("hijos", []):
                    if v not in level:
                        level[v] = level[u] + 1
                        nxt.append(v)
            frontier = nxt
            i += 1
        # If anyone unassigned (cycles or disconnected), put level 0
        for pid in people.keys():
            if pid not in level:
                level[pid] = 0
        return level

@app.get("/tree.svg")
def tree_svg():
    with store.lock:
        people = dict(store.people)  # shallow copy
        unions = list(store.unions)
    level = compute_levels()
    # Group by level
    layers = {}
    for pid, lv in level.items():
        layers.setdefault(lv, []).append(pid)
    # Sort persons per layer for stable layout
    for lv in layers:
        layers[lv].sort()
    # Layout params
    layer_gap = 120
    node_w, node_h = 140, 46
    hgap = 40
    # Compute width by max nodes
    max_nodes = max((len(nodes) for nodes in layers.values()), default=1)
    width = max(400, max_nodes * (node_w + hgap) + hgap)
    max_level = max(layers.keys(), default=0)
    height = (max_level + 1) * (layer_gap + node_h) + layer_gap
    # Coordinates
    coords = {}
    for lv in range(max_level + 1):
        row = layers.get(lv, [])
        n = max(1, len(row))
        total_w = n * node_w + (n + 1) * hgap
        x = (width - total_w) / 2 + hgap
        y = layer_gap + lv * (node_w * 0 + node_h + layer_gap)
        for i, pid in enumerate(row):
            coords[pid] = (x + i * (node_w + hgap), y)

    # Build SVG
    def esc(s): 
        return (s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" style="background:#0b1020">']
    # Edges: parent -> child
    with store.lock:
        for cid, p in people.items():
            x2, y2 = coords.get(cid, (0,0))
            for par in p.get("padres", []):
                x1, y1 = coords.get(par, (x2, y2-60))
                parts.append(f'<line x1="{x1+node_w/2}" y1="{y1+node_h}" x2="{x2+node_w/2}" y2="{y2}" stroke="#6ea8fe" stroke-width="1.5" />')
        # Edges: unions
        for a_id, b_id in unions:
            if a_id in coords and b_id in coords:
                xa, ya = coords[a_id]; xb, yb = coords[b_id]
                ym = (ya + yb) / 2
                parts.append(f'<path d="M {xa+node_w/2} {ya+node_h/2} C {xa+node_w/2} {ym} {xb+node_w/2} {ym} {xb+node_w/2} {yb+node_h/2}" stroke="#b794f4" stroke-width="1.5" fill="none" />')

        # Nodes
        for pid, p in people.items():
            x, y = coords.get(pid, (10,10))
            fill = "#152347" if is_alive(p) else "#3a0f1e"
            border = "#475569" if is_alive(p) else "#ef4444"
            parts.append(f'<rect x="{x}" y="{y}" rx="10" ry="10" width="{node_w}" height="{node_h}" fill="{fill}" stroke="{border}" stroke-width="1.5" />')
            name = esc(p.get("nombre","?"))[:18]
            meta = f'{p.get("edad",0)}{" • ♥" if p.get("pareja") else ""}'
            parts.append(f'<text x="{x+10}" y="{y+20}" fill="#e2e8f0" font-size="12" font-family="ui-sans-serif">{name}</text>')
            parts.append(f'<text x="{x+10}" y="{y+36}" fill="#94a3b8" font-size="11" font-family="ui-sans-serif">{meta}</text>')

    parts.append('</svg>')
    svg = "".join(parts)
    resp = make_response(svg)
    resp.headers["Content-Type"] = "image/svg+xml"
    resp.headers["Cache-Control"] = "no-store"
    return resp

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
