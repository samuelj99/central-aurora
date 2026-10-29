"""
Monta a Central inteira num ARQUIVO SÓ: Central_Aurora.html.

Roda as contas (build_central, build_risco, build_previsao, build_regua, nessa ordem, porque
Previsão e Régua leem os exports das anteriores), pede o texto do Relatório ao redator e embute
tudo -- dados, estilo, script e as duas fontes -- em um único HTML que abre com duplo clique,
sem internet e sem instalar nada. Não faz nenhuma conta de negócio: só junta o que os outros
scripts já calcularam.

O desenho vive em app/: base.html (esqueleto), estilo.css, redacao.js (motor de texto, o ponto
único a trocar por IA) e app.js (as cinco telas). As fontes ficam em app/fontes/.

Uso:
    python build_app.py
"""

import base64
import json
from pathlib import Path

import build_central
import build_previsao
import build_regua
import build_risco
import redator_relatorio

PASTA = Path(__file__).parent
APP = PASTA / "app"
SAIDA = PASTA / "Central_Aurora.html"

FONTES = [  # (família, arquivo, intervalo de pesos da fonte variável)
    ("Unbounded", "unbounded.woff2", "200 900"),
    ("Manrope", "manrope.woff2", "200 800"),
]


def css_das_fontes() -> str:
    regras = []
    for familia, arquivo, pesos in FONTES:
        b64 = base64.b64encode((APP / "fontes" / arquivo).read_bytes()).decode("ascii")
        regras.append(
            f"@font-face{{font-family:'{familia}';font-style:normal;font-weight:{pesos};font-display:swap;"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2');}}"
        )
    return "\n".join(regras)


def montar_dados() -> dict:
    hoje = build_central.main()
    risco = build_risco.main()
    previsao = build_previsao.main()
    regua = build_regua.main()
    texto = redator_relatorio.montar_relatorio(PASTA)
    # contagens simples para o topo da Régua (nenhuma conta nova: só contar a lista que já existe)
    regua["resumo"] = {
        "qtd": len(regua["clientes"]),
        "cobrados_48h": sum(1 for c in regua["clientes"]
                            if c["dias_desde_ultimo_contato"] is not None
                            and c["dias_desde_ultimo_contato"] <= build_central.JANELA_CONTATO_DIAS),
    }
    return {
        "referencia": hoje["resumo"]["data_base"],
        "hoje": hoje, "risco": risco, "previsao": previsao, "regua": regua,
        "relatorio": {"texto": texto, "semana": redator_relatorio.numeros_da_semana()},
    }


def main():
    dados = montar_dados()
    # "</" dentro de um <script> fecharia a tag antes da hora
    dados_json = json.dumps(dados, ensure_ascii=False).replace("</", r"<\/")
    html = (APP / "base.html").read_text(encoding="utf-8")
    html = (html.replace("/*__FONTES__*/", css_das_fontes())
                .replace("/*__CSS__*/", (APP / "estilo.css").read_text(encoding="utf-8"))
                .replace("__DATA_JSON__", dados_json)
                .replace("/*__JS__*/", (APP / "redacao.js").read_text(encoding="utf-8") + "\n" + (APP / "app.js").read_text(encoding="utf-8")))
    SAIDA.write_text(html, encoding="utf-8")
    print(f"OK -- {SAIDA.name} gerado ({SAIDA.stat().st_size / 1024:.0f} KB, arquivo único).")
    return dados


if __name__ == "__main__":
    main()
