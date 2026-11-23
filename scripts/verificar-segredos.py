#!/usr/bin/env python3
"""Confere que nenhum arquivo do repositório tem chave, senha ou token (este repositório não usa nenhum).

Procura padrões de chaves conhecidas, o mesmo escondido em base64 ou hexadecimal, endereço com senha e
caracteres invisíveis (que escondem texto de quem lê). Roda nos testes a cada envio.
Uso: python3 scripts/verificar-segredos.py [pasta]   (sai com erro se achar algo)
"""
import base64, binascii, os, re, sys

PADROES = {
    "chave do Supabase": r"sb_secret_[A-Za-z0-9_-]{8,}",
    "JWT (service_role etc.)": r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}",
    "chave privada": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "conta de serviço do Google": r"\"private_key\"\s*:",
    "token do GitHub": r"\b(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})",
    "chave da AWS": r"\bAKIA[0-9A-Z]{16}\b",
    "chave do Google": r"AIza[0-9A-Za-z_-]{35}",
    "token do Slack": r"xox[abpors]-[A-Za-z0-9-]{10,}",
    "chave do Stripe": r"\b[rs]k_live_[A-Za-z0-9]{10,}",
    "segredo do Turnstile": r"0x4AAAAAAA[A-Za-z0-9_-]{10,}",
    "chave do Brevo": r"xkeysib-[a-f0-9]{20,}",
    "endereço com senha": r"[a-z]+://[^\s/:@\"'$]+:[^\s/@\"'$]{4,}@",
}
INVISIVEIS = re.compile("[​-‏‪-‮⁠-⁤﻿]")
IGNORAR = {".git", "parcial", "saida", "dados", "__pycache__"}

def achados(texto):
    for nome, p in PADROES.items():
        if re.search(p, texto): yield nome
    if INVISIVEIS.search(texto): yield "caractere invisível"
    for m in re.finditer(r"[A-Za-z0-9+/_-]{24,}={0,2}", texto):
        try:
            d = base64.b64decode(m.group(0) + "=" * (-len(m.group(0)) % 4)).decode("utf-8")
            for nome, p in PADROES.items():
                if re.search(p, d): yield nome + " (em base64)"
        except Exception: pass
    for m in re.finditer(r"\b[0-9a-fA-F]{24,}\b", texto):
        try:
            d = binascii.unhexlify(m.group(0)).decode("utf-8")
            for nome, p in PADROES.items():
                if re.search(p, d): yield nome + " (em hexadecimal)"
        except Exception: pass

def main():
    raiz = sys.argv[1] if len(sys.argv) > 1 else "."
    erros = []
    for pasta, subs, arqs in os.walk(raiz):
        subs[:] = [s for s in subs if s not in IGNORAR]
        for a in arqs:
            c = os.path.join(pasta, a)
            if c.endswith("verificar-segredos.py"): continue
            try: t = open(c, encoding="utf-8").read()
            except (UnicodeDecodeError, OSError): erros.append((c, "arquivo que não é texto")); continue
            for nome in set(achados(t)): erros.append((c, nome))
    for c, n in erros: print(f"::error file={c}::{n}")
    if erros: sys.exit(1)
    print("Nenhum segredo encontrado.")

if __name__ == "__main__":
    main()
