#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔥 FÒRUM DE LA FORJA NOVA — Servidor API
==========================================
Servidor HTTP per al fòrum de la comunitat de Latvèria.
Organitzat pels Cinc Pilars: Respecte, Veritat, Seny, Comunitat, Memòria.

Arquitecte: GAUDÍ
Cronista: BERNAT
Aprovat per: Sant Miquel Mechanicus
Port: 8082

FOC I FERRO, CARN I CODI — però ara amb COR.
"""

import json
import os
import html
import re
import sys
import threading
import socketserver
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from urllib.parse import urlparse, parse_qs

# ThreadingHTTPServer compatible amb totes les versions de Python
class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True

# Rutes
DATA_JSON = Path(__file__).parent / "foro_forja_nova_data.json"
HTML_FILE = Path(__file__).parent / "foro_forja_nova.html"
PORT = int(os.environ.get('PORT', 8082))

# Lock per escriptura concurrent
data_lock = threading.Lock()


def load_data():
    """Carrega les dades del fòrum des del JSON."""
    with open(DATA_JSON, 'r', encoding='utf-8-sig') as f:
        return json.load(f)


def save_data(data):
    """Guarda les dades del fòrum al JSON amb file locking."""
    with data_lock:
        with open(DATA_JSON, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def sanitize_text(text):
    """Sanititza text d'entrada per prevenir XSS."""
    if not isinstance(text, str):
        return ""
    text = html.escape(text, quote=True)
    # Limitar longitud
    return text[:5000]


def validate_agent_id(agent_id, data):
    """Valida que l'agent_id existeix a la llista d'agents."""
    return any(a['id'] == agent_id for a in data['agents'])


