/* =====================================================================
   Central Aurora — as cinco telas num arquivo só.
   Este script NÃO faz conta de negócio: só lê DATA (montado por build_app.py a partir das
   mesmas contas de sempre), filtra, ordena e desenha. A redação das mensagens da Régua mora
   em redacao.js (gerarTexto), que vem antes deste arquivo.
   ===================================================================== */
"use strict";

const H = DATA.hoje, R = DATA.risco, P = DATA.previsao, G = DATA.regua, REL = DATA.relatorio;
const riscoPor = Object.fromEntries(R.clientes.map(c => [c.codigo, c]));
const reguaPor = Object.fromEntries(G.clientes.map(c => [c.codigo, c]));
const hojePor = Object.fromEntries(H.fila.map(c => [c.codigo, c]));

/* ---------- utilidades ---------- */
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
const dec = (v, casas = 1) => Number(v).toFixed(casas).replace(".", ",");
const semAcento = s => String(s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const movimentoReduzido = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const ICONE = {
  busca: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>',
  seta: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14m-6-6 6 6-6 6"/></svg>',
  check: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>',
  abre: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>',
};

const SEV_ROTULO = { critico: "Crítico", atencao: "Atenção", ok: "Dentro do padrão", neutro: "Sem histórico" };
const TIER_ROTULO = { inedito: "atraso inédito", acima_normal: "acima do normal dele", dentro_padrao: "dentro do padrão dele", sem_historico: "sem histórico" };
const NIVEL = { alto: { sev: "critico", rot: "Alto" }, medio: { sev: "atencao", rot: "Médio" }, baixo: { sev: "ok", rot: "Baixo" } };
const SEV_CASO = { deteriorou: "critico", comprando_menos: "atencao", caro_silencioso: "atencao", falso_positivo_cronico: "ok", sazonal: "ok" };

/* ---------- "já liguei": marcação só deste navegador ---------- */
const CHAVE_LIGUEI = "aurora:liguei:" + DATA.referencia;
let liguei = new Set();
try { liguei = new Set(JSON.parse(localStorage.getItem(CHAVE_LIGUEI) || "[]")); } catch (e) { /* sem armazenamento: só nesta sessão */ }
function alternarLiguei(cod) {
  liguei.has(cod) ? liguei.delete(cod) : liguei.add(cod);
  try { localStorage.setItem(CHAVE_LIGUEI, JSON.stringify([...liguei])); } catch (e) { /* segue só na memória */ }
}

/* ---------- servidor (só existe quando a Central roda com python servidor.py) ---------- */
let servidor = false;
async function verificarServidor() {
  if (location.protocol === "file:") return false;
  try { const r = await fetch("/api/ping", { cache: "no-store" }); return r.ok; } catch (e) { return false; }
}

/* ---------- estado das telas ---------- */
const estado = {
  hoje: { busca: "", filtro: "todos", ordem: "prioridade", abertos: new Set() },
  risco: { busca: "", filtro: "todos", ordem: "risco", abertos: new Set() },
  previsao: { busca: "", ordem: "diferenca" },
  regua: { busca: "", filtro: "todos", ordem: "prioridade", sel: null, escolha: {} },
};

/* =====================================================================
   PEÇAS COMUNS
   ===================================================================== */
function chips(tela, opcoes) {
  const atual = estado[tela].filtro;
  return `<div class="chips" role="group" aria-label="Filtrar">${opcoes.map(o =>
    `<button class="chip ${o.sev ? "sev-" + o.sev : ""}" type="button" data-acao="filtro" data-tela="${tela}" data-valor="${o.id}" aria-pressed="${atual === o.id}">${o.sev ? '<span class="pt"></span>' : ""}${esc(o.rot)} <span class="n">${o.n}</span></button>`
  ).join("")}</div>`;
}
function busca(tela, rotulo) {
  return `<label class="busca">${ICONE.busca}<input type="search" data-busca="${tela}" placeholder="${esc(rotulo)}" aria-label="${esc(rotulo)}" value="${esc(estado[tela].busca)}"></label>`;
}
function ordem(tela, opcoes) {
  return `<label class="ordem">Ordenar por <select data-ordem="${tela}">${opcoes.map(([v, t]) =>
    `<option value="${v}" ${estado[tela].ordem === v ? "selected" : ""}>${t}</option>`).join("")}</select></label>`;
}
function bateBusca(tela, ...campos) {
  const q = semAcento(estado[tela].busca.trim());
  return !q || campos.some(c => semAcento(c).includes(q));
}
function tagSev(sev, texto) { return `<span class="tag sev-${sev}"><span class="pt"></span>${esc(texto)}</span>`; }
function tagContato(dias_) { return tagSev("acao", dias_ === 0 ? "Cobrado hoje" : `Cobrado há ${dias(dias_)}`); }
function tagLiguei(cod) { return liguei.has(cod) ? tagSev("ok", "Já liguei") : ""; }
function botaoLiguei(cod) {
  const on = liguei.has(cod);
  return `<button class="btn discreto" type="button" data-acao="liguei" data-cod="${cod}" aria-pressed="${on}" title="Marcação só neste navegador — não muda a fila nem registra cobrança">${ICONE.check}${on ? "Liguei" : "Já liguei"}</button>`;
}
function metodo(titulo, corpo) {
  return `<details class="metodo vidro"><summary>${esc(titulo)}</summary>${corpo}</details>`;
}
function realcarDinheiro(textoEscapado) {
  return textoEscapado.replace(/[−+-]?R\$[\s ]?[\d.]+(,\d{2})?/g, m => `<span class="realce">${m}</span>`);
}

/* =====================================================================
   GRÁFICOS (SVG feito à mão; texto sempre em cor de texto, nunca na cor da série)
   ===================================================================== */
function faixasHTML(faixas) {
  const max = Math.max(...faixas.map(f => f.valor_centavos), 1);
  return `<div class="faixas" role="list">${faixas.map(f => `
    <div class="faixa" role="listitem" data-tip="${esc(f.rotulo)}: ${esc(fmtReais(f.valor_centavos))} em ${f.qtd} ${plural(f.qtd, "título", "títulos")}">
      <span class="rot">${esc(f.rotulo)}</span>
      <div class="trilho"><div class="barra" style="width:${(f.valor_centavos / max * 100).toFixed(1)}%"></div></div>
      <span class="val">${fmtReais(f.valor_centavos)}<small>${f.qtd} ${plural(f.qtd, "título", "títulos")}</small></span>
    </div>`).join("")}</div>`;
}

function sparkline(c) {
  const s = c.serie_mensal || [];
  if (s.length < 2) return "";
  const W = 180, Hh = 48, pad = 5;
  const vals = s.map(p => p.media);
  const lo = Math.min(...vals, c.media_atraso - (c.desvio_atraso || 0)), hi = Math.max(...vals, c.media_atraso + (c.desvio_atraso || 0));
  const x = i => pad + i / (s.length - 1) * (W - 2 * pad);
  const y = v => pad + (1 - (v - lo) / ((hi - lo) || 1)) * (Hh - 2 * pad);
  let svg = `<svg class="spark" viewBox="0 0 ${W} ${Hh}" role="img" aria-label="Atraso médio por mês: de ${Math.round(Math.min(...vals))} a ${Math.round(Math.max(...vals))} dias; último mês ${Math.round(vals[vals.length - 1])} dias">`;
  if (c.desvio_atraso != null) svg += `<rect x="${pad}" y="${y(c.media_atraso + c.desvio_atraso)}" width="${W - 2 * pad}" height="${y(c.media_atraso - c.desvio_atraso) - y(c.media_atraso + c.desvio_atraso)}" fill="#8f6bff" opacity=".16" rx="3"/>`;
  for (let i = 1; i < s.length; i++) {
    const cor = s[i].fora_padrao && s[i - 1].fora_padrao ? "#ff6a45" : "#b9a5ff";
    svg += `<line x1="${x(i - 1)}" y1="${y(s[i - 1].media)}" x2="${x(i)}" y2="${y(s[i].media)}" stroke="${cor}" stroke-width="2" stroke-linecap="round"/>`;
  }
  const u = s.length - 1;
  svg += `<circle cx="${x(u)}" cy="${y(s[u].media)}" r="4" fill="${s[u].fora_padrao ? "#ff6a45" : "#b9a5ff"}" stroke="#1a0f45" stroke-width="2"/>`;
  return svg + "</svg>";
}

const MES_CURTO = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const mesCurto = iso => { const [a, m] = iso.split("-"); return MES_CURTO[+m - 1] + "/" + a.slice(2); };
function passoBonito(amplitude, marcas = 4) {
  const bruto = amplitude / marcas, mag = Math.pow(10, Math.floor(Math.log10(bruto)));
  return [1, 2, 2.5, 5, 10].map(k => k * mag).find(k => k >= bruto);
}

function graficoFicha(cli) {
  const serie = cli.serie_mensal;
  if (!serie || !serie.length) return '<p class="hero-sub">Sem histórico de pagamento suficiente para o gráfico.</p>';
  const W = 760, Hh = 240, pl = 44, pr = 14, pt = 14, pb = 28;
  const vals = serie.map(p => p.media), media = cli.media_atraso, desvio = cli.desvio_atraso || 0;
  let lo = Math.min(...vals, media - desvio, 0), hi = Math.max(...vals, media + desvio);
  const passo = passoBonito(Math.max(4, hi - lo));
  lo = Math.floor(lo / passo) * passo; hi = Math.ceil(hi / passo) * passo;
  const x = i => pl + i / Math.max(1, serie.length - 1) * (W - pl - pr);
  const y = v => pt + (1 - (v - lo) / (hi - lo)) * (Hh - pt - pb);
  let svg = `<svg class="grafico" viewBox="0 0 ${W} ${Hh}" role="img" aria-label="Atraso médio mês a mês de ${esc(cli.nome)}">`;
  for (let v = lo; v <= hi + 1e-9; v += passo) {
    svg += `<line class="grade" x1="${pl}" x2="${W - pr}" y1="${y(v)}" y2="${y(v)}"/><text x="${pl - 8}" y="${y(v) + 4}" font-size="11" text-anchor="end">${v}d</text>`;
  }
  if (cli.desvio_atraso != null) {
    svg += `<rect x="${pl}" y="${y(media + desvio)}" width="${W - pl - pr}" height="${y(media - desvio) - y(media + desvio)}" fill="#8f6bff" opacity=".16"/>`;
    svg += `<line x1="${pl}" x2="${W - pr}" y1="${y(media)}" y2="${y(media)}" stroke="#b9a5ff" stroke-width="1" opacity=".6"/>`;
  }
  for (let i = 1; i < serie.length; i++) {
    const a = serie[i - 1], b = serie[i];
    svg += `<line x1="${x(i - 1)}" y1="${y(a.media)}" x2="${x(i)}" y2="${y(b.media)}" stroke="${a.fora_padrao && b.fora_padrao ? "#ff6a45" : "#b9a5ff"}" stroke-width="2" stroke-linecap="round"/>`;
  }
  serie.forEach((p, i) => {
    const cor = p.fora_padrao ? "#ff6a45" : (p.sazonal ? "#ffc247" : "#b9a5ff");
    svg += `<circle cx="${x(i)}" cy="${y(p.media)}" r="4.5" fill="${cor}" stroke="#1d1150" stroke-width="2" data-tip="${mesCurto(p.mes)}: ${dec(p.media)} dias em média (${p.n} ${plural(p.n, "título", "títulos")})${p.sazonal ? " · mês sazonal" : ""}${p.fora_padrao ? " · fora do padrão" : ""}"/>`;
  });
  const idx = serie.length > 1 ? [0, Math.floor((serie.length - 1) / 2), serie.length - 1] : [0];
  idx.forEach((i, k) => {
    const anc = idx.length === 1 ? "middle" : (k === 0 ? "start" : (k === idx.length - 1 ? "end" : "middle"));
    svg += `<text x="${x(i)}" y="${Hh - 6}" font-size="11" text-anchor="${anc}">${mesCurto(serie[i].mes)}</text>`;
  });
  return svg + "</svg>";
}

function graficoAcumulado() {
  const c = P.cumulativo, n = c.planilha.length;
  const W = 900, Hh = 280, pl = 86, pr = 18, pt = 16, pb = 30;
  const todos = [...c.planilha, ...c.esperado, ...c.otimista, ...c.pessimista];
  const passo = passoBonito(Math.max(...todos, 1));
  const hi = Math.ceil(Math.max(...todos, 1) / passo) * passo, lo = 0;
  const x = i => pl + i / (n - 1) * (W - pl - pr);
  const y = v => pt + (1 - (v - lo) / (hi - lo)) * (Hh - pt - pb);
  let svg = `<svg class="grafico" viewBox="0 0 ${W} ${Hh}" role="img" aria-label="Acumulado nas próximas 4 semanas: planilha ${esc(fmtReais(c.planilha[n - 1]))}, esperado ${esc(fmtReais(c.esperado[n - 1]))}">`;
  for (let v = lo; v <= hi + 1; v += passo) svg += `<line class="grade" x1="${pl}" x2="${W - pr}" y1="${y(v)}" y2="${y(v)}"/><text x="${pl - 10}" y="${y(v) + 4}" font-size="11" text-anchor="end">${esc(fmtReais(v))}</text>`;
  const top = c.otimista.map((v, i) => `${x(i)},${y(v)}`).join(" L ");
  const bot = c.pessimista.map((v, i) => `${x(i)},${y(v)}`).reverse().join(" L ");
  svg += `<path d="M ${top} L ${bot} Z" fill="#5fd8ff" opacity=".12"/>`;
  svg += `<path d="M ${c.planilha.map((v, i) => `${x(i)},${y(v)}`).join(" L ")}" fill="none" stroke="#9e97c9" stroke-width="2" stroke-dasharray="7 5"/>`;
  svg += `<path d="M ${c.esperado.map((v, i) => `${x(i)},${y(v)}`).join(" L ")}" fill="none" stroke="#5fd8ff" stroke-width="2.5" stroke-linecap="round"/>`;
  const rot = ["hoje", "sem 1", "sem 2", "sem 3", "sem 4"];
  for (let i = 0; i < n; i++) {
    svg += `<circle cx="${x(i)}" cy="${y(c.planilha[i])}" r="4" fill="#9e97c9" stroke="#160c42" stroke-width="2" data-tip="${rot[i]} · planilha acumulada: ${esc(fmtReais(c.planilha[i]))}"/>`;
    svg += `<circle cx="${x(i)}" cy="${y(c.esperado[i])}" r="5" fill="#5fd8ff" stroke="#160c42" stroke-width="2" data-tip="${rot[i]} · esperado acumulado: ${esc(fmtReais(c.esperado[i]))} (faixa de ${esc(fmtReais(c.pessimista[i]))} a ${esc(fmtReais(c.otimista[i]))})"/>`;
    svg += `<text x="${x(i)}" y="${Hh - 8}" font-size="11" text-anchor="${i === n - 1 ? "end" : (i === 0 ? "start" : "middle")}">${rot[i]}</text>`;
  }
  return svg + "</svg>";
}

/* =====================================================================
   TELA HOJE
   ===================================================================== */
function telaHoje() {
  const r = H.resumo, st = estado.hoje, fila = H.fila;
  const conta = f => fila.filter(f).length;
  const opcoes = [
    { id: "todos", rot: "Todos", n: fila.length },
    { id: "critico", rot: "Crítico", sev: "critico", n: conta(c => c.severidade === "critico") },
    { id: "atencao", rot: "Atenção", sev: "atencao", n: conta(c => c.severidade === "atencao") },
    { id: "ok", rot: "Dentro do padrão", sev: "ok", n: conta(c => c.severidade === "ok") },
    { id: "cobrados", rot: "Cobrado em 48h", sev: "acao", n: conta(c => c.contato_recente_48h) },
    { id: "liguei", rot: "Já liguei", n: conta(c => liguei.has(c.codigo)) },
  ];
  return `
  <section class="hero">
    <div class="brilho-hero">
      <p class="kicker"><span class="tela-nome">Hoje</span>Vencido hoje · ${esc(r.data_base)}</p>
      <h1 class="num-hero" data-conta="${r.total_vencido_centavos}">${fmtReais(r.total_vencido_centavos)}</h1>
      <p class="hero-sub"><b>${r.qtd_titulos_vencidos} títulos vencidos</b> em <b>${r.clientes_na_fila} de ${r.total_clientes_base} clientes</b>. Fora da fila: ${fmtReais(r.total_a_vencer_centavos)} em ${r.qtd_titulos_a_vencer} títulos a vencer · ${r.total_titulos_base} títulos na base.</p>
    </div>
    <div class="hero-lado vidro">
      <div class="lado-t">Quanto está vencido, por tempo de atraso <span>${r.qtd_titulos_vencidos} títulos</span></div>
      ${faixasHTML(r.faixas_atraso)}
    </div>
  </section>

  <section aria-labelledby="t-desc">
    <div class="bloco-t"><h2 id="t-desc">O que a Central descobriu</h2><p>Conclusões tiradas do histórico de cada cliente, não da lista de vencidos</p></div>
    <div class="descobertas">${R.descobertas.map(d => `
      <a class="descoberta vidro sev-${SEV_CASO[d.tipo] || "neutro"}" href="#/risco/${d.codigo}">
        <span class="chave">${esc(d.chave)}<small>${esc(d.chave_rotulo)}</small></span>
        <span class="o-que">${tagSev(SEV_CASO[d.tipo] || "neutro", d.tipo_rotulo)}<br>${esc(d.frase)}</span>
        <span class="ir">Ver a ficha →</span>
      </a>`).join("")}
    </div>
  </section>

  <section aria-labelledby="t-fila">
    <div class="bloco-t"><h2 id="t-fila">Quem eu ligo primeiro</h2><p>Ordem: valor vencido × risco do atraso; quem foi cobrado nas últimas 48 horas desce</p></div>
    <div class="ferramentas">${busca("hoje", "Buscar cliente")}${chips("hoje", opcoes)}${ordem("hoje", [["prioridade", "Prioridade da fila"], ["valor", "Valor vencido"], ["atraso", "Dias de atraso"], ["nome", "Nome"]])}</div>
    <ol class="lista" id="lista-hoje">${listaHoje()}</ol>
  </section>

  ${metodo("Como a fila é montada", `<p>A fila cruza três coisas: quanto o cliente tem vencido, o risco calculado a partir do histórico de pagamento dele mesmo (comparado com a média e o pior atraso que ele já teve), e se ele foi cobrado nas últimas 48 horas (nesse caso desce de posição). Todos os números vêm de uma conta sobre Base_bruta.xlsx, congelada na data de referência da planilha — não é o relógio do computador. Para atualizar esta tela com uma base nova, gere a Central de novo a partir da planilha atualizada.</p><p style="margin-top:.5rem">O anel de cada cliente mostra quanto do total vencido hoje é dele. "Já liguei" é uma marcação só deste navegador: não muda a fila nem registra cobrança (para registrar, use a Régua).</p>`)}`;
}

function listaHoje() {
  const st = estado.hoje;
  let l = H.fila.filter(c => bateBusca("hoje", c.nome, c.contato_nome, c.regiao, c.categoria));
  if (st.filtro === "cobrados") l = l.filter(c => c.contato_recente_48h);
  else if (st.filtro === "liguei") l = l.filter(c => liguei.has(c.codigo));
  else if (st.filtro !== "todos") l = l.filter(c => c.severidade === st.filtro);
  const ord = { prioridade: (a, b) => a.posicao - b.posicao, valor: (a, b) => b.valor_vencido_centavos - a.valor_vencido_centavos,
    atraso: (a, b) => b.dias_vencido_max - a.dias_vencido_max, nome: (a, b) => a.nome.localeCompare(b.nome, "pt-BR") }[st.ordem];
  l.sort(ord);
  if (!l.length) return `<li class="vazio vidro">Nenhum cliente com esse filtro.</li>`;
  return l.map(c => cartaoHoje(c)).join("");
}

function cartaoHoje(c) {
  const aberto = estado.hoje.abertos.has(c.codigo);
  const tags = [tagSev(c.severidade, `${SEV_ROTULO[c.severidade]} · ${TIER_ROTULO[c.tier]}`)];
  if (c.mudou_comportamento) tags.push(tagSev("critico", "Mudou de comportamento"));
  if (c.contato_recente_48h) tags.push(tagContato(c.dias_desde_contato));
  tags.push(tagLiguei(c.codigo));
  const circ = 2 * Math.PI * 16;
  const titulos = c.titulos.map(t => `<tr><td>${esc(t.numero)}</td><td class="n">${fmtReais(t.valor_centavos)}</td><td>${esc(t.vencimento)}</td><td class="n">${dias(t.dias_vencido)}</td></tr>`).join("");
  return `
  <li class="cliente vidro sev-${c.severidade} ${c.posicao === 1 ? "primeiro" : ""}" id="cli-${c.codigo}">
    <div class="c-topo">
      <span class="rank" aria-label="Posição ${c.posicao}">${c.posicao}</span>
      <div class="c-nome"><h3>${esc(c.nome)}</h3><p class="sub">${esc(c.categoria)} · ${esc(c.regiao)} · contato: ${esc(c.contato_nome)}</p></div>
      <div class="anel" data-tip="${c.pct_do_vencido}% de tudo o que está vencido hoje é deste cliente">
        <svg viewBox="0 0 40 40" aria-hidden="true"><circle class="fundo" cx="20" cy="20" r="16" fill="none" stroke-width="5"/><circle class="arco" cx="20" cy="20" r="16" fill="none" stroke-width="5" stroke-dasharray="${(c.pct_do_vencido / 100 * circ).toFixed(1)} ${circ.toFixed(1)}"/></svg>
        <span class="t"><b>${c.pct_do_vencido}%</b><span>do vencido</span></span>
      </div>
      <div class="c-valor"><div class="v">${fmtReais(c.valor_vencido_centavos)}</div><div class="l">${c.qtd_vencidos} ${plural(c.qtd_vencidos, "título vencido", "títulos vencidos")}</div></div>
    </div>
    <div class="c-corpo">
      <div><div class="tags">${tags.join("")}</div>
        <div class="motivo">${c.motivo.map(m => `<p>${esc(m)}</p>`).join("")}</div></div>
      <div class="acoes">
        ${botaoLiguei(c.codigo)}
        <button class="btn discreto" type="button" data-acao="dobra" data-tela="hoje" data-cod="${c.codigo}" aria-expanded="${aberto}" aria-controls="dobra-h-${c.codigo}">${aberto ? "Fechar detalhes" : "Detalhes"} ${ICONE.abre}</button>
        <a class="btn discreto" href="#/risco/${c.codigo}">Ver risco</a>
        <a class="btn primario" href="#/regua/${c.codigo}">Cobrar ${ICONE.seta}</a>
      </div>
    </div>
    <div class="dobra" id="dobra-h-${c.codigo}" ${aberto ? "" : "hidden"}><div class="dobra-corpo">
      <p class="frase">${esc(c.frase)}</p>
      <table class="titulos"><thead><tr><th>Título</th><th class="n">Valor</th><th>Vencimento</th><th class="n">Atraso hoje</th></tr></thead><tbody>${titulos}</tbody></table>
    </div></div>
  </li>`;
}

/* =====================================================================
   TELA RISCO
   ===================================================================== */
function telaRisco() {
  const r = R.resumo, cl = R.clientes;
  const conta = f => cl.filter(f).length;
  const opcoes = [
    { id: "todos", rot: "Todos", n: cl.length },
    { id: "alto", rot: "Alto 60+", sev: "critico", n: conta(c => c.nivel === "alto") },
    { id: "medio", rot: "Médio 30–59", sev: "atencao", n: conta(c => c.nivel === "medio") },
    { id: "baixo", rot: "Baixo até 29", sev: "ok", n: conta(c => c.nivel === "baixo") },
    { id: "alerta", rot: "Com alerta", n: conta(c => c.casos_especiais.length) },
    { id: "liguei", rot: "Já liguei", n: conta(c => liguei.has(c.codigo)) },
  ];
  const top = cl.slice(0, 3).map(c => `<b>${esc(c.nome)}</b>`);
  return `
  <section class="hero">
    <div class="brilho-hero">
      <p class="kicker"><span class="tela-nome">Risco por cliente</span>Valor em risco · soma de todos os clientes</p>
      <h1 class="num-hero" data-conta="${r.valor_em_risco_total_centavos}">${fmtReais(r.valor_em_risco_total_centavos)}</h1>
      <p class="hero-sub">É o saldo em aberto de cada cliente multiplicado pelo índice de risco dele. O maior pedaço está em ${top.slice(0, -1).join(", ")} e ${top[top.length - 1]}.</p>
    </div>
    <div class="tiles">
      <div class="tile vidro"><div class="v">${fmtReais(r.saldo_aberto_total_centavos)}</div><div class="l">saldo em aberto total (vencido + a vencer)</div></div>
      <div class="tile vidro"><div class="v">${fmtReais(r.faturamento_total_12m_centavos)}</div><div class="l">faturamento emitido nos últimos 12 meses</div></div>
      <div class="tile vidro"><div class="v">${r.total_clientes}</div><div class="l">clientes na carteira · dados de ${esc(r.data_base)}</div></div>
    </div>
  </section>
  <section aria-labelledby="t-risco">
    <div class="bloco-t"><h2 id="t-risco">Onde está o dinheiro em risco</h2><p>Ordenado por valor em risco (saldo em aberto × índice de risco), não pelo índice puro. Clique em "Ver ficha" para o histórico completo.</p></div>
    <div class="ferramentas">${busca("risco", "Buscar cliente")}${chips("risco", opcoes)}${ordem("risco", [["risco", "Valor em risco"], ["indice", "Índice de risco"], ["saldo", "Saldo em aberto"], ["nome", "Nome"]])}</div>
    <ol class="lista" id="lista-risco">${listaRisco()}</ol>
  </section>
  ${metodo("Como o índice de risco é calculado", `<p>Índice de risco (0-100) combina cinco pesos sobre o histórico de pagamento e compra do próprio cliente — nunca a lista de vencidos de hoje: nível de atraso (${R.pesos.nivel}), previsibilidade (${R.pesos.imprevisibilidade}), mudança de comportamento (${R.pesos.mudanca}), atividade de compra (${R.pesos.compra}) e exposição (${R.pesos.exposicao}). "Saldo em aberto" aqui é tudo que ainda não foi pago (vencido ou não), por isso a ordem desta tela pode diferir da tela Hoje. Meses de atraso que se repetem todo ano em pelo menos 2 anos diferentes são tratados como calendário do negócio do cliente e descontados da conta de tendência. Dados congelados na data de referência da planilha.</p><p style="margin-top:.5rem">A linha pequena de cada cliente é o atraso médio mês a mês nos últimos dois anos; a faixa sombreada é o padrão dele (média ± variação) e o trecho em brasa é onde ele saiu do padrão.</p>`)}`;
}

function listaRisco() {
  const st = estado.risco;
  let l = R.clientes.filter(c => bateBusca("risco", c.nome, c.regiao, c.categoria));
  if (st.filtro === "alerta") l = l.filter(c => c.casos_especiais.length);
  else if (st.filtro === "liguei") l = l.filter(c => liguei.has(c.codigo));
  else if (st.filtro !== "todos") l = l.filter(c => c.nivel === st.filtro);
  const ord = { risco: (a, b) => a.posicao - b.posicao, indice: (a, b) => b.indice_risco - a.indice_risco || a.posicao - b.posicao,
    saldo: (a, b) => b.saldo_aberto_centavos - a.saldo_aberto_centavos, nome: (a, b) => a.nome.localeCompare(b.nome, "pt-BR") }[st.ordem];
  l.sort(ord);
  if (!l.length) return `<li class="vazio vidro">Nenhum cliente com esse filtro.</li>`;
  const max = Math.max(...R.clientes.map(c => c.valor_em_risco_centavos), 1);
  return l.map(c => cartaoRisco(c, max)).join("");
}

function compRow(k) {
  const pct = Math.max(0, Math.min(100, k.pontos / k.peso * 100));
  return `<div class="comp"><div class="rot">${esc(k.rotulo)} <span>(peso ${k.peso})</span></div><div class="trilho"><div style="width:${pct}%"></div></div><div class="pts">${dec(k.pontos)}</div><div class="fr">${esc(k.frase)}</div></div>`;
}

function cartaoRisco(c, max) {
  const nv = NIVEL[c.nivel], aberto = estado.risco.abertos.has(c.codigo);
  const tags = c.casos_especiais.map(k => tagSev(SEV_CASO[k] || "neutro", TAG_CASO[k] || k));
  tags.push(tagLiguei(c.codigo));
  return `
  <li class="cliente vidro sev-${nv.sev}" id="risco-${c.codigo}">
    <div class="r-topo">
      <span class="rank" aria-label="Posição ${c.posicao}">${c.posicao}</span>
      <div class="c-nome"><h3>${esc(c.nome)}</h3><p class="sub">${esc(c.categoria)} · ${esc(c.regiao)} · ${dec(c.share_faturamento_12m)}% do faturamento dos últimos 12 meses</p></div>
      <div class="spark-wrap">${sparkline(c)}<span>atraso por mês</span></div>
      <div class="indice sev-${nv.sev}"><span class="n">${c.indice_risco}</span><span class="t">índice<b>${nv.rot}</b></span></div>
      <div class="c-valor"><div class="v">${fmtReais(c.valor_em_risco_centavos)}</div><div class="l">valor em risco</div></div>
    </div>
    <div class="r-barra" aria-hidden="true"><div style="width:${(c.valor_em_risco_centavos / max * 100).toFixed(1)}%"></div></div>
    <div class="c-corpo">
      <div><div class="tags">${tags.join("")}</div><div class="motivo"><p class="alerta-curto">${esc(c.alerta_curto)}</p></div></div>
      <div class="acoes">
        ${botaoLiguei(c.codigo)}
        ${reguaPor[c.codigo] ? `<a class="btn discreto" href="#/regua/${c.codigo}">Cobrar</a>` : ""}
        <button class="btn discreto" type="button" data-acao="dobra" data-tela="risco" data-cod="${c.codigo}" aria-expanded="${aberto}" aria-controls="dobra-r-${c.codigo}">${aberto ? "Fechar fatores" : "Os 5 fatores"} ${ICONE.abre}</button>
        <button class="btn primario" type="button" data-acao="ficha" data-cod="${c.codigo}">Ver ficha ${ICONE.seta}</button>
      </div>
    </div>
    <div class="dobra" id="dobra-r-${c.codigo}" ${aberto ? "" : "hidden"}><div class="dobra-corpo"><div class="componentes">${c.componentes.map(compRow).join("")}</div></div></div>
  </li>`;
}

function abrirFicha(cod) {
  const cli = riscoPor[cod];
  if (!cli) return;
  const nv = NIVEL[cli.nivel];
  const prazo = cli.prazo_contratado_dias === 0 ? "à vista" : dias(cli.prazo_contratado_dias);
  $("#ficha").innerHTML = `
    <div class="ficha-cab">
      <div><p class="tela-nome">Ficha do cliente</p><h2 id="ficha-titulo">${esc(cli.nome)}</h2>
        <p class="sub">${esc(cli.categoria)} · ${esc(cli.regiao)} · cliente desde ${esc(cli.cliente_desde)} · prazo contratado: ${prazo}</p></div>
      <button class="btn sec" type="button" data-acao="fechar-ficha" aria-label="Fechar a ficha">✕ Fechar</button>
    </div>
    <div class="stats">
      <div class="stat"><div class="v">${cli.media_atraso != null ? dias(Math.round(cli.media_atraso)) : "—"}</div><div class="l">atraso médio</div></div>
      <div class="stat"><div class="v">${cli.desvio_atraso != null ? "±" + dias(Math.round(cli.desvio_atraso)) : "—"}</div><div class="l">variação típica</div></div>
      <div class="stat"><div class="v">${cli.min_atraso != null ? cli.min_atraso + " a " + dias(cli.max_atraso) : "—"}</div><div class="l">atraso mais curto e mais longo</div></div>
      <div class="stat"><div class="v">${cli.n_titulos_pagos}</div><div class="l">títulos pagos no histórico</div></div>
      <div class="stat sev-${nv.sev}"><div class="v" style="color:var(--sev-txt)">${cli.indice_risco} · ${nv.rot}</div><div class="l">índice de risco</div></div>
      <div class="stat"><div class="v">${fmtReais(cli.valor_em_risco_centavos)}</div><div class="l">valor em risco</div></div>
    </div>
    ${graficoFicha(cli)}
    <div class="legenda">
      <span><i class="ponto" style="background:#b9a5ff;border-radius:50%"></i>dentro do padrão</span>
      <span><i class="ponto" style="background:#ff6a45;border-radius:50%"></i>fora do padrão (piora)</span>
      <span><i class="ponto" style="background:#ffc247;border-radius:50%"></i>mês sazonal (descontado)</span>
      <span><i style="background:rgba(143,107,255,.45)"></i>faixa sombreada = média ± desvio histórico</span>
    </div>
    <div class="o-que-fazer"><b>O que fazer</b>${esc(cli.alerta)}</div>
    <div class="componentes">${cli.componentes.map(compRow).join("")}</div>
    <div class="acoes-reg">${reguaPor[cod] ? `<a class="btn primario" href="#/regua/${cod}">Cobrar este cliente ${ICONE.seta}</a>` : ""}<button class="btn sec" type="button" data-acao="fechar-ficha">Fechar</button></div>`;
  const fundo = $("#ficha-fundo");
  fundo.hidden = false;
  document.body.style.overflow = "hidden";
  $("#ficha").scrollTop = 0;
  $("#ficha [data-acao=fechar-ficha]").focus();
}
function fecharFicha() {
  const fundo = $("#ficha-fundo");
  if (fundo.hidden) return;
  fundo.hidden = true;
  document.body.style.overflow = "";
  if (location.hash.startsWith("#/risco/")) history.replaceState(null, "", "#/risco");
}

/* =====================================================================
   TELA PREVISÃO
   ===================================================================== */
function telaPrevisao() {
  const r = P.resumo, w = P.semanas.find(s => s.indice === P.semana_maior_diferenca);
  const aMais = w.diferenca_centavos < 0; // esperado maior que a planilha
  const pctTotal = Math.abs(r.diferenca_centavos / r.planilha_centavos * 100);
  const pctTxt = pctTotal < 0.1 ? "menos de 0,1%" : dec(pctTotal) + "%";
  const total = Math.abs(r.diferenca_pct) < 1
    ? `No total das 4 semanas os dois quase empatam (${pctTxt} de diferença): os títulos já vencidos, que a planilha ignora, compensam quase exatamente os atrasos e o risco que ela não desconta. O que muda é <b>quando</b> o dinheiro entra.`
    : (r.diferenca_centavos >= 0
      ? `No total das 4 semanas, a planilha superestima o caixa em ${pctTxt}: soma o valor cheio de título que, pelo comportamento do cliente, só deve entrar (ou só entra em parte) depois da janela.`
      : `No total das 4 semanas, a planilha subestima o caixa em ${pctTxt}: ela só soma título que vence no período e ignora os já vencidos, mas parte do que já está vencido tende a entrar nessas 4 semanas.`);
  const maxSem = Math.max(...P.semanas.flatMap(s => [s.planilha_centavos, s.esperado_centavos]), 1);
  return `
  <section class="hero">
    <div class="brilho-hero tom-din">
      <p class="kicker"><span class="tela-nome">Previsão de caixa</span>Maior diferença · semana ${w.indice} (${esc(w.inicio)}–${esc(w.fim)})</p>
      <h1 class="num-hero tom-din" data-conta="${Math.abs(w.diferenca_centavos)}" data-prefixo="${aMais ? "+" : "−"}">${aMais ? "+" : "−"}${fmtReais(Math.abs(w.diferenca_centavos))}</h1>
      <p class="hero-sub">${aMais ? `Nessa semana a planilha deixa de contar <b>${fmtReais(Math.abs(w.diferenca_centavos))}</b> que, pelo comportamento dos clientes, devem entrar.` : `Nessa semana a planilha promete <b>${fmtReais(Math.abs(w.diferenca_centavos))}</b> a mais do que deve entrar.`} O valor total quase não se mexe; o dinheiro entra em outra semana.</p>
      <span class="aviso-chip">Considera só os títulos que já existem na carteira hoje — não é projeção de venda nova.</span>
    </div>
    <div>
      <div class="tiles">
        <div class="tile vidro"><div class="v">${fmtReais(r.planilha_centavos)}</div><div class="l">planilha · só vencimento, 4 semanas</div></div>
        <div class="tile vidro"><div class="v" style="color:var(--din-txt)">${fmtReais(r.esperado_centavos)}</div><div class="l">esperado · pelo comportamento, 4 semanas</div></div>
        <div class="tile vidro"><div class="v">${r.diferenca_centavos >= 0 ? "−" : "+"}${fmtReais(Math.abs(r.diferenca_centavos))}</div><div class="l">diferença no total (${pctTxt})</div></div>
      </div>
      <p class="hero-sub" style="margin-top:.8rem;font-size:.92rem">${total}</p>
    </div>
  </section>

  <section aria-labelledby="t-sem">
    <div class="bloco-t"><h2 id="t-sem">Semana a semana</h2><p>Entre ${esc(r.data_base)} e ${esc(r.horizonte_fim)}: ${r.qtd_titulos_no_horizonte} títulos vencem dentro do período (de ${r.qtd_titulos_abertos} em aberto no total — o resto já venceu antes de hoje ou vence depois da janela).</p></div>
    <div class="semanas">${P.semanas.map(s => {
      const mais = s.diferenca_centavos < 0;
      return `<div class="semana vidro ${s.indice === w.indice ? "maior" : ""}">
        <div class="t">Semana ${s.indice}<span>${esc(s.inicio)}–${esc(s.fim)}${s.indice === 1 ? ", inclui hoje" : ""}</span></div>
        <div class="colunas" aria-hidden="true">
          <div class="pl" style="height:${(s.planilha_centavos / maxSem * 100).toFixed(1)}%" data-tip="Planilha: ${esc(fmtReais(s.planilha_centavos))}"></div>
          <div class="es" style="height:${(s.esperado_centavos / maxSem * 100).toFixed(1)}%" data-tip="Esperado: ${esc(fmtReais(s.esperado_centavos))}"></div>
        </div>
        <dl><dt>Planilha</dt><dd>${fmtReais(s.planilha_centavos)}</dd><dt>Esperado</dt><dd style="color:var(--din-txt)">${fmtReais(s.esperado_centavos)}</dd></dl>
        <div class="dif">${mais ? "+" : "−"}${fmtReais(Math.abs(s.diferenca_centavos))}<small>${mais ? "a planilha deixa de contar" : "a planilha conta a mais"}</small></div>
      </div>`; }).join("")}
    </div>
    <div class="legenda"><span><i style="background:var(--planilha)"></i>planilha (soma por vencimento, sem comportamento)</span><span><i style="background:var(--din)"></i>esperado (lendo o comportamento de cada cliente)</span></div>
  </section>

  <section aria-labelledby="t-acum" style="margin-top:1.6rem">
    <div class="bloco-t"><h2 id="t-acum">Acumulado nas próximas 4 semanas</h2><p>A faixa entre otimista e conservador só aparece no acumulado: semana a semana os cenários se cruzam.</p></div>
    <div class="cartao-grafico vidro">${graficoAcumulado()}
      <div class="legenda"><span><i style="background:var(--planilha)"></i>planilha (tracejada: soma por vencimento, sem comportamento)</span><span><i style="background:var(--din)"></i>esperado (lendo o comportamento de cada cliente)</span><span><i style="background:rgba(95,216,255,.3);height:.7rem"></i>faixa entre cenário otimista e conservador</span></div>
    </div>
  </section>

  <section aria-labelledby="t-quem" style="margin-top:1.6rem">
    <div class="bloco-t"><h2 id="t-quem">Quem puxa a diferença</h2><p>Clientes cuja previsão (planilha vs. esperado) mais diverge dentro das 4 semanas.</p></div>
    <div class="ferramentas">${busca("previsao", "Buscar cliente")}${ordem("previsao", [["diferenca", "Maior diferença"], ["esperado", "Valor esperado"], ["nome", "Nome"]])}</div>
    <div class="linhas-cli" id="lista-previsao">${listaPrevisao()}</div>
  </section>

  ${metodo("Como esta previsão é calculada", `<p>Como a data prevista é calculada: vencimento + o atraso que o cliente pratica de verdade. Para quem mudou de comportamento de forma real e recente (mesmo critério da tela Risco), uso a média recente dele, não os 2 anos de histórico. Sobre o valor, aplico uma chance de entrada que cai conforme o título envelhece e conforme o índice de risco do cliente (tela Risco por cliente).</p>
  <p style="margin-top:.5rem">Semana a semana só vai o esperado (central), sem a faixa otimista/conservadora. Motivo: atrasar não faz o dinheiro sumir, só empurra ele para a semana seguinte — então, olhando semana a semana, o cenário otimista de uma semana pode ficar abaixo do conservador da semana seguinte (o que chegou antes "rouba" da semana de depois). A faixa só é honesta no acumulado.</p>
  <ul style="margin-top:.5rem"><li>Estimativa aqui não tem centavo — está tudo arredondado para reais. O valor de cada título em si continua exato, em centavos, por trás da conta.</li>
  <li>Cenário otimista usa o pagamento mais rápido que o cliente já fez; o conservador, o mais lento (para quem piorou de verdade, só os pagamentos dos últimos 90 dias contam).</li>
  <li>Títulos de clientes sem histórico de pagamento suficiente usam a média geral da carteira, marcados como tal no detalhe.</li>
  <li>Esta tela não altera nenhum número das telas Hoje e Risco por cliente — lê o mesmo cálculo de comportamento que elas usam.</li></ul>`)}`;
}

function listaPrevisao() {
  let l = P.clientes.filter(c => bateBusca("previsao", c.nome));
  const ord = { diferenca: (a, b) => Math.abs(b.diferenca_centavos) - Math.abs(a.diferenca_centavos), esperado: (a, b) => b.esperado_centavos - a.esperado_centavos,
    nome: (a, b) => a.nome.localeCompare(b.nome, "pt-BR") }[estado.previsao.ordem];
  l.sort(ord);
  if (!l.length) return `<div class="vazio vidro">Nenhum cliente com essa busca.</div>`;
  return l.map(c => {
    const mais = c.diferenca_centavos < 0;
    return `<div class="linha-cli vidro">
      <div><div class="nome">${esc(c.nome)}</div><div class="sub">${c.usando_recente ? `usa o atraso recente (${Math.round(c.media_recente)} dias), não a média de dois anos (${Math.round(c.media_atraso)} dias) · ` : ""}índice de risco: ${c.indice_risco}</div></div>
      <div class="n">${fmtReais(c.naive_centavos)}<small>planilha</small></div>
      <div class="n" style="color:var(--din-txt)">${fmtReais(c.esperado_centavos)}<small>esperado</small></div>
      <div class="n">${mais ? "+" : "−"}${fmtReais(Math.abs(c.diferenca_centavos))}<small>${mais ? "planilha deixa de contar" : "planilha conta a mais"}</small></div>
    </div>`; }).join("");
}

/* =====================================================================
   TELA RÉGUA (lista de um lado, texto de um cliente só do outro)
   ===================================================================== */
function telaRegua() {
  const cl = G.clientes, st = estado.regua;
  const conta = f => cl.filter(f).length;
  const cobrado = c => c.dias_desde_ultimo_contato !== null && c.dias_desde_ultimo_contato <= 2;
  const opcoes = [
    { id: "todos", rot: "Todos", n: cl.length },
    { id: "critico", rot: "Crítico", sev: "critico", n: conta(c => c.severidade === "critico") },
    { id: "atencao", rot: "Atenção", sev: "atencao", n: conta(c => c.severidade === "atencao") },
    { id: "ok", rot: "No padrão", sev: "ok", n: conta(c => c.severidade === "ok") },
    { id: "cobrados", rot: "Cobrado em 48h", sev: "acao", n: conta(cobrado) },
    { id: "liguei", rot: "Já liguei", n: conta(c => liguei.has(c.codigo)) },
  ];
  if (!st.sel || !reguaPor[st.sel]) st.sel = cl.length ? cl[0].codigo : null;
  return `
  <section class="hero compacto">
    <div class="brilho-hero tom-acao">
      <p class="kicker"><span class="tela-nome">Régua de cobrança</span>Mensagens prontas · ${esc(G.data_base)}</p>
      <div class="linha-num"><h1 class="num-hero tom-acao" data-conta-n="${G.resumo.qtd}">${G.resumo.qtd}</h1>
      <p class="hero-sub">${plural(G.resumo.qtd, "cliente com o texto", "clientes com o texto")} de cobrança já redigido no tom certo para cada caso · <b>${G.resumo.cobrados_48h}</b> ${plural(G.resumo.cobrados_48h, "cobrado", "cobrados")} nas últimas 48 horas.</p></div>
    </div>
    <div class="hero-lado vidro">
      <div class="lado-t">Como usar</div>
      <p class="hero-sub" style="font-size:.92rem">Escolha o cliente → confira o tom (trocar reescreve o texto na hora) → copie e mande pelo seu WhatsApp ou e-mail → registre a cobrança. Quem foi cobrado nas últimas 48 horas desce na fila de Hoje.</p>
    </div>
  </section>
  <section class="regua">
    <aside class="regua-lista vidro" aria-label="Clientes">
      ${busca("regua", "Buscar cliente")}
      ${chips("regua", opcoes)}
      ${ordem("regua", [["prioridade", "Ordem da fila de Hoje"], ["valor", "Valor vencido"], ["nome", "Nome"]])}
      <div id="lista-regua" style="margin-top:.7rem">${listaRegua()}</div>
    </aside>
    <article class="regua-detalhe vidro" id="regua-detalhe" aria-live="polite">${detalheRegua()}</article>
  </section>
  ${metodo("Como a Régua escolhe o tom e registra", `<p>O tom é escolhido a partir dos números (veja a justificativa de cada cliente) — você pode trocar na mão a qualquer momento e o texto é reescrito na hora, sem recarregar a página. "Registrar cobrança" grava o envio à parte da Base_bruta.xlsx (que fica intacta) e atualiza a fila da tela Hoje de verdade — não é só um efeito visual aqui. O relógio usado é o da data de referência da planilha, não o do computador.</p><p style="margin-top:.5rem">A Central redige e copia; quem manda o WhatsApp ou o e-mail é a pessoa. "Registrar cobrança" só funciona quando a Central é aberta pelo computador onde roda o servidor (python servidor.py); no arquivo enviado por e-mail ele fica desligado, com o motivo escrito ao lado.</p>`)}`;
}

function listaRegua() {
  const st = estado.regua, cobrado = c => c.dias_desde_ultimo_contato !== null && c.dias_desde_ultimo_contato <= 2;
  let l = G.clientes.filter(c => bateBusca("regua", c.nome, c.contato_nome));
  if (st.filtro === "cobrados") l = l.filter(cobrado);
  else if (st.filtro === "liguei") l = l.filter(c => liguei.has(c.codigo));
  else if (st.filtro !== "todos") l = l.filter(c => c.severidade === st.filtro);
  const ord = { prioridade: (a, b) => a.posicao - b.posicao, valor: (a, b) => b.valor_vencido_centavos - a.valor_vencido_centavos, nome: (a, b) => a.nome.localeCompare(b.nome, "pt-BR") }[st.ordem];
  l.sort(ord);
  if (!l.length) return `<p class="vazio">Nenhum cliente com esse filtro.</p>`;
  return l.map(c => `
    <button class="item sev-${c.severidade}" type="button" data-acao="sel-regua" data-cod="${c.codigo}" aria-current="${c.codigo === st.sel}">
      <span class="rank">${c.posicao}</span>
      <span class="nm">${esc(c.nome)}</span>
      <span class="vl">${fmtReais(c.valor_vencido_centavos)}</span>
      <span class="mt">${esc(DATA.regua.tons[c.tom_sugerido])}${cobrado(c) ? " · " + (c.dias_desde_ultimo_contato === 0 ? "cobrado hoje" : "cobrado há " + dias(c.dias_desde_ultimo_contato)) : ""}${liguei.has(c.codigo) ? " · já liguei" : ""}</span>
    </button>`).join("");
}

function escolhaRegua(c) {
  const e = estado.regua.escolha;
  if (!e[c.codigo]) e[c.codigo] = { tom: c.tom_sugerido, canal: CANAL_PADRAO_POR_TOM[c.tom_sugerido] || "WhatsApp", texto: null };
  return e[c.codigo];
}

function detalheRegua() {
  const c = reguaPor[estado.regua.sel];
  if (!c) return `<p class="vazio">Escolha um cliente na lista.</p>`;
  const e = escolhaRegua(c);
  if (e.texto == null) e.texto = gerarTexto(c, e.tom, e.canal);
  const tags = [tagSev(c.severidade, SEV_ROTULO[c.severidade])].concat(c.casos_especiais.map(k => tagSev(SEV_CASO[k] || "neutro", TAG_CASO[k] || k)));
  if (c.dias_desde_ultimo_contato !== null && c.dias_desde_ultimo_contato <= 2) tags.push(tagContato(c.dias_desde_ultimo_contato));
  tags.push(tagLiguei(c.codigo));
  const ultimo = c.dias_desde_ultimo_contato === null ? " Sem contato registrado ainda." : (c.dias_desde_ultimo_contato === 0 ? " Último contato: hoje." : ` Último contato: há ${dias(c.dias_desde_ultimo_contato)}.`);
  const hist = c.historico_contatos.map(h => `<tr><td>${esc(h.data_hora)}</td><td>${esc(h.canal)}</td><td>${esc(h.tom_label)}</td><td>${h.valor_cobrado_centavos != null ? fmtReais(h.valor_cobrado_centavos) : "—"}</td><td>${h.origem === "planilha" ? "Da planilha original" : "Registrado na Central"}</td></tr>`).join("");
  return `
    <div class="det-cab">
      <div><p class="tela-nome">${c.posicao}º da fila</p><h2>${esc(c.nome)}</h2><p class="sub">${esc(c.categoria)} · ${esc(c.regiao)} · contato: ${esc(c.contato_nome)}</p></div>
      <div class="c-valor"><div class="v">${fmtReais(c.valor_vencido_centavos)}</div><div class="l">${c.titulos_vencidos.length} ${plural(c.titulos_vencidos.length, "título vencido", "títulos vencidos")}</div></div>
    </div>
    <div class="tags" style="margin-top:.7rem">${tags.join("")}</div>
    <div class="por-que"><b>Por que esse tom:</b> ${esc(c.justificativa_tom)}${ultimo}</div>
    <div class="controles">
      <div><label for="sel-tom">Tom</label><select id="sel-tom" data-tom="${c.codigo}">${Object.entries(G.tons).map(([id, rot]) => `<option value="${id}" ${id === e.tom ? "selected" : ""}>${esc(rot)}${id === c.tom_sugerido ? " (sugerido)" : ""}</option>`).join("")}</select></div>
      <div><label for="sel-canal">Canal</label><select id="sel-canal" data-canal="${c.codigo}">${["WhatsApp", "E-mail", "Telefone"].map(ch => `<option ${ch === e.canal ? "selected" : ""}>${ch}</option>`).join("")}</select></div>
    </div>
    <textarea class="msg" id="texto-msg" data-texto="${c.codigo}" aria-label="Texto da cobrança">${esc(e.texto)}</textarea>
    <div class="acoes-reg">
      <button class="btn primario" type="button" data-acao="copiar-msg">Copiar texto ${ICONE.check}</button>
      <button class="btn sec" type="button" data-acao="registrar" data-cod="${c.codigo}" ${servidor ? "" : "disabled"}>Registrar cobrança</button>
      ${botaoLiguei(c.codigo)}
      <span class="msg-reg" id="msg-reg" role="status"></span>
    </div>
    ${servidor ? "" : `<p class="desligado">Registrar cobrança está desligado neste arquivo: ele não tem onde gravar. Copie o texto e mande normalmente; para registrar, abra a Central no computador onde ela roda com o servidor (python servidor.py).</p>`}
    <details class="hist-d"><summary>Histórico de contato (${c.historico_contatos.length})</summary>
      ${c.historico_contatos.length ? `<table class="hist"><thead><tr><th>Quando</th><th>Canal</th><th>Tom</th><th>Valor</th><th>Origem</th></tr></thead><tbody>${hist}</tbody></table>` : `<p class="hero-sub" style="font-size:.88rem;margin-top:.5rem">Nenhum contato registrado ainda.</p>`}
    </details>`;
}

function ajustarAltura(t) { if (!t) return; t.style.height = "auto"; t.style.height = (t.scrollHeight + 2) + "px"; }

async function registrar(cod) {
  const c = reguaPor[cod], e = escolhaRegua(c), msg = $("#msg-reg"), btn = $("[data-acao=registrar]");
  btn.disabled = true; msg.className = "msg-reg"; msg.textContent = "Registrando…";
  try {
    const resp = await fetch("/api/registrar", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ codigo_cliente: cod, nome_cliente: c.nome, canal: e.canal, tom: e.tom, tom_label: G.tons[e.tom],
        titulos: c.titulos_vencidos.map(t => t.numero), valor_cobrado_centavos: c.valor_vencido_centavos, texto: $("#texto-msg").value }),
    });
    if (!resp.ok) throw new Error(await resp.text());
    msg.className = "msg-reg ok"; msg.textContent = "Registrado. Atualizando a Central…";
    setTimeout(() => location.reload(), 1200);
  } catch (err) {
    msg.className = "msg-reg erro"; msg.textContent = "Não consegui registrar (servidor offline ou com erro). " + err.message;
    btn.disabled = false;
  }
}

