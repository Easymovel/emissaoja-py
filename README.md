# emissaoja: API de NFS-e nacional para Python

[![PyPI](https://img.shields.io/pypi/v/emissaoja)](https://pypi.org/project/emissaoja/) [![CI](https://github.com/Easymovel/emissaoja-py/actions/workflows/ci.yml/badge.svg)](https://github.com/Easymovel/emissaoja-py/actions/workflows/ci.yml) [![Licença MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-blue)](LICENSE)

Cliente oficial da **[API do emissaoja](https://emissaoja.com.br/docs/)** para emitir **NFS-e (Nota Fiscal de Serviço eletrônica) no Emissor Nacional** (nfse.gov.br) a partir do seu sistema em Python, **sem certificado digital**: o emissaoja entra no portal com o CNPJ e a senha da própria empresa. Feito para **MEI e empresas do Simples Nacional**. Cadastre tomadores pelo CNPJ (nome e endereço vêm da Receita Federal), emita, acompanhe a autorização, baixe o **PDF (DANFSe) e o XML** e cancele notas.

- **Só biblioteca padrão** (urllib), Python 3.9+, com `py.typed`.
- **Idempotência embutida:** toda emissão leva uma `referencia` sua, que vira o cabeçalho `Idempotency-Key`. Repetir a mesma referência nunca emite duas notas.
- `notas.aguardar()` acompanha o pedido até `autorizada`, `recusada` ou `incerta`, no ritmo que a API indica (`proxima_consulta_ms`).
- Erros com `code` estável (`nota_bloqueada`, `limite_notas`, `possivel_duplicada`…) e o que falta resolver em `extras["bloqueios"]`.
- **Sandbox grátis** com Emissor Nacional simulado: teste o fluxo inteiro sem efeito fiscal.

## Instalação

```bash
pip install emissaoja
```

Crie a conta com o Google em [emissaoja.com.br](https://emissaoja.com.br/?origem=lib-pypi) e gere a chave em **Conta → API** (ela aparece uma vez; prefixo `ej_live_`). Guarde a chave no servidor:

```bash
export EMISSAOJA_KEY=ej_live_...
```

## Teste no sandbox em 2 minutos

O sandbox (`https://sandbox.emissaoja.com.br`) é o mesmo emissaoja com um **Emissor Nacional simulado**: nada ali existe no fisco e nada é cobrado. Entre com o Google, crie uma chave `ej_test_` em Conta → API e rode:

```python
from emissaoja import BASE_SANDBOX, Emissaoja

ej = Emissaoja(base_url=BASE_SANDBOX)  # lê a chave de EMISSAOJA_KEY; ou Emissaoja("ej_test_...", base_url=...)

# 1. Conectar a empresa (uma vez). 11111111000191 é um MEI de exemplo pronto para emitir; qualquer senha serve.
ej.empresa.conectar("11111111000191", "senha-de-teste")
ej.empresa.aguardar_credencial()

# 2. Tomador pelo CNPJ: nome e endereço vêm da Receita Federal
tomador = ej.tomadores.criar("12345678000195")["tomador"]

# 3. Emitir (prévia + emissão num passo). A referência é o seu id da nota.
pedido = ej.notas.emitir(
    "pedido-2026-11-0001",
    tomador["tipo"],
    tomador["id"],
    1500,
    descricao="Consultoria em marketing digital - novembro/2026",
)["pedido"]

# 4. Acompanhar até autorizada | recusada | incerta
final = ej.notas.aguardar(pedido["id"])["pedido"]
print(final["estado"], final.get("numero"), final.get("chave_acesso"))

# 5. PDF (DANFSe) e XML
if final["estado"] == "autorizada":
    pdf = ej.notas.pdf(final["nota"]["origem"], final["nota"]["id"])  # bytes
    xml = ej.notas.xml(final["nota"]["origem"], final["nota"]["id"])  # str
```

Valores com significado no sandbox: `13.13` gera uma nota **incerta** que `ej.emissoes.conferir(id)` resolve como autorizada, `77.77` uma incerta que não saiu, `66.66` uma **recusada** pelo fisco e `99.99` um **bloqueio** já na prévia (`422 nota_bloqueada`). Outras empresas de exemplo: `22222222000191` (ME que pede a alíquota do Simples antes de emitir), `33333333000191` (MEI sem notas anteriores) e `44444444000191` (bloqueada). A senha `errada` simula senha recusada pelo portal. Exemplo completo em [`exemplos/emitir_nfse_sandbox.py`](exemplos/emitir_nfse_sandbox.py).

## Em produção

`Emissaoja()` usa `https://emissaoja.com.br` e lê `EMISSAOJA_KEY`. A chave `ej_live_` vale para a empresa e o plano da conta que a criou; chaves `ej_test_` só valem no sandbox.

> **A chave é secreta.** Use o cliente só no servidor (Django, Flask, FastAPI, filas, scripts). Quem tiver a chave emite notas em nome da empresa.

Com Django ou FastAPI, crie um cliente por processo e reutilize (ele não guarda estado entre chamadas):

```python
# settings.py / config.py
from emissaoja import Emissaoja

EMISSAOJA = Emissaoja()  # chave de EMISSAOJA_KEY, lida na primeira chamada
```

## Empresa: conectar ao Emissor Nacional

```python
ej.empresa.conectar("11222333000181", "senha-do-emissor-nacional")  # 202, verificação em segundo plano
tentativa = ej.empresa.aguardar_credencial()["tentativa"]
# tentativa["proximo_passo"]: configurando | pronto | corrigir_senha | tentar_mais_tarde | redefinir_no_portal | suporte

empresa = ej.empresa.obter()  # empresa["onboarding"]["estado"]: configurando → perguntas → pronto
if empresa["onboarding"]["estado"] == "perguntas":
    print(ej.empresa.onboarding())  # o que o cadastro fiscal não respondeu sozinho
    ej.empresa.fiscal(aliquota_simples=6)  # só com o valor que a empresa informou
```

A senha é conferida no portal e nunca volta em resposta. O portal bloqueia a conta da empresa depois de algumas senhas erradas: a API limita a 3 tentativas erradas por CNPJ em 24 h.

## Tomadores e serviços

```python
ej.tomadores.criar("52998224725", nome="Maria da Silva")  # CPF precisa do nome
ej.tomadores.listar(busca="alfa", ordem="recentes")
ej.tomadores.buscar("12.345.678")

itens = ej.servicos.catalogo("consultoria")["itens"]  # código nacional (cTribNac) por texto
ej.servicos.criar(descricao="Consultoria", c_trib_nac=itens[0]["c_trib_nac"], trib_issqn="tributavel", retem_iss=False)
ej.servicos.listar()  # emitir sem servico_id usa o principal
```

## Notas

```python
notas = ej.notas.listar(periodo="mes_atual", situacao="emitidas")["notas"]
operacao = ej.notas.cancelar("local", nota_id, "1", justificativa="Valor digitado errado.")["operacao"]
ej.operacoes.aguardar(operacao["id"])  # processando → concluida | falhou
```

Nota não se altera: para corrigir, cancele e emita outra. Nota autorizada e depois cancelada conta no plano; recusada não conta.

## Idempotência e nota em dobro

- Use uma `referencia` por nota que você quer emitir (o id do seu pedido serve; 8 a 64 caracteres: letras, números, `_` e `-`). Repetir a mesma devolve o mesmo `pedido` com `repetido: True`.
- `503 fila_indisponivel`: repita **com a mesma referência**.
- `409 possivel_duplicada`: já existe nota igual (tomador, valor e competência) no mesmo dia. Se for mesmo outra nota, repita com `permitir_repetida_de=e.extras["nota_igual_recente"]["pedido_id"]`.
- `409 emissao_repetida_recente`: mesma nota há menos de 2 minutos. Se for intencional, repita com `confirmo_repeticao=True`.
- A biblioteca não repete chamadas sozinha: emitir tem efeito fiscal, e quem decide repetir é você.

## Erros

```python
from emissaoja import EmissaojaErro

try:
    ej.notas.emitir("pedido-0002", "pj", tomador_id, 100)
except EmissaojaErro as e:
    if e.code == "nota_bloqueada":
        print(e.extras["bloqueios"])  # [{"code", "mensagem", "acao"}]
    elif e.code == "limite_notas":
        print("limite do plano no mês")
    else:
        print(e.status, e.code, e, e.request_id)
```

| HTTP | `code` | O que fazer |
| --- | --- | --- |
| 400 | `validation_error`, `valor_invalido`, `cnpj_invalido`, `chave_idempotencia_invalida` | Corrigir o campo |
| 401 | `chave_invalida` | Conferir a chave (ou o ambiente: `ej_test_` só no sandbox) |
| 402 | `limite_notas` | Limite do plano no mês |
| 404 | `tomador_nao_encontrado`, `servico_nao_encontrado`, `nota_nao_encontrada`, `pedido_nao_encontrado` | Conferir o id |
| 409 | `sem_empresa` | Conectar a empresa (`empresa.conectar`) |
| 409 | `aceite_pendente` | Termos ou Política mudaram: entre no [app](https://emissaoja.com.br/app) e aceite a versão nova; a chave volta a funcionar |
| 409 | `possivel_duplicada`, `emissao_repetida_recente`, `incerta_pendente` | Ver "Idempotência e nota em dobro" |
| 422 | `nota_bloqueada` | Resolver `extras["bloqueios"]` |
| 429 | `rate_limited` | Esperar `Retry-After` |
| 503 | `motor_indisponivel`, `fila_indisponivel`, `receita_indisponivel` | Tentar de novo (com a mesma referência) |
| 0 | `rede`, `tempo_esgotado` | Falha de rede ou tempo esgotado no seu lado |

Limites: 60 chamadas por minuto por chave, 10 emissões por minuto e 120 por minuto em buscas e catálogo.

## Referência

| Recurso | Métodos |
| --- | --- |
| `empresa` | `obter`, `conectar`, `credencial`, `aguardar_credencial`, `onboarding`, `fiscal`, `reler_fisco` |
| `tomadores` | `listar`, `buscar`, `criar`, `obter`, `atualizar` |
| `servicos` | `listar`, `criar`, `atualizar`, `desativar`, `catalogo` |
| `notas` | `emitir`, `aguardar`, `listar`, `pdf`, `xml`, `cancelar` |
| `emissoes` | `obter`, `listar`, `conferir` |
| `operacoes` | `obter`, `aguardar` |
| `cnpj` | `consultar` (dados da Receita Federal) |
| — | `status()` (sem chave) |

`Emissaoja(chave=None, base_url=BASE_PRODUCAO, timeout=30.0)`. Referência completa da API: [emissaoja.com.br/docs](https://emissaoja.com.br/docs/) e [OpenAPI 3.1](https://emissaoja.com.br/v1/openapi.json).

## Perguntas frequentes

**Precisa de certificado digital?** Não. O emissaoja entra no Emissor Nacional com o CNPJ e a senha do portal da própria empresa, o acesso que o portal oferece a MEI e empresas do Simples Nacional.

**Funciona para MEI?** Sim. O público é MEI, ME e EPP optantes pelo Simples Nacional, em um município que emite pelo Emissor Nacional.

**Tem ambiente de testes?** Sim, o sandbox em `https://sandbox.emissaoja.com.br`, com o Emissor Nacional simulado e empresas de exemplo.

**Quanto custa?** O plano Grátis emite 1 nota por mês; os planos pagos estão em [emissaoja.com.br/#precos](https://emissaoja.com.br/#precos). O sandbox é grátis. Nota recusada não conta.

**Tem webhook?** Ainda não. Acompanhe o pedido com `notas.aguardar()` ou `emissoes.obter()`, que trazem `proxima_consulta_ms`.

## Outras formas de integrar

- Node.js/TypeScript: [`npm install emissaoja`](https://github.com/Easymovel/emissaoja-js) · PHP/Laravel: [`composer require emissaoja/emissaoja`](https://github.com/Easymovel/emissaoja-php) · .NET: [`dotnet add package Emissaoja`](https://github.com/Easymovel/emissaoja-dotnet) · Go: [`go get emissaoja.com.br/go`](https://github.com/Easymovel/emissaoja-go) · Ruby: [`gem install emissaoja`](https://github.com/Easymovel/emissaoja-ruby)
- n8n: [`n8n-nodes-emissaoja`](https://github.com/Easymovel/n8n-nodes-emissaoja) · WooCommerce: [emissaoja NFS-e para WooCommerce](https://github.com/Easymovel/emissaoja-woocommerce)
- Assistentes de IA (Claude, ChatGPT, Cursor, VS Code): servidor MCP em `https://emissaoja.com.br/mcp` ([emissaoja-mcp](https://github.com/Easymovel/emissaoja-mcp))
- Documentação para IAs: [llms.txt](https://emissaoja.com.br/llms.txt) · [docs.md](https://emissaoja.com.br/docs.md)

## In English

Official Python client for the [emissaoja API](https://emissaoja.com.br/docs/): issue Brazilian **NFS-e** (electronic service invoices) through the national **Emissor Nacional** without a digital certificate, for MEI and Simples Nacional companies. Standard library only, typed, idempotent issuing, PDF and XML download, and a free sandbox with a simulated tax authority. The API and the docs are in Portuguese.

---

Suporte: [suporte@emissaoja.com.br](mailto:suporte@emissaoja.com.br). Licença MIT, © 2026 BINOBO LTDA.

O emissaoja é um serviço privado e não tem vínculo com a Receita Federal nem com o Emissor Nacional.