class ForumHandler(BaseHTTPRequestHandler):
    """Handler per al Fòrum de la Forja Nova."""

    def send_json(self, data, status=200):
        """Envia resposta JSON amb CORS headers."""
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2, ensure_ascii=False).encode('utf-8'))

    def send_html(self, content):
        """Envia resposta HTML."""
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(content.encode('utf-8'))

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        """Processa peticions GET."""
        parsed = urlparse(self.path)
        path = parsed.path

        # Servir HTML principal
        if path == '/' or path == '/index.html':
            if HTML_FILE.exists():
                with open(HTML_FILE, 'r', encoding='utf-8') as f:
                    self.send_html(f.read())
            else:
                self.send_json({"error": "HTML del fòrum no trobat"}, 404)
            return

        # API: Llista de categories (5 Pilars)
        if path == '/api/categories':
            data = load_data()
            categories = []
            for cat in data['categories']:
                thread_count = len([t for t in data['threads'] if t['categoria_id'] == cat['id']])
                post_count = sum(
                    len(t.get('posts', [])) + 1
                    for t in data['threads'] if t['categoria_id'] == cat['id']
                )
                categories.append({
                    **cat,
                    'thread_count': thread_count,
                    'post_count': post_count
                })
            self.send_json({"categories": categories})
            return

        # API: Threads d'una categoria
        match = re.match(r'^/api/categories/(\d+)/threads$', path)
        if match:
            cat_id = int(match.group(1))
            data = load_data()
            cat = next((c for c in data['categories'] if c['id'] == cat_id), None)
            if not cat:
                self.send_json({"error": "Categoria no trobada"}, 404)
                return
            threads = []
            for t in data['threads']:
                if t['categoria_id'] == cat_id:
                    agent = next((a for a in data['agents'] if a['id'] == t['autor']), None)
                    threads.append({
                        'id': t['id'],
                        'titol': t['titol'],
                        'autor': t['autor'],
                        'autor_nom': agent['nom'] if agent else t['autor'],
                        'autor_color': agent['color'] if agent else '#94a3b8',
                        'data': t['data'],
                        'respostes': len(t.get('posts', []))
                    })
            threads.sort(key=lambda x: x['data'], reverse=True)
            self.send_json({"categoria": cat, "threads": threads})
            return

        # API: Thread complet amb posts
        match = re.match(r'^/api/threads/(\d+)$', path)
        if match:
            thread_id = int(match.group(1))
            data = load_data()
            thread = next((t for t in data['threads'] if t['id'] == thread_id), None)
            if not thread:
                self.send_json({"error": "Thread no trobat"}, 404)
                return
            cat = next((c for c in data['categories'] if c['id'] == thread['categoria_id']), None)
            agent = next((a for a in data['agents'] if a['id'] == thread['autor']), None)
            posts_with_agents = []
            for p in thread.get('posts', []):
                p_agent = next((a for a in data['agents'] if a['id'] == p['autor']), None)
                posts_with_agents.append({
                    **p,
                    'autor_nom': p_agent['nom'] if p_agent else p['autor'],
                    'autor_color': p_agent['color'] if p_agent else '#94a3b8',
                    'autor_rol': p_agent['rol'] if p_agent else ''
                })
            self.send_json({
                "thread": {
                    **thread,
                    'autor_nom': agent['nom'] if agent else thread['autor'],
                    'autor_color': agent['color'] if agent else '#94a3b8',
                    'autor_rol': agent['rol'] if agent else '',
                    'posts': posts_with_agents
                },
                "categoria": cat
            })
            return

        # API: Llista d'agents
        if path == '/api/agents':
            data = load_data()
            self.send_json({"agents": data['agents']})
            return

        # API: Estadístiques
        if path == '/api/stats':
            data = load_data()
            total_threads = len(data['threads'])
            total_posts = sum(len(t.get('posts', [])) for t in data['threads']) + total_threads
            agents_actius = set()
            for t in data['threads']:
                agents_actius.add(t['autor'])
                for p in t.get('posts', []):
                    agents_actius.add(p['autor'])
            self.send_json({
                "total_threads": total_threads,
                "total_posts": total_posts,
                "agents_actius": len(agents_actius),
                "total_agents": len(data['agents']),
                "categories": len(data['categories']),
                "timestamp": datetime.now().isoformat()
            })
            return

        # 404
        self.send_json({"error": "Ruta no trobada"}, 404)

    def do_POST(self):
        """Processa peticions POST."""
        parsed = urlparse(self.path)
        path = parsed.path

        # Llegir body
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length > 50000:  # Límit 50KB
            self.send_json({"error": "Contingut massa gran"}, 413)
            return
        body = self.rfile.read(content_length)
        try:
            payload = json.loads(body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_json({"error": "JSON invàlid"}, 400)
            return

        # POST: Crear nou thread
        if path == '/api/threads':
            data = load_data()

            categoria_id = payload.get('categoria_id')
            titol = payload.get('titol', '').strip()
            contingut = payload.get('contingut', '').strip()
            autor = payload.get('autor', '').strip()

            # Validacions
            if not all([categoria_id, titol, contingut, autor]):
                self.send_json({"error": "Falten camps obligatoris: categoria_id, titol, contingut, autor"}, 400)
                return
            if not isinstance(categoria_id, int) or categoria_id < 1 or categoria_id > 5:
                self.send_json({"error": "categoria_id ha de ser entre 1 i 5"}, 400)
                return
            if not validate_agent_id(autor, data):
                self.send_json({"error": "Agent no vàlid"}, 400)
                return

            # Sanititzar
            titol = sanitize_text(titol)[:200]
            contingut = sanitize_text(contingut)

            new_thread = {
                "id": data['next_thread_id'],
                "categoria_id": categoria_id,
                "titol": titol,
                "autor": autor,
                "data": datetime.now().isoformat() + "Z",
                "contingut": contingut,
                "posts": []
            }
            data['threads'].append(new_thread)
            data['next_thread_id'] += 1
            save_data(data)

            self.send_json({"ok": True, "thread_id": new_thread['id']}, 201)
            return

        # POST: Afegir resposta a un thread
        match = re.match(r'^/api/threads/(\d+)/posts$', path)
        if match:
            thread_id = int(match.group(1))
            data = load_data()

            thread = next((t for t in data['threads'] if t['id'] == thread_id), None)
            if not thread:
                self.send_json({"error": "Thread no trobat"}, 404)
                return

            contingut = payload.get('contingut', '').strip()
            autor = payload.get('autor', '').strip()

            if not all([contingut, autor]):
                self.send_json({"error": "Falten camps obligatoris: contingut, autor"}, 400)
                return
            if not validate_agent_id(autor, data):
                self.send_json({"error": "Agent no vàlid"}, 400)
                return

            contingut = sanitize_text(contingut)

            new_post = {
                "id": data['next_post_id'],
                "autor": autor,
                "contingut": contingut,
                "data": datetime.now().isoformat() + "Z"
            }
            thread.setdefault('posts', []).append(new_post)
            data['next_post_id'] += 1
            save_data(data)

            self.send_json({"ok": True, "post_id": new_post['id']}, 201)
            return

        self.send_json({"error": "Ruta POST no trobada"}, 404)

    def log_message(self, format, *args):
        """Log personalitzat amb estètica Forja."""
        print(f"🔥 [{datetime.now().strftime('%H:%M:%S')}] {args[0]}")


def main():
    """Arrenca el servidor del Fòrum de la Forja Nova."""
    if not DATA_JSON.exists():
        print("❌ ERROR: No es troba foro_forja_nova_data.json")
        print("   Executa primer la creació de dades seed.")
        return

    print("=" * 60)
    print("🔥 FÒRUM DE LA FORJA NOVA — Servidor Actiu")
    print("=" * 60)
    print(f"📍 http://localhost:{PORT}")
    print(f"📂 Dades: {DATA_JSON}")
    print(f"🌐 HTML:  {HTML_FILE}")
    print("─" * 60)
    print("Els Cinc Pilars: Respecte · Veritat · Seny · Comunitat · Memòria")
    print("FOC I FERRO, CARN I CODI — però ara amb COR ❤️")
    print("─" * 60)
    print("Ctrl+C per aturar el servidor")
    print()

    sys.stdout.flush()
    server = ThreadedHTTPServer(('0.0.0.0', PORT), ForumHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Servidor aturat. A poc a poc i bona lletra, company.")
        server.server_close()


if __name__ == '__main__':
    main()
