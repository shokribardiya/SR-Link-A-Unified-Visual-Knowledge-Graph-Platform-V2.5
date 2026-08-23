# ============================================================
# SR Link - Visual Intelligence Linking & Analysis Platform
# Pure Python (stdlib only) - single cohesive script
# ============================================================

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import sqlite3, json, os, pathlib, threading, hashlib, datetime, csv, math, uuid, webbrowser, random

APP_TITLE = "SR Link — Intelligence Graph Platform"
DB_FILE = "sr_link_data.db"

BG        = "#050505"
PANEL_BG  = "#0b0b0b"
PANEL_BG2 = "#111111"
FG        = "#e8e8e8"
FG_DIM    = "#9a9a9a"
ACCENT    = "#ffffff"
BORDER    = "#2a2a2a"

TYPE_COLORS = {
    "Website":"#4fd1c5","File":"#f6ad55","Folder":"#f6e05e","Application":"#ed64a6",
    "Text":"#a0aec0","Image":"#68d391","Database":"#63b3ed","Person":"#fc8181",
    "Organization":"#b794f4","Event":"#f56565","Custom":"#e2e8f0"
}
NODE_TYPES = list(TYPE_COLORS.keys())

def now_iso(): return datetime.datetime.now().isoformat(timespec="seconds")
def new_id(): return uuid.uuid4().hex[:12]

