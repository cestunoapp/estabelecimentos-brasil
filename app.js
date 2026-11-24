// Busca de estabelecimentos: baixa o índice (estados e cidades) e, depois, só a cidade escolhida.
"use strict";
const UF_NOME = { AC: "Acre", AL: "Alagoas", AP: "Amapá", AM: "Amazonas", BA: "Bahia", CE: "Ceará", DF: "Distrito Federal", ES: "Espírito Santo", GO: "Goiás", MA: "Maranhão", MT: "Mato Grosso", MS: "Mato Grosso do Sul", MG: "Minas Gerais", PA: "Pará", PB: "Paraíba", PR: "Paraná", PE: "Pernambuco", PI: "Piauí", RJ: "Rio de Janeiro", RN: "Rio Grande do Norte", RS: "Rio Grande do Sul", RO: "Rondônia", RR: "Roraima", SC: "Santa Catarina", SP: "São Paulo", SE: "Sergipe", TO: "Tocantins" };
const TIPO = { hiper: ["Hipermercado", "super"], super: ["Supermercado", "super"], atacarejo: ["Atacarejo", "atacarejo"], mini: ["Minimercado", "mini"], farmacia: ["Farmácia", "farmacia"] };
const POR_PAGINA = 100;
const $ = id => document.getElementById(id);
const el = { uf: $("uf"), cidade: $("cidade"), texto: $("texto"), tipos: $("tipos"), estado: $("estado"), lista: $("lista"), mais: $("mais"), fonte: $("fonte"), baixar: $("baixar") };
let indice = null, linhas = [], filtradas = [], mostradas = 0, pedido = 0;

const normal = s => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const fmtCnpj = c => c.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5");
const fmtCep = c => c ? c.replace(/^(\d{5})(\d{3})$/, "$1-$2") : "";
const fmtNum = n => n.toLocaleString("pt-BR");
const mesBR = m => { const [a, b] = (m || "").split("-"); const nomes = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]; return b ? `${nomes[Number(b) - 1]} de ${a}` : ""; };

function lerHash() { const p = new URLSearchParams(location.hash.slice(1)); return { uf: p.get("uf") || "", cidade: p.get("cidade") || "", q: p.get("q") || "", tipos: p.get("tipos") }; }
function gravarHash() {
  const p = new URLSearchParams();
  if (el.uf.value) p.set("uf", el.uf.value);
  if (el.cidade.value) p.set("cidade", el.cidade.value);
  if (el.texto.value.trim()) p.set("q", el.texto.value.trim());
  const marcados = tiposMarcados();
  if (marcados.length !== 4) p.set("tipos", marcados.join(","));
  history.replaceState(null, "", p.toString() ? "#" + p : location.pathname);
}
const tiposMarcados = () => [...el.tipos.querySelectorAll("input:checked")].map(i => i.value);

async function json(url) { const r = await fetch(url, { cache: "no-cache" }); if (!r.ok) throw new Error(r.status); return r.json(); }

async function iniciar() {
  try { indice = await json("dados/indice.json"); }
  catch (e) { el.estado.textContent = "Não foi possível carregar os dados agora. Tente de novo em alguns minutos."; return; }
  if (indice.receita_mes) el.fonte.textContent = `Dados da Receita Federal de ${mesBR(indice.receita_mes)} e do IBGE (CNEFE, Censo 2022). Só estabelecimentos ativos; sem MEI nem Empresário Individual.`;
  if (indice.versao) el.baixar.href = `https://github.com/${indice.repo}/releases/tag/${indice.versao}`;
  const ufs = Object.keys(indice.estados).sort((a, b) => UF_NOME[a].localeCompare(UF_NOME[b]));
  el.uf.innerHTML = `<option value="">Escolha o estado</option>` + ufs.map(u => `<option value="${u}">${UF_NOME[u]} (${fmtNum(indice.estados[u].total)})</option>`).join("");
  el.uf.disabled = false;
  const h = lerHash();
  if (h.tipos) el.tipos.querySelectorAll("input").forEach(i => { i.checked = h.tipos.split(",").includes(i.value); });
  el.texto.value = h.q;
  if (h.uf && indice.estados[h.uf]) { el.uf.value = h.uf; preencherCidades(); if (h.cidade) { el.cidade.value = h.cidade; await carregarCidade(); } }
  else el.estado.textContent = "Escolha o estado e a cidade para ver os estabelecimentos.";
}

