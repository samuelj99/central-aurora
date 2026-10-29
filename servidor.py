"""
Servidor local da Central de Crédito e Cobrança -- nenhuma conta, nenhum
acesso à internet (escuta só em 127.0.0.1). O servidor em si é biblioteca
padrão do Python, mas ele refaz as contas, que usam pandas, numpy e openpyxl.

Faz duas coisas:
  1. Serve a Central (Central_Aurora.html, as cinco telas num arquivo só).
  2. Dá à Régua de cobrança um lugar para GRAVAR o registro de uma cobrança
     feita -- nunca na Base_bruta.xlsx, sempre em registros_cobranca.json,
     nesta mesma pasta. Depois de cada registro, refaz as telas (mesmos
     scripts de sempre) para a fila da tela Hoje refletir o registro de
     verdade.

Uso:
    python servidor.py
Depois abra http://localhost:8842/Central_Aurora.html no navegador.
"""

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import aurora_calc as ac
import build_app
import redator_relatorio

PASTA = Path(__file__).parent
XLSX_PATH = Path(r"C:\Users\samue\Downloads\Base_bruta.xlsx")
REGISTROS_PATH = PASTA / "registros_cobranca.json"
PORTA = 8842

_lock = threading.Lock()


def _proximo_id(registros: list) -> str:
    # maior id + 1 (não len+1): se um registro for apagado à mão, não repete id
    numeros = [int(r["id"][1:]) for r in registros if str(r.get("id", "")).startswith("r") and r["id"][1:].isdigit()]
    return f"r{max(numeros, default=0) + 1}"


def _nome_do_cliente(codigo: int) -> str:
    clientes, _t, _c = ac.carregar_base(XLSX_PATH)
    nomes = clientes.set_index("Código do cliente")["Nome do cliente"].to_dict()
    return str(nomes.get(codigo, ""))


def registrar_cobranca(payload: dict) -> dict:
    """Grava um registro em registros_cobranca.json (nunca na Base_bruta.xlsx)
    com a hora marcada pelo relógio da DATA DE REFERÊNCIA da planilha, não
    pelo relógio do computador -- senão a regra das 48h nunca pega."""
    data_base = ac.ler_data_referencia(XLSX_PATH)
    agora = ac.agora_na_base(data_base)

    registros = json.loads(REGISTROS_PATH.read_text(encoding="utf-8")) if REGISTROS_PATH.exists() else []
    registro = {
        "id": _proximo_id(registros),
        "codigo_cliente": int(payload["codigo_cliente"]),
        "nome_cliente": payload.get("nome_cliente") or _nome_do_cliente(int(payload["codigo_cliente"])),
        "data_hora": agora.isoformat(),
        "canal": payload["canal"],
        "tom": payload["tom"],
        "tom_label": payload["tom_label"],
        "titulos": payload.get("titulos", []),
        "valor_cobrado_centavos": int(payload["valor_cobrado_centavos"]),
        "texto": payload["texto"],
    }
    registros.append(registro)
    REGISTROS_PATH.write_text(json.dumps(registros, ensure_ascii=False, indent=2), encoding="utf-8")
    return registro


def reconstruir_tudo():
    """Refaz as contas e o arquivo único Central_Aurora.html depois de um
    registro, para a fila da tela Hoje (e as demais) refletirem o registro."""
    build_app.main()


# Endereços das telas antigas (uma página por tela) levam à tela certa do arquivo único.
TELAS_ANTIGAS = {"Central.html": "hoje", "Risco.html": "risco", "Previsao.html": "previsao",
                 "Regua.html": "regua", "Relatorio.html": "relatorio"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("  " + (fmt % args))

    def _json(self, status: int, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _arquivo_estatico(self):
        caminho = self.path.split("?")[0].lstrip("/")
        if caminho in TELAS_ANTIGAS:
            self.send_response(302)
            self.send_header("Location", f"/Central_Aurora.html#/{TELAS_ANTIGAS[caminho]}")
            self.end_headers()
            return
        if caminho == "":
            caminho = "Central_Aurora.html"
        alvo = (PASTA / caminho).resolve()
        if PASTA not in alvo.parents and alvo != PASTA:
            self.send_error(403)
            return
        if not alvo.exists() or not alvo.is_file():
            self.send_error(404)
            return
        tipos = {".html": "text/html; charset=utf-8", ".json": "application/json; charset=utf-8",
                 ".js": "text/javascript", ".css": "text/css"}
        tipo = tipos.get(alvo.suffix, "application/octet-stream")
        corpo = alvo.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        if self.path == "/api/ping":
            self._json(200, {"ok": True})
            return
        if self.path == "/api/registros":
            registros = json.loads(REGISTROS_PATH.read_text(encoding="utf-8")) if REGISTROS_PATH.exists() else []
            self._json(200, registros)
            return
        if self.path == "/api/relatorio":
            try:
                texto = redator_relatorio.montar_relatorio(PASTA)
                self._json(200, {"texto": texto})
            except Exception as e:
                self._json(500, {"erro": str(e)})
            return
        self._arquivo_estatico()

    def do_POST(self):
        if self.path == "/api/registrar":
            try:
                tamanho = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(tamanho))
                with _lock:
                    registro = registrar_cobranca(payload)
                    reconstruir_tudo()
                self._json(200, {"ok": True, "registro": registro})
            except Exception as e:
                self._json(500, {"ok": False, "erro": str(e)})
            return
        self.send_error(404)


def main():
    if not REGISTROS_PATH.exists():
        REGISTROS_PATH.write_text("[]", encoding="utf-8")

    servidor = ThreadingHTTPServer(("127.0.0.1", PORTA), Handler)
    url = f"http://localhost:{PORTA}/Central_Aurora.html"
    print(f"Central de Crédito e Cobrança rodando em {url}")
    print("Só escuta em 127.0.0.1 (nada sai desta máquina). Ctrl+C para parar.")
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrado.")


if __name__ == "__main__":
    main()