/* =====================================================================
   TELA RELATÓRIO
   ===================================================================== */
let textoRelatorio = REL.texto;
function telaRelatorio() {
  const s = REL.semana;
  return `
  <section class="hero">
    <div class="brilho-hero tom-din">
      <p class="kicker"><span class="tela-nome">Relatório da semana</span>Entrou no caixa · ${esc(s.inicio)} a ${esc(s.fim)}</p>
      <h1 class="num-hero tom-din" data-conta="${s.entrou_centavos}">${fmtReais(s.entrou_centavos)}</h1>
      <p class="hero-sub">Dos ${realcarDinheiro(esc(fmtReais(s.previsto_centavos)))} que venceram nessa janela, ${realcarDinheiro(esc(fmtReais(s.nao_entrou_do_previsto_centavos)))} ainda não foram pagos. Abaixo, o texto para a diretoria: quatro minutos de leitura, terminando em decisão.</p>
    </div>
    <div class="hero-lado vidro">
      <div class="lado-t">Para mandar</div>
      <div class="rel-acoes">
        <button class="btn primario" type="button" data-acao="copiar-rel">Copiar texto ${ICONE.check}</button>
        <button class="btn sec" type="button" data-acao="baixar-rel">Baixar .txt</button>
        ${servidor ? `<button class="btn sec" type="button" data-acao="atualizar-rel">Atualizar com os registros de hoje</button>` : ""}
      </div>
      <p class="hero-sub" id="rel-status" style="font-size:.86rem">${servidor ? "Texto montado a partir dos números atuais da Central." : "Neste arquivo o texto é o do momento em que ele foi gerado (dados de " + esc(DATA.referencia) + "). Cobranças registradas depois só entram abrindo a Central pelo servidor."}</p>
    </div>
  </section>
  <div class="rel-grade">
    <article class="papel vidro" id="papel">${papel(textoRelatorio)}</article>
    <aside class="rel-numeros" aria-label="Os números que o texto cita">
      <p class="kicker">Os números do texto</p>
      <div class="tile vidro"><div class="v">${fmtReais(H.resumo.total_vencido_centavos)}</div><div class="l">vencidos hoje, em ${H.resumo.qtd_titulos_vencidos} títulos</div></div>
      <div class="tile vidro"><div class="v">${fmtReais(R.resumo.valor_em_risco_total_centavos)}</div><div class="l">em risco na carteira toda</div></div>
      <div class="tile vidro"><div class="v" style="color:var(--din-txt)">${fmtReais(P.resumo.esperado_centavos)}</div><div class="l">esperados nas próximas 4 semanas</div></div>
      <div class="tile vidro"><div class="v">${H.fila.length}</div><div class="l">clientes na lista do que fazer (os 5 primeiros vão no texto)</div></div>
    </aside>
  </div>
  ${metodo("Como este relatório é feito", `<p>Texto corrido para a diretoria, pronto para colar num e-mail ou mensagem — sem gráfico, sem precisar abrir a Central. Não recalcula nada: lê os mesmos números que as telas Hoje, Risco por cliente, Previsão de caixa e Régua de cobrança já mostram, congelados na data de referência da planilha. Todo valor em reais aparece em destaque para achar os números sem ler.</p>`)}`;
}
function papel(texto) {
  const linhas = texto.split("\n").filter(l => l.trim());
  return linhas.map((l, i) => {
    const e = realcarDinheiro(esc(l));
    if (i === 0) return `<p class="ln h titulo">${e}</p>`;
    if (/^[A-ZÁÉÍÓÚÂÊÔÃÕÇ ,()]+:$/.test(l.trim()) || (l === l.toUpperCase() && /[A-Z]/.test(l) && l.length > 20)) return `<p class="ln h">${e}</p>`;
    const m = l.match(/^(\d+)\.\s(.*)$/);
    if (m) return `<p class="ln item"><span class="num">${m[1]}.</span> ${realcarDinheiro(esc(m[2]))}</p>`;
    return `<p class="ln">${e}</p>`;
  }).join("");
}

