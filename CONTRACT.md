# Contrato · Mapa MIDI

CLI/biblioteca Python 3.11+, PT-BR, MIT. Mido 1.3.3 é o decoder central de SMF; Matplotlib 3.11.2 gera rolo de piano SVG/PNG headless. Não abrir portas MIDI, tocar áudio, enviar mensagens, ler dispositivos ou salvar entradas. Relatórios locais JSON, CSV, Markdown e ZIP, com SHA dos bytes capturados. Dados de exemplo são originais e sintéticos, sem música de terceiros.

## Escopo

SMF tipos 0/1 com PPQN positivo; type0 exige uma trilha. Tipo2, divisão SMPTE/zero, tempo zero e mudanças de tempo fora da trilha0 em type1 são rejeitados explicitamente. Nada de inferir equivalência musical, duração audível ou identificação GM de instrumentos. Header extra é contado; não chamar relatório de cópia sem perdas ou validador completo SMF.

Andamento inicial 500000 µs/semínima quando ausente, identificado como default. Tempo no tick T governa os intervalos após T. Várias mudanças no mesmo tick da trilha0: preservar todos os eventos; o mapa derivado usa a última na ordem dessa trilha para o segmento seguinte. Sem relógio: segundos exatos por Fraction, não MidiFile.length nem iteração de MidiFile (que produzem floats/merge). Time signatures são eventos observados, sem cálculo de compassos.

Texto: charset explícito latin1 (default reversível byte→caractere) ou utf-8 estrito. Não inferir encoding. Strings e controles são preservados nos fatos JSON; erros não ecoam valores. SysEx e meta desconhecida exportam tamanho+SHA-256 do payload, não bytes; não interpretar comandos. Programas são números MIDI observados, sem nomes de instrumentos presumidos.

Intervalos derivam de mensagens de nota, por `(track,port,channel,note)` e FIFO; jamais parear entre trilhas. `port=None` significa porta não declarada, separada de valores explícitos. Meta midi_port atualiza o contexto da própria trilha antes dos próximos eventos; mensagens de voz preservam seu channel. Note-on com velocity0 é note-off. Cada note-on positivo gera um objeto de nota, completo ou aberto, com proveniência dos eventos. Não estender notas abertas até o fim do arquivo. Controle64/pedal, sostenuto e channel-mode ficam como fatos/contagens, não estendem/encerram intervalos inferidos.

Diagnosticar overlapping_note_on, unmatched_note_off, open_note e shared_channel_across_tracks (mesmo port/channel lógico usado em trilhas distintas). Sobreposição é pareada FIFO com indicação de ambiguidade; isso não demonstra a voz musical pretendida. Ordem `(tick,track,index)` é somente apresentação reproduzível; não prova ordem física entre trilhas simultâneas.

## Modelos · src/mapa_midi/models.py

Dataclasses frozen, coleções tuple; API validate_snapshot/validate_limits rejeita shapes forjados/mutáveis/inválidos.

- `MidiError(code,message)` em errors.py, ambos strings; mensagem sanitizada.
- `Limits(max_file_bytes=8MiB,max_tracks=128,max_events=200000,max_payload_bytes=262144,max_notes=100000,max_diagnostics=100000,max_ticks=9007199254740991,max_plot_notes=20000,max_plot_tracks=32,max_report_bytes=64MiB)` inteiros positivos, bool recusado.
- `Event(track,index,tick,type,is_meta,port,channel,fields)`: track/index/tick inteiros0+, port None|int0..255, channel None|int0..15; fields tuple[(str, int|str|bool|None|tuple[int,...]),...], chaves únicas ordenadas. Excluir time/type de fields. Floats de metadados (frame_rate) viram texto decimal, não afetam relógio. Payloads opacos só payload_bytes/payload_sha256; meta desconhecida retém type_byte.
- `Track(index,name,end_tick,event_count)` name None|str (primeiro track_name observado); todos os nomes permanecem nos eventos.
- `Snapshot(sha256,size_bytes,format,ppqn,charset,header_extra_bytes,tracks:tuple[Track,...],events:tuple[Event,...])`. Events em ordem de trilha e índice (não merge). indices contíguos0-based por trilha, ticks não decrescentes, último end_of_track exatamente uma vez. Tempo em fields tempo integer1..16777215. Note/controller/program ranges MIDI verificados. Texte UTF8-encodável, controles permitidos como dados.

## Leitor · reader.py

`read_bytes(data:bytes,limits=Limits(),charset='latin1')->Snapshot`, `read_path(path,limits=...,charset=...)->Snapshot`.

Capturar bytes uma vez: arquivo regular, descriptor com fstat antes/depois da mesma API, read limite+1; rejeitar mudança durante captura, não bloquear em pipes. SHA dos bytes, sem promessa de transação sobre caminhos futuros. Sem extrair ou reescrever entrada.

Preflight leve de framing antes do Mido: MThd/MTrk, header6..1024, contagem de tracks/chunks e tamanhos exatos, sem dados finais ignorados; VLQ máximo4bytes, payload limitado, eventcount/ticks limitados antes da criação de objetos. Running-status conforme SMF deve ser verificado com a documentação/consumidor; não inventar regra de cancelamento. Mensagens de canal e meta/SysEx são aceitas; estados de sistema fora desse perfil geram diagnóstico. EOT precisa ser final e único, sem payload extra. Metatipos conhecidos com prefixo insuficiente para os campos deste perfil são recusados antes do Mido, sem sintetizar porta ou número ausente. Extensões após os campos conhecidos podem ser ignoradas pelo decoder conforme SMF; essa normalização não equivale à reprodução de todos os bytes. Esse guard não substitui o decoder Mido; comparar contagens/deltas/ticks de framing com os objetos decodificados para provar cobertura dos eventos. Mido com clip=False e charset escolhido, lendo BytesIO dos mesmos bytes.

