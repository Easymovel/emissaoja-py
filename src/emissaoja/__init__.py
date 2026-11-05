"""emissaoja: cliente oficial da API de NFS-e do emissaoja (https://emissaoja.com.br/docs/).

Emite Nota Fiscal de Serviço eletrônica (NFS-e) no Emissor Nacional (nfse.gov.br) com o CNPJ e a senha do
portal, sem certificado digital, para MEI e empresas do Simples Nacional.

Só biblioteca padrão (urllib). Mesma forma do cliente JavaScript: ``Emissaoja(chave)`` e os
recursos ``empresa``, ``tomadores``, ``servicos``, ``notas``, ``emissoes``, ``operacoes`` e ``cnpj``.
Erros da API viram ``EmissaojaErro`` com ``code`` (a lista fechada da API), ``status`` e ``extras``.

Exemplo no sandbox (Emissor Nacional simulado)::

    from emissaoja import Emissaoja, BASE_SANDBOX

    ej = Emissaoja(base_url=BASE_SANDBOX)  # chave em EMISSAOJA_KEY (ej_test_...)
    tomador = ej.tomadores.criar("12345678000195")["tomador"]
    pedido = ej.notas.emitir("pedido-0001", tomador["tipo"], tomador["id"], 150, descricao="Consultoria")["pedido"]
    final = ej.notas.aguardar(pedido["id"])["pedido"]
"""

from __future__ import annotations

import http.client
import json
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Optional

__all__ = ["Emissaoja", "EmissaojaErro", "BASE_PRODUCAO", "BASE_SANDBOX", "__version__"]
__version__ = "0.1.0"

BASE_PRODUCAO = "https://emissaoja.com.br"
BASE_SANDBOX = "https://sandbox.emissaoja.com.br"
_BASE_PADRAO = BASE_PRODUCAO
_TERMINAIS = {"autorizada", "recusada", "incerta"}
_RE_REFERENCIA = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class EmissaojaErro(Exception):
    """Erro da API (``status`` HTTP, ``code`` da lista fechada, ``extras`` com bloqueios etc.)."""

    def __init__(self, status: int, corpo: Optional[dict] = None, request_id: Optional[str] = None):
        c = corpo if isinstance(corpo, dict) else {}
        super().__init__(c.get("message") or f"HTTP {status}")
        self.status = status
        self.code: str = c.get("code") or "erro_desconhecido"
        self.extras: Dict[str, Any] = {k: v for k, v in c.items() if k not in ("status", "message", "code")}
        self.request_id = request_id


# Transporte: (metodo, url, cabecalhos, corpo_bytes, timeout) -> (status, cabecalhos, bytes). Injetável nos testes.
Transporte = Callable[[str, str, Dict[str, str], Optional[bytes], float], "tuple[int, Dict[str, str], bytes]"]


def _transporte_urllib(metodo: str, url: str, cabecalhos: Dict[str, str], corpo: Optional[bytes], timeout: float):
    req = urllib.request.Request(url, data=corpo, method=metodo, headers=cabecalhos)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:  # noqa: S310 (URL é a da API)
            return res.status, {k.lower(): v for k, v in res.headers.items()}, res.read()
    except urllib.error.HTTPError as e:
        cabecalhos_erro = {k.lower(): v for k, v in e.headers.items()} if e.headers is not None else {}
        return e.code, cabecalhos_erro, e.read()
    except urllib.error.URLError as e:
        if isinstance(e.reason, (TimeoutError, socket.timeout)):
            raise EmissaojaErro(0, {"code": "tempo_esgotado", "message": "A API não respondeu a tempo."}) from e
        raise EmissaojaErro(0, {"code": "rede", "message": str(e.reason)}) from e
    except (TimeoutError, socket.timeout) as e:  # no 3.9, socket.timeout ainda não é TimeoutError
        raise EmissaojaErro(0, {"code": "tempo_esgotado", "message": "A API não respondeu a tempo."}) from e
    except (OSError, http.client.HTTPException) as e:
        raise EmissaojaErro(0, {"code": "rede", "message": str(e) or e.__class__.__name__}) from e


class _Recurso:
    def __init__(self, cliente: "Emissaoja"):
        self._c = cliente


