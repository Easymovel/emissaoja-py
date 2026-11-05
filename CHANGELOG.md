# Changelog

## 0.1.0 — 2026-11-05

Primeira versão pública do cliente oficial da API do emissaoja para Python.

- Recursos `empresa`, `tomadores`, `servicos`, `notas`, `emissoes`, `operacoes`, `cnpj` e `status()`.
- `notas.emitir` exige `referencia` (vira o cabeçalho `Idempotency-Key`) e valida o formato antes de chamar a API.
- `notas.aguardar`, `empresa.aguardar_credencial` e `operacoes.aguardar` respeitam `proxima_consulta_ms`.
- Erros da API viram `EmissaojaErro` com `status`, `code`, `extras` e `request_id`; timeout e falha de conexão viram
  `tempo_esgotado` e `rede`.
- Constantes `BASE_PRODUCAO` e `BASE_SANDBOX`. Só biblioteca padrão, Python 3.9+.
