#!/usr/bin/env python3
"""Estabelecimentos do Brasil · Receita Federal (CNPJ) + IBGE (CNEFE).

Roda no GitHub Actions deste repositório, uma vez por mês, em três passos:
  receita     baixa a base de CNPJ da Receita (dados abertos), separa os estabelecimentos ATIVOS dos tipos
              de interesse (tipos abaixo e o arquivo incluir.csv) e grava parcial/UF.json.gz (sem posição);
  posicionar  para um estado: acha a posição de cada um pelo endereço, com o CNEFE do Censo 2022 (IBGE):
              número exato na rua, senão o número mais perto no mesmo CEP, senão o centro do CEP;
              grava saida/UF.csv.gz;
  indice      grava saida/indice.json (mês da Receita, quantidades e impressão digital de cada arquivo).

LGPD: só lê CNPJ, nome fantasia, situação, CNAE e endereço do estabelecimento. Não lê razão social
(que, no MEI, traz nome e CPF do dono), sócios, telefone nem e-mail. Sequências longas de números
(possível CPF) são tiradas do nome. MEI fica de fora por inteiro (arquivo Simples da Receita): o nome
fantasia de um MEI costuma ser o nome do dono e o endereço, a casa dele. Pelo mesmo motivo, o Empresário
Individual (natureza jurídica 213-5, arquivo Empresas da Receita: só a natureza é lida) também fica de fora.
Sequências longas de números também são tiradas do endereço.

Só usa a biblioteca padrão do Python.
"""
import argparse, base64, csv, gzip, hashlib, io, json, os, re, sys, tempfile, time, unicodedata, urllib.parse, urllib.request, zipfile

UA = "estabelecimentos-brasil/1.0 (+https://github.com/cestunoapp/estabelecimentos-brasil)"
# Desde 2026 a Receita publica num Nextcloud (link público de compartilhamento). Formato do endereço:
#   nextcloud:<servidor>|<código do link>|<pasta>     (os antigos, de pasta comum, ficam de reserva)
RECEITA_BASES = [
    "nextcloud:https://arquivos.receitafederal.gov.br|gn672Ad4CF8N6TK|/Dados/Cadastros/CNPJ",
    "https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/",
    "https://dadosabertos.rfb.gov.br/CNPJ/dados_abertos_cnpj/",
]
CNEFE_BASE = "https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/Censo_Demografico_2022/Arquivos_CNEFE/CSV/UF/"
UFS = "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
# Tipo de cada atividade principal (CNAE). Atacarejo: atacado de alimentos (4639-7/01) que também tem
# hiper/supermercado como atividade secundária. Para um tipo novo, acrescente aqui (e no README).
CNAE_TIPO = {"4711301": "hiper", "4711302": "super", "4712100": "mini",
             "4771701": "farmacia", "4771702": "farmacia"}
TIPOS = ("hiper", "super", "atacarejo", "mini", "farmacia")
VAREJO = {"4711301", "4711302"}
csv.field_size_limit(10_000_000)

# ---------- texto ----------
MINUSC = {"de", "da", "do", "das", "dos", "e", "em", "na", "no"}
SIGLAS = {"ltda", "me", "epp", "eireli", "sa", "s/a"}
def titulo(s):
    out = []
    for i, w in enumerate(s.lower().split()):
        if w in SIGLAS: continue
        out.append(w if (i and w in MINUSC) else w[:1].upper() + w[1:])
    return " ".join(out)

