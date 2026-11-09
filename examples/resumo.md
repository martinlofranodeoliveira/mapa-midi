# Mapa MIDI · relatório de mensagens

SHA-256 da captura: `8407f47bf973569edad2cfb45a4ec4b790de0f29e41e007e41c1330040d372b8`. Formato 1; 480 ticks por semínima; charset utf-8.

3 trilhas · 42 eventos · 13 note-ons positivos · 13 intervalos completos · 0 abertos.
Fim das trilhas: 41/10 s (4.100000000 s); 3840 ticks.

## Como ler

Segundos racionais exatos; PPQN, andamento explícito ou padrão inicial de 500000 µs/semínima\.
FIFO por trilha/porta/canal/nota; ordem simultânea entre trilhas não é uma ordem física\. C4=60\.
Intervalos entre mensagens, não duração audível; pedal, sostenuto e modos de canal não prolongam nem encerram notas\.
zero\_based
digest\_only

Os numeradores e denominadores são os tempos exatos; os decimais têm nove casas, arredondamento para o par. Trilhas, canais e índices começam em zero. Campos textuais são escapados nesta apresentação; o JSON preserva os dados.

## Trilhas e programas observados

| Trilha | Nome | Eventos | Fim | Canais | Programas observados |
| --- | --- | --- | --- | --- | --- |
| 0 | Estudo original \- mapa de mensagens | 6 | 41/10 s \(4\.100000000 s\) | \[\] | \[\] |
| 1 | Linha principal | 18 | 41/10 s \(4\.100000000 s\) | \[0\] | \[\{&quot;tick&quot;: 0, &quot;index&quot;: 2, &quot;port&quot;: 0, &quot;channel&quot;: 0, &quot;program&quot;: 12\}\] |
| 2 | Base e pedal observado | 18 | 41/10 s \(4\.100000000 s\) | \[1\] | \[\{&quot;tick&quot;: 0, &quot;index&quot;: 2, &quot;port&quot;: 0, &quot;channel&quot;: 1, &quot;program&quot;: 4\}\] |

## Mapa de andamento

