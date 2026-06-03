# Solicitação de Liberação de Métodos — API de Saída Linx Microvix

**Para:** Chilli Beans — TI / Suporte à Franquia / Integrações Microvix
**De:** Rafael Burim Ramo — Franqueado, Ótica P. Ferreira (Porto Ferreira/SP)
**Loja / Empresa:** SP PORTO FERREIRA - OTICA P FERREIRA LJR
**CNPJ da loja:** 58.179.991/0001-00
**Chave de integração (API Saída):** Acesso via sistema ERP → Integrações
**Data:** 29/05/2026
**Assunto:** Liberação de métodos do WebService de Saída Padrão para projeto interno de análise

---

## 1. Contexto

Estamos desenvolvendo internamente uma ferramenta de **análise de vendas, gestão de estoque e
sugestão de compras** para nossa loja, consumindo a **API de Saída Padrão do Linx Microvix**
(endpoint `http://webapi.microvix.com.br/1.0/api/integracao`), conforme a *Especificação Web
Service de Saída Padrão* (versão atual v263/v209) publicada pela Linx.

A integração **já está ativa e autenticando corretamente** com nossa chave. Confirmamos que parte
dos métodos retorna dados normalmente. Porém, **vários métodos essenciais ao projeto ainda não
estão liberados/retornando dados** para a nossa chave, o que nos impede de avançar.

Solicitamos a **regularização (liberação) dos métodos listados no item 4** para a nossa chave/CNPJ.

---

## 2. O que já está funcionando (não precisa de ação)

Estes métodos já retornam dados para a nossa chave:

| Método | Retorno (conforme spec oficial) | Situação |
|---|---|---|
| `LinxMovimento` | Itens de movimento (vendas/entradas) | ✅ OK — ~537 reg./mês |
| `LinxProdutosCodBar` | Códigos de barras dos produtos | ✅ OK — ~5.000 reg. |
| `LinxProdutosFornec` | Produtos × fornecedores (com custo) | ✅ OK — ~5.000 reg. |
| `LinxVendedores` | Cadastro de vendedores | ✅ OK — 10 reg. |
| `LinxSetores` | Setores cadastrados | ✅ OK — 24 reg. |
| `LinxMarcas` | Marcas cadastradas | ✅ OK — 111 reg. |

---

## 3. O que está faltando — diagnóstico

Testamos cada método pelo **nome exato da especificação oficial**. O resultado:

**a) Retornam VAZIO (autenticam, mas não trazem dados — pedimos verificação/liberação):**
- `LinxProdutos` — cadastro de produtos
- `LinxProdutosDetalhes` — saldo, preços, custos e configuração tributária por empresa
- `LinxProdutosDetalhesDepositos` — saldos por depósito
- `LinxProdutosTabelasPrecos` — vínculo produto × tabela de preço
- `LinxClientesFornec` — clientes/fornecedores
- `LinxMetasVendedores` — metas dos vendedores
- `LinxXMLDocumentos` — XML dos documentos fiscais emitidos

**b) Retornam ERRO "O parâmetro é inválido" (indicativo de método não liberado para a chave):**
- `LinxProdutosInventario` — saldo do produto na data pesquisada
- `LinxMovimentoPrincipal` — cabeçalho do movimento (vendedor, desconto, cliente, totais)
- `LinxMetasVendedoresDia` — metas dos vendedores por dia
- `LinxNFeEvento` — eventos de NF-e
- `LinxOticoReceitas` — receitas óticas importadas
- `LinxOrdensServico` — ordens de serviço (laboratório de lentes)

---

## 4. Métodos cuja liberação solicitamos

Pedimos a liberação/habilitação dos métodos abaixo, agrupados por finalidade:

### 4.1 Catálogo e categorização de produtos
- **`LinxProdutos`** — cadastro de produtos
- **`LinxProdutosDetalhes`** — saldo, preços, custos e configuração tributária por empresa

### 4.2 Estoque / saldo
- **`LinxProdutosDetalhesDepositos`** — saldos dos produtos por depósito
- **`LinxProdutosInventario`** — saldo do produto na data pesquisada

### 4.3 Vendas — detalhamento
- **`LinxMovimentoPrincipal`** — cabeçalho do movimento (vendedor, desconto, cliente, totais por nota)

### 4.4 Metas e desempenho de vendedores
- **`LinxMetasVendedores`** — metas dos vendedores
- **`LinxMetasVendedoresDia`** — metas dos vendedores por dia

### 4.5 Fiscal / NF-e
- **`LinxXMLDocumentos`** — XML dos documentos fiscais emitidos
- **`LinxNFeEvento`** — eventos de NF-e (cancelamentos, correções)

### 4.6 Ótico (essencial para o nosso ramo)
- **`LinxOticoReceitas`** — receitas óticas importadas no sistema
- **`LinxOrdensServico`** e **`LinxOrdensServicoProdutos`** — ordens de serviço e seus produtos

### 4.7 Clientes (CRM)
- **`LinxClientesFornec`** — cadastro de clientes/fornecedores

---

## 5. Pedido objetivo

Solicitamos que, junto à Linx, seja providenciada a **liberação dos métodos do item 4 no contrato
de API de Saída** vinculado à nossa chave de integração e CNPJ, **garantindo o retorno de dados**
(não apenas a habilitação nominal). Caso algum método exija parâmetros específicos diferentes do
padrão `data_inicial`/`data_fim` ou `timestamp`, pedimos a indicação dos parâmetros corretos.

A chave de integração está disponível no próprio ERP (menu **Integrações**), acessível pela
Chilli Beans. Permanecemos à disposição para os testes de validação após a liberação.

Atenciosamente,

**Rafael Burim Ramo**
Franqueado — Ótica P. Ferreira (Porto Ferreira/SP)
(19) 99763-9515 · rafaburim@gmail.com