class _Empresa(_Recurso):
    def obter(self) -> dict:
        return self._c._json("GET", "/v1/empresa")

    def conectar(self, cnpj: str, senha: str, ciente_ultima_tentativa: bool = False) -> dict:
        """``PUT /v1/empresa/credencial``: CNPJ e senha do Emissor Nacional → ``{"tentativa": …}``."""
        return self._c._json("PUT", "/v1/empresa/credencial", {"cnpj": cnpj, "senha": senha, "ciente_ultima_tentativa": bool(ciente_ultima_tentativa)})

    def credencial(self) -> dict:
        return self._c._json("GET", "/v1/empresa/credencial")

    def aguardar_credencial(self, intervalo: float = 2.0, timeout: float = 120.0) -> dict:
        """Consulta até ``tentativa.proximo_passo`` sair de ``aguardar``."""
        fim = time.monotonic() + timeout
        while True:
            r = self.credencial()
            t = r.get("tentativa")
            if not t or t.get("proximo_passo") != "aguardar":
                return r
            if time.monotonic() > fim:
                raise EmissaojaErro(0, {"code": "tempo_esgotado", "message": "A verificação da senha não terminou a tempo."})
            self._c._dormir(intervalo)

    def onboarding(self) -> dict:
        return self._c._json("GET", "/v1/empresa/onboarding")

    def fiscal(self, aliquota_simples: Optional[float] = None, reg_ap_trib_sn: Optional[int] = None) -> dict:
        corpo: Dict[str, Any] = {}
        if aliquota_simples is not None:
            corpo["aliquota_simples"] = aliquota_simples
        if reg_ap_trib_sn is not None:
            corpo["reg_ap_trib_sn"] = reg_ap_trib_sn
        return self._c._json("PUT", "/v1/empresa/fiscal", corpo)

    def reler_fisco(self) -> dict:
        return self._c._json("POST", "/v1/empresa/reler-fisco")


class _Tomadores(_Recurso):
    def listar(self, busca: Optional[str] = None, pagina: int = 1, limite: Optional[int] = None, ordem: Optional[str] = None) -> dict:
        return self._c._json("GET", "/v1/tomadores", query={"busca": busca, "pagina": pagina, "limite": limite, "ordem": ordem})

    def buscar(self, q: str) -> dict:
        return self._c._json("GET", "/v1/tomadores/busca", query={"q": q})

    def criar(self, documento: str, nome: Optional[str] = None) -> dict:
        corpo: Dict[str, Any] = {"documento": documento}
        if nome:
            corpo["nome"] = nome
        return self._c._json("POST", "/v1/tomadores", corpo)

    def obter(self, tipo: str, id: str) -> dict:
        return self._c._json("GET", f"/v1/tomadores/{_q(tipo)}/{_q(id)}")

    def atualizar(self, tipo: str, id: str, **campos: Any) -> dict:
        return self._c._json("PUT", f"/v1/tomadores/{_q(tipo)}/{_q(id)}", campos)


class _Servicos(_Recurso):
    def listar(self, ativos: str = "1") -> dict:
        return self._c._json("GET", "/v1/servicos", query={"ativos": ativos})

    def criar(self, **campos: Any) -> dict:
        return self._c._json("POST", "/v1/servicos", campos)

    def atualizar(self, id: str, **campos: Any) -> dict:
        return self._c._json("PUT", f"/v1/servicos/{_q(id)}", campos)

    def desativar(self, id: str) -> dict:
        return self._c._json("DELETE", f"/v1/servicos/{_q(id)}")

    def catalogo(self, q: str, limite: Optional[int] = None) -> dict:
        return self._c._json("GET", "/v1/catalogo/servicos", query={"q": q, "limite": limite})


class _Notas(_Recurso):
    def emitir(self, referencia: str, tomador_tipo: str, tomador_id: str, valor: float, **campos: Any) -> dict:
        """``POST /v1/notas`` com ``Idempotency-Key`` = ``referencia`` (um id seu por nota).

        Devolve ``{"pedido": …, "previa": …}`` (202) ou ``{"pedido": …, "repetido": True}`` (mesma referência).
        """
        if not isinstance(referencia, str) or not _RE_REFERENCIA.match(referencia):
            raise EmissaojaErro(0, {"code": "chave_idempotencia_invalida", "message": "Informe `referencia` (8 a 64 caracteres: letras, números, _ e -), única por nota."})
        corpo = {"tomador_tipo": tomador_tipo, "tomador_id": tomador_id, "valor": valor, **{k: v for k, v in campos.items() if v is not None}}
        return self._c._json("POST", "/v1/notas", corpo, cabecalhos={"Idempotency-Key": referencia})

    def aguardar(self, pedido_id: str, timeout: float = 180.0, intervalo_minimo: float = 1.0) -> dict:
        """Consulta o pedido até ``autorizada``, ``recusada`` ou ``incerta``, respeitando ``proxima_consulta_ms``."""
        fim = time.monotonic() + timeout
        while True:
            r = self._c.emissoes.obter(pedido_id)
            p = r.get("pedido") or {}
            if p.get("estado") in _TERMINAIS:
                return r
            if time.monotonic() > fim:
                raise EmissaojaErro(0, {"code": "tempo_esgotado", "message": "O pedido não terminou a tempo; consulte de novo mais tarde.", "pedido_id": pedido_id})
            self._c._dormir(max(intervalo_minimo, (p.get("proxima_consulta_ms") or 3000) / 1000))

    def listar(self, **query: Any) -> dict:
        return self._c._json("GET", "/v1/notas", query=query)

    def pdf(self, origem: str, id: str) -> bytes:
        return self._c._bytes(f"/v1/notas/{_q(origem)}/{_q(id)}/pdf")

    def xml(self, origem: str, id: str) -> str:
        return self._c._bytes(f"/v1/notas/{_q(origem)}/{_q(id)}/xml").decode("utf-8")

    def cancelar(self, origem: str, id: str, motivo: str, justificativa: Optional[str] = None) -> dict:
        corpo: Dict[str, Any] = {"motivo": str(motivo)}
        if justificativa:
            corpo["justificativa"] = justificativa
        return self._c._json("POST", f"/v1/notas/{_q(origem)}/{_q(id)}/cancelar", corpo)