| Tick | µs por semínima | Início | Evento de origem | Padrão |
| --- | --- | --- | --- | --- |
| 0 | 500000 | 0/1 s \(0\.000000000 s\) | \{&\#x27;track&\#x27;: 0, &\#x27;index&\#x27;: 2\} | False |
| 960 | 750000 | 1/1 s \(1\.000000000 s\) | \{&\#x27;track&\#x27;: 0, &\#x27;index&\#x27;: 3\} | False |
| 1920 | 400000 | 5/2 s \(2\.500000000 s\) | \{&\#x27;track&\#x27;: 0, &\#x27;index&\#x27;: 4\} | False |

## Intervalos entre mensagens de nota

| Trilha | Porta | Canal | Nota | Eventos início/fim | Ticks início/fim | Início | Fim | Duração | Velocidade | Release | Off | Ambíguo |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0 | 0 | C4 | 3/4 | 0/1440 | 0/1 s \(0\.000000000 s\) | 7/4 s \(1\.750000000 s\) | 7/4 s \(1\.750000000 s\) | 90 | 36 | note\_off | False |
| 1 | 0 | 0 | E4 | 5/6 | 1440/1920 | 7/4 s \(1\.750000000 s\) | 5/2 s \(2\.500000000 s\) | 3/4 s \(0\.750000000 s\) | 85 | 0 | note\_on\_zero | False |
| 1 | 0 | 0 | G4 | 7/8 | 1920/2400 | 5/2 s \(2\.500000000 s\) | 29/10 s \(2\.900000000 s\) | 2/5 s \(0\.400000000 s\) | 92 | 0 | note\_off | False |
| 1 | 0 | 0 | A4 | 9/10 | 2400/2640 | 29/10 s \(2\.900000000 s\) | 31/10 s \(3\.100000000 s\) | 1/5 s \(0\.200000000 s\) | 80 | 0 | note\_off | False |
| 1 | 0 | 0 | G4 | 11/12 | 2640/2880 | 31/10 s \(3\.100000000 s\) | 33/10 s \(3\.300000000 s\) | 1/5 s \(0\.200000000 s\) | 82 | 0 | note\_off | False |
| 1 | 0 | 0 | E4 | 13/14 | 2880/3360 | 33/10 s \(3\.300000000 s\) | 37/10 s \(3\.700000000 s\) | 2/5 s \(0\.400000000 s\) | 88 | 0 | note\_off | False |
| 1 | 0 | 0 | C4 | 15/16 | 3360/3840 | 37/10 s \(3\.700000000 s\) | 41/10 s \(4\.100000000 s\) | 2/5 s \(0\.400000000 s\) | 76 | 0 | note\_off | False |
| 2 | 0 | 1 | C3 | 4/6 | 0/960 | 0/1 s \(0\.000000000 s\) | 1/1 s \(1\.000000000 s\) | 1/1 s \(1\.000000000 s\) | 72 | 0 | note\_off | False |
| 2 | 0 | 1 | G3 | 5/7 | 0/960 | 0/1 s \(0\.000000000 s\) | 1/1 s \(1\.000000000 s\) | 1/1 s \(1\.000000000 s\) | 65 | 0 | note\_off | False |
| 2 | 0 | 1 | D3 | 9/11 | 1920/2880 | 5/2 s \(2\.500000000 s\) | 33/10 s \(3\.300000000 s\) | 4/5 s \(0\.800000000 s\) | 74 | 0 | note\_off | False |
| 2 | 0 | 1 | A3 | 10/12 | 1920/2880 | 5/2 s \(2\.500000000 s\) | 33/10 s \(3\.300000000 s\) | 4/5 s \(0\.800000000 s\) | 67 | 0 | note\_off | False |
| 2 | 0 | 1 | C3 | 13/15 | 2880/3840 | 33/10 s \(3\.300000000 s\) | 41/10 s \(4\.100000000 s\) | 4/5 s \(0\.800000000 s\) | 70 | 0 | note\_off | False |
| 2 | 0 | 1 | G3 | 14/16 | 2880/3840 | 33/10 s \(3\.300000000 s\) | 41/10 s \(4\.100000000 s\) | 4/5 s \(0\.800000000 s\) | 64 | 0 | note\_off | False |

## Diagnósticos

Nenhum dos diagnósticos implementados foi observado. Isso não comprova conformidade MIDI completa.

## Todos os eventos

| Trilha | Índice | Tick | Segundos | Tipo | Porta | Canal | Campos |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 0 | 0 | 0/1 s \(0\.000000000 s\) | track\_name | — | — | \{&quot;name&quot;: &quot;Estudo original \- mapa de mensagens&quot;\} |
| 0 | 1 | 0 | 0/1 s \(0\.000000000 s\) | time\_signature | — | — | \{&quot;clocks\_per\_click&quot;: 24, &quot;denominator&quot;: 4, &quot;notated\_32nd\_notes\_per\_beat&quot;: 8, &quot;numerator&quot;: 4\} |
| 0 | 2 | 0 | 0/1 s \(0\.000000000 s\) | set\_tempo | — | — | \{&quot;tempo&quot;: 500000\} |
| 0 | 3 | 960 | 1/1 s \(1\.000000000 s\) | set\_tempo | — | — | \{&quot;tempo&quot;: 750000\} |
| 0 | 4 | 1920 | 5/2 s \(2\.500000000 s\) | set\_tempo | — | — | \{&quot;tempo&quot;: 400000\} |
| 0 | 5 | 3840 | 41/10 s \(4\.100000000 s\) | end\_of\_track | — | — | \{\} |
| 1 | 0 | 0 | 0/1 s \(0\.000000000 s\) | track\_name | — | — | \{&quot;name&quot;: &quot;Linha principal&quot;\} |
| 1 | 1 | 0 | 0/1 s \(0\.000000000 s\) | midi\_port | — | — | \{&quot;port&quot;: 0\} |
| 1 | 2 | 0 | 0/1 s \(0\.000000000 s\) | program\_change | 0 | 0 | \{&quot;program&quot;: 12\} |
| 1 | 3 | 0 | 0/1 s \(0\.000000000 s\) | note\_on | 0 | 0 | \{&quot;note&quot;: 60, &quot;velocity&quot;: 90\} |
| 1 | 4 | 1440 | 7/4 s \(1\.750000000 s\) | note\_off | 0 | 0 | \{&quot;note&quot;: 60, &quot;velocity&quot;: 36\} |
| 1 | 5 | 1440 | 7/4 s \(1\.750000000 s\) | note\_on | 0 | 0 | \{&quot;note&quot;: 64, &quot;velocity&quot;: 85\} |
| 1 | 6 | 1920 | 5/2 s \(2\.500000000 s\) | note\_on | 0 | 0 | \{&quot;note&quot;: 64, &quot;velocity&quot;: 0\} |
| 1 | 7 | 1920 | 5/2 s \(2\.500000000 s\) | note\_on | 0 | 0 | \{&quot;note&quot;: 67, &quot;velocity&quot;: 92\} |
| 1 | 8 | 2400 | 29/10 s \(2\.900000000 s\) | note\_off | 0 | 0 | \{&quot;note&quot;: 67, &quot;velocity&quot;: 0\} |
| 1 | 9 | 2400 | 29/10 s \(2\.900000000 s\) | note\_on | 0 | 0 | \{&quot;note&quot;: 69, &quot;velocity&quot;: 80\} |
| 1 | 10 | 2640 | 31/10 s \(3\.100000000 s\) | note\_off | 0 | 0 | \{&quot;note&quot;: 69, &quot;velocity&quot;: 0\} |
| 1 | 11 | 2640 | 31/10 s \(3\.100000000 s\) | note\_on | 0 | 0 | \{&quot;note&quot;: 67, &quot;velocity&quot;: 82\} |
| 1 | 12 | 2880 | 33/10 s \(3\.300000000 s\) | note\_off | 0 | 0 | \{&quot;note&quot;: 67, &quot;velocity&quot;: 0\} |
| 1 | 13 | 2880 | 33/10 s \(3\.300000000 s\) | note\_on | 0 | 0 | \{&quot;note&quot;: 64, &quot;velocity&quot;: 88\} |
| 1 | 14 | 3360 | 37/10 s \(3\.700000000 s\) | note\_off | 0 | 0 | \{&quot;note&quot;: 64, &quot;velocity&quot;: 0\} |
| 1 | 15 | 3360 | 37/10 s \(3\.700000000 s\) | note\_on | 0 | 0 | \{&quot;note&quot;: 60, &quot;velocity&quot;: 76\} |
| 1 | 16 | 3840 | 41/10 s \(4\.100000000 s\) | note\_off | 0 | 0 | \{&quot;note&quot;: 60, &quot;velocity&quot;: 0\} |
| 1 | 17 | 3840 | 41/10 s \(4\.100000000 s\) | end\_of\_track | 0 | — | \{\} |
| 2 | 0 | 0 | 0/1 s \(0\.000000000 s\) | track\_name | — | — | \{&quot;name&quot;: &quot;Base e pedal observado&quot;\} |
| 2 | 1 | 0 | 0/1 s \(0\.000000000 s\) | midi\_port | — | — | \{&quot;port&quot;: 0\} |
| 2 | 2 | 0 | 0/1 s \(0\.000000000 s\) | program\_change | 0 | 1 | \{&quot;program&quot;: 4\} |
| 2 | 3 | 0 | 0/1 s \(0\.000000000 s\) | control\_change | 0 | 1 | \{&quot;control&quot;: 64, &quot;value&quot;: 127\} |
| 2 | 4 | 0 | 0/1 s \(0\.000000000 s\) | note\_on | 0 | 1 | \{&quot;note&quot;: 48, &quot;velocity&quot;: 72\} |
| 2 | 5 | 0 | 0/1 s \(0\.000000000 s\) | note\_on | 0 | 1 | \{&quot;note&quot;: 55, &quot;velocity&quot;: 65\} |
| 2 | 6 | 960 | 1/1 s \(1\.000000000 s\) | note\_off | 0 | 1 | \{&quot;note&quot;: 48, &quot;velocity&quot;: 0\} |
| 2 | 7 | 960 | 1/1 s \(1\.000000000 s\) | note\_off | 0 | 1 | \{&quot;note&quot;: 55, &quot;velocity&quot;: 0\} |
| 2 | 8 | 1200 | 11/8 s \(1\.375000000 s\) | control\_change | 0 | 1 | \{&quot;control&quot;: 64, &quot;value&quot;: 0\} |
| 2 | 9 | 1920 | 5/2 s \(2\.500000000 s\) | note\_on | 0 | 1 | \{&quot;note&quot;: 50, &quot;velocity&quot;: 74\} |
| 2 | 10 | 1920 | 5/2 s \(2\.500000000 s\) | note\_on | 0 | 1 | \{&quot;note&quot;: 57, &quot;velocity&quot;: 67\} |
| 2 | 11 | 2880 | 33/10 s \(3\.300000000 s\) | note\_off | 0 | 1 | \{&quot;note&quot;: 50, &quot;velocity&quot;: 0\} |
| 2 | 12 | 2880 | 33/10 s \(3\.300000000 s\) | note\_off | 0 | 1 | \{&quot;note&quot;: 57, &quot;velocity&quot;: 0\} |
| 2 | 13 | 2880 | 33/10 s \(3\.300000000 s\) | note\_on | 0 | 1 | \{&quot;note&quot;: 48, &quot;velocity&quot;: 70\} |
| 2 | 14 | 2880 | 33/10 s \(3\.300000000 s\) | note\_on | 0 | 1 | \{&quot;note&quot;: 55, &quot;velocity&quot;: 64\} |
| 2 | 15 | 3840 | 41/10 s \(4\.100000000 s\) | note\_off | 0 | 1 | \{&quot;note&quot;: 48, &quot;velocity&quot;: 0\} |
| 2 | 16 | 3840 | 41/10 s \(4\.100000000 s\) | note\_off | 0 | 1 | \{&quot;note&quot;: 55, &quot;velocity&quot;: 0\} |
| 2 | 17 | 3840 | 41/10 s \(4\.100000000 s\) | end\_of\_track | 0 | — | \{\} |

