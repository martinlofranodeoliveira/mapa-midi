"""Interface de linha de comando; erros sem o conteúdo do arquivo de entrada."""
import argparse
from importlib.resources import files
import sys

from . import __version__
from .analysis import analyze
from .errors import MidiError
from .publication import publish_bytes
from .reader import read_bytes, read_path
from .reports import prepare_output


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, "Erro [arguments]: argumentos inválidos; consulte --help.\n")


def main(argv=None) -> int:
    parser = _Parser(description="Inspeciona mensagens MIDI localmente, sem reprodução ou dispositivos.")
    parser.add_argument("--version", action="version", version=f"mapa-midi {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspecionar", help="Ler um arquivo SMF tipo 0/1 com PPQN.")
    inspect.add_argument("arquivo", help="Arquivo MIDI local regular.")
    inspect.add_argument("--saida", required=True, help="Novo arquivo de saída; a pasta deve existir.")
    inspect.add_argument("--formato", choices=("bundle", "json", "csv", "markdown"), default="bundle",
                         help="bundle=ZIP completo; csv=ZIP com duas tabelas e manifesto.")
    inspect.add_argument("--charset", choices=("latin1", "utf-8"), default="latin1", help="Codificação explícita dos metadados textuais.")
    example = commands.add_parser("exemplo", help="Gerar um ZIP com MIDI sintético original e todos os relatórios.")
    example.add_argument("--saida", required=True, help="Novo arquivo ZIP; a pasta deve existir.")
    args = parser.parse_args(argv)
    try:
        sample = None
        if args.command == "exemplo":
            sample = files("mapa_midi").joinpath("samples/exemplo.mid").read_bytes()
            snapshot = read_bytes(sample, charset="utf-8")
            output_format = "bundle"
        else:
            snapshot = read_path(args.arquivo, charset=args.charset)
            output_format = args.formato
        report = analyze(snapshot)
        prepared = prepare_output(report, output_format, sample=sample)
        publish_bytes(args.saida, prepared)
        summary = report["summary"]
        print(f"Relatório criado: {summary['track_count']} trilhas, {summary['event_count']} eventos, "
              f"{summary['note_count']} notas, {len(report['diagnostics'])} diagnósticos.")
        return 0
    except MidiError as error:
        print(f"Erro [{error.code}]: {error.message}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrompido; confira se a saída chegou a ser criada.", file=sys.stderr)
        return 130
    except Exception:
        print("Erro [operation_failed]: não foi possível concluir a operação; nenhum conteúdo da entrada foi exibido.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
