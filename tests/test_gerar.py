# Estabelecimentos pela Receita: filtro por CNAE e situação, LGPD no nome, endereço e posição pelo CNEFE.
import argparse, csv, gzip, io, json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import gerar as R

def linha(cnpj8, ordem, dv, fantasia, sit, cnae, sec, tipo, logr, num, bairro, cep, uf, mun):
    l = [""] * 30
    l[0], l[1], l[2], l[4], l[5], l[11], l[12], l[13], l[14], l[15], l[17], l[18], l[19], l[20] = cnpj8, ordem, dv, fantasia, sit, cnae, sec, tipo, logr, num, bairro, cep, uf, mun
    l[21], l[22], l[27] = "62", "999999999", "dono@email.com"  # telefone e e-mail não podem sair
    return l

def texto(linhas):
    b = io.StringIO()
    w = csv.writer(b, delimiter=";", quoting=csv.QUOTE_ALL)
    for l in linhas: w.writerow(l)
    b.seek(0); return b

class Testes(unittest.TestCase):
    def test_mei_fica_de_fora(self):
        simples = texto([["11111111", "S", "20200101", "", "N", "", ""], ["22222222", "S", "20200101", "", "S", "20200101", ""], ["99999999", "N", "", "", "S", "", ""]])
        mei = R.ler_mei(simples, {"11111111", "22222222"})
        self.assertEqual(mei, {"22222222"})
        por_uf = {"GO": [{"cnpj": "11111111000111"}, {"cnpj": "22222222000122"}]}
        self.assertEqual(R.tirar_mei(por_uf, mei), 1)
        self.assertEqual([e["cnpj"] for e in por_uf["GO"]], ["11111111000111"])

    def test_filtra_e_limpa(self):
        t = texto([
            linha("11111111", "0001", "11", "SUPERMERCADO BOM DE PRECO LTDA", "02", "4711302", "", "RUA", "DAS FLORES", "120", "CENTRO", "74000100", "GO", "9373"),
            linha("22222222", "0001", "22", "MERCEARIA JOAO 123.456.789-00", "02", "4712100", "", "AVENIDA", "GOIAS", "SN", "SETOR SUL", "74000200", "GO", "9373"),
            linha("33333333", "0001", "33", "FECHADO", "08", "4711302", "", "RUA", "X", "1", "Y", "74000300", "GO", "9373"),
            linha("44444444", "0002", "44", "DISTRIBUIDORA SO ATACADO", "02", "4639701", "4637107", "RUA", "Z", "2", "W", "74000400", "GO", "9373"),
            linha("55555555", "0001", "55", "ATACAREJO BOM", "02", "4639701", "4637107,4711302", "RODOVIA", "BR 153", "KM 5", "", "74000500", "GO", "9373"),
            linha("56565656", "0001", "56", "ATACADO GERAL COM LOJA", "02", "4691500", "4711302", "RODOVIA", "GO 060", "KM 1", "", "74000510", "GO", "9373"),
            linha("57575757", "0001", "57", "DISTRIBUIDORA GERAL", "02", "4691500", "4637107", "RUA", "Y", "3", "", "74000520", "GO", "9373"),
            linha("66666666", "0001", "66", "PADARIA", "02", "1091102", "", "RUA", "A", "1", "B", "74000600", "GO", "9373"),
            linha("77777777", "0001", "77", "SUPER SP", "02", "4711301", "", "RUA", "A", "1", "B", "01000000", "SP", "7107"),
            linha("88888888", "0001", "88", "DROGARIA SAUDE", "02", "4771701", "", "RUA", "C", "10", "CENTRO", "74000700", "GO", "9373"),
        ])
        saida = {}
        n = R.ler_estabelecimentos(t, {"9373": "GOIANIA"}, {"GO"}, saida)
        self.assertEqual(n, 5)
        go = {e["cnpj"]: e for e in saida["GO"]}
        self.assertEqual(set(go), {"11111111000111", "22222222000122", "55555555000155", "88888888000188"})
        self.assertEqual((go["88888888000188"]["tipo"], go["88888888000188"]["cnae"], go["88888888000188"]["bairro"]), ("farmacia", "4771701", "Centro"))
        self.assertEqual(go["11111111000111"]["nome"], "Supermercado Bom de Preco")
        self.assertEqual(go["11111111000111"]["endereco"], "Rua das Flores, 120 - Centro")
        self.assertEqual(go["11111111000111"]["cidade"], "Goiania")
        self.assertEqual(go["22222222000122"]["tipo"], "mini")
        self.assertNotIn("123", go["22222222000122"]["nome"])
        self.assertEqual(go["22222222000122"]["endereco"], "Avenida Goias, s/n - Setor Sul")
        self.assertEqual(go["55555555000155"]["tipo"], "atacarejo")
        self.assertEqual(go["56565656000156"]["tipo"], "atacarejo", "atacado geral de alimentos com supermercado secundário")
        self.assertNotIn("57575757000157", go, "atacado geral sem varejo fica de fora")
        txt = repr(saida)
        self.assertNotIn("email", txt); self.assertNotIn("999999999", txt)

    def test_incluir_outra_atividade(self):
        d = tempfile.mkdtemp(); p = os.path.join(d, "incluir.csv")
        with open(p, "w", encoding="utf-8") as f:
            f.write("# comentário\ncnpj;tipo;observacao\n66.666.666/0001-66;super;padaria que é mercado\n99999999000199;tipo_que_nao_existe;x\n")
        inc = R.ler_incluir(p)
        self.assertEqual(inc, {"66666666000166": "super"})
        t = texto([linha("66666666", "0001", "66", "PADARIA E MERCADO", "02", "1091102", "", "RUA", "A", "1", "B", "74000600", "GO", "9373"),
                   linha("66666666", "0002", "67", "OUTRA FILIAL", "02", "1091102", "", "RUA", "A", "2", "B", "74000600", "GO", "9373")])
        saida = {}
        R.ler_estabelecimentos(t, {}, {"GO"}, saida, inc)
        self.assertEqual([(e["cnpj"], e["tipo"]) for e in saida["GO"]], [("66666666000166", "super")])

    def test_nome_sem_cpf(self):
        self.assertIsNone(R.limpar_nome("12345678901"))
        self.assertEqual(R.limpar_nome("MERCADO 12.345.678 MARIA"), "Mercado Maria")

    def test_posicao_pelo_cnefe(self):
        cnefe = io.StringIO("COD_UNICO_ENDERECO;CEP;NOM_SEGLOGR;NUM_ENDERECO;LATITUDE;LONGITUDE\n"
                            "1;74000100;FLORES;120;-16.6801;-49.2501\n"
                            "2;74000100;FLORES;150;-16.6805;-49.2505\n"
                            "3;74000500;BR 153;0;-16.70;-49.30\n"
                            "4;99999999;OUTRO;1;-1;-1\n")
        exato, centro, numeros = R.ler_cnefe(cnefe, {"74000100", "74000500"})
        est = [{"cep": "74000100", "num": "120"}, {"cep": "74000100", "num": "140"}, {"cep": "74000500", "num": "5"}, {"cep": "70000000", "num": "1"}]
        R.posicionar(est, exato, centro, numeros)
        self.assertEqual((est[0]["precisao"], est[0]["lat"]), ("endereco", -16.6801))
        self.assertEqual((est[1]["precisao"], est[1]["lat"]), ("rua", -16.6805))
        self.assertEqual(est[2]["precisao"], "cep")
        self.assertIsNone(est[3]["lat"])

    def test_csv_de_saida_e_indice(self):
        d = tempfile.mkdtemp(); p = os.path.join(d, "GO.csv.gz")
        n = R.gravar([{"cnpj": "22222222000122", "nome": "B", "tipo": "farmacia", "cnae": "4771701", "endereco": "Rua 3", "bairro": "Sul", "cep": "74000200", "cidade": "Goiania", "uf": "GO", "lat": None, "lng": None, "precisao": None},
                      {"cnpj": "11111111000111", "nome": "A", "tipo": "super", "cnae": "4711302", "endereco": "Rua 1, 2", "bairro": "Centro", "cep": "74000100", "cidade": "Goiania", "uf": "GO", "lat": -16.1, "lng": -49.2, "precisao": "cep"},
                      {"cnpj": "11111111000111", "nome": "Dup", "tipo": "super", "endereco": None, "cidade": None, "uf": "GO", "lat": None, "lng": None, "precisao": None}], p)
        self.assertEqual(n, 2)
        linhas = gzip.open(p, "rt", encoding="utf-8").read().strip().split("\n")
        self.assertEqual(linhas[0], "cnpj;nome;tipo;cnae;endereco;bairro;cep;cidade;uf;lat;lng;precisao")
        self.assertTrue(linhas[1].startswith("11111111000111;A;super;4711302;"), "em ordem de CNPJ")
        with open(os.path.join(d, "_receita.json"), "w") as f: json.dump({"mes": "2026-10", "mei_fora": 3}, f)
        R.cmd_indice(argparse.Namespace(saida=d, receita=os.path.join(d, "_receita.json"), versao="2026-10", parcial=True))
        ind = json.load(open(os.path.join(d, "indice.json"), encoding="utf-8"))
        self.assertEqual((ind["receita_mes"], ind["estados"]["GO"]["total"], ind["estados"]["GO"]["com_posicao"]), ("2026-10", 2, 1))
        self.assertEqual(ind["estados"]["GO"]["tipos"], {"super": 1, "farmacia": 1})
        self.assertEqual(len(ind["estados"]["GO"]["sha256"]), 64)
        with self.assertRaises(SystemExit):  # sem --parcial, falta de estado é erro
            R.cmd_indice(argparse.Namespace(saida=d, receita=os.path.join(d, "_receita.json"), versao="2026-10", parcial=False))

    def test_empresario_individual_fica_de_fora(self):
        emp = texto([['11111111', 'MARIA DA SILVA 12345678901', '2135', '50', '1000,00', '01', ''],
                     ['22222222', 'SUPERMERCADO X LTDA', '2062', '49', '1000,00', '03', ''],
                     ['33333333', 'JOAO "ZE"; SOUZA', '2135', '50', '1,00', '01', '']])
        fora = R.ler_naturezas(emp, {"11111111", "22222222"})
        self.assertEqual(fora, {"11111111"})  # 33333333 não interessa (não está entre os estabelecimentos)
        por_uf = {"GO": [{"cnpj": "11111111000111"}, {"cnpj": "22222222000122"}]}
        self.assertEqual(R.tirar_basicos(por_uf, fora), 1)
        self.assertEqual([e["cnpj"] for e in por_uf["GO"]], ["22222222000122"])

    def test_endereco_sem_numeros_longos(self):
        e = R.montar_endereco("AREA", "POV MATO PRETO 8464401651109200JF623 RURAL", "SN", "AREA RURAL LAPA")
        self.assertNotIn("8464401651109200", e)
        self.assertEqual(R.montar_endereco("RUA", "1 DE JULHO QUADRA 01", "120", "CENTRO"), "Rua 1 de Julho Quadra 01, 120 - Centro")
        self.assertEqual(R.sem_numeros_longos("Padrao da Celtins 0508300006281 lote"), "Padrao da Celtins lote")

    def test_mes_da_pasta(self):
        self.assertEqual(R.mes_da_pasta("https://x/public.php/webdav/Dados/Cadastros/CNPJ/2026-10/"), "2026-10")

