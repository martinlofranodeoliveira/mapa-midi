"""Erros públicos com mensagens que não incluem o conteúdo da entrada."""


class MidiError(Exception):
    """Falha de entrada, limite ou operação; ``code`` é estável para automação."""

    def __init__(self, code: str, message: str) -> None:
        if type(code) is not str or type(message) is not str:
            raise TypeError("Código e mensagem devem ser strings.")
        self.code = code
        self.message = message
        super().__init__(message)
