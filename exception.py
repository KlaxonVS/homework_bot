class ErrorToSend(Exception):
    pass


class ErrorNotToSend(Exception):
    pass


class SendMessageFailed(ErrorNotToSend):
    pass


class UnexpectedHTTPStatusCodeError(ErrorToSend):
    pass


class UnexpectedTypeError(ErrorToSend):
    pass
