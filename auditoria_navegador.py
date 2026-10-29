"""
Auditoria da Central no navegador de verdade -- complementa conferencia.py (que confere as
CONTAS); esta confere a TELA. Abre Central_Aurora.html no Chrome, em tamanho de telão
(1920x1080), notebook (1366x768) e celular (390x844), tira foto de cada tela e verifica:

  1. A LISTA DO QUE NÃO PODE SUMIR: cada alerta, link, número e a frase que explica cada
     cliente continuam na tela (visíveis ou guardados atrás de um clique -- mas presentes).
  2. Nada cortado: o número grande cabe inteiro; nada rola para o lado.
  3. Telão: na tela Hoje, o número grande, a fila e o PRIMEIRO CLIENTE INTEIRO aparecem
     sem rolar (acima da barra de navegação).
  4. Sem erro de JavaScript no console.

Precisa do Playwright (só para auditar; a Central em si não precisa de nada):
    pip install playwright
Uso:
    python auditoria_navegador.py [pasta_das_fotos]
"""

import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

PASTA = Path(__file__).parent
ARQ = PASTA / "Central_Aurora.html"
FOTOS = Path(sys.argv[1]) if len(sys.argv) > 1 else PASTA / "auditoria_fotos"
TAMANHOS = [(1920, 1080, "telao"), (1366, 768, "notebook"), (390, 844, "celular")]
ROTAS = ["hoje", "risco", "previsao", "regua", "relatorio"]

falhas, oks = [], 0


def checar(nome, ok, detalhe=""):
    global oks
    if ok:
        oks += 1
    else:
        falhas.append(f"{nome}" + (f" -- {detalhe}" if detalhe else ""))


def norm(s):
    return re.sub(r"\s+", " ", str(s).replace(" ", " ")).strip()


def reais(c):
    r = (abs(round(c)) + 50) // 100
    return ("−" if c < 0 and r else "") + "R$ " + f"{r:,}".replace(",", ".")


def dados():
    html = ARQ.read_text(encoding="utf-8")
    i = html.index("const DATA = ") + len("const DATA = ")
    return json.JSONDecoder().raw_decode(html[i:])[0]


def lista_nao_pode_sumir(D):
    """O que cada tela precisa conter. Montada a partir dos dados, não escrita à mão."""
    H, R, P, G, REL = D["hoje"], D["risco"], D["previsao"], D["regua"], D["relatorio"]
    r = H["resumo"]
    hoje = [reais(r["total_vencido_centavos"]), f"{r['qtd_titulos_vencidos']} títulos vencidos", f"{r['clientes_na_fila']} de {r['total_clientes_base']} clientes",
            reais(r["total_a_vencer_centavos"]), f"{r['qtd_titulos_a_vencer']} títulos a vencer", f"{r['total_titulos_base']} títulos na base",
            "Quem eu ligo primeiro", "O que a Central descobriu", "Como a fila é montada", "A fila cruza três coisas"]
    for c in H["fila"]:
        hoje += [c["nome"], reais(c["valor_vencido_centavos"]), c["frase"], c["contato_nome"]] + [t["numero"] for t in c["titulos"]] + c["motivo"]
        if c["mudou_comportamento"]:
            hoje.append("Mudou de comportamento")
    for d in R["descobertas"]:
        hoje += [d["nome"], d["chave"], d["tipo_rotulo"]]
    rr = R["resumo"]
    risco = [reais(rr["valor_em_risco_total_centavos"]), reais(rr["saldo_aberto_total_centavos"]), reais(rr["faturamento_total_12m_centavos"]),
             "saldo em aberto total", "faturamento emitido nos últimos 12 meses", "Onde está o dinheiro em risco", "Como o índice de risco é calculado"]
    for c in R["clientes"]:
        risco += [c["nome"], reais(c["valor_em_risco_centavos"]), c["alerta_curto"]] + [k["frase"] for k in c["componentes"]]
    pr = P["resumo"]
    prev = ["não é projeção de venda nova", reais(pr["planilha_centavos"]), reais(pr["esperado_centavos"]), reais(abs(pr["diferenca_centavos"])),
            f"{pr['qtd_titulos_no_horizonte']} títulos vencem dentro do período", "Acumulado nas próximas 4 semanas", "Quem puxa a diferença",
            "Como a data prevista é calculada", "Cenário otimista usa", "A faixa só é honesta no acumulado"]
    for s in P["semanas"]:
        prev += [reais(s["planilha_centavos"]), reais(s["esperado_centavos"]), reais(abs(s["diferenca_centavos"]))]
    for c in P["clientes"]:
        prev += [c["nome"], reais(c["naive_centavos"]), reais(c["esperado_centavos"])]
    regua = ["Como a Régua escolhe o tom", "Registrar cobrança", "Copiar texto", "Histórico de contato"] + [c["nome"] for c in G["clientes"]]
    rel = [norm(l) for l in REL["texto"].split("\n") if l.strip()] + ["Copiar texto", "Baixar .txt", reais(REL["semana"]["entrou_centavos"])]
    return {"hoje": hoje, "risco": risco, "previsao": prev, "regua": regua, "relatorio": rel}