/* =====================================================================
   COPIAR / BAIXAR
   ===================================================================== */
async function copiar(texto, botao) {
  let ok = false;
  try { await navigator.clipboard.writeText(texto); ok = true; } catch (e) {
    const t = document.createElement("textarea"); t.value = texto; t.style.position = "fixed"; t.style.opacity = "0";
    document.body.appendChild(t); t.select(); try { ok = document.execCommand("copy"); } catch (e2) { ok = false; } t.remove();
  }
  if (botao) { const orig = botao.innerHTML; botao.textContent = ok ? "Copiado!" : "Não consegui copiar: selecione e copie à mão"; setTimeout(() => { botao.innerHTML = orig; }, 1800); }
}
function baixar(texto) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([texto], { type: "text/plain;charset=utf-8" }));
  a.download = `relatorio_aurora_${DATA.referencia.split("/").reverse().join("-")}.txt`;
  document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
}

/* =====================================================================
   ROTEAMENTO, EVENTOS E ANIMAÇÃO
   ===================================================================== */
const TELAS = { hoje: [telaHoje, "Hoje"], risco: [telaRisco, "Risco por cliente"], previsao: [telaPrevisao, "Previsão de caixa"], regua: [telaRegua, "Régua de cobrança"], relatorio: [telaRelatorio, "Relatório da semana"] };
let telaAtual = null;