function preencherCidades() {
  const e = indice.estados[el.uf.value];
  linhas = []; filtradas = []; el.lista.innerHTML = ""; el.mais.hidden = true;
  if (!e) { el.cidade.innerHTML = `<option value="">Escolha o estado</option>`; el.cidade.disabled = true; travar(true); return; }
  el.cidade.innerHTML = `<option value="">Escolha a cidade</option>` + e.cidades.map(c => `<option value="${c[1]}">${esc(c[0])} (${fmtNum(c[2])})</option>`).join("");
  el.cidade.disabled = false; travar(true);
  el.estado.textContent = `${fmtNum(e.total)} estabelecimentos em ${UF_NOME[el.uf.value]}. Escolha a cidade.`;
}
const travar = sim => { el.texto.disabled = sim; el.tipos.disabled = sim; };

async function carregarCidade() {
  const uf = el.uf.value, arq = el.cidade.value, meu = ++pedido;
  gravarHash();
  if (!uf || !arq) { linhas = []; mostrar(); return; }
  el.estado.textContent = "Carregando…"; el.lista.setAttribute("aria-busy", "true");
  try { const d = await json(`dados/${uf}/${arq}.json`); if (meu !== pedido) return; linhas = d.map(x => ({ x, busca: normal([x[1], x[3], x[4], x[0], fmtCnpj(x[0]), x[5]].join(" ")) })); }
  catch (e) { if (meu === pedido) { linhas = []; el.estado.textContent = "Não foi possível carregar esta cidade. Tente de novo."; } return; }
  finally { el.lista.removeAttribute("aria-busy"); }
  travar(false); filtrar();
}

function filtrar() {
  const tipos = new Set(tiposMarcados()); if (tipos.has("super")) tipos.add("hiper");
  const termos = normal(el.texto.value).replace(/[./-]/g, " ").split(/\s+/).filter(Boolean);
  const termosNum = el.texto.value.replace(/\D/g, "");
  filtradas = linhas.filter(l => tipos.has(l.x[2]) && (termosNum.length >= 8 && l.x[0].includes(termosNum) || termos.every(t => l.busca.includes(t))));
  mostradas = 0; el.lista.innerHTML = ""; gravarHash(); mostrar();
}

function mostrar() {
  if (!linhas.length) { el.mais.hidden = true; return; }
  const parte = filtradas.slice(mostradas, mostradas + POR_PAGINA);
  el.lista.insertAdjacentHTML("beforeend", parte.map(cartao).join(""));
  mostradas += parte.length;
  const cid = el.cidade.options[el.cidade.selectedIndex]?.text.replace(/ \([\d.]+\)$/, "") || "";
  el.estado.textContent = filtradas.length ? `${fmtNum(filtradas.length)} ${filtradas.length === 1 ? "estabelecimento" : "estabelecimentos"} em ${cid}${mostradas < filtradas.length ? ` · mostrando ${fmtNum(mostradas)}` : ""}.` : "Nenhum estabelecimento com esses filtros. Tente outro nome ou marque mais tipos.";
  el.mais.hidden = mostradas >= filtradas.length;
}

const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
function cartao({ x }) {
  const [cnpj, nome, tipo, end, bairro, cep, lat, lng, prec] = x;
  const [rotulo, cor] = TIPO[tipo] || [tipo, "super"];
  const mapa = lat != null ? `<a href="https://www.openstreetmap.org/?mlat=${lat}&amp;mlon=${lng}#map=18/${lat}/${lng}" target="_blank" rel="noopener">Ver no mapa${prec === "cep" ? " (aproximado)" : ""}</a>` : "";
  return `<li class="item"><h2>${esc(nome || "Sem nome fantasia")} <span class="tipo" style="--cor: var(--t-${cor})">${rotulo}</span></h2>
    <p class="end">${esc(end)}${cep ? " · CEP " + fmtCep(cep) : ""}</p>
    <p class="meta"><span>CNPJ ${fmtCnpj(cnpj)}</span>${mapa}</p></li>`;
}

let espera;
el.uf.addEventListener("change", () => { el.cidade.value = ""; preencherCidades(); gravarHash(); });
el.cidade.addEventListener("change", carregarCidade);
el.texto.addEventListener("input", () => { clearTimeout(espera); espera = setTimeout(filtrar, 150); });
el.tipos.addEventListener("change", filtrar);
el.mais.addEventListener("click", mostrar);
iniciar();
