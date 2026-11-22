# Dados da página de busca: índice de estados e cidades e um arquivo por cidade.
import argparse, json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import gerar as R, pagina as P

class Testes(unittest.TestCase):
    def test_monta_indice_e_cidades(self):
        d, site = tempfile.mkdtemp(), tempfile.mkdtemp()
        base = {"cnae": "4711302", "endereco": "Rua 1", "bairro": "Centro", "cep": "74000100", "uf": "GO", "precisao": "endereco"}
        R.gravar([dict(base, cnpj="11111111000111", nome="Zeta", tipo="super", cidade="Goiania", lat=-16.6, lng=-49.2),
                  dict(base, cnpj="22222222000122", nome="Alfa", tipo="farmacia", cidade="Goiania", lat=None, lng=None),
                  dict(base, cnpj="33333333000133", nome="Beta", tipo="mini", cidade="São Luís de Montes Belos", lat=None, lng=None)], os.path.join(d, "GO.csv.gz"))
        with open(os.path.join(d, "_r.json"), "w") as f: json.dump({"mes": "2026-10"}, f)
        R.cmd_indice(argparse.Namespace(saida=d, receita=os.path.join(d, "_r.json"), versao="2026-10", parcial=True))
        sys.argv = ["pagina.py", "--entrada", d, "--site", site]
        P.main()
        ind = json.load(open(os.path.join(site, "dados", "indice.json"), encoding="utf-8"))
        self.assertEqual(ind["versao"], "2026-10")
        self.assertEqual([c[:3] for c in ind["estados"]["GO"]["cidades"]], [["Goiania", "goiania", 2], ["São Luís de Montes Belos", "sao-luis-de-montes-belos", 1]])
        gyn = json.load(open(os.path.join(site, "dados", "GO", "goiania.json"), encoding="utf-8"))
        self.assertEqual([x[1] for x in gyn], ["Alfa", "Zeta"])          # em ordem de nome
        self.assertEqual(gyn[1][6:8], [-16.6, -49.2]); self.assertIsNone(gyn[0][6])

    def test_slug(self):
        self.assertEqual(P.slug("São João d'Aliança"), "sao-joao-d-alianca")
        self.assertEqual(P.slug(""), "sem-cidade")

if __name__ == "__main__":
    unittest.main()