function desenhar(manterRolagem) {
  const y = window.scrollY;
  $("#tela").innerHTML = TELAS[telaAtual][0]();
  if (telaAtual === "regua") ajustarAltura($("#texto-msg"));
  ajustarNumeros();
  if (manterRolagem) window.scrollTo(0, y);
}

function rotear() {
  const partes = (location.hash || "#/hoje").replace(/^#\/?/, "").split("/");
  const nome = TELAS[partes[0]] ? partes[0] : "hoje", arg = partes[1] ? Number(partes[1]) : null;
  const mesmaTela = nome === telaAtual;
  if (nome === "regua" && arg) estado.regua.sel = arg;
  if (!(mesmaTela && nome === "risco")) { telaAtual = nome; desenhar(mesmaTela); if (!mesmaTela) { window.scrollTo(0, 0); animarNumeros(); } }
  document.title = TELAS[nome][1] + " · Central de Crédito e Cobrança · Aurora";
  document.querySelectorAll(".dock a").forEach(a => { if (a.dataset.rota === nome) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
  if (nome === "risco" && arg) abrirFicha(arg); else fecharFicha();
  if (!mesmaTela) $("#tela").focus({ preventScroll: true });
}

function ajustarNumeros() {
  // o número grande nunca é cortado: se não couber na coluna, encolhe até caber
  // mede sempre com o valor FINAL (durante a contagem o número é mais curto e enganaria a medida)
  document.querySelectorAll(".num-hero").forEach(el => {
    if (!el.dataset.final) el.dataset.final = el.textContent;
    const exibido = el.textContent;
    el.textContent = el.dataset.final; el.style.fontSize = "";
    const livre = el.parentElement.clientWidth;
    if (el.scrollWidth > livre) el.style.fontSize = (parseFloat(getComputedStyle(el).fontSize) * livre / el.scrollWidth * 0.97) + "px";
    el.textContent = exibido;
  });
}

function animarNumeros() {
  if (movimentoReduzido) return;
  document.querySelectorAll("[data-conta], [data-conta-n]").forEach(el => {
    const ehDinheiro = el.hasAttribute("data-conta");
    const fim = Number(ehDinheiro ? el.dataset.conta : el.dataset.contaN), pref = el.dataset.prefixo || "";
    const final = el.dataset.final || el.textContent, t0 = performance.now(), dur = 1100;
    const passo = agora => {
      if (!el.isConnected) return;
      const k = Math.min(1, (agora - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      el.textContent = k >= 1 ? final : pref + (ehDinheiro ? fmtReais(fim * e) : String(Math.round(fim * e)));
      if (k < 1) requestAnimationFrame(passo);
    };
    requestAnimationFrame(passo);
  });
}

document.addEventListener("click", ev => {
  const alvo = ev.target.closest("[data-acao]");
  if (ev.target.id === "ficha-fundo") { fecharFicha(); return; }
  if (!alvo) return;
  const acao = alvo.dataset.acao, cod = Number(alvo.dataset.cod);
  if (acao === "filtro") { estado[alvo.dataset.tela].filtro = alvo.dataset.valor; desenhar(true); }
  else if (acao === "liguei") { alternarLiguei(cod); desenhar(true); }
  else if (acao === "dobra") {
    const ab = estado[alvo.dataset.tela].abertos; ab.has(cod) ? ab.delete(cod) : ab.add(cod); desenhar(true);
  }
  else if (acao === "ficha") { history.replaceState(null, "", "#/risco/" + cod); abrirFicha(cod); }
  else if (acao === "fechar-ficha") fecharFicha();
  else if (acao === "sel-regua") {
    estado.regua.sel = cod; history.replaceState(null, "", "#/regua/" + cod);
    $("#lista-regua").innerHTML = listaRegua(); $("#regua-detalhe").innerHTML = detalheRegua(); ajustarAltura($("#texto-msg"));
    if (window.innerWidth <= 1100) $("#regua-detalhe").scrollIntoView({ behavior: movimentoReduzido ? "auto" : "smooth", block: "start" });
  }
  else if (acao === "copiar-msg") copiar($("#texto-msg").value, alvo);
  else if (acao === "registrar") registrar(cod);
  else if (acao === "copiar-rel") copiar(textoRelatorio, alvo);
  else if (acao === "baixar-rel") baixar(textoRelatorio);
  else if (acao === "atualizar-rel") {
    fetch("/api/relatorio", { cache: "no-store" }).then(r => r.json()).then(j => {
      if (j.texto) { textoRelatorio = j.texto; $("#papel").innerHTML = papel(textoRelatorio); $("#rel-status").textContent = "Atualizado agora, com os números atuais da Central."; }
    }).catch(() => { $("#rel-status").textContent = "Não consegui atualizar: o servidor não respondeu."; });
  }
});

document.addEventListener("input", ev => {
  const t = ev.target;
  if (t.dataset.busca) {
    const tela = t.dataset.busca; estado[tela].busca = t.value;
    const alvo = { hoje: ["#lista-hoje", listaHoje], risco: ["#lista-risco", listaRisco], previsao: ["#lista-previsao", listaPrevisao], regua: ["#lista-regua", listaRegua] }[tela];
    $(alvo[0]).innerHTML = alvo[1]();
  } else if (t.dataset.texto) {
    escolhaRegua(reguaPor[Number(t.dataset.texto)]).texto = t.value; ajustarAltura(t);
  }
});

document.addEventListener("change", ev => {
  const t = ev.target;
  if (t.dataset.ordem) { estado[t.dataset.ordem].ordem = t.value; desenhar(true); }
  else if (t.dataset.tom || t.dataset.canal) {
    const c = reguaPor[Number(t.dataset.tom || t.dataset.canal)], e = escolhaRegua(c);
    if (t.dataset.tom) { e.tom = t.value; e.canal = CANAL_PADRAO_POR_TOM[e.tom] || "WhatsApp"; } else e.canal = t.value;
    e.texto = gerarTexto(c, e.tom, e.canal);
    $("#regua-detalhe").innerHTML = detalheRegua(); ajustarAltura($("#texto-msg"));
  }
});

document.addEventListener("keydown", ev => { if (ev.key === "Escape") fecharFicha(); });

/* dicas ao passar o mouse (gráficos, anéis) */
const dica = $("#dica");
document.addEventListener("mouseover", ev => {
  const el = ev.target.closest("[data-tip]");
  if (!el) { dica.hidden = true; return; }
  dica.textContent = el.dataset.tip; dica.hidden = false;
});
document.addEventListener("mousemove", ev => {
  if (dica.hidden) return;
  const x = Math.min(ev.clientX + 14, window.innerWidth - dica.offsetWidth - 8), y = Math.max(8, ev.clientY - dica.offsetHeight - 12);
  dica.style.left = x + "px"; dica.style.top = y + "px";
});
window.addEventListener("resize", () => { ajustarAltura($("#texto-msg")); ajustarNumeros(); });
window.addEventListener("hashchange", rotear);

/* início */
$("#selo-ref").textContent = "Dados de " + DATA.referencia;
rotear();
if (document.fonts && document.fonts.ready) document.fonts.ready.then(ajustarNumeros);
verificarServidor().then(on => {
  servidor = on;
  const selo = $("#selo-servidor");
  selo.textContent = on ? "servidor conectado" : "arquivo offline · registrar desligado";
  selo.className = "selo " + (on ? "on" : "off");
  selo.title = on ? "Registrar cobrança grava de verdade e atualiza a fila." : "Este arquivo abre sem servidor: dá para ler, filtrar, copiar e marcar \"já liguei\"; registrar cobrança fica desligado.";
  if (telaAtual === "regua" || telaAtual === "relatorio") desenhar(true);
});
