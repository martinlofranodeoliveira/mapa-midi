# Validação e limites da evidência

## Leitura e análise

Os testes usam entradas binárias pequenas e originais para verificar framing, contagens, ticks, proveniência, codificação de texto e limites antes da decodificação. Mido 1.3.3 recebe os mesmos bytes capturados; as trilhas não são mescladas. A captura de arquivo regular usa descritor somente para leitura e compara `fstat` antes/depois; pipes são recusados sem aguardar um escritor nas plataformas com `O_NONBLOCK`.

Oráculos racionais verificam o tempo inicial padrão, mudanças no mesmo tick, notas que atravessam mudanças, valores não representáveis exatamente como float e arredondamento decimal para o par. O pareamento tem testes de porta/canal/trilha, sobreposição FIFO, início sem fim, fim sem início e duração zero. Controladores não mudam os intervalos.

Os modelos imutáveis também são validados na entrada da análise. Isso verifica estrutura, ranges e consistência interna; não demonstra que um objeto construído manualmente veio do arquivo cujo hash ele declara.

Uma revisão independente reproduziu a inferência de porta zero pelo Mido a partir de FF21 sem byte de porta. O guard deste perfil recusa prefixos insuficientes antes do decoder, sem transformar preenchimento padrão em fato observado. Bytes de extensão além de campos conhecidos continuam permitidos e podem ser ignorados pelo Mido conforme SMF; não se afirma que o relatório reconstrói a captura inteira.

## Consumidor independente

O ensaio executou os programas C **csvmidi e midicsv 1.1**, sem Mido na geração/decodificação externa. Cinco casos válidos cobrem 90 eventos e 22 notas com expectativas manuais de pares e tempo. Dois contraexemplos registram a permissividade do consumidor para running status após meta/SysEx, comparada à regra normativa aplicada pelo guard.

[INTEROPERABILIDADE.md](INTEROPERABILIDADE.md) explica o build, a adaptação de portabilidade e os comandos. `--offline` só verifica registros duráveis; não deve ser descrito como nova execução do consumidor.

## Gráfico e relatórios

As posições de retângulos e marcadores são verificadas contra tempos racionais escolhidos manualmente. O PNG tem 1440 × 960 pixels; o SVG contém texto, sem imagens ou fontes externas. O gráfico do exemplo foi aberto e inspecionado visualmente. A plotagem usa ponto flutuante para apresentação; o JSON conserva a fração exata. O artefato é um rolo de piano estático, não uma partitura ou execução sonora.

Testes de relatórios conferem controles de texto, escaping Markdown, prefixos CSV, manifesto, notas abertas e resultado completo. Falha de plotagem não produz um ZIP parcial. Na publicação, um link exclusivo do temporário impede sobrescrever arquivo ou symlink existente; falhas limpam apenas o temporário.

## Distribuição

O workflow executa os testes, build, verificação de wheel/sdist/RECORD e instalação em ambiente novo nas combinações Linux/Python 3.11, 3.12, 3.13, 3.14 e Windows/Python 3.14. Um job Linux compila novamente o consumidor C e executa o ensaio externo. O estado de cada execução fica em [Actions](https://github.com/martinlofranodeoliveira/mapa-midi/actions).

`scripts/check_release.py` compara os arquivos de execução e os recursos do wheel com a árvore fonte, verifica hashes RECORD e confere o conteúdo do sdist. `scripts/check_installed.py` instala o wheel fora do checkout, executa o comando de exemplo e inspeciona novamente seu MIDI. Confere 13 intervalos, a duração 7/4 s da nota longa, gráficos, CSV, manifesto e preservação de destino já existente.

O exemplo publicado em `examples/` foi extraído do ZIP produzido pela CLI. Seus relatórios são dados originais do projeto, sem gravações ou composições de terceiros. Não há PyPI, serviço hospedado, telemetria ou acesso a dispositivos configurado neste projeto.

## O que não foi demonstrado

Essas verificações cobrem o subconjunto documentado, sem provar conformidade com todos os arquivos SMF existentes, todas as implementações de SysEx ou todos os sintetizadores. A análise não recupera vozes musicais intencionais e não calcula duração audível. Não houve execução em equipamento MIDI nem teste em macOS. Fontes e versões de renderização podem mudar pixels; o relógio racional e os fatos não dependem dessa aparência.
