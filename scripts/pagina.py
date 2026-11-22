#!/usr/bin/env python3
"""Monta os dados da página de busca (GitHub Pages) a partir de saida/UF.csv.gz.

Grava, em <site>/dados/:
  indice.json        mês da Receita, versão, estados, cidades de cada estado (nome, arquivo, quantidade, por tipo)
  UF/<cidade>.json   estabelecimentos da cidade: [cnpj, nome, tipo, endereco, bairro, cep, lat, lng, precisao]
A página baixa só o índice e, depois, a cidade escolhida: rápido até no celular.
Só usa a biblioteca padrão do Python.
"""
import argparse, csv, gzip, json, os, re, shutil, unicodedata

UFS = "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()

def slug(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "sem-cidade"

def num(s):
    try: return round(float(s), 6)
    except (TypeError, ValueError): return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", default="saida")
    ap.add_argument("--site", default="site")
    ap.add_argument("--repo", default="cestunoapp/estabelecimentos-brasil")
    a = ap.parse_args()
    with open(os.path.join(a.entrada, "indice.json"), encoding="utf-8") as f: ind = json.load(f)
    destino = os.path.join(a.site, "dados")
    shutil.rmtree(destino, ignore_errors=True)
    estados = {}
    for uf in UFS:
        p = os.path.join(a.entrada, uf + ".csv.gz")
        if not os.path.exists(p): continue
        cidades = {}
        with gzip.open(p, "rt", encoding="utf-8", newline="") as f:
            for l in csv.DictReader(f, delimiter=";"):
                c = l["cidade"] or "Sem cidade"
                cidades.setdefault(c, []).append([l["cnpj"], l["nome"], l["tipo"], l["endereco"], l["bairro"], l["cep"],
                                                  num(l["lat"]), num(l["lng"]), l["precisao"]])
        os.makedirs(os.path.join(destino, uf), exist_ok=True)
        lista, usados = [], set()
        for nome in sorted(cidades, key=lambda x: slug(x)):
            arq = slug(nome)
            while arq in usados: arq += "-2"
            usados.add(arq)
            linhas = sorted(cidades[nome], key=lambda x: (x[1] or "").lower())
            with open(os.path.join(destino, uf, arq + ".json"), "w", encoding="utf-8") as f:
                json.dump(linhas, f, ensure_ascii=False, separators=(",", ":"))
            tipos = {}
            for x in linhas: tipos[x[2]] = tipos.get(x[2], 0) + 1
            lista.append([nome, arq, len(linhas), tipos])
        estados[uf] = {"cidades": lista, "total": sum(c[2] for c in lista)}
    saida = {"versao": ind.get("versao"), "receita_mes": ind.get("receita_mes"), "gerado_em": ind.get("gerado_em"),
             "repo": a.repo, "estados": estados}
    with open(os.path.join(destino, "indice.json"), "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))
    print({uf: e["total"] for uf, e in estados.items()})

if __name__ == "__main__":
    main()
