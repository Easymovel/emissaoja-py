"""Emite uma NFS-e de teste no sandbox do emissaoja (Emissor Nacional simulado: nada vai ao fisco).

1. Entre em https://sandbox.emissaoja.com.br com o Google e crie uma chave em Conta → API (começa com ej_test_).
2. pip install emissaoja
3. EMISSAOJA_KEY=ej_test_... python emitir_nfse_sandbox.py
"""

import time

from emissaoja import BASE_SANDBOX, Emissaoja, EmissaojaErro

ej = Emissaoja(base_url=BASE_SANDBOX)  # a chave vem de EMISSAOJA_KEY

try:
    # 1. Conectar a empresa (uma vez). No sandbox, 11111111000191 é um MEI pronto para emitir e qualquer senha serve.
    if ej.empresa.obter()["credencial"]["estado"] != "ativa":
        ej.empresa.conectar("11111111000191", "senha-de-teste")
        print("Credencial:", (ej.empresa.aguardar_credencial().get("tentativa") or {}).get("proximo_passo"))

    # 2. Tomador pelo CNPJ: nome e endereço vêm da Receita Federal.
    tomador = ej.tomadores.criar("12345678000195")["tomador"]

    # 3. Emitir. A referência é o seu id da nota: repetir a mesma nunca emite duas vezes.
    pedido = ej.notas.emitir(
        f"exemplo-{int(time.time())}",
        tomador["tipo"],
        tomador["id"],
        150,
        descricao="Consultoria em marketing digital",
    )["pedido"]

    # 4. Acompanhar até autorizada, recusada ou incerta.
    final = ej.notas.aguardar(pedido["id"])["pedido"]
    print(final["estado"], final.get("numero"), final.get("chave_acesso"))

    # 5. Baixar o PDF (DANFSe) e o XML.
    if final["estado"] == "autorizada":
        nota = final["nota"]
        with open(f"nfse-{final['numero']}.pdf", "wb") as f:
            f.write(ej.notas.pdf(nota["origem"], nota["id"]))
        with open(f"nfse-{final['numero']}.xml", "w", encoding="utf-8") as f:
            f.write(ej.notas.xml(nota["origem"], nota["id"]))
except EmissaojaErro as e:
    print(e.status, e.code, e, e.extras.get("bloqueios", ""))
    raise SystemExit(1)