class Nextcloud(unittest.TestCase):
    def test_meses_do_webdav(self):
        xml = ('<d:multistatus xmlns:d="DAV:"><d:response><d:href>/public.php/webdav/Dados/Cadastros/CNPJ/</d:href></d:response>'
               '<d:response><d:href>/public.php/webdav/Dados/Cadastros/CNPJ/2026-09/</d:href></d:response>'
               '<d:response><d:href>/public.php/webdav/Dados/Cadastros/CNPJ/2026-10/</d:href></d:response></d:multistatus>')
        self.assertEqual(R.meses_do_webdav(xml), ["2026-09", "2026-10"])

    def test_pasta_nextcloud_com_servidor_simulado(self):
        import http.server, threading
        vistos = []
        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_PROPFIND(self):
                vistos.append((self.path, self.headers.get("Authorization"), self.headers.get("Depth")))
                if self.path.startswith("/public.php/dav/"): self.send_response(404); self.end_headers(); return
                corpo = (b'<d:multistatus xmlns:d="DAV:"><d:response><d:href>/public.php/webdav/Dados/Cadastros/CNPJ/2026-10/</d:href></d:response>'
                         b'<d:response><d:href>/public.php/webdav/Dados/Cadastros/CNPJ/2026-11/</d:href></d:response></d:multistatus>')
                self.send_response(207); self.end_headers(); self.wfile.write(corpo)
        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            pastas = R.pastas_mais_novas([f"nextcloud:http://127.0.0.1:{srv.server_port}|TOKEN123|/Dados/Cadastros/CNPJ"])
        finally:
            srv.shutdown()
        # o mês mais novo primeiro; o anterior fica de reserva (a Receita publica o mês aos poucos)
        self.assertTrue(pastas[0][0].endswith("/CNPJ/2026-11/") and pastas[1][0].endswith("/CNPJ/2026-10/"))
        pasta, cab = pastas[0]
        self.assertEqual(cab["Authorization"], "Basic VE9LRU4xMjM6")  # código do link como usuário, senha vazia
        self.assertEqual(vistos[0][2], "1")

    def test_mes_incompleto_usa_o_anterior(self):
        import tempfile, zipfile, io
        tmp = tempfile.mkdtemp()
        def zipado(nome, texto):
            b = io.BytesIO()
            with zipfile.ZipFile(b, "w") as z: z.writestr(nome, texto)
            return b.getvalue()
        # como em 17/11: o mês novo já tinha os estabelecimentos, mas o Simples ainda vinha cortado
        arquivos = {"2026-11/Municipios.zip": zipado("m.csv", ""), "2026-11/Simples.zip": b"PK\x03\x04 cortado no meio"}
        for i in range(10):
            arquivos[f"2026-11/Estabelecimentos{i}.zip"] = zipado("e.csv", "")
            arquivos[f"2026-10/Estabelecimentos{i}.zip"] = zipado("e.csv", "")
            arquivos[f"2026-10/Empresas{i}.zip"] = zipado("p.csv", "")
        arquivos["2026-10/Municipios.zip"] = zipado("m.csv", ""); arquivos["2026-10/Simples.zip"] = zipado("s.csv", "")
        baixados = []
        def falso(url, destino, tentativas=4, cab=None):
            chave = "/".join(url.rstrip("/").split("/")[-2:])
            baixados.append(chave)
            if chave not in arquivos: raise SystemExit("Não consegui baixar " + url)
            with open(destino, "wb") as f: f.write(arquivos[chave])
            return destino
        original = R.baixar; R.baixar = falso
        try:
            with self.assertRaises(zipfile.BadZipFile):
                R.ler_receita("x/2026-11/", {}, ["TO"], tmp)          # mês novo incompleto: recusa
            # recusa logo, sem baixar os 10 arquivos de estabelecimentos à toa
            self.assertFalse([b for b in baixados if b.startswith("2026-11/Estab")])
            por_uf, mei, ei = R.ler_receita("x/2026-10/", {}, ["TO"], tmp)  # mês anterior: segue
            self.assertEqual(por_uf, {})
        finally:
            R.baixar = original

if __name__ == "__main__":
    unittest.main()
