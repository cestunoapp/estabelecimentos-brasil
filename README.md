# Estabelecimentos do Brasil

Supermercados, atacarejos, minimercados e farmácias **ativos** de todo o Brasil, com **nome fantasia, endereço e posição no mapa**, atualizados todo mês a partir de dados abertos do governo:

- **Receita Federal do Brasil:** Dados Abertos do CNPJ (estabelecimentos, municípios, Simples Nacional);
- **IBGE:** CNEFE, Cadastro Nacional de Endereços para Fins Estatísticos (Censo Demográfico 2022), para achar a posição pelo endereço.

**Buscar:** [cestunoapp.github.io/estabelecimentos-brasil](https://cestunoapp.github.io/estabelecimentos-brasil/), por estado, cidade, tipo e nome.

Os arquivos ficam em [Releases](../../releases): uma versão por mês (ex.: `2026-11`), com um arquivo por estado.

## Arquivos

| Arquivo | O que tem |
|---|---|
| `UF.csv.gz` | um estabelecimento por linha (CSV em UTF-8, separador `;`, compactado com gzip) |
| `indice.json` | mês da Receita, quantidades por estado e por tipo, tamanho e impressão digital (SHA-256) de cada arquivo |

Colunas:

| Coluna | Exemplo | Observação |
|---|---|---|
| `cnpj` | `11222333000181` | 14 números |
| `nome` | `Supermercado Bom Preço` | nome fantasia, sem números longos (possível CPF) |
| `tipo` | `super` | `hiper`, `super`, `atacarejo`, `mini` ou `farmacia` |
| `cnae` | `4711302` | atividade principal na Receita |
| `endereco` | `Rua das Flores, 120 - Centro` | |
| `bairro` | `Centro` | |
| `cep` | `74000100` | |
| `cidade` | `Goiania` | como na Receita (sem acento) |
| `uf` | `GO` | |
| `lat`, `lng` | `-16.680100`, `-49.250100` | vazio quando o endereço não foi achado |
| `precisao` | `endereco` | `endereco` (número exato), `rua` (número mais perto no mesmo CEP) ou `cep` (centro do CEP) |

## Tipos

| Tipo | Atividade principal (CNAE) |
|---|---|
| `hiper` | 4711-3/01 Hipermercados |
| `super` | 4711-3/02 Supermercados |
| `mini` | 4712-1/00 Minimercados, mercearias e armazéns |
| `atacarejo` | 4639-7/01 Atacado de produtos alimentícios em geral, com hiper ou supermercado como atividade secundária |
| `farmacia` | 4771-7/01 e 4771-7/02 Farmácias e drogarias |

Um estabelecimento registrado com outra atividade (por exemplo, uma padaria que funciona como mercado) pode entrar pelo arquivo [`incluir.csv`](incluir.csv): uma linha com o CNPJ e o tipo.

## Privacidade (LGPD)

- Só entram estabelecimentos **ativos**.
- **MEI fica de fora:** o nome fantasia de um MEI costuma ser o nome do dono, e o endereço, a casa dele.
- Não usa razão social, sócios, telefone nem e-mail.

## Como é gerado

O GitHub Actions deste repositório roda no dia 20 de cada mês ([`gerar.yml`](.github/workflows/gerar.yml)):

1. baixa a base de CNPJ da Receita e separa os estabelecimentos dos tipos acima;
2. para cada estado, em paralelo, acha a posição pelo endereço no CNEFE;
3. publica a versão do mês, com o `indice.json`;
4. atualiza a página de busca (ramo `gh-pages`, servido pelo GitHub Pages).

Não usa nenhuma chave nem senha: só dados abertos. O script ([`scripts/gerar.py`](scripts/gerar.py)) usa só a biblioteca padrão do Python.

## Licença

Código: MIT. Dados: Receita Federal do Brasil e IBGE, dados abertos; cite as fontes ao usar.

Usado pelo [Cestuno](https://cestuno.com.br), app de lista de compras e comparação de preços.
