# Casos originais e registros do consumidor independente

Todos os CSVs de entrada foram escritos especificamente para este projeto, sem
músicas de terceiros, e estão sob a licença MIT do repositório. Cada `.mid`
válido foi produzido pelo `csvmidi` C 1.1; `.decoded.csv` é a saída real de
`midicsv` 1.1. Não se usa o Mido para gerar esses arquivos.

Os dois `status-after-*.mid` são contraexemplos não conformes mínimos escritos
em bytes, para documentar uma permissividade do consumidor C: depois de um
note-on explícito, inserem meta texto ou SysEx e em seguida dados de canal sem
novo status. A sintaxe de blocos continua completa, mas o guard os rejeita.
Não são exemplos aceitos para uso musical.

`oracles.json` contém expectativas manuais de intervalos e tempos; `records.json`
identifica execução, ferramentas e checksums. Ver a metodologia e os comandos
em [INTEROPERABILIDADE.md](../../docs/INTEROPERABILIDADE.md). O consumidor e seu
código-fonte permanecem externos; não fazem parte do pacote distribuído.