def main():
    FOTOS.mkdir(exist_ok=True)
    D = dados()
    exigido = lista_nao_pode_sumir(D)
    url = ARQ.resolve().as_uri()
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        for w, h, tag in TAMANHOS:
            pg = b.new_page(viewport={"width": w, "height": h})
            erros = []
            pg.on("pageerror", lambda e: erros.append(str(e)))
            pg.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
            for rota in ROTAS:
                pg.goto(f"{url}#/{rota}")
                pg.wait_for_timeout(1600)
                pg.screenshot(path=str(FOTOS / f"{rota}_{tag}.png"))
                pg.screenshot(path=str(FOTOS / f"{rota}_{tag}_inteira.png"), full_page=True)
                checar(f"[{tag}] {rota}: nada rola para o lado", pg.evaluate("document.documentElement.scrollWidth") <= w,
                       f"largura {pg.evaluate('document.documentElement.scrollWidth')}")
                cortado = pg.evaluate("""() => [...document.querySelectorAll('.num-hero')].filter(e => e.scrollWidth > e.parentElement.clientWidth + 1).map(e => e.textContent)""")
                checar(f"[{tag}] {rota}: número grande inteiro, sem corte", not cortado, str(cortado))
                if tag != "celular":
                    texto = norm(pg.evaluate("document.body.textContent"))
                    faltando = [x for x in exigido[rota] if norm(x) not in texto]
                    checar(f"[{tag}] {rota}: nada da lista do que não pode sumir sumiu ({len(exigido[rota])} itens)", not faltando, str(faltando[:5]))
                    dock = pg.evaluate("[...document.querySelectorAll('.dock a')].map(a => a.textContent.trim())")
                    atual = pg.evaluate("document.querySelector('.dock a[aria-current=page]')?.dataset.rota")
                    checar(f"[{tag}] {rota}: as cinco telas à vista e a atual marcada", len(dock) == 5 and atual == rota, f"{dock} atual={atual}")
            # telão: primeiro cliente inteiro sem rolar, acima da barra de navegação
            if tag == "telao":
                pg.goto(f"{url}#/hoje"); pg.wait_for_timeout(1600)
                fim_cartao = pg.evaluate("document.querySelector('.cliente').getBoundingClientRect().bottom")
                topo_dock = pg.evaluate("document.querySelector('.dock').getBoundingClientRect().top")
                checar("[telao] hoje: número grande, fila e primeiro cliente inteiro sem rolar", fim_cartao <= topo_dock,
                       f"cartão termina em {fim_cartao:.0f}px, barra começa em {topo_dock:.0f}px")
                # cada ficha do Risco abre com gráfico e o alerta por extenso
                for c in D["risco"]["clientes"]:
                    pg.goto(f"{url}#/risco/{c['codigo']}"); pg.wait_for_timeout(250)
                    ficha = norm(pg.evaluate("document.getElementById('ficha').textContent"))
                    checar(f"ficha de {c['nome']}: abre com o alerta por extenso e o gráfico",
                           norm(c["alerta"]) in ficha and pg.evaluate("!!document.querySelector('#ficha svg')"))
                    pg.screenshot(path=str(FOTOS / f"ficha_{c['codigo']}.png")) if c["posicao"] <= 2 else None
                # régua: cada cliente mostra o texto com os títulos dele, e os 6 tons reescrevem o texto
                for c in D["regua"]["clientes"]:
                    pg.goto(f"{url}#/regua/{c['codigo']}"); pg.wait_for_timeout(250)
                    txt = pg.input_value("#texto-msg")
                    det = norm(pg.evaluate("document.getElementById('regua-detalhe').textContent"))
                    checar(f"régua de {c['nome']}: texto com todos os títulos e a justificativa do tom",
                           all(t["numero"] in txt for t in c["titulos_vencidos"]) and norm(c["justificativa_tom"]) in det)
                    textos = set()
                    for tom in D["regua"]["tons"]:
                        pg.select_option("#sel-tom", tom); pg.wait_for_timeout(40); textos.add(pg.input_value("#texto-msg"))
                    checar(f"régua de {c['nome']}: trocar o tom reescreve o texto (6 tons, 6 textos)", len(textos) == len(D["regua"]["tons"]))
                pg.goto(f"{url}#/regua"); pg.wait_for_timeout(300)
                desligado = pg.evaluate("document.querySelector('[data-acao=registrar]').disabled")
                motivo = pg.evaluate("!!document.querySelector('.desligado')")
                checar("régua (arquivo sem servidor): 'Registrar' desligado E com o motivo escrito ao lado", desligado and motivo)
                pg.goto(f"{url}#/relatorio"); pg.wait_for_timeout(400)
                n_valores = len(re.findall(r"R\$\s?[\d.]+", D["relatorio"]["texto"]))
                n_realce = pg.evaluate("document.querySelectorAll('#papel .realce').length")
                checar(f"relatório: todo valor em reais do texto está realçado ({n_valores} valores)", n_realce == n_valores, f"realçados {n_realce}")
                # ações da fila: "já liguei" marca, filtra e desmarca
                pg.goto(f"{url}#/hoje"); pg.wait_for_timeout(300)
                cod = D["hoje"]["fila"][0]["codigo"]
                pg.click(f"#cli-{cod} [data-acao=liguei]"); pg.wait_for_timeout(150)
                pg.click("[data-acao=filtro][data-valor=liguei]"); pg.wait_for_timeout(150)
                n = pg.evaluate("document.querySelectorAll('#lista-hoje .cliente').length")
                pg.click("[data-acao=filtro][data-valor=todos]"); pg.click(f"#cli-{cod} [data-acao=liguei]")
                checar("hoje: marcar 'já liguei' e filtrar mostra só o cliente marcado", n == 1, f"{n} cartões")
                pg.fill("[data-busca=hoje]", D["hoje"]["fila"][-1]["nome"][:8]); pg.wait_for_timeout(150)
                checar("hoje: a busca acha o cliente", pg.evaluate("document.querySelectorAll('#lista-hoje .cliente').length") >= 1)
            checar(f"[{tag}] sem erro de JavaScript", not erros, str(erros[:3]))
            pg.close()
        b.close()
    print(f"{oks} verificações OK, {len(falhas)} falharam. Fotos em {FOTOS}")
    for f in falhas:
        print("  FALHOU:", f)
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
