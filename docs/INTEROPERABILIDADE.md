# Interoperabilidade com MIDICSV

A verificação usa o par **csvmidi/midicsv 1.1**, implementação C da Fourmilab,
separada do Mido utilizado em produção. Os CSVs desta pasta de fixtures foram
escritos para o Mapa MIDI; não contêm músicas, arquivos ou informações de terceiros.

Há duas provas diferentes:

1. `csvmidi` codifica os CSVs originais e `midicsv` decodifica os arquivos gerados.
   O verificador compara todos os eventos estruturais: trilha, índice, tick,
   tipo, canal, contexto de porta e campos. Inclui texto, metadados e digest de
   payload. O hash do arquivo capturado também precisa coincidir.
2. `oracles.json` registra expectativas manuais para os intervalos e seus
   tempos racionais. O teste não usa a produção para gerar essas expectativas.
   Um round trip do consumidor C, sozinho, não prova o pareamento de notas.

## Evidências preservadas

`fixtures/midicsv/records.json` contém data UTC da execução externa real, versão,
SHA-256 do arquivo-fonte do consumidor, ambiente, hashes dos executáveis e dos
artefatos. Os arquivos `.decoded.csv` são saídas reais do executável C.

| Caso original | Formato | Eventos conferidos | Intervalos | O que exercita |
|---|---:|---:|---:|---|
| `exemplo` | 1 | 42 | 13 | Condutora + duas trilhas; 3 andamentos; nota atravessando mudança; pedal observado |
| `edgecases` | 0 | 18 | 5 | PPQN 7, FIFO ambíguo, velocity zero, zero duração, órfãos, notas abertas e troca de porta |
| `shared` | 1 | 10 | 1 | Mesmo canal/porta em trilhas distintas; sem pareamento cruzado; dois andamentos no mesmo tick |
| `metadata` | 0 | 13 | 0 | Texto com controles/aspas/barra, fórmula de compasso, tonalidade, sequência, pressão, pitch bend e payloads opacos |
| `running` | 0 | 7 | 3 | Running status de canal produzido pelo codificador C |

São **90 eventos estruturais e 22 intervalos** nos cinco casos válidos. A
comparação de eventos usa o módulo `csv` da biblioteca padrão para ler a saída
independente; converte a notação octal de texto documentada pelo MIDICSV e as
convenções numéricas necessárias (por exemplo, pitch bend sem sinal para valor
centrado em zero). Não há uso do parser do Mido nessa conversão independente.

O exemplo distribuído em `src/mapa_midi/samples/exemplo.mid` corresponde
exatamente ao arquivo gerado a partir de `fixtures/midicsv/exemplo.csv`. Os rótulos
são ASCII, portanto também UTF-8 estrito. Os dados originais são disponibilizados
sob a licença MIT do projeto.

### Oráculos temporais

No exemplo, PPQN = 480. Os segmentos são 500000 µs/semínima a partir do tick 0,
750000 a partir de 960 e 400000 a partir de 1920. A primeira nota da trilha 1
vai de 0 a 1440: 1 segundo até 960 + 3/4 segundo até 1440 = **7/4 segundo**.
A duração até o último EOT, tick 3840, é **41/10 segundos**.

Na base, o desligamento das notas em 960 fecha os intervalos em 1 segundo,
embora CC64 só seja liberado em 1200. Isso verifica o contrato de mensagens:
não se calcula duração audível nem se estende um intervalo por causa do pedal.
No caso PPQN 7, as duas notas sobrepostas têm duração **1/7 segundo** cada,
pareadas FIFO; a nota com início e fim no tick 7 tem duração zero.

## Reproduzir sem executar o consumidor externo

Depois de instalar o projeto e suas dependências:

```sh
python tools/check_interop.py --offline
python -m unittest tests.test_interop -v
```

Esse modo verifica hashes, fatos e oráculos preservados. A saída informa
`offline_recordings_only`: **não é uma nova execução do MIDICSV**. A suíte comum
não baixa ferramentas nem consulta a rede.

## Executar novamente o consumidor C

Em Linux ou macOS, com compilador C e `make`, use diretórios novos fora do
repositório:

```sh
python tools/fetch_midicsv.py --destino ../midicsv-verificacao
python tools/check_interop.py --live \
  --tool-dir ../midicsv-verificacao/midicsv-1.1 \
  --saida ../midicsv-nova-execucao
```

O primeiro comando baixa o arquivo oficial, exige o SHA-256 fixado abaixo e
compila localmente. Não executa `make install`, não altera o sistema e não inclui
o código externo no pacote MIT. Há uma única adaptação de compilação: remover a
declaração antiga e não utilizada `char *index();` em `getopt.c`, incompatível
com o protótipo fornecido pela glibc atual. A lógica de codificação/decodificação
permanece intacta. Os hashes anterior/posterior da fonte adaptada, os executáveis
e o log do build ficam em `../midicsv-verificacao`.

O segundo comando executa `csvmidi -z -x` e `midicsv` para cada caso válido; no
caso `running`, omite `-x` para gerar a compressão de status. Confere os novos
bytes, todos os fatos e os oráculos, preservando `live-run.json` com identidade
dos executáveis e data da nova execução. `--saida` deve ser um diretório novo.
O job de interoperabilidade do CI executa esse mesmo caminho real.

Fonte externa fixada:

```text
https://www.fourmilab.ch/webtools/midicsv/midicsv-1.1.tar.gz
SHA-256 7c5a749ab5c4ebac4bd7361df0af65892f380245be57c838e08ec6e4ac9870ef
```

## Running status: consumidor não é validador

Dois contraexemplos mínimos, `status-after-meta.mid` e
`status-after-sysex.mid`, mantêm o último status de canal depois de uma mensagem
que o cancela. O MIDICSV 1.1 decodifica ambos permissivamente; essa diferença está
registrada nas respectivas saídas CSV. O Mido 1.3.3 também é permissivo após meta.
O guard do Mapa MIDI rejeita os dois com `invalid_running_status` antes da
construção dos objetos do Mido, conforme a regra normativa de SMF 1.0.

O PDF **Standard MIDI Files 1.0 (RP-001)** foi efetivamente baixado do link
público disponibilizado pelo MIDI.org e consultado: página PDF 9, página impressa
7, seção de sintaxe dos eventos de trilha. A regra estabelece o cancelamento por
meta e SysEx. Identidade do PDF consultado:

```text
SHA-256 fdb65bd58cd92981273468954b46fe7e915b1f8b5697f55eaec0d475895762b8
```

O documento é uma referência externa; não é redistribuído nem relicenciado por
este repositório. As fixtures não conformes são pequenas e deliberadas. O modo
live não submete arquivos arbitrários do usuário ao consumidor C antigo.

Esta verificação comprova os casos e a cobertura descritos. Não demonstra
compatibilidade universal entre sequenciadores, áudio equivalente ou validação
completa do padrão SMF.

## Referências

- [MIDICSV: comandos, formato, código-fonte e limitações](https://www.fourmilab.ch/webtools/midicsv/).
- [MIDI Association — Standard MIDI Files](https://midi.org/standard-midi-files).
- [RP-001 v1.0 — PDF público vinculado pela MIDI Association](https://drive.google.com/file/d/1t4jcCCKoi5HMi7YJ6skvZfKcefLhhOgU/view).
- [Mido — arquivos MIDI](https://mido.readthedocs.io/en/stable/files/midi.html).