def limpar_nome(fantasia):
    """Nome fantasia em 'Título', sem números longos (possível CPF/CNPJ) nem siglas de empresa."""
    s = re.sub(r"\d[\d.\-/ ]{6,}\d", " ", fantasia or "")
    s = re.sub(r"[^\w&'. -]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip(" .-")
    if len(s) < 2 or not re.search(r"[A-Za-zÀ-ÿ]", s): return None
    return titulo(s)[:80] or None

def so_digitos(s): return re.sub(r"\D", "", s or "")

def numero(s):
    d = so_digitos(s)
    return d.lstrip("0") or None

def sem_numeros_longos(s):
    """Tira sequências longas de números (código de medidor, de lote, possível CPF) de um texto."""
    return re.sub(r"\s+", " ", re.sub(r"[\w-]*\d[\d.\-/ ]{8,}\d[\w-]*", " ", s or "")).strip()

def montar_endereco(tipo, logradouro, num, bairro):
    rua = titulo(sem_numeros_longos(" ".join(x for x in [tipo or "", logradouro or ""] if x).strip()))
    bairro = sem_numeros_longos(bairro)
    if not rua: return None
    n = numero(num)
    end = rua + ", " + (n if n else "s/n")
    if bairro and bairro.strip(): end += " - " + titulo(bairro.strip())
    return end[:160]

def plano(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()

# ---------- Receita ----------
def ler_incluir(caminho):
    """incluir.csv: estabelecimentos com outra atividade principal que devem entrar (cnpj;tipo;observacao)."""
    out = {}
    if not caminho or not os.path.exists(caminho): return out
    with open(caminho, encoding="utf-8") as f:
        for l in csv.DictReader((x for x in f if not x.startswith("#")), delimiter=";"):
            c, t = so_digitos(l.get("cnpj")), (l.get("tipo") or "").strip().lower()
            if len(c) == 14 and t in TIPOS: out[c] = t
    return out

def escolher(linha, incluir=None, cnpj=None):
    """Devolve o tipo se o estabelecimento interessa, ou None."""
    if len(linha) < 21 or linha[5].strip() != "02": return None   # 02 = ativa
    if incluir and cnpj in incluir: return incluir[cnpj]
    principal = linha[11].strip()
    if principal in CNAE_TIPO: return CNAE_TIPO[principal]
    if principal == "4639701":
        secund = set(x.strip() for x in linha[12].split(",") if x.strip())
        if secund & VAREJO: return "atacarejo"
    return None

def ler_estabelecimentos(arquivo_texto, municipios, ufs, saida, incluir=None):
    """Lê um CSV de Estabelecimentos (texto latin-1, separador ';') e junta em saida[UF]."""
    n = 0
    for linha in csv.reader(arquivo_texto, delimiter=";", quotechar='"'):
        if len(linha) < 21: continue
        cnpj = so_digitos(linha[0]).zfill(8) + so_digitos(linha[1]).zfill(4) + so_digitos(linha[2]).zfill(2)
        tipo = escolher(linha, incluir, cnpj)
        if not tipo: continue
        uf = linha[19].strip().upper()
        if uf not in ufs or len(cnpj) != 14: continue
        saida.setdefault(uf, []).append({
            "cnpj": cnpj, "tipo": tipo, "cnae": linha[11].strip(), "nome": limpar_nome(linha[4]),
            "endereco": montar_endereco(linha[13], linha[14], linha[15], linha[17]),
            "bairro": titulo(sem_numeros_longos(linha[17])) or None,
            "cep": so_digitos(linha[18])[:8], "num": numero(linha[15]),
            "cidade": titulo(municipios.get(linha[20].strip(), "")) or None, "uf": uf})
        n += 1
    return n

def ler_mei(arquivo_texto, basicos):
    """CNPJs básicos (8 dígitos) que são MEI, entre os pedidos. Arquivo Simples: coluna 4 = opção pelo MEI."""
    mei = set()
    for l in csv.reader(arquivo_texto, delimiter=";", quotechar='"'):
        if len(l) >= 5 and l[4].strip().upper() == "S":
            b = so_digitos(l[0]).zfill(8)
            if b in basicos: mei.add(b)
    return mei

def tirar_mei(por_uf, mei):
    """Tira os estabelecimentos de MEI. Devolve quantos saíram."""
    n = 0
    for uf in list(por_uf):
        antes = len(por_uf[uf])
        por_uf[uf] = [e for e in por_uf[uf] if e["cnpj"][:8] not in mei]
        n += antes - len(por_uf[uf])
    return n

def ler_municipios(arquivo_texto):
    return {l[0].strip(): l[1].strip() for l in csv.reader(arquivo_texto, delimiter=";", quotechar='"') if len(l) >= 2}

# ---------- CNEFE (IBGE) ----------
def coord(s):
    try: return float(str(s).replace(",", "."))
    except ValueError: return None

def ler_cnefe(arquivo_texto, ceps):
    """Posições dos endereços dos CEPs pedidos: {(cep, numero): (lat, lng)} e centro de cada CEP."""
    leitor = csv.reader(arquivo_texto, delimiter=";", quotechar='"')
    cab = [c.strip().upper() for c in next(leitor)]
    i_cep, i_num, i_lat, i_lng = (cab.index(c) for c in ("CEP", "NUM_ENDERECO", "LATITUDE", "LONGITUDE"))
    exato, soma = {}, {}
    for l in leitor:
        if len(l) <= max(i_cep, i_num, i_lat, i_lng): continue
        cep = so_digitos(l[i_cep])[:8]
        if cep not in ceps: continue
        la, ln = coord(l[i_lat]), coord(l[i_lng])
        if la is None or ln is None or not (-34 <= la <= 6 and -74 <= ln <= -28): continue
        n = numero(l[i_num])
        if n: exato.setdefault((cep, n), (la, ln))
        s = soma.setdefault(cep, [0.0, 0.0, 0, {}]); s[0] += la; s[1] += ln; s[2] += 1
        if n and n.isdigit(): s[3].setdefault(int(n), (la, ln))
    centro = {c: (v[0] / v[2], v[1] / v[2]) for c, v in soma.items() if v[2]}
    numeros = {c: v[3] for c, v in soma.items()}
    return exato, centro, numeros

def posicionar(est, exato, centro, numeros):
    """Põe lat, lng e precisão em cada estabelecimento."""
    for e in est:
        e["lat"] = e["lng"] = e["precisao"] = None
        cep, n = e["cep"], e["num"]
        if n and (cep, n) in exato:
            e["lat"], e["lng"] = exato[(cep, n)]; e["precisao"] = "endereco"; continue
        if n and n.isdigit() and numeros.get(cep):
            alvo = int(n)
            perto = min(numeros[cep], key=lambda x: abs(x - alvo))
            if abs(perto - alvo) <= 200:
                e["lat"], e["lng"] = numeros[cep][perto]; e["precisao"] = "rua"; continue
        if cep in centro:
            e["lat"], e["lng"] = centro[cep]; e["precisao"] = "cep"
    return est

COLUNAS = ["cnpj", "nome", "tipo", "cnae", "endereco", "bairro", "cep", "cidade", "uf", "lat", "lng", "precisao"]

def gravar(est, caminho):
    """CSV (UTF-8, separador ';') compactado com gzip, um estabelecimento por CNPJ, em ordem de CNPJ."""
    vistos, n = set(), 0
    # mtime=0: o mesmo conteúdo dá sempre o mesmo arquivo (e a mesma impressão digital)
    with open(caminho, "wb") as bruto, gzip.GzipFile(fileobj=bruto, mode="wb", compresslevel=9, mtime=0, filename="") as gz, \
         io.TextIOWrapper(gz, encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(COLUNAS)
        for e in sorted(est, key=lambda x: x["cnpj"]):
            if e["cnpj"] in vistos: continue
            vistos.add(e["cnpj"]); n += 1
            w.writerow([e["cnpj"], e["nome"] or "", e["tipo"], e.get("cnae") or "", e["endereco"] or "", e.get("bairro") or "",
                        e.get("cep") or "", e["cidade"] or "", e["uf"],
                        "" if e["lat"] is None else round(e["lat"], 6), "" if e["lng"] is None else round(e["lng"], 6),
                        e["precisao"] or ""])
    return n

# ---------- download ----------
def baixar(url, destino, tentativas=4, cab=None):
    for t in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, **(cab or {})})
            with urllib.request.urlopen(req, timeout=300) as r, open(destino, "wb") as f:
                while True:
                    b = r.read(1 << 20)
                    if not b: break
                    f.write(b)
            return destino
        except Exception as e:  # noqa: BLE001
            print(f"  falhou ({e}); tentando de novo", file=sys.stderr)
            time.sleep(10 * (t + 1))
    raise SystemExit("Não consegui baixar " + url)

def listar(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode("utf-8", "ignore")

def meses_do_webdav(xml):
    # <d:href>/public.php/webdav/Dados/Cadastros/CNPJ/2026-10/</d:href>
    return sorted(set(re.findall(r"/(\d{4}-\d{2})/?</(?:[a-z]+:)?href>", xml, re.I)))

def propfind(url, cab):
    req = urllib.request.Request(url, method="PROPFIND", headers={"User-Agent": UA, "Depth": "1", **cab})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode("utf-8", "ignore")

def pasta_nextcloud(base):
    servidor, codigo, pasta = base[len("nextcloud:"):].split("|")
    servidor, pasta = servidor.rstrip("/"), "/" + pasta.strip("/")
    q = urllib.parse.quote(pasta)
    # dois jeitos que o Nextcloud aceita para link público: o novo (sem senha) e o antigo (código como usuário)
    tentativas = [
        (f"{servidor}/public.php/dav/files/{codigo}{q}/", {}),
        (f"{servidor}/public.php/webdav{q}/", {"Authorization": "Basic " + base64.b64encode((codigo + ":").encode()).decode()}),
    ]
    erros = []
    for url, cab in tentativas:
        try:
            meses = meses_do_webdav(propfind(url, cab))
            if meses: return [(url + m + "/", cab) for m in reversed(meses[-2:])]
            erros.append(url + ": nenhuma pasta de mês")
        except Exception as e:  # noqa: BLE001
            erros.append(f"{url}: {e}")
    raise RuntimeError("; ".join(erros))

def pastas_mais_novas(bases):
    """Devolve as pastas dos 2 meses mais novos (o mais novo primeiro), com os cabeçalhos para baixar.
    A Receita publica o mês aos poucos: enquanto a pasta nova está incompleta, usa a do mês anterior."""
    for base in bases:
        try:
            if base.startswith("nextcloud:"): return pasta_nextcloud(base)
            meses = sorted(set(re.findall(r'href="(\d{4}-\d{2})/?"', listar(base))))
            if meses: return [(base.rstrip("/") + "/" + m + "/", {}) for m in reversed(meses[-2:])]
        except Exception as e:  # noqa: BLE001
            print(f"  {base}: {e}", file=sys.stderr)
    raise SystemExit("Não achei a pasta da Receita. Confira o endereço e passe em RECEITA_BASE.")

def textos_do_zip(caminho, encoding):
    with zipfile.ZipFile(caminho) as z:
        for nome in z.namelist():
            if nome.endswith("/"): continue
            with z.open(nome) as b:
                yield io.TextIOWrapper(b, encoding=encoding, errors="replace", newline="")

def baixar_zip(url, destino, cab):
    # um download cortado no meio vira um arquivo que não abre: baixa de novo uma vez antes de desistir
    for _ in range(2):
        z = baixar(url, destino, cab=cab)
        if zipfile.is_zipfile(z): return z
        print(f"  {url.rsplit('/', 1)[-1]} veio incompleto; baixando de novo", file=sys.stderr)
    raise zipfile.BadZipFile(url.rsplit("/", 1)[-1] + " não é um zip completo")

# Natureza jurídica 213-5 = Empresário (Individual): a empresa É a pessoa (como no MEI); o nome fantasia
# costuma ser o nome dela e o endereço, a casa. Fica de fora, como o MEI.
NATUREZA_PESSOA = {"2135"}

def ler_naturezas(arquivo_texto, basicos):
    """Empresas da Receita: só cnpj_basico (coluna 0) e natureza jurídica (coluna 2); a razão social não é lida."""
    fora = set()
    for linha in csv.reader(arquivo_texto, delimiter=";", quotechar='"'):
        if len(linha) > 2 and linha[0] in basicos and linha[2].strip() in NATUREZA_PESSOA: fora.add(linha[0])
    return fora

def tirar_basicos(por_uf, fora):
    n = 0
    for uf in por_uf:
        antes = len(por_uf[uf])
        por_uf[uf] = [e for e in por_uf[uf] if e["cnpj"][:8] not in fora]
        n += antes - len(por_uf[uf])
    return n

def ler_receita(pasta, cab, ufs, tmp, incluir=None):
    z = baixar_zip(pasta + "Municipios.zip", os.path.join(tmp, "m.zip"), cab)
    municipios = {}
    for t in textos_do_zip(z, "latin-1"): municipios.update(ler_municipios(t))
    # o Simples é o último a ser publicado no mês: baixa primeiro, para um mês incompleto falhar logo
    # (e não depois de baixar os 10 arquivos de estabelecimentos)
    simples = baixar_zip(pasta + "Simples.zip", os.path.join(tmp, "s.zip"), cab)
    por_uf = {}
    for i in range(10):
        z = baixar_zip(pasta + f"Estabelecimentos{i}.zip", os.path.join(tmp, "e.zip"), cab)
        n = sum(ler_estabelecimentos(t, municipios, set(ufs), por_uf, incluir) for t in textos_do_zip(z, "latin-1"))
        os.remove(z)
        print(f"Estabelecimentos{i}: {n} estabelecimentos")
    basicos = {e["cnpj"][:8] for est in por_uf.values() for e in est}
    mei = set()
    for t in textos_do_zip(simples, "latin-1"): mei |= ler_mei(t, basicos)
    os.remove(simples)
    mei_fora = tirar_mei(por_uf, mei)
    basicos = {e["cnpj"][:8] for est in por_uf.values() for e in est}
    pessoa = set()
    for i in range(10 if basicos else 0):
        z = baixar_zip(pasta + f"Empresas{i}.zip", os.path.join(tmp, "p.zip"), cab)
        for t in textos_do_zip(z, "latin-1"): pessoa |= ler_naturezas(t, basicos)
        os.remove(z)
    ei_fora = tirar_basicos(por_uf, pessoa)
    print(f"Empresário Individual fora: {ei_fora}")
    return por_uf, mei_fora, ei_fora

def mes_da_pasta(pasta):
    m = re.findall(r"(\d{4}-\d{2})", pasta)
    return m[-1] if m else ""

def cmd_receita(a):
    ufs = [u for u in a.ufs.upper().replace(" ", "").split(",") if u in UFS]
    os.makedirs(a.saida, exist_ok=True)
    incluir = ler_incluir(a.incluir)
    bases = [os.environ["RECEITA_BASE"]] if os.environ.get("RECEITA_BASE") else RECEITA_BASES
    tmp = tempfile.mkdtemp()
    por_uf = mei_fora = ei_fora = None
    for pasta, cab in pastas_mais_novas(bases):
        print("Receita:", pasta)
        try:
            por_uf, mei_fora, ei_fora = ler_receita(pasta, cab, ufs, tmp, incluir)
            break
        except (zipfile.BadZipFile, SystemExit) as e:
            # arquivo incompleto (a Receita ainda está publicando o mês) ou que não baixou: tenta o mês anterior
            print(f"::warning::A pasta {pasta} ainda não está completa ({e}); usando o mês anterior.", file=sys.stderr)
    if por_uf is None: raise SystemExit("Nenhuma pasta da Receita está completa agora. Tente de novo mais tarde.")
    print(f"MEI fora: {mei_fora}")
    for uf in ufs:
        with gzip.open(os.path.join(a.saida, uf + ".json.gz"), "wt", encoding="utf-8") as f:
            json.dump(por_uf.get(uf, []), f, ensure_ascii=False)
    with open(os.path.join(a.saida, "_receita.json"), "w", encoding="utf-8") as f:
        json.dump({"mes": mes_da_pasta(pasta), "mei_fora": mei_fora, "empresario_individual_fora": ei_fora, "incluidos": len(incluir)}, f)

def cmd_posicionar(a):
    uf = a.uf.upper()
    if uf not in UFS: raise SystemExit("estado inválido: " + a.uf)
    with gzip.open(os.path.join(a.entrada, uf + ".json.gz"), "rt", encoding="utf-8") as f: est = json.load(f)
    os.makedirs(a.saida, exist_ok=True)
    tmp = tempfile.mkdtemp()
    if est:
        m = re.search(r'href="(\d{2}_' + uf + r'\.zip)"', listar(CNEFE_BASE))
        if m:
            z = baixar(CNEFE_BASE + m.group(1), os.path.join(tmp, "c.zip"))
            ceps = {e["cep"] for e in est if e["cep"]}
            exato, centro, numeros = {}, {}, {}
            for t in textos_do_zip(z, "utf-8"):
                a1, b1, c1 = ler_cnefe(t, ceps); exato.update(a1); centro.update(b1); numeros.update(c1)
            os.remove(z)
            posicionar(est, exato, centro, numeros)
        else:
            print(f"::warning::{uf}: arquivo do CNEFE não encontrado; segue sem posição", file=sys.stderr)
            posicionar(est, {}, {}, {})
    n = gravar(est, os.path.join(a.saida, uf + ".csv.gz"))
    com = sum(1 for e in est if e.get("lat") is not None)
    print(f"{uf}: {n} estabelecimentos, {com} com posição")

def resumo_do_arquivo(caminho):
    tipos, total, com = {}, 0, 0
    with gzip.open(caminho, "rt", encoding="utf-8", newline="") as f:
        for l in csv.DictReader(f, delimiter=";"):
            total += 1; tipos[l["tipo"]] = tipos.get(l["tipo"], 0) + 1
            if l["lat"]: com += 1
    with open(caminho, "rb") as f: h = hashlib.sha256(f.read()).hexdigest()
    return {"arquivo": os.path.basename(caminho), "total": total, "com_posicao": com, "tipos": tipos,
            "bytes": os.path.getsize(caminho), "sha256": h}

def cmd_indice(a):
    with open(a.receita, encoding="utf-8") as f: rec = json.load(f)
    estados = {}
    for uf in UFS:
        p = os.path.join(a.saida, uf + ".csv.gz")
        if os.path.exists(p): estados[uf] = resumo_do_arquivo(p)
    faltam = [u for u in UFS if u not in estados]
    if faltam and not a.parcial: raise SystemExit("Faltam estados: " + ", ".join(faltam))
    indice = {"versao": a.versao, "receita_mes": rec.get("mes"), "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "colunas": COLUNAS, "tipos": list(TIPOS), "mei_fora": rec.get("mei_fora"), "empresario_individual_fora": rec.get("empresario_individual_fora"),
              "fontes": ["Receita Federal do Brasil: Dados Abertos do CNPJ", "IBGE: CNEFE, Censo Demográfico 2022"],
              "estados": estados}
    with open(os.path.join(a.saida, "indice.json"), "w", encoding="utf-8") as f:
        json.dump(indice, f, ensure_ascii=False, indent=1)
    print(json.dumps({u: e["total"] for u, e in estados.items()}))

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("receita"); r.add_argument("--saida", default="parcial"); r.add_argument("--ufs", default=",".join(UFS)); r.add_argument("--incluir", default="incluir.csv")
    p = sub.add_parser("posicionar"); p.add_argument("--uf", required=True); p.add_argument("--entrada", default="parcial"); p.add_argument("--saida", default="saida")
    i = sub.add_parser("indice"); i.add_argument("--saida", default="saida"); i.add_argument("--receita", default="parcial/_receita.json"); i.add_argument("--versao", required=True); i.add_argument("--parcial", action="store_true")
    a = ap.parse_args()
    {"receita": cmd_receita, "posicionar": cmd_posicionar, "indice": cmd_indice}[a.cmd](a)

if __name__ == "__main__":
    main()