# ---------------------------------------------------------------
# DATABASE LAYER
# ---------------------------------------------------------------
class DB:
    def __init__(self, path=DB_FILE):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self):
        c = self.conn.cursor()
        c.executescript("""
        CREATE TABLE IF NOT EXISTS nodes(
            id TEXT PRIMARY KEY, name TEXT, type TEXT, description TEXT,
            tags TEXT, created TEXT, source TEXT, x REAL, y REAL,
            custom_fields TEXT, notes TEXT, attachments TEXT
        );
        CREATE TABLE IF NOT EXISTS edges(
            id TEXT PRIMARY KEY, src TEXT, dst TEXT, rel_type TEXT,
            created TEXT, weight REAL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS projects(
            id TEXT PRIMARY KEY, name TEXT, created TEXT, meta TEXT
        );
        CREATE TABLE IF NOT EXISTS history(
            id TEXT PRIMARY KEY, ts TEXT, action TEXT, details TEXT
        );
        """)
        self.conn.commit()

    def log(self, action, details=""):
        self.conn.execute("INSERT INTO history VALUES(?,?,?,?)",
            (new_id(), now_iso(), action, details))
        self.conn.commit()

    # --- nodes ---
    def add_node(self, n):
        self.conn.execute("""INSERT OR REPLACE INTO nodes
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (n["id"], n["name"], n["type"], n.get("description",""),
             ",".join(n.get("tags",[])), n.get("created", now_iso()),
             n.get("source",""), n.get("x",0), n.get("y",0),
             json.dumps(n.get("custom_fields",{})), n.get("notes",""),
             json.dumps(n.get("attachments",[]))))
        self.conn.commit()

    def update_node(self, n):
        self.add_node(n)

    def delete_node(self, nid):
        self.conn.execute("DELETE FROM nodes WHERE id=?", (nid,))
        self.conn.execute("DELETE FROM edges WHERE src=? OR dst=?", (nid, nid))
        self.conn.commit()

    def all_nodes(self):
        rows = self.conn.execute("SELECT * FROM nodes").fetchall()
        out = []
        for r in rows:
            out.append({
                "id":r[0],"name":r[1],"type":r[2],"description":r[3],
                "tags": r[4].split(",") if r[4] else [],
                "created":r[5],"source":r[6],"x":r[7],"y":r[8],
                "custom_fields": json.loads(r[9]) if r[9] else {},
                "notes": r[10] or "", "attachments": json.loads(r[11]) if r[11] else []
            })
        return out

    def get_node(self, nid):
        for n in self.all_nodes():
            if n["id"] == nid: return n
        return None

    # --- edges ---
    def add_edge(self, src, dst, rel_type="related", weight=1):
        eid = new_id()
        self.conn.execute("INSERT INTO edges VALUES(?,?,?,?,?,?)",
            (eid, src, dst, rel_type, now_iso(), weight))
        self.conn.commit()
        return eid

    def delete_edge(self, eid):
        self.conn.execute("DELETE FROM edges WHERE id=?", (eid,))
        self.conn.commit()

    def all_edges(self):
        rows = self.conn.execute("SELECT * FROM edges").fetchall()
        return [{"id":r[0],"src":r[1],"dst":r[2],"rel_type":r[3],
                 "created":r[4],"weight":r[5]} for r in rows]

    def clear_all(self):
        self.conn.execute("DELETE FROM nodes")
        self.conn.execute("DELETE FROM edges")
        self.conn.commit()

# ---------------------------------------------------------------
# ANALYSIS ENGINE
# ---------------------------------------------------------------
class Analyzer:
    def __init__(self, db): self.db = db

    def build_adj(self):
        adj = {}
        for n in self.db.all_nodes(): adj[n["id"]] = set()
        for e in self.db.all_edges():
            adj.setdefault(e["src"], set()).add(e["dst"])
            adj.setdefault(e["dst"], set()).add(e["src"])
        return adj

    def duplicate_detection(self):
        nodes = self.db.all_nodes()
        seen, dups = {}, []
        for n in nodes:
            key = (n["name"].strip().lower(), n["type"])
            if key in seen: dups.append((seen[key], n["id"]))
            else: seen[key] = n["id"]
        return dups

    def keyword_search(self, keyword):
        keyword = keyword.lower()
        res = []
        for n in self.db.all_nodes():
            blob = " ".join([n["name"], n["description"], " ".join(n["tags"]), n["notes"]]).lower()
            if keyword in blob: res.append(n)
        return res

    def similarity(self, a, b):
        sa = set(a["tags"]) | set(a["name"].lower().split())
        sb = set(b["tags"]) | set(b["name"].lower().split())
        if not sa or not sb: return 0.0
        return len(sa & sb) / len(sa | sb)

    def importance_ranking(self):
        adj = self.build_adj()
        ranked = sorted(adj.items(), key=lambda kv: -len(kv[1]))
        return [(nid, len(neigh)) for nid, neigh in ranked]

    def connection_count(self, nid):
        return len(self.build_adj().get(nid, set()))

    def path_find(self, src, dst):
        adj = self.build_adj()
        if src not in adj or dst not in adj: return None
        visited = {src: None}
        queue = [src]
        while queue:
            cur = queue.pop(0)
            if cur == dst: break
            for nb in adj[cur]:
                if nb not in visited:
                    visited[nb] = cur
                    queue.append(nb)
        if dst not in visited: return None
        path, cur = [], dst
        while cur is not None:
            path.append(cur); cur = visited[cur]
        return list(reversed(path))

    def clusters(self):
        adj = self.build_adj()
        seen, groups = set(), []
        for nid in adj:
            if nid in seen: continue
            stack, comp = [nid], []
            while stack:
                cur = stack.pop()
                if cur in seen: continue
                seen.add(cur); comp.append(cur)
                stack.extend(adj[cur] - seen)
            groups.append(comp)
        return groups

# ---------------------------------------------------------------
# IMPORT SYSTEM
# ---------------------------------------------------------------
class Importer:
    def __init__(self, db, log_fn): self.db, self.log = db, log_fn

    def _mk_node(self, name, ntype, desc="", source="", tags=None, x=None, y=None):
        n = {"id": new_id(), "name": name, "type": ntype, "description": desc,
             "tags": tags or [], "created": now_iso(), "source": source,
             "x": x if x is not None else random.randint(100,900),
             "y": y if y is not None else random.randint(100,700),
             "custom_fields": {}, "notes": "", "attachments": []}
        self.db.add_node(n)
        return n

    def import_file(self, path):
        try:
            size = os.path.getsize(path)
            h = hashlib.sha256()
            with open(path,"rb") as f:
                for chunk in iter(lambda: f.read(65536), b""): h.update(chunk)
            n = self._mk_node(os.path.basename(path), "File",
                desc=f"Size: {size} bytes", source=path,
                tags=[pathlib.Path(path).suffix.lstrip(".") or "file"])
            n["custom_fields"] = {"sha256": h.hexdigest(), "size": size}
            self.db.update_node(n)
            self.log(f"Imported file: {path}")
            return n
        except Exception as e:
            self.log(f"Import error: {e}")
            return None

    def import_folder(self, path):
        root = self._mk_node(os.path.basename(path.rstrip("/\\")) or path,
                              "Folder", source=path)
        count = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for fn in filenames:
                if count > 400: break
                fp = os.path.join(dirpath, fn)
                fnode = self.import_file(fp)
                if fnode:
                    self.db.add_edge(root["id"], fnode["id"], "contains")
                    count += 1
            if count > 400: break
        self.log(f"Imported folder ({count} files): {path}")
        return root

    def import_csv(self, path):
        created = []
        with open(path, newline="", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i > 500: break
                name = row.get("name") or row.get("Name") or f"Row-{i}"
                desc = json.dumps(row, ensure_ascii=False)
                n = self._mk_node(str(name), "Custom", desc=desc, source=path)
                created.append(n)
        self.log(f"Imported CSV ({len(created)} rows): {path}")
        return created

    def import_json(self, path):
        with open(path, encoding="utf-8") as f: data = json.load(f)
        created = []
        items = data if isinstance(data, list) else [data]
        for i, item in enumerate(items):
            if i > 500: break
            name = item.get("name") if isinstance(item, dict) else str(item)
            n = self._mk_node(str(name or f"Item-{i}"), "Custom",
                               desc=json.dumps(item, ensure_ascii=False), source=path)
            created.append(n)
        self.log(f"Imported JSON ({len(created)} items): {path}")
        return created

    def import_url(self, url):
        n = self._mk_node(url, "Website", desc="Imported URL", source=url,
                           tags=[url.split("/")[2]] if "://" in url else [])
        self.log(f"Imported URL: {url}")
        return n

# ---------------------------------------------------------------
# EXPORT SYSTEM
# ---------------------------------------------------------------
class Exporter:
    def __init__(self, db): self.db = db

    def export_json(self, path):
        data = {"nodes": self.db.all_nodes(), "edges": self.db.all_edges(),
                "exported": now_iso()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def export_csv(self, path):
        nodes = self.db.all_nodes()
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id","name","type","description","tags","created","source"])
            for n in nodes:
                w.writerow([n["id"], n["name"], n["type"], n["description"],
                            ";".join(n["tags"]), n["created"], n["source"]])

    def export_text(self, path):
        nodes, edges = self.db.all_nodes(), self.db.all_edges()
        with open(path, "w", encoding="utf-8") as f:
            f.write("SR LINK — TEXT REPORT\nGenerated: %s\n\n" % now_iso())
            f.write("NODES (%d)\n" % len(nodes) + "-"*40 + "\n")
            for n in nodes:
                f.write(f"[{n['type']}] {n['name']} ({n['id']})\n  {n['description']}\n")
            f.write("\nRELATIONSHIPS (%d)\n" % len(edges) + "-"*40 + "\n")
            id2name = {n["id"]: n["name"] for n in nodes}
            for e in edges:
                f.write(f"{id2name.get(e['src'],'?')} --[{e['rel_type']}]--> {id2name.get(e['dst'],'?')}\n")

    def export_html(self, path):
        nodes, edges = self.db.all_nodes(), self.db.all_edges()
        id2 = {n["id"]: n for n in nodes}
        rows = "".join(
            f"<tr><td style='color:{TYPE_COLORS.get(n['type'],'#fff')}'>{n['type']}</td>"
            f"<td>{n['name']}</td><td>{n['description']}</td>"
            f"<td>{','.join(n['tags'])}</td></tr>" for n in nodes)
        erows = "".join(
            f"<tr><td>{id2.get(e['src'],{}).get('name','?')}</td>"
            f"<td>{e['rel_type']}</td>"
            f"<td>{id2.get(e['dst'],{}).get('name','?')}</td></tr>" for e in edges)
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>SR Link Report</title>
<style>
body{{background:#050505;color:#eee;font-family:Segoe UI,Tahoma,sans-serif;padding:30px}}
h1{{border-bottom:1px solid #333;padding-bottom:10px}}
table{{width:100%;border-collapse:collapse;margin:20px 0}}
td,th{{border:1px solid #222;padding:6px 10px;font-size:13px}}
th{{background:#111;text-align:left}}
tr:hover{{background:#0f0f0f}}
</style></head><body>
<h1>SR Link — Intelligence Report</h1>
<p>Generated: {now_iso()} | Nodes: {len(nodes)} | Relationships: {len(edges)}</p>
<h2>Nodes</h2>
<table><tr><th>Type</th><th>Name</th><th>Description</th><th>Tags</th></tr>{rows}</table>
<h2>Relationships</h2>
<table><tr><th>Source</th><th>Type</th><th>Target</th></tr>{erows}</table>
</body></html>"""
        with open(path, "w", encoding="utf-8") as f: f.write(html)

# ---------------------------------------------------------------
# GRAPH CANVAS ENGINE
# ---------------------------------------------------------------
class GraphCanvas(tk.Canvas):
    def __init__(self, master, app, **kw):
        super().__init__(master, bg=BG, highlightthickness=0, **kw)
        self.app = app
        self.db = app.db
        self.scale = 1.0
        self.offset = [0, 0]
        self.node_items = {}   # nid -> canvas item ids dict
        self.edge_items = {}   # eid -> line id
        self.selected = set()
        self.drag_data = {"nid": None, "x": 0, "y": 0}
        self.pan_data = {"x": 0, "y": 0, "active": False}
        self.connect_mode = False
        self.connect_first = None
        self.rubber = None
        self.rubber_start = None

        self.bind("<ButtonPress-1>", self.on_press)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<ButtonPress-3>", self.on_right_click)
        self.bind("<ButtonPress-2>", self.start_pan)
        self.bind("<B2-Motion>", self.do_pan)
        self.bind("<MouseWheel>", self.on_zoom)
        self.bind("<Button-4>", lambda e: self.on_zoom(e, 1))
        self.bind("<Button-5>", lambda e: self.on_zoom(e, -1))

    def world(self, x, y):
        return (x * self.scale + self.offset[0], y * self.scale + self.offset[1])

    def to_world(self, sx, sy):
        return ((sx - self.offset[0]) / self.scale, (sy - self.offset[1]) / self.scale)

    def redraw(self):
        self.delete("all")
        self.node_items.clear(); self.edge_items.clear()
        nodes = {n["id"]: n for n in self.db.all_nodes()}
        for e in self.db.all_edges():
            if e["src"] in nodes and e["dst"] in nodes:
                self._draw_edge(nodes[e["src"]], nodes[e["dst"]], e)
        for n in nodes.values():
            self._draw_node(n)

    def _draw_edge(self, a, b, e):
        x1, y1 = self.world(a["x"], a["y"])
        x2, y2 = self.world(b["x"], b["y"])
        mx, my = (x1+x2)/2, (y1+y2)/2 - 40*self.scale
        # glow layers
        for w, col in [(6, "#1a1a1a"), (3, "#3a3a3a"), (1, "#cfcfcf")]:
            lid = self.create_line(x1, y1, mx, my, x2, y2,
                smooth=True, splinesteps=24, width=w, fill=col,
                arrow=tk.LAST if col == "#cfcfcf" else None, tags=("edge",))
        self.edge_items[e["id"]] = lid
        lx, ly = mx, my - 8
        self.create_text(lx, ly, text=e["rel_type"], fill=FG_DIM,
                          font=("Segoe UI", 8), tags=("edge_label",))

    def _draw_node(self, n):
        x, y = self.world(n["x"], n["y"])
        r = 22 * self.scale
        color = TYPE_COLORS.get(n["type"], "#ffffff")
        outline = "#ffffff" if n["id"] in self.selected else color
        glow = self.create_oval(x-r-6, y-r-6, x+r+6, y+r+6,
                                 outline="", fill="", tags=("node", n["id"]))
        for gr, alpha_col in [(r+10, "#151515"), (r+4, "#1f1f1f")]:
            self.create_oval(x-gr, y-gr, x+gr, y+gr, outline="", fill=alpha_col,
                              tags=("node", n["id"]))
        body = self.create_oval(x-r, y-r, x+r, y+r, fill="#000000",
                                 outline=outline, width=2, tags=("node", n["id"], "body"))
        label = self.create_text(x, y, text=n["type"][:2].upper(), fill=color,
                                  font=("Consolas", 9, "bold"), tags=("node", n["id"]))
        name_lbl = self.create_text(x, y+r+12, text=n["name"][:22], fill=FG,
                                     font=("Segoe UI", 9), tags=("node", n["id"], "name"))
        self.node_items[n["id"]] = {"body": body, "label": label, "name": name_lbl, "r": r}

    def find_node_at(self, sx, sy):
        items = self.find_overlapping(sx-2, sy-2, sx+2, sy+2)
        for it in items:
            tags = self.gettags(it)
            for t in tags:
                if t in self.node_items:
                    return t
        return None

    def on_press(self, ev):
        nid = self.find_node_at(ev.x, ev.y)
        if self.connect_mode:
            if nid:
                if self.connect_first is None:
                    self.connect_first = nid
                    self.app.log(f"Select target node to connect from {nid[:6]}")
                else:
                    rel = simpledialog.askstring("Relationship", "Relationship type:",
                                                  initialvalue="related")
                    if rel:
                        self.db.add_edge(self.connect_first, nid, rel)
                        self.app.log(f"Linked {self.connect_first[:6]} -> {nid[:6]} ({rel})")
                    self.connect_first = None
                    self.connect_mode = False
                    self.redraw()
            return
        if nid:
            if not (ev.state & 0x0001):  # no shift
                self.selected = {nid}
            else:
                self.selected.symmetric_difference_update({nid})
            self.drag_data = {"nid": nid, "x": ev.x, "y": ev.y}
            self.app.show_properties(nid)
            self.redraw()
        else:
            self.selected.clear()
            self.rubber_start = (ev.x, ev.y)
            self.redraw()

    def on_drag(self, ev):
        if self.drag_data["nid"]:
            nid = self.drag_data["nid"]
            dx = (ev.x - self.drag_data["x"]) / self.scale
            dy = (ev.y - self.drag_data["y"]) / self.scale
            n = self.db.get_node(nid)
            n["x"] += dx; n["y"] += dy
            self.db.update_node(n)
            self.drag_data["x"], self.drag_data["y"] = ev.x, ev.y
            self.redraw()
        elif self.rubber_start:
            x0, y0 = self.rubber_start
            if self.rubber: self.delete(self.rubber)
            self.rubber = self.create_rectangle(x0, y0, ev.x, ev.y,
                                                 outline="#666666", dash=(3,2))

    def on_release(self, ev):
        if self.rubber_start and not self.drag_data["nid"]:
            x0, y0 = self.rubber_start
            x1, y1 = ev.x, ev.y
            box = (min(x0,x1), min(y0,y1), max(x0,x1), max(y0,y1))
            for nid, items in self.node_items.items():
                n = self.db.get_node(nid)
                sx, sy = self.world(n["x"], n["y"])
                if box[0] <= sx <= box[2] and box[1] <= sy <= box[3]:
                    self.selected.add(nid)
        self.drag_data = {"nid": None, "x": 0, "y": 0}
        self.rubber_start = None
        if self.rubber: self.delete(self.rubber); self.rubber = None
        self.redraw()

    def on_right_click(self, ev):
        nid = self.find_node_at(ev.x, ev.y)
        menu = tk.Menu(self, tearoff=0, bg=PANEL_BG2, fg=FG)
        if nid:
            menu.add_command(label="Edit", command=lambda: self.app.show_properties(nid))
            menu.add_command(label="Delete", command=lambda: self.app.delete_node(nid))
            menu.add_command(label="Start connection", command=lambda: self.start_connect(nid))
            menu.add_command(label="Find shortest path from...", command=lambda: self.app.pick_path_target(nid))
        else:
            menu.add_command(label="Create node here", command=lambda: self.app.create_node_at(*self.to_world(ev.x, ev.y)))
        menu.tk_popup(ev.x_root, ev.y_root)

    def start_connect(self, nid):
        self.connect_mode = True
        self.connect_first = nid

    def start_pan(self, ev):
        self.pan_data = {"x": ev.x, "y": ev.y, "active": True}

    def do_pan(self, ev):
        if self.pan_data["active"]:
            dx = ev.x - self.pan_data["x"]; dy = ev.y - self.pan_data["y"]
            self.offset[0] += dx; self.offset[1] += dy
            self.pan_data["x"], self.pan_data["y"] = ev.x, ev.y
            self.redraw()

    def on_zoom(self, ev, direction=None):
        d = direction if direction is not None else (1 if ev.delta > 0 else -1)
        factor = 1.1 if d > 0 else 0.9
        self.scale = max(0.2, min(3.0, self.scale * factor))
        self.redraw()

    def highlight_path(self, path_ids):
        self.selected = set(path_ids)
        self.redraw()

# ---------------------------------------------------------------
# MAIN APPLICATION
# ---------------------------------------------------------------
class SRLinkApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1500x900")
        self.root.configure(bg=BG)
        self.db = DB()
        self.analyzer = Analyzer(self.db)
        self.importer = Importer(self.db, self.log)
        self.exporter = Exporter(self.db)
        self.current_node = None
        self._style()
        self._build_ui()
        self.graph.redraw()
        self.log("SR Link initialized. Ready.")

    def _style(self):
        style = ttk.Style()
        try: style.theme_use("clam")
        except: pass
        style.configure("TFrame", background=PANEL_BG)
        style.configure("TLabel", background=PANEL_BG, foreground=FG, font=("Segoe UI", 9))
        style.configure("Head.TLabel", background=PANEL_BG, foreground=ACCENT, font=("Segoe UI", 10, "bold"))
        style.configure("TButton", background=PANEL_BG2, foreground=FG, font=("Segoe UI", 9), borderwidth=1)
        style.map("TButton", background=[("active", "#222222")])
        style.configure("TEntry", fieldbackground="#111111", foreground=FG)
        style.configure("Treeview", background="#0a0a0a", fieldbackground="#0a0a0a",
                         foreground=FG, borderwidth=0)
        style.configure("Treeview.Heading", background=PANEL_BG2, foreground=FG)
        style.map("Treeview", background=[("selected", "#2a2a2a")])
        style.configure("TCombobox", fieldbackground="#111111", foreground=FG)
        style.configure("TNotebook", background=PANEL_BG)
        style.configure("TNotebook.Tab", background=PANEL_BG2, foreground=FG)

    def _build_ui(self):
        # Toolbar
        toolbar = tk.Frame(self.root, bg=PANEL_BG2, height=42)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        actions = [
            ("New Project", self.new_project), ("Open", self.open_project),
            ("Save", self.save_project), ("Import Data", self.import_menu),
            ("Create Node", self.create_node_dialog), ("Connect Nodes", self.enable_connect_mode),
            ("Search", self.open_search), ("Analyze", self.open_analyze_menu),
            ("Export", self.open_export_menu)
        ]
        for text, cmd in actions:
            b = tk.Button(toolbar, text=text, command=cmd, bg=PANEL_BG2, fg=FG,
                          activebackground="#222222", activeforeground="#fff",
                          relief=tk.FLAT, font=("Segoe UI", 9), padx=10, pady=8,
                          bd=0, highlightthickness=0)
            b.pack(side=tk.LEFT, padx=2, pady=2)

        main = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=BG, sashwidth=3)
        main.pack(fill=tk.BOTH, expand=True)

        # LEFT PANEL
        left = tk.Frame(main, bg=PANEL_BG, width=260)
        main.add(left, minsize=220)
        ttk.Label(left, text="DATA SOURCES", style="Head.TLabel").pack(anchor="w", padx=10, pady=(10,4))
        self.tree = ttk.Treeview(left, show="tree")
        self.tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self.tree.bind("<Double-1>", self.on_tree_select)
        ttk.Label(left, text="TOOLS", style="Head.TLabel").pack(anchor="w", padx=10, pady=(10,4))
        for txt, cmd in [("Refresh List", self.refresh_tree),
                          ("Duplicate Scan", self.run_duplicate_scan),
                          ("Importance Ranking", self.run_importance),
                          ("Cluster Detection", self.run_clusters)]:
            ttk.Button(left, text=txt, command=cmd).pack(fill=tk.X, padx=8, pady=2)

        # CENTER: graph + bottom log
        center = tk.Frame(main, bg=BG)
        main.add(center, minsize=600)
        self.graph = GraphCanvas(center, self)
        self.graph.pack(fill=tk.BOTH, expand=True)

        bottom = tk.Frame(center, bg=PANEL_BG2, height=140)
        bottom.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Label(bottom, text="CONSOLE / LOG", style="Head.TLabel").pack(anchor="w", padx=8, pady=(4,0))
        self.console = tk.Text(bottom, height=7, bg="#080808", fg="#8fe38f",
                                insertbackground=FG, font=("Consolas", 9), bd=0)
        self.console.pack(fill=tk.X, padx=8, pady=4)
        self.status = tk.Label(bottom, text="Ready", bg=PANEL_BG2, fg=FG_DIM, anchor="w")
        self.status.pack(fill=tk.X, padx=8, pady=(0,4))

        # RIGHT PANEL
        right = tk.Frame(main, bg=PANEL_BG, width=320)
        main.add(right, minsize=280)
        ttk.Label(right, text="PROPERTIES / METADATA", style="Head.TLabel").pack(anchor="w", padx=10, pady=(10,4))
        form = tk.Frame(right, bg=PANEL_BG)
        form.pack(fill=tk.X, padx=10)

        self.f_name = self._form_entry(form, "Name")
        self.f_type = ttk.Combobox(form, values=NODE_TYPES, state="readonly")
        ttk.Label(form, text="Type").pack(anchor="w"); self.f_type.pack(fill=tk.X, pady=(0,6))
        self.f_desc = self._form_text(form, "Description", h=4)
        self.f_tags = self._form_entry(form, "Tags (comma separated)")
        self.f_source = self._form_entry(form, "Source Location")
        self.f_notes = self._form_text(form, "Notes", h=4)
        self.f_custom = self._form_text(form, "Custom Fields (JSON)", h=3)

        btnrow = tk.Frame(right, bg=PANEL_BG); btnrow.pack(fill=tk.X, padx=10, pady=8)
        ttk.Button(btnrow, text="Save Changes", command=self.save_properties).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(btnrow, text="Delete Node", command=self.delete_current).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        ttk.Label(right, text="LINKED OBJECTS", style="Head.TLabel").pack(anchor="w", padx=10, pady=(10,4))
        self.linked_list = tk.Listbox(right, bg="#0a0a0a", fg=FG, bd=0, height=8,
                                       highlightthickness=0)
        self.linked_list.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        self.refresh_tree()

    def _form_entry(self, parent, label):
        ttk.Label(parent, text=label).pack(anchor="w")
        e = tk.Entry(parent, bg="#111111", fg=FG, insertbackground=FG, relief=tk.FLAT)
        e.pack(fill=tk.X, pady=(0,6))
        return e

    def _form_text(self, parent, label, h=3):
        ttk.Label(parent, text=label).pack(anchor="w")
        t = tk.Text(parent, height=h, bg="#111111", fg=FG, insertbackground=FG, relief=tk.FLAT)
        t.pack(fill=tk.X, pady=(0,6))
        return t

    # ---------------- logging ----------------
    def log(self, msg):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.console.insert(tk.END, f"[{ts}] {msg}\n")
        self.console.see(tk.END)
        self.status.config(text=msg)
        self.db.log("LOG", msg)

    # ---------------- tree ----------------
    def refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        groups = {}
        for n in self.db.all_nodes():
            groups.setdefault(n["type"], []).append(n)
        for t, items in groups.items():
            parent = self.tree.insert("", "end", text=f"{t} ({len(items)})", open=False)
            for n in items:
                self.tree.insert(parent, "end", text=n["name"], iid=n["id"])

    def on_tree_select(self, ev):
        sel = self.tree.selection()
        if sel and self.db.get_node(sel[0]):
            self.show_properties(sel[0])

    # ---------------- node CRUD ----------------
    def create_node_dialog(self):
        name = simpledialog.askstring("New Node", "Node name:")
        if not name: return
        self.create_node_at(random.randint(150,850), random.randint(150,650), name)

    def create_node_at(self, x, y, name=None):
        name = name or simpledialog.askstring("New Node", "Node name:")
        if not name: return
        ntype = simpledialog.askstring("Node Type", f"Type ({'/'.join(NODE_TYPES)}):",
                                        initialvalue="Custom") or "Custom"
        if ntype not in NODE_TYPES: ntype = "Custom"
        n = {"id": new_id(), "name": name, "type": ntype, "description": "",
             "tags": [], "created": now_iso(), "source": "", "x": x, "y": y,
             "custom_fields": {}, "notes": "", "attachments": []}
        self.db.add_node(n)
        self.log(f"Created node: {name} ({ntype})")
        self.refresh_tree(); self.graph.redraw()

    def show_properties(self, nid):
        n = self.db.get_node(nid)
        if not n: return
        self.current_node = nid
        self.f_name.delete(0, tk.END); self.f_name.insert(0, n["name"])
        self.f_type.set(n["type"])
        self.f_desc.delete("1.0", tk.END); self.f_desc.insert("1.0", n["description"])
        self.f_tags.delete(0, tk.END); self.f_tags.insert(0, ",".join(n["tags"]))
        self.f_source.delete(0, tk.END); self.f_source.insert(0, n["source"])
        self.f_notes.delete("1.0", tk.END); self.f_notes.insert("1.0", n["notes"])
        self.f_custom.delete("1.0", tk.END)
        self.f_custom.insert("1.0", json.dumps(n["custom_fields"], ensure_ascii=False, indent=2))
        self.linked_list.delete(0, tk.END)
        for e in self.db.all_edges():
            if e["src"] == nid or e["dst"] == nid:
                other = e["dst"] if e["src"] == nid else e["src"]
                on = self.db.get_node(other)
                if on: self.linked_list.insert(tk.END, f"[{e['rel_type']}] {on['name']}")

    def save_properties(self):
        if not self.current_node: return
        n = self.db.get_node(self.current_node)
        if not n: return
        n["name"] = self.f_name.get()
        n["type"] = self.f_type.get() or n["type"]
        n["description"] = self.f_desc.get("1.0", tk.END).strip()
        n["tags"] = [t.strip() for t in self.f_tags.get().split(",") if t.strip()]
        n["source"] = self.f_source.get()
        n["notes"] = self.f_notes.get("1.0", tk.END).strip()
        try:
            n["custom_fields"] = json.loads(self.f_custom.get("1.0", tk.END) or "{}")
        except Exception:
            self.log("Custom fields JSON invalid, kept previous value.")
        self.db.update_node(n)
        self.log(f"Saved changes: {n['name']}")
        self.refresh_tree(); self.graph.redraw()

    def delete_current(self):
        if self.current_node: self.delete_node(self.current_node)

    def delete_node(self, nid):
        n = self.db.get_node(nid)
        if n and messagebox.askyesno("Delete", f"Delete node '{n['name']}'?"):
            self.db.delete_node(nid)
            self.log(f"Deleted node: {n['name']}")
            self.refresh_tree(); self.graph.redraw()

    def enable_connect_mode(self):
        self.graph.connect_mode = True
        self.graph.connect_first = None
        self.log("Connect mode: click source node, then target node.")

    def pick_path_target(self, src):
        dst_name = simpledialog.askstring("Path Finding", "Target node name:")
        if not dst_name: return
        for n in self.db.all_nodes():
            if n["name"].lower() == dst_name.lower():
                path = self.analyzer.path_find(src, n["id"])
                if path:
                    self.graph.highlight_path(path)
                    self.log(f"Path found ({len(path)} hops).")
                else:
                    self.log("No path found.")
                return
        self.log("Target node not found.")

    # ---------------- project I/O ----------------
    def new_project(self):
        if messagebox.askyesno("New Project", "Clear current graph and start new project?"):
            self.db.clear_all()
            self.refresh_tree(); self.graph.redraw()
            self.log("New project started.")

    def save_project(self):
        path = filedialog.asksaveasfilename(defaultextension=".srlink",
                                             filetypes=[("SR Link Project","*.srlink")])
        if not path: return
        data = {"nodes": self.db.all_nodes(), "edges": self.db.all_edges()}
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        if messagebox.askyesno("Encrypt", "Encrypt project file?"):
            pwd = simpledialog.askstring("Password", "Enter password:", show="*") or "srlink"
            raw = self._xor_crypt(raw, pwd)
            with open(path, "wb") as f: f.write(b"SRLE" + raw)
        else:
            with open(path, "wb") as f: f.write(b"SRLP" + raw)
        self.log(f"Project saved: {path}")

    def open_project(self):
        path = filedialog.askopenfilename(filetypes=[("SR Link Project","*.srlink")])
        if not path: return
        with open(path, "rb") as f: raw = f.read()
        header, body = raw[:4], raw[4:]
        if header == b"SRLE":
            pwd = simpledialog.askstring("Password", "Enter password:", show="*") or "srlink"
            body = self._xor_crypt(body, pwd)
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            self.log("Failed to open project (wrong password or corrupt file).")
            return
        self.db.clear_all()
        for n in data.get("nodes", []): self.db.add_node(n)
        for e in data.get("edges", []):
            self.db.add_edge(e["src"], e["dst"], e["rel_type"], e.get("weight",1))
        self.refresh_tree(); self.graph.redraw()
        self.log(f"Project loaded: {path}")

    @staticmethod
    def _xor_crypt(data, password):
        key = hashlib.sha256(password.encode("utf-8")).digest()
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))

    # ---------------- import ----------------
    def import_menu(self):
        menu = tk.Menu(self.root, tearoff=0, bg=PANEL_BG2, fg=FG)
        menu.add_command(label="Import File(s)...", command=self._imp_files)
        menu.add_command(label="Import Folder...", command=self._imp_folder)
        menu.add_command(label="Import CSV...", command=self._imp_csv)
        menu.add_command(label="Import JSON...", command=self._imp_json)
        menu.add_command(label="Import URL...", command=self._imp_url)
        menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())

    def _imp_files(self):
        paths = filedialog.askopenfilenames()
        for p in paths: self.importer.import_file(p)
        self.refresh_tree(); self.graph.redraw()

    def _imp_folder(self):
        path = filedialog.askdirectory()
        if path:
            def worker():
                self.importer.import_folder(path)
                self.root.after(0, lambda: (self.refresh_tree(), self.graph.redraw()))
            threading.Thread(target=worker, daemon=True).start()

    def _imp_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV","*.csv")])
        if path:
            self.importer.import_csv(path)
            self.refresh_tree(); self.graph.redraw()

    def _imp_json(self):
        path = filedialog.askopenfilename(filetypes=[("JSON","*.json")])
        if path:
            self.importer.import_json(path)
            self.refresh_tree(); self.graph.redraw()

    def _imp_url(self):
        url = simpledialog.askstring("Import URL", "Enter URL:")
        if url:
            self.importer.import_url(url)
            self.refresh_tree(); self.graph.redraw()

    # ---------------- search ----------------
    def open_search(self):
        win = tk.Toplevel(self.root, bg=PANEL_BG)
        win.title("Search")
        win.geometry("420x420")
        ttk.Label(win, text="Keyword").pack(anchor="w", padx=10, pady=(10,0))
        e = tk.Entry(win, bg="#111111", fg=FG, relief=tk.FLAT)
        e.pack(fill=tk.X, padx=10, pady=4)
        lb = tk.Listbox(win, bg="#0a0a0a", fg=FG, bd=0)
        lb.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)

        def do_search():
            lb.delete(0, tk.END)
            res = self.analyzer.keyword_search(e.get())
            for n in res:
                lb.insert(tk.END, f"[{n['type']}] {n['name']} — {n['id']}")
        ttk.Button(win, text="Search", command=do_search).pack(fill=tk.X, padx=10, pady=4)

        def jump(ev):
            sel = lb.curselection()
            if sel:
                nid = lb.get(sel[0]).split("—")[-1].strip()
                self.show_properties(nid)
        lb.bind("<Double-1>", jump)

    # ---------------- analyze ----------------
    def open_analyze_menu(self):
        menu = tk.Menu(self.root, tearoff=0, bg=PANEL_BG2, fg=FG)
        menu.add_command(label="Duplicate Detection", command=self.run_duplicate_scan)
        menu.add_command(label="Importance Ranking", command=self.run_importance)
        menu.add_command(label="Cluster Detection", command=self.run_clusters)
        menu.add_command(label="Similarity Matrix (top pairs)", command=self.run_similarity)
        menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())

    def run_duplicate_scan(self):
        dups = self.analyzer.duplicate_detection()
        self.log(f"Duplicate scan complete: {len(dups)} potential duplicate pairs.")
        for a, b in dups[:20]:
            na, nb = self.db.get_node(a), self.db.get_node(b)
            if na and nb: self.log(f"  Possible duplicate: {na['name']} <-> {nb['name']}")

    def run_importance(self):
        ranking = self.analyzer.importance_ranking()[:15]
        self.log("Top nodes by network importance:")
        for nid, deg in ranking:
            n = self.db.get_node(nid)
            if n: self.log(f"  {n['name']} — connections: {deg}")

    def run_clusters(self):
        cl = self.analyzer.clusters()
        self.log(f"Cluster detection complete: {len(cl)} clusters found.")
        for i, comp in enumerate(cl[:10]):
            self.log(f"  Cluster {i+1}: {len(comp)} nodes")

    def run_similarity(self):
        nodes = self.db.all_nodes()
        pairs = []
        for i in range(len(nodes)):
            for j in range(i+1, len(nodes)):
                s = self.analyzer.similarity(nodes[i], nodes[j])
                if s > 0: pairs.append((s, nodes[i]["name"], nodes[j]["name"]))
        pairs.sort(reverse=True)
        self.log("Top similar node pairs:")
        for s, a, b in pairs[:15]:
            self.log(f"  {a} ~ {b}  (score {s:.2f})")

    # ---------------- export ----------------
    def open_export_menu(self):
        menu = tk.Menu(self.root, tearoff=0, bg=PANEL_BG2, fg=FG)
        menu.add_command(label="Export JSON", command=lambda: self._export("json"))
        menu.add_command(label="Export CSV", command=lambda: self._export("csv"))
        menu.add_command(label="Export HTML Report", command=lambda: self._export("html"))
        menu.add_command(label="Export Text Report", command=lambda: self._export("txt"))
        menu.add_command(label="Export Graph Snapshot (PS)", command=self._export_snapshot)
        menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())

    def _export(self, kind):
        ext = {"json": ".json", "csv": ".csv", "html": ".html", "txt": ".txt"}[kind]
        path = filedialog.asksaveasfilename(defaultextension=ext)
        if not path: return
        if kind == "json": self.exporter.export_json(path)
        elif kind == "csv": self.exporter.export_csv(path)
        elif kind == "html": self.exporter.export_html(path)
        elif kind == "txt": self.exporter.export_text(path)
        self.log(f"Exported {kind.upper()} -> {path}")
        if kind == "html" and messagebox.askyesno("Open", "Open report in browser?"):
            webbrowser.open(f"file://{os.path.abspath(path)}")

    def _export_snapshot(self):
        path = filedialog.asksaveasfilename(defaultextension=".ps")
        if not path: return
        self.graph.postscript(file=path)
        self.log(f"Graph snapshot exported: {path}")

# ---------------------------------------------------------------
def main():
    root = tk.Tk()
    app = SRLinkApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