class _Emissoes(_Recurso):
    def obter(self, id: str) -> dict:
        return self._c._json("GET", f"/v1/emissoes/{_q(id)}")

    def listar(self, estados: Optional[str] = None) -> dict:
        return self._c._json("GET", "/v1/emissoes", query={"estados": estados})

    def conferir(self, id: str) -> dict:
        return self._c._json("POST", f"/v1/emissoes/{_q(id)}/conferir")


class _Operacoes(_Recurso):
    def obter(self, id: str) -> dict:
        return self._c._json("GET", f"/v1/operacoes/{_q(id)}")

    def aguardar(self, id: str, intervalo: float = 2.0, timeout: float = 180.0) -> dict:
        fim = time.monotonic() + timeout
        while True:
            r = self.obter(id)
            if (r.get("operacao") or {}).get("estado") != "processando":
                return r
            if time.monotonic() > fim:
                raise EmissaojaErro(0, {"code": "tempo_esgotado", "message": "A operação não terminou a tempo."})
            self._c._dormir(intervalo)


class _Cnpj(_Recurso):
    def consultar(self, cnpj: str) -> dict:
        return self._c._json("GET", f"/v1/cnpj/{re.sub(r'[^0-9]', '', str(cnpj))}")


class Emissaoja:
    """``Emissaoja(chave)``; ``chave`` omitida lê ``EMISSAOJA_KEY`` na primeira chamada."""

    def __init__(
        self,
        chave: Optional[str] = None,
        base_url: str = _BASE_PADRAO,
        timeout: float = 30.0,
        transporte: Optional[Transporte] = None,
        dormir: Optional[Callable[[float], None]] = None,
    ):
        self._chave = chave
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._transporte = transporte or _transporte_urllib
        self._dormir: Callable[[float], None] = dormir or time.sleep
        self.empresa = _Empresa(self)
        self.tomadores = _Tomadores(self)
        self.servicos = _Servicos(self)
        self.notas = _Notas(self)
        self.emissoes = _Emissoes(self)
        self.operacoes = _Operacoes(self)
        self.cnpj = _Cnpj(self)

    @property
    def chave(self) -> str:
        if self._chave is None:
            env = os.environ.get("EMISSAOJA_KEY")
            if not env:
                raise EmissaojaErro(0, {"code": "chave_invalida", "message": "Informe a chave: Emissaoja(chave) ou a variável EMISSAOJA_KEY."})
            self._chave = env
        return self._chave

    def status(self) -> dict:
        return self._json("GET", "/v1/status", sem_chave=True)

    # ---- transporte ----
    def _req(self, metodo: str, caminho: str, corpo: Any = None, query: Optional[dict] = None, cabecalhos: Optional[dict] = None, sem_chave: bool = False):
        url = self.base_url + caminho
        q = {k: v for k, v in (query or {}).items() if v is not None and v != ""}
        if q:
            url += "?" + urllib.parse.urlencode(q)
        h = {"Accept": "application/json", "User-Agent": f"emissaoja-py/{__version__}", **(cabecalhos or {})}
        if not sem_chave:
            h["Authorization"] = f"Bearer {self.chave}"
        dados = None
        if corpo is not None:
            h["Content-Type"] = "application/json"
            dados = json.dumps(corpo).encode("utf-8")
        return self._transporte(metodo, url, h, dados, self.timeout)

    def _json(self, metodo: str, caminho: str, corpo: Any = None, query: Optional[dict] = None, cabecalhos: Optional[dict] = None, sem_chave: bool = False) -> dict:
        status, h, bytes_ = self._req(metodo, caminho, corpo, query, cabecalhos, sem_chave)
        texto = bytes_.decode("utf-8") if bytes_ else ""
        try:
            dados = json.loads(texto) if texto else None
        except ValueError:
            dados = None
        if status >= 400:
            raise EmissaojaErro(status, dados if isinstance(dados, dict) else {"message": texto[:200] or f"HTTP {status}"}, h.get("x-request-id"))
        return dados if isinstance(dados, dict) else {}

    def _bytes(self, caminho: str) -> bytes:
        status, h, bytes_ = self._req("GET", caminho)
        if status >= 400:
            try:
                dados = json.loads(bytes_.decode("utf-8"))
            except ValueError:
                dados = None
            raise EmissaojaErro(status, dados if isinstance(dados, dict) else None, h.get("x-request-id"))
        return bytes_


def _q(v: Any) -> str:
    return urllib.parse.quote(str(v), safe="")