## Análise · analysis.py

`analyze(snapshot,limits=Limits())->dict` JSON determinístico, sem paths/clock. Raiz: schema_version1, application_version1.0.0, source{sha256,size_bytes,format,ppqn,charset,header_extra_bytes}, scope{timing,pairing,not_audio,channel_numbering:'zero_based',opaque_payloads:'digest_only'}, tracks, events, tempo_map, notes, diagnostics, summary.

Tempos exatos em qualquer campo temporal: `{numerator:str,denominator:str,decimal:str}` segundos; decimal apresentação9casas half-even, exato nos dois inteiros. Tempo_map segmentos `{tick,tempo_us_per_quarter,start_seconds,source_event:{track,index}|None,default:bool}`. Inicial tick0 sempre; uma mudança real em0 substitui default. Evento no mesmo tick do tempo tem o mesmo instante.

Events JSON: propriedades do Event, fields como dict + seconds. Tracks: propriedades de Track + end_seconds, channels observados, programs observados com tick/index/channel/port/program; nunca presumir programa inicial. Notes: `{track,port,channel,note,note_name,start_event,end_event,start_tick,end_tick,start_seconds,end_seconds,duration_seconds,velocity,release_velocity,off_kind,ambiguous_pairing}`. start/end_event são index0-based na trilha; abertos têm fim/duração/release/off_kind None. C4=60 convenção explícita para note_name. Zero-duration completo é válido. Ordenar notas por track,start_event; diagnósticos por tick,track,index,code (indexNone tratado-1). Cada diagnóstico `{code,track,index,tick,port,channel,note}` com None onde não se aplica.

Summary: duration_ticks=maxendtick, duration_seconds, track_count,event_count,note_count,completed_notes,open_notes,unmatched_note_offs,overlapping_note_ons,shared_channels,control_changes,tempo_changes. Todos os eventos/note-ons cobertos ou erro de recurso antes de retornar; não truncar nem inventar endpoints. Control_changes é contagem total e contagem por control. Tempo_changes conta eventos reais. Shared_channels conta grupos port/channel com voz em várias trilhas e gera diagnóstico por grupo com track/index/tickNone se necessário (ordenarNone antes).

## CLI/relatórios · root

`mapa-midi inspecionar ARQUIVO --saida NOVO [--formato bundle|json|csv|markdown] [--charset latin1|utf-8]`; defaultbundle inclui resumo.json,eventos.csv,notas.csv,resumo.md,rolo.svg,rolo.png,manifesto.json. CSV individual pode ser ZIP só eventos/notas/manifesto para evitar publicação parcial de vários arquivos. `mapa-midi exemplo --saida demo.zip` acrescenta exemplo.mid original. Exit0 completo (mesmo com diagnósticos),2 erro; stdout somente status/contagens, nunca conteúdo. Manifesto SHA/tamanhos, sem hash autorreferente. Relatórios contêm fatos/diagnósticos; nada é transmitido.

Publicar um único arquivo preparado em temporário irmão e link exclusivo sem sobrescrever qualquer destino (inclusive symlink), sem fallback destrutivo. Preparar todos os membros antes de publicar; falha de análise/plot/limite não deixa relatório parcial. JSON com ensure_ascii=False, escapes de controles, sem NaN. CSV UTF8+BOM/CRLF com quoting e proteção de prefixos de fórmula. Markdown escapa dados. Máximo64MiB total de membros/saída.

Plot Matplotlib Agg, fonte padrão local do Matplotlib, figura fixa e limites de tamanho; SVG.fonttype=none (texto, sem incorporar fontes ou recursos externos) e PNG. Cada intervalo completo gera retângulo com gid por track/start_event, zero-duration tem marcador; aberto tem marcador apenas no início (sem duração fabricada). Cores por trilha, legenda e limites32trilhas ativas/20000notas; JSON/CSV/Markdown podem funcionar quando plot excede limite. Tempo-change markers e eixo em segundos de apresentação, posições verificadas contra Fraction nos testes. Título/legenda deixam claro intervalo de mensagens e exclusão de pedal. Rótulos podem ser abreviados/escapados só no gráfico, dados completos ficam no JSON. Arquivo sem notas tem estado vazio legível. Não abrir GUI.

## Interoperabilidade/distribuição

MIDICSV upstream C independente, executar csvmidi→midicsv em exemplos CSV originais, sem músicas de terceiros. Registrar versão/hash do consumidor e comandos; código/licença externa não copiados no pacote. Conferir fatos por CSV independente, tempos racionais e pares por oráculos manuais, não alegar que roundtrip prova toda semântica. Exercitar type0/1, andamento através de nota longa, onzero, sobreposição FIFO, notas abertas/offs órfãos, canais compartilhados/port changes, metadados e rejeições. Fixture packaged src/mapa_midi/samples/exemplo.mid. Verificação offline de registros separada de reexecução real. CI Python3.11–3.14/Linux+Windows3.14, wheel/sdist/RECORD e instalação fora do checkout. Publicar GitHub/release MIT com README PTBR e imagens do exemplo; perfil só PROJETOS-ABERTOS.md/EVIDENCIAS.md, preservar README principal.
